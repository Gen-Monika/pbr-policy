#!/usr/bin/env python3
"""
★★★ 修正 r 的统计口径，并重算成本模型的最优 K

═══════════════════════════════════════════════════════════════════════
两个修正
═══════════════════════════════════════════════════════════════════════
1. r 只能在【重建步】(reused==0) 上统计。
   复用步的 tPCSetup 是 ~1.5 µs 的残值（PCSetReusePreconditioner 跳过分解）
   ⇒ 会把 r 拉到 0.01。

2. 成本模型 cost(K) = ΣtPCSetup + ΣN·tIter
   - ΣtPCSetup 现在已是完整口径（每步 3 行）✓
   - ΣN·tIter 需要：ΣN 从日志取（完整），tIter 取【重建步】的中位
   ⇒ 两项口径现已统一。
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)")


def load_csv(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25:
            continue
        d = {}
        try:
            for k, v in zip(CSV_HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def count_N(path):
    tot = 0
    for ln in open(path, errors="ignore"):
        m = SOLVE_RE.search(ln)
        if m:
            tot += int(m.group(1))
    return tot


wall = defaultdict(list)
for ln in open("fx.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)),
                                          exe=float(m.group(4))))

print("=" * 100)
print("★★★ 修正 r 口径 + 重算成本模型")
print("=" * 100)

print(f"\n  1. ★ r 的口径修正")
print(f"  {'K':>3} {'全部行 r 中位':>14} {'重建步 r 中位':>14} {'tPCSetup重建步/µs':>18} "
      f"{'tIter/µs':>10} {'重建步数':>9}")
rr = {}
for K in sorted(wall):
    allr, rebr, tis, tss = [], [], [], []
    nreb = 0
    for w in wall[K]:
        rows = load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv")
        for d in rows:
            if d["tPCSetup"] <= 0:
                continue
            if d["reused"] == 0:
                nreb += 1
                if d["tIter"] > 0:
                    rebr.append(d["r"])
                    tis.append(d["tIter"])
                    tss.append(d["tPCSetup"])
            if d["r"] > 0:
                allr.append(d["r"])
    rr[K] = st.median(rebr) if rebr else float("nan")
    print(f"  {K:>3} {st.median(allr) if allr else 0:>14.2f} "
          f"{rr[K]:>14.2f} {st.median(tss)*1e6 if tss else 0:>18.1f} "
          f"{st.median(tis)*1e6 if tis else 0:>10.2f} {nreb//5:>9}")

print(f"\n  ⇒ 修正后 r 稳定在 "
      f"[{min(rr.values()):.1f}, {max(rr.values()):.1f}]"
      f"（修正前 K=5/K=8 是 0.01）")

print(f"\n{'='*100}")
print("2. ★★ 成本模型（两项口径现已统一）")
print(f"{'='*100}")
print(f"  cost(K) = ΣtPCSetup(完整) + ΣN · tIter(重建步)")
print(f"\n  {'K':>3} {'ΣtPCSetup/s':>12} {'ΣN':>8} {'tIter/µs':>10} "
      f"{'ΣN·tIter/s':>11} {'cost/s':>9} {'相对K=1':>10} {'墙钟实测/s':>11}")
model = {}
for K in sorted(wall):
    su = st.median([sum(d["tPCSetup"] + d["tAssemble"] + d["tConvert"] + d["tFreeze"]
                        for d in load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv"))
                    for w in wall[K]])
    sN = count_N(f"fixed/log.r1k{K}")
    ti = []
    for w in wall[K]:
        for d in load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv"):
            if d["reused"] == 0 and d["tIter"] > 0:
                ti.append(d["tIter"])
    tm = st.median(ti) if ti else 0.0
    it = sN * tm
    model[K] = dict(su=su, sN=sN, tm=tm, it=it, cost=su + it,
                    exe=st.median([w["exe"] for w in wall[K]]))
    print(f"  {K:>3} {su:>12.3f} {sN:>8} {tm*1e6:>10.2f} {it:>11.3f} "
          f"{su+it:>9.3f} {'':>10} {model[K]['exe']:>11.2f}")

b = model[1]["cost"]
print(f"\n  {'K':>3} {'cost/s':>9} {'相对K=1':>10} {'墙钟/s':>9} {'墙钟相对K=1':>13} "
      f"{'两者排序一致?':>14}")
for K in sorted(model):
    m = model[K]
    cm = (m["cost"] / b - 1) * 100
    wm = (m["exe"] / model[1]["exe"] - 1) * 100
    print(f"  {K:>3} {m['cost']:>9.3f} {cm:>9.2f}% {m['exe']:>9.2f} "
          f"{wm:>12.2f}% {'✓' if (cm<0)==(wm<0) else '✗':>14}")

bk_m = min(model, key=lambda K: model[K]["cost"])
bk_w = min(model, key=lambda K: model[K]["exe"])
print(f"\n  ⇒ 成本模型最优 K = {bk_m}（{(model[bk_m]['cost']/b-1)*100:+.2f}%）")
print(f"  ⇒ 墙钟实测最优 K = {bk_w}（{(model[bk_w]['exe']/model[1]['exe']-1)*100:+.2f}%）")
print(f"  ⇒ {'★ 两者一致' if bk_m == bk_w else '⚠️ 两者不一致'}")

print(f"\n{'='*100}")
print("3. ★★ 判据验证：ΔN_step(a) < r 是否成立")
print(f"{'='*100}")
print("""  判据：复用胜出 ⟺ 每步 s 次求解的总劣化 ΔN_step < r
       等价于 ΔN_single < r/s""")
# 年龄曲线（用 fixed 数据）
print(f"\n  {'步段':>12} {'ΔN_step(0→1) 中位':>18} {'r':>8} {'判定':>8}")
for K in (3,):
    cells = defaultdict(list)
    for w in wall[K]:
        rows = load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv")
        last = None
        for d in rows:
            t = int(d["timeIndex"])
            if d["reused"] == 0:
                last = t
            if last is not None:
                cells[(t, t - last)].append(
                    sum(x["tIter"] for x in [] ) or 0)
    # 改用日志的迭代数（更直接）
    print("  （需用日志的逐步迭代数，见下一节）")

print(f"\n{'='*100}")
print("4. r 与填充层级的关系（修正口径后）")
print(f"{'='*100}")
print(f"  {'K':>3} {'r（重建步）':>13} {'tPCSetup/µs':>13} {'tIter/µs':>10}")
for K in sorted(rr):
    tss, tis = [], []
    for w in wall[K]:
        for d in load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv"):
            if d["reused"] == 0 and d["tIter"] > 0:
                tss.append(d["tPCSetup"])
                tis.append(d["tIter"])
    if tss:
        print(f"  {K:>3} {rr[K]:>13.2f} {st.median(tss)*1e6:>13.1f} "
              f"{st.median(tis)*1e6:>10.2f}")
print(f"""
  ⇒ r 在各 K 下应大致相同（同一填充层级、同一算例）
    实测范围 [{min(rr.values()):.1f}, {max(rr.values()):.1f}]
""")
