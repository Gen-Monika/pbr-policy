#!/usr/bin/env python3
"""
★★★ s（=nCorrectors）扫描分析：验证判据阈值 r/s 决定最优 K

预测：复用胜出 ⟺ ΔN_single(a) < r/s
  s=3 → 阈值 19.3 → K*=3（已实测）
  s=2 → 阈值 29.0 → K*=4
  s=1 → 阈值 58.1 → K*=6

★ 关键自验证：r 只依赖 levels（预条件子构造与迭代的【单次】成本），
  与 s 无关 ⇒ 三个 s 下 r 必须相同。
  若 r 随 s 变化，说明测量被污染或模型有误。
"""
import os, re, glob, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
WL_RE = re.compile(r"s=(\d+)\s+round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+"
                   r"execTime=([0-9.]+)\s+solveTime=([0-9.eE+-]+)\s+"
                   r"nSolve=(\d+)\s+nStep=(\d+)")


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


def per_step_N(logpath):
    """按 Time = 块切分，返回每步 s 次求解的迭代数之和。"""
    out = []
    cur = 0
    for ln in open(logpath, errors="ignore"):
        if TIME_RE.match(ln):
            if cur:
                out.append(cur)
            cur = 0
            continue
        m = SOLVE_RE.search(ln)
        if m:
            cur += int(m.group(1))
    if cur:
        out.append(cur)
    return out


wall = defaultdict(lambda: defaultdict(list))
for ln in open("s_scan.out"):
    m = WL_RE.search(ln)
    if m:
        wall[int(m.group(1))][int(m.group(3))].append(
            dict(rnd=int(m.group(2)), exe=float(m.group(5)),
                 solve=float(m.group(6)), nsol=int(m.group(7)),
                 nstp=int(m.group(8))))


def tagdir(s):
    return "srun"


print("=" * 104)
print("★★★ s 扫描：只改 nCorrectors（s），levels=10 固定")
print("=" * 104)

# --- 0. s 是否真的生效 ---
print("\n  0. ★ s 生效验证（nSolve/nStep 应等于 s）")
for S in sorted(wall):
    w = wall[S][sorted(wall[S])[0]][0]
    print("     s=%d : nSolve=%d nStep=%d 比值=%.2f  墙钟(%.1fs) CG(%.2fs)"
          % (S, w["nsol"], w["nstp"], w["nsol"] / w["nstp"], w["exe"], w["solve"]))

# --- 1. r 的 s 不变性（最强的模型自验证）---
print("\n" + "=" * 104)
print("1. ★★★ r 的 s 不变性检验（r 只依赖 levels，必须与 s 无关）")
print("=" * 104)
print("  %4s %10s %14s %12s %10s" % ("s", "r（重建步）", "tPCSetup/us", "tIter/us", "重建步数"))
rinv = {}
for S in sorted(wall):
    rs, ts, ti = [], [], []
    for K, ws in wall[S].items():
        for w in ws:
            for d in load_csv("s_pc_s%d_k%d_r%d.csv" % (S, K, w["rnd"])):
                if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rs.append(d["r"]); ts.append(d["tPCSetup"]); ti.append(d["tIter"])
    if rs:
        rinv[S] = (st.median(rs), st.median(ts) * 1e6, st.median(ti) * 1e6)
        print("  %4d %10.2f %14.1f %12.2f %10d"
              % (S, st.median(rs), st.median(ts) * 1e6, st.median(ti) * 1e6, len(rs)))
vals = [v[0] for v in rinv.values()]
if len(vals) > 1:
    print("\n  ⇒ 跨 s 波动 = %.2f%%  %s"
          % ((max(vals) - min(vals)) / st.mean(vals) * 100,
             "★ 不变 ✓（模型自验证通过）" if (max(vals)-min(vals))/st.mean(vals) < 0.02
             else "⚠️ 有变化，需查因"))

# --- 2. 每个 s 的预算与最优 K ---
print("\n" + "=" * 104)
print("2. ★★★ 各 s 的完整预算与最优 K")
print("=" * 104)
best = {}
for S in sorted(wall):
    print("\n  ── s = %d ──" % S)
    print("  %5s %10s %11s %11s %9s %9s" %
          ("K", "墙钟/s", "CG总/s", "分解/s", "重建数", "步数"))
    med = {}
    for K in sorted(wall[S]):
        ws = wall[S][K]
        if not ws:
            continue
        setup, nreb, rows_ok = [], [], 0
        for w in ws:
            rr = load_csv("s_pc_s%d_k%d_r%d.csv" % (S, K, w["rnd"]))
            setup.append(sum(d["tPCSetup"] for d in rr))
            nreb.append(sum(1 for d in rr if d["reused"] == 0))
        med[K] = dict(exe=st.median([w["exe"] for w in ws]),
                      solve=st.median([w["solve"] for w in ws]),
                      su=st.median(setup), nreb=st.median(nreb),
                      nstp=st.median([w["nstp"] for w in ws]))
        print("  %5d %10.2f %11.2f %11.3f %9.0f %9.0f"
              % (K, med[K]["exe"], med[K]["solve"], med[K]["su"],
                 med[K]["nreb"], med[K]["nstp"]))
    b = med[min(med)]["exe"]
    bk = min(med, key=lambda K: med[K]["exe"])
    bc = min(med, key=lambda K: med[K]["solve"])
    best[S] = dict(bk=bk, bc=bc, gain=(med[bk]["exe"] / b - 1) * 100)
    print("  ⇒ 墙钟最优 K = %d (%.2f%%)   CG 最优 K = %d"
          % (bk, (med[bk]["exe"] / b - 1) * 100, bc))

# --- 3. 判据预测 vs 实测 ---
print("\n" + "=" * 104)
print("3. ★★★ 判据预测 ΔN_single < r/s  vs  实测最优 K")
print("=" * 104)
print("  %4s %10s %10s %12s %14s %10s %8s" %
      ("s", "r", "阈值 r/s", "实测最优K", "预测最优K", "一致?", "收益"))
for S in sorted(wall):
    if S not in rinv:
        continue
    r = rinv[S][0]
    thr = r / S
    # 各 s 下重新测年龄曲线（用 K=1 的完整序列：每步都是重建）
    Ns = per_step_N("srun/log.s%dr1k1" % S)
    if not Ns:
        cand = glob.glob("srun/log.s%dr1k1" % S)
        if cand:
            Ns = per_step_N(cand[0])
    pred = None
    if len(Ns) > 10:
        base = st.median(Ns[:5])
        maxage = 0
        for a in range(1, min(12, len(Ns) // 10)):
            seg = Ns[a * (len(Ns) // 10):(a + 1) * (len(Ns) // 10)]
            if not seg:
                break
            dN_single = (st.median(seg) - base) / S
            if dN_single < thr:
                maxage = a
            else:
                break
        pred = maxage + 1
    print("  %4d %10.2f %10.2f %12d %14s %10s %7.2f%%"
          % (S, r, thr, best[S]["bk"],
             pred if pred else "n/a",
             ("✓" if pred == best[S]["bk"] else "✗") if pred else "-",
             best[S]["gain"]))

print("""
  ⇒ 结构性约束的核心：s 只改变判据的【阈值】r/s，不改变 r。
    若实测最优 K 随 s 单调下降方向正确，则"决策空间被 s 压缩"的论断成立。
""")
