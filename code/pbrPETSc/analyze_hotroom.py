#!/usr/bin/env python3
"""
★★★ hotRoom（buoyantPimpleFoam, 4000 单元, 真 3D, s=2）分析

与 damBreak 的关键差异：
  - s=2（真实算例，非人为改 nCorrectors）
  - 真 3D 网格 ⇒ ILU 填充三维扩张，增长【加速】而非衰减
  - 浮力驱动，温度场缓慢漂移
  - 固定时间步（deltaT=2），1000 步
"""
import os, re, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)\s+nStep=(\d+)\s+nSolve=(\d+)")


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
    if not os.path.exists(path):
        return out
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


wall = defaultdict(list)
for ln in open("hr_scan.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)), exe=float(m.group(4)),
                                         solve=float(m.group(5)), nstp=int(m.group(6)),
                                         nsol=int(m.group(7))))
ks = sorted(wall)
print("=" * 108)
print("★★★ hotRoom（buoyantPimpleFoam, 4000 单元, 3D, levels=5, s=2）")
print("=" * 108)

print("\n  0. ★ s 生效验证（nSolve/nStep 应为 2）")
for K in ks:
    w = wall[K][0]
    print("     K=%-3d nStep=%d nSolve=%d 比值=%.2f" % (K, w["nstp"], w["nsol"], w["nsol"]/w["nstp"]))
    break

print("\n  1. ★ 口径验证")
print("  %4s %5s %9s %9s %12s %12s %8s" %
      ("K", "轮", "行数", "nBuildPC", "ΣtPCSetup", "tSetupAll", "一致"))
for K in ks:
    for w in wall[K][:1]:
        rows = load_csv("hr_pc_k%d_r%d.csv" % (K, w["rnd"]), valid_only=False)
        if not rows: continue
        su = sum(d["tPCSetup"] for d in rows); ta = rows[-1]["tSetupAll"]
        print("  %4d %5d %9d %9d %12.3f %12.3f %8s"
              % (K, w["rnd"], len(rows), int(rows[-1]["nBuildPC"]), su, ta,
                 "✓" if abs(su/ta-1) < 0.01 else "✗"))

print("\n  2. ★★ 预算（轮中位）")
print("  %4s %10s %11s %11s %9s %9s %12s %11s" %
      ("K", "墙钟/s", "CG总/s", "分解/s", "重建数", "步数", "单次分解/µs", "Σ迭代数"))
med, rinfo, Nsum = {}, {}, {}
for K in ks:
    ws = wall[K]
    setup, nreb, tpc, tit, rs = [], [], [], [], []
    for w in ws:
        rows = load_csv("hr_pc_k%d_r%d.csv" % (K, w["rnd"]))
        setup.append(sum(d["tPCSetup"] for d in rows))
        nreb.append(sum(1 for d in rows if d["reused"] == 0))
        for d in rows:
            if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                tpc.append(d["tPCSetup"]); tit.append(d["tIter"]); rs.append(d["r"])
    med[K] = dict(exe=st.median([w["exe"] for w in ws]),
                  solve=st.median([w["solve"] for w in ws]),
                  su=st.median(setup), nreb=st.median(nreb),
                  nstp=st.median([w["nstp"] for w in ws]))
    rinfo[K] = (st.median(rs) if rs else float("nan"),
                st.median(tpc)*1e6 if tpc else float("nan"),
                st.median(tit)*1e6 if tit else float("nan"))
    ns = []
    for w in ws:
        v = per_step_N("hotRoom/log.r%dk%d" % (w["rnd"], K))
        if v: ns.append(sum(v))
    if ns: Nsum[K] = st.median(ns)
    print("  %4d %10.2f %11.2f %11.3f %9.0f %9.0f %12.1f %11s"
          % (K, med[K]["exe"], med[K]["solve"], med[K]["su"], med[K]["nreb"],
             med[K]["nstp"], rinfo[K][1], "%d" % Nsum[K] if K in Nsum else "-"))

b = med[ks[0]]["exe"]
print("\n  3. ★★ 相对 K=1")
print("  %4s %12s %12s %12s" % ("K", "墙钟", "CG总", "分解"))
for K in ks:
    print("  %4d %11.2f%% %11.2f%% %11.2f%%"
          % (K, (med[K]["exe"]/b-1)*100,
             (med[K]["solve"]/med[1]["solve"]-1)*100,
             (med[K]["su"]/med[1]["su"]-1)*100))

print("\n  4. ★★★ 逐轮配对")
byround = defaultdict(dict)
for K in ks:
    for w in wall[K]:
        byround[w["rnd"]][K] = w["exe"]
print("  %4s " % "轮" + "".join("%10s" % ("K=%d" % K) for K in ks) + "%10s" % "最优")
wins = defaultdict(int)
n = 0
for r in sorted(byround):
    d = byround[r]
    if len(d) < len(ks): continue
    n += 1
    w_ = min(d, key=lambda K: d[K]); wins[w_] += 1
    print("  %4d " % r + "".join("%10.2f" % d[K] for K in ks) + "%10s" % ("K=%d" % w_))
print("\n  ⇒ 夺冠: " + ", ".join("K=%d:%d" % (k, wins[k]) for k in sorted(wins)))
print("\n  ── 与 K=1 的逐轮配对 ──")
for K in ks:
    if K == 1: continue
    ds = [(byround[r][K]/byround[r][1]-1)*100 for r in sorted(byround)
          if len(byround[r]) == len(ks)]
    if ds:
        print("     K=%2d vs K=1: 中位 %+7.2f%%  优于 %d/%d 轮  [%s]"
              % (K, st.median(ds), sum(1 for x in ds if x < 0), len(ds),
                 " ".join("%+.1f%%" % x for x in ds)))

print("\n  5. ★★★ r 与判据（抗波动量）")
vs = [rinfo[K][0] for K in ks if rinfo[K][0] == rinfo[K][0]]
thr = st.median(vs)/2 if vs else float("nan")
print("  %4s %12s %10s %14s %14s %10s" %
      ("K", "r", "阈值r/s", "ΔN_step均值", "Σ迭代相对", "判定"))
n0 = Nsum.get(1)
for K in ks:
    if K not in Nsum or n0 is None: continue
    dn = (Nsum[K]-n0)/max(med[K]["nstp"], 1)
    print("  %4d %12.2f %10.2f %14.1f %13.2f%% %10s"
          % (K, rinfo[K][0], rinfo[K][0]/2, dn, (Nsum[K]/n0-1)*100,
             "复用 ✓" if dn < rinfo[K][0]/2 else "重建 ✗"))
if vs:
    print("\n  ⇒ r 跨 K 波动 %.2f%%  %s"
          % ((max(vs)-min(vs))/st.mean(vs)*100,
             "★ 稳定 ✓" if (max(vs)-min(vs))/st.mean(vs) < 0.02 else "⚠️ 有变化"))
bk = min(ks, key=lambda K: med[K]["exe"])
print("  ⇒ 墙钟最优 K = %d (%.2f%%)" % (bk, (med[bk]["exe"]/b-1)*100))
print("  ⇒ CG 最优 K = %d" % min(ks, key=lambda K: med[K]["solve"]))
print("  ⇒ 分解最优 K = %d" % min(ks, key=lambda K: med[K]["su"]))
