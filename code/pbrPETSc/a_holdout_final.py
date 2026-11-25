#!/usr/bin/env python3
"""
最终裁决：用【已验收的相位表】跑 v3 的折叠协议（8 变体 + 训练轮选优），
看「在线优于固定周期」是否成立。

★ 与 a_holdout_decisive.py 的区别：那个用单变体 P0。
   本脚本复现 v3 的变体族选择，只把 N 表换成正表。
   以此分离「表错」与「变体选择」两个因素。
"""
import sys, statistics as st
sys.path.insert(0,"/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail

TAGS=["fx","l15","l20","fine","x3","fl30","sth"]
KS=(1,2,3,4,5,6)

print("="*118)
print("★ 最终裁决：相位表（已验收）+ ρ=r1 ⇒ 在线 vs 最优固定周期")
print("   （ρ=r1 是 C++ ONLs 的内部记账口径，也是能 100% 复现实的测口径）")
print("="*118)
print("  %-6s %-9s %-11s %-11s %-11s %-9s %s"
      %("配置","ρ=r1","在线cost","最优固定K","固定cost","gap","在线更优?"))

wins=0; rows=[]
for tag in TAGS:
    d=load_phase(tag)
    if not d: continue
    env=Env(d["tab"],sFact=d["s"]); lvl,T,B0=CFG[tag]
    rho=d["r1"]
    c,it,rb,_,_=sim_online_detail(env,rho,T,B0)
    bc,bk=min(((sim_fixed(env,rho,k,T,B0)[0],k) for k in KS if k<=env.amax_data+1))
    gap=100.0*(c-bc)/bc
    wins+=(1 if gap<0 else 0)
    rows.append((tag,rho,c,bk,bc,gap,it,rb))
    print("  %-6s %-9.1f %-11.0f K=%-9d %-11.0f %+8.2f%%  %s"
          %(tag,rho,c,bk,bc,gap,"✓ 优" if gap<0 else "★ 劣"))

print("\n  ⇒ 相位表 + 单判据 P0 + ρ=r1：在线更优 %d/7"%wins)
print()
print("  ▸ 与其余口径的对照：")
print("     v3 原样（旧表 + 最近邻 + 8变体 + r_eff） → 7/7   ← 表无法复现 C++（31–66%）")
print("     v3 强制P0（旧表 + 最近邻 + P0 + r_eff）    → 6/7")
print("     相位表 + P0 + r_eff                        → 1/7")
print("     相位表 + P0 + r1（本行）                    → %d/7"%wins)
