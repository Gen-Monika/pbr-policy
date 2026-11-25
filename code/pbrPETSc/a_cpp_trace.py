#!/usr/bin/env python3
"""
★★★ 用 C++ 实测日志核验在线策略的重建间隔

═══ 两种 CSV 格式 ═══
(A) 冻结/固定周期扫描的 pc CSV —— 25 列、无表头
    1 timeIndex 2 field 3 kind 4 levels 5 nCells 6 nFaces 7 rep 8 freezeAt
    9 reused 10 period 11 reusedFrom ... 23 nApplyCalls 25 nBuildPC
    重建判定：reusedFrom < 0

(B) 在线策略的日志 CSV —— 11 列、有表头
    timeIndex,rebuild,reusedFrom,runAge,est,avg,rMed,prevN,prevFact,prevAge,prevRcost
    rebuild == 1 即重建；runAge 是该步开始前持有的年龄

本脚本对两种格式都做间隔统计。格式 (B) 尤其关键：
它直接记录了 C++ 的每一次决策，是核验"周期 2 死循环"的一手证据。
"""
import sys, os, glob, statistics as st
from collections import Counter
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"


def is_online_csv(path):
    with open(path, errors="ignore") as f:
        h = f.readline()
    return h.startswith("timeIndex,rebuild")


def online_steps(path):
    """解析格式 (B)，返回 [(t, rebuild, runAge, est, avg, prevN, rMed), ...]"""
    out = []
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                out.append(dict(
                    t=int(float(q[idx["timeIndex"]])),
                    rb=int(float(q[idx["rebuild"]])),
                    rf=int(float(q[idx["reusedFrom"]])),
                    age=int(float(q[idx.get("runAge", 0)])),
                    est=float(q[idx.get("est", 0)]),
                    avg=float(q[idx.get("avg", 0)]),
                    rMed=float(q[idx.get("rMed", 0)]),
                    pN=float(q[idx.get("prevN", 0)]),
                ))
            except (ValueError, KeyError):
                pass
    return out


def frozen_steps(path):
    """解析格式 (A)，返回每个 timeIndex 是否重建。"""
    rr = P.rows(path)
    seen = {}
    for x in rr:
        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
            seen[int(x["timeIndex"])] = x
    return [(t, 1 if int(seen[t]["reusedFrom"]) < 0 else 0) for t in sorted(seen)]


def report(path):
    name = os.path.basename(path)
    try:
        if is_online_csv(path):
            rows = online_steps(path)
            if not rows: return None
            base = P.B0
            rb = [r["t"] for r in rows if r["rb"] == 1]
            n = len(rows)
            ages = [r["age"] for r in rows if r["t"] > base]
            fmt = "ONL"
        else:
            rows = frozen_steps(path)
            if not rows: return None
            base = P.B0
            rb = [t for t, r in rows if r == 1]
            n = len(rows)
            ages = []
            fmt = "PC"
    except Exception as e:
        print("     %-44s ★读取失败 %s" % (name, e)); return None

    post = [t for t in rb if t > base]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)]
    dist = dict(sorted(Counter(gaps).items()))
    med = "%.0f" % st.median(gaps) if gaps else "—"
    flag = ""
    if gaps:
        if st.median(gaps) <= 2:
            flag = "  ★★ 周期≤2 死循环"
        elif st.median(gaps) >= 0.8*n:
            flag = "  (几乎不重建)"
    extra = ""
    if fmt == "ONL" and ages:
        extra = " age中位=%.0f 最大age=%d" % (st.median(ages), max(ages))
    print("     %-44s [%s] 步=%-6d 重建=%-5d 预热后=%-5d 间隔中位=%-4s%s%s"
          % (name, fmt, n, len(rb), len(post), med, extra, flag))
    return dict(name=name, n=n, nrb=len(rb), post=len(post), gaps=dist,
                med=(st.median(gaps) if gaps else None))


print("=" * 122)
print("★★★ C++ 实测：在线策略的重建间隔核验")
print("=" * 122)

# ---- 在线策略的 (B) 格式 ----
onl = sorted(glob.glob(os.path.join(P2, "*onl*.csv")))
onl = [f for f in onl if is_online_csv(f)]
if onl:
    print("\n  ══ 在线策略（C++ 决策日志，格式 B）══")
    bycase = {}
    for f in onl:
        r = report(f)
        if r: bycase.setdefault(os.path.basename(f).split("_r")[0], []).append(r)
    print()
    for case, rs in sorted(bycase.items()):
        meds = [r["med"] for r in rs if r["med"] is not None]
        if meds:
            print("  ── %-22s 共 %d 轮，间隔中位: %s（中位数的中位 = %.0f）"
                  % (case, len(rs), [("%.0f" % m) for m in meds], st.median(meds)))
else:
    print("\n  ★ 未找到在线策略的 (B) 格式 CSV")

# ---- 固定周期扫描的 (A) 格式（抽样，确认解析无误）----
print("\n  ══ 固定周期扫描（格式 A，抽样核对）══")
sample = ["l15_pc_k5_r1.csv", "l20_pc_k5_r1.csv", "fl30_pc_k5_r1.csv",
          "cov2_l15_pc_k13_r1.csv", "sth_pc_k13_r1.csv"]
for nm in sample:
    p = os.path.join(P2, nm)
    if os.path.exists(p):
        report(p)
    else:
        print("     %-44s （不存在，跳过）" % nm)

# ---- 关键：l15 若没有 C++ 在线日志，明确说明 ----
print("\n" + "=" * 122)
have_l15 = any("l15" in f for f in onl)
print("  l15 是否有 C++ 在线日志：%s" % ("有" if have_l15 else "★ 没有"))
if not have_l15:
    print("  ⇒ l15 的周期 2 死循环目前只有 Python 模型（pbrlib.sim_online）的证据。")
    print("    该模型与 C++ 的等价性此前已在 l20 上用 245 次决策、0 处不一致验证过")
    print("    （a2_replay.py），但 l15 本身尚未在 C++ 上实跑。")
    print("    若要拿 l15 作为论文素材，必须补一次 l15 的 C++ 在线运行。")
print("=" * 122)
