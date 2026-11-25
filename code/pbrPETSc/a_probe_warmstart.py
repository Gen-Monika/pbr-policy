#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测式热启动（probe warm start）的收益测量。

要判定的句子
------------
把"预热期多等一会儿"换成"预热末尾做一次受控复用探测（强制重建一次后强制复用 L 步）"，
能否在同样的预热预算下，把在线策略相对事后最优固定 K 的遗憾收回来？
且收益不能由一个更长的固定预热复现。

为什么怀疑它划算
----------------
现行预热每步重建：一步代价 = ρ·s + N(t,0)。在高 ρ 区制下花的是最贵的操作，
买的却是每步重复测的同一个量 N(t,0)；年龄 ≥2 的观测一条也拿不到
（这就是 t=B0+1 时 know={1:1} 的来源）。
探测 L 步的代价 = Σ_{a=1..L} N(t,a)，通常是重建的 20%–40%（fx/L=3：199 vs 614）。
=> 更便宜，且产出的正是缺的信息。

三条对照（缺一不可）
--------------------
  A 现行在线：B0=100，预热每步重建，之后正常判据。
  B 固定更长预热：B0=200，预热每步重建 —— **最关键的对照**。
    若探测的收益能被它复现，结论是"B0 该取大"，不是新机制。
  C 探测：B0=100 预热 → 强制重建一次 → 强制复用 L 步 → 恢复正常判据。
  oracle：反事实 cut=170/160 的 0.11%/0.14%（不可部署，仅作上界参照）。

度量
----
* **全程总成本** = Σ iters + ρ·s·重建数（含预热与探测本身的代价）。
* **遗憾** = (总成本 − 同窗口事后最优固定 K 的总成本) / 事后最优固定 K 的总成本。
  分母与既有闸门一致（`sim_fixed` 在同一窗口上重算）。
* 同时报探测后估出的 K̂ 与后期是否漂回。

安全性的边界（必须随结果一起读）
--------------------------------
相位表只提供 N(t,a)，**看不到 GCR 触顶、残差发散、NaN**。
所以本轮测的是"收益上界"，不是"可部署方案"。
强制复用 L 步在真实求解器上可能触发迭代上限（Elmer B0=20 的先例），
这一风险本轮无法测量，必须在真机小批验证前不得下结论。

审计边界
--------
不改 pbrcost.py、不改论文、不跑求解器、不改判据形式与 ρ 口径。
L 是新引入的设计量；若收益依赖逐算例调 L，必须如实报告为超参数。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, Env, load_phase, sim_fixed, sim_online_detail  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_probe_warmstart.json")
L_LIST = (2, 3, 4, 5, 6)
B0_BASE = 100
B0_LONG = 200


def online_core(env, rho, T, t_start, know0=None, levels0=None):
    """从 t_start 起跑正常判据；t_start 之前一律不计（由调用方单独累计）。

    know0 / levels0 允许注入探测得到的历史。acc/accn 从 t_start 重新起算，
    因为探测结束等价于"刚做过一次重建"。
    """
    know = {} if know0 is None else {k: list(v) for k, v in know0.items()}
    levels = [] if levels0 is None else list(levels0)
    it = 0.0
    rb = 0
    a = 0
    acc = 0.0
    accn = 0
    held = -1
    tot = 0.0
    for t in range(t_start, T + 1):
        rc1 = rho            # ★ 与 sim_fixed 同口径
        if held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc / accn if accn else tot / max(1, t - t_start + 1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2 - d1) / max(1e-9, a2 - a1) * (age - a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0)
            it += N
            rb += 1
            tot += rc1 + N
            acc, accn = rc1 + N, 1
            levels.append(N)
            a = 1
            held = t
        else:
            N = env(t, a)
            it += N
            tot += N
            acc += N
            accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9:
                    know.setdefault(a, []).append(N - bm)
            a += 1
    return tot, it, rb, know


