#!/usr/bin/env python3
"""
★★★ l15 在线策略为何退化到周期 2（诊断）

现象：l15 的在线 regret = 18.83%（最差），而最优固定周期 K*=5 只有 2.18%，
      在线 − K* = +16.66 pp。
逐步追踪显示在线在 t≥102 后稳定地【隔一步重建一次】（周期 2），
重建时刻 102,104,106,...,128...

判据：rebuild = (lvl + max(0, delta)) > avg
  lvl   = 最近一次重建时观测到的 N（即"新鲜因子下的迭代数"）
  delta = 当前年龄下 N 相对 lvl 的增量估计
  avg   = 运行平均每步成本（建后再复用，含 r0 的那一步被算进来）

本脚本把每一步的三个量及其来源全部打印出来，看清到底是哪一项错了。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"


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
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac),
                nsteps=max(t for t, a in cells))


which = sys.argv[1] if len(sys.argv) > 1 else "l15"
SPEC = {
    "l15":  [("l15", "%s/l15" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("cov2_l15", "%s/cov2_l15" % P2, [13,20,30], [1,2,3])],
    "l20":  [("l20", "%s/l20" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3])],
    "fx":   [("fx", "%s/fixed" % P2, [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3])],
}[which]

cfg = load(SPEC)
env = P.Env(cfg["tab"], mode="real", interp="linear")
T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
B0 = P.B0

print("=" * 118)
print("★★★ [%s] 在线策略逐步诊断   T=%d  r_eff=%.1f  amax_data=%d" % (which, T, r0, env.amax_data))
print("=" * 118)
print("判据 rebuild ⟺ (lvl + max(0, delta)) > avg")
print()

know = defaultdict(list); levels = []
tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
print("  %-5s %-6s %6s | %8s %8s %8s %8s | %-10s %s"
      % ("t", "动作", "age", "N(t,a)", "lvl", "delta", "avg", "delta来源", "判据 左>右?"))
for t in range(1, T+1):
    src = ""; delta = 0.0; lvl = float("nan"); avg = float("nan"); age = -1
    if t < B0 or held < 0 or not levels:
        rebuild = True
    else:
        age = t - held
        avg = acc/accn if accn else tot/max(1, t-1)
        lvl = levels[-1]
        if age in know and know[age]:
            delta = st.median(know[age]); src = "know[%d](n=%d)" % (age, len(know[age]))
        elif know:
            ks = sorted(k for k in know if know[k])
            if len(ks) >= 2:
                a2, a1 = ks[-1], ks[-2]
                d2, d1 = st.median(know[a2]), st.median(know[a1])
                delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                src = "外推 %d,%d" % (a1, a2)
            else:
                delta = st.median(know[ks[-1]]); src = "know[%d](唯一)" % ks[-1]
        else:
            delta = 0.0; src = "空"
        rebuild = (lvl + max(0.0, delta)) > avg

    if rebuild:
        N = env(t, 0); c = r0 + N; tot += c
        acc, accn = (0.0, 0) if t < B0 else (c, 1)
        levels.append(N); a = 1; held = t
        act = "重建"
    else:
        N = env(t, a); tot += N; acc += N; accn += 1
        if levels:
            bm = st.median(levels)
            if bm > 1e-9: know[a].append(N - bm)
        a += 1
        act = "复用"

    if 98 <= t <= 135:
        mark = ""
        if act == "复用" or t < B0:
            mark = ""
        if not (t < B0) and held >= 0 and age >= 0:
            lhs = lvl + max(0.0, delta)
            mark = "%.1f > %.1f → %s" % (lhs, avg, "重建" if lhs > avg else "复用")
        print("  %-5d %-6s %6d | %8.1f %8.1f %8.1f %8.1f | %-10s %s"
              % (t, act, age, N, lvl, delta, avg, src, mark))

print()
rb = [t for t in range(B0+1, T+1) if False]
print("  median(levels) = %.1f   （levels 共 %d 个样本）" % (st.median(levels), len(levels)))
print("  know 表（年龄 → delta 的样本数与中位）:")
for k in sorted(know):
    if know[k]:
        print("    age=%-3d n=%-4d median=%8.1f  min=%8.1f max=%8.1f"
              % (k, len(know[k]), st.median(know[k]), min(know[k]), max(know[k])))
print()
print("  ★ 关键比值：r_eff = %.1f" % r0)
print("    判据改写：重建 ⟺ delta > avg − lvl")
print("    avg 在【刚重建后】≈ r_eff + N(t,0) = %.1f + %.1f = %.1f  ← 极大"
      % (r0, env(B0+1, 0) if env.byt.get(B0+1) else float('nan'), r0 + (env(B0+1, 0) if env.byt.get(B0+1) else 0)))
print("    ⇒ 紧接着重建的那一步，avg 被 r_eff 拉高到 ~%.0f" % (r0 + 16))
print("      而 lvl ≈ 16、delta ≈ 25 ⇒ 左边只有 ~41 ≪ 右边 ~249 ⇒ 必然选择复用")
print("    ⇒ 再下一步 avg 被拉低到 ~145，但左边仍未超过 ⇒ 出现【隔步重建】的周期 2")

# 逐项核对：如果 avg 不含 r_eff（只算迭代数），会怎样？
print()
print("=" * 118)
print("★★★ 反事实：把 avg 的口径从【含 r_eff 的每步总成本】改成【只算迭代数】")
print("=" * 118)


def sim_online_variant(env, r0, T, avg_mode="cost"):
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    n_rb = 0
    for t in range(1, T+1):
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            if avg_mode == "cost":
                acc, accn = (0.0, 0) if t < B0 else (c, 1)
            else:
                acc, accn = (0.0, 0) if t < B0 else (N, 1)
            levels.append(N); a = 1; held = t; n_rb += 1
        else:
            N = env(t, a); tot += N
            acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot, n_rb


orc = P.sim_dp(env, r0, T)
Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
kb = min(fx, key=fx.get)
print("  oracle=%.0f  K*=%d(%.2f%%)  K=1(%.2f%%)" % (orc, kb, 100*(fx[kb]/orc-1), 100*(fx[1]/orc-1)))
for mode in ("cost", "iter"):
    c, nrb = sim_online_variant(env, r0, T, mode)
    print("  avg 口径=%-5s  在线=%.0f  regret=%7.2f%%  重建 %d 次 (%.2f 次/步)"
          % (mode, c, 100*(c/orc-1), nrb, nrb/float(T)))
