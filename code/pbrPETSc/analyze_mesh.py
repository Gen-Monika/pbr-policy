#!/usr/bin/env python3
"""
★★★ 分辨率 / levels 二维交叉分析

回答两个问题：
  Q1  3x 网格（20412 单元）@ levels=20 的最优 K 是否仍在 3-5 区间？
  Q2  d(最优K)/d(levels) 与 d(最优K)/d(nCells) 谁更大？

★ 遵从实验设计规范：主报告量为
    r（比值，抗波动）、ΔN_step(K)（离散量）、判据交叉点，
    绝对墙钟只作辅证且必须逐轮配对。
"""
import os, re, sys, statistics as st
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
    if not os.path.exists(path):
        return out
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


def analyze(tag, outfile, logdir, logpat, title):
    if not os.path.exists(outfile):
        print("  (缺 %s，跳过 %s)" % (outfile, tag))
        return None
    wall = defaultdict(list)
    for ln in open(outfile):
        m = WL.search(ln)
        if m:
            wall[int(m.group(2))].append(dict(rnd=int(m.group(1)),
                                             exe=float(m.group(4)),
                                             solve=float(m.group(5)),
                                             nstp=int(m.group(7))))
    if not wall:
        print("  ( %s 无数据)" % tag); return None
    ks = sorted(wall)

    print("\n" + "=" * 108)
    print("  %s   [%s]" % (title, tag))
    print("=" * 108)

    med, rinfo, Nsum = {}, {}, {}
    for K in ks:
        ws = wall[K]
        setup, nreb, tpc, tit, rs = [], [], [], [], []
        for w in ws:
            rows = load_csv("%s_pc_k%d_r%d.csv" % (tag, K, w["rnd"]))
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
            v = per_step_N(os.path.join(logdir, logpat % (w["rnd"], K)))
            if v: ns.append(sum(v))
        if ns: Nsum[K] = st.median(ns)

    print("\n  ★ 预算（轮中位）")
    print("  %4s %10s %11s %11s %9s %9s %12s %11s" %
          ("K", "墙钟/s", "CG总/s", "分解/s", "重建数", "步数", "单次分解/µs", "Σ迭代数"))
    for K in ks:
        print("  %4d %10.2f %11.2f %11.3f %9.0f %9.0f %12.1f %11s"
              % (K, med[K]["exe"], med[K]["solve"], med[K]["su"],
                 med[K]["nreb"], med[K]["nstp"], rinfo[K][1],
                 "%d" % Nsum[K] if K in Nsum else "-"))

    b = med[min(med)]["exe"]
    print("\n  ★ 相对 K=1")
    print("  %4s %12s %12s %12s" % ("K", "墙钟", "CG总", "分解"))
    for K in ks:
        print("  %4d %11.2f%% %11.2f%% %11.2f%%"
              % (K, (med[K]["exe"]/b-1)*100,
                 (med[K]["solve"]/med[min(med)]["solve"]-1)*100,
                 (med[K]["su"]/med[min(med)]["su"]-1)*100))

    # ★ 逐轮配对（主指标）
    byround = defaultdict(dict)
    for K in ks:
        for w in wall[K]:
            byround[w["rnd"]][K] = w["exe"]
    print("\n  ★★ 逐轮配对")
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
    for K in ks:
        if K == 1: continue
        ds = [(byround[r][K]/byround[r][1]-1)*100 for r in sorted(byround)
              if len(byround[r]) == len(ks)]
        if ds:
            print("     K=%2d vs K=1: 中位 %+7.2f%%  优于 %d/%d 轮  [%s]"
                  % (K, st.median(ds), sum(1 for x in ds if x < 0), len(ds),
                     " ".join("%+.1f%%" % x for x in ds)))

    # ★ r 与判据
    vs = [rinfo[K][0] for K in ks if rinfo[K][0] == rinfo[K][0]]
    print("\n  ★★★ r 与判据（抗波动量）")
    print("  %4s %12s %10s %14s %14s %10s" %
          ("K", "r", "阈值r/3", "ΔN_step均值", "Σ迭代相对", "判定"))
    rmed = st.median(vs) if vs else float("nan")
    n0 = Nsum.get(1)
    for K in ks:
        if K not in Nsum or n0 is None: continue
        dn = (Nsum[K]-n0)/max(med[K]["nstp"], 1)
        print("  %4d %12.2f %10.2f %14.1f %13.2f%% %10s"
              % (K, rinfo[K][0], rinfo[K][0]/3, dn,
                 (Nsum[K]/n0-1)*100,
                 "复用 ✓" if dn < rinfo[K][0]/3 else "重建 ✗"))
    if vs:
        print("\n  ⇒ r 跨 K 波动 %.2f%%  %s"
              % ((max(vs)-min(vs))/st.mean(vs)*100,
                 "★ 稳定 ✓" if (max(vs)-min(vs))/st.mean(vs) < 0.02 else "⚠️ 有变化"))
    bk = min(ks, key=lambda K: med[K]["exe"])
    print("  ⇒ 墙钟最优 K = %d (%.2f%%)" % (bk, (med[bk]["exe"]/b-1)*100))
    return dict(k=bk, r=rmed, med=med, N=Nsum, nstp=med[bk]["nstp"])


res = {}
res["x3_L20"]   = analyze("x3",   "x3_scan.out",   "x3run",   "log.r%dk%d",
                          "3x 网格 20412 单元 @ levels=20")
res["fine_L10"] = analyze("fl10", "fl10_scan.out", "fl10run", "log.r%dk%d",
                          "fine 网格 9072 单元 @ levels=10")
res["fine_L30"] = analyze("fl30", "fl30_scan.out", "fl30run", "log.r%dk%d",
                          "fine 网格 9072 单元 @ levels=30")

print("\n" + "=" * 108)
print("  ★★★ 二维汇总：最优 K vs (nCells, levels)")
print("=" * 108)
print("  %8s %8s %10s %10s %12s" % ("nCells", "levels", "r", "最优K", "来源"))
ROWS = [("base", 2268, 10, 58.06, 3), ("base", 2268, 15, 78.02, 5),
        ("base", 2268, 20, 90.79, 5), ("fine", 9072, 20, 114.83, 3)]
for src, nc, lv, r_, k in ROWS:
    print("  %8d %8d %10.2f %10d %12s" % (nc, lv, r_, k, src))
for key, lbl in (("fine_L10", "fine-L10"), ("fine_L30", "fine-L30"),
                 ("x3_L20", "3x-L20")):
    v = res.get(key)
    if v:
        nc = 9072 if key.startswith("fine") else 20412
        lv = 10 if key.endswith("L10") else (30 if key.endswith("L30") else 20)
        print("  %8d %8d %10.2f %10d %12s" % (nc, lv, v["r"], v["k"], lbl))
print("""
  ★ 判读：
    - 若 3x-L20 的最优 K 仍在 3-5 ⇒ 预测成立 ⇒ 转 hotRoom/Stefan
    - 比较 fine-L10 / fine-L20 / fine-L30 的最优 K 变化幅度
      与 base-L20 / fine-L20 / 3x-L20 的变化幅度，
      即可回答 d(最优K)/d(levels) 与 d(最优K)/d(nCells) 谁更大
""")
