#!/usr/bin/env python3
"""
★ A3 修正版检验：重建步是否与"每步重建"基线【逐位一致】

═══ 前一版 a3_test.py 测错了对象 ═══
它选 age==1 —— 但 age==1 是【复用步】（用 1 步前建的预条件子），
不是重建步。于是测到的是普通的 ΔN(1) 劣化（+46% ~ +127%），与 A3 无关。

═══ 正确的 A3 检验 ═══
周期策略（K>1）在【重建步】上（reusedFrom < 0，且 t >= 100 脱离预热期），
用的预条件子是从当前矩阵 A_t 现场重算的
—— 与 K=1 在同一个 t 上的动作【完全相同】。
若重建是 "as good as new"（perfect repair）⇒ 两者迭代数应【逐位相等】。
若系统性偏高 ⇒ imperfect repair（重建只部分恢复）⇒ 转 Kijima 分支。

★ 本检验无噪声底：迭代数是离散确定量，且各 K 的时间步序列已实测逐位一致。
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


def load(tag, logdir, K, R):
    """返回 {t: (reusedFrom, N)}；reusedFrom < 0 表示该步是重建步。"""
    c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
    l = os.path.join(logdir, "log.r%dk%d" % (R, K))
    if not (os.path.exists(c) and os.path.exists(l)): return None
    seen = {}
    for d in rows(c):
        if int(d["rep"]) >= 0:
            t = int(d["timeIndex"])
            if t not in seen: seen[t] = d
    Ns = per_step_N(l)
    out = {}
    for i, t in enumerate(sorted(seen)):
        if i < len(Ns):
            out[t] = (int(seen[t]["reusedFrom"]), Ns[i])
    return out


CFG = [("fx",  "fixed",   [1,2,3,5,8],    [1,2,3,4,5]),
       ("l15", "l15",     [1,2,3,5,8],    [1,2,3,4,5]),
       ("l20", "l20",     [1,2,3,5,8],    [1,2,3,4,5]),
       ("fine","finerun", [1,2,3,5,8],    [1,2,3]),
       ("fl30","fl30run", [1,3,5],        [1,2]),
       ("x3",  "x3run",   [1,2,3,5,8],    [1,2]),
       ("sth", "stefan",  [1,2,3,5,8,13], list(range(1,11)))]

B0 = 100
print("="*104)
print("★★★ A3 修正版：重建步 vs 每步重建基线（逐位比较）")
print("="*104)

print("\n--- 0) 噪声底：同一策略、不同轮的迭代数是否逐位相同 ---")
for tag, logdir, Ks, rounds in CFG[:3]:
    a = load(tag, logdir, 1, rounds[0]); b = load(tag, logdir, 1, rounds[1])
    if a and b:
        common = sorted(set(a) & set(b))
        bad = [t for t in common if a[t][1] != b[t][1]]
        print("  [%s] K=1 R%d vs R%d：共同步 %d，不一致 %d  ⇒ %s"
              % (tag, rounds[0], rounds[1], len(common), len(bad),
                 "逐位一致 ✓" if not bad else "不一致 %s" % bad[:5]))

print("\n--- 1) sanity：fx K=3 在 t=100..108 的 reusedFrom 与 N ---")
fa = load("fx", "fixed", 3, 1)
if fa:
    for t in sorted(fa):
        if 100 <= t <= 108:
            print("     t=%-4d reusedFrom=%-6d N=%d" % (t, fa[t][0], fa[t][1]))

print("\n" + "="*104)
print("★★★ A3 主结果（t >= 100 的重建步）")
print("="*104)
print("  %-6s %-5s %9s %10s %8s %8s %13s" %
      ("配置","K","对比步数","完全一致","偏高","偏低","相对偏差中位"))
allrows = []
for tag, logdir, Ks, rounds in CFG:
    base = defaultdict(list)
    for R in rounds:
        d = load(tag, logdir, 1, R)
        if d:
            for t, (rf, N) in d.items():
                if t >= B0: base[t].append(N)
    if not base:
        print("  [%s] 无 K=1 数据" % tag); continue
    bmed = {t: st.median(v) for t, v in base.items()}
    for K in Ks:
        if K == 1: continue
        cmp_ = []
        for R in rounds:
            d = load(tag, logdir, K, R)
            if not d: continue
            for t, (rf, N) in d.items():
                if t >= B0 and rf < 0 and t in bmed:
                    cmp_.append((t, N, bmed[t]))
        if not cmp_: continue
        eq = sum(1 for t, N, b in cmp_ if N == b)
        gt = sum(1 for t, N, b in cmp_ if N > b)
        lt = sum(1 for t, N, b in cmp_ if N < b)
        rel = [100.0*(N/b - 1) for t, N, b in cmp_ if b > 0]
        print("  %-6s %-5d %9d %10d %8d %8d %12.3f%%"
              % (tag, K, len(cmp_), eq, gt, lt, st.median(rel)))
        allrows.append((tag, K, len(cmp_), eq, gt, lt, st.median(rel)))

print()
tot = len(allrows)
ident = sum(1 for r in allrows if r[2] == r[3])
near = sum(1 for r in allrows if abs(r[6]) < 0.5)
print("  ⇒ %d 个 (配置,K) 组合中：%d 个重建步【逐位完全一致】，%d 个相对偏差 < 0.5%%"
      % (tot, ident, near))
print("  ⇒ 若基本全部一致 ⇒ A3（重建 = perfect repair）在真实 PDE 上严格成立")
print("  ⇒ 若系统性正偏差 ⇒ 转 Kijima imperfect-repair 分支")
