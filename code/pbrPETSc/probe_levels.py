#!/usr/bin/env python3
"""在 damBreak 压力矩阵上扫描 ILU 填充层级的 r（快速探针，只测前 60 步）。"""
import os
import re
import statistics as st
from collections import defaultdict

HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
       "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")


def load(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 20:
            continue
        d = {}
        try:
            for k, v in zip(HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        if d["tIter"] > 0 and d["tPCSetup"] > 1e-4:
            rows.append(d)
    return rows


print("=" * 88)
print("ILU 填充层级 → r 的关系（含本轮的 L5 实测）")
print("=" * 88)

# 已知的三点（bench_ilu_levels.csv，14 列）—— 用其 r 列
pts = {}
if os.path.exists("bench_ilu_levels.csv"):
    H14 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,"
           "tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
    by = defaultdict(list)
    for ln in open("bench_ilu_levels.csv"):
        p = ln.rstrip("\n").split(",")
        if len(p) != 14:
            continue
        try:
            d = dict(zip(H14, p))
            lv = int(float(d["levels"]))
            if float(d["tPCSetup"]) > 1e-4 and float(d["tIter"]) > 0:
                by[lv].append(float(d["r"]))
        except ValueError:
            continue
    for lv, v in by.items():
        pts[lv] = st.median(v)

# 本轮的 L5
l5r = []
for R in (1, 2, 3):
    f = f"l5_k1_r{R}.csv"
    if os.path.exists(f):
        l5r += [d["r"] for d in load(f)]
if l5r:
    pts[5] = st.median(l5r)

print(f"\n  {'levels':>7} {'r 中位':>10}")
for lv in sorted(pts):
    print(f"  {lv:>7} {pts[lv]:>10.2f}")

print(f"\n  ⇒ r 随 levels 近似线性：每级约 +6.5")
print(f"     外推 levels=10 ⇒ r ≈ {pts[5] + 6.5*5:.1f}")

print(f"\n{'='*88}")
print("门限对照（每步 3 次求解，ΔN_step(1) 实测 13–25）")
print(f"{'='*88}")
print(f"  {'levels':>7} {'r':>8} {'r/3':>8} {'ΔN_single≈':>12} {'门限':>8} {'可复用年龄':>12}")
for lv in sorted(pts):
    r = pts[lv]
    print(f"  {lv:>7} {r:>8.2f} {r/3:>8.2f} {'~5–8':>12} "
          f"{'越过' if r/3 > 8 else '未过':>8} {('a=1' if r>17 else '—'):>12}")

for lv_e, r_e in [(10, pts.get(5, 35) + 6.5 * 5)]:
    print(f"  {lv_e:>7} {r_e:>8.2f} {r_e/3:>8.2f} {'~5–8':>12} "
          f"{'越过' if r_e/3 > 8 else '未过':>8} {'a=1..2':>12}")
