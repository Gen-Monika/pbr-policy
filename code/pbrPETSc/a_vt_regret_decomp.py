#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向二闸门的补充诊断：把「锁定 K^ vs 逐帧最优」的遗憾拆开，看它是不是平凡事实。

为什么需要这一步
----------------
主闸门比较的是两条不同性质的策略：
  · 逐帧最优：每帧都可换 K，等价于每帧都重建（K=1 的重建频率最高，但每帧
    可选最优 K）——它是**不可实现的 oracle**；
  · 固定 K^：每 K^ 步才重建一次。
两者在**重建频率**上本就不同，所以"固定 K 有遗憾"几乎是恒真的：K=1 每步重建
一定能压住迭代数。若遗憾全部来自这一点，主闸门测到的不是"识别失败"，而是
"少重建就要多迭代"这个成本权衡——那是已知的 ρ 权衡，不是新事实。

分解（同一批帧，逐帧加性，因为 N(t,a) 与策略无关）
--------------------------------------------------
逐帧成本 c_t(K) = mean_{a<K} N(t,a) + rho/K 可拆成
    it_t(K) = mean_{a<K} N(t,a)     迭代项
    rb_t(K) = rho/K                 重建项（每帧摊到的重建代价）
于是任意两个 K 的差就是这两项之差，无需跑状态机。

三类候选 K 的对比（每个都在 eval 帧上累加）：
  A. K^       = 预热窗口估出来的固定值（主闸门用的那个）
  B. K*_fix   = **事后**在 eval 帧上使总量最优的固定 K（静态再优化上限）
  C. K*_mode  = eval 帧上逐帧 argmin 的众数（简单静态规则）
  D. oracle   = 逐帧 argmin（不可实现）

判读规则（写死，不许事后调）
--------------------------
* 若 A 与 B 的差距 << A 与 D 的差距 → 遗憾主要是"选错了那个固定 K"
  （即标定/识别问题），值得当对照片段；
* 若 A≈B 而两者都明显差于 D → 遗憾是"固定周期本身"的结构性代价，
  与识别无关，不能算作"识别失败且遗憾不可忽略"的证据；
* K*_fix 落在扫描上限 7 时单列（censoring），不当"最优"。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, load_phase  # noqa: E402

KMAX = 7
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_decomp.json")


def frame_costs(tab, t, kmax=KMAX):
    out = {}
    for K in range(1, kmax + 1):
        ages = list(range(K))
        vals = [tab.get((t, a)) for a in ages]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def main():
    out = {"kind": "VT_regret_decomp", "P2": P2, "kmax": KMAX, "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        ts = sorted({x for (x, _a) in tab})
        pf = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if pf[t]]
        # eval 帧：预热之后，且固定 K 在每帧都可观测
        eval_ts = [t for t in usable if t > B0]
        # 只保留所有 K 都有观测的帧，使 A/B/C/D 可比（同一批帧、同一分母）
        full = [t for t in eval_ts if len(pf[t]) == KMAX]
        if len(full) < 20:
            out["cases"][tag] = {"error": "too few full frames", "n": len(full)}
            continue

        def total(K):
            it = sum(pf[t][K] for t in full)
            rb = len(full) * rho / K
            return it, rb, it + rb

        ks = list(range(1, KMAX + 1))
        tot = {K: total(K) for K in ks}
        c_or = sum(min(pf[t][K] + rho / K for K in pf[t]) for t in full)
        k_or = [min(pf[t], key=lambda K: pf[t][K] + rho / K) for t in full]
        mode = st.mode(k_or)
        k_fix = min(ks, key=lambda K: tot[K][2])

        # 预热窗口估计的 K^（与主闸门同口径）
        est = {K: st.mean([pf[t][K] + rho / K for t in usable if t <= B0 and K in pf[t]])
               for K in ks if any(K in pf[t] for t in usable if t <= B0)}
        k_hat = min(est, key=lambda K: est[K]) if est else None

        c_hat = tot[k_hat][2] if k_hat else None
        c_fix = tot[k_fix][2]
        c_mode = tot[mode][2]

        entry = {
            "rho": round(rho, 4), "B0": B0, "n_full_frames": len(full),
            "t_range": [full[0], full[-1]],
            "k_hat_warmup": k_hat, "k_star_fixed_hindsight": k_fix,
            "k_star_mode": mode, "k_at_ceiling": (k_fix == KMAX or mode == KMAX),
            "cost_by_K": {str(K): round(tot[K][2], 2) for K in ks},
            "iters_by_K": {str(K): round(tot[K][0], 2) for K in ks},
            "rebuild_by_K": {str(K): round(tot[K][1], 2) for K in ks},
            "oracle_cost": round(c_or, 2),
            "gap_hat_vs_oracle_pct": round(100 * (c_hat - c_or) / c_or, 4) if c_hat else None,
            "gap_hindsight_vs_oracle_pct": round(100 * (c_fix - c_or) / c_or, 4),
            "gap_mode_vs_oracle_pct": round(100 * (c_mode - c_or) / c_or, 4),
            "gap_hat_vs_hindsight_pct": round(100 * (c_hat - c_fix) / c_fix, 4) if c_hat else None,
            "share_of_hat_gap_that_is_wrong_K": (
                round(100 * (c_hat - c_fix) / (c_hat - c_or), 1)
                if c_hat and c_hat > c_or else None),
            "kstar_hist": {str(K): k_or.count(K) for K in ks},
        }
        out["cases"][tag] = entry
        print("%-5s K^=%-2s Kfix*=%-2s Kmode=%-2s | hat-or=%-7s fix*-or=%-7s hat-fix*=%-7s  wrongK_share=%-6s ceil=%s"
              % (tag, k_hat, k_fix, mode, entry["gap_hat_vs_oracle_pct"],
                 entry["gap_hindsight_vs_oracle_pct"], entry["gap_hat_vs_hindsight_pct"],
                 entry["share_of_hat_gap_that_is_wrong_K"], entry["k_at_ceiling"]))
        print("      cost by K:", {K: round(tot[K][2]) for K in ks})
        print("      iters   :", {K: round(tot[K][0]) for K in ks})
        print("      rebuild :", {K: round(tot[K][1]) for K in ks})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
