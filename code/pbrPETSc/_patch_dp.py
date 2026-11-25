#!/usr/bin/env python3
"""
修正 sim_dp 的两个口径问题，使 oracle 与其余策略【严格可比】。

统一约定（与 sim_fixed / sim_online / sim_ceiling 一致）：
  - 第 t 步开始时的 age 记为 a；重建后 age 变为 1，复用一步后 age 变为 a+1
  - 预热期 t <= b0 一律强制重建（所有策略同一口径）
  - 第 1 步必然重建 ⇒ DP 的入口状态是 a=1（不是 a=0）

原 bug：返回 V[1][0]，那是"第 1 步尚未重建"的状态，
       与其余策略"第 1 步强制重建"的初始条件不同 ⇒ 不可比。

同时加入【自检】：oracle 必须 <= 任何固定周期，否则报错。
"""
p = "online_cross.py"
s = open(p).read()

old = '''def sim_dp(Nfn, r0, T, b0=100, AMAX=40):
    """真 oracle：动态规划（不可实现，作 regret 基准）。"""
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            if t < b0:
                V[t][a] = r0 + Nfn(t, 0) + V[t+1][1]
                continue
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][0], V'''

new = '''def sim_dp(Nfn, r0, T, b0=100, AMAX=60):
    """真 oracle：动态规划（不可实现，作 regret 基准）。

    ★ 口径（与 sim_fixed/sim_online/sim_ceiling 严格一致）：
        - 第 t 步开始时 age = a
        - 重建：付 r0 + N(t,0)，age -> 1
        - 复用：付 N(t,a)，age -> a+1
        - 预热期 t <= b0 强制重建
      入口状态为 a=1（因为第 1 步必然重建）。
    """
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1):
        V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            # 重建
            best = r0 + Nfn(t, 0) + V[t+1][1]
            # 复用（预热期与超龄时禁止）
            if t > b0 and a + 1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][1], V'''
assert old in s, "sim_dp 未找到"
s = s.replace(old, new)

# 加自检：oracle 必须 <= 所有固定周期
old_call = '''    cv = sim_ceiling(Nfn, r0, T, b0)'''
new_call = '''    cv = sim_ceiling(Nfn, r0, T, b0)
    # ★ 自检：oracle 必须是下界（cost 最小），任何可行策略都不该低于它
    viol = [(K, v) for K, v in fixed.items() if v < oracle - 1e-6]
    print("  自检: oracle=%.1f；固定周期最小值=%.1f；违反下界的档位=%s"
          % (oracle, min(fixed.values()),
             ("无 ✓" if not viol else str([(k, round(v,1)) for k,v in viol]))))'''
assert old_call in s, "调用处未找到"
s = s.replace(old_call, new_call)

open(p, "w").write(s)
print("OK: sim_dp 口径已修正 + 加入下界自检")
