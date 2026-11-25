#!/usr/bin/env python3
"""
★★★ 用【实测数据】重算头条结论：在线策略 vs 事后最优固定周期。

动机：论文 §7.3 的 ≤7.67% 是用【模型表】算的（虽有实测裁判背书，
      但仍是"模型 + 一次裁判"）。本脚本把它变成【纯实测】：
        cost = iters(实测) + ρ · rbsteps(实测)
      · iters    = 该运行的 log 里逐 Time 块求和（每步 s 次求解之和）
      · rbsteps  = 该运行的 pc CSV 中 reusedFrom < 0 的步数
      · ρ        = 区间 [r1, s·r1]（只用于把两者折算到同一单位）

★ 可比性前提（已核对）：
   · 同配置的在线运行与固定周期运行【步数完全相同】（344/720/1231/5866）
   · 时间步序列在 6/7 配置上逐位相同；x3 与 sth 仅在中途出现 1e-6 量级的
     浮点末位差（x3 第 823 步、sth 第 494 步），不改步数、不改迭代数量级

★★★ 口径约束（极易出错，必须遵守）：
   C++ 的在线实跑有两个记账口径：
     ONLs（RCOST=solve）：一次重建按 rMed 记账 ⇒ 对应 ρ = r1
     ONLp（RCOST=step） ：一次重建按 rMed·stepFact 记账 ⇒ 对应 ρ = s·r1
   ⇒ 【必须口径配对】：ONLs 只与 ρ=r1 下的最优比；ONLp 只与 ρ=s·r1 下的最优比。
   ✗ 错误做法（会把 gap 从 ~4% 放大到 ~19%）：拿 ONLs 去比 ρ=s·r1 下的最优固定周期。
     原因：ONLs 的决策是在 r1 口径下做的，而 s·r1 下的最优是"每 K 步重建一次"以外的
     更长周期，两者不在同一口径上。

★ 输出去重：每配置给出（在线、各固定 K）的实测 cost，
  并报"在线相对实测最优固定 K*"的差距区间。
"""
import re, os, sys, statistics as st

P = "/root/autodl-tmp/PBR"
TRE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
NRE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

# 配置 → (在线 log 模板, 在线 pc 前缀, 固定周期 log 目录, 固定 pc 前缀, K 列表, r1, s)
# ★ 命名约定已核实：pc CSV 在顶层，命名 <前缀>_pc_k<K>_r<R>.csv；
#   log 在各自目录，命名 log.r<R>k<K>。
CFG = [
    ("fx",   "a2fx_case/log.ONLs.r%d",   "a2fx",  "fixed",   "fx",   [1, 2, 3, 5, 8],     57.9, 3.00),
    ("l15",  "a2l15_case/log.ONLs.r%d",  "a2l15", "l15",     "l15",  [1, 2, 3, 5, 8],     77.7, 3.00),
    ("l20",  "a2A_case/log.ONLs.r%d",    "a2A",   "l20",     "l20",  [1, 2, 3, 5, 8],     90.6, 3.00),
    ("fine", "a2fine_case/log.ONLs.r%d", "a2fine","finerun", "fine", [1, 2, 3, 5, 8],    115.2, 3.00),
    ("x3",   "a2x3_case/log.ONLs.r%d",   "a2x3",  "x3run",   "x3",   [1, 2, 3, 5, 8],    113.2, 3.00),
    ("fl30", "a2B_case/log.ONLs.r%d",    "a2B",   "fl30run", "fl30", [1, 3, 5],          147.4, 3.00),
    ("sth",  "a2sth_case/log.ONLs.r%d",  "a2sth", "stefan",  "sth",  [1, 2, 3, 5, 8, 13], 17.0, 4.00),
]


def per_step_N(path):
    out = []; cur = []; started = False
    for ln in open(path, errors="ignore"):
        if TRE.match(ln):
            if started:
                out.append(sum(cur))
            cur = []; started = True; continue
        m = NRE.search(ln)
        if m:
            cur.append(int(m.group(1)))
    if started:
        out.append(sum(cur))
    return out


def rbsteps(pc):
    """重建步数：pc CSV 里 reusedFrom < 0 的唯一步数。

    ★ 注意 pc CSV 无表头，字段名在 CSV_HDR 里；每步可能有 s 行（每次求解一行），
      但只有"每步第一次求解"那行的 rep>=0，据此去重。
    """
    seen = {}
    for ln in open(pc, errors="ignore"):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25:
            continue
        try:
            d = dict(zip(CSV_HDR, q))
            ti = int(float(d["timeIndex"]))
            rep = float(d["rep"])
            rf = float(d["reusedFrom"])
        except ValueError:
            continue
        if rep >= 0 and ti not in seen:
            seen[ti] = rf
    return sum(1 for t in seen if seen[t] < 0), len(seen)


