import os, collections, statistics as st, sys, json
P2="/root/autodl-tmp/PBR"; sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import CFG, phase_scan_anchor, _rows, _per_step_N
A,K=6,7
tag="fx"; lvl,T,B0=CFG[tag]; Bscan=phase_scan_anchor(tag)
# 固定 age，按来源文件 B 分组，看是否有系统性差异
by=collections.defaultdict(list)
for B in range(Bscan-A,Bscan+1):
    c=os.path.join(P2,"phs_%s_B%d_K%d_r1.csv"%(tag,B,K))
    l=os.path.join(P2,"phs_%s"%tag,"log.B%dK%d_r1"%(B,K))
    if not (os.path.exists(c) and os.path.exists(l)): continue
    rr=_rows(c); seen={}
    for x in rr:
        if int(x["rep"])>=0 and int(x["timeIndex"]) not in seen: seen[int(x["timeIndex"])]=x
    steps=[seen[t] for t in sorted(seen)]; Ns=_per_step_N(l); n=min(len(steps),len(Ns))
    for i in range(n):
        t=i+1
        if t<=Bscan: continue
        rf=int(steps[i]["reusedFrom"]); age=0 if rf<0 else t-rf
        by[(B,age)].append(Ns[i])
print("tag=%s  固定 age 下各来源文件的 N 均值（t>Bscan）"%tag)
for age in range(0,4):
    row=[]
    for B in range(Bscan-A,Bscan+1):
        v=by.get((B,age))
        if v: row.append("B%d n=%d mean=%.2f sd=%.2f"%(B,len(v),st.mean(v),st.pstdev(v)))
    print(" age=%d"%age)
    for r in row: print("   ",r)
    means=[st.mean(by[(B,age)]) for B in range(Bscan-A,Bscan+1) if by.get((B,age))]
    if len(means)>1:
        print("   跨文件均值极差=%.3f  各文件均值=%s"%(max(means)-min(means),[round(m,2) for m in means]))
