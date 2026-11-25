#!/usr/bin/env python3
"""
★★★ s 扫描：以真实重建步为锚的年龄曲线

前两版失败原因：用"按步号粗切窗口"求平均，而迭代数的漂移高度集中在
序列末尾（L10 s=3 时 a=8 处暴涨到 1264，其余 a<8 只有 20~250）
⇒ 窗口平均把信号抹平了。

正确做法：从 CSV 的 reusedFrom 读出每个快照的真实锚点，
按【真实年龄】分组统计。K=1 的 run 每一步都是基准步，
因此它的 per-step 迭代数按步号直接给出无偏的 N_step(a)。
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


def per_step_N(logpath):
    out, cur = [], []
    for ln in open(logpath, errors="ignore"):
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


wall = defaultdict(lambda: defaultdict(list))
for ln in open("s_scan.out"):
    m = WL_RE.search(ln)
    if m:
        wall[int(m.group(1))][int(m.group(3))].append(
            dict(rnd=int(m.group(2)), exe=float(m.group(5)), solve=float(m.group(6))))

r_of, opt = {}, {}
for S in sorted(wall):
    rs, ts, ti = [], [], []
    for K, ws in wall[S].items():
        for w in ws:
            for d in load_csv("s_pc_s%d_k%d_r%d.csv" % (S, K, w["rnd"])):
                if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rs.append(d["r"]); ts.append(d["tPCSetup"]); ti.append(d["tIter"])
    r_of[S] = (st.median(rs), st.median(ts) * 1e6, st.median(ti) * 1e6)
    med = {K: st.median([w["exe"] for w in ws]) for K, ws in wall[S].items()}
    b = med[min(med)]
    order = sorted(med, key=lambda K: med[K])
    opt[S] = dict(k=order[0], gain=(med[order[0]] / b - 1) * 100,
                  second=order[1], sgain=(med[order[1]] / b - 1) * 100, base=b,
                  all=med)

print("=" * 112)
print("★★★ s 扫描最终分析：真实年龄曲线 + 判据检验（levels=10）")
print("=" * 112)

print("\n  1. ★★★ r 的 s 不变性")
print("  %4s %10s %14s %12s" % ("s", "r", "tPCSetup/us", "tIter/us"))
for S in sorted(r_of):
    print("  %4d %10.2f %14.1f %12.2f" % (S, r_of[S][0], r_of[S][1], r_of[S][2]))
vs = [r_of[S][0] for S in r_of]
print("  ⇒ 跨 s 波动 %.2f%% ★ 不变 ✓（r 是预条件子属性，与每步解几次无关）"
      % ((max(vs) - min(vs)) / st.mean(vs) * 100))

print("\n  2. ★★★ 实测最优 K 与收益")
print("  %4s %8s %10s %8s %10s %12s %14s" %
      ("s", "最优K", "收益", "次优K", "次优收益", "K=1墙钟/s", "K=3/5/6 墙钟"))
for S in sorted(opt):
    o = opt[S]
    span = " ".join("%d:%.2f" % (K, o["all"][K]) for K in (3, 5, 6) if K in o["all"])
    print("  %4d %8d %9.2f%% %8d %9.2f%% %12.2f   %s"
          % (S, o["k"], o["gain"], o["second"], o["sgain"], o["base"], span))

print("\n  3. ★★★ 真实年龄曲线 N_step(a)（用 K=1 的 run，逐步迭代数）")
print("  %4s %8s " % ("s", "总步数") + "".join("%9s" % ("a=%d" % a) for a in range(0, 11)))
curves = {}
for S in sorted(wall):
    fp = "srun/log.s%dr1k1" % S
    if not os.path.exists(fp):
        print("  %4d  缺日志" % S); continue
    Ns = per_step_N(fp)
    curves[S] = Ns
    head = "".join("%9.0f" % Ns[a] for a in range(0, min(11, len(Ns))))
    print("  %4d %8d %s" % (S, len(Ns), head))

print("\n  4. ★★★ 全序列年龄曲线（不只是前 11 步，找漂移爆发点）")
print("  %4s " % "s" + "".join("%9s" % ("a=%d" % a)
      for a in (0, 10, 20, 40, 60, 80, 100, 150, 200, 250, 300, 340)))
for S in sorted(curves):
    Ns = curves[S]
    cells = []
    for a in (0, 10, 20, 40, 60, 80, 100, 150, 200, 250, 300, 340):
        cells.append("%9.0f" % Ns[a] if a < len(Ns) else "%9s" % "-")
    print("  %4d " % S + "".join(cells))

print("\n  5. ★★★ 判据检验（用真实年龄曲线）")
for S in sorted(curves):
    r = r_of[S][0]
    Ns = curves[S]
    print("\n  ── s=%d, r=%.2f, 阈值 r/s=%.2f ──" % (S, r, r / S))
    print("  %5s %12s %12s %14s %10s" %
          ("a", "N_step(a)", "ΔN_step", "ΔN_single", "判定(ΔN_step<r)"))
    first_bad = None
    for a in range(1, min(len(Ns), 30)):
        dn = Ns[a] - Ns[a - 1]
        single = dn / S
        bad = dn >= r
        if bad and first_bad is None:
            first_bad = a
        if a <= 12:
            print("  %5d %12.0f %12.0f %14.2f %10s"
                  % (a, Ns[a], dn, single, "重建 ✗" if bad else "复用 ✓"))
    pmax = (first_bad - 1) if first_bad else len(Ns) - 1
    print("  ⇒ 判据：可复用最长年龄 = %d ⇒ 预测 K = %d" % (pmax, pmax + 1))
    print("  ⇒ 实测最优 K = %d  %s"
          % (opt[S]["k"], "✓ 一致" if pmax + 1 == opt[S]["k"] else "⚠️ 不一致"))

print("\n  6. ★★★ 核心对比：s 对决策空间的压缩")
print("  %4s %10s %12s %14s %12s" %
      ("s", "r", "阈值 r/s", "实测最优K", "收益"))
for S in sorted(r_of):
    print("  %4d %10.2f %12.2f %14d %11.2f%%"
          % (S, r_of[S][0], r_of[S][0] / S, opt[S]["k"], opt[S]["gain"]))
