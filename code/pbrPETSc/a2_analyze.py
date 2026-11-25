#!/usr/bin/env python3
"""
★★★ A2 分析：在线策略的实机墙钟对照

三组：K=1（每步重建）/ K=3（调优后的固定周期）/ ONL（在线策略）
协议：每轮内 K1 → K3 → ONL 交错，多轮取中位（消除组间漂移）

输出三个口径，必须同时报告（§7 的三口径分歧）：
  ① wall_ms        端到端墙钟（主指标，需配对）
  ② ExecutionTime  OpenFOAM 自报求解时间
  ③ cost_model     Σ迭代数 + 重建次数 × r （模型口径，与离线对照）
"""
import os, re, glob, statistics as st

TIME = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLV = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def parse_log(p):
    """返回 (nsteps, sum_iters, execTime)"""
    it, ex = 0, None
    n = 0
    for ln in open(p, errors="ignore"):
        if TIME.match(ln):
            n += 1
        m = SOLV.search(ln)
        if m:
            it += int(m.group(1))
        m2 = re.search(r"ExecutionTime = ([0-9.]+) s", ln)
        if m2:
            ex = float(m2.group(1))
    return n, it, ex


def parse_csv_r(p):
    """重建步的 r 中位；同时给出重建次数"""
    rv, nrb = [], 0
    if not os.path.exists(p):
        return None, 0
    for ln in open(p):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25:
            continue
        try:
            d = dict(zip(CSV_HDR, q))
            if int(float(d["rep"])) < 0:
                continue
            if int(float(d["reused"])) == 0:
                nrb += 1
                tps, ti = float(d["tPCSetup"]), float(d["tIter"])
                if tps > 1e-4 and ti > 0:
                    rv.append(tps/ti)
        except ValueError:
            pass
    return (st.median(rv) if rv else None), nrb


TAG = os.environ.get("TAG", "a2l20")
MODES = ["K1", "K3", "ONL"]

rows = {}
for m in MODES:
    for p in sorted(glob.glob("%s_sv_%s_r*.csv" % (TAG, m))):
        pass
    for p in sorted(glob.glob("%s_case/log.%s.r*" % (TAG, m))):
        base = os.path.basename(p).replace("log.", "")
        # log.K1.r3  -> round 3
        mr = re.search(r"\.r(\d+)$", base)
        if not mr:
            continue
        R = int(mr.group(1))
        n, it, ex = parse_log(p)
        csvr = "%s_pc_%s_r%d.csv" % (TAG, m, R)
        rmed, nrb = parse_csv_r(csvr)
        rows.setdefault(m, []).append(dict(R=R, n=n, it=it, ex=ex,
                                           r=rmed, nrb=nrb))

print("=" * 100)
print("★★★ A2：在线策略实机对照    TAG=%s" % TAG)
print("=" * 100)

# ---- 逐指标 ----
for key, unit, label in (("wall", "ms", "端到端墙钟"),
                         ("ex", "s", "ExecutionTime")):
    pass

def wall_of(m, R):
    p = "%s_case/a2wall.csv" % TAG
    return None

# wall_ms 从运行日志解析（脚本自己打印的）
wall = {}
LOGFILE = os.environ.get("LOGFILE", "a2_l20.log")
for ln in open(LOGFILE, errors="ignore"):
    m = re.match(r"round=(\d+) mode=(\w+) wall_ms=(\d+) execTime=(\S*)", ln.strip())
    if m:
        wall.setdefault(m.group(2), {})[int(m.group(1))] = int(m.group(3))

print("\n%-6s %-6s %10s %10s %10s %10s %10s" %
      ("模式", "轮", "墙钟/ms", "迭代数", "重建数", "r", "模型成本"))
for m in MODES:
    for d in sorted(rows.get(m, []), key=lambda x: x["R"]):
        cm = (d["it"] + d["nrb"]*(d["r"] or 0.0)) if d["r"] else float("nan")
        print("%-6s %-6d %10s %10d %10d %10.2f %10.0f"
              % (m, d["R"], wall.get(m, {}).get(d["R"], "-"), d["it"],
                 d["nrb"], d["r"] or 0, cm))
    print()

print("=" * 100)
print("★★★ 汇总（中位）")
print("=" * 100)
print("%-6s %12s %12s %12s %12s %10s" %
      ("模式", "墙钟/ms", "ExecutionTime/s", "Σ迭代数", "重建次数", "r"))
med = {}
for m in MODES:
    ds = rows.get(m, [])
    if not ds: continue
    w = [wall.get(m, {})[d["R"]] for d in ds if d["R"] in wall.get(m, {})]
    med[m] = dict(w=st.median(w) if w else float("nan"),
                  ex=st.median([d["ex"] for d in ds if d["ex"]]),
                  it=st.median([d["it"] for d in ds]),
                  nrb=st.median([d["nrb"] for d in ds]),
                  r=st.median([d["r"] for d in ds if d["r"]]))
    print("%-6s %12.0f %12.2f %12.0f %12.0f %10.2f"
          % (m, med[m]["w"], med[m]["ex"], med[m]["it"], med[m]["nrb"], med[m]["r"]))

if "K1" in med and "K3" in med and "ONL" in med:
    print("\n★ 相对 K=1（每步重建）")
    for m in ("K3", "ONL"):
        print("   %-4s 墙钟 %+7.2f%%   ExecutionTime %+7.2f%%   迭代数 %+8.2f%%"
              % (m, 100*(med[m]["w"]/med["K1"]["w"]-1),
                 100*(med[m]["ex"]/med["K1"]["ex"]-1),
                 100*(med[m]["it"]/med["K1"]["it"]-1)))
    print("\n★ 相对 K=3（调优后的固定周期）—— 这是论文的关键对比")
    print("   ONL  墙钟 %+7.2f%%   ExecutionTime %+7.2f%%   迭代数 %+8.2f%%"
          % (100*(med["ONL"]["w"]/med["K3"]["w"]-1),
             100*(med["ONL"]["ex"]/med["K3"]["ex"]-1),
             100*(med["ONL"]["it"]/med["K3"]["it"]-1)))
    print("\n★ 逐轮配对（墙钟，ONL 优于 K=3 的轮数）")
    w3 = wall.get("K3", {}); wo = wall.get("ONL", {})
    win = sum(1 for R in w3 if R in wo and wo[R] < w3[R])
    print("   %d / %d 轮" % (win, len([R for R in w3 if R in wo])))
