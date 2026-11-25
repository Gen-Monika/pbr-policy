#!/usr/bin/env python3
"""
★★★ 在线策略判据的变体对比（2026-10-12，第二版）

═══ 第一版的错误（记录在案）═══
第一版里我写了「变体 A = 现行 C++ 判据」，但样本记录用了 levels[-1]，
而 pbrlib.sim_online 用的是 st.median(levels)。两者不等价：
  fx  : A(错版)=13.04%  vs  pbrlib=3.46%
  l15 : A(错版)=18.83%  vs  pbrlib=18.83%   ← 巧合相同
  fine: A(错版)=28.45%  vs  pbrlib=6.98%
⇒ 第一版的 A 列全部作废。
本版把「A 必须逐位等于 pbrlib.sim_online」写成硬断言，不通过就报错。

═══ 判据的三层 ═══
现行（C++ / pbrlib）: rebuild ⟺ (lvl + max(0,delta)) > avg
    lvl   = 最近一次重建观测到的 N(t,0)
    delta = median over { N(t',a) − median(levels) }   ← 注意减的是 levels 的中位
    avg   = 运行平均的每步总成本（含 r_eff）

边际最优判据: rebuild ⟺ N(t,a) − N(t,0) > r_eff
    即 ΔN > r_eff。这是"这一步重建值不值"的正确答案。
    在线只能估计 N(t,0)：用 lvl（可能过时）。

═══ 要回答 ═══
1. 现行判据在各配置上的 regret 是多少？（先确认口径）
2. 边际判据在同样的估算器下能好多少？
3. 如果 N(t,0) 的估计带漂移（lvl 用 trend 外推），能好多少？
4. l15 的周期 2 死循环在边际判据下是否消失？
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0


def load(parts):
    cells = defaultdict(list); rv = []; fac = []
    for prefix, logdir, Ks, rounds in parts:
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
                for i in range(n):
                    x = steps[i]; rf = int(x["reusedFrom"])
                    cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
                for x in rr:
                    if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                        rv.append(x["tPCSetup"]/x["tIter"])
                rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac),
                nsteps=max(t for t, a in cells))


MERGED = {
    "fx":   [("fx", "%s/fixed" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3])],
    "l15":  [("l15", "%s/l15" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("cov2_l15", "%s/cov2_l15" % P2, [13,20,30], [1,2,3])],
    "l20":  [("l20", "%s/l20" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3])],
    "fine": [("fine", "%s/finerun" % P2, [1,2,3,5,8], [1,2,3])],
    "x3":   [("x3", "%s/x3run" % P2, [1,2,3,5,8], [1,2])],
    "fl30": [("fl30", "%s/fl30run" % P2, [1,3,5], [1,2])],
    "sth":  [("sth", "%s/stefan" % P2, [1,2,3,5,8,13], [1,2,3])],
}


def run(env, r0, T, rule, theta=1.0, dmode="extrap", lvl_mode="last",
        sample="median_levels"):
    """
    rule     : "cpp"  现行 (lvl+delta) > avg
               "marg" 边际 ΔN > theta·r_eff
    dmode    : 未知年龄时 delta 的取值 —— extrap / flat / zero
    lvl_mode : N(t,0) 的估计 —— last（最近一次重建的值） / trend（线性外推）
    sample   : delta 样本的基准 —— median_levels（pbrlib 口径） / last_level
    """
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1; n_rb = 0
    for t in range(1, T+1):
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            lvl = levels[-1]
            if lvl_mode == "trend" and len(levels) >= 2:
                lvl = levels[-1] + (levels[-1] - levels[-2])
            # ---- delta 估计 ----
            if age in know and know[age]:
                d = st.median(know[age])
            else:
                ks = sorted(k for k in know if know[k])
                if not ks:
                    d = 0.0
                elif dmode == "zero":
                    d = 0.0
                elif dmode == "flat" or len(ks) < 2:
                    d = st.median(know[ks[-1]])
                else:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    d = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
            d = max(0.0, d)
            if rule == "cpp":
                avg = acc/accn if accn else tot/max(1, t-1)
                rebuild = (lvl + d) > avg
            else:
                rebuild = d > theta * r0
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < B0 else (c, 1)
            levels.append(N); a = 1; held = t; n_rb += 1
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels) if sample == "median_levels" else levels[-1]
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot, n_rb


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 138)
print("★★★ 在线判据变体对比（第二版；A 列强制等于 pbrlib.sim_online）")
print("=" * 138)

CFG = {}
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load(MERGED[tag])
    if cfg is None:
        print("  [%s] 数据缺失" % tag); continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="linear")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    orc = P.sim_dp(env, r0, T)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    CFG[tag] = (cfg, env, T, r0, orc, fx, kb, Ks)

# ---------- 断言：A 必须逐位等于 pbrlib.sim_online ----------
print("\n[前置自检] 变体 A 与 pbrlib.sim_online 必须逐位相等")
for tag, (cfg, env, T, r0, orc, fx, kb, Ks) in CFG.items():
    a_mine, _ = run(env, r0, T, rule="cpp", dmode="extrap", lvl_mode="last",
                    sample="median_levels")
    a_ref = P.sim_online(env, r0, T)
    d = abs(a_mine - a_ref)
    flag = "OK" if d < 1e-9 else "★★ 不一致"
    print("  %-6s mine=%.4f  pbrlib=%.4f  差=%.2e  %s" % (tag, a_mine, a_ref, d, flag))
    assert d < 1e-9, "变体 A 口径错误"

# ---------- 主对比 ----------
VARIANTS = [
    ("A 现行(cpp/avg)",     dict(rule="cpp",  dmode="extrap", lvl_mode="last")),
    ("B 边际 ΔN>r_eff",      dict(rule="marg", dmode="extrap", lvl_mode="last")),
    ("C 边际 未知记0",       dict(rule="marg", dmode="zero",   lvl_mode="last")),
    ("D 边际 未知取平",       dict(rule="marg", dmode="flat",   lvl_mode="last")),
    ("E 边际 + lvl trend",   dict(rule="marg", dmode="extrap", lvl_mode="trend")),
    ("F 现行 + lvl trend",   dict(rule="cpp",  dmode="extrap", lvl_mode="trend")),
]

print("\n" + "=" * 138)
print("★★★ 各变体的 regret（vs oracle）；括号内 = 重建次数")
print("=" * 138)
print("  %-6s %8s %6s %6s | %s" % ("配置", "r_eff", "K*", "T",
      " | ".join("%-21s" % n for n, _ in VARIANTS)))
print("  " + "-" * 134)
store = {}
for tag, (cfg, env, T, r0, orc, fx, kb, Ks) in CFG.items():
    cells = []
    store[tag] = {}
    for name, kw in VARIANTS:
        c, nrb = run(env, r0, T, **kw)
        reg = 100*(c/orc - 1)
        store[tag][name] = (reg, nrb)
        cells.append("%7.2f%%(%4d)" % (reg, nrb))
    print("  %-6s %8.1f %6d %6d | %s" % (tag, r0, kb, T, " | ".join(cells)))

print("  " + "-" * 134)
kk = [100*(CFG[t][5][CFG[t][6]]/CFG[t][4]-1) for t in CFG]
print("  %-6s %8s %6s %6s | %s" % ("K*→", "", "", "", " | ".join(
    "%7.2f%%      " % v for v in kk)))
print()
print("  %-24s %10s %10s %10s %10s" % ("变体", "中位", "最小", "最大", "优于K*的配置数"))
for name, _ in VARIANTS:
    v = [store[t][name][0] for t in CFG]
    win = sum(1 for t, k in zip(CFG, kk) if store[t][name][0] < k)
    print("  %-24s %9.2f%% %9.2f%% %9.2f%% %10d / %d"
          % (name, st.median(v), min(v), max(v), win, len(v)))
print("  %-24s %9.2f%% %9.2f%% %9.2f%%" % ("最优固定周期 K*", st.median(kk), min(kk), max(kk)))

# ---------- theta 扫描（边际判据）----------
print("\n" + "=" * 138)
print("★★★ 边际判据的 θ 扫描（ΔN > θ·r_eff）")
print("=" * 138)
TH = (0.2, 0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0)
print("  %-6s %6s" % ("配置", "K*") + "".join("%10s" % ("θ=%.2f" % t) for t in TH))
best = {}
for tag, (cfg, env, T, r0, orc, fx, kb, Ks) in CFG.items():
    kk1 = 100*(fx[kb]/orc-1)
    line = "  %-6s %5.2f%%" % (tag, kk1)
    row = []
    for th in TH:
        c, nrb = run(env, r0, T, rule="marg", theta=th, dmode="extrap", lvl_mode="last")
        r = 100*(c/orc-1); row.append((r, th, nrb))
        line += "%9.2f%%" % r
    best[tag] = min(row, key=lambda z: z[0])
    print(line)
print()
print("  每个配置的最优 θ：")
for tag, (r, th, nrb) in best.items():
    kk1 = 100*(CFG[tag][5][CFG[tag][6]]/CFG[tag][4]-1)
    print("    %-6s θ*=%.2f → %7.2f%%  (K*=%5.2f%%, 差 %+6.2f pp, 重建 %d 次)"
          % (tag, th, r, kk1, r-kk1, nrb))
print("=" * 138)
