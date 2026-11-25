#!/usr/bin/env python3
"""
★ A2 一致性回放测试：C++ 在线策略是否是离线 sim_online（P0/T0）的忠实移植

做法：C++ 每步记录 (timeIndex, rebuild, est, avg, rMed, prevN, prevFact)。
      prevN / prevFact / rMed 是【环境的响应】（实测迭代数、分解次数、r），
      本脚本独立地按离线 online_holdout_v2.sim_online 的逻辑，
      用同样的环境响应逐步重放，得出自己的决策，再与 C++ 的决策逐步比对。

若移植忠实 ⇒ 每一步的 rebuild 标志完全相同，est/avg 数值一致（浮点误差内）。

用法： python a2_replay.py <onl.csv> [solve|step] [last|trend] [b0]
"""
import sys, statistics as st
from collections import defaultdict

path = sys.argv[1]
RCOST = sys.argv[2] if len(sys.argv) > 2 else "solve"
LVL = sys.argv[3] if len(sys.argv) > 3 else "last"
B0 = int(sys.argv[4]) if len(sys.argv) > 4 else 100

rows = []
for ln in open(path):
    q = ln.strip().split(",")
    if q[0] == "timeIndex" or len(q) != 11:
        continue
    rows.append(dict(t=int(q[0]), rb=int(q[1]), est=float(q[4]), avg=float(q[5]),
                     r=float(q[6]), pN=int(q[7]), pF=int(q[8])))

levels, know = [], defaultdict(list)
acc, accn, tot, ndone = 0.0, 0, 0.0, 0
held, run_age = -1, 0
mism, cmp_n, max_de, max_da = [], 0, 0.0, 0.0

for k, R in enumerate(rows):
    t = R["t"]
    # ---- fold previous step with the ENVIRONMENT's response ----
    if k > 0:
        N = R["pN"]
        if run_age == 0:
            rc = R["r"]*R["pF"] if RCOST == "step" else R["r"]
            c = rc + N; tot += c; levels.append(N)
            if rows[k-1]["t"] < B0: acc, accn = 0.0, 0
            else: acc, accn = c, 1
        else:
            tot += N
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[run_age].append(N - bm)
            acc += N; accn += 1
        ndone += 1
    # ---- decide (offline sim_online, P0 / T0) ----
    rebuild, est, avg = True, 0.0, 0.0
    if t >= B0 and held >= 0 and levels:
        a = t - held
        lvl = levels[-1]
        if LVL == "trend" and len(levels) >= 2:
            lvl = levels[-1] + (levels[-1] - levels[-2])
        avg = acc/accn if accn else tot/max(1, ndone)
        if a in know and know[a]:
            delta = st.median(know[a])
        elif know:
            ks = sorted(x for x in know if know[x])
            if len(ks) >= 2:
                a2, a1 = ks[-1], ks[-2]
                d2, d1 = st.median(know[a2]), st.median(know[a1])
                delta = d2 + (d2 - d1)/max(1e-9, a2 - a1)*(a - a2)
            else:
                delta = st.median(know[ks[-1]])
        else:
            delta = 0.0
        est = lvl + max(0.0, delta)
        rebuild = est > avg
        cmp_n += 1
        max_de = max(max_de, abs(est - R["est"]))
        max_da = max(max_da, abs(avg - R["avg"]))
    if int(rebuild) != R["rb"]:
        mism.append((t, int(rebuild), R["rb"], round(est, 3), R["est"], round(avg, 3), R["avg"]))
    if rebuild:
        held, run_age = t, 0
    else:
        run_age = t - held

print("回放 %s   RCOST=%s LVL=%s b0=%d" % (path, RCOST, LVL, B0))
print("  步数 %d，其中预热后可比较的决策 %d 个" % (len(rows), cmp_n))
print("  决策不一致的步数: %d" % len(mism))
for m in mism[:10]:
    print("     t=%d  py=%d cpp=%d  est py=%s cpp=%s  avg py=%s cpp=%s" % m)
print("  max|est 差| = %.3g   max|avg 差| = %.3g" % (max_de, max_da))
print("  ⇒ %s" % ("C++ 是离线策略的忠实移植 ✓" if not mism and max_de < 1e-3 and max_da < 1e-3
                  else "存在不一致 ✗"))
nrb = sum(R["rb"] for R in rows if R["t"] >= B0)
print("  预热后重建步数 = %d / %d" % (nrb, sum(1 for R in rows if R["t"] >= B0)))
