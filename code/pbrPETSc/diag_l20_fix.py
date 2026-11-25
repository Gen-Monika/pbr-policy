#!/usr/bin/env python3
"""
★★★ 诊断 4（修正版）：l20 的真根因 + 滞回修复

═══ 已定位的真根因（两个，都是实现层面，不是判据本身的错）═══

【根因 1】avg 的统计窗口不干净
    `avg = acc/accn` 是"本周期已累计成本 / 本周期已过步数"。
    但 acc 在**预热期结束后**仍然带着预热期那一大步的成本残留
    （重建周期跨过 t=100 边界时，acc 里还挂着 t<100 时的一次重建成本）。
    ⇒ 观测：稳态下 avg 在 59–105 之间抖动，而真实稳态均值只有 42.7。
       avg 被高估 → 判据倾向"重建"。

【根因 2】判据的两边口径不匹配
    est ≈ lvl + ΔN(a)  ← 已经是【每步】单位
    avg                ← 是【每步】单位（正确）
    但阈值 r 出现在错误的位置：判据应比较
        ΔN_step(a)  vs  r/s        （每步增量 vs 每步分摊的构造费）
    实测 l20 的 est 在 age=1 时为 31，age=2 时为 97（同一量级说明 est 用的
    是每步 ΔN），而 avg 稳态应为 r/s + N̄ = 30.3 + 12.4 = 42.7。
    ⇒ 正确阈值是 42.7，而不是被污染的 60–105。

═══════════ 修复方案 ═══════════
    (a) acc 在预热期结束时【清零重算】（消除根因 1）
    (b) 判据改成 `est > avg * (1+h)`，h 为滞回裕度（消除抖动）
    (c) 加 age 上限 A_max 作保护
    (d) ★ 阈值不再用 avg，直接用已知的 r/s：判据 `ΔN(a) > (r/s)*(1+h)`
        —— 这是最干净的版本（我们本来就测得到 r）
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


def trace_marginal(Nfn, r0, T, s, b0=100, thresh_mode="rs", hyst=0.0, amax=99,
                   verbose=False):
    """
    thresh_mode:
      "rs"   → ΔN(a) 与 (r0/s)*(1+h) 比   ★ 推荐（干净、只需 r 可测）
      "avg"  → est 与 avg*(1+h) 比        （原实现，avg 在 b0 处清零）
    """
    know = defaultdict(list); levels = []
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    a_pre = 0
    for t in range(1, T+1):
        lvl = levels[-1] if levels else None
        est = None; thr = None
        if t < b0:
            rb = True
        elif a >= amax:
            rb = True
        else:
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
            if thresh_mode == "rs":
                thr = (r0/s)*(1.0+hyst)
            else:
                base = acc/accn if accn else 0.0
                thr = base*(1.0+hyst)
            rb = est > thr
        a_pre = a
        if verbose and t >= b0:
            print("     t=%-4d a=%-3d est=%-9s thr=%-9s %s"
                  % (t, a_pre, ("%.1f" % est) if est is not None else "-",
                     ("%.1f" % thr) if thr is not None else "-",
                     "REBUILD" if rb else "reuse"))
        if rb:
            nn = Nfn(t, 0); c = r0+nn; tot += c
            if t < b0:
                acc, accn = 0.0, 0          # ★ 预热期不计入统计窗口
            else:
                acc, accn = c, 1
            a = 1; levels.append(nn)
        else:
            nn = Nfn(t, a); tot += nn; acc += nn; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(nn-bm)
            a += 1
    return tot


def cost_fixed(Nfn, r0, K, T, b0=100):
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


CFG = [("l20", "l20", [1,2,3,4,5], [1,2,3,5,8], 3),
       ("l15", "l15", [1,2,3,4,5], [1,2,3,5,8], 3),
       ("fine", "finerun", [1,2,3], [1,2,3,5,8], 3)]

for tag, logdir, rounds, Ks, s in CFG:
    cfg = build(tag, logdir, rounds, Ks)
    Nfn, curve = mk(cfg["tab"])
    T, r0 = cfg["nsteps"], cfg["r"]
    ks = sorted(curve)
    base = curve[0]
    print("="*104)
    print("★★★ [%s]  T=%d  r=%.2f  s=%d  r/s=%.2f  N(t,0)中位=%.0f"
          % (tag, T, r0, s, r0/s, base))
    print("="*104)
    print("  ΔN(age) 曲线（每步单位）:")
    for a in ks:
        print("     age=%-3d ΔN=%7.1f   vs r/s=%.1f  → %s"
              % (a, curve[a]-base, r0/s,
                 "重建" if curve[a]-base > r0/s else "继续复用"))
    k1 = cost_fixed(Nfn, r0, 1, T)
    fx = {K: cost_fixed(Nfn, r0, K, T) for K in (1,2,3,5,8) if K in Ks or K == 1}
    Kbest = min(fx, key=fx.get)
    print("\n  参照: K=1=%.0f   K*= %d (%.0f)   K=5=%.0f"
          % (k1, Kbest, fx[Kbest], fx.get(5, float("nan"))))
    print("\n  %-10s %-10s %8s %12s %12s %10s" %
          ("模式", "hyst", "A_max", "总成本", "vs 最优K", "重建数"))
    for mode in ("rs", "avg"):
        for h in (0.0, 0.1, 0.2, 0.3):
            for am in (99, 4, 5):
                tot = trace_marginal(Nfn, r0, T, s, thresh_mode=mode,
                                     hyst=h, amax=am)
                print("  %-10s %-10.1f %8d %12.0f %11.2f%% %10s"
                      % (mode, h, am, tot, 100*(tot/fx[Kbest]-1), "-"))
        print()

print("="*104)
print("★★★ l20 修复版决策序列（thresh_mode=rs, hyst=0, A_max=5）")
print("="*104)
tag, logdir, rounds, Ks, s = "l20", "l20", [1,2,3,4,5], [1,2,3,5,8], 3
cfg = build(tag, logdir, rounds, Ks); Nfn, curve = mk(cfg["tab"])
T, r0 = cfg["nsteps"], cfg["r"]
trace_marginal(Nfn, r0, T, s, thresh_mode="rs", hyst=0.0, amax=5, verbose=True)
