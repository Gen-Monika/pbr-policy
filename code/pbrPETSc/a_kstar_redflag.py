#!/usr/bin/env python3
"""
★★★ 红旗核查：为什么 6/7 配置的 K* 都变成 4？

═══ 疑点 ═══
shape 口径下，fx/l15/l20/fine/x3/fl30 的最优固定周期 K* 全等于 4，
而历史结论分别是 fx=3、l15/l20/fine/x3=5。

两种可能：
 (a) 真实：成本曲线在 K=4 附近本来就平坦，K* 对填充口径不敏感
 (b) 假象：shape 的 G(a) 形状让曲线在 K=4 处必然出现极小
     （例如 G(a) 的形状恰好使 amortized cost 在 4 步附近最小）

判据：
 · 若 K=3,4,5 的成本差异 <1% ⇒ 曲线平坦，(a) 成立，K* 的"漂移"
   无实质意义，任何一处微扰都会挪动 argmin
 · 若差异明显且随 amax 变化 ⇒ (b) 可疑

同时检查：K* 是否随 amax_data 变化（若 K*=4 是数据边界造成的，
则减小 amax 会逼出不同的 K*）。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

SPEC = {
    "fx":   (344,  [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])]),
    "l15":  (344,  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
                    ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])]),
    "l20":  (344,  [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])]),
    "fine": (720,  [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
                    ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])]),
    "x3":   (1231, [("x3", "x3run", [1,2,3,5,8], [1,2]),
                    ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])]),
    "fl30": (720,  [("fl30", "fl30run", [1,3,5], [1,2]),
                    ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])]),
    "sth":  (5866, [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
                    ("cov2_sth", "cov2_sth", [20,30], [1,2,3])]),
}


def load(tag, policy="B"):
    base_n = SPEC[tag][0]
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                if policy == "B" and len(steps) < base_n: continue
                Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
                for i in range(n):
                    x = steps[i]; rf = int(x["reusedFrom"])
                    cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
                for x in rr:
                    if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                        rv.append(x["tPCSetup"]/x["tIter"])
                rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
                ns = max(ns, len(steps))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 132)
print("★★★ 1. K=3/4/5 的成本差异 —— 曲线是否平坦？")
print("=" * 132)
print("  %-6s %12s %12s %12s %12s   %s"
      % ("配置", "K=3 (相对K*)", "K=4", "K=5", "K=3..5 极差", "判定"))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load(tag)
    if cfg is None: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    base = fx[kb]
    vals = [fx[k] for k in (3, 4, 5) if k in fx]
    spread = 100*(max(vals)/min(vals) - 1)
    verdict = "曲线平坦（K* 无实质意义）" if spread < 1.0 else \
              ("中等" if spread < 5 else "曲线有明显极小")
    row = []
    for k in (3, 4, 5):
        row.append("%11.2f%%" % (100*(fx[k]/base-1)) if k in fx else "%12s" % "—")
    print("  %-6s %s %s %s %12.2f%%   %s (K*=%d)" % (tag, row[0], row[1], row[2], spread, verdict, kb))

print()
print("=" * 132)
print("★★★ 2. K* 是否随 amax（数据覆盖上限）变化？")
print("=" * 132)
print("  若 K*=4 只在 amax 大时出现，而 amax 小的时候 K* 不同，")
print("  说明 K* 受「数据里出现了哪些年龄」支配 —— 那是不可接受的口径依赖。")
print()
print("  %-6s" % "配置" + "".join("%12s" % ("amax≤%d" % a) for a in (2, 3, 4, 5, 7, 10, 15, 29)))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load(tag)
    if cfg is None: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    line = ""
    for cap in (2, 3, 4, 5, 7, 10, 15, 29):
        # 只保留 age ≤ cap 的格子，T 不变
        tab = {k: v for k, v in cfg["tab"].items() if k[1] <= cap}
        if not tab: line += "%12s" % "—"; continue
        env = P.Env(tab, mode="real", interp="shape")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: line += "%12s" % "—"; continue
        fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
        kb = min(fx, key=fx.get)
        line += "%11s" % ("K*=%d" % kb)
    print("  %-6s%s" % (tag, line))

print()
print("=" * 132)
print("★★★ 3. 换个填充口径，K* 是否也全部是 4？")
print("=" * 132)
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load(tag)
    if cfg is None: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    out = []
    for ip in ("shape", "linear", "step", "curve"):
        env = P.Env(cfg["tab"], mode="real", interp=ip)
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: continue
        fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
        kb = min(fx, key=fx.get)
        out.append("%s=K%d" % (ip, kb))
    print("  %-6s %s" % (tag, "  ".join(out)))
print()
print("  若四个口径的 K* 一致 ⇒ K* 稳健，不依赖填充方式")
print("  若差异大 ⇒ K* 是填充口径的产物，不能作为论文的主结论")
print("=" * 132)
