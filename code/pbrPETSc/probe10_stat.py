#!/usr/bin/env python3
"""levels=10 探针结果统计。"""
import os
import statistics as st

H = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
     "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")

path = "probe10.csv"
rows = []
for ln in open(path):
    p = ln.rstrip("\n").split(",")
    if len(p) != 20:
        continue
    d = {}
    try:
        for k, v in zip(H, p):
            d[k] = v if k in ("field", "kind") else float(v)
    except ValueError:
        continue
    if d["tIter"] > 0 and d["tPCSetup"] > 1e-4:
        rows.append(d)

print("=" * 70)
print("levels=10 探针结果")
print("=" * 70)
print("有效重建样本 %d" % len(rows))

ts = st.median([d["tPCSetup"] for d in rows])
ma = st.median([d["ma"] for d in rows])
mp = st.median([d["mp"] for d in rows])
ti = st.median([d["tIter"] for d in rows])
rr = st.median([d["r"] for d in rows])
tc = st.median([d["tConvert"] for d in rows])

print("  tPCSetup 中位 = %8.1f us" % (ts * 1e6))
print("  tConvert 中位 = %8.1f us" % (tc * 1e6))
print("  ma(amul) 中位 = %8.2f us" % (ma * 1e6))
print("  mp(apply) 中位= %8.2f us" % (mp * 1e6))
print("  tIter 中位    = %8.2f us" % (ti * 1e6))
print("")
print("  R 中位        = %8.2f" % rr)
print("")

print("levels -> r 汇总（含外推对照）:")
pts = [(0, 9.84, 448.7), (2, 22.43, 1259.1), (5, 35.00, 2920.1), (10, rr, ts * 1e6)]
print("  %-8s %-10s %-12s %s" % ("levels", "r", "tPCSetup/us", "每级增量"))
prev = None
for lv, r, t in pts:
    inc = "" if prev is None else "%+.2f" % ((r - prev[1]) / (lv - prev[0]))
    print("  %-8d %-10.2f %-12.1f %s" % (lv, r, t, inc))
    prev = (lv, r)
