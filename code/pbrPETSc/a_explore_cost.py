#!/usr/bin/env python3
"""
量化「在线标定」的探索代价（修正版）。

★ 修正说明：前一版的"先知 Δ"用了【全局中位增量】，而全局中位混进了
   序列早期的小增量，导致估计恒小于阈值 ⇒ 策略退化为"永不重建" ⇒
   代价爆炸 50 倍（l15: 1.33M vs 25k）。那是我的实现 bug，不是结论。

正确的"先知"应当是：**在该步就知道这一步的真实老化增量**
    Δ_t(a) = N(t, a) − N(t, 0)
即"免费获得完美的、随 t 更新的老化信念"，无任何探索成本。

对照三方：
  ① 在线（现状）       ：Δ 从运行中积累的样本估计
  ② 先知 Δ（完美局部） ：Δ 取 Δ_t(a)
  ③ 事后最优 K*        ：周期族内的最优
"""
import sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
KS = (1, 2, 3, 4, 5, 6)


def sim_online_perfect_delta(env, rho, T, B0):
    """与 sim_online_detail 同构，但 delta 直接取当前步的真实增量（完美局部信念）。"""
    it = 0.0; rb = 0; tot = 0.0
    acc = 0.0; accn = 0; levels = []; held = -1
    for t in range(1, T + 1):
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc / accn if accn else tot / max(1, t - 1)
            # ★ 完美局部信念：直接问"年龄 age 相对 age 0 涨多少"（在当前 t 上）
            delta = env(t, age) - env(t, 0)
            rebuild = (levels[-1] + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); it += N; rb += 1; tot += rho + N
            acc, accn = (0.0, 0) if t < B0 else (rho + N, 1)
            levels.append(N); held = t
        else:
            N = env(t, t - held); it += N; tot += N
            acc += N; accn += 1
    return tot, it, rb


print("=" * 126)
print("★ 在线标定的探索代价（在线 vs 完美局部信念）")
print("=" * 126)
print("  %-6s %-11s %-12s %-11s %-12s %s"
      % ("配置", "在线 cost", "先知Δ cost", "探索代价", "vs K* 差距", "探索/K*差距"))

exp_list = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    rho = d["r1"]
    c_learn, _, _, _, _ = sim_online_detail(env, rho, T, B0)
    c_perf, _, _ = sim_online_perfect_delta(env, rho, T, B0)
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k) for k in KS if k <= env.amax_data + 1))
    exp = 100.0 * (c_learn - c_perf) / c_perf
    gap = 100.0 * (c_learn - bc) / bc
    exp_list.append((tag, exp, gap))
    print("  %-6s %-11.0f %-12.0f %+10.2f%% %+11.2f%%   %.2f"
          % (tag, c_learn, c_perf, exp, gap, exp / gap if gap else float('nan')))

v = [e for _, e, _ in exp_list]
print("\n  ★ 探索代价: 范围 [%+.2f%%, %+.2f%%]，中位 %+.2f%%"
      % (min(v), max(v), st.median(v)))
print("  ★ 判读：")
print("     ≈0 或负 ⇒ 在线学习未支付额外代价，'在求解过程中完成标定'这一主张无保留")
print("     ≫0      ⇒ 标定是用一部分性能换来的，必须如实说明")
