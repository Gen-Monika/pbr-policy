#!/usr/bin/env python3
"""
★★★ Stefan 高分辨率扫描分析（10 轮）

目的：K=3/5/8 在 3 轮下各夺冠一次，分不清。
     10 轮后用【夺冠次数】与【逐轮配对胜率】区分。

★ 同时检验：K=13 是否仍优于 K=1（判断 K=8 是否为内部最优）
"""
import os, re, sys, statistics as st
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


def run(tag, outfile, logdir, title):
    if not os.path.exists(outfile):
        print("(缺 %s，跳过)" % outfile); return None
    wall = defaultdict(list)
    for ln in open(outfile):
        m = WL.search(ln)
        if m:
            wall[int(m.group(2))].append(dict(rnd=int(m.group(1)), exe=float(m.group(4)),
                                             nstp=int(m.group(5)), nsol=int(m.group(6))))
    if not wall:
        print("(%s 无数据)" % outfile); return None
    ks = sorted(wall)
    print("\n" + "=" * 104)
    print("  %s   [%s]" % (title, tag))
    print("=" * 104)

    med, rinfo, Nsum, nreb = {}, {}, {}, {}
    for K in ks:
        ws = wall[K]
        setup, nb, tpc, tit, rs = [], [], [], [], []
        for w in ws:
            rows = load_csv("%s_pc_k%d_r%d.csv" % (tag, K, w["rnd"]))
            setup.append(sum(d["tPCSetup"] for d in rows))
            nb.append(sum(1 for d in rows if d["reused"] == 0))
            for d in rows:
                if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    tpc.append(d["tPCSetup"]); tit.append(d["tIter"]); rs.append(d["r"])
        med[K] = dict(exe=st.median([w["exe"] for w in ws]),
                      su=st.median(setup), nstp=st.median([w["nstp"] for w in ws]))
        nreb[K] = st.median(nb) if nb else 0
        rinfo[K] = (st.median(rs) if rs else float("nan"),
                    st.median(tpc)*1e6 if tpc else float("nan"),
                    st.median(tit)*1e6 if tit else float("nan"))
        ns = []
        for w in ws:
            v = per_step_N(os.path.join(logdir, "log.r%dk%d" % (w["rnd"], K)))
            if v: ns.append(sum(v))
        Nsum[K] = st.median(ns) if ns else None

    print("\n  ★ 预算（轮中位）")
    print("  %4s %10s %11s %9s %12s %10s %11s" %
          ("K", "墙钟/s", "分解/s", "重建数", "单次分解/µs", "n轮", "Σ迭代数"))
    for K in ks:
        print("  %4d %10.2f %11.3f %9.0f %12.1f %10d %11s"
              % (K, med[K]["exe"], med[K]["su"], nreb[K], rinfo[K][1],
                 len(wall[K]), "%d" % Nsum[K] if Nsum[K] else "-"))

    b = med[ks[0]]["exe"]
    print("\n  相对 K=1：")
    for K in ks:
        print("     K=%-3d 墙钟 %+7.2f%%   分解 %+7.2f%%"
              % (K, (med[K]["exe"]/b-1)*100, (med[K]["su"]/med[ks[0]]["su"]-1)*100))

    # ★ 逐轮配对
    print("\n  ★★★ 逐轮配对（主指标）")
    byround = defaultdict(dict)
    for K in ks:
        for w in wall[K]:
            byround[w["rnd"]][K] = w["exe"]
    wins = defaultdict(int)
    n = 0
    print("  %4s " % "轮" + "".join("%9s" % ("K=%d" % K) for K in ks) + "%9s" % "最优")
    for r in sorted(byround):
        d = byround[r]
        if len(d) < len(ks): continue
        n += 1
        w_ = min(d, key=lambda K: d[K]); wins[w_] += 1
        print("  %4d " % r + "".join("%9.2f" % d[K] for K in ks) + "%9s" % ("K=%d" % w_))
    print("\n  ⇒ 夺冠次数（共 %d 轮）: " % n
          + ", ".join("K=%d:%d" % (k, wins[k]) for k in sorted(wins)))
    print("\n  ── 与 K=1 的逐轮配对 ──")
    for K in ks:
        if K == 1: continue
        ds = [(byround[r][K]/byround[r][1]-1)*100 for r in sorted(byround)
              if len(byround[r]) == len(ks)]
        if ds:
            print("     K=%-3d vs K=1: 中位 %+7.2f%%  优于 %2d/%d 轮"
                  % (K, st.median(ds), sum(1 for x in ds if x < 0), len(ds)))
    # ★ 候选之间的两两胜率（区分能力）
    print("\n  ── 候选之间的两两胜率（关键：能否区分 3/5/8）──")
    cands = [K for K in ks if K > 1]
    for i in range(len(cands)):
        for j in range(i+1, len(cands)):
            a, c = cands[i], cands[j]
            ds = [byround[r][a] - byround[r][c] for r in sorted(byround)
                  if len(byround[r]) == len(ks)]
            if ds:
                win_a = sum(1 for x in ds if x < 0)
                print("     K=%-3d vs K=%-3d: K=%d 胜 %2d/%d 轮"
                      % (a, c, a, win_a, len(ds)))

    # ★ r 与判据
    print("\n  ★★★ r 与判据")
    print("  %4s %11s %10s %14s %13s %10s" %
          ("K", "r", "阈值r/s", "ΔN_step均值", "Σ迭代相对", "判定"))
    vs = [rinfo[K][0] for K in ks if rinfo[K][0] == rinfo[K][0]]
    thr = st.median(vs)/4 if vs else float("nan")
    n0 = Nsum.get(ks[0])
    for K in ks:
        if not Nsum.get(K) or not n0: continue
        dn = (Nsum[K]-n0)/max(med[K]["nstp"], 1)
        print("  %4d %11.2f %10.2f %14.1f %12.2f%% %10s"
              % (K, rinfo[K][0], rinfo[K][0]/4, dn, (Nsum[K]/n0-1)*100,
                 "复用 ✓" if dn < rinfo[K][0]/4 else "重建 ✗"))
    if vs:
        print("\n  ⇒ r 跨 K 波动 %.2f%%" % ((max(vs)-min(vs))/st.mean(vs)*100))
    bk = min(ks, key=lambda K: med[K]["exe"])
    print("  ⇒ 墙钟最优 K = %d (%.2f%%)" % (bk, (med[bk]["exe"]/b-1)*100))
    print("  ⇒ 分解最优 K = %d" % min(ks, key=lambda K: med[K]["su"]))
    return dict(k=bk, med=med)


print("=" * 104)
print("★★★ Stefan 高分辨率扫描（10 轮）")
print("=" * 104)
print("\n【ITEM 1】endTime=20, K∈{1,2,3,5,8,13} × 10 轮")
r1 = run("sth", "sth_scan.out", "stefan", "ITEM1: Stefan endTime=20 高分辨率")

print("\n\n【ITEM 2】endTime=50（官方完整时长）")
r2 = run("stf", "stf_scan.out", "stefan", "ITEM2: Stefan endTime=50")

print("""
  ★ 判读：
    - ITEM1：夺冠次数是否集中在单一 K？两两胜率是否 >7/10？
      ⇒ 分布均匀则该 K 附近仍无法区分，需换更长时间窗（ITEM2）
    - ITEM2：更长时间窗下最优 K 是否与 ITEM1 一致？
      ⇒ 一致则结论稳健；不一致则说明最优 K 依赖演化阶段
""")
