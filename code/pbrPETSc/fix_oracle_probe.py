#!/usr/bin/env python3
"""
★ 诊断 sim_dp 的 oracle 为何低于物理下界

假设：环境函数 Nfn(t,a) 在表里没有 (t,a) 时，回退到"最近的年龄"。
      当 a 超出该 t 实际访问过的最大年龄时，最近年龄可能是一个【很小的】年龄，
      于是 DP 以为"复用 60 步"只花 age≈7 的迭代数 ⇒ 扫遍大年龄 ⇒ 成本低于下界。

本脚本先证实这个假设，再给出修复后的 oracle。

═══ 修复原则 ═══
年龄超出表覆盖范围时，唯一物理上正确的做法是【外推增长】，绝不是回退到小年龄。
"""
import os, re, statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur)); cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def build(tag, logdir, rounds, Ks):
    cells = defaultdict(list); rv = []; fac = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c); seen = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                    seen[int(d["timeIndex"])] = d
            rr = [seen[t] for t in sorted(seen)]
            Ns = per_step_N(l); n = min(len(rr), len(Ns))
            if ns is None or n > ns: ns = n
            for i in range(n):
                d = rr[i]; t = i + 1
                rf = int(d["reusedFrom"])
                cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
            allr = rows(c)
            for d in allr:
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
            rbs = set(int(d["timeIndex"]) for d in allr if int(d["reused"]) == 0)
            nrs = sum(1 for d in allr if int(d["reused"]) == 0)
            if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


def make_env(tab, extrap="linear"):
    """返回 (Nfn, 该表覆盖的最大年龄, 各 t 的可用年龄集合)"""
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}

    # 全局曲线（用于 t 无数据时的兜底）
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    maxage = max(curve)

    # 全局斜率（每增加一岁，N 增加多少），用曲线末端两点估计
    ks = sorted(curve)
    if len(ks) >= 2:
        a2, a1 = ks[-1], ks[-2]
        gslope = (curve[a2] - curve[a1])/max(1e-9, a2 - a1)
    else:
        gslope = 1.0
    gslope = max(1e-6, gslope)

    def Nfn(t, a):
        row = byt.get(t)
        if row is None:
            # 该步无数据：用全局曲线，超范围则外推
            if a in curve: return curve[a]
            return curve[maxage] + gslope*(a - maxage)
        if a in row: return row[a]
        ages = sa[t]
        if a > ages[-1]:
            # ★ 关键修复：超出该步覆盖范围 ⇒ 线性外推增长
            if len(ages) >= 2:
                a2, a1 = ages[-1], ages[-2]
                sl = (row[a2] - row[a1])/max(1e-9, a2 - a1)
            else:
                sl = gslope
            return row[ages[-1]] + max(sl, gslope)*(a - ages[-1])
        # 在覆盖范围内：取不超过 a 的最大可用年龄（保守，不偷用小年龄）
        lo = [x for x in ages if x <= a]
        return row[lo[-1]] if lo else row[ages[0]]
    return Nfn, maxage, sa, curve


def sim_dp(Nfn, r0, T, b0=100, AMAX=60):
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if t > b0 and a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][1], V


def sim_fixed(Nfn, r0, K, T, b0=100):
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


CFG = [("l20", "l20", [1,2,3,4,5], [1,2,3,5,8]),
       ("fl30", "fl30run", [1,2], [1,3,5])]

for tag, logdir, rounds, Ks in CFG:
    cfg = build(tag, logdir, rounds, Ks)
    tab = cfg["tab"]; T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    Nfn, maxage, sa, curve = make_env(tab)
    print("=" * 100)
    print("[%s] T=%d  r_eff=%.1f  表覆盖的最大年龄 = %d" % (tag, T, r0, maxage))
    print("=" * 100)

    # ---- 诊断 1：大年龄处 Nfn 是多少？----
    for t in (150, 200, 300):
        if t > T: continue
        ages_avail = sa.get(t, [])
        vals = [round(Nfn(t, a), 1) for a in (0, 1, 3, 5, 8, 13, 20, 40, 60)]
        print("  t=%-4d 可用年龄=%-28s" % (t, str(ages_avail[:12]) + ("..." if len(ages_avail) > 12 else "")))
        print("        Nfn(a=0,1,3,5,8,13,20,40,60) = %s" % vals)

    # ---- 诊断 2：DP 走过的路径 ----
    orc, V = sim_dp(Nfn, r0, T, AMAX=60)
    print("\n  ★ 修复后 oracle = %.0f  (%.2f/步)" % (orc, orc/T))
    # 回溯路径
    path = []
    a = 1
    for t in range(1, T+1):
        if t < 100:
            path.append((t, "R", 1)); a = 1; continue
        rebuild = r0 + Nfn(t, 0) + V[t+1][1]
        act = "R"
        if a+1 <= 60 and Nfn(t, a) + V[t+1][a+1] <= rebuild:
            act = "r"
        if act == "R": a = 1
        else: a = a+1
        path.append((t, act, a))
    nrb = sum(1 for _, act, _ in path if act == "R")
    ages = [a for _, act, a in path if act == "r"]
    print("     预热后重建 %d 次，复用 %d 次；复用时的年龄 最大=%d 中位=%.0f"
          % (nrb - 100, len(ages), max(ages) if ages else 0,
             st.median(ages) if ages else 0))

    # ---- 诊断 3：固定周期对照 ----
    print("\n  %-6s %12s %12s" % ("K", "成本", "每步"))
    c1 = sim_fixed(Nfn, r0, 1, T)
    for K in (1, 2, 3, 4, 5, 8, 13):
        v = sim_fixed(Nfn, r0, K, T)
        print("  %-6d %12.0f %12.2f %s" % (K, v, v/T,
              "← 最优" if v == min(sim_fixed(Nfn, r0, k, T) for k in (1,2,3,4,5,8,13)) else ""))

    # ---- 一致性自检 ----
    kbest = min((sim_fixed(Nfn, r0, k, T), k) for k in (1,2,3,4,5,8,13))
    print("\n  ★ 自检：oracle(%.0f) ≤ 最优固定周期 K=%d(%.0f) ？ %s"
          % (orc, kbest[1], kbest[0], "✓" if orc <= kbest[0] + 1e-6 else "✗ 违反"))
    print("  ★ 自检：oracle ≥ 每步至少付 N(t,该步实际年龄)？ ",
          "下界 %.0f，oracle %.0f ⇒ %s"
          % (sum(min(Nfn(t,0), Nfn(t,60)) for t in range(1,T+1)), orc,
             "✓" if orc >= sum(min(Nfn(t,0), Nfn(t,60)) for t in range(1,T+1)) - 1e-6 else "✗"))
