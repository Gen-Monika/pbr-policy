#!/usr/bin/env python3
"""
★★★ Stage D 公平性核查：REAC_PRECOND 的优势是否来自"我给了它 r"？

═══ 问题 ═══
在 stage_d_heuristics 里我把 REAC_PRECOND 的阈值设为 reac = 0.5·r_eff。
但文献中 reac 是【用户给定的固定整数】（生产求解器的输入参数），
其值不该依赖 r。给定 0.5·r_eff 等于把一个 oracle 信息塞给了阈值策略，
而在线策略必须自己学 —— 这不是公平比较。

═══ 本脚本 ═══
(1) 扫描 REAC 的固定阈值 reac ∈ [1, 500]，看 regret 曲线
(2) 找出【不依赖 r 的最优固定阈值】能到多少（这是"REAC 族"的真实上限）
(3) 与在线策略的 regret 对比；并报告在"不知道 r"的前提下，
    什么样的阈值规则能匹配在线
(4) 同样处理 Chalmers（它的 max(2k0,10) 里 2 是固定常数，也要扫）
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


def mk(tab):
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)
    ks = sorted(curve)
    gsl = (curve[ks[-1]] - curve[ks[-2]])/max(1e-9, ks[-1] - ks[-2]) if len(ks) >= 2 else 1.0
    gsl = max(1e-6, gsl)
    def N(t, a):
        row = byt.get(t)
        if row is None:
            return curve[a] if a in curve else curve[amx] + gsl*(a - amx)
        if a in row: return row[a]
        ages = sa[t]
        if a > ages[-1]:
            sl = ((row[ages[-1]] - row[ages[-2]])/max(1e-9, ages[-1]-ages[-2])) if len(ages) >= 2 else gsl
            return row[ages[-1]] + max(sl, gsl)*(a - ages[-1])
        lo = [x for x in ages if x <= a]
        return row[lo[-1]] if lo else row[ages[0]]
    return N, curve


def sim_dp(Nfn, r0, T, b0=100, AMAX=25):
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if t > b0 and a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][1]


def sim_reac(Nfn, r0, T, reac, b0=100):
    tot = 0.0; a = 0; nrb = 0
    for t in range(1, T+1):
        if t < b0 or a == 0: rebuild = True
        else: rebuild = Nfn(t, a) > reac
        if rebuild:
            tot += r0 + Nfn(t, 0); a = 1; nrb += 1
        else:
            tot += Nfn(t, a); a += 1
    return tot, nrb


def sim_chalmers(Nfn, r0, T, factor, floor, b0=100):
    tot = 0.0; a = 0; k0 = None; nrb = 0
    for t in range(1, T+1):
        N = Nfn(t, 0 if a == 0 else a)
        if t < b0 or a == 0: rebuild = True
        else:
            thr = max(factor*(k0 if k0 else N), floor)
            rebuild = N > thr
        if rebuild:
            k0 = Nfn(t, 0); tot += r0 + Nfn(t, 0); a = 1; nrb += 1
        else:
            tot += N; a += 1
    return tot, nrb


def sim_online(Nfn, r0, T, b0=100, lvl_mode="last"):
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    for t in range(1, T+1):
        if t < b0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if lvl_mode == "trend" and len(levels) >= 2:
                lvl = levels[-1] + (levels[-1] - levels[-2])
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
            N = Nfn(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < b0 else (c, 1)
            levels.append(N); a = 1; held = t
        else:
            N = Nfn(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot


CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8]),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8]),
    ("fl30", "fl30run", [1,2],             [1,3,5]),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8]),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13]),
]

print("=" * 112)
print("★★★ Stage D 公平性核查：REAC / Chalmers 在【不依赖 r】的固定阈值下能到多少")
print("=" * 112)

THR = [1, 2, 3, 5, 8, 13, 20, 30, 50, 80, 120, 200, 300, 500]
FAC = [1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
FLR = [5, 10, 20, 50]

rows_out = []
for tag, logdir, rounds, Ks in CONFIGS:
    cfg = build(tag, logdir, rounds, Ks)
    if cfg is None: continue
    Nfn, curve = mk(cfg["tab"])
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    orc = sim_dp(Nfn, r0, T)

    base = curve[0]
    # REAC：扫固定阈值
    reac_curve = []
    for th in THR:
        v, nr = sim_reac(Nfn, r0, T, th)
        reac_curve.append((th, 100*(v/orc - 1), nr))
    th_best, reac_best, _ = min(reac_curve, key=lambda x: x[1])

    # REAC：与 r 挂钩的版本（stage_d 里用的那个，作为"给了 r"的下界）
    v_r, nr_r = sim_reac(Nfn, r0, T, max(1.0, 0.5*r0))
    reac_with_r = 100*(v_r/orc - 1)

    # Chalmers：扫 (factor, floor)
    ch_best, ch_cfg = 1e9, None
    for f in FAC:
        for fl in FLR:
            v, nr = sim_chalmers(Nfn, r0, T, f, fl)
            if 100*(v/orc-1) < ch_best:
                ch_best, ch_cfg = 100*(v/orc-1), (f, fl)
    v_ch_lit, _ = sim_chalmers(Nfn, r0, T, 2.0, 10.0)
    ch_lit = 100*(v_ch_lit/orc - 1)

    # 在线
    onl = 100*(sim_online(Nfn, r0, T)/orc - 1)
    onl_t = 100*(sim_online(Nfn, r0, T, lvl_mode="trend")/orc - 1)

    rows_out.append(dict(tag=tag, T=T, r=r0, orc=orc, N0=base,
                         reac_best=reac_best, th_best=th_best,
                         reac_with_r=reac_with_r,
                         ch_lit=ch_lit, ch_best=ch_best, ch_cfg=ch_cfg,
                         onl=onl, onl_t=onl_t, curve=reac_curve))

print("\n  %-6s %8s %8s %9s %10s %11s %10s %10s %10s" %
      ("配置","r_eff","N₀","REAC最优","(该阈值)","REAC@0.5r","Chalmers","(最优f,fl)","在线"))
for d in rows_out:
    print("  %-6s %8.1f %8.1f %8.2f%% %10.0f %10.2f%% %9.2f%% %10s %9.2f%%"
          % (d["tag"], d["r"], d["N0"], d["reac_best"], d["th_best"],
             d["reac_with_r"], d["ch_lit"], str(d["ch_cfg"]), d["onl"]))

print("\n  ★ 关键对比：")
n1 = sum(1 for d in rows_out if d["onl"] < d["reac_best"])
n2 = sum(1 for d in rows_out if d["onl"] < d["ch_lit"])
n3 = sum(1 for d in rows_out if d["onl"] < d["reac_with_r"])
N = len(rows_out)
print("     在线优于【最优固定阈值的 REAC】: %d/%d" % (n1, N))
print("     在线优于【文献原形的 Chalmers】: %d/%d" % (n2, N))
print("     在线优于【与 r 挂钩的 REAC】  : %d/%d" % (n3, N))

print("\n  ★ REAC 的 regret 随固定阈值的变化（找平台区）")
print("  %-6s %s" % ("配置", " ".join("%7g" % t for t in THR)))
for d in rows_out:
    print("  %-6s %s" % (d["tag"],
          " ".join("%6.1f%%" % v for _, v, _ in d["curve"])))
