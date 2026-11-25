#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写法一的三项补充（第 2、3 项为数据项；第 1 项的实测部分）。

第 1 项  m-1 的实例化（只做"数出来"，不做证明）
    问：要把 K^ 从错改成对，究竟需要新增哪些 (age) 观测、各几条？
    做法：对每个配置，逐个加入 age 的观测（按 cut 逐步放宽），记录 K^ 何时变对，
    以及"变对"与"新增观测条数"的关系。若需要 age=1..k 各约一整个横截面，
    且 k = m-1，这里就给出了 m 的实测读数。
    不做的事：不声称这就是 m-1 的证明。Lean 里没有 m-1 的形式化，方向文档也
    只说它"未证"。本脚本只产出"某个算例需要几条激励"的计数。

第 2 项  x3 的非单调性
    cut 200→300 时 K^ 从 3 退回 2。查逐帧 K*(t) 的分布：
    是"K*=2 与 K*=3 两段并存、长窗平均后被拉回"，还是别的原因。

第 3 项  漂移界限
    c_2-c_3 的符号翻转是否一次性（单调），还是来回。
    用翻转次数、最长同号游程来量化，避免再把一次性移动说成"漂移"。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, load_phase  # noqa: E402

KMAX = 7
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_m1.json")


def frame_costs(tab, t, kmax=KMAX):
    out = {}
    for K in range(1, kmax + 1):
        vals = [tab.get((t, a)) for a in range(K)]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def main():
    out = {"kind": "VT_regret_m1_and_x3", "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        ts = sorted({x for (x, _a) in tab})
        pf = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if pf[t]]
        full = [t for t in usable if len(pf[t]) == KMAX]

        # ---------- 第 1 项：需要多少新增观测才能估对 ----------
        # 逐步推进 cut（每 10 帧一格），记录 K^ 与该 cut 下的最优固定 K
        sweep = []
        for cut in range(B0, full[-1], 10):
            est = {K: st.mean([pf[t][K] + rho / K for t in usable if t <= cut and K in pf[t]])
                   for K in range(1, KMAX + 1)
                   if any(K in pf[t] for t in usable if t <= cut)}
            if not est:
                continue
            k_hat = min(est, key=lambda K: est[K])
            ev = [t for t in full if t > cut]
            if len(ev) < 30:
                break
            best = min(range(1, KMAX + 1),
                       key=lambda K: sum(pf[t][K] + rho / K for t in ev))
            cnt = {str(K): sum(1 for t in usable if t <= cut and K in pf[t])
                   for K in range(1, min(4, KMAX + 1))}
            sweep.append({"cut": cut, "k_hat": k_hat, "k_best": best,
                          "ok": k_hat == best, "counts": cnt,
                          "n_age_ge2": sum(1 for t in usable if t <= cut and 2 in pf[t])})
        # 首次变对的 cut 与那时的新增观测数
        first_ok = next((s for s in sweep if s["ok"]), None)
        # 变对后又变错（非单调）
        flip_back = None
        if first_ok:
            after = [s for s in sweep if s["cut"] > first_ok["cut"] and not s["ok"]]
            flip_back = after[0] if after else None

        # ---------- 第 2 项：逐帧 K* 分布（分前后两半） ----------
        kstar = {t: min(pf[t], key=lambda K: pf[t][K] + rho / K) for t in full}
        mid = full[len(full) // 2]
        hist1 = {str(K): sum(1 for t in full if t <= mid and kstar[t] == K) for K in range(1, KMAX + 1)}
        hist2 = {str(K): sum(1 for t in full if t > mid and kstar[t] == K) for K in range(1, KMAX + 1)}

        # ---------- 第 3 项：c2-c3 的符号游程 ----------
        d = [(t, (pf[t][2] + rho / 2) - (pf[t][3] + rho / 3))
             for t in full if 2 in pf[t] and 3 in pf[t]]
        signs = [1 if v > 0 else -1 for _t, v in d]
        runs = []
        cur = 1
        for i in range(1, len(signs)):
            if signs[i] == signs[i - 1]:
                cur += 1
            else:
                runs.append(cur)
                cur = 1
        runs.append(cur)
        n_flip = len(runs) - 1
        longest = max(runs) if runs else 0

        out["cases"][tag] = {
            "rho": round(rho, 4), "B0": B0,
            "m1_sweep_first_correct_cut": first_ok,
            "m1_sweep_flip_back": flip_back,
            "m1_sweep_len": len(sweep),
            "kstar_hist_first_half": hist1,
            "kstar_hist_second_half": hist2,
            "mid_frame": mid,
            "d23_flips": n_flip,
            "d23_longest_run": longest,
            "d23_n": len(d),
            "d23_longest_run_frac": round(longest / len(d), 3) if d else None,
        }
        print("%-5s 首次估对的cut=%-5s (新增age>=2观测=%-4s) 再变错=%s"
              % (tag, first_ok["cut"] if first_ok else None,
                 first_ok["n_age_ge2"] if first_ok else None,
                 (flip_back["cut"], flip_back["k_hat"]) if flip_back else None))
        print("      K* 前半=%s 后半=%s | d23 翻转 %d 次, 最长游程 %d/%d (%.2f)"
              % (hist1, hist2, n_flip, longest, len(d), longest / len(d) if d else 0))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
