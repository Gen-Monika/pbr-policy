import re, statistics as st, sys
sys.path.insert(0,"/root/autodl-tmp/PBR")
from pbrcost import _rows
P="/root/autodl-tmp/PBR"
TRE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$"); NRE=re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
def series(p):
    ts=[];ns=[];cur=[];st_=False
    for ln in open(p,errors="ignore"):
        m=TRE.match(ln)
        if m:
            if st_: ns.append(sum(cur))
            cur=[]; ts.append(float(m.group(1))); st_=True; continue
        mm=NRE.search(ln)
        if mm: cur.append(int(mm.group(1)))
    if st_: ns.append(sum(cur))
    n=min(len(ts),len(ns)); return ts[:n],ns[:n]
def rblist(pc):
    rr=_rows(pc); seen={}
    for x in rr:
        ti=int(x["timeIndex"])
        if int(x["rep"])>=0 and ti not in seen: seen[ti]=x
    return [int(seen[t]["reusedFrom"])<0 for t in sorted(seen)]
CAL={"fx":(57.9,10),"l20":(90.6,20)}

print("="*118)
print("★★★ (b) 完整裁决：跨物理阶段 K* 移动   [审计 W1-W6]")
print("="*118)
for tag,(r1,lv) in CAL.items():
    print("\n"+"─"*118); print("【%s】ρ ∈ [%.1f, %.1f]"%(tag,r1,r1*3))
    # 载入两批数据
    new={}; old={}
    for K in range(1,7):
        for r in (1,2,3):
            try:
                ts,nn=series("%s/w2%s_case/log.K%d.r%d"%(P,tag,K,r)); bb=rblist("%s/w2%s_pc_K%d_r%d.csv"%(P,tag,K,r))
                n=min(len(ts),len(nn),len(bb)); new.setdefault(K,[]).append((ts[:n],nn[:n],bb[:n]))
            except Exception as e: pass
            try:
                ts,nn=series("%s/k2%s_case/log.K%d.r%d"%(P,tag,K,r)); bb=rblist("%s/k2%s_pc_K%d_r%d.csv"%(P,tag,K,r))
                n=min(len(ts),len(nn),len(bb)); old.setdefault(K,[]).append((ts[:n],nn[:n],bb[:n]))
            except Exception as e: pass
    print("  数据: new(K..)=%s  old(K..)=%s"%(sorted(new),sorted(old)))

    # W6 跨轮确定性
    for lab,D in (("new",new),("old",old)):
        bad=[]
        for K,runs in D.items():
            sig=set((tuple(nn),tuple(bb)) for _,nn,bb in runs)
            if len(sig)!=1: bad.append(K)
        print("  W6 %s 跨轮逐位一致: %s"%(lab,"✓ 全部 %d 个 K"%len(D) if not bad else "★ K=%s 不同"%bad))

    # 窗口切分
    for lab,D in (("new",new),("old",old)):
        runs=D.get(1,[])
        if not runs: continue
        ts=runs[0][0]
        print("  %s: 总 %d 步, t<=1.0 有 %d 步, t>1.0 有 %d 步, 末步=%.4f"
              %(lab,len(ts),sum(1 for t in ts if t<=1.0),sum(1 for t in ts if t>1.0),ts[-1]))

    # W4/W5：ρ 全程扫描
    RHO=[r1*(1+2.0*i/12.0) for i in range(13)]
    print("\n  ρ 全程扫描（K* 集合与 penalty）:")
    print("    %-9s %-22s %-22s %-9s %s"%("ρ","W1 K*","W2 K*","单K最优","penalty(单K vs 分段最优)"))
    for rho in RHO:
        res={}
        for W in ("W1","W2"):
            med={}
            for K,runs in new.items():
                cs=[]
                for ts,nn,bb in runs:
                    n=min(len(ts),len(nn),len(bb))
                    idx=[i for i in range(n) if (ts[i]<=1.0)==(W=="W1")]
                    cs.append(sum(nn[i] for i in idx)+rho*sum(1 for i in idx if bb[i]))
                med[K]=st.median(cs)
            res[W]=med
        k1=min(res["W1"],key=res["W1"].get); k2=min(res["W2"],key=res["W2"].get)
        tot={K:res["W1"][K]+res["W2"][K] for K in res["W1"]}
        ks=min(tot,key=tot.get)
        seg=min(res["W1"].values())+min(res["W2"].values()); wh=tot[ks]
        pen=100.0*(wh-seg)/seg
        print("    %-9.1f K=%-6d            K=%-6d            K=%-6d  %.3f%%"%(rho,k1,k2,ks,pen))

    # W1 交叉核对：新(341步) vs 旧(344步) 的 K*
    print("\n  W1 交叉核对（新 341 步 endTime=2 vs 旧 344 步 endTime=1）:")
    for rho in (r1, r1*3):
        out=[]
        for lab,D in (("new341",new),("old344",old)):
            if not D: continue
            med={}
            for K,runs in D.items():
                cs=[]
                for ts,nn,bb in runs:
                    n=min(len(ts),len(nn),len(bb))
                    idx=[i for i in range(n) if ts[i]<=1.0]
                    cs.append(sum(nn[i] for i in idx)+rho*sum(1 for i in idx if bb[i]))
                med[K]=st.median(cs)
            out.append((lab,min(med,key=med.get)))
        print("    ρ=%.1f   %s"%(rho,"   ".join("%s: K*=%d"%x for x in out)))
