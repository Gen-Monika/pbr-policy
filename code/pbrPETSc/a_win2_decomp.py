import re, statistics as st, sys
sys.path.insert(0,"/root/autodl-tmp/PBR")
from pbrcost import _rows
P="/root/autodl-tmp/PBR"
TRE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$"); NRE=re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
def series(p):
    ts=[];ns=[];cur=[];s_=False
    for ln in open(p,errors="ignore"):
        m=TRE.match(ln)
        if m:
            if s_: ns.append(sum(cur))
            cur=[]; ts.append(float(m.group(1))); s_=True; continue
        mm=NRE.search(ln)
        if mm: cur.append(int(mm.group(1)))
    if s_: ns.append(sum(cur))
    n=min(len(ts),len(ns)); return ts[:n],ns[:n]
def rbl(pc):
    rr=_rows(pc); seen={}
    for x in rr:
        ti=int(x["timeIndex"])
        if int(x["rep"])>=0 and ti not in seen: seen[ti]=x
    return [int(seen[t]["reusedFrom"])<0 for t in sorted(seen)]
CAL={"fx":(57.9,173.7),"l20":(90.6,271.8)}
for tag,(lo,hi) in CAL.items():
    D={}
    for K in range(1,7):
        runs=[]
        for r in (1,2,3):
            ts,nn=series("%s/w2%s_case/log.K%d.r%d"%(P,tag,K,r)); bb=rbl("%s/w2%s_pc_K%d_r%d.csv"%(P,tag,K,r))
            n=min(len(ts),len(nn),len(bb)); runs.append((ts[:n],nn[:n],bb[:n]))
        D[K]=runs
    print("="*112); print("【%s】ρ 标定区间 [%.1f, %.1f]  —— 分解：ρ 不确定 vs 阶段差异"%(tag,lo,hi))
    for W in ("W1","W2"):
        print("  ── %s"%W)
        for rho in (lo, hi):
            med={}
            for K,runs in D.items():
                cs=[]
                for ts,nn,bb in runs:
                    n=min(len(ts),len(nn),len(bb))
                    idx=[i for i in range(n) if (ts[i]<=1.0)==(W=="W1")]
                    cs.append(sum(nn[i] for i in idx)+rho*sum(1 for i in idx if bb[i]))
                med[K]=st.median(cs)
            ks=min(med,key=med.get)
            print("     ρ=%7.1f  →  K*=%d     (各K成本: %s)"%(rho,ks," ".join("K%d=%.0f"%(k,med[k]) for k in sorted(med))))
    # 决定量：同窗口内 rho 变化引起的 K* 移动 vs 同 rho 下窗口变化
    allk=set()
    for W in ("W1","W2"):
        for rho in (lo,hi):
            med={}
            for K,runs in D.items():
                cs=[sum(nn[i] for i in range(min(len(ts),len(nn),len(bb))) if (ts[i]<=1.0)==(W=="W1"))+
                    rho*sum(1 for i in range(min(len(ts),len(nn),len(bb))) if (ts[i]<=1.0)==(W=="W1") and bb[i]) for ts,nn,bb in runs]
                med[K]=st.median(cs)
            allk.add((W,rho,min(med,key=med.get)))
    ks_w1={r:k for w,r,k in allk if w=="W1"}; ks_w2={r:k for w,r,k in allk if w=="W2"}
    move_rho_w1=abs(ks_w1[hi]-ks_w1[lo]); move_rho_w2=abs(ks_w2[hi]-ks_w2[lo])
    move_win_lo=abs(ks_w2[lo]-ks_w1[lo]); move_win_hi=abs(ks_w2[hi]-ks_w1[hi])
    print("  ★ 分解:")
    print("     ρ 从 %.1f→%.1f（同窗口内）: K* 移动 %d / %d 步   [W1: K%d→K%d, W2: K%d→K%d]"
          %(lo,hi,move_rho_w1,move_rho_w2,ks_w1[lo],ks_w1[hi],ks_w2[lo],ks_w2[hi]))
    print("     窗口 W1→W2（同 ρ 下）:      K* 移动 %d / %d 步   [ρ=lo: K%d→K%d, ρ=hi: K%d→K%d]"
          %(move_win_lo,move_win_hi,ks_w1[lo],ks_w2[lo],ks_w1[hi],ks_w2[hi]))
    # K* 的完整张成
    spread=sorted(set(k for _,_,k in allk))
    print("     K* 总张成 = %s   (跨 ρ 与跨窗合计)"%("{"+",".join("K%d"%k for k in spread)+"}"))
