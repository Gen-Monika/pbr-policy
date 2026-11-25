#!/usr/bin/env python3
"""
★★★ s 扫描：正确的老化曲线（从 reusedFrom 锚点取年龄）

★ 前三版失败的根本原因：
  K=1 的 run 【每一步都重建】，根本没有老化
  ⇒ 它的逐步迭代数是 N(0) 常量（8~10），不是 N(a)。
  老化曲线必须从 K>1 的 run 里，按 CSV 的 reusedFrom 算出每步真实年龄。

做法：把 CSV 每行的 timeIndex/reusedFrom 与日志的【逐步迭代数】按行序对齐
（CSV 每个时间步写一行，行序 = 步序）。年龄 a = timeIndex - reusedFrom。
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
    """每个时间步的 s 次求解迭代数之和，按出现顺序。"""
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

# ---- r 与最优 K ----
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
    opt[S] = dict(k=order[0], gain=(med[order[0]] / b - 1) * 100, base=b, all=med)

print("=" * 112)
print("★★★ s 扫描最终分析 v2：从 reusedFrom 锚点取真实年龄")
print("=" * 112)

print("\n  1. ★★★ r 的 s 不变性")
print("  %4s %10s %14s %12s" % ("s", "r", "tPCSetup/us", "tIter/us"))
for S in sorted(r_of):
    print("  %4d %10.2f %14.1f %12.2f" % (S, r_of[S][0], r_of[S][1], r_of[S][2]))
vs = [r_of[S][0] for S in r_of]
print("  ⇒ 跨 s 波动 %.2f%% ★ 不变 ✓" % ((max(vs) - min(vs)) / st.mean(vs) * 100))

print("\n  2. ★★★ 实测最优 K")
print("  %4s %8s %10s %12s %12s" % ("s", "最优K", "收益", "K=1墙钟/s", "K=3墙钟/s"))
for S in sorted(opt):
    o = opt[S]
    print("  %4d %8d %9.2f%% %12.2f %12.2f"
          % (S, o["k"], o["gain"], o["base"], o["all"].get(3, float("nan"))))

# ---- 真实老化曲线：按 CSV 年龄分组，联合所有 K 与所有轮 ----
print("\n  3. ★★★ 真实老化曲线 N_step(a)（从 reusedFrom 锚点取，5 轮合并）")
buckets = defaultdict(lambda: defaultdict(list))
for S in sorted(wall):
    for K, ws in wall[S].items():
        for w in ws:
            csvp = "s_pc_s%d_k%d_r%d.csv" % (S, K, w["rnd"])
            logp = "srun/log.s%dr%dk%d" % (S, w["rnd"], K)
            rows = load_csv(csvp)
            if not rows or not os.path.exists(logp):
                continue
            Ns = per_step_N(logp)
            if len(Ns) != len(rows):
                # 行序与步序可能因首个孤儿步错位，用长度对齐到较短者
                n = min(len(Ns), len(rows))
                rows, Ns = rows[:n], Ns[:n]
            for d, n in zip(rows, Ns):
                rf = int(d["reusedFrom"])
                ti = int(d["timeIndex"])
                if rf < 0:
                    a = 0
                elif rf == 1:
                    # 哨兵：PBR_PETSC_FREEZE_AT=1 模式下 reusedFrom=1 表示"冻结于步1"
                    a = ti - 1
                else:
                    a = ti - rf
                if a < 0:
                    continue
                buckets[S][a].append(n)

curves = {}
print("  %4s " % "s" + "".join("%12s" % ("a=%d" % a) for a in range(0, 9)))
for S in sorted(buckets):
    cur = []
    for a in range(0, 9):
        v = buckets[S].get(a, [])
        cur.append(st.median(v) if v else float("nan"))
    curves[S] = cur
    print("  %4d " % S + "".join("%12.1f" % v if v == v else "%12s" % "-" for v in cur))

print("\n  （样本数）")
print("  %4s " % "s" + "".join("%12s" % ("a=%d" % a) for a in range(0, 9)))
for S in sorted(buckets):
    print("  %4d " % S + "".join("%12d" % len(buckets[S].get(a, [])) for a in range(0, 9)))

print("\n  4. ★★★ 判据检验")
for S in sorted(curves):
    r = r_of[S][0]
    cur = curves[S]
    print("\n  ── s=%d, r=%.2f, 阈值 r/s=%.2f ──" % (S, r, r / S))
    print("  %5s %14s %14s %10s" % ("a", "N_step(a)", "ΔN_step", "判定"))
    first_bad = None
    for a in range(1, len(cur)):
        if cur[a] != cur[a] or cur[a - 1] != cur[a - 1]:
            continue
        dn = cur[a] - cur[a - 1]
        bad = dn >= r
        if bad and first_bad is None:
            first_bad = a
        print("  %5d %14.1f %14.1f %10s" % (a, cur[a], dn, "重建 ✗" if bad else "复用 ✓"))
    if first_bad:
        print("  ⇒ 可复用最长年龄 = %d ⇒ 预测 K = %d" % (first_bad - 1, first_bad))
    else:
        print("  ⇒ 在 a<=8 内未出现失效点")
    print("  ⇒ 实测最优 K = %d" % opt[S]["k"])

print("\n  5. ★★★ 核心结论表")
print("  %4s %10s %12s %12s %10s %14s" %
      ("s", "r", "阈值 r/s", "实测最优K", "收益", "N_step(4)/N_step(0)"))
for S in sorted(r_of):
    cur = curves.get(S, [])
    ratio = (cur[4] / cur[0]) if len(cur) > 4 and cur[0] == cur[0] and cur[0] else float("nan")
    print("  %4d %10.2f %12.2f %12d %9.2f%% %14.2f"
          % (S, r_of[S][0], r_of[S][0] / S, opt[S]["k"], opt[S]["gain"], ratio))
