#!/usr/bin/env python3
"""
A2 补充：凸性判据对整数离散的稳健性。

前一版用严格不等式 Δ(a+1) ≥ Δ(a)，在 N 是【整数】时会大量假违反：
相邻增量差 ±1 就翻面。本脚本扫容差 δ，给出
    Δ(a+1) ≥ Δ(a) − δ
下逐 t 凸比例，并给出"违反幅度"的分布，用于区分
    「真非凸」 vs 「整数离散造成的平坦/抖动」。

同时也报告每个配置 N 的量级（N 大 ⇒ δ 的相对影响小）。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]


def _v(x):
    return float(st.median(x)) if isinstance(x, (list, tuple)) else float(x)


def curves(tab):
    by = {}
    for (t, a), v in tab.items():
        by.setdefault(int(t), {})[int(a)] = _v(v)
    return by


print("=" * 120)
print("★★★ A2 补充：凸性判据对整数离散的稳健性（容差扫描）")
print("=" * 120)
print("判据：Δ(a+1) ≥ Δ(a) − δ。δ=0 为严格凸。\n")

print("  %-6s %-11s %-13s %-13s %-13s %-13s %s"
      % ("配置", "N(a=0)中位", "δ=0", "δ=0.05", "δ=0.15", "δ=0.30", "最大违反幅度"))
summary = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    by = curves(d["tab"])
    n0 = [c[0] for c in by.values() if 0 in c]
    res = {0: 0, 1: 0, 2: 0, 3: 0}
    tot = 0
    worst = 0.0
    for t, c in by.items():
        if 0 not in c or c[0] <= 0:
            continue
        ks = sorted(c)
        if len(ks) < 4:
            continue
        g0 = c[0]
        cc = [c[a] / g0 for a in ks]
        dd = [cc[i + 1] - cc[i] for i in range(len(cc) - 1)]
        if len(dd) < 3:
            continue
        tot += 1
        # 最大违反幅度（Δ 回落量）
        w = max((dd[i] - dd[i + 1]) for i in range(len(dd) - 1))
        worst = max(worst, w)
        for k, delta in ((0, 0.0), (1, 0.05), (2, 0.15), (3, 0.30)):
            bad = any(dd[i + 1] < dd[i] - delta - 1e-12 for i in range(len(dd) - 1))
            res[k] += (0 if bad else 1)
    summary.append((tag, st.median(n0) if n0 else float("nan"), tot, res, worst))
    print("  %-6s %-11.1f %-13s %-13s %-13s %-13s %.3f"
          % (tag, st.median(n0) if n0 else float("nan"),
             "%.1f%%" % (100.0 * res[0] / tot if tot else 0),
             "%.1f%%" % (100.0 * res[1] / tot if tot else 0),
             "%.1f%%" % (100.0 * res[2] / tot if tot else 0),
             "%.1f%%" % (100.0 * res[3] / tot if tot else 0),
             worst))

print("\n  ★ 说明：「逐 t 凸比例」低不等于 A2 不成立——")
print("     若 N(a=0) 只有十几，Δ 的量级也是几，±1 的整数抖动就足以把 1/3 的 t 翻面。")
print("     真正的判据应当是【平均曲线】与【违反幅度是否随 N 量级缩放】。")
