#!/usr/bin/env python3
"""核对「在线 vs K=1」这一列（相对 K=1 的节省）。"""
import sys
sys.path.insert(0,"/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail
TAGS=["fx","l15","l20","fine","x3","fl30","sth"]
print("  %-6s %-12s %-12s %-12s %s"%("配置","在线","K=1","K*","在线相对K=1"))
for tag in TAGS:
    d=load_phase(tag)
    if not d: continue
    env=Env(d["tab"],sFact=d["s"]); lvl,T,B0=CFG[tag]; rho=d["r1"]
    c,_,_,_,_=sim_online_detail(env,rho,T,B0)
    c1=sim_fixed(env,rho,1,T,B0)[0]
    bc,bk=min(((sim_fixed(env,rho,k,T,B0)[0],k) for k in (1,2,3,4,5,6)))
    print("  %-6s %-12.0f %-12.0f K%-11d %+.2f%%"%(tag,c,c1,bk,100.0*(c-c1)/c1))
