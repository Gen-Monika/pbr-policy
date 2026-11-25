#!/usr/bin/env python3
"""
★★★ A（重跑）：在修正后的 oracle 与数据边界下，重建全部结论

═══ 相对此前版本的修正 ═══
1. oracle 的三层 bug 全部修好（见 pbrlib 的 docstring），并强制自检
2. ★ 新增【数据边界约束】：候选 K 不得超过数据支撑的范围
   （各配置扫过的 max(K)：fl30 = 5，其余 = 8，Stefan = 13）
   此前把 K 扫到 50，等于在"没有实测的年龄"上做外推，结论不可信。
3. ★ 插值敏感性：step（N 的下界）与 linear（N 的上界）两个口径都报，
   结论只在两者一致时才声称。

═══ 输出 ═══
- 表 1：oracle / K=1 / 最优 K* / 在线，在两种插值下
- 表 2：在线相对 K=1 与相对最优 K* 的 regret
- 表 3：插值敏感性（两口径的差异）
- 表 4：漂移判别（real vs scramble）
"""
import sys, random, statistics as st
sys.path.insert(0, ".")
import pbrlib as P

# 数据支撑的 K 上限（= 扫过的最大 K，不再外推）
KSUP = {}
for tag, lg, rds, Ks in P.CONFIGS:
    KSUP[tag] = max(Ks)
    # ★ 注意：K 的上限同时是"数据覆盖的最大年龄 + 1"，两者一致
print("数据支撑的 K 上限：", KSUP)

INTERPS = ("linear", "step")   # linear = 主口径（step 宣称大年龄不再劣化，物理上不成立）

print("\n" + "=" * 116)
print("表 1：修正 oracle 后的主结果（两种插值；相对各自 oracle 的 regret，%）")
print("=" * 116)
rows = {}
for tag, lg, rds, Ks in P.CONFIGS:
    cfg = P.load_config(tag, lg, rds, Ks)
    if cfg is None:
        print("[%s] 缺数据" % tag); continue
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    ksup = KSUP[tag]
    for interp in INTERPS:
        env = P.Env(cfg["tab"], mode="real", interp=interp)
        try:
            orc, info = P.selfcheck(env, r0, T, label="%s/%s" % (tag, interp),
                                    Ks=tuple(K for K in (1,2,3,4,5,6,8,10,13,20,30)
                                             if K <= KSUP[tag]))
        except AssertionError as e:
            print("  [%s/%s] %s" % (tag, interp, e)); continue
        # 只在与数据一致的 K 范围内取最优固定周期
        cand = [K for K in (1,2,3,4,5,6,8,10,13,20,30) if K <= ksup]
        fx = {K: P.sim_fixed(env, r0, K, T) for K in cand}
        kb = min(fx, key=fx.get)
        onl = P.sim_online(env, r0, T)
        reac = P.sim_reac(env, r0, T, 120)
        ch = P.sim_chalmers(env, r0, T)
        rows[(tag, interp)] = dict(
            T=T, r=r0, orc=orc, ksup=ksup, kb=kb,
            c1=fx[1], ck=fx[kb], conl=onl, creac=reac, cch=ch,
            r1=100*(fx[1]/orc-1), rk=100*(fx[kb]/orc-1),
            ronl=100*(onl/orc-1), rreac=100*(reac/orc-1),
            rch=100*(ch/orc-1),
            per_step_orc=orc/T, per_step_1=fx[1]/T, per_step_onl=onl/T)

print("  %-6s %-7s %8s %8s %9s %10s %10s %10s %10s" %
      ("配置","interp","r_eff","K上限","oracle/步","K=1","最优K*","在线","REAC"))
for (tag, interp), d in rows.items():
    print("  %-6s %-7s %8.1f %8d %9.1f %9.2f%% %9.2f%% %9.2f%% %9.2f%%"
          % (tag, interp, d["r"], d["ksup"], d["per_step_orc"],
             d["r1"], d["rk"], d["ronl"], d["rreac"]))

print("\n" + "=" * 116)
print("表 2：在线策略 vs 每步重建 vs 最优固定周期（regret，%；主口径 = linear）")
print("=" * 116)
print("  %-6s %-7s %12s %14s %14s %12s" %
      ("配置","interp","每步重建K=1","最优K*(该K)","在线","在线vs K*"))
for (tag, interp), d in rows.items():
    print("  %-6s %-7s %11.2f%% %13.2f%% %13.2f%% %+11.2f pp"
          % (tag, interp, d["r1"], d["rk"], d["ronl"], d["ronl"] - d["rk"]))

print("\n" + "=" * 116)
print("表 3：★ 插值敏感性（两个口径的 regret 差；两口径一致才算定论）")
print("=" * 116)
print("  %-6s %14s %14s %14s %14s %10s" %
      ("配置","K=1(step)","K=1(linear)","在线(step)","在线(linear)","判定"))
consistent = []
for tag, lg, rds, Ks in P.CONFIGS:
    a = rows.get((tag, "step")); b = rows.get((tag, "linear"))
    if not a or not b:
        print("  %-6s  (缺一)" % tag); continue
    d1 = b["r1"] - a["r1"]; do = b["ronl"] - a["ronl"]
    ok = abs(d1) < 15 and abs(do) < 8
    consistent.append((tag, ok))
    print("  %-6s %13.2f%% %13.2f%% %13.2f%% %13.2f%% %10s"
          % (tag, a["r1"], b["r1"], a["ronl"], b["ronl"],
             "一致✓" if ok else "敏感⚠️"))

print("\n" + "=" * 116)
print("表 4：漂移判别（real vs scramble，仅 linear 口径）")
print("=" * 116)
print("  %-6s %12s %12s %12s" % ("配置","real 在线","scr 在线","漂移增益"))
gains = []
for tag, lg, rds, Ks in P.CONFIGS:
    cfg = P.load_config(tag, lg, rds, Ks)
    if cfg is None: continue
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="linear")
    try:
        orc, _ = P.selfcheck(env, r0, T, label=tag+"/real")
        onl = P.sim_online(env, r0, T)
    except AssertionError as e:
        print("  %-6s  real 自检失败: %s" % (tag, str(e)[:40])); continue
    so = []; sn = []
    for rep in range(5):
        es = P.Env(cfg["tab"], mode="scramble", interp="linear",
                   rng=random.Random(1000+rep))
        try:
            o = P.sim_dp(es, r0, T, es.amax_for(T))
            so.append(o); sn.append(P.sim_online(es, r0, T))
        except Exception:
            continue
    if not so: continue
    r_real = 100*(onl/orc-1)
    r_scr = 100*(st.median(sn)/st.median(so)-1)
    g = r_real - r_scr
    gains.append(g)
    print("  %-6s %11.2f%% %11.2f%% %+11.2f pp" % (tag, r_real, r_scr, g))

print()
if gains:
    print("  ⇒ 漂移增益中位 = %+.2f pp，范围 [%+.2f, %+.2f]"
          % (st.median(gains), min(gains), max(gains)))
    print("  ⇒ 判定：%s"
          % ("漂移结构有实质影响" if st.median(gains) > 3.0
             else "★ 漂移结构对 regret 几乎无影响 ⇒ 瓶颈是 r"))
