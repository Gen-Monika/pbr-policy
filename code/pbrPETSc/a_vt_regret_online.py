#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写法一的必要补充检查：把闸门的"锁定 K^"和第一篇真正的在线策略对齐。

为什么必须做
------------
闸门测的是"锁定一个固定 K、永不更新"的策略。第一篇的在线策略**不是**这个：
它不估 K*，而是每步比较 lvl=N(t,0) 与 avg=历史代价均值，逐步决定重建与否。
所以 l15/l20 的 6.5%/9.0% 遗憾，只证明"锁定固定 K 有代价"，**不**证明第一篇
的策略在 l15/l20 上有损失。两者混为一谈，就是换掉了科学目标。

本脚本把三条策略放在同一批步、同一个成本口径下：
  A. online         = sim_online_detail（第一篇的唯一定义）
  B. fixed K        = sim_fixed，K 取事后最优
  C. oracle         = 逐帧 argmin c_t(K)（不可实现的参照）
统一只统计 **预热之后** 的增量成本：Δcost / (T - B0) 每步。

判读规则（写死）
---------------
* 若 online 每步成本 ≤ fixed(best) 每步成本 → 第一篇的策略确实绕开了锁定陷阱，
  写法一不能把 l15/l20 的遗憾算到第一篇头上，只能说"锁定会有代价"。
* 若 online 在 l15/l20 上反而更贵 → 需要回头查 sim_online 的实现或口径，
  不得直接写进论文。
* online 与 oracle 的差 = 第一篇实测的"学习成本"，应与已知 1.2%-6.5% 同量级；
  若不同量级，说明本口径与论文口径不同，只能作相对比较。
"""
import json
import os
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import Env, ORDER, load_phase, sim_fixed, sim_online_detail  # noqa: E402

KMAX = 7
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret_online.json")


def frame_costs(tab, t, kmax=KMAX):
    import statistics as st
    out = {}
    for K in range(1, kmax + 1):
        vals = [tab.get((t, a)) for a in range(K)]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def partial_cost(fn, cutoff):
    """跑完整流程，返回 t<=cutoff 的累计成本（用 stop= 实现，仅 online 支持）。"""
    return fn(cutoff)


def main():
    out = {"kind": "VT_regret_vs_online", "cases": {}}
    for tag in ORDER:
        ph = load_phase(tag, verbose=False)
        if not ph:
            continue
        tab, rho, B0, T = ph["tab"], ph["r1"], ph["B0"], ph["T"]
        env = Env(tab, sFact=1.0)

        # A. online：用 stop 分别跑到 B0 和 T，取增量
        c0, it0, rb0, _, _ = sim_online_detail(env, rho, T, B0, stop=B0)
        c1, it1, rb1, _, _ = sim_online_detail(env, rho, T, B0)
        onl_inc = c1 - c0
        n_eval = T - B0

        # B. fixed K：同样取增量（sim_fixed 不支持 stop，直接跑 T 再扣掉预热段公式）
        fixed = {}
        for K in range(1, KMAX + 1):
            tot, it, rb = sim_fixed(env, rho, K, T, B0)
            # 预热段成本：每步重建，成本 = rc + N(t,0)
            warm = sum(env(t, 0) + rho for t in range(1, B0 + 1))
            fixed[K] = tot - warm
        best_K = min(fixed, key=lambda K: fixed[K])

        # C. oracle：逐帧最优（只在 eval 帧、K 全可观测的帧上）
        pf = {t: frame_costs(tab, t) for t in range(B0 + 1, T + 1)}
        full = [t for t in pf if len(pf[t]) == KMAX]
        import statistics as st
        or_cost = sum(min(pf[t][K] + rho / K for K in pf[t]) for t in full)
        onl_same = None   # online 在 full 帧上的增量成本无法直接切分，用总增量近似

        entry = {
            "rho": round(rho, 4), "B0": B0, "T": T, "n_eval": n_eval,
            "online_incremental": round(onl_inc, 2),
            "online_per_step": round(onl_inc / n_eval, 3),
            "online_rebuilds_eval": rb1 - rb0,
            "fixed_incremental": {str(K): round(fixed[K], 2) for K in fixed},
            "fixed_best_K": best_K,
            "fixed_best_per_step": round(fixed[best_K] / n_eval, 3),
            "oracle_frames_n": len(full),
            "oracle_cost_on_full": round(or_cost, 2),
            "oracle_per_step_on_full": round(or_cost / len(full), 3) if full else None,
            "online_vs_fixed_pct": round(100 * (onl_inc / n_eval - fixed[best_K] / n_eval)
                                         / (fixed[best_K] / n_eval), 3),
        }
        out["cases"][tag] = entry
        print("%-5s online/step=%-8s fixedK%d/step=%-8s (delta %+6.2f%%) | oracle/frame=%-8s rb_eval=%s"
              % (tag, entry["online_per_step"], best_K, entry["fixed_best_per_step"],
                 entry["online_vs_fixed_pct"], entry["oracle_per_step_on_full"],
                 entry["online_rebuilds_eval"]))
        print("      fixed by K:", {K: round(v) for K, v in fixed.items()})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
