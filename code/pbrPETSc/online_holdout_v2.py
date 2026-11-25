#!/usr/bin/env python3
"""
★★★ A1c：修正版在线策略的留出验证（全 7 配置）

相对 A1b 的唯一改动（两个都是实现层面的 bug，不是判据变更）：

★ 修复 1：预热期污染统计窗口
   原实现 `acc, accn = c, 1` 在 t < b0 时也执行，于是 t=100 之后
   第一个决策点的 avg 里仍挂着预热期最后一步的成本（r + N(t,0) ≈ 105），
   把阈值抬高到 60–105（真实稳态应约 42.7）⇒ 判据提前重建。
   修法：t < b0 时不写入 acc/accn（保持 0），预热结束从干净状态开始统计。

★ 修复 2：age 上限的失效（A_max 需要显式生效，见 diag_l20_fix.py 的验证）

对每个配置做留一轮：训练轮选 K* 与最佳变体，测试轮评估。
"""
import os, re, sys, json, statistics as st
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
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=st.median(rv) if rv else float("nan"), nsteps=ns)


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
            return row[a] if a in row else row[min(sa[t], key=lambda x: abs(x-a))]
        return curve.get(a, curve[amx])
    return N, curve


def sim_fixed(Nfn, r0, K, T, b0=100):
    tot, a = 0.0, 0
    for t in range(1, T+1):
        if (t < b0) or ((t-b0) % K == 0):
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


def sim_ceiling(Nfn, r0, T, b0=100):
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    for t in range(1, T+1):
        if t < b0:
            v = r0 + Nfn(t, 0); tot += v; acc, accn = v, 1; a = 1; continue
        avg = acc/accn if accn else tot/(t-1)
        if a == 0 or Nfn(t, a) > avg:
            v = r0 + Nfn(t, 0); tot += v; acc, accn = v, 1; a = 1
        else:
            v = Nfn(t, a); tot += v; acc += v; accn += 1; a += 1
    return tot


def sim_online(Nfn, r0, T, b0=100, target_age=0, force_every=0, lvl_mode="last",
               amax=99):
    """★ 修复版：预热期不污染统计窗口。"""
    know = defaultdict(list); levels = []
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    in_probe = 0; since = 10**9
    for t in range(1, T+1):
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        else:
            lvl = (levels[-1] + (levels[-1]-levels[-2])
                   if len(levels) >= 2 else (levels[-1] if levels else None))
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
            rb = est > avg
        if rb:
            nn = Nfn(t, 0); c = r0 + nn; tot += c
            # ★★ 修复 1：预热期不计入统计窗口
            if t < b0:
                acc, accn = 0.0, 0
            else:
                acc, accn = c, 1
            a = 1; levels.append(nn); since += 1
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
    return tot


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
    return V[1][1]


VARIANTS = [("P0",    dict(target_age=0, force_every=0,  lvl_mode="last",  amax=99)),
            ("P3/40", dict(target_age=3, force_every=40, lvl_mode="last",  amax=99)),
            ("P5/40", dict(target_age=5, force_every=40, lvl_mode="last",  amax=99)),
            ("P5/20", dict(target_age=5, force_every=20, lvl_mode="last",  amax=99)),
            ("T0",    dict(target_age=0, force_every=0,  lvl_mode="trend", amax=99)),
            ("T5/40", dict(target_age=5, force_every=40, lvl_mode="trend", amax=99)),
            ("A6",    dict(target_age=0, force_every=0,  lvl_mode="last",  amax=6)),
            ("A8",    dict(target_age=0, force_every=0,  lvl_mode="last",  amax=8))]
VKW = dict(VARIANTS)

CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8],       99),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8],       99),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8],       99),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8],       99),
    ("fl30", "fl30run", [1,2],             [1,3,5],           99),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8],       99),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13],     3),
]

