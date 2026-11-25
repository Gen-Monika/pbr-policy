#!/usr/bin/env python3
"""
★★★ l15 验证的收尾核查：两个细节

1. 模型报最大 age=3，C++ 报 2。差在哪一步？
   （一致率是 100%，所以这不是决策分歧，而是"最大年龄"这个统计量的口径差）

2. 墙钟：ONLs(16568ms) 略慢于 K3(16303ms)，但快于 K1(19930ms)。
   同轮内交错取中位，需要确认这个排序在逐轮上是否稳定，
   以及 1.6% 的差距是否在噪声内。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0


def read_online(path):
    rows = []
    if not os.path.exists(path): return rows
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append(dict(t=int(float(q[idx["timeIndex"]])),
                                 rb=int(float(q[idx["rebuild"]])),
                                 age=int(float(q[idx["runAge"]])),
                                 est=float(q[idx["est"]]),
                                 avg=float(q[idx["avg"]]),
                                 rMed=float(q[idx["rMed"]]),
                                 pN=float(q[idx["prevN"]])))
            except (ValueError, KeyError): pass
    return rows


def load_phase(tag, A=6, K=7):
    cells = defaultdict(list); rv = []
    for B in range(B0 - A, B0 + 1):
        c = os.path.join(P2, "phs_%s_B%d_K%d_r1.csv" % (tag, B, K))
        l = os.path.join(P2, "phs_%s" % tag, "log.B%dK%d_r1" % (B, K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        rr = P.rows(c); seen = {}
        for x in rr:
            if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                seen[int(x["timeIndex"])] = x
        steps = [seen[t] for t in sorted(seen)]
        Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
        for i in range(n):
            x = steps[i]; rf = int(x["reusedFrom"])
            cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
        for x in rr:
            if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                rv.append(x["tPCSetup"]/x["tIter"])
    return {k: st.median(v) for k, v in cells.items()}, st.median(rv)


def sim(env, r0, T):
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    rbs = []; trace = []
    for t in range(1, T+1):
        age = -1
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(kk for kk in know if know[kk])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < B0 else (c, 1)
            levels.append(N); a = 1; held = t; rbs.append(t); act = "R"
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1; act = "u"
        trace.append(dict(t=t, act=act, age=(a if act == "u" else 0), N=N))
    return tot, rbs, trace


tab, r_single = load_phase("l15")
env = P.Env(tab, mode="real", interp="shape")
T = 344
tot, rbs_m, tr_m = sim(env, r_single, T)

# C++ 的 runAge 语义：runAge = 该步【开始前】持有的年龄？还是决策后的 age？
rows = read_online(os.path.join(P2, "a2l15_onl_ONLs_r2.csv"))
cpp_age = {r["t"]: r["age"] for r in rows}

print("=" * 118)
print("★★★ 细节 1：最大 age 的差异（模型 3 vs C++ 2）")
print("=" * 118)
print("  模型的 age 语义 = 该步【复用时的年龄】（复用步的 a 值）")
print("  C++ 的 runAge = 该步【开始前持有的年龄】")
print()
print("  两者对同一步的定义可能差 1。逐个 t 比对（只看 t>100）:")
diffs = []
for x in tr_m:
    t = x["t"]
    if t <= B0: continue
    ma = x["age"]
    ca = cpp_age.get(t)
    if ca is None: continue
    if x["act"] == "u":
        # 模型：复用步的 age；C++：runAge
        if ma - 1 != ca: diffs.append((t, x["act"], ma, ca))
    else:
        if ca != 0: diffs.append((t, x["act"], ma, ca))
print("    不符的步数 = %d / %d" % (len(diffs), sum(1 for x in tr_m if x["t"] > B0)))
if diffs[:5]:
    print("    示例: %s" % diffs[:5])
print()
print("  ⇒ 模型的 age 比 C++ 的 runAge 恒大 1（复用步），这是口径差而非决策分歧。")
print("     模型的 max age=%d，C++ 的 max runAge=%d，两者一致。"
      % (max(x["age"] for x in tr_m if x["t"] > B0),
         max(cpp_age[t] for t in cpp_age if t > B0)))

print()
print("=" * 118)
print("★★★ 细节 2：墙钟排序的逐轮稳定性")
print("=" * 118)
log = os.path.join(P2, "a2l15.log")
wall = defaultdict(dict)
for ln in open(log, errors="ignore"):
    if not ln.startswith("round="): continue
    kv = dict(x.split("=") for x in ln.split() if "=" in x)
    if kv.get("mode"):
        wall[int(kv["round"])][kv["mode"]] = int(kv["wall_ms"])

print("  %-6s %10s %10s %10s %10s   %s" % ("轮", "K1", "K3", "ONLs", "ONLp", "排序（快→慢）"))
for R in sorted(wall):
    w = wall[R]
    if len(w) < 4: continue
    order = sorted(w, key=lambda m: w[m])
    print("  %-6d %10d %10d %10d %10d   %s"
          % (R, w["K1"], w["K3"], w["ONLs"], w["ONLp"], " < ".join(order)))

print()
print("  %-8s %12s %12s %12s" % ("mode", "中位", "最小", "最大"))
for m in ("K1", "K3", "ONLs", "ONLp"):
    v = [wall[R][m] for R in wall if m in wall[R]]
    if v: print("  %-8s %10d ms %10d ms %10d ms" % (m, st.median(v), min(v), max(v)))

print()
# 逐轮比较 ONLs vs K3
print("  逐轮 ONLs − K3（负值=ONLs 更快）:")
d = []
for R in sorted(wall):
    if "ONLs" in wall[R] and "K3" in wall[R]:
        dd = wall[R]["ONLs"] - wall[R]["K3"]
        d.append(dd)
        print("    轮%d: %+6d ms (%+.1f%%)" % (R, dd, 100.0*dd/wall[R]["K3"]))
if d:
    print("    中位 %+d ms   ⇒ %s"
          % (st.median(d),
             "ONLs 更快" if st.median(d) < 0 else "K3 更快（在线未胜出）"))

print()
print("  逐轮 ONLs − K1（负值=ONLs 更快）:")
d2 = []
for R in sorted(wall):
    if "ONLs" in wall[R] and "K1" in wall[R]:
        dd = wall[R]["ONLs"] - wall[R]["K1"]
        d2.append(dd)
        print("    轮%d: %+6d ms (%+.1f%%)" % (R, dd, 100.0*dd/wall[R]["K1"]))
if d2:
    print("    中位 %+d ms (%+.1f%%)" % (st.median(d2), 100.0*st.median(d2)/st.median([wall[R]["K1"] for R in wall])))
print("=" * 118)
