#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ρ̂ 带系统性偏差时，在线决策序列的翻转率与首次分歧时刻。

两个量，用途不同：
  · 翻转率 = 与基准决策不同的步数 / 可比步数（B0..T）。
    整条轨迹会因一次提前/推迟的重建而错位，所以它衡量的是“影响面”，
    不适合单独用来比较各配置的敏感度（决策点数不同会带来偏差）。
  · 首次分歧 = 相对 B0 的偏移；它回答“第一个决策要错到什么程度才开始错”。

ρ 偏差只通过 sim_online_detail 的 rho_of_t 钩子注入——唯一实现只有那一处，
不在这里另写决策循环（详见 pbrcost.sim_online_detail 的注释）。

依赖：pbrcost.load_phase 需要服务器上的相位扫描文件。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbrcost as P

TAGS = P.ORDER
DELTAS = (0.005, 0.01, 0.02, 0.05, 0.10, -0.02, -0.05, -0.10)
FIRST_DELTAS = (0.002, 0.005, 0.01, 0.02, 0.05, 0.10,
                -0.002, -0.005, -0.01, -0.02, -0.05, -0.10)


def run(tag):
    d = P.load_phase(tag)
    env = P.Env(d["tab"], sFact=d["s"])
    T, r1, B0 = d["T"], d["r1"], P.CFG[tag][2]
    return env, T, r1, B0


def flip_rate(pred, ref, lo, hi):
    """lo..hi 为 1-based 的步号区间（含两端）。"""
    diff = sum(1 for i in range(lo - 1, hi) if pred[i] != ref[i])
    return 100.0 * diff / (hi - lo + 1)


def main():
    print("翻转率（%，相对基准轨迹，区间 B0..T）")
    print("%-6s %-9s %-6s | %s" % ("cfg", "rho", "B0", "  ".join("%+6g%%" % d for d in DELTAS)))
    print("-" * 112)
    for tag in TAGS:
        env, T, r1, B0 = run(tag)
        ref = P.sim_online_detail(env, r1, T, B0)[3]
        line = [flip_rate(P.sim_online_detail(env, r1, T, B0,
                                             rho_of_t=lambda t, d=d: r1 * (1 + d))[3],
                          ref, B0, T) for d in DELTAS]
        print("%-6s %-9.4f %-6d | %s" % (tag, r1, B0, "  ".join("%7.2f" % x for x in line)))

    print()
    print("首次分歧所在步（相对 B0 的偏移）；— = 全程无分歧")
    print("%-6s %-9s %-6s | %s" % ("cfg", "rho", "B0", "  ".join("%+7g%%" % d for d in FIRST_DELTAS)))
    print("-" * 128)
    for tag in TAGS:
        env, T, r1, B0 = run(tag)
        ref = P.sim_online_detail(env, r1, T, B0)[3]
        out = []
        for dl in FIRST_DELTAS:
            pr = P.sim_online_detail(env, r1, T, B0,
                                     rho_of_t=lambda t, dl=dl: r1 * (1 + dl))[3]
            first = next((i + 1 - B0 for i in range(B0, T) if pr[i] != ref[i]), None)
            out.append("—" if first is None else str(first))
        print("%-6s %-9.4f %-6d | %s" % (tag, r1, B0, "  ".join("%8s" % x for x in out)))
    print()
    print("限制：偏差为常数、整条轨迹一致；真实在线 ρ̂ 是逐步更新的中位数，")
    print("其抽样噪声按逐决策独立近似见 b_rho_precision.py（一阶估计）。")


if __name__ == "__main__":
    main()
