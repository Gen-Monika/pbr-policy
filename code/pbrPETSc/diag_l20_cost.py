#!/usr/bin/env python3
"""
★ 关键诊断：在【同一条 l20 数据】上，对在线策略与固定周期做逐点成本对照。

已知矛盾（必须解释）：
    固定 K=3 总成本 低于 在线策略 —— 但全量重建(K=1)理应最贵。
    如果在线真的"判断错了"，错在哪里？

本脚本输出：
  1. 三条策略的 (重建次数, age 分布, 总成本)
  2. 逐步成本差 Δ(t) = cost_online(t) - cost_fixed3(t)，找出亏损集中在哪些步
  3. ★ 关键的"机会成本"检验：
     在固定 K=3 的每个重建点上，若改为复用（推迟），
     真实总成本会下降还是上升 —— 这是对"推迟是否值得"的无歧义检验。
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


def build(tag, logdir, rounds, Ks):
    cells = defaultdict(list); rv = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c)
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
            if a in row: return row[a]
            return row[min(sa[t], key=lambda x: abs(x-a))]
        ks = sorted(curve)
        if a in curve: return curve[a]
        return curve[ks[-1]]
    return N, curve


def trace_fixed(Nfn, r0, K, T, b0=100):
    tl = []; a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            c = r0 + Nfn(t, 0); a = 1; tl.append((t, True, a, c))
        else:
            c = Nfn(t, a); a += 1; tl.append((t, False, a, c))
    return tl


def trace_online(Nfn, r0, T, target_age=5, force_every=40, lvl_mode="last", b0=100):
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
        if t < b0: rb = True
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
            nn = Nfn(t, 0); c = r0+nn; tot += c; acc, accn = c, 1; a = 1
            levels.append(nn); since += 1
            if target_age > 0:
                lm = max([k for k in know if know[k]], default=0)
                if lm < target_age and since >= force_every:
                    in_probe = target_age-lm; since = 0
        else:
            nn = Nfn(t, a); c = nn; tot += c; acc += nn; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(nn-bm)
            a += 1
            if in_probe > 0: in_probe -= 1
            since += 1
        tl.append((t, rb, a, c))
    return tot, tl


tag, logdir, rounds, Ks = "l20", "l20", [1,2,3,4,5], [1,2,3,5,8]
cfg = build(tag, logdir, rounds, Ks)
Nfn, curve = mk(cfg["tab"])
T, r0 = cfg["nsteps"], cfg["r"]
print("="*104)
print("★★★ l20 在同一条数据上的逐点成本对照     T=%d  r=%.2f（s=3）" % (T, r0))
print("="*104)

pol = {}
pol["在线 P5/40"] = trace_online(Nfn, r0, T)[1]
for K in (2, 3, 5):
    pol["固定 K=%d" % K] = trace_fixed(Nfn, r0, K, T)

print("\n%-12s %8s %8s %9s %9s %8s %8s" %
      ("策略", "总成本", "重建数", "等效K", "age均值", "age中位", "age最大"))
for nm, tl in pol.items():
    ages = [a for _, rb, a, _ in tl if not rb]
    tot = sum(c for _, _, _, c in tl)
    print("%-12s %8.0f %8d %9.2f %9.2f %8.1f %8d"
          % (nm, tot, sum(1 for _, rb, _, _ in tl if rb),
             sum(1 for _, rb, _, _ in tl if rb)/T,
             st.mean(ages), st.median(ages), max(ages)))

# ---- 逐步成本差：在线 - 固定K3（只看 t>=100，预热期相同）----
a_onl, a_fix = pol["在线 P5/40"], pol["固定 K=3"]
print("\n★ 在线 与 固定K=3 的成本差（在线 − 固定）")
print("   预热期: %.0f" % sum(c for _, _, _, c in a_onl[:100]))
d_tot = 0.0; segs = []
for i in range(100, T):
    d = a_onl[i][3] - a_fix[i][3]
    d_tot += d
    segs.append((a_fix[i][0], d, a_onl[i][1], a_onl[i][2], a_fix[i][1], a_fix[i][2]))
print("   预热后总差 = %+.0f  （>0 表示在线更贵）" % d_tot)
gap_reb = sum(d for t, d, ro, ao, rf, af in segs if (ro and not rf) or (rf and not ro))
print("   其中 重建时机不同 的步贡献 = %+.0f" % gap_reb)
same_rb = [d for t, d, ro, ao, rf, af in segs if ro == rf]
print("   其中【双方都重建】/【双方都复用】的步贡献 = %+.0f" % sum(same_rb))

# ---- 无歧义检验：把固定 K=3 的某个重建推迟一步，真实成本变好还是变坏 ----
print("\n★ 无歧义检验：固定 K=3 的第 m 个重建点推迟一步重算（真实总成本）")
def cost_with_delay(K, m, T, b0=100):
    """把固定 K 策略的第 m 个重建点往后推 1 步，其余相位顺延。"""
    base = trace_fixed(Nfn, r0, K, T, b0)
    idx = [i for i, (t, rb, a, c) in enumerate(base) if rb and t > b0]
    if m >= len(idx): return None
    skip = idx[m]
    tot = 0.0; a = 0
    for i, (t, rb, aa, c) in enumerate(base):
        if i == skip:
            tot += Nfn(t, a); a += 1          # 该重建改为复用
        else:
            if t < b0 or (t-b0) % K == 0:
                tot += r0 + Nfn(t, 0); a = 1
            else:
                tot += Nfn(t, a); a += 1
    return tot
base3 = sum(c for _, _, _, c in trace_fixed(Nfn, r0, 3, T))
nrb3 = sum(1 for t, rb, a, c in trace_fixed(Nfn, r0, 3, T) if rb and t > 100)
better = 0; worse = 0; tested = 0
for m in range(nrb3):
    v = cost_with_delay(3, m, T)
    if v is None: break
    tested += 1
    if v < base3 - 1e-6: better += 1
    elif v > base3 + 1e-6: worse += 1
print("   测试了 K=3 的 %d 个重建点（t>100）" % tested)
print("   其中 推迟一步反而更便宜 的: %d 个（%.1f%%）" % (better, 100.0*better/max(1, tested)))
print("   推迟一步更贵 的:           %d 个（%.1f%%）" % (worse, 100.0*worse/max(1, tested)))
print("   ⇒ 若 更好的 占多数，说明固定 K=3 已经【过于频繁】")
