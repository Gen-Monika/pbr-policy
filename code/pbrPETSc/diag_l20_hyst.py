#!/usr/bin/env python3
"""
★ 诊断 4：在线策略为什么比 K=3 多重建 45%？
   + 滞回阈值（hysteresis）能否修复？

核心问题：判据 `est > avg` 里
    avg = 本周期【已累计成本】/ 本周期【已过步数】
这是"周期平摊"口径，理论上正确。但实测在线得到 119 次重建
而 K=3 得到 82 次 —— 差异必须定位到具体机制。

本脚本：
  (1) 打印重建时的 age 直方图（在线 vs 固定K=3）
  (2) 逐点打印前 30 个决策（est / avg / 判定），人眼可核
  (3) 滞回测试：重建阈值 = avg * (1+h)，h ∈ {0,0.1,0.2,0.3,0.5}
      并加 age 上限 A_max 保护
"""
import os, re, statistics as st
from collections import defaultdict, Counter

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


def build(tag, logdir, rounds, Ks):
    cells = defaultdict(list); rv = []; ns = None
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
            for d in rows(c):
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=st.median(rv) if rv else float("nan"), nsteps=ns)


def mk(tab):
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}
    def N(t, a):
        row = byt.get(t)
        if row is not None:
            return row[a] if a in row else row[min(sa[t], key=lambda x: abs(x-a))]
        ks = sorted(curve)
        return curve[a] if a in curve else curve[ks[-1]]
    return N, curve


def trace_online(Nfn, r0, T, b0=100, target_age=5, force_every=40,
                 lvl_mode="last", hyst=0.0, amax=99, verbose=False):
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
        est = None; avg = None
        if t < b0:
            rb = True
        elif a >= amax:
            rb = True
        elif in_probe > 0:
            rb = False
        elif a == 0:
            rb = True
        else:
            avg = acc/accn if accn else tot/(t-1)
            if lvl is None:
                est = 0.5*r0*a
            else:
                if a in know and know[a]:
                    delta = st.median(know[a])
                elif know:
                    ks = sorted(k for k in know if know[k])
                    if len(ks) >= 2:
                        a2, a1 = ks[-1], ks[-2]
                        d2, d1 = st.median(know[a2]), st.median(know[a1])
                        delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(a-a2)
                    else:
                        delta = st.median(know[ks[-1]])
                else:
                    delta = 0.0
                est = lvl + max(0.0, delta)
            rb = est > avg*(1.0+hyst)
        a_pre = a
        if verbose and 100 <= t < 145:
            print("     t=%-4d a_pre=%-3d lvl=%-9s est=%-10s avg=%-10s  %s"
                  % (t, a_pre, ("%.1f" % lvl) if lvl is not None else "-",
                     ("%.1f" % est) if est is not None else "-",
                     ("%.1f" % avg) if avg is not None else "-",
                     "REBUILD" if rb else "reuse"))
        if rb:
            nn = Nfn(t, 0); c = r0+nn; tot += c; acc, accn = c, 1; a = 1
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
        tl.append((t, rb, a_pre, tot, est, avg))
    return tot, tl


def trace_fixed(Nfn, r0, K, T, b0=100):
    tl = []; a = 0; tot = 0.0
    for t in range(1, T+1):
        a_pre = a
        if t < b0 or (t-b0) % K == 0:
            c = r0 + Nfn(t, 0); a = 1; rb = True
        else:
            c = Nfn(t, a); a += 1; rb = False
        tot += c; tl.append((t, rb, a_pre, tot, None, None))
    return tot, tl


# ══════════════════════════════════════════════════════════════════
cfg = build("l20", "l20", [1,2,3,4,5], [1,2,3,5,8])
Nfn, curve = mk(cfg["tab"])
T, r0 = cfg["nsteps"], cfg["r"]
print("="*104)
print("★★★ 诊断 4a：l20 重建点 age 直方图    T=%d  r=%.2f" % (T, r0))
print("="*104)
_, tl_onl = trace_online(Nfn, r0, T, target_age=5, force_every=40)
_, tl_fix = trace_fixed(Nfn, r0, 3, T)
for nm, tl in (("在线 P5/40", tl_onl), ("固定 K=3", tl_fix)):
    c = Counter(a for t, rb, a, *_ in tl if rb and t >= 100)
    print("  %-10s 重建次数=%-4d  重建【前】age 分布: %s"
          % (nm, sum(c.values()), dict(sorted(c.items()))))

print("\n★★★ 诊断 4b：前 30 个决策逐点打印（在线 P5/40，t=100 起）")
trace_online(Nfn, r0, T, target_age=5, force_every=40, verbose=True)

print("\n" + "="*104)
print("★★★ 诊断 4c：滞回阈值 + age 上限 扫描（l20）")
print("="*104)
base3 = sum(c for _, _, _, c, _, _ in tl_fix)
_, tl1 = trace_fixed(Nfn, r0, 1, T)
cost1 = sum(c for _, _, _, c, _, _ in tl1)
print("  参照：K=1(全重建)=%.0f   K=3(最优)=%.0f   K=5=%.0f"
      % (cost1, base3, sum(c for _, _, _, c, _, _ in trace_fixed(Nfn, r0, 5, T)[1])))
print("\n  %-8s %-8s %10s %10s %10s" % ("h", "A_max", "总成本", "vs K=3", "重建数"))
for h in (0.0, 0.1, 0.2, 0.3, 0.5):
    for am in (99, 4, 5):
        tot, tl = trace_online(Nfn, r0, T, target_age=5, force_every=40,
                               hyst=h, amax=am)
        nrb = sum(1 for t, rb, *_ in tl if rb and t >= 100)
        print("  %-8.1f %-8d %10.0f %9.2f%% %10d"
              % (h, am, tot, 100*(tot/base3-1), nrb))
    print()
