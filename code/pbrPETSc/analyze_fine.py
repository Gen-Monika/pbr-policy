#!/usr/bin/env python3
"""
★★★ fine 网格（9072 单元，levels=20）的 K 扫描分析

目标 1：最优 K 是否继续外移（base 网格 L20 最优 K=5，r=90.8；fine r=110.6）
目标 2：★ 遵从"实验设计规范"，报告比值（r）与离散量（迭代数），
        并以【逐轮配对 + 优于基线的轮数】为主指标，弱化绝对秒数。
"""
import os, re, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)\s+nSolve=(\d+)\s+nStep=(\d+)")


def load_csv(path, valid_only=True):
    rows = []
    if not os.path.exists(path):
        return rows
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25:
            continue
        try:
            d = dict(zip(CSV_HDR, p))
            for k in d:
                if k not in ("field", "kind"):
                    d[k] = float(d[k])
            if valid_only and int(d["rep"]) < 0:
                continue
            rows.append(d)
        except ValueError:
            continue
    return rows


def per_step_N(path):
    out, cur = [], []
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur:
                out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m:
            cur.append(int(m.group(1)))
    if cur:
        out.append(sum(cur))
    return out


wall = defaultdict(list)
for ln in open("fine_scan.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)), exe=float(m.group(4)),
                                         solve=float(m.group(5)), nstp=int(m.group(7))))

print("=" * 110)
print("★★★ fine 网格（9072 单元）levels=20 的 K 扫描")
print("=" * 110)

# ---- 口径验证 ----
print("\n  1. ★ 口径验证")
print("  %4s %5s %9s %9s %11s %11s %8s" %
      ("K", "轮", "行数", "nBuildPC", "ΣtPCSetup", "tSetupAll", "一致"))
for K in sorted(wall):
    for w in wall[K]:
        rows = load_csv("fine_pc_k%d_r%d.csv" % (K, w["rnd"]), valid_only=False)
        if not rows:
            continue
        su = sum(d["tPCSetup"] for d in rows)
        ta = rows[-1]["tSetupAll"]
        if w["rnd"] <= 1:
            print("  %4d %5d %9d %9d %11.3f %11.3f %8s"
                  % (K, w["rnd"], len(rows), int(rows[-1]["nBuildPC"]), su, ta,
                     "✓" if abs(su / ta - 1) < 0.01 else "✗"))

# ---- 预算 ----
print("\n  2. ★★ 完整预算（轮中位）")
print("  %4s %10s %11s %11s %10s %10s %12s" %
      ("K", "墙钟/s", "CG总/s", "分解/s", "重建数", "步数", "单次分解/µs"))
med = {}
for K in sorted(wall):
    ws = wall[K]
    setup, nreb, tpc = [], [], []
    for w in ws:
        rows = load_csv("fine_pc_k%d_r%d.csv" % (K, w["rnd"]))
        setup.append(sum(d["tPCSetup"] for d in rows))
        nreb.append(sum(1 for d in rows if d["reused"] == 0))
        tpc += [d["tPCSetup"] for d in rows if d["reused"] == 0 and d["tPCSetup"] > 1e-4]
    med[K] = dict(exe=st.median([w["exe"] for w in ws]),
                  solve=st.median([w["solve"] for w in ws]),
                  su=st.median(setup), nreb=st.median(nreb),
                  nstp=st.median([w["nstp"] for w in ws]),
                  tpc=st.median(tpc) * 1e6 if tpc else float("nan"))
    print("  %4d %10.2f %11.2f %11.3f %10.0f %10.0f %12.1f"
          % (K, med[K]["exe"], med[K]["solve"], med[K]["su"],
             med[K]["nreb"], med[K]["nstp"], med[K]["tpc"]))

b = med[min(med)]["exe"]
print("\n  %4s %12s %12s %12s" % ("K", "墙钟相对K=1", "CG相对K=1", "分解相对K=1"))
for K in sorted(med):
    print("  %4d %11.2f%% %11.2f%% %11.2f%%"
          % (K, (med[K]["exe"] / b - 1) * 100,
             (med[K]["solve"] / med[1]["solve"] - 1) * 100,
             (med[K]["su"] / med[1]["su"] - 1) * 100))
