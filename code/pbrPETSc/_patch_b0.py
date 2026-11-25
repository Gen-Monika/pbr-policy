#!/usr/bin/env python3
"""修正 online_cross.py 的 b0（预热期）问题。"""
p = "online_cross.py"
s = open(p).read()

# 1) 各 sim_* 的 b0 默认改为 100（与原版 greedy_v6 一致）
s = s.replace("def sim_fixed(Nfn, r0, K, T, b0=1):",
              "def sim_fixed(Nfn, r0, K, T, b0=100):")
s = s.replace("def sim_ceiling(Nfn, r0, T, b0=1, amax=10**9):",
              "def sim_ceiling(Nfn, r0, T, b0=100, amax=10**9):")
s = s.replace("def sim_online(Nfn, r0, T, b0=1, target_age=0, force_every=0,",
              "def sim_online(Nfn, r0, T, b0=100, target_age=0, force_every=0,")
s = s.replace("def sim_dp(Nfn, r0, T, b0=1, AMAX=40):",
              "def sim_dp(Nfn, r0, T, b0=100, AMAX=40):")

# 2) 调用处传自适应 b0
old_call = """    base = sim_fixed(Nfn, r0, 1, T)
    oracle, _ = sim_dp(Nfn, r0, T)
    fixed = {K: sim_fixed(Nfn, r0, K, T) for K in Ks}
    bestK = min(fixed, key=fixed.get)
    cv = sim_ceiling(Nfn, r0, T)"""
new_call = """    b0 = min(100, max(1, T // 4))
    print("  （预热期 b0=%d 步）" % b0)
    base = sim_fixed(Nfn, r0, 1, T, b0)
    oracle, _ = sim_dp(Nfn, r0, T, b0)
    fixed = {K: sim_fixed(Nfn, r0, K, T, b0) for K in Ks}
    bestK = min(fixed, key=fixed.get)
    cv = sim_ceiling(Nfn, r0, T, b0)"""
assert old_call in s, "调用处未找到"
s = s.replace(old_call, new_call)

s = s.replace("c0, _, lm0 = sim_online(Nfn, r0, T, target_age=0)",
              "c0, _, lm0 = sim_online(Nfn, r0, T, b0, target_age=0)")
s = s.replace("c, p, lm = sim_online(Nfn, r0, T, target_age=ta, force_every=fe)",
              "c, p, lm = sim_online(Nfn, r0, T, b0, target_age=ta, force_every=fe)")

# 3) sim_dp 的预热期：前 b0 步强制重建
old_dp = """    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best"""
new_dp = """    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            if t < b0:
                V[t][a] = r0 + Nfn(t, 0) + V[t+1][1]
                continue
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best"""
assert old_dp in s, "sim_dp 未找到"
s = s.replace(old_dp, new_dp)

open(p, "w").write(s)
print("OK: b0 已修正")
