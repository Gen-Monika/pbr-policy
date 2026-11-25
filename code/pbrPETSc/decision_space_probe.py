#!/usr/bin/env python3
"""
★★★ 判断实验：决策空间到底有多大，由什么决定？

═══ 问题的由来 ═══
Stage D 发现：七配置上 oracle 与 K=1 的差距只有 0.79–2.48 pp。
即【即使完美预测未来】，也只能比"每步重建"好 2.5%。
在这个尺度上所有策略都挤在一起，无法区分。

⇒ 那么：决策空间是【选算例选出来的】还是【结构上就窄】？

═══ 决策空间的解析形式 ═══
设基线的每步迭代数 N₀，劣化增量 ΔN(a)，每步分解次数 f，r=r_setup/r_iter。

  每步重建 (K=1) 的成本      = f·r + N₀
  最优周期 K 的每步分摊成本  = (f·r + Σ_{a=1}^{K} N₀+ΔN(a-1)) / K

相对节省 = 1 − min_K [...] / (f·r + N₀)

关键无量纲量：
  ρ := f·r / N₀          （重建成本相对于基线迭代数的倍数）
  g := ΔN(N₀ 的劣化速度)  （每步劣化）

当 ρ → 0（重建便宜）⇒ 每步重建最优 ⇒ 决策空间 → 0
当 ρ → ∞（重建贵）  ⇒ 一直复用最优 ⇒ 决策空间 → 0
∴ 决策空间在 ρ 的中间区间最大。

本脚本：
 (1) 从实测数据算出每个配置的 ρ、g、以及实际决策空间
 (2) 用【实测的劣化曲线形状】做外推，预测"若 r 提高到某值，决策空间能到多大"
 (3) 给出"要多大决策空间才能撑起论文"的判据
"""
import os, re, statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur)); cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def build(tag, logdir, rounds, Ks):
    cells = defaultdict(list); rv = []; fac = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c); seen = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                    seen[int(d["timeIndex"])] = d
            rr = [seen[t] for t in sorted(seen)]
            Ns = per_step_N(l); n = min(len(rr), len(Ns))
            if ns is None or n > ns: ns = n
            for i in range(n):
                d = rr[i]; t = i + 1
                rf = int(d["reusedFrom"])
                cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
            allr = rows(c)
            for d in allr:
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
            rbs = set(int(d["timeIndex"]) for d in allr if int(d["reused"]) == 0)
            nrs = sum(1 for d in allr if int(d["reused"]) == 0)
            if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac) if fac else 1.0, nsteps=ns)


def make_N(tab):
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)
    return curve, amx


def sim_fixed_cost(curve, amx, r0, K, b0=100, T=344):
    """用【纯劣化曲线】算周期 K 的每步平均成本（与 t 无关的稳态模型）"""
    tot = 0.0
    a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            tot += r0 + curve[0]; a = 1
        else:
            tot += curve.get(a, curve[amx]); a += 1
    npost = T - b0
    return tot/max(1, T)


def decision_space(curve, amx, r0, T=344, b0=100):
    """最优周期相对 K=1 的相对节省（决策空间）"""
    c1 = sim_fixed_cost(curve, amx, r0, 1, b0, T)
    best = min(sim_fixed_cost(curve, amx, r0, K, b0, T)
               for K in (1,2,3,4,5,6,8,10,13,20,30,50))
    return (1.0 - best/c1), c1


CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8]),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8]),
    ("fl30", "fl30run", [1,2],             [1,3,5]),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8]),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13]),
]

print("=" * 110)
print("★★★ 判断实验 A：决策空间的实测值与解析分解")
print("=" * 110)
print("""
ρ := f·r / N₀   （重建总成本 / 基线每步迭代数）
    ρ ≪ 1 ⇒ 重建便宜 ⇒ 每步重建 ⇒ 无决策空间
    ρ ≫ 1 ⇒ 重建贵   ⇒ 一直复用 ⇒ 无决策空间
∴ 决策空间在 ρ 中间最大
""")
print("  %-7s %8s %6s %8s %8s %9s %9s %10s" %
      ("配置","r_eff","f","N₀","ΔN(1)","ΔN(3)","ρ","决策空间"))