print("="*112)
print("★★★ A1c：修正版在线策略 · 留一轮验证（修复预热期统计窗口污染）")
print("="*112)
summary = []
for tag, logdir, rounds, Ks, maxfold in CONFIGS:
    full = build(tag, logdir, rounds, Ks)
    if full is None:
        print("\n[%s] 数据缺失，跳过" % tag); continue
    T_full, r_full = full["nsteps"], full["r"]
    folds = rounds[:maxfold] if maxfold < 99 else rounds
    rec = defaultdict(list)
    for R in folds:
        tr_rounds = [x for x in rounds if x != R]
        tr = build(tag, logdir, tr_rounds, Ks)
        te = build(tag, logdir, [R], Ks)
        if tr is None or te is None: continue
        T = min(tr["nsteps"], te["nsteps"])
        Ntr, _ = mk(tr["tab"]); Nte, _ = mk(te["tab"])
        r_tr, r_te = tr["r"], te["r"]
        Kstar = min(Ks, key=lambda K: sim_fixed(Ntr, r_tr, K, T))
        onl_pick = min(VARIANTS, key=lambda kv: sim_online(Ntr, r_tr, T, **kv[1]))[0]
        orc = sim_dp(Nte, r_te, T)
        rec["fix"].append(sim_fixed(Nte, r_te, Kstar, T)/orc - 1)
        rec["onl"].append(sim_online(Nte, r_te, T, **VKW[onl_pick])/orc - 1)
        rec["cv"].append(sim_ceiling(Nte, r_te, T)/orc - 1)
        rec["K"].append(Kstar); rec["pick"].append(onl_pick)
    if not rec["fix"]: continue
    n = len(rec["fix"])
    def md(x): return st.median(x)*100
    win = sum(1 for i in range(n) if rec["onl"][i] < rec["fix"][i])
    v = "在线优 ✓" if md(rec["onl"]) < md(rec["fix"]) else "在线劣 ✗"
    print("\n[%s]  T=%d  r=%.2f  折叠=%d  候选变体=%s"
          % (tag, T_full, r_full, n, sorted(set(rec["pick"]))))
    print("   %-6s %-9s %10s %10s %10s" % ("轮", "选定K*", "在线变体", "固定周期", "在线"))
    for i in range(n):
        print("   R%-5d %-9d %10s %9.2f%% %9.2f%%"
              % (i+1, rec["K"][i], rec["pick"][i], rec["fix"][i]*100, rec["onl"][i]*100))
    print("   %-6s %-9s %10s %9.2f%% %9.2f%%   ceiling=%.2f%%   ⇒ %s (%+.2f pp, 胜率 %d/%d)"
          % ("中位", "-", "-", md(rec["fix"]), md(rec["onl"]), md(rec["cv"]),
             v, md(rec["onl"])-md(rec["fix"]), win, n))
    summary.append(dict(tag=tag, T=T_full, r=r_full, fix=md(rec["fix"]),
                        onl=md(rec["onl"]), cv=md(rec["cv"]), win=win, n=n, v=v))

print("\n" + "="*112)
print("★★★ A1c 汇总")
print("="*112)
print("  %-7s %8s %8s %11s %11s %11s %11s %10s" %
      ("配置","nsteps","r","固定周期","在线","ceiling","在线vs固定","胜率"))
for d in summary:
    print("  %-7s %8d %8.2f %10.2f%% %10.2f%% %10.2f%% %+10.2f pp %6d/%d"
          % (d["tag"], d["T"], d["r"], d["fix"], d["onl"], d["cv"],
             d["onl"]-d["fix"], d["win"], d["n"]))
print()
print("  ⇒ 在线优于固定周期: %d/%d" % (sum(1 for d in summary if d["onl"] < d["fix"]), len(summary)))
print("  ⇒ 在线相对 ceiling 中位差距: %+.2f pp"
      % st.median([d["onl"]-d["cv"] for d in summary]))
with open("a1c_result.json","w") as f:
    json.dump(summary, f, indent=1, ensure_ascii=False)
print("\n=> 写入 a1c_result.json")
