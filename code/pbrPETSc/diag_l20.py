#!/usr/bin/env python3
"""
★ l20 诊断：为什么在留出验证下，在线策略仍然劣于固定周期？

事实（A1b 留出）：
    l20:  r=90.78   固定周期 K*=3 → 15.61%    在线(P5/40) → 17.05%   ceiling → 3.46%
    而   fine: r=114.72 相同 s=3, 相同 nsteps 曲线 ⇒ 在线 11.33% 优于固定 20.10%
    ⇒ 不是 r 单调造成的，l20 是特例。

三个假设：
    H1 策略的 age 分布与 K*=3 差别大（重建过少或过多）
    H2 策略在"边际判据说该重建"时没有重建（判据本身错）
    H3 策略学到了错误的 ΔN（数据噪声）

本脚本逐条检验。
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
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25: continue
        try:
            d = dict(zip(CSV_HDR, p))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def build(tag, rounds, Ks, logdir):
    cells = defaultdict(list); rv = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))   # ★ 别忘了目录前缀
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c)
            # ★ rep>=0 的行是"快照元数据行"（带 timeIndex/reusedFrom，但 tIter=-1）；
            #   rep=-1 的行才是"真实计时行"。取代表行只用于判定 age。
            seen = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                    seen[int(d["timeIndex"])] = d
            rr = [seen[t] for t in sorted(seen)]
            Ns = per_step_N(l)
            n = min(len(rr), len(Ns))
            if ns is None or n > ns: ns = n
            for i in range(n):
                d = rr[i]; t = i + 1
                rf = int(d["reusedFrom"])
                cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
            # ★ r 用"真实计时行"（rep=-1）算，与 online_cross.py 口径一致
            for d in rows(c):
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=st.median(rv), nsteps=ns,
                raw={(R, K): None for K in Ks for R in rounds})


def mk(tab):
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}
    def N(t, a):
        row = byt.get(t)
        if row is not None:
            if a in row: return row[a]
            return row[min(sa[t], key=lambda x: abs(x-a))]
        return curve.get(a, curve[amx])
    return N, curve


def trace(Nfn, r0, T, target_age, force_every, lvl_mode):
    """返回 policy 的逐步 (t, 是否重建, age)。与 sim_online 相同逻辑。"""
    know = defaultdict(list); levels = []
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    in_probe = 0; since = 10**9
    tl = []
    for t in range(1, T+1):
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        else:
            lvl = (levels[-1] + (levels[-1]-levels[-2])
                   if len(levels) >= 2 else (levels[-1] if levels else None))
        if t < 100: rb = True
        elif in_probe > 0: rb = False
        elif a == 0: rb = True
        else:
            avg = acc/accn if accn else tot/(t-1)
            if lvl is None: est = 0.5*r0*a
            else:
                if a in know and know[a]: delta = st.median(know[a])
                elif know:
                    ks = sorted(k for k in know if know[k])
                    if len(ks) >= 2:
                        a2, a1 = ks[-1], ks[-2]
                        d2, d1 = st.median(know[a2]), st.median(know[a1])
                        delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(a-a2)
                    else: delta = st.median(know[ks[-1]])
                else: delta = 0.0
                est = lvl + max(0.0, delta)
            rb = est > avg
        if rb:
            nn = Nfn(t, 0); tot += r0+nn; acc, accn = r0+nn, 1; a = 1
            levels.append(nn); since += 1
            if target_age > 0:
                lm = max([k for k in know if know[k]], default=0)
                if lm < target_age and since >= force_every:
                    in_probe = target_age-lm; since = 0
        else:
            nn = Nfn(t, a); tot += nn; acc += nn; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(nn-bm)
            a += 1
            if in_probe > 0: in_probe -= 1
            since += 1
        tl.append((t, rb, a))
    return tot, tl


def trace_fixed(K, T):
    tl = []; a = 0
    for t in range(1, T+1):
        if t < 100 or (t-100) % K == 0: a = 1; tl.append((t, True, a))
        else: a += 1; tl.append((t, False, a))
    return tl


def agestats(tl, T):
    ages = [a for _, rb, a in tl if not rb]
    return dict(nrb=sum(1 for _, rb, _ in tl if rb),
                K=sum(1 for _, rb, _ in tl if rb)/T,
                mean=st.mean(ages) if ages else 0,
                med=st.median(ages) if ages else 0,
                mx=max(ages) if ages else 0)


Ks = [1, 2, 3, 5, 8]
print("="*100)
print("★★★ 诊断 1：l20 与 l15/fine 的 ΔN_step 曲线形状对比")
print("="*100)
for tag, R in (("l20", [1,2,3,4,5]), ("l15", [1,2,3,4,5]), ("fine", [1,2,3])):
    cfg = build(tag, R, Ks, tag)
    Nfn, curve = mk(cfg["tab"])
    T, r0 = cfg["nsteps"], cfg["r"]
    base = curve[0]
    print("\n[%s]  T=%d  r=%.2f  N(t,0)中位=%.0f" % (tag, T, r0, base))
    print("   %-4s %10s %12s %12s %10s" % ("age", "Nmedian", "dN_step", "dN/thr", "rebuild?"))
    for a in sorted(curve):
        d = curve[a]-base
        print("   %-4d %10.1f %12.1f %12.3f %10s"
              % (a, curve[a], d, d/r0, "YES" if d > r0 else ""))
    # 用 K* 的实际 age 分布算加权 ΔN_step
    for K in (2, 3, 5, 8):
        tl = trace_fixed(K, T)
        num = sum(curve.get(a, curve[max(curve)]) - base for _, rb, a in tl if not rb)
        print("   K=%d: 实际加权 ΔN_step = %+.2f  (阈值 r=%.1f  ⇒ %s)"
              % (K, num, r0, "复用划算" if num < r0 else "重建划算"))

print("\n" + "="*100)
print("★★★ 诊断 2：在线策略的实际重建序列 vs 固定 K=3")
print("="*100)
cfg = build("l20", [1,2,3,4,5], Ks, "l20")
Nfn, curve = mk(cfg["tab"])
T, r0 = cfg["nsteps"], cfg["r"]
tot_onl, tl_onl = trace(Nfn, r0, T, 5, 40, "last")
print("  在线(P5/40) 总成本 = %.1f" % tot_onl)
def cfix(K):
    return sum((r0 + Nfn(t, 0)) if (t < 100 or (t-100) % K == 0)
               else Nfn(t, int([a for tt, rb, a in trace_fixed(K, T)][t-1]))
               for t in range(1, T+1))
print("  固定 K=3   总成本 = %.1f" % cfix(3))
s1, s3 = agestats(tl_onl, T), agestats(trace_fixed(3, T), T)
print("\n  %-14s %8s %8s %8s %8s %8s" % ("策略", "重建次数", "等效K", "age均值", "age中位", "age最大"))
for nm, s in (("在线 P5/40", s1), ("固定 K=3", s3)):
    print("  %-14s %8d %8.2f %8.2f %8.1f %8d"
          % (nm, s["nrb"], s["K"], s["mean"], s["med"], s["mx"]))

print("\n★★★ 诊断 3：边际判据在真实序列上是对还是太贪婪？")
print("   做法：拿固定 K=3 的序列，逐点问：若这里不重建、推迟一步，成本变好还是变坏")
tl3 = trace_fixed(3, T)
bad = 0; checked = 0
for i in range(100, T-1):
    t, rb, a = tl3[i]
    if not rb: continue
    pt, prb, pa = tl3[i-1]
    if prb: continue
    checked += 1
    # 真实选择：重建于 t
    real = r0 + Nfn(t, 0)
    # 反事实：跳过 t 的重建，在 t 复用(age=a)，成本推迟到下一次必然
    alt = Nfn(t, a)
    if alt < real: bad += 1
print("  在 K=3 的 %d 个重建点里，有 %d 个（%.1f%%）本可以再复用一步更便宜"
      % (checked, bad, 100.0*bad/max(1, checked)))
print("  ⇒ 这衡量的是固定 K=3 是否已经过保守")
