#!/usr/bin/env python3
"""
★★★ A1b：留一轮验证（leave-one-round-out），消除选择偏差

═══════════════════════════════════════════════════════════════════
为什么需要这个
═══════════════════════════════════════════════════════════════════
A1 的两边都有选择偏差，但方向不同：
  - 固定周期的 K* 是在【同一批数据】上选出的最优 ⇒ 有事后信息优势
  - 在线的"最好"是从 8 个变体里挑的最小值     ⇒ 偏差方向是【利于在线】

⇒ 两者的比较不公平，且无法判断"在线是否真的优于固定周期"。

本脚本的做法（留一轮）：
  对每一轮 R：
    1. 用【除 R 之外的所有轮】构建训练表
    2. 在训练表上选定：固定周期的 K*、在线的最佳变体
    3. 在【仅含 R】的测试表上评估两者的表现
  最后对所有 R 求中位/均值。

⇒ 选定过程从未见过测试轮 ⇒ 两边都是诚实的。

同时报告"作弊"基线（在测试轮上直接选最优）以量化偏差大小。
"""
import os, re, sys, json, statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def per_step_N(logpath):
    out, cur = [], []
    for ln in open(logpath, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def load_csv_rows(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25: continue
        try:
            d = dict(zip(CSV_HDR, p))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            rows.append(d)
        except ValueError: pass
    return rows


def row_per_step(rows):
    seen = {}
    for d in rows:
        if int(d["rep"]) < 0: continue
        t = int(d["timeIndex"])
        if t not in seen: seen[t] = d
    return [seen[t] for t in sorted(seen)]


def build_config(tag, logdir, logpat, Ks, rounds, s):
    cells = defaultdict(list)
    rvals = []
    nsteps = None
    for K in Ks:
        for R in rounds:
            csvp = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            logp = os.path.join(logdir, logpat % (R, K))
            if not (os.path.exists(csvp) and os.path.exists(logp)): continue
            rows = row_per_step(load_csv_rows(csvp))
            Ns = per_step_N(logp)
            n = min(len(rows), len(Ns))
            if nsteps is None or n > nsteps: nsteps = n
            for i in range(n):
                d = rows[i]; t = i + 1
                rf = int(d["reusedFrom"])
                a = 0 if rf < 0 else (t - rf)
                cells[(t, a)].append(Ns[i])
            for d in rows:
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rvals.append(d["tPCSetup"] / d["tIter"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=st.median(rvals) if rvals else float("nan"),
                nsteps=nsteps)


def make_Nfn(tab):
    """★ 优化：按 t 预索引，避免每次缺失查表都遍历全表（原 O(T*A)）。"""
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amax_obs = max(curve) if curve else 0
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sorted_ages = {t: sorted(d) for t, d in byt.items()}

    def Nfn(t, a):
        row = byt.get(t)
        if row is not None:
            if a in row: return row[a]
            ages = sorted_ages[t]
            # 同一步内按年龄最近者取值
            best = min(ages, key=lambda aa: abs(aa - a))
            return row[best]
        if a in curve: return curve[a]
        return curve[amax_obs]
    return Nfn, curve


def sim_fixed(Nfn, r0, K, T, b0=100):
    tot, a = 0.0, 0
    for t in range(1, T+1):
        if (t < b0) or ((t - b0) % K == 0):
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


def sim_online(Nfn, r0, T, b0=100, target_age=0, force_every=0, lvl_mode="last"):
    know = defaultdict(list)
    levels = []
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    in_probe = 0
    since_probe = 10**9
    for t in range(1, T+1):
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        else:
            lvl = (levels[-1] + (levels[-1]-levels[-2])
                   if len(levels) >= 2 else (levels[-1] if levels else None))
        if t < b0: rebuild = True
        elif in_probe > 0: rebuild = False
        elif a == 0: rebuild = True
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
                        sl = (d2-d1)/max(1e-9, a2-a1)
                        delta = d2 + sl*(a-a2)
                    else:
                        delta = st.median(know[ks[-1]])
                else:
                    delta = 0.0
                est = lvl + max(0.0, delta)
            rebuild = est > avg
        if rebuild:
            nn = Nfn(t, 0); tot += r0 + nn
            acc, accn = r0 + nn, 1; a = 1; levels.append(nn); since_probe += 1
            if target_age > 0:
                learned = max([k for k in know if know[k]], default=0)
                if learned < target_age and since_probe >= force_every:
                    in_probe = target_age - learned; since_probe = 0
        else:
            nn = Nfn(t, a); tot += nn; acc += nn; accn += 1
            if levels:
                bmed = st.median(levels)
                if bmed > 1e-9: know[a].append(nn - bmed)
            a += 1
            if in_probe > 0: in_probe -= 1
            since_probe += 1
    return tot


def sim_dp(Nfn, r0, T, b0=100, AMAX=60):
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if t > b0 and a + 1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][1]


# 在线变体（★ 固定集合，训练轮选一个，测试轮用同一个）
VARIANTS = [("P0", dict(target_age=0, force_every=0, lvl_mode="last")),
            ("P3/40", dict(target_age=3, force_every=40, lvl_mode="last")),
            ("P5/40", dict(target_age=5, force_every=40, lvl_mode="last")),
            ("P8/40", dict(target_age=8, force_every=40, lvl_mode="last")),
            ("P5/20", dict(target_age=5, force_every=20, lvl_mode="last")),
            ("T0", dict(target_age=0, force_every=0, lvl_mode="trend")),
            ("T5/40", dict(target_age=5, force_every=40, lvl_mode="trend")),
            ("T8/40", dict(target_age=8, force_every=40, lvl_mode="trend"))]
VKW = dict(VARIANTS)   # ★ name -> kwargs

CONFIGS = [
    ("fx",    "fixed",   "log.r%dk%d", [1,2,3,5,8],    [1,2,3,4,5],      3, 99),
    ("l15",   "l15",     "log.r%dk%d", [1,2,3,5,8],    [1,2,3,4,5],      3, 99),
    ("l20",   "l20",     "log.r%dk%d", [1,2,3,5,8],    [1,2,3,4,5],      3, 99),
    ("fine",  "finerun", "log.r%dk%d", [1,2,3,5,8],    [1,2,3],          3, 99),
    ("fl30",  "fl30run", "log.r%dk%d", [1,3,5],        [1,2],            3, 99),
    ("x3",    "x3run",   "log.r%dk%d", [1,2,3,5,8],    [1,2],            3, 99),
    ("sth",   "stefan",  "log.r%dk%d", [1,2,3,5,8,13], list(range(1,11)), 4, 3),
]

print("=" * 112)
print("★★★ A1b：留一轮验证（消除选择偏差）")
print("=" * 112)
summary = []
for tag, logdir, logpat, Ks, rounds, s, maxfold in CONFIGS:
    full = build_config(tag, logdir, logpat, Ks, rounds, s)
    if full is None:
        print("\n[%s] 数据缺失，跳过" % tag); continue
    T_full, r_full = full["nsteps"], full["r"]
    print("\n" + "#"*112)
    print("#  [%s]  nsteps=%d  r=%.2f  s=%d  留出轮数=%d"
          % (tag, T_full, r_full, s, min(len(rounds), maxfold)))
    print("#"*112)

    folds = rounds[:maxfold] if maxfold < 99 else rounds
    rec = defaultdict(list)
    for R in folds:
        tr_rounds = [x for x in rounds if x != R]
        tr = build_config(tag, logdir, logpat, Ks, tr_rounds, s)
        te = build_config(tag, logdir, logpat, Ks, [R], s)
        if tr is None or te is None: continue
        T = min(tr["nsteps"], te["nsteps"])
        Ntr, _ = make_Nfn(tr["tab"]); Nte, _ = make_Nfn(te["tab"])
        r_tr, r_te = tr["r"], te["r"]

        # ---- 在训练轮上选定 ----
        fixed_tr = {K: sim_fixed(Ntr, r_tr, K, T) for K in Ks}
        Kstar = min(fixed_tr, key=fixed_tr.get)
        onl_tr = {n: sim_online(Ntr, r_tr, T, **kw) for n, kw in VARIANTS}
        onl_pick = min(onl_tr, key=onl_tr.get)

        # ---- 在测试轮上评估（同一个 K* / 同一个变体）----
        oracle_te = sim_dp(Nte, r_te, T)
        c_fix = sim_fixed(Nte, r_te, Kstar, T)
        c_onl = sim_online(Nte, r_te, T, **VKW[onl_pick])
        c_cv = sim_ceiling(Nte, r_te, T)
        c_base = sim_fixed(Nte, r_te, 1, T)
        rec["fix"].append(c_fix/oracle_te - 1)
        rec["onl"].append(c_onl/oracle_te - 1)
        rec["cv"].append(c_cv/oracle_te - 1)
        rec["base"].append(c_base/oracle_te - 1)
        rec["K"].append(Kstar); rec["pick"].append(onl_pick)
        # 作弊基线：在测试轮上直接选最优
        fixed_te = {K: sim_fixed(Nte, r_te, K, T) for K in Ks}
        rec["fix_cheat"].append(min(fixed_te.values())/oracle_te - 1)

    if not rec["fix"]:
        print("  无有效折叠"); continue
    n = len(rec["fix"])
    def md(x): return st.median(x)*100
    print("  折叠数 = %d" % n)
    print("  %-4s %-9s %10s %10s %10s %9s" % ("轮", "选定K*", "在线变体", "固定周期", "在线", "ceiling"))
    for i in range(n):
        print("  R%-3s %-9d %10s %9.2f%% %9.2f%% %8.2f%%"
              % (i+1, rec["K"][i], rec["pick"][i], rec["fix"][i]*100,
                 rec["onl"][i]*100, rec["cv"][i]*100))
    verdict = "在线优于固定周期 ✓" if md(rec["onl"]) < md(rec["fix"]) else "在线劣于固定周期 ✗"
    print("  %-4s %-9s %10s %9.2f%% %9.2f%% %8.2f%%   ← 中位"
          % ("—", "—", "—", md(rec["fix"]), md(rec["onl"]), md(rec["cv"])))
    print("  ⇒ %s（差 %+.2f pp）" % (verdict, md(rec["onl"]) - md(rec["fix"])))
    print("  ⇒ 在线 vs ceiling: %+.2f pp" % (md(rec["onl"]) - md(rec["cv"])))
    print("  ⇒ 作弊固定周期（在测试轮上选）: %.2f%%（泄漏量 %+.2f pp）"
          % (md(rec["fix_cheat"]), md(rec["fix"]) - md(rec["fix_cheat"])))
    win = sum(1 for i in range(n) if rec["onl"][i] < rec["fix"][i])
    print("  ⇒ 逐折胜率: 在线 %d/%d" % (win, n))
    summary.append(dict(tag=tag, n=n, K=md(rec["K"]) if False else rec["K"],
                        fix=md(rec["fix"]), onl=md(rec["onl"]), cv=md(rec["cv"]),
                        cheat=md(rec["fix_cheat"]), win=win,
                        verdict=verdict, r=r_full, T=T_full))

print("\n" + "=" * 112)
print("★★★ 留出验证汇总（中位 regret，相对测试轮的 oracle）")
print("=" * 112)
print("  %-7s %8s %8s %10s %10s %10s %10s %10s %8s" %
      ("配置","nsteps","r","固定周期","在线","ceiling","作弊固定","在线vs固定","胜率"))
for d in summary:
    print("  %-7s %8d %8.2f %9.2f%% %9.2f%% %9.2f%% %9.2f%% %+9.2f pp %5d/%d"
          % (d["tag"], d["T"], d["r"], d["fix"], d["onl"], d["cv"], d["cheat"],
             d["onl"]-d["fix"], d["win"], d["n"]))

nfav = sum(1 for d in summary if d["onl"] < d["fix"])
print()
print("  ⇒ 在线优于固定周期的配置数: %d/%d" % (nfav, len(summary)))
print("  ⇒ 在线达到 ceiling（差距 <1pp）的配置数: %d/%d"
      % (sum(1 for d in summary if d["onl"] - d["cv"] < 1.0), len(summary)))
print("  ⇒ 在线相对 ceiling 的中位差距: %+.2f pp"
      % st.median([d["onl"]-d["cv"] for d in summary]))

with open("online_holdout_result.json","w") as f:
    json.dump(summary, f, indent=1, ensure_ascii=False)
print("\n=> 写入 online_holdout_result.json")
