#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向二闸门的复核：两件必须做的独立检查。

检查 1（轨迹）：K*(t) 到底怎么走。若 l15/l20 的 K^=2 只是预热窗内的边界效应，
而 eval 窗一开始就已经是 3，那"识别失败"是我估计窗口选得不好造成的，
不能算算例属性。要看 K*(t) 逐帧序列、首次离开 2 的时刻、以及两段各自的
c(2) 与 c(3) 差多少（是否刀刃）。

检查 2（对独立实现）：用 pbrcost 的 sim_fixed 状态机跑 K=2/3/…，确认
"K=3 优于 K=2"这个定性结论不依赖我这份逐帧加性代码。两者不可能逐位相等
（sim_fixed 从 t=1 预热带状态，且 age 会外推），但排序与量级必须一致。

判读规则（写死）：
* 轨迹检查若显示 K* 在预热窗内就已经是 3，则主闸门 l15/l20 的 6.5%/9.0% 作废
  （是我窗口选错，不是算例属性）。
* 若 K* 在 t≈B0 附近才从 2 跳到 3 并保持，则是真实的标定过期，结论保留。
* sim_fixed 若给出相反排序，主闸门作废并回报矛盾。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, Env, load_phase, sim_fixed  # noqa: E402

KMAX = 7
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_checks.json")


def frame_costs(tab, t, kmax=KMAX):
    out = {}
    for K in range(1, kmax + 1):
        vals = [tab.get((t, a)) for a in range(K)]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def main():
    out = {"kind": "VT_regret_checks", "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            continue
        tab, rho, B0, T = ph["tab"], ph["r1"], ph["B0"], ph["T"]
        ts = sorted({x for (x, _a) in tab})
        pf = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if pf[t]]
        full = [t for t in usable if len(pf[t]) == KMAX]

        # ---- 检查 1：K*(t) 轨迹与 c(2)/c(3) 的差距随 t 的走向 ----
        traj = [(t, min(pf[t], key=lambda K: pf[t][K] + rho / K)) for t in usable]
        first_runs = {}
        for K in range(1, KMAX + 1):
            firsts = [t for i, (t, k) in enumerate(traj) if k == K and
                      (i == 0 or traj[i - 1][1] != K)]
            first_runs[str(K)] = firsts[:6]
        # c(2) 与 c(3) 的逐帧差（只在两 K 都观测时）
        d23 = [(t, (pf[t][2] + rho / 2) - (pf[t][3] + rho / 3))
               for t in usable if 2 in pf[t] and 3 in pf[t]]
        seg = lambda lo, hi: [d for t, d in d23 if lo <= t < hi]
        b_lo, b_hi = 1, B0
        e_lo, e_hi = B0 + 1, 10 ** 9
        mr = lambda xs: round(st.mean(xs), 3) if xs else None
        # ---- 检查 2：sim_fixed 独立实现，K=1..7 ----
        env = Env(tab, sFact=1.0)
        fixed = {}
        for K in range(1, KMAX + 1):
            try:
                c, it, rb = sim_fixed(env, rho, K, T, B0)
                fixed[str(K)] = {"cost": round(c, 2), "iters": round(it, 2), "rb": rb}
            except Exception as exc:                       # noqa: BLE001
                fixed[str(K)] = {"error": repr(exc)}
        best_fixed = min((v["cost"], K) for K, v in fixed.items() if "cost" in v)

        entry = {
            "rho": round(rho, 4), "B0": B0, "T": T,
            "first_runs_of_Kstar": first_runs,
            "n_frames_Kstar": {"%s" % K: sum(1 for _t, k in traj if k == K)
                               for K in range(1, KMAX + 1)},
            "d_c2_minus_c3_warmup_mean": mr(seg(b_lo, b_hi)),
            "d_c2_minus_c3_eval_mean": mr(seg(e_lo, e_hi)),
            "d_c2_minus_c3_eval_frac_pos": (
                round(sum(1 for d in seg(e_lo, e_hi) if d > 0) / len(seg(e_lo, e_hi)), 4)
                if seg(e_lo, e_hi) else None),
            "sim_fixed": fixed,
            "sim_fixed_best_K": best_fixed[1],
            "sim_fixed_best_cost": best_fixed[0],
        }
        out["cases"][tag] = entry
        print("%-5s K* frames=%s | d(c2-c3): warm=%-8s eval=%-8s frac_pos=%-6s | sim_fixed best K=%s"
              % (tag, entry["n_frames_Kstar"], entry["d_c2_minus_c3_warmup_mean"],
                 entry["d_c2_minus_c3_eval_mean"], entry["d_c2_minus_c3_eval_frac_pos"],
                 best_fixed[1]))
        print("      first appearance of each K*:", first_runs)
        print("      sim_fixed:", {K: v.get("cost") for K, v in fixed.items()})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
