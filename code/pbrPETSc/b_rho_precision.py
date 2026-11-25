#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ρ̂ 的精度容限：判据离「平局」有多近，以及要达到给定翻转率需要多少预热样本。

用途：回答“在线估计的 ρ 若带上抽样误差，决策会不会翻”。结论用于
docs/rho_precision_sensitivity_20261031.md 与论文 §8 的边界证据，
以及“自适应热启动”那条后续工作的拐点估计（该方向目前暂缓）。

三个量：
  1) margin = lhs - avg，即判据两端之差（>0 触发重建）。
     折成 ρ 的比例 |m|/r 后取分位数，才是可跨配置比较的“容限”；
     ★ 不要用最小值——整数巧合会造成精确 0，把所需样本量高估约三个数量级。
  2) 翻转率：对相对误差 SE 的 ρ̂，某决策点翻转概率 ≈ 0.5·P(|m|/r < SE)。
  3) 拐点 n*：翻转率首次降到 1% 所需的预热样本数（SE(n) = K·CV/√n）。

margin 只能从 sim_online_detail 的内部状态取得，本脚本用它的 trace 参数，
不另写决策循环（重复实现曾直接导致过真实缺陷，见 pbrcost.sim_online_detail 的注释）。

依赖：pbrcost.load_phase 需要服务器上的相位扫描文件。
"""
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbrcost as P

TAGS = P.ORDER
K_COVER = 1.2533   # 中位数的 95% 置信区间半宽 / SE（正态近似）
CV = 0.11          # 实测 ρ̂ 的相对变异系数（见敏感性文档 §二）
NS = [50, 100, 200, 400, 800, 1600, 3200, 6400, 25600]
TARGET = 1.0       # 拐点定义：翻转率降到该百分比以下


def margins(tag, B0=None):
    """返回 (|margin| 列表, r1)，只含有决策的步（预热步不记录）。"""
    d = P.load_phase(tag)
    env = P.Env(d["tab"], sFact=d["s"])
    T, r1 = d["T"], d["r1"]
    B0 = B0 if B0 is not None else P.CFG[tag][2]
    tr = []
    pred = P.sim_online_detail(env, r1, T, B0, trace=tr)[3]
    for (t, lhs, avg, m) in tr:
        assert pred[t - 1] == (m > 0), "margin 符号与决策不一致：%s t=%d" % (tag, t)
    return [abs(m) for (_, _, _, m) in tr], r1


def main():
    print("%-6s %-9s %-8s %-10s %-10s %-10s %-10s"
          % ("cfg", "rho", "决策点", "P0.1%", "P1%", "P5%", "中位"))
    print("-" * 76)
    rows = {}
    for tag in TAGS:
        ms, r1 = margins(tag)
        ms.sort()
        n = len(ms)
        q = lambda p: ms[min(n - 1, max(0, int(p * n)))]
        rows[tag] = (ms, r1)
        print("%-6s %-9.4f %-8d %-10.4f %-10.4f %-10.4f %-10.4f"
              % (tag, r1, n, q(0.001) / r1 * 100, q(0.01) / r1 * 100,
                 q(0.05) / r1 * 100, st.median(ms) / r1 * 100))

    print()
    print("单位：最后四列为 |margin| 折成 ρ 的百分比（%）。")
    print()
    print("翻转率(%%) 随预热样本数 n 的变化，SE(n)=%.4f/√n（占 ρ）" % (K_COVER * CV))
    print("%-6s | %s" % ("cfg", " ".join("%7d" % n for n in NS)))
    print("-" * (8 + 8 * len(NS)))
    knee = {}
    for tag in TAGS:
        ms, r1 = rows[tag]
        n = len(ms)
        row = [50.0 * sum(1 for m in ms if m < (K_COVER * CV / math.sqrt(N)) * r1) / n
               for N in NS]
        print("%-6s | %s" % (tag, " ".join("%7.2f" % x for x in row)))
        hit = next((NS[i] for i, v in enumerate(row) if v < TARGET), None)
        knee[tag] = hit

    print()
    print("拐点：翻转率首次降到 %.0f%% 以下所需的 n" % TARGET)
    for tag in TAGS:
        hit = knee[tag]
        print("  %-6s -> %s" % (tag, ("n ≈ %d" % hit) if hit else "本表范围内未达到（>%d）" % NS[-1]))
    print()
    print("限制：SE 取常数 CV、误差按 iid 处理、各决策点独立；这是一阶估计，")
    print("不是完整的随机扰动 Monte Carlo，也不保证实跑中的相对敏感度排序不变。")


if __name__ == "__main__":
    main()
