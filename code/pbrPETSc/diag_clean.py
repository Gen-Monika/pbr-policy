#!/usr/bin/env python3
"""★ 只取 rep==8 的有效测量行，重查 tPCSetup / ma / mp / tIter 随 K 的变化。"""
import os, re, statistics as st
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
            if int(d["rep"]) < 0: continue     # ★ 只保留有效测量行
            rows.append(d)
        except ValueError: pass
    return rows

print("=" * 112)
print("★ 干净口径（rep==8）下的单次成本（s=3, 第 1 轮）")
print("=" * 112)
print("  %4s %8s %10s %10s %9s %9s %11s %10s %10s" %
      ("K","有效行","tPCSetup","tAssemble","tConvert","ma","mp","tIter","r"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    reb = [d for d in rows if d["reused"]==0]
    if not reb: continue
    f = lambda key: st.median([d[key] for d in reb])*1e6
    print("  %4d %8d %10.0f %10.0f %9.0f %9.2f %9.2f %11.2f %10.2f"
          % (K, len(rows), f("tPCSetup"), f("tAssemble"), f("tConvert"),
             f("ma"), f("mp"), f("tIter"),
             st.median([d["r"] for d in reb if d["r"]>0])))

print()
print("  ── 分解 = 总 tPCSetup − 其他已知项？逐项求和 ──")
print("  %4s %12s %12s %12s %12s %12s" %
      ("K","Σ tPCSetup","Σ tAssemble","Σ tConvert","Σ tFreeze","Σ(tIter-tApply)"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    s = lambda key: sum(d[key] for d in rows)
    print("  %4d %12.3f %12.3f %12.3f %12.3f %12.3f"
          % (K, s("tPCSetup"), s("tAssemble"), s("tConvert"), s("tFreeze"),
             sum(d["tIter"] for d in rows)))

print()
print("  ── tIter 与 ma+mp 是否一致（校验列语义）──")
for K in (1,3,8):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    ok = sum(1 for d in rows if d["tIter"]>0 and abs(d["tIter"]-(d["ma"]+d["mp"]))<1e-9)
    tot = sum(1 for d in rows if d["tIter"]>0)
    print("     K=%2d : tIter == ma+mp 的行 %d/%d" % (K, ok, tot))

print()
print("  ── ★ tIter 分布（K=1 vs K=3 vs K=8）──")
for K in (1,3,8):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    v = sorted(d["tIter"]*1e6 for d in rows if d["tIter"]>0)
    if not v: continue
    q = st.quantiles(v, n=4)
    print("     K=%2d  n=%3d  中位=%.2f  P25=%.2f  P75=%.2f  min=%.2f max=%.2f"
          % (K, len(v), st.median(v), q[0], q[2], v[0], v[-1]))
