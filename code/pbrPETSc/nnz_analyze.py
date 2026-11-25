#!/usr/bin/env python3
"""逐 levels 拆解 ma / mp / tPCSetup，找出 r 增量衰减的真正来源。"""
import glob, os, re, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

NNZ = {}
for lv in (0,1,2,3,5,8,10,12,15,18,20,25,30):
    f = "/root/autodl-tmp/PBR/nnz/log.lv%d" % lv
    if os.path.exists(f):
        for ln in open(f, errors="ignore"):
            m = re.search(r"PBR_NNZ levels=(\d+) n=(\d+) nz_used=(\d+)", ln)
            if m:
                NNZ[int(m.group(1))] = int(m.group(3))
                break

print("=" * 108)
print("逐 levels 拆解：ma（原始矩阵 SpMV）/ mp（因子三角求解）/ tPCSetup")
print("=" * 108)
print("  %7s %10s %10s %10s %10s %10s %10s %10s" %
      ("levels", "nz_used", "tPCS/us", "ma/us", "mp/us", "tIter/us",
       "tPCS/nnz", "mp/nnz"))

prev = None
rows = []
for lv in sorted(NNZ):
    f = "/root/autodl-tmp/PBR/nnz_lv%d.csv" % lv
    if not os.path.exists(f):
        continue
    tps, mas, mps = [], [], []
    for ln in open(f):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25:
            continue
        try:
            d = dict(zip(CSV_HDR, p))
            if float(d["reused"]) != 0 or float(d["tPCSetup"]) <= 1e-4:
                continue
            if float(d["tIter"]) <= 0:
                continue
            tps.append(float(d["tPCSetup"]))
            mas.append(float(d["ma"]))
            mps.append(float(d["mp"]))
        except ValueError:
            continue
    if not tps:
        continue
    nz = NNZ[lv]
    tp = st.median(tps) * 1e6
    ma = st.median(mas) * 1e6
    mp = st.median(mps) * 1e6
    rows.append((lv, nz, tp, ma, mp, tp / nz, mp / nz))
    dnz = "" if prev is None else "%+d" % (nz - prev[1])
    print("  %7d %10d %10.1f %10.2f %10.2f %10.2f %10.5f %10.5f"
          % (lv, nz, tp, ma, mp, ma + mp, tp / nz, mp / nz)
          + "   dnz=" + dnz
          + ("   dtPCS=%+.1f%%" % ((tp - prev[2]) / prev[2] * 100) if prev else "")
          + ("   dmp=%+.1f%%" % ((mp - prev[4]) / prev[4] * 100) if prev else ""))
    prev = (lv, nz, tp, ma, mp)

print()
print("  ── r 与其拆解 ──")
print("  %7s %10s %10s %12s %12s" % ("levels", "r", "tPCS/tIter",
      "d(r)/d(level)", "d(mp)/d(level) %"))
prev = None
for lv, nz, tp, ma, mp, tn, mn in rows:
    r = tp / (ma + mp)
    dr = "" if prev is None else "%+.2f" % ((r - prev[5]) / (lv - prev[0]))
    dm = "" if prev is None else "%+.1f" % ((mp - prev[4]) / prev[4] * 100 / (lv - prev[0]))
    print("  %7d %10.2f %12.2f %13s %14s" % (lv, r, r, dr, dm))
    prev = (lv, nz, tp, ma, mp, r)
