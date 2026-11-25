#!/usr/bin/env python3
"""诊断 tPCSetup 的分布形状：中位 vs 均值 vs 总量/次数。"""
import os, statistics as st
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

print("=" * 100)
print("tPCSetup 分布诊断（s=3, 各 K, 第 1 轮）")
print("=" * 100)
print("  %4s %8s %10s %10s %10s %12s %12s %10s" %
      ("K","重建数","中位/µs","均值/µs","P25/µs","P75/µs","总量/次数","r=中位"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    reb = [d for d in rows if d["reused"]==0 and d["tPCSetup"]>1e-4]
    if not reb: continue
    v = sorted(d["tPCSetup"] for d in reb)
    tot = sum(v)/len(v)
    ti = [d["tIter"] for d in reb if d["tIter"]>0]
    med = st.median(v)
    q = st.quantiles(v, n=4)
    print("  %4d %8d %10.0f %10.0f %10.0f %10.0f %12.0f %10.2f"
          % (K, len(v), med*1e6, tot*1e6, q[0]*1e6, q[2]*1e6, tot*1e6, med/st.median(ti)))

print()
print("  ── K=1 的完整分布（前 30 个重建步的 tPCSetup, µs）──")
rows = load("s_pc_s3_k1_r1.csv")
reb = [d["tPCSetup"]*1e6 for d in rows if d["reused"]==0 and d["tPCSetup"]>1e-4]
print("    " + " ".join("%.0f" % x for x in reb[:40]))
print("  ── K=8 的前 30 个 ──")
rows = load("s_pc_s3_k8_r1.csv")
reb = [d["tPCSetup"]*1e6 for d in rows if d["reused"]==0 and d["tPCSetup"]>1e-4]
print("    " + " ".join("%.0f" % x for x in reb[:40]))
print()
print("  ★ 若 K=1 的前若干次明显高于 K=8，说明是【进程内的前若干次重建更慢】")
