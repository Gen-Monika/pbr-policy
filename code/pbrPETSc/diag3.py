#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验：C++ 的真实重建步集合 vs 因果型表上模拟的重建步集合，是否【逐位相同】。"""
import os, sys
from collections import defaultdict
P="/root/autodl-tmp/PBR"; sys.path.insert(0,P)
from pbrcost import Env, load_phase, CFG
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
def ca_set(Nfn,T,rule,reac=120.0,fr=0.20,factor=2.0,floor=10.0,b0=100):
    S=set();a=0;k0=None;prev=None
    for t in range(1,T+1):
        if rule=="ch": rb=True if (t<b0 or a==0 or prev is None) else (prev>max(factor*(k0 if k0 is not None else prev),floor))
        elif rule=="re": rb=True if (t<b0 or a==0 or prev is None) else (prev>reac)
        else: rb=True if (t<b0 or a==0 or k0 is None or prev is None) else ((prev-k0)/k0>fr)
        if rb: N0=Nfn(t,0); k0=N0; S.add(t); prev=N0; a=1
        else: prev=Nfn(t,a); a+=1
    return S
POLS=[("ONLch","Chalmers","ch"),("ONLre","REAC120","re"),("ONLra","20%","ra")]
print("="*96)
print("★ 核验：C++ 真实重建步集合 与 因果型表上模拟 的逐位一致性")
print("="*96)
print("  %-6s %-10s %8s %8s %8s %8s  %s"%("配置","规则","C++数","因果数","交","并","结论"))
for TAG in ["fx","l15","l20","fine","fl30"]:
    d=load_phase(TAG)
    if not d: continue
    lvl,T,B0=CFG[TAG]; env=Env(d["tab"],sFact=d["s"])
    for pol,label,rule in POLS:
        p=os.path.join(P,"%s_heur_pc_%s_r1.csv"%(TAG,pol))
        if not os.path.exists(p): continue
        A=cpp_rb(p); B=ca_set(env,T,rule)
        inter=len(A&B); uni=len(A|B)
        ok="✓ 逐位相同" if A==B else ("≈ Jaccard=%.3f"%(inter/uni) if uni else "?")
        print("  %-6s %-10s %8d %8d %8d %8d  %s"%(TAG,label,len(A),len(B),inter,uni,ok))
