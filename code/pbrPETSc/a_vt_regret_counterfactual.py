#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写法一的两个决定性检查。

背景
----
闸门显示 l15/l20 是「识别失败且遗憾不可忽略」（6.5%/9.0%）。但那个 6.5%/9.0%
是用**相位扫描表**在预热窗上估 K^ 得到的，而相位扫描表在 t<=B0 的 age>=1 覆盖
（fx: age1 有 6 帧）是**扫描锚点 A=6 的结构**，不是在线策略看到的东西。

在线策略在预热期 `if t < B0: rebuild=True`，即每步都重建 → 年龄从未超过 1。
所以它到 t=B0 时刻的知识库里到底有多少条老化样本，必须直接测，不能拿相位表代替。

检查 A：B0 时刻的知识库规模（全部 7 配置）
    若 |know| 恒为 1，则「预热期无法识别 K>1」是**结构性**的，不是统计结论。

检查 B：反事实 —— 把预热窗加长，K^ 会不会变对、遗憾会不会消失
    B0' ∈ {100,150,200,300}：用前 B0' 帧估 K^，在 t>B0' 上算遗憾。
    · 若加长后 K^ 变成 3 且遗憾跌到 <1% → 缺的是**观测长度**（写法一成立）
    · 若 K^ 一直是 2 → 缺的不是长度，是年龄–相位混叠（回到方向一）
    这一步只用现有表，无需新求解器。

判读写死：检查 B 若在任一配置上显示"加长到 300 帧仍估错"，则该配置不能作为
「延长预热就能解决」的证据。
"""
import collections
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import Env, ORDER, load_phase  # noqa: E402

KMAX = 7
CUTS = (100, 150, 200, 300)
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_counterfactual.json")


def frame_costs(tab, t, kmax=KMAX):
    out = {}
    for K in range(1, kmax + 1):
        vals = [tab.get((t, a)) for a in range(K)]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def warmup_knowledge(tab, rho, B0):
    """复刻 sim_online_detail 的预热段，返回 t=B0+1 首个决策时的 know 规模。"""
    env = Env(tab, sFact=1.0)
    know = collections.defaultdict(list)
    levels = []
    a = 0
    held = -1
    acc = accn = 0.0
    tot = 0.0
    first = None
    for t in range(1, B0 + 2):
        rc1 = rho
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc / accn if accn else tot / max(1, t - 1)
            lvl = levels[-1]
            delta = st.median(know[age]) if (age in know and know[age]) else 0.0
            rebuild = lvl + max(0.0, delta) > avg
            first = {"t": t, "age": age, "n_know_ages": len(know),
                     "know": {k: len(v) for k, v in know.items()},
                     "levels_seen": len(levels)}
        if rebuild:
            N = env(t, 0)
            tot += rc1 + N
            acc, accn = (0.0, 0) if t < B0 else (rc1 + N, 1)
            levels.append(N)
            a = 1
            held = t
        else:
            N = env(t, a)
            tot += N
            acc += N
            accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9:
                    know[a].append(N - bm)
            a += 1
    return first


def main():
    out = {"kind": "VT_regret_counterfactual", "cuts": list(CUTS), "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        ts = sorted({x for (x, _a) in tab})
        pf = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if pf[t]]

        entry = {"rho": round(rho, 4), "B0": B0,
                 "knowledge_at_B0": warmup_knowledge(tab, rho, B0),
                 "counterfactual": {}}

        # 检查 B：用前 cut 帧估 K^（只用 K 可观测的帧），在 t>cut 且 K 全可观测的帧上算遗憾
        for cut in CUTS:
            est = {}
            for K in range(1, KMAX + 1):
                vals = [pf[t][K] + rho / K for t in usable if t <= cut and K in pf[t]]
                if vals:
                    est[K] = st.mean(vals)
            if not est:
                entry["counterfactual"][str(cut)] = {"error": "no est frames"}
                continue
            k_hat = min(est, key=lambda K: est[K])
            eval_ts = [t for t in usable if t > cut and len(pf[t]) == KMAX]
            if len(eval_ts) < 20:
                entry["counterfactual"][str(cut)] = {
                    "k_hat": k_hat, "error": "too few eval frames", "n": len(eval_ts)}
                continue
            c_fix = sum(pf[t][k_hat] + rho / k_hat for t in eval_ts)
            c_or = sum(min(pf[t][K] + rho / K for K in pf[t]) for t in eval_ts)
            best_fix = min(range(1, KMAX + 1),
                           key=lambda K: sum(pf[t][K] + rho / K for t in eval_ts))
            entry["counterfactual"][str(cut)] = {
                "k_hat": k_hat, "n_eval": len(eval_ts),
                "t_range": [eval_ts[0], eval_ts[-1]],
                "k_best_fixed": best_fix,
                "regret_over_oracle_pct": round(100 * (c_fix - c_or) / c_or, 4),
                "k_hat_is_correct": k_hat == best_fix,
                "est_samples_per_K": {str(K): sum(1 for t in usable if t <= cut and K in pf[t])
                                      for K in range(1, 4)},
            }
        out["cases"][tag] = entry
        kb = entry["knowledge_at_B0"]
        print("%-5s B0=%d 首次决策 t=%s age=%s |know|=%s know=%s levels=%s"
              % (tag, B0, kb["t"], kb["age"], kb["n_know_ages"], kb["know"], kb["levels_seen"]))
        for cut in CUTS:
            c = entry["counterfactual"].get(str(cut), {})
            print("      cut=%-4d K^=%-2s best=%-2s ok=%-5s regret=%-8s n_eval=%-4s samples=%s"
                  % (cut, c.get("k_hat"), c.get("k_best_fixed"), c.get("k_hat_is_correct"),
                     c.get("regret_over_oracle_pct"), c.get("n_eval"), c.get("est_samples_per_K")))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
