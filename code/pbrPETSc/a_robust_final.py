#!/usr/bin/env python3
"""
★★★ 定稿核验：什么结论稳健、什么不稳健

═══ 背景 ═══
shape（形状迁移）口径下，6/7 配置的 K* 都变成 4，而历史（linear）是 3 或 5。
这需要判断：是"曲线本来就平坦、argmin 易漂"，还是"shape 把曲线抹平了"。

═══ 三个检验 ═══
A. K* 的平台宽度：成本在 K* 的 ±1% 内覆盖哪些 K？
   · 平台宽（如 {3,4,5}）⇒ argmin 不稳，K* 不宜作主结论
   · 平台窄（只有 K*）  ⇒ K* 是稳健的物理量

B. K* 与 r_eff 的关系：若 K* 正比于 sqrt(r_eff)，说明它由物理决定；
   若 K* 与 r_eff 无关（全是 4），说明 shape 把它规整化了。

C. 在线优势是否跨口径稳健：
   在线 − K* 与 在线 − oracle 在四种填充下的变化幅度。
   这才是论文要主张的量。
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
ORDER = ("fx", "l15", "l20", "fine", "x3", "fl30", "sth")


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


CFG = {}
for tag in ORDER:
    c = load(tag)
    if c: CFG[tag] = c

CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 130)
print("★★★ A. K* 的平台宽度（成本在 K* 的 +1% 内的 K 集合）")
print("=" * 130)
print("  %-6s %10s %8s %14s %14s   %s"
      % ("配置", "r_eff", "K*", "≤K*+1% 的 K", "平台宽度", "K* 是否可信"))
for tag in ORDER:
    cfg = CFG.get(tag)
    if not cfg: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    plateau = [k for k in Ks if fx[k] <= fx[kb]*1.01]
    w = max(plateau) - min(plateau) + 1 if plateau else 0
    verdict = "平台宽 ⇒ argmin 不稳" if w >= 3 else "平台窄 ⇒ 可信"
    print("  %-6s %10.1f %8d %14s %14d   %s"
          % (tag, r0, kb, "%d..%d" % (min(plateau), max(plateau)), w, verdict))

print()
print("=" * 130)
print("★★★ B. K* 与 r_eff 的关系（物理还是规整化？）")
print("=" * 130)
rows = []
for tag in ORDER:
    cfg = CFG.get(tag)
    if not cfg: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    # 从曲线算小年龄的每步增长 g = (curve(2)-curve(0))/2
    c0 = env.curve.get(0, 1.0)
    c2 = env.curve.get(2, c0)
    g = max(1e-6, (c2 - c0)/2.0)
    pred = (2.0*r0/max(1e-6, g))**0.5
    rows.append((tag, r0, g, kb, pred))
    print("  %-6s r_eff=%8.1f  N(t,0)≈%8.1f  g(dN/da)≈%7.2f  K*=%-3d  sqrt(2r/g)=%6.2f"
          % (tag, r0, c0, g, kb, pred))
if rows:
    ks = [r[3] for r in rows]
    print()
    print("  K* 实际取值：%s" % sorted(set(ks)))
    print("  ⇒ 若 K* 全相同而 sqrt(2r/g) 分布很宽，说明 K* 被 shape 的 G(a) 形状锁住。")

print()
print("=" * 130)
print("★★★ C. 在线优势的跨口径稳健性（这是论文要主张的量）")
print("=" * 130)
IP = ("shape", "linear", "step", "curve")
print("  %-6s" % "配置" + "".join("%26s" % ("%s: 在线−K* / 在线−orc" % ip) for ip in IP))
summ = {ip: [] for ip in IP}
for tag in ORDER:
    cfg = CFG.get(tag)
    if not cfg: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    line = ""
    for ip in IP:
        env = P.Env(cfg["tab"], mode="real", interp=ip)
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError:
            line += "%26s" % "★自检失败"; continue
        kb = info["Kbest"]
        gk = 100*(info["online"]/orc-1) - 100*(info["fixed"][kb]/orc-1)
        go = 100*(info["online"]/orc-1)
        summ[ip].append((tag, gk, go))
        line += "%26s" % ("%+.2f / %+.2f" % (gk, go))
    print("  %-6s%s" % (tag, line))

print()
print("  %-10s %16s %16s   %s" % ("填充口径", "在线−K* 中位", "在线−orc 中位", "样本数"))
for ip in IP:
    gs = [x[1] for x in summ[ip]]; os_ = [x[2] for x in summ[ip]]
    if not gs: continue
    print("  %-10s %+15.2f pp %+15.2f pp   %d" % (ip, st.median(gs), st.median(os_), len(gs)))
print()
gs = [x[1] for x in summ["shape"]]
print("  ★ shape 下 在线优于 K* 的配置：%s"
      % [t for t, g, _ in summ["shape"] if g < 0])
print("  ★ 跨四种口径都满足「在线 − K* ≤ +2 pp」的配置：%s"
      % [t for t in ORDER
         if all(any(y[0] == t and y[1] <= 2.0 for y in summ[ip]) for ip in IP
                if any(y[0] == t for y in summ[ip]))])
print("=" * 130)
