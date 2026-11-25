#!/usr/bin/env python3
"""
★★★ Q3 修正版 + fine 异常诊断

═══ 上一版 Q3 的两个错误 ═══
(1) 我截断的是 T（时间长度），而不是「年龄覆盖上限」。
    cap=4 ⇒ Tmax=4 ⇒ 整个算例只有 4 步，oracle ≡ K=1，全部退化。
    正确做法：保留完整 T，只丢弃【年龄 > cap】的格子。
(2) fine 报出 106.74% 的在线 regret（此前只覆盖到年龄 7 时是 6.98%）。
    这是新数据引入的异常，必须查清 —— 覆盖【增加】反而让在线【变差】，
    说明估计器对新出现的大年龄样本反应病态。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

SPEC = {
    "fx":   (344,  [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])]),
    "l15":  (344,  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
                    ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])]),
    "l20":  (344,  [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])]),
    "fine": (720,  [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
                    ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])]),
    "x3":   (1231, [("x3", "x3run", [1,2,3,5,8], [1,2]),
                    ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])]),
    "fl30": (720,  [("fl30", "fl30run", [1,3,5], [1,2]),
                    ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])]),
    "sth":  (5866, [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
                    ("cov2_sth", "cov2_sth", [20,30], [1,2,3])]),
}

CACHE = {}


def parse_one(prefix, logdir, K, R):
    key = (prefix, logdir, K, R)
    if key in CACHE: return CACHE[key]
    c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
    l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
    val = None
    if os.path.exists(c) and os.path.exists(l):
        try:
            rr = P.rows(c)
            seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            Ns = P.per_step_N(l)
            n = min(len(steps), len(Ns))
            ent = []
            for i in range(n):
                x = steps[i]; rf = int(x["reusedFrom"])
                ent.append((i+1, 0 if rf < 0 else i+1-rf, Ns[i]))
            rv = [x["tPCSetup"]/x["tIter"] for x in rr
                  if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0]
            rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
            nrs = sum(1 for x in rr if int(x["reused"]) == 0)
            val = dict(ent=ent, rv=rv, fac=(nrs/len(rbs)) if rbs else 1.0,
                       nstep=len(steps), K=K)
        except Exception:
            val = None
    CACHE[key] = val
    return val


def build(tag, policy="A", age_cap=None, k_cap=None):
    """
    policy : 'A' 全部 / 'B' 剔除截断（nstep < 基准）
    age_cap: 只保留 age ≤ age_cap 的格子（T 保持完整）★修正点
    k_cap  : 只使用 K ≤ k_cap 的文件
    """
    base_n = SPEC[tag][0]
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            if k_cap and K > k_cap: continue
            for R in rounds:
                d = parse_one(prefix, logdir, K, R)
                if d: files.append((K, R, d))
    if policy in ("B", "C"):
        files = [f for f in files if f[2]["nstep"] >= base_n]
    if not files: return None
    Tmax = max(f[2]["nstep"] for f in files) if policy != "C" else min(f[2]["nstep"] for f in files)

    cells = defaultdict(list); rv = []; fac = []
    for K, R, d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            if age_cap is not None and a > age_cap: continue   # ★ 只丢大年龄
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)


def ev(cfg, tag, Ks=None):
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="linear")
    if Ks is None:
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    if not Ks: return None
    try:
        orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
    except AssertionError:
        return None
    kb = info["Kbest"]
    return dict(T=T, amax=env.amax_data, orc=orc, kb=kb,
                kk=100*(info["fixed"][kb]/orc-1),
                onl=100*(info["online"]/orc-1), env=env, info=info, r0=r0)


print("=" * 126)
print("★★★ Q3（修正）：年龄覆盖上限扫描 —— T 保持完整，只丢弃 age > cap 的格子")
print("=" * 126)
CAPS = (3, 5, 7, 12, 19, 29)
print("  %-6s %10s" % ("配置", "完整amax") + "".join("%20s" % ("age≤%d" % c) for c in CAPS))
print("  %-6s %10s" % ("", "") + "".join("%20s" % "(K* / 在线 / 差)" for c in CAPS))
for tag in SPEC:
    full = ev(build(tag, "A"), tag)
    line = "  %-6s %10s" % (tag, full["amax"] if full else "—")
    for cap in CAPS:
        r = ev(build(tag, "A", age_cap=cap), tag)
        if r is None:
            line += "%20s" % "—"; continue
        line += "%20s" % ("K%d %.1f%% %+.1f" % (r["kb"], r["onl"], r["onl"] - r["kk"]))
    print(line)

print()
print("=" * 126)
print("★★★ fine 异常诊断：为什么覆盖增加反而让在线变差？")
print("=" * 126)
for tag in ("fine", "x3", "l15"):
    print("\n  ── %s ──" % tag)
    print("  %-6s %14s %12s %8s %10s %10s %8s"
          % ("K上限", "文件数", "T", "amax", "K*regret", "在线", "差"))
    for kc in (None, 3, 5, 8, 13, 20, 30):
        cfg = build(tag, "A", k_cap=kc)
        if cfg is None: continue
        r = ev(cfg, tag)
        if r is None:
            print("  %-6s %14s  ★自检失败" % (str(kc), "—")); continue
        nfiles = sum(1 for prefix, logdir, Ks, rounds in SPEC[tag][1]
                     for K in Ks if (kc is None or K <= kc) for R in rounds
                     if parse_one(prefix, logdir, K, R))
        print("  %-6s %14d %12d %8d %9.2f%% %9.2f%% %+7.2f"
              % (str(kc) if kc else "全部", nfiles, r["T"], r["amax"],
                 r["kk"], r["onl"], r["onl"] - r["kk"]))

print()
print("=" * 126)
print("★★★ 核心问题：在线策略的 regret 对【覆盖上限】是否敏感（稳定性判据）")
print("=" * 126)
print("  衡量：把 age 上限从 1 扫到 30，看在线 regret 的波动幅度。")
print("  波动大 ⇒ 策略对数据里出现的最大年龄敏感 ⇒ 不宜作论文主结果。")
print()
for tag in SPEC:
    vals = []
    for cap in range(1, 31):
        r = ev(build(tag, "A", age_cap=cap), tag)
        if r: vals.append((cap, r["onl"], r["kb"], r["amax"]))
    if not vals: continue
    ons = [v[1] for v in vals]
    span = max(ons) - min(ons)
    # 找出波动最大的相邻台阶
    jump = max(((vals[i+1][1]-vals[i][1], vals[i][0], vals[i+1][0])
                for i in range(len(vals)-1)), key=lambda z: abs(z[0]))
    print("  %-6s 在线 regret: 最小 %7.2f%%  最大 %9.2f%%  跨度 %8.2f pp"
          % (tag, min(ons), max(ons), span))
    print("         最大跳变发生在 age 上限 %d→%d：%+.2f pp"
          % (jump[1], jump[2], jump[0]))
print("=" * 126)
