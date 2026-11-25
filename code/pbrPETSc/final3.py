#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§7.5 / §7.6 定稿数据（唯一来源）。
   §7.5：因果型（可部署）——Chalmers / REAC / 20%；在线用 C++ 实测 ONLs 决策集
   §7.6：完美信念（我们自己的上界）+ 先知型（给对手塞入不可实现信息的上界）
"""
import os, sys, statistics as st
P="/root/autodl-tmp/PBR"; sys.path.insert(0,P)
from pbrcost import Env, load_phase, CFG, sim_dp, sim_fixed, sim_online_detail
HDR=("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,reusedFrom,"
     "adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,r,rTotal,tApplyAccum,"
     "nApplyCalls,tSetupAll,nBuildPC").split(",")
def cpp_rb(p):
    seen={}
    for ln in open(p,errors="ignore"):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(HDR,q)); ti=int(float(d["timeIndex"]))
            if float(d["rep"])>=0 and ti not in seen: seen[ti]=float(d["reusedFrom"])
        except ValueError: pass
    return set(t for t,v in seen.items() if v<0)
def price(env,rho,T,rb):
    tot=0.0;a=0
    for t in range(1,T+1):
        if t in rb or a==0: tot+=rho+env(t,0); a=1
        else: tot+=env(t,a); a+=1
    return tot
# ---- 因果型 ----
def causal(env,rho,T,B0,rule,factor=2.0,floor=10.0,reac=120.0,frac=0.20):
    tot=0.0;a=0;k0=None;prev=None;nrb=0
    for t in range(1,T+1):
        if t<B0 or a==0 or prev is None: rb=True
        elif rule=="ch": rb=prev>max(factor*(k0 if k0 is not None else prev),floor)
        elif rule=="re": rb=prev>reac
        else: rb=(k0 is not None and k0>1e-9) and ((prev-k0)/k0>frac)
        if rb: N0=env(t,0); k0=N0; tot+=rho+N0; prev=N0; a=1; nrb+=1
        else: prev=env(t,a); tot+=prev; a+=1
    return tot,nrb
# ---- 先知型（用本步自己的 N(t,a) 判定）----
def clair(env,rho,T,B0,rule,factor=2.0,floor=10.0,reac=120.0,frac=0.20):
    tot=0.0;a=0;k0=None;nrb=0
    for t in range(1,T+1):
        N=env(t,0 if a==0 else a)
        if t<B0 or a==0: rb=True
        elif rule=="ch": rb=N>max(factor*(k0 if k0 else N),floor)
        elif rule=="re": rb=N>reac
        else: rb=N>(k0 if k0 else N)*(1.0+frac)
        if rb: k0=env(t,0); tot+=rho+env(t,0); a=1; nrb+=1
        else: tot+=N; a+=1
    return tot,nrb
def perfect(env,rho,T,B0):
    tot=0.0;acc=0.0;accn=0;levels=[];held=-1
    for t in range(1,T+1):
        if t<B0 or held<0 or not levels: rb=True
        else:
            age=t-held; avg=acc/accn if accn else tot/max(1,t-1)
            rb=(levels[-1]+max(0.0,env(t,age)-env(t,0)))>avg
        if rb:
            N=env(t,0); tot+=rho+N
            acc,accn=(0.0,0) if t<B0 else (rho+N,1)
            levels.append(N); held=t
        else:
            N=env(t,t-held); tot+=N; acc+=N; accn+=1
    return tot
TAGS=["fx","l15","l20","fine","x3","fl30","sth"]; KS=(1,2,3,4,5,6,8,13,20)
FAC=[1.05,1.1,1.2,1.3,1.5,1.75,2.0,2.5,3.0,4.0,6.0,10.0]
REACS=[10,20,30,40,50,60,80,100,120,150,200]
D={}
for mode in ["r1","sr1"]:
    for TAG in TAGS:
        d=load_phase(TAG)
        if not d: continue
        lvl,T,B0=CFG[TAG]; env=Env(d["tab"],sFact=d["s"])
        rho=d["r1"] if mode=="r1" else d["r1"]*d["s"]
        orc=sim_dp(env,rho,T,B0,reach=30)[0]
        fx={K:sim_fixed(env,rho,K,T,B0)[0] for K in KS if K<=env.amax_data+1}
        Kb=min(fx,key=fx.get)
        row=dict(orc=orc,K1=fx[1],Kb=Kb,fix=fx[Kb],rho=rho)
        row["onl"]=sim_online_detail(env,rho,T,B0)[0]
        row["pf"]=perfect(env,rho,T,B0)
        row["ch"]=causal(env,rho,T,B0,"ch")[0]
        row["re"]=causal(env,rho,T,B0,"re")[0]
        row["ra"]=causal(env,rho,T,B0,"ra")[0]
        cvs=[causal(env,rho,T,B0,"ch",factor=f)[0] for f in FAC]
        row["cs"]=min(cvs); row["fs"]=FAC[cvs.index(min(cvs))]
        rvs=[causal(env,rho,T,B0,"re",reac=r)[0] for r in REACS]
        row["rs"]=min(rvs); row["restar"]=REACS[rvs.index(min(rvs))]
        row["ch_cl"]=clair(env,rho,T,B0,"ch")[0]
        row["re_cl"]=clair(env,rho,T,B0,"re")[0]
        row["ra_cl"]=clair(env,rho,T,B0,"ra")[0]
        # C++ 实测决策集定价（若存在）
        for pol,key in [("ONLc","onl_cpp"),("ONLch","ch_cpp"),("ONLre","re_cpp"),("ONLra","ra_cpp")]:
            p=os.path.join(P,"%s_heur_pc_%s_r1.csv"%(TAG,pol))
            if os.path.exists(p):
                rb=cpp_rb(p)
                if rb and max(rb)<=T: row[key]=price(env,rho,T,rb)
        D.setdefault(mode,{})[TAG]=row
import json
print(json.dumps({m:{t:{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()} for t,r in D[m].items()} for m in D}))