def probe_variant(env, rho, T, B0, L):
    """B0 段每步重建 → 在 B0+1 强制重建 → 之后强制复用 L 步 → 恢复正常判据。"""
    know = {}
    levels = []
    it = 0.0
    rb = 0
    tot = 0.0
    held = -1
    probe_end = B0 + 1 + L
    for t in range(1, probe_end + 1):
        rc1 = rho            # ★ 与 sim_fixed 同口径：一次重建记 ρ，不乘 sFact
        if t <= B0 or t == B0 + 1:
            N = env(t, 0)
            it += N
            rb += 1
            tot += rc1 + N
            levels.append(N)
            held = t
        else:
            age = t - held
            N = env(t, age)
            it += N
            tot += N
            if levels:
                bm = st.median(levels)
                if bm > 1e-9:
                    know.setdefault(age, []).append(N - bm)
    # 探测结束后的状态：acc/accn 重置（与重建后的口径一致），继续
    rest_tot, rest_it, rest_rb, _ = online_core(
        env, rho, T, probe_end + 1, know0=know, levels0=levels)
    return tot + rest_tot, it + rest_it, rb + rest_rb, know


def online_detail_no_s(env, rho, T, B0, **kw):
    """sim_online_detail 但 cost 用 rho*rb（与 sim_fixed 同口径），供分母对齐。"""
    c, it, rb, pred, mv = sim_online_detail(env, rho, T, B0, step_cost=False, **kw)
    return c, it, rb


def best_fixed_on_window(env, rho, T, B0, Ks=range(1, 8)):
    out = {}
    for K in Ks:
        try:
            c, _it, _rb = sim_fixed(env, rho, K, T, B0)
            out[K] = c
        except Exception:                            # noqa: BLE001
            continue
    if not out:
        return None, None
    bk = min(out, key=lambda k: out[k])
    return bk, out[bk]


def main():
    out = {"kind": "probe_warmstart", "L_list": list(L_LIST),
           "note": "相位表不含 GCR 触顶/发散信息；本轮只测收益上界，不是可部署方案",
           "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                     # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        tab, rho, T = ph["tab"], ph["r1"], ph["T"]
        env = Env(tab, sFact=ph["s"])

        # A：现行
        cA, itA, rbA = online_detail_no_s(env, rho, T, B0_BASE)
        # B：固定更长预热
        cB, itB, rbB = online_detail_no_s(env, rho, T, B0_LONG)
        # 分母
        bk, cfx = best_fixed_on_window(env, rho, T, B0_BASE)

        entry = {"rho": round(rho, 4), "T": T, "sFact": round(ph["s"], 3),
                 "best_fixed_K": bk, "best_fixed_cost": round(cfx, 1) if cfx else None,
                 "A_current": {"cost": round(cA, 1), "rebuilds": rbA,
                               "regret_pct": round(100 * (cA - cfx) / cfx, 3) if cfx else None},
                 "B_long_warmup": {"cost": round(cB, 1), "rebuilds": rbB,
                                   "regret_pct": round(100 * (cB - cfx) / cfx, 3) if cfx else None},
                 "probe": {}}
        for L in L_LIST:
            cC, itC, rbC, know = probe_variant(env, rho, T, B0_BASE, L)
            entry["probe"][str(L)] = {
                "cost": round(cC, 1), "rebuilds": rbC,
                "regret_pct": round(100 * (cC - cfx) / cfx, 3) if cfx else None,
                "vs_A_pct": round(100 * (cC - cA) / cA, 3),
                "vs_B_pct": round(100 * (cC - cB) / cB, 3),
                "know_ages": sorted(know),
                "n_known_ge2": sum(1 for k in know if k >= 2),
            }
        out["cases"][tag] = entry
        e = entry
        best_L = min(e["probe"], key=lambda k: e["probe"][k]["cost"])
        print("%-5s bestfix K=%-2s | A %8.0f (%+.2f%%) | B0=200 %8.0f (%+.2f%%) | "
              "最优 L=%-2s %8.0f (%+.2f%%) vsA %+.2f%% know≥2:%d"
              % (tag, bk, cA, e["A_current"]["regret_pct"], cB,
                 e["B_long_warmup"]["regret_pct"], best_L,
                 e["probe"][best_L]["cost"], e["probe"][best_L]["regret_pct"],
                 e["probe"][best_L]["vs_A_pct"], e["probe"][best_L]["n_known_ge2"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
