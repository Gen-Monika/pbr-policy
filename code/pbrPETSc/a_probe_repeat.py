import sys,json,statistics as st
sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import ORDER,Env,load_phase,sim_fixed,sim_online_detail

def run_probe(env,rho,T,B0,L,P):
    """每 P 个决策步执行一次探测（强制重建 + 强制复用 L 步）。"""
    know={};levels=[];it=0.0;rb=0;tot=0.0;held=-1;acc=0.0;accn=0;a=0
    t=1; decisions=0; nprobe=0
    while t<=T:
        rc1=rho
        if t<B0 or held<0 or not levels:
            N=env(t,0);it+=N;rb+=1;tot+=rc1+N
            acc,accn=(0.0,0) if t<B0 else (rc1+N,1)
            levels.append(N);a=1;held=t;t+=1;continue
        # 该做探测了吗
        if decisions>0 and decisions%P==0 and t+L<=T:
            # 强制重建
            N=env(t,0);it+=N;rb+=1;tot+=rc1+N
            acc,accn=rc1+N,1;levels.append(N);a=1;held=t;t+=1;nprobe+=1
            for _ in range(L):
                if t>T: break
                age=t-held;N=env(t,age);it+=N;tot+=N;acc+=N;accn+=1
                if levels:
                    bm=st.median(levels)
                    if bm>1e-9: know.setdefault(age,[]).append(N-bm)
                a=age+1;t+=1
            decisions+=1
            continue
        age=t-held
        avg=acc/accn if accn else tot/max(1,t-1)
        lvl=levels[-1]
        if age in know and know[age]: d=st.median(know[age])
        elif know:
            ks=sorted(k for k in know if know[k])
            if len(ks)>=2:
                a2,a1=ks[-1],ks[-2]
                d2,d1=st.median(know[a2]),st.median(know[a1])
                d=st.median(know[a2])+(d2-d1)/max(1e-9,a2-a1)*(age-a2)
            else: d=st.median(know[ks[-1]])
        else: d=0.0
        rebuild=(lvl+max(0.0,d))>avg
        if rebuild:
            N=env(t,0);it+=N;rb+=1;tot+=rc1+N
            acc,accn=rc1+N,1;levels.append(N);a=1;held=t
        else:
            N=env(t,a);it+=N;tot+=N;acc+=N;accn+=1
            if levels:
                bm=st.median(levels)
                if bm>1e-9: know.setdefault(age,[]).append(N-bm)
            a+=1
        decisions+=1;t+=1
    return tot,it,rb,len([k for k in know if k>=2]),sum(len(v) for k,v in know.items() if k>=2),nprobe

out={}
for tag in ORDER:
    ph=load_phase(tag);tab,rho,T=ph["tab"],ph["r1"],ph["T"];env=Env(tab,sFact=ph["s"])
    cA,itA,rbA,_,_=sim_online_detail(env,rho,T,100,step_cost=False)
    fx={K:sim_fixed(env,rho,K,T,100)[0] for K in range(1,8)}
    bk=min(fx,key=lambda k:fx[k]); cbest=fx[bk]
    row={"A_cost":round(cA,1),"A_regret":round(100*(cA-cbest)/cbest,2),"best_K":bk,"variants":{}}
    for L in (2,3):
        for P in (20,50,100):
            c,it_,rb_,nages,nobs,npr=run_probe(env,rho,T,100,L,P)
            row["variants"]["L%dP%d"%(L,P)]={"cost":round(c,1),
                "regret":round(100*(c-cbest)/cbest,2),"vsA":round(100*(c-cA)/cA,2),
                "n_ages_ge2":nages,"n_obs_ge2":nobs,"n_probes":npr}
    out[tag]=row
    best=min(row["variants"],key=lambda k:row["variants"][k]["cost"])
    print("%-5s A %7.0f (%+.2f%%) | 最优 %-8s %7.0f (%+.2f%%) obs≥2:%-4d"%(
        tag,cA,row["A_regret"],best,row["variants"][best]["cost"],
        row["variants"][best]["regret"],row["variants"][best]["n_obs_ge2"]))
json.dump(out,open("/root/autodl-tmp/PBR_vt_20261031/vt_probe_repeat.json","w"),indent=1)
print("wrote")
