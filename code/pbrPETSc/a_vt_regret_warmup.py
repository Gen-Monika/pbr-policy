#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸门的第三个检查：l15/l20 的 K^=2 是「真实标定过期」还是「预热窗样本太薄」。

两种解释在数据上分得开：
* 样本薄：预热窗内能观测到 age>=1 的帧很少，K=2 与 K=3 的均值差被个别帧决定，
  或者根本只有很少的帧同时给出两个 K → 那不是识别失败，是采样不足。
* 真过期：预热窗内两个 K 都有大量帧、且差值的符号稳定为负（c2<c3），
  进入 eval 窗后符号稳定翻转（c3<c2）→ 最优周期真的移动了。

同时给出：逐窗（每 50 帧）的 c2-c3 均值与帧数，看符号是在哪个 t 翻转的；
以及把 K^ 的估计改成「只用两 K 都可观测的帧」后是否仍然是 2（口径敏感性）。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, load_phase  # noqa: E402

KMAX = 7
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_warmup.json")


def frame_costs(tab, t, kmax=KMAX):
    out = {}
    for K in range(1, kmax + 1):
        vals = [tab.get((t, a)) for a in range(K)]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def main():
    out = {"kind": "VT_regret_warmup_detail", "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        ts = sorted({x for (x, _a) in tab})
        pf = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if pf[t]]
        warm = [t for t in usable if t <= B0]
        evalz = [t for t in usable if t > B0]

        def cover(frames, K):
            return sum(1 for t in frames if K in pf[t])

        both = [t for t in warm if 2 in pf[t] and 3 in pf[t]]
        d_both = [(pf[t][2] + rho / 2) - (pf[t][3] + rho / 3) for t in both]
        # 只用两 K 都可观测的帧重估 K^（口径敏感性）
        est = {}
        for K in range(1, KMAX + 1):
            vals = [pf[t][K] + rho / K for t in warm if K in pf[t]]
            if vals:
                est[K] = st.mean(vals)
        k_hat_cov = min(est, key=lambda K: est[K]) if est else None
        both_est = {}
        for K in (2, 3):
            vals = [pf[t][K] + rho / K for t in both]
            if vals:
                both_est[K] = st.mean(vals)
        k_hat_23 = min(both_est, key=lambda K: both_est[K]) if both_est else None

        # 每 50 帧一个窗的 c2-c3 符号
        win = {}
        step = 50
        lo = usable[0]
        while lo <= usable[-1]:
            hi = lo + step
            ds = [(pf[t][2] + rho / 2) - (pf[t][3] + rho / 3)
                  for t in usable if lo <= t < hi and 2 in pf[t] and 3 in pf[t]]
            if ds:
                win["%d-%d" % (lo, hi - 1)] = {
                    "n": len(ds), "mean_d": round(st.mean(ds), 3),
                    "frac_pos": round(sum(1 for d in ds if d > 0) / len(ds), 3)}
            lo = hi

        out["cases"][tag] = {
            "B0": B0, "rho": round(rho, 4),
            "n_warm": len(warm), "n_eval": len(evalz),
            "warm_coverage_by_K": {str(K): cover(warm, K) for K in range(1, KMAX + 1)},
            "eval_coverage_by_K": {str(K): cover(evalz, K) for K in range(1, KMAX + 1)},
            "warm_both23_n": len(both),
            "warm_d23_mean": round(st.mean(d_both), 3) if d_both else None,
            "warm_d23_frac_pos": (round(sum(1 for d in d_both if d > 0) / len(d_both), 3)
                                  if d_both else None),
            "k_hat_all_warm": k_hat_cov,
            "k_hat_only23": k_hat_23,
            "windows_d23": win,
        }
        print("%-5s warm_n=%-4d both23=%-4d d23warm=%-8s frac+%-6s | Khat(all)=%s Khat(only23)=%s"
              % (tag, len(warm), len(both),
                 out["cases"][tag]["warm_d23_mean"],
                 out["cases"][tag]["warm_d23_frac_pos"], k_hat_cov, k_hat_23))
        print("      coverage warm:", out["cases"][tag]["warm_coverage_by_K"])
        print("      windows:", {k: (v["n"], v["mean_d"], v["frac_pos"]) for k, v in win.items()})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
