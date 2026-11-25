#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chalmers 的 factor 常数是否"幸运值"？扫 factor ∈ [1.05, 4]，因果型，rho=r1。"""
import os, sys
P="/root/autodl-tmp/PBR"; sys.path.insert(0,P)
from pbrcost import Env, load_phase, CFG, sim_dp
def chal(env,rho,T,B0,factor,floor=10.0):
    tot=0.0;a=0;k0=None;prev=None
    for t in range(1,T+1):
        rb = True if (t<B0 or a==0 or prev is None) else (prev>max(factor*(k0 if k0 is not None else prev),floor))
        if rb: N0=env(t,0); k0=N0; tot+=rho+N0; prev=N0; a=1
        else: prev=env(t,a); tot+=prev; a+=1
    return tot
FAC=[1.05,1.1,1.2,1.3,1.5,1.75,2.0,2.5,3.0,4.0,6.0,10.0]
TAGS=["fx","l15","l20","fine","fl30","x3"]
print("="*112)
print("★ 敏感性：Chalmers 的 factor 常数（论文硬编码 2.0）在各配置上的最优值")
print("="*112)
hdr="  %-6s"%("配置")+"".join("%9s"%("f=%.2f"%f) for f in FAC)+"   %s"%("最优f")
print(hdr)
OPTS={}
for TAG in TAGS:
    d=load_phase(TAG)
    if not d: continue
    lvl,T,B0=CFG[TAG]; env=Env(d["tab"],sFact=d["s"]); rho=d["r1"]
    orc=sim_dp(env,rho,T,B0,reach=30)[0]
    vals=[chal(env,rho,T,B0,f) for f in FAC]
    rel=[100*(v/orc-1) for v in vals]
    bi=min(range(len(FAC)),key=lambda i:rel[i]); OPTS[TAG]=FAC[bi]
    print("  %-6s"%TAG+"".join("%+8.2f%%"%r for r in rel)+"   f*=%.2f"%FAC[bi])
print()
print("★ 若最优 factor 随配置分散 ⇒ 硬编码 2.0 是'幸运值'，而非普适常量")
print("  各配置最优 f*: "+", ".join("%s=%.2f"%(k,v) for k,v in OPTS.items()))
sp=[v for v in OPTS.values()]
print("  f* 范围 [%.2f, %.2f]，跨度 %.2f×"%(min(sp),max(sp),max(sp)/min(sp)))
