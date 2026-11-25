#!/usr/bin/env python3
"""定位 tPCSetup 随 K 变化的原因：拆 ma / mp / 双峰占比。"""
import os, statistics as st
from collections import Counter
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
def load(p):
    rows=[]
    if not os.path.exists(p): return rows
    for ln in open(p):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(CSV_HDR,q))
            for k in d:
                if k not in ("field","kind"): d[k]=float(d[k])
            rows.append(d)
        except ValueError: pass
    return rows

print("=" * 106)
print("tPCSetup 随 K 变化的原因定位（s=3, 第 1 轮，均为重建步）")
print("=" * 106)
print("  %4s %10s %10s %10s %10s %10s %12s %10s" %
      ("K","tPCSetup","tAssemble","tConvert","ma","mp","tIter","tSetup/tIter"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    reb = [d for d in rows if d["reused"]==0 and d["tPCSetup"]>1e-4]
    if not reb: continue
    f = lambda key: st.mean([d[key] for d in reb])*1e6
    print("  %4d %10.0f %10.0f %10.0f %10.2f %10.2f %12.2f %10.2f"
          % (K, f("tPCSetup"), f("tAssemble"), f("tConvert"),
             f("ma"), f("mp"), f("tIter"),
             st.mean([d["tPCSetup"] for d in reb])/st.mean([d["tIter"] for d in reb])))

print()
print("  ── K=1 与 K=8 的 tPCSetup 直方图（µs 分箱，步长 500）──")
for K in (1,8):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    reb = [d["tPCSetup"]*1e6 for d in rows if d["reused"]==0 and d["tPCSetup"]>1e-4]
    h = Counter(int(x//500)*500 for x in reb)
    print("\n   K=%d  (n=%d)" % (K, len(reb)))
    for b in sorted(h):
        if h[b] >= 5:
            print("     %5d-%5d µs : %-5d %s" % (b, b+499, h[b], "#"*min(60,h[b]//8)))

print()
print("  ── tIter 随 K ──")
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    reb = [d["tIter"] for d in rows if d["reused"]==0 and d["tIter"]>0]
    if reb:
        print("     K=%2d  tIter 中位=%.2f 均值=%.2f  (n=%d)"
              % (K, st.median(reb)*1e6, st.mean(reb)*1e6, len(reb)))