data = []
for tag, logdir, rounds, Ks in CONFIGS:
    cfg = build(tag, logdir, rounds, Ks)
    if cfg is None: continue
    curve, amx = make_N(cfg["tab"])
    N0 = curve[0]
    r0 = cfg["r1"]*cfg["fac"]
    rho = r0/N0
    ds, c1 = decision_space(curve, amx, r0, cfg["nsteps"])
    g1 = curve.get(1, N0) - N0
    g3 = curve.get(3, curve[amx]) - N0
    print("  %-7s %8.1f %6.2f %8.1f %8.1f %9.1f %9.1f %9.2f%%"
          % (tag, r0, cfg["fac"], N0, g1, g3, rho, 100*ds))
    data.append(dict(tag=tag, r=r0, f=cfg["fac"], N0=N0, rho=rho, ds=ds,
                     curve=curve, amx=amx, T=cfg["nsteps"]))

print()
print("  ★ 观测：现有配置的 ρ 覆盖 %.0f–%.0f（两个数量级），但决策空间全部 <3%%"
      % (min(d["rho"] for d in data), max(d["rho"] for d in data)))
print("     ⇒ 说明【不是 ρ 取值范围的问题】，而是曲线形状的问题（见 B）。")

print("\n" + "=" * 110)
print("★★★ 判断实验 B：决策空间的上限由什么决定？（解析）")
print("=" * 110)
print("""
把劣化曲线理想化为 N(a) = N₀ + g·a（线性劣化）。
则周期 K 的每步平均成本：
    C(K) = (f·r + N₀ + Σ_{a=0}^{K-1}(N₀ + g·a)) / K
         = (f·r + N₀)/K + N₀ + g·(K-1)/2
对 K 求极值 ⇒ K* = sqrt( 2(f·r + N₀) / g )
最优相对节省 = 1 − C(K*)/C(1)，其中 C(1) = f·r + N₀

放大 g（劣化更快）与放大 f·r（重建更贵）都能增大决策空间。
""")
print("  --- 用各配置实测的 g 与 f·r 外推：把 f·r 放大多少倍，决策空间到多少 ---")
print("  %-7s %10s %10s %10s %10s %10s %10s" %
      ("配置","实测","×2","×5","×10","×20","×50"))
import math
for d in data:
    curve, amx = d["curve"], d["amx"]
    # 用前几个年龄估计斜率 g（线性拟合）
    ks = [a for a in sorted(curve) if a <= 5]
    if len(ks) >= 2:
        xs = list(ks); ys = [curve[a]-curve[0] for a in ks]
        mx = st.mean(xs); my = st.mean(ys)
        g = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/max(1e-9, sum((x-mx)**2 for x in xs))
    else:
        g = 1.0
    g = max(0.05, g)
    row = []
    for mult in (1, 2, 5, 10, 20, 50):
        ds, _ = decision_space(curve, amx, d["r"]*mult, d["T"])
        row.append(100*ds)
    # 实测（无外推）
    ds_real, _ = decision_space(curve, amx, d["r"], d["T"])
    print("  %-7s %9.2f%% %9.2f%% %9.2f%% %9.2f%% %9.2f%% %9.2f%%"
          % (d["tag"], 100*ds_real, row[1], row[2], row[3], row[4], row[5]))

print("\n" + "=" * 110)
print("★★★ 判断实验 C：需要多大的决策空间，才能撑起一篇论文？")
print("=" * 110)
print("""
判据来自本项目已实测的【测量噪声底】：
  - 离线代价模型口径：离散度约 1–3 pp（来自组间漂移）
  - 实机墙钟口径：离散度 1.4–22 pp（A2/A2B 实测）
要在论文里主张"方法 A 显著优于方法 B"，需要
  决策空间 ≥ 3× 噪声底，否则差异淹没在噪声里。

⇒ 离线：决策空间需 ≥ 5–9 pp
⇒ 实机：决策空间需 ≥ 5–70 pp（取决于配置）
""")
for d in data:
    ds_real, _ = decision_space(d["curve"], d["amx"], d["r"], d["T"])
    verdict = "可判" if ds_real*100 >= 5 else "不可判"
    print("  %-7s 决策空间 %6.2f%%  ⇒ 离线%s" % (d["tag"], 100*ds_real, verdict))
