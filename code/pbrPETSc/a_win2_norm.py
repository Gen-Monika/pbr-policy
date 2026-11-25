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
    # 先看窗口的绝对构成（用 K3 为例）
    print("="*116); print("【%s】"%tag)
    for K in (3,):
        ts,nn,bb=D[K][0]; n=len(ts)
        i1=[i for i in range(n) if ts[i]<=1.0]; i2=[i for i in range(n) if ts[i]>1.0]
        print("  K=%d 构成: W1 %d步 ΣN=%d rb=%d | W2 %d步 ΣN=%d rb=%d"
              %(K,len(i1),sum(nn[i] for i in i1),sum(1 for i in i1 if bb[i]),
                len(i2),sum(nn[i] for i in i2),sum(1 for i in i2 if bb[i])))
        print("     W1 每步均 N=%.1f   W2 每步均 N=%.1f   （后段迭代数显著下降 ⇒ 重建相对更贵）"
              %(sum(nn[i] for i in i1)/len(i1), sum(nn[i] for i in i2)/len(i2)))
    for rho in (lo,hi):
        C={}
        for W in ("W1","W2"):
            m={}; it={}; rb={}
            for K,runs in D.items():
                cs=[];its=[];rbs=[]
                for ts,nn,bb in runs:
                    n=min(len(ts),len(nn),len(bb))
                    idx=[i for i in range(n) if (ts[i]<=1.0)==(W=="W1")]
                    its.append(sum(nn[i] for i in idx)); rbs.append(sum(1 for i in idx if bb[i]))
                    cs.append(its[-1]+rho*rbs[-1])
                m[K]=st.median(cs); it[K]=st.median(its); rb[K]=st.median(rbs)
            C[W]=(m,it,rb)
        k1=min(C["W1"][0],key=C["W1"][0].get); k2=min(C["W2"][0],key=C["W2"][0].get)
        tot={K:C["W1"][0][K]+C["W2"][0][K] for K in C["W1"][0]}
        ks=min(tot,key=tot.get)
        # 归一化：以"分段最优"为基准，但把损失除以【两窗口总成本】
        seg=min(C["W1"][0].values())+min(C["W2"][0].values())
        grand=seg
        print("\n  ── ρ=%.1f    W1K*=%d  W2K*=%d  单K最优=%d"%(rho,k1,k2,ks))
        print("     %-6s %-32s %-32s %s"%("K","W1 (iters,rb,cost)","W2 (iters,rb,cost)","合计"))
        for K in sorted(C["W1"][0]):
            print("     %-6s (%6d,%3d,%7.0f)          (%6d,%3d,%7.0f)          %7.0f"
                  %("K%d"%K,C["W1"][1][K],C["W1"][2][K],C["W1"][0][K],
                    C["W2"][1][K],C["W2"][2][K],C["W2"][0][K],tot[K]))
        w2best=min(C["W2"][0].values())
        print("     扫W1得K%d 用到W2: 成本 %.0f vs 最优 %.0f  ⇒ 绝对增 %.0f, 相对全轨 %.3f%%, 相对W2 %.3f%%"
              %(k1,C["W2"][0][k1],w2best,C["W2"][0][k1]-w2best,
                100.0*(C["W2"][0][k1]-w2best)/grand, 100.0*(C["W2"][0][k1]-w2best)/w2best))
        print("     单K跨两窗最优K%d 相对分段最优: 绝对增 %.0f ⇒ 相对全轨 %.3f%%"
              %(ks,tot[ks]-seg,100.0*(tot[ks]-seg)/grand))
