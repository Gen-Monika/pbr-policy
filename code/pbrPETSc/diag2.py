#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一口径的启发式对照：先知型 vs 因果型 vs C++ 真实决策，两端口径都算。"""
import os, re, sys, statistics as st
from collections import defaultdict
P="/root/autodl-tmp/PBR"; sys.path.insert(0,P)
from pbrcost import Env, load_phase, CFG, sim_dp
HDR=("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,reusedFrom,"
     "adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,r,rTotal,tApplyAccum,"
     "nApplyCalls,tSetupAll,nBuildPC").split(",")
def cpp_rb(path):
    seen={}
    for ln in open(path,errors="ignore"):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(HDR,q)); ti=int(float(d["timeIndex"]))
            if float(d["rep"])>=0 and ti not in seen: seen[ti]=float(d["reusedFrom"])
        except ValueError: pass
    return set(t for t,v in seen.items() if v<0)
def price(env,rho,rb,T):
    tot=0.0;a=0
    for t in range(1,T+1):
        if t in rb or a==0: tot+=rho+env(t,0); a=1
        else: tot+=env(t,a); a+=1
    return tot
def cl(Nfn,rho,T,rule,f={}):
    tot=0.0;a=0;k0=None;b0=100;nrb=0
    for t in range(1,T+1):
        if rule=="ch":
            N=Nfn(t,0 if a==0 else a)
            rb=True if (t<b0 or a==0) else (N>max(2.0*(k0 if k0 else N),10.0))
        elif rule=="re":
            rb=True if (t<b0 or a==0) else (Nfn(t,a)>f.get("re",120.0))
            N=Nfn(t,0 if a==0 else a)
        else:
            N=Nfn(t,0 if a==0 else a)
            rb=True if (t<b0 or a==0) else (N>(k0 if k0 else N)*(1.0+f.get("fr",0.20)))
        if rb: k0=Nfn(t,0); tot+=rho+Nfn(t,0); a=1; nrb+=1
        else: tot+=N; a+=1
    return tot,nrb
def ca(Nfn,rho,T,rule,f={}):
    tot=0.0;a=0;k0=None;prev=None;b0=100;nrb=0
    for t in range(1,T+1):
        if rule=="ch":
            rb=True if (t<b0 or a==0 or prev is None) else (prev>max(2.0*(k0 if k0 is not None else prev),10.0))
        elif rule=="re":
            rb=True if (t<b0 or a==0 or prev is None) else (prev>f.get("re",120.0))
        else:
            rb=True if (t<b0 or a==0 or k0 is None or prev is None) else ((prev-k0)/k0>f.get("fr",0.20))
        if rb: N0=Nfn(t,0); k0=N0; tot+=rho+N0; prev=N0; a=1; nrb+=1
        else: Na=Nfn(t,a); tot+=Na; prev=Na; a+=1
    return tot,nrb
POLS=[("ONLch","Chalmers","ch"),("ONLre","REAC120","re"),("ONLra","20%规则","ra")]
for TAG in ["fx","l15","l20","fine","fl30"]:
    d=load_phase(TAG)
    if not d: continue
    lvl,T,B0=CFG[TAG]; env=Env(d["tab"],sFact=d["s"])
    print("="*104); print("【%s】 T=%d  r1=%.2f  s*r1=%.2f"%(TAG,T,d["r1"],d["r1"]*d["s"]))
    for lab,rho in [("rho=r1",d["r1"]),("rho=s*r1",d["r1"]*d["s"])]:
        orc=sim_dp(env,rho,T,B0,reach=30)[0]
        fx={K:price(env,rho,set(t for t in range(1,T+1) if t<B0 or (t-B0)%K==0),T) for K in (1,2,3,4,5,8,13,20)}
        Kb=min(fx,key=fx.get)
        print("  [%s] oracle=%.0f  最优固定周期 K*=K%d (%.0f, %+.2f%%)"%(lab,orc,Kb,fx[Kb],100*(fx[Kb]/orc-1)))
        print("    %-11s %10s %10s | %10s %10s | %s"%("规则","先知型","重建数","因果型","重建数","C++真实决策(同表定价)"))
        for pol,label,rule in POLS:
            c1=cl(env,rho,T,rule); c2=ca(env,rho,T,rule)
            p=os.path.join(P,"%s_heur_pc_%s_r1.csv"%(TAG,pol)); cpp="—"
            if os.path.exists(p):
                rb=cpp_rb(p)
                if rb and max(rb)<=T: cpp="%+.2f%% (nrb=%d)"%(100*(price(env,rho,rb,T)/orc-1),len(rb))
            print("    %-11s %+9.2f%% %10d | %+9.2f%% %10d | %s"%(label,100*(c1[0]/orc-1),c1[1],100*(c2[0]/orc-1),c2[1],cpp))
