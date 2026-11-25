#!/usr/bin/env python3
"""
★★★ 覆盖策略敏感性：截断数据的影响 + 需要多大年龄覆盖

═══ 背景 ═══
cov2 把各配置的年龄覆盖补到 ~30。但 x3 的 K=20/K=30 单次成本远超脚本里的
`timeout 3600`，被中途杀死，产出是【截断】的：
    cov2_x3_pc_k20_r1.csv   759/1231 步 (62%)
    cov2_x3_pc_k30_r1.csv   365/1231 (30%)
    cov2_x3_pc_k20_r2.csv   进行中

截断的危害不只是"少了一段"，更隐蔽的是【窗口不一致】：
某个年龄的中位数只在一个短窗口上算，而邻居年龄在长窗口上算。
若 N 随时间有系统漂移，两个年龄的中位数就不可比，曲线会出现"假拐点"。

本脚本回答三个问题：
  Q1  N 随时间有系统漂移吗？（决定截断是否会污染曲线）
  Q2  把截断文件剔除后，主结果变多少？（政策 A vs B）
  Q3  年龄覆盖到多少就够？（把覆盖上限从 4 扫到 29，看结论何时稳定）
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → (基准步数, [(prefix, logdir, Ks, rounds), ...])
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

# ─────────── 解析缓存：每个文件只读一次 ───────────
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
                ent.append((i + 1, 0 if rf < 0 else i + 1 - rf, Ns[i]))
            rv = [x["tPCSetup"]/x["tIter"] for x in rr
                  if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0]
            rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
            nrs = sum(1 for x in rr if int(x["reused"]) == 0)
            fac = (nrs/len(rbs)) if rbs else 1.0
            val = dict(ent=ent, rv=rv, fac=fac, nstep=len(steps), nlog=len(Ns), K=K)
        except Exception:
            val = None
    CACHE[key] = val
    return val


def build(tag, policy, cap=None):
    """policy: 'A'=全部 / 'B'=剔除截断 / 'C'=B+共同窗口"""
    base_n = SPEC[tag][0]
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                d = parse_one(prefix, logdir, K, R)
                if d: files.append((prefix, logdir, K, R, d))

    if policy in ("B", "C"):
        files = [f for f in files if f[4]["nstep"] >= base_n]
    if not files: return None

    Tmax = min(f[4]["nstep"] for f in files) if policy == "C" else max(f[4]["nstep"] for f in files)
    if cap: Tmax = min(Tmax, cap)

    cells = defaultdict(list); rv = []; fac = []
    for prefix, logdir, K, R, d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 130)
print("★★★ Q1: N 随时间是否有系统漂移？（决定截断是否会污染曲线）")
print("=" * 130)
print("  对每个配置，取 K=1（每步重建，无年龄效应）的 N(t) 序列，")
print("  比较前半段与后半段的中位数。若差异大，则不同长度的窗口不可比。")
print()
print("  %-8s %10s %14s %14s %10s" % ("配置", "T", "前半段中位", "后半段中位", "变化"))
for tag in SPEC:
    d = None
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                dd = parse_one(prefix, logdir, K, R)
                if dd and K == 1:
                    d = dd; break
            if d: break
        if d: break
    if not d:
        print("  %-8s （无 K=1 数据）" % tag); continue
    N = [x[2] for x in d["ent"]]
    h = len(N)//2
    a1, a2 = st.median(N[:h]), st.median(N[h:])
    print("  %-8s %10d %14.1f %14.1f %9.1f%%"
          % (tag, len(N), a1, a2, 100*(a2/a1 - 1) if a1 else 0))

print()
print("=" * 130)
print("★★★ Q2: 剔除截断文件后，主结果变多少？（A=全部 / B=剔除 / C=B+共同窗口）")
print("=" * 130)
print("  %-6s %-4s %7s %6s %12s %8s %10s %10s %10s"
      % ("配置", "政策", "T", "amax", "oracle", "K*", "K*regret", "在线", "在线−K*"))
RES = {}
for tag in SPEC:
    for policy in ("A", "B", "C"):
        cfg = build(tag, policy)
        if cfg is None:
            print("  %-6s %-4s  ★无数据" % (tag, policy)); continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: Ks = (1,)
        try:
            orc, info = P.selfcheck(env, r0, T, label="%s/%s" % (tag, policy), Ks=Ks)
        except AssertionError as e:
            print("  %-6s %-4s  ★自检失败: %s" % (tag, policy, str(e)[:60])); continue
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc - 1); onl = 100*(info["online"]/orc - 1)
        RES[(tag, policy)] = dict(T=T, amax=env.amax_data, orc=orc, kb=kb,
                                  kk=kk, onl=onl, gap=onl-kk)
        print("  %-6s %-4s %7d %6d %12.0f %8d %9.2f%% %9.2f%% %+9.2f pp"
              % (tag, policy, T, env.amax_data, orc, kb, kk, onl, onl - kk))
    print()

print("  ── 政策 A→B 的结论漂移 ──")
print("  %-6s %12s %12s %12s %12s" % ("配置", "A 在线−K*", "B 在线−K*", "A K*regret", "B K*regret"))
for tag in SPEC:
    a = RES.get((tag, "A")); b = RES.get((tag, "B"))
    if not a or not b: continue
    flag = "  ★漂移>1pp" if abs(a["gap"] - b["gap"]) > 1.0 else ""
    print("  %-6s %+11.2f %+11.2f %11.2f%% %11.2f%%%s"
          % (tag, a["gap"], b["gap"], a["kk"], b["kk"], flag))

print()
print("=" * 130)
print("★★★ Q3: 年龄覆盖上限扫描 —— 覆盖到多少结论就稳定？（政策 B，剔除截断）")
print("=" * 130)
CAPS = (4, 7, 12, 19, 29)
print("  %-6s" % "配置" + "".join("%22s" % ("覆盖≤%d" % c) for c in CAPS))
print("  %-6s" % "" + "".join("%22s" % "(K* / 在线 / 差)" for c in CAPS))
for tag in SPEC:
    line = "  %-6s" % tag
    for cap in CAPS:
        cfg = build(tag, "B", cap=cap)
        if cfg is None:
            line += "%22s" % "—"; continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: line += "%22s" % "—"; continue
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError:
            line += "%22s" % "★自检失败"; continue
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc - 1); onl = 100*(info["online"]/orc - 1)
        line += "%22s" % ("Kstar%d %.1f%% %+.1f" % (kb, onl, onl - kk))
    print(line)
print("=" * 130)
