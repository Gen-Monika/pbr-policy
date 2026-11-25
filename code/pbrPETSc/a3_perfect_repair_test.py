#!/usr/bin/env python3
"""
★★★ A3 检验（离线，零新增仿真成本）

A3 假设 = "重建后回到基线"（as good as new / perfect repair）。
若成立：重建后第 1 步的迭代数，应当等于"每步都重建"基线在同一时刻的迭代数。
若不成立（imperfect repair）：重建后仍有残留惩罚。

★ 关键洞察：这个检验【不需要构造 IT[a,b] 表】。
   IT[a,b] 表要分离"算子漂移 vs 初值质量"，那是为了测【漂移速率】。
   而 A3 问的是"重建是否把状态恢复到基线"——只需比较：
       重建后 age=1 的 N  vs  K=1 基线在同一 t 的 N
   两者若在统计上相等 ⇒ 重建是"如新"的；若有系统性正偏差 ⇒ imperfect repair。

数据来源：已有的 K=1（每步重建）与 K=3/5/8（周期重建）CSV+日志。
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
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25: continue
        try:
            d = dict(zip(CSV_HDR, p))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def seq(tag, logdir, K, R):
    """返回 [(t, age_at_action, N_step)]，age 由 reusedFrom 推出。"""
    c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
    l = os.path.join(logdir, "log.r%dk%d" % (R, K))
    if not (os.path.exists(c) and os.path.exists(l)): return None
    rr = rows(c); seen = {}
    for d in rr:
        if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
            seen[int(d["timeIndex"])] = d
    rr = [seen[t] for t in sorted(seen)]
    Ns = per_step_N(l)
    n = min(len(rr), len(Ns))
    out = []
    for i in range(n):
        d = rr[i]; t = i + 1
        rf = int(d["reusedFrom"])
        out.append((t, 0 if rf < 0 else t - rf, Ns[i]))
    return out


CFG = [("fx",  "fixed",   [1,2,3,5,8], [1,2,3,4,5], 3),
       ("l15", "l15",     [1,2,3,5,8], [1,2,3,4,5], 3),
       ("l20", "l20",     [1,2,3,5,8], [1,2,3,4,5], 3),
       ("fine","finerun", [1,2,3,5,8], [1,2,3],     3),
       ("fl30","fl30run", [1,3,5],     [1,2],       3),
       ("x3",  "x3run",   [1,2,3,5,8], [1,2],       3),
       ("sth", "stefan",  [1,2,3,5,8,13], list(range(1,11)), 4)]

print("=" * 108)
print("★★★ A3 检验：重建后是否回到基线（perfect repair vs imperfect repair）")
print("=" * 108)
print("""
方法：对每个配置，取 K>1 的周期策略，把所有"重建步"的 N_step 与其年龄分组：
      age=1 表示"刚重建完，这是重建后的第 1 步"。
      再取 K=1 基线（每步重建）在同一时间步的 N_step 作为对照。
      若 A3 成立 ⇒ 两者分布应无系统性差异。
""")

summary = []
for tag, logdir, Ks, rounds, s in CFG:
    # K=1 基线：每步都是 age=1
    base_by_t = {}
    for R in rounds:
        sq = seq(tag, logdir, 1, R)
        if sq is None: continue
        for t, a, v in sq:
            base_by_t.setdefault(t, []).append(v)
    if not base_by_t:
        print("[%s] 无 K=1 数据，跳过" % tag); continue
    base_med = {t: st.median(v) for t, v in base_by_t.items()}

    # 周期策略：收集 age=1 的样本（刚重建后第一步）
    reb1 = defaultdict(list)   # t -> [N]
    allreb = 0
    for K in Ks:
        if K == 1: continue
        for R in rounds:
            sq = seq(tag, logdir, K, R)
            if sq is None: continue
            for t, a, v in sq:
                if a == 1:
                    if t in base_med: reb1[t].append(v)
                    allreb += 1
    if not reb1:
        print("[%s] 无 age=1 的重建样本，跳过" % tag); continue

    diffs = [st.median(v) - base_med[t] for t, v in reb1.items() if len(v) >= 1]
    rel = [100.0*(st.median(v)/base_med[t] - 1) for t, v in reb1.items()
           if base_med[t] > 0]
    n_gt = sum(1 for d in diffs if d > 0.5)
    n_lt = sum(1 for d in diffs if d < -0.5)
    n_eq = len(diffs) - n_gt - n_lt
    print("[%s]  重建后 age=1 样本 t 数 = %d（总样本 %d）" % (tag, len(diffs), allreb))
    print("      相对基线的偏差：中位 %+.3f%%   均值 %+.3f%%   |偏差|中位 %.3f%%"
          % (st.median(rel), st.mean(rel), st.median([abs(x) for x in rel])))
    print("      逐点符号：N 偏高 %d 点 / 偏低 %d 点 / 持平(±0.5) %d 点"
          % (n_gt, n_lt, n_eq))
    print("      ⇒ %s" % ("A3 成立（无系统性残留）✓" if abs(st.median(rel)) < 1.0
                          else "A3 存疑（系统性偏差 %.2f%%）⚠️" % st.median(rel)))
    summary.append(dict(tag=tag, rel=st.median(rel), npts=len(diffs),
                        gt=n_gt, lt=n_lt, eq=n_eq))

print("\n" + "=" * 108)
print("★★★ A3 汇总")
print("=" * 108)
print("  %-8s %12s %10s %10s %10s %10s" %
      ("配置", "相对偏差中位", "样本点数", "偏高", "偏低", "持平"))
for d in summary:
    print("  %-8s %+11.3f%% %10d %10d %10d %10d"
          % (d["tag"], d["rel"], d["npts"], d["gt"], d["lt"], d["eq"]))
print()
print("  ⇒ 若所有配置的相对偏差都 < 1%%，则可判定 A3 在真实 PDE 中【成立】，")
print("     即重建是 perfect repair，无需引入 Kijima imperfect-repair 分支。")
print("  ⇒ 若出现系统性正偏差，则重建只部分恢复，需转 imperfect repair 分支。")
