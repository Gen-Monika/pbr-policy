#!/usr/bin/env python3
"""
★ 诊断：为什么在 fx（levels=10，r=173.4）上在线策略比最优 K* 差 10.90 pp？

已知（linear 口径，数据边界内）：
    fx:  r_eff=173.4  最优 K*=2 (2.14%)   在线 13.05%   K=1 57.26%
    其他配置（r 更高）在线都在 K* 之上 1.6–5.5 pp

假设：
  H1  最优 K* 很小（=2）⇒ 正确做法是"几乎每步都重建"，
      而在线的判据天然倾向"多复用"（重建要付 s·r）⇒ 系统性偏晚
  H2  在线的"学习"阶段（前若干周期）代价占比大，而 T=344 中预热占 100
  H3  fx 的劣化曲线在 age=1 就陡（ΔN(1) 大）⇒ 复用一步就明显变差

本脚本逐条检验。
"""
import sys, statistics as st
sys.path.insert(0, ".")
import pbrlib as P

tag, lg, rds, Ks = "fx", "fixed", [1,2,3,4,5], [1,2,3,5,8]
cfg = P.load_config(tag, lg, rds, Ks)
T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
env = P.Env(cfg["tab"], mode="real", interp="linear")
orc = P.sim_dp(env, r0, T, env.amax_for(T))

print("=" * 100)
print("fx 诊断：T=%d  r_eff=%.1f  amax_data=%d  oracle/步=%.1f"
      % (T, r0, env.amax_data, orc/T))
print("=" * 100)

print("\n--- H3：劣化曲线的陡度 ---")
for a in sorted(env.curve)[:9]:
    print("   age=%d  全局曲线 N=%.1f   ΔN=%.1f   ΔN/r_eff=%.3f"
          % (a, env.curve[a], env.curve[a]-env.curve[0],
             (env.curve[a]-env.curve[0])/r0))
print("   ⇒ 若 age=1 的 ΔN/r_eff 已接近或超过 1，说明【复用一步就不划算】")

print("\n--- 固定周期的成本与重建数 ---")
cand = [K for K in (1,2,3,4,5,6,8) if K <= env.amax_data+1]
for K in cand:
    c = P.sim_fixed(env, r0, K, T)
    nrb = 100 + (T-100)//K
    print("   K=%-3d  %.0f (%.1f/步)  regret %6.2f%%  重建约 %d 次"
          % (K, c, c/T, 100*(c/orc-1), nrb))

print("\n--- H1/H2：在线策略的实际行为 ---")
# 重跑在线并记录轨迹
know = {}; levels = []
tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
trace = []
for t in range(1, T+1):
    if t < P.B0 or held < 0 or not levels:
        rebuild = True
    else:
        age = t - held
        avg = acc/accn if accn else tot/max(1, t-1)
        lvl = levels[-1]
        d = know.get(age)
        if d:
            delta = st.median(d)
        else:
            ks = sorted(k for k in know if know[k])
            if len(ks) >= 2:
                a2, a1 = ks[-1], ks[-2]
                d2, d1 = st.median(know[a2]), st.median(know[a1])
                delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
            elif ks:
                delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
        rebuild = (lvl + max(0.0, delta)) > avg
    if rebuild:
        N = env(t, 0); c = r0 + N; tot += c
        acc, accn = (0.0, 0) if t < P.B0 else (c, 1)
        levels.append(N); a = 1; held = t
    else:
        N = env(t, a); tot += N; acc += N; accn += 1
        bm = st.median(levels)
        if bm > 1e-9: know.setdefault(a, []).append(N - bm)
        a += 1
    trace.append((t, rebuild, a))
post = [x for x in trace if x[0] >= P.B0]
nrb = sum(1 for x in post if x[1])
ages = [x[2] for x in post if not x[1]]
print("   预热后重建 %d 次 / %d 步（等效 K≈%.2f）" % (nrb, len(post), len(post)/max(1,nrb)))
print("   复用时的年龄：中位 %.0f  最大 %d  分布 %s"
      % (st.median(ages) if ages else 0, max(ages) if ages else 0,
         dict(sorted({}.fromkeys(ages, 0).items())) if False else
         {a: ages.count(a) for a in sorted(set(ages))}))
print("   ⇒ 与最优 K*=2 对比：最优约需 %d 次重建，在线做了 %d 次"
      % (100 + (T-100)//2, nrb+100))
print("   ⇒ %s" % ("在线重建【过少】⇒ 判据偏晚（支持 H1）"
                   if nrb+100 < 100+(T-100)//2*1.3 else "重建次数接近，问题在别处"))

print("\n--- 在线的 regret 分解：学习期 vs 稳态 ---")
# 分段看成本差
env_c = lambda t, aa: env(t, aa)
c_onl = P.sim_online(env, r0, T)
c_k2 = P.sim_fixed(env, r0, 2, T)
print("   在线总成本 %.0f   固定 K=2 总成本 %.0f   差 %.0f"
      % (c_onl, c_k2, c_onl - c_k2))
# 前 N 个重建周期（学习期）的成本占比
first_cycle_end = None
seen = 0
for t, rb, a in post:
    if rb: seen += 1
    if seen == 3:
        first_cycle_end = t; break
if first_cycle_end:
    print("   预热后前 3 次重建结束于 t=%d（约占 %d%% 的步数）"
          % (first_cycle_end, 100*(first_cycle_end-P.B0)/len(post)))
print("\n   ⇒ 若学习期占步数比例大，则 H2 成立（T=344 且预热占 100 步，"
      "预热后只剩 244 步，学习窗口相对紧张）")
