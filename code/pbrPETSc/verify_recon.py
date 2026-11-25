#!/usr/bin/env python3
"""自检：对 v3 旧表的重建是否忠实（用 v3 报过的数字反查）。"""
import sys, statistics as st
from collections import defaultdict
sys.path.insert(0,"/root/autodl-tmp/PBR")

src = open("/root/autodl-tmp/PBR/a_ntab_referee2.py").read().split("CONF = [")[0]
exec(src)

def sim_fixed(Nfn, r0, K, T, b0=100):
    tot, a = 0.0, 0
    for t in range(1, T+1):
        if (t < b0) or ((t-b0) % K == 0):
            tot += r0 + Nfn(t,0); a = 1
        else:
            tot += Nfn(t,a); a += 1
    return tot

def sim_dp(Nfn, r0, T, b0=100, AMAX=60):
    INF=float("inf")
    V=[[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a]=0.0
    for t in range(T,0,-1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t,0) + V[t+1][1]
            if t>b0 and a+1<=AMAX:
                v = Nfn(t,a) + V[t+1][a+1]
                if v < best: best = v
            V[t][a] = best
    return V[1][0]

tab = v3_table("l20","l20",[1,2,3,4,5],[1,2,3,5,8])
N = mk_nearest(tab)
T=344; r_eff=90.78*2.99
orc = sim_dp(N, r_eff, T)
bc, bk = min(((sim_fixed(N, r_eff, k, T), k) for k in [1,2,3,5,8]))
got = 100.0*(bc/orc - 1)
print("  我的重建表（旧 K 扫描 + 最近邻）:")
print("    固定周期最优 K*=%d  cost=%.0f  oracle=%.0f  ⇒ %.2f%%   (v3 报告 17.62%%)" % (bk, bc, orc, got))
print("    %s" % ("✓ 复算一致 ⇒ 重建忠实，可用于裁决" if abs(got-17.62) < 0.5
                 else "★ 不一致（差 %.2f pp）⇒ 我的重建不可用" % (got-17.62)))