print("=" * 122)
print("★★★ 用实测数据重算：在线策略 vs 事后最优固定周期")
print("=" * 122)

summary = []
for tag, onlpat, onlpre, fixdir, fixpre, Ks, r1, s in CFG:
    # ---- 在线（取 3 轮的中位）
    onl_it = []; onl_rb = []
    for r in (1, 2, 3):
        lg = os.path.join(P, onlpat % r)
        pc = os.path.join(P, "%s_pc_ONLs_r%d.csv" % (onlpre, r))
        if not (os.path.exists(lg) and os.path.exists(pc)):
            continue
        onl_it.append(sum(per_step_N(lg)))
        onl_rb.append(rbsteps(pc)[0])
    if not onl_it:
        print("【%s】★ 在线数据缺失" % tag); continue
    OIT = st.median(onl_it); ORB = st.median(onl_rb)

    # ---- 固定周期（取 3 轮的中位）
    fix = {}
    for K in Ks:
        its = []; rbs = []
        for r in (1, 2, 3):
            lg = os.path.join(P, fixdir, "log.r%dk%d" % (r, K))
            pc = os.path.join(P, "%s_pc_k%d_r%d.csv" % (fixpre, K, r))
            if not (os.path.exists(lg) and os.path.exists(pc)):
                continue
            its.append(sum(per_step_N(lg)))
            rbs.append(rbsteps(pc)[0])
        if its:
            fix[K] = (st.median(its), st.median(rbs))
    if not fix:
        print("【%s】★ 固定周期数据缺失" % tag); continue

    print("\n" + "─" * 122)
    print("【%s】r1=%.1f s=%.2f   在线: iters=%d rbsteps=%d（%d 轮）"
          % (tag, r1, s, OIT, ORB, len(onl_it)))
    print("  %-6s %-10s %-10s %-12s %-12s %s"
          % ("K", "iters", "rbsteps", "cost@r1", "cost@s·r1", "vs 在线@r1"))
    rows = []
    for K in sorted(fix):
        it, rb = fix[K]
        c1 = it + r1 * rb
        c2 = it + r1 * s * rb
        oc1 = OIT + r1 * ORB
        rows.append((K, it, rb, c1, c2))
        print("  K%-5d %-10d %-10d %-12.0f %-12.0f %+11.2f%%"
              % (K, it, rb, c1, c2, 100.0 * (oc1 - c1) / c1))
    # 在线两端口径
    oc1 = OIT + r1 * ORB
    oc2 = OIT + r1 * s * ORB
    print("  %-6s %-10d %-10d %-12.0f %-12.0f %s"
          % ("在线", OIT, ORB, oc1, oc2, "—"))
    # 实测 K*
    kstar1 = min(rows, key=lambda x: x[3])[0]
    kstar2 = min(rows, key=lambda x: x[4])[0]
    b1 = min(r[3] for r in rows); b2 = min(r[4] for r in rows)
    g1 = 100.0 * (oc1 - b1) / b1
    g2 = 100.0 * (oc2 - b2) / b2
    print("  ⇒ 实测最优固定 K*: @r1 → K%d, @s·r1 → K%d" % (kstar1, kstar2))
    print("  ⇒ ★ 在线 vs 实测最优固定周期: @r1 %+.2f%%   @s·r1 %+.2f%%"
          % (g1, g2))
    summary.append((tag, kstar1, kstar2, g1, g2))

print("\n" + "=" * 122)
print("汇总（纯实测）")
print("=" * 122)
print("  %-6s %-12s %-12s %-14s %s"
      % ("配置", "实测K*@r1", "实测K*@s·r1", "在线gap@r1", "在线gap@s·r1"))
for tag, k1, k2, g1, g2 in summary:
    print("  %-6s K%-11d K%-11d %+13.2f%% %+13.2f%%" % (tag, k1, k2, g1, g2))
g1s = [x[3] for x in summary]; g2s = [x[4] for x in summary]
print("\n  ⇒ gap@r1   范围 [%+.2f%%, %+.2f%%]  中位 %+.2f%%" % (min(g1s), max(g1s), st.median(g1s)))
print("  ⇒ gap@s·r1 范围 [%+.2f%%, %+.2f%%]  中位 %+.2f%%" % (min(g2s), max(g2s), st.median(g2s)))
