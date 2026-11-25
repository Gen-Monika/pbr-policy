#!/usr/bin/env python3
"""双峰诊断：tIter 在同一个 run 内是否【混合】两种模式，还是整轮取一种。"""
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
            if int(d["rep"])<0: continue
            rows.append(d)
        except ValueError: pass
    return rows

def mode(v, lo, hi):
    """把值分到低位模式/高位模式"""
    n_lo = sum(1 for x in v if x < (lo+hi)/2)
    return n_lo, len(v)-n_lo

print("=" * 108)
print("★ 双峰诊断：tIter 与 tPCSetup 在单个 run 内的模式占比")
print("=" * 108)
print("  %4s %4s %8s %14s %14s %10s" %
      ("K","轮","样本","低位模式(<131)","高位模式(>=131)","低位占比"))
LO, HI = 116.0, 147.0
for K in (1,2,3,5,8):
    for R in range(1,6):
        rows = load("s_pc_s3_k%d_r%d.csv" % (K,R))
        if not rows: continue
        v = [d["tIter"]*1e6 for d in rows]
        nlo, nhi = mode(v, LO, HI)
        print("  %4d %4d %8d %14d %14d %9.1f%%"
              % (K,R,len(v),nlo,nhi,100.0*nlo/len(v)))
    print()

print("  ── tPCSetup 的双峰（阈值 7.5 ms）──")
print("  %4s %4s %14s %14s %10s" % ("K","轮","低位(<7500)","高位(>=7500)","低位占比"))
for K in (1,2,3,5,8):
    for R in range(1,6):
        rows = load("s_pc_s3_k%d_r%d.csv" % (K,R))
        reb = [d["tPCSetup"]*1e6 for d in rows if d["reused"]==0]
        if not reb: continue
        nlo = sum(1 for x in reb if x < 7500)
        print("  %4d %4d %14d %14d %9.1f%%"
              % (K,R,nlo,len(reb)-nlo,100.0*nlo/len(reb)))
    print()

print("  ── ★ 相关性：低位 tIter 是否与低位 tPCSetup 同时出现 ──")
print("  %4s %4s %14s %14s %10s" % ("K","轮","tPCSetup均值","tIter均值","同步?"))
for K in (1,2,3,5,8):
    for R in range(1,6):
        rows = load("s_pc_s3_k%d_r%d.csv" % (K,R))
        reb = [d for d in rows if d["reused"]==0]
        if not reb: continue
        ts = st.mean([d["tPCSetup"] for d in reb])*1e6
        ti = st.mean([d["tIter"] for d in reb])*1e6
        # 若 tPCSetup 与 tIter 都在低位或都在高位，则同步
        syncT = "低" if ts < 7500 else "高"
        syncI = "低" if ti < 131 else "高"
        print("  %4d %4d %14.0f %14.2f %10s" % (K,R,ts,ti,
              "✓ 同步" if syncT==syncI else "✗ 错位"))
    print()
