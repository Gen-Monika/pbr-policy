#!/usr/bin/env python3
"""
★★★ Stefan ITEM2 扩档分析（endTime=50, K∈{1,5,8,13,20} × 3 轮）

目的：ITEM2 原扫描的最优 K=8 压在扫描上界（K∈{1,3,5,8}）
      ⇒ 扩档到 20 判断是否存在内部最优。
★ 整批重跑（含 K=1 基线），保证配对合法。
"""
import os, re, statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"nStep=(\d+)\s+nSolve=(\d+)")


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
for ln in open("stx_scan.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)), exe=float(m.group(4)),
                                         nstp=int(m.group(5)), nsol=int(m.group(6))))
ks = sorted(wall)
print("=" * 104)
print("★★★ Stefan ITEM2 扩档（endTime=50, levels=5, s=4）")
print("=" * 104)

print("\n  0. ★ s 生效验证（nSolve/nStep 应为 4）")
w = wall[ks[0]][0]
print("     K=%d nStep=%d nSolve=%d 比值=%.2f" % (ks[0], w["nstp"], w["nsol"], w["nsol"]/w["nstp"]))

med, rinfo, Nsum, nreb = {}, {}, {}, {}
for K in ks:
    ws = wall[K]
    setup, nb, tpc, tit, rs = [], [], [], [], []
    for w in ws:
        rows = load_csv("stx_pc_k%d_r%d.csv" % (K, w["rnd"]))
        setup.append(sum(d["tPCSetup"] for d in rows))
        nb.append(sum(1 for d in rows if d["reused"] == 0))
        for d in rows:
            if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                tpc.append(d["tPCSetup"]); tit.append(d["tIter"]); rs.append(d["r"])
    med[K] = dict(exe=st.median([w["exe"] for w in ws]),
                  su=st.median(setup) if setup else 0.0,
                  nstp=st.median([w["nstp"] for w in ws]))
    nreb[K] = st.median(nb) if nb else 0
    rinfo[K] = (st.median(rs) if rs else float("nan"),
                st.median(tpc)*1e6 if tpc else float("nan"),
                st.median(tit)*1e6 if tit else float("nan"))
    ns = []
    for w in ws:
        v = per_step_N("stefan/log.r%dk%d" % (w["rnd"], K))
        if v: ns.append(sum(v))
    Nsum[K] = st.median(ns) if ns else None

print("\n  1. ★ 口径与预算（轮中位）")
print("  %4s %10s %11s %9s %12s %10s %11s" %
      ("K", "墙钟/s", "分解/s", "重建数", "单次分解/µs", "n轮", "Σ迭代数"))
for K in ks:
    print("  %4d %10.2f %11.3f %9.0f %12.1f %10d %11s"
          % (K, med[K]["exe"], med[K]["su"], nreb[K], rinfo[K][1], len(wall[K]),
             "%d" % Nsum[K] if Nsum[K] else "-"))

# 口径验证
print("\n  2. ★ 口径验证")
ok = 0
for K in ks:
    for w in wall[K]:
        rows = load_csv("stx_pc_k%d_r%d.csv" % (K, w["rnd"]), valid_only=False)
        if not rows: continue
        su = sum(d["tPCSetup"] for d in rows); ta = rows[-1]["tSetupAll"]
        if ta and abs(su/ta-1) < 1e-3: ok += 1
tot = sum(len(wall[K]) for K in ks)
print("     ΣtPCSetup == tSetupAll : %d/%d" % (ok, tot))

b = med[ks[0]]["exe"]
print("\n  3. ★★ 相对 K=1")
for K in ks:
    print("     K=%-3d 墙钟 %+7.2f%%   分解 %+7.2f%%"
          % (K, (med[K]["exe"]/b-1)*100,
             (med[K]["su"]/med[ks[0]]["su"]-1)*100 if med[ks[0]]["su"] else 0))

print("\n  4. ★★★ 逐轮配对")
byround = defaultdict(dict)
for K in ks:
    for w in wall[K]:
        byround[w["rnd"]][K] = w["exe"]
wins = defaultdict(int); n = 0
print("  %4s " % "轮" + "".join("%9s" % ("K=%d" % K) for K in ks) + "%9s" % "最优")
for r in sorted(byround):
    d = byround[r]
    if len(d) < len(ks): continue
    n += 1
    w_ = min(d, key=lambda K: d[K]); wins[w_] += 1
    print("  %4d " % r + "".join("%9.2f" % d[K] for K in ks) + "%9s" % ("K=%d" % w_))
print("\n  ⇒ 夺冠: " + ", ".join("K=%d:%d" % (k, wins[k]) for k in sorted(wins)))
print("\n  ── 与 K=1 配对 ──")
for K in ks:
    if K == 1: continue
    ds = [(byround[r][K]/byround[r][1]-1)*100 for r in sorted(byround)
          if len(byround[r]) == len(ks)]
    if ds:
        print("     K=%-3d vs K=1: 中位 %+7.2f%%  优于 %d/%d" %
              (K, st.median(ds), sum(1 for x in ds if x < 0), len(ds)))

print("\n  5. ★★★ 判据")
print("  %4s %11s %10s %13s %12s %10s" %
      ("K", "r", "阈值r/s", "ΔN_step", "Σ迭代相对", "判定"))
vs = [rinfo[K][0] for K in ks if rinfo[K][0] == rinfo[K][0]]
n0 = Nsum.get(ks[0])
for K in ks:
    if not Nsum.get(K) or not n0: continue
    dn = (Nsum[K]-n0)/max(med[K]["nstp"], 1)
    print("  %4d %11.2f %10.2f %13.1f %11.2f%% %10s"
          % (K, rinfo[K][0], rinfo[K][0]/4, dn, (Nsum[K]/n0-1)*100,
             "复用 ✓" if dn < rinfo[K][0]/4 else "重建 ✗"))
if vs:
    print("\n  ⇒ r 跨 K 波动 %.2f%%" % ((max(vs)-min(vs))/st.mean(vs)*100))
bk = min(ks, key=lambda K: med[K]["exe"])
print("  ⇒ 墙钟最优 K = %d (%.2f%%)" % (bk, (med[bk]["exe"]/b-1)*100))
print("  ⇒ 是否压在扫描上界: %s" % ("★ 是（需继续扩档）" if bk == ks[-1] else "否（存在内部最优）"))
print("  ⇒ 分解最优 K = %d" % min(ks, key=lambda K: med[K]["su"]))
