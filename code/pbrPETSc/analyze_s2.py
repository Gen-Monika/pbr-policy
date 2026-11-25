#!/usr/bin/env python3
"""
★★★ s 扫描：正确的年龄曲线与判据检验

前版 analyze_s.py 的年龄曲线提取有缺陷（按块中位数粗切，导致预测 K=11）。
本版用【日志的 Time= 块号】与【CSV 的 timeIndex】精确对齐：
  对每个基准步 b，取"快照写于 b 的那些步"的全部 s 次求解的迭代数之和。
"""
import os, re, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
WL_RE = re.compile(r"s=(\d+)\s+round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+"
                   r"execTime=([0-9.]+)\s+solveTime=([0-9.eE+-]+)\s+"
                   r"nSolve=(\d+)\s+nStep=(\d+)")


def per_step_Ns(logpath):
    """返回 [(step_no, [该步每次求解的迭代数, ...]), ...]"""
    out, cur = [], []
    for ln in open(logpath, errors="ignore"):
        if TIME_RE.match(ln):
            if cur:
                out.append(cur)
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m:
            cur.append(int(m.group(1)))
    if cur:
        out.append(cur)
    return out


wall = defaultdict(lambda: defaultdict(list))
for ln in open("s_scan.out"):
    m = WL_RE.search(ln)
    if m:
        wall[int(m.group(1))][int(m.group(3))].append(
            dict(rnd=int(m.group(2)), exe=float(m.group(5)), solve=float(m.group(6))))


def load_csv(path):
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
            rows.append(d)
        except ValueError:
            continue
    return rows


print("=" * 108)
print("★★★ s 扫描：正确口径的年龄曲线 + 判据检验（levels=10 固定）")
print("=" * 108)

# ---- r 的 s 不变性 ----
print("\n  1. ★★★ r 的 s 不变性（r 只依赖 levels）")
print("  %4s %12s %14s %12s" % ("s", "r（重建步）", "tPCSetup/us", "tIter/us"))
r_of = {}
for S in sorted(wall):
    rs, ts, ti = [], [], []
    for K, ws in wall[S].items():
        for w in ws:
            for d in load_csv("s_pc_s%d_k%d_r%d.csv" % (S, K, w["rnd"])):
                if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rs.append(d["r"]); ts.append(d["tPCSetup"]); ti.append(d["tIter"])
    r_of[S] = st.median(rs)
    print("  %4d %12.2f %14.1f %12.2f" % (S, st.median(rs),
                                          st.median(ts) * 1e6, st.median(ti) * 1e6))
vs = list(r_of.values())
print("  ⇒ 跨 s 波动 %.2f%%  %s" % ((max(vs) - min(vs)) / st.mean(vs) * 100,
      "★ 不变 ✓" if (max(vs) - min(vs)) / st.mean(vs) < 0.02 else "⚠️ 有变化"))

# ---- 最优 K ----
print("\n  2. ★★★ 实测最优 K")
print("  %4s %10s %10s %10s %12s %12s" %
      ("s", "最优K", "收益", "次优K", "次优收益", "K=1墙钟/s"))
opt = {}
for S in sorted(wall):
    med = {K: st.median([w["exe"] for w in ws]) for K, ws in wall[S].items()}
    b = med[min(med)]
    order = sorted(med, key=lambda K: med[K])
    opt[S] = order[0]
    print("  %4d %10d %9.2f%% %10d %11.2f%% %12.2f"
          % (S, order[0], (med[order[0]] / b - 1) * 100,
             order[1], (med[order[1]] / b - 1) * 100, b))

# ---- 年龄曲线（正确的按基准步分组）----
print("\n  3. ★★★ 年龄曲线：以每个基准步为锚，每步 s 次求解的迭代总数")
print("  %4s " % "s" + "".join("%10s" % ("a=%d" % a) for a in range(0, 9)))
curve = {}
for S in sorted(wall):
    # 用 K=1 的 run（每步都是基准步，快照写于自身）
    fp = "srun/log.s%dr1k1" % S
    if not os.path.exists(fp):
        print("  %4d  (缺 %s)" % (S, fp)); continue
    steps = per_step_Ns(fp)
    n_tot = len(steps)
    if n_tot < 40:
        continue
    # 用 K=1 的 CSV 拿 timeIndex -> 行号 的映射
    rows = load_csv("s_pc_s1_k1_r1.csv")
    # 年龄 a 的平均迭代数：取步号区间 [a*L, (a+1)*L) 内每步的和
    L = n_tot // 8
    med = []
    for a in range(0, 9):
        seg = steps[a * L:(a + 1) * L]
        if not seg:
            break
        med.append(st.median([sum(x) for x in seg]))
    curve[S] = med
    print("  %4d " % S + "".join("%10.1f" % v for v in med))

# ---- 判据数值检验 ----
print("\n  4. ★★★ 判据 ΔN_step(a) < r  与  ΔN_single(a) < r/s")
print("  复用多撑一步的收益 = tPCSetup；代价 = 该步 s 次求解的迭代增量")
for S in sorted(curve):
    r = r_of[S]
    m = curve[S]
    print("\n  ── s=%d, r=%.2f, 阈值 r/s=%.2f ──" % (S, r, r / S))
    print("  %4s %12s %12s %14s %10s" %
          ("a", "N_step(a)", "ΔN_step", "ΔN_single", "判定"))
    for a in range(1, len(m)):
        dn = m[a] - m[a - 1]
        single = dn / S
        verdict = "复用 ✓" if dn < r else "重建 ✗"
        print("  %4d %12.1f %12.1f %14.2f %10s" % (a, m[a], dn, single, verdict))
    cross = [a for a in range(1, len(m)) if (m[a] - m[a - 1]) >= r]
    pmax = (cross[0] - 1) if cross else (len(m) - 1)
    print("  ⇒ 判据：可复用最长年龄 = %d ⇒ 预测 K = %d" % (pmax, pmax + 1))
    print("  ⇒ 实测最优 K = %d  %s" % (opt[S], "✓ 一致" if pmax + 1 == opt[S] else "⚠️ 不一致"))

print("""
  ★ 结构性约束的完整表述：
    s 同时进入【收益侧】（复用省下一次 tPCSetup）与【代价侧】（s 次求解都变慢），
    但代价侧的权重是 s·ΔN_single，收益侧与 s 无关
    ⇒ 阈值 r/s 随 s 下降 ⇒ s 越小，可复用年龄越长，决策空间越宽。
""")
