#!/usr/bin/env python3
"""
★★★ 形状迁移的独立验证（留一年龄交叉验证）

═══ 为什么必须做 ═══
形状迁移让在线策略的 regret 从 (l15 +16.66 / fine +102.53) 降到接近 0。
这正是"看起来太好的结果"，必须先排除"这个填充方式本身在偏袒在线策略"。

警惕的失效模式：如果形状迁移系统性地【低估】大年龄的 N，那么
  · oracle 会以为"复用很便宜"，从而给出偏低的 oracle
  · 在线策略也会因为同样的低估而少重建
  结果两者一起偏低，regret 看起来就小了 —— 这是自欺。

═══ 验证设计 ═══
留一年龄交叉验证（leave-one-age-out）：
  对每个年龄 a0（a0 ≥ 1），把【所有 t 上 age=a0 的实测值】全部藏起来，
  只用其余年龄重建 G(·)，然后预测 age=a0 的 N(t,a0)，与实测比较。

判据：
  · 若预测/实测 的中位数接近 1.0 且无系统偏差 ⇒ 形状假设成立
  · 若系统性 < 1（低估大年龄）⇒ 形状迁移在偏袒"多复用"
  · 若系统性 > 1 ⇒ 在偏袒"多重建"
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

SPEC = {
    "fx":   [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])],
    "l15":  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
             ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])],
    "l20":  [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])],
    "fine": [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
             ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])],
    "x3":   [("x3", "x3run", [1,2,3,5,8], [1,2]),
             ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])],
    "fl30": [("fl30", "fl30run", [1,3,5], [1,2]),
             ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])],
    "sth":  [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
             ("cov2_sth", "cov2_sth", [20,30], [1,2,3])],
}


def load_raw(tag):
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    for prefix, logdir, Ks, rounds in SPEC[tag]:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                try:
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
                    rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                    nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                    if rbs: fac.append(nrs/len(rbs))
                    ns = max(ns, n)
                except Exception:
                    pass
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


print("=" * 130)
print("★★★ 留一年龄交叉验证：形状迁移能否预测被藏起来的年龄？")
print("=" * 130)
print("  对每个 a0：藏起全部 age=a0 的实测值 → 用其余年龄重建 G(·) → 预测 a0 → 与实测比")
print()
print("  判据：比值中位数≈1.0 且无系统偏差 ⇒ 形状假设成立且不偏袒任何一侧")
print()

for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load_raw(tag)
    if cfg is None: continue
    tab = cfg["tab"]
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v

    # 全局曲线（含所有年龄）
    bya = defaultdict(list)
    for t, d in byt.items():
        for a, v in d.items(): bya[a].append(v)
    curve_all = {a: st.median(v) for a, v in bya.items()}
    ages_all = sorted(curve_all)

    print("  ── %s ──  （实测年龄: %s）" % (tag, ages_all[:14]))
    print("     %-6s %8s %14s %14s %10s   %s"
          % ("藏起a0", "样本数", "预测/实测 中位", "预测/实测 均值", "系统偏差", "判定"))
    for a0 in ages_all:
        if a0 == 0: continue
        if len(bya.get(a0, [])) < 5: continue
        # 重新计算 curve，排除 a0
        curve_wo = {a: v for a, v in curve_all.items() if a != a0}
        ks = sorted(curve_wo)
        if not ks: continue
        g0 = curve_wo.get(0, st.median(list(curve_wo.values())))
        if g0 <= 0: continue

        # G(a0) —— 用 a0 两侧的已知年龄插值（模拟"不知道 a0 时"的估计）
        if a0 in curve_wo:
            G = curve_wo[a0]/g0
        else:
            lo = [x for x in ks if x < a0]
            hi = [x for x in ks if x > a0]
            if lo and hi:
                l_, h_ = lo[-1], hi[0]
                w = (a0 - l_)/(h_ - l_)
                v = (1-w)*curve_wo[l_] + w*curve_wo[h_]
                G = v/g0
            elif lo:
                G = curve_wo[lo[-1]]/g0
            else:
                G = curve_wo[hi[0]]/g0

        ratios = []
        for t, d in byt.items():
            if a0 in d and 0 in d and d[0] > 1 and t > P.B0:
                pred = d[0]*G
                ratios.append(pred/d[a0])
        if len(ratios) < 5: continue
        med = st.median(ratios); mean = sum(ratios)/len(ratios)
        # 系统偏差：中位数偏离 1 的程度
        bias = med - 1.0
        verdict = "无偏" if abs(bias) < 0.15 else ("★低估" if bias < 0 else "★高估")
        print("     %-6d %8d %14.3f %14.3f %+9.1f%%   %s"
              % (a0, len(ratios), med, mean, 100*bias, verdict))
    print()

print("=" * 130)
print("★★★ 汇总：各配置的系统偏差（只统计样本数≥10 的年龄）")
print("=" * 130)
print("  %-6s %14s %14s %14s   %s" % ("配置", "最小(最负)偏差", "中位偏差", "最大偏差", "总体判定"))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load_raw(tag)
    if cfg is None: continue
    tab = cfg["tab"]
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    bya = defaultdict(list)
    for t, d in byt.items():
        for a, v in d.items(): bya[a].append(v)
    curve_all = {a: st.median(v) for a, v in bya.items()}
    biases = []
    for a0 in sorted(curve_all):
        if a0 == 0 or len(bya.get(a0, [])) < 10: continue
        curve_wo = {a: v for a, v in curve_all.items() if a != a0}
        ks = sorted(curve_wo); g0 = curve_wo.get(0)
        if not g0: continue
        lo = [x for x in ks if x < a0]; hi = [x for x in ks if x > a0]
        if lo and hi:
            l_, h_ = lo[-1], hi[0]; w = (a0-l_)/(h_-l_)
            G = ((1-w)*curve_wo[l_] + w*curve_wo[h_])/g0
        elif lo: G = curve_wo[lo[-1]]/g0
        elif hi: G = curve_wo[hi[0]]/g0
        else: continue
        ratios = [d[0]*G/d[a0] for t, d in byt.items()
                  if a0 in d and 0 in d and d[0] > 1 and t > P.B0]
        if len(ratios) >= 5: biases.append((a0, st.median(ratios)-1.0))
    if not biases:
        print("  %-6s 无足够样本" % tag); continue
    bs = [b for _, b in biases]
    worst = min(biases, key=lambda z: z[1])
    verdict = "OK 无系统偏差" if abs(st.median(bs)) < 0.15 else "★有系统偏差"
    print("  %-6s %13.1f%% %13.1f%% %13.1f%%   %s（最偏在 age=%d）"
          % (tag, 100*min(bs), 100*st.median(bs), 100*max(bs), verdict, worst[0]))
print("=" * 130)
