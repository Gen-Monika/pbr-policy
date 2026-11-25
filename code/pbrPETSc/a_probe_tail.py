"""把"早期年龄2可见"单独做出来：只改预热期末段的复用规则，不做周期探测。

四个变体，都只在 B0 附近动作，之后完全恢复正常判据：
  V0 现行：t<B0 每步重建
  V1 B0-2 处重建一次，然后连续复用 2 步（覆盖年龄 1,2），再恢复
  V2 B0-1 处重建一次，然后复用 2 步
  V3 预热最后 2 步复用（即 B0-2 前保留重建，最后两步不重建）
判读：能否在 l15/l20 上复现 P=50 探测的收益，且不在 x3/fl30/fx 上变差。
"""
import sys,json,statistics as st
sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import ORDER,Env,load_phase,sim_fixed,sim_online_detail

def core(env,rho,T,t_start,know0,levels0,B0=100):
    know={k:list(v) for k,v in know0.items()}; levels=list(levels0)
    it=0.0;rb=0;tot=0.0;held=-1;acc=0.0;accn=0;a=0
    for t in range(t_start,T+1):
        rc1=rho
        if t<B0 or held<0 or not levels:
            N=env(t,0);it+=N;rb+=1;tot+=rc1+N
            acc,accn=rc1+N,1;levels.append(N);a=1;held=t;continue
        age=t-held
        avg=acc/accn if accn else tot/max(1,t-t_start+1)
        lvl=levels[-1]
        if age in know and know[age]: d=st.median(know[age])
        elif know:
            ks=sorted(k for k in know if know[k])
            if len(ks)>=2:
                a2,a1=ks[-1],ks[-2]
                d2,d1=st.median(know[a2]),st.median(know[a1])
                d=d2+(d2-d1)/max(1e-9,a2-a1)*(age-a2)
            else: d=st.median(know[ks[-1]])
        else: d=0.0
        if (lvl+max(0.0,d))>avg:
            N=env(t,0);it+=N;rb+=1;tot+=rc1+N
            acc,accn=rc1+N,1;levels.append(N);a=1;held=t
        else:
            N=env(t,a);it+=N;tot+=N;acc+=N;accn+=1
            if levels:
                bm=st.median(levels)
                if bm>1e-9: know.setdefault(age,[]).append(N-bm)
            a+=1
    return tot,it,rb,know

def variant(env,rho,T,variant_id):
    B0=100
    if variant_id=="V0":
        return core(env,rho,T,1,{},[])
    # V1/V2: 在 B0-k 处重建，然后复用 L 步，再恢复
    if variant_id=="V1": start, L = B0-2, 2
    elif variant_id=="V2": start, L = B0-1, 2
    elif variant_id=="V3": start, L = B0-2, 2
    # 预热直到 start-1 每步重建
    it=0.0;rb=0;tot=0.0;levels=[];know={}
    for t in range(1,start):
        N=env(t,0);it+=N;rb+=1;tot+=rho+N;levels.append(N)
    # 在 start 强制重建，然后复用 L 步
    t=start
    N=env(t,0);it+=N;rb+=1;tot+=rho+N;levels.append(N);held=t
    for _ in range(L):
        t+=1
        age=t-held;N=env(t,age);it+=N;tot+=N
        bm=st.median(levels)
        if bm>1e-9: know.setdefault(age,[]).append(N-bm)
    # 恢复（t 已越过探测段）
    c2,i2,r2,_=core(env,rho,T,t+1,know,levels)
    return tot+c2, it+i2, rb+r2, know

out={}
for tag in ORDER:
    ph=load_phase(tag);tab,rho,T=ph["tab"],ph["r1"],ph["T"];env=Env(tab,sFact=ph["s"])
    fx={K:sim_fixed(env,rho,K,T,100)[0] for K in range(1,8)}
    bk=min(fx,key=lambda k:fx[k]);cb=fx[bk]
    row={"best_K":bk,"variants":{}}
    for v in ["V0","V1","V2","V3"]:
        c,it_,rb_,know=variant(env,rho,T,v)
        row["variants"][v]={"cost":round(c,1),"regret":round(100*(c-cb)/cb,3),
                            "n_obs_ge2":sum(len(vv) for k,vv in know.items() if k>=2)}
    base=row["variants"]["V0"]["regret"]
    row["A_regret"]=base
    out[tag]=row
    print("%-5s K*=%-2d  V0 %+.2f%% | V1 %+.2f%% (%+.2f)  V2 %+.2f%% (%+.2f)  V3 %+.2f%% (%+.2f)"
          %(tag,bk,base,row["variants"]["V1"]["regret"],row["variants"]["V1"]["regret"]-base,
            row["variants"]["V2"]["regret"],row["variants"]["V2"]["regret"]-base,
            row["variants"]["V3"]["regret"],row["variants"]["V3"]["regret"]-base))
json.dump(out,open("/root/autodl-tmp/PBR_vt_20261031/vt_probe_tail.json","w"),indent=1)
print("wrote")
