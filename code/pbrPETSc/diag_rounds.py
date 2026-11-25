#!/usr/bin/env python3
"""
★★★ 决定性诊断：tPCSetup / tIter 的单次值是否【跨轮漂移】（热漂移假设）
     vs 【跨 K 且跨轮稳定】（cache 假设）

关键区分：
  - 热漂移  ⇒ 同一 K 的不同轮之间差异大，且随扫描顺序单调
  - cache   ⇒ 同一 K 的同一轮内，重建步与复用步差异大，但跨轮稳定
"""
import os, statistics as st
from collections import defaultdict
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
def load(p, rep_only=True):
    rows=[]
    if not os.path.exists(p): return rows
    for ln in open(p):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(CSV_HDR,q))
            for k in d:
                if k not in ("field","kind"): d[k]=float(d[k])
            if rep_only and int(d["rep"])<0: continue
            rows.append(d)
        except ValueError: pass
    return rows

PREFIX = os.environ.get("PREFIX", "s_pc_s3")
print("=" * 112)
print("★★★ 跨轮诊断（前缀 %s）" % PREFIX)
print("=" * 112)
print("\n  1. ★ 同一 K 的不同轮：单次成本（重建步）")
print("  %4s %5s %12s %12s %10s %10s %10s" %
      ("K","轮","tPCSetup/µs","tIter/µs","ma/µs","mp/µs","r"))
for K in (1,2,3,5,8):
    for R in range(1,6):
        rows = load("%s_k%d_r%d.csv" % (PREFIX, K, R))
        reb = [d for d in rows if d["reused"]==0]
        if not reb: continue
        f = lambda k: st.median([d[k] for d in reb])
        print("  %4d %5d %12.0f %12.2f %10.2f %10.2f %10.2f"
              % (K, R, f("tPCSetup")*1e6, f("tIter")*1e6,
                 f("ma")*1e6, f("mp")*1e6, st.median([d["r"] for d in reb if d["r"]>0])))
    print()

print("  2. ★★ 重建步 vs 复用步的 tIter，逐轮逐 K")
print("  %4s %5s %14s %14s %10s" % ("K","轮","重建步 tIter","复用步 tIter","差异"))
for K in (1,2,3,5,8):
    for R in range(1,6):
        rows = load("%s_k%d_r%d.csv" % (PREFIX, K, R))
        reb = [d["tIter"] for d in rows if d["reused"]==0]
        reu = [d["tIter"] for d in rows if d["reused"]!=0]
        if not reb: continue
        b = st.median(reb)*1e6
        u = (st.median(reu)*1e6) if reu else float("nan")
        print("  %4d %5d %14.2f %14.2f %9s"
              % (K, R, b, u, ("%+.1f%%" % ((u/b-1)*100)) if reu else "-"))
    print()

print("  3. ★★★ 全 run 内 tIter 的时序（K=1 与 K=3，各轮前/中/后 30 个测量行）")
print("  %4s %5s %12s %12s %12s" % ("K","轮","前30中位","中30中位","后30中位"))
for K in (1,3,8):
    for R in range(1,6):
        rows = load("%s_k%d_r%d.csv" % (PREFIX, K, R))
        if not rows: continue
        v = [d["tIter"]*1e6 for d in rows]
        n = len(v)
        print("  %4d %5d %12.2f %12.2f %12.2f"
              % (K, R, st.median(v[:30]), st.median(v[n//2-15:n//2+15]), st.median(v[-30:])))
    print()