bk = min(med, key=lambda K: med[K]["exe"])
print("\n  ⇒ 墙钟最优 K = %d (%.2f%%)" % (bk, (med[bk]["exe"] / b - 1) * 100))
print("  ⇒ CG 最优 K = %d" % min(med, key=lambda K: med[K]["solve"]))
print("  ⇒ 分解最优 K = %d" % min(med, key=lambda K: med[K]["su"]))

# ---- 逐轮配对（主指标） ----
print("\n  3. ★★★ 逐轮配对（主指标：优于 K=1 的轮数）")
ks = sorted(wall)
byround = defaultdict(dict)
for K in ks:
    for w in wall[K]:
        byround[w["rnd"]][K] = w["exe"]
n = 0
print("  %4s " % "轮" + "".join("%9s" % ("K=%d" % K) for K in ks) + "%10s" % "最优")
wins = defaultdict(int)
for r in sorted(byround):
    d = byround[r]
    if len(d) < len(ks):
        continue
    n += 1
    w_ = min(d, key=lambda K: d[K])
    wins[w_] += 1
    print("  %4d " % r + "".join("%9.2f" % d[K] for K in ks) + "%10s" % ("K=%d" % w_))
print("\n  ⇒ 夺冠次数: " + ", ".join("K=%d:%d" % (k, wins[k]) for k in sorted(wins)))
print("\n  ── 与 K=1 的逐轮配对 ──")
for K in ks:
    if K == 1:
        continue
    ds = [(byround[r][K] / byround[r][1] - 1) * 100 for r in sorted(byround)
          if len(byround[r]) == len(ks)]
    better = sum(1 for x in ds if x < 0)
    print("     K=%2d vs K=1: 中位 %+7.2f%%  优于 %d/%d 轮  [%s]"
          % (K, st.median(ds), better, len(ds),
             " ".join("%+.1f%%" % x for x in ds)))

# ---- r 的稳健性 ----
print("\n  4. ★★★ r（比值，免疫波动）的口径")
print("  %4s %12s %14s %12s %10s" % ("K", "r（重建步）", "tPCSetup/µs", "tIter/µs", "重建步数"))
rr = {}
for K in sorted(wall):
    rs, ts, ti = [], [], []
    for w in wall[K]:
        for d in load_csv("fine_pc_k%d_r%d.csv" % (K, w["rnd"])):
            if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                rs.append(d["r"]); ts.append(d["tPCSetup"]); ti.append(d["tIter"])
    if rs:
        rr[K] = (st.median(rs), st.median(ts) * 1e6, st.median(ti) * 1e6)
        print("  %4d %12.2f %14.1f %12.2f %10d"
              % (K, rr[K][0], rr[K][1], rr[K][2], len(rs)))
vs = [v[0] for v in rr.values()]
if len(vs) > 1:
    print("\n  ⇒ 跨 K 波动 %.2f%%  %s"
          % ((max(vs) - min(vs)) / st.mean(vs) * 100,
             "★ 稳定 ✓（r 仍不随策略变化）" if (max(vs)-min(vs))/st.mean(vs) < 0.02
             else "⚠️ 有变化"))

# ---- 迭代数与判据 ----
print("\n  5. ★★★ 迭代数（离散量，最抗波动）")
print("  %4s %12s %14s %12s" % ("K", "Σ迭代数", "相对K=1", "步数"))
base_N = None
NN = {}
for K in sorted(wall):
    ns = []
    for w in wall[K]:
        Ns = per_step_N("finerun/log.r%dk%d" % (w["rnd"], K))
        if Ns:
            ns.append(sum(Ns))
    if ns:
        NN[K] = st.median(ns)
        if base_N is None:
            base_N = NN[K]
        print("  %4d %12.0f %13.2f%% %12.0f"
              % (K, NN[K], (NN[K] / base_N - 1) * 100, med[K]["nstp"]))

print("\n  6. ★★★ 判据检验：用 r 与迭代数（两者都抗波动）")
print("  %4s %10s %12s %14s %12s" %
      ("K", "r", "阈值 r/s", "ΔN_step均值", "判定"))
for K in sorted(rr):
    if K == 1:
        continue
    dN = (NN[K] - NN[1]) / max(med[K]["nstp"], 1)
    print("  %4d %10.2f %12.2f %14.1f %12s"
          % (K, rr[K][0], rr[K][0] / 3, dN,
             "复用 ✓" if dN < rr[K][0] else "重建 ✗"))

print("""
  ★ 判据预测：ΔN_step < r 时应复用。
  同时给出 fine 与 base 的 r 对比，看最优 K 是否随 r 外移。
""")
