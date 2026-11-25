#!/usr/bin/env python3
"""
★★★ 修复 delta 估计器：为什么 flat 失败，什么才有效

═══ C++ 实测证据（a2smoke3）═══
ONLs (extrap):
    t=104 rb=1 age=0 est=128.5 avg=78.1   dm=extrap   ← est 随 age 成长
    t=108 rb=1 age=0 est=87.0  avg=75.7   dm=hit
ONLf (flat):
    t=111 rb=0 age=7  est=43.0 avg=268.5  dm=flat
    t=120 rb=0 age=16 est=43.0 avg=1833.4 dm=flat     ← est 冻结，永不重建

诊断：`flat` 把 delta 取成【最大已知年龄的中位数】后就变成常数，
      不再随 age 增长。avg 一路涨到 1833，est 恒为 43，
      数学上不可能触发重建。之后 avg 继续涨、est 继续冻结 ⇒ 死锁。

⇒ 结论：任何"冻结"的 delta 估计器都不成立。delta 必须随 age 单调增长。

═══ 真正要修的问题 ═══
原始 extrap 的问题是【外推斜率被污染样本放大】：
l15 上 dN[1]=124.5, dN[2]=153.5（都取自预热瞬变），
外推出 delta(age=3)=182.5，导致周期性重建。

但 extrap 的【单调性】是对的。所以要保留单调性、只治污染。

候选修复：
  A. slope_cap    外推斜率上限 = 小年龄段的实测斜率（防止污染样本给出巨大斜率）
  B. min_n        要求样本数 ≥ N 才采信，不足则退回【仍随 age 增长】的形式
  C. median_win   只用最近 W 个样本（去掉预热期的陈旧污染）
  D. robust       用中位数绝对偏差剔除离群样本后再取中位
"""
import sys, os, statistics as st
from collections import defaultdict, deque
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
ORDER = ("fx", "l15", "l20", "fine", "x3", "fl30", "sth")

# 基准步数（用于剔除截断文件）
BASE_N = {"fx": 344, "l15": 344, "l20": 344, "fine": 720,
          "x3": 1231, "fl30": 720, "sth": 5866}


def load(tag, policy="B"):
    base_n = BASE_N[tag]
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    for prefix, logdir, Ks, rounds in SPEC[tag]:
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
for t in ORDER:
    c = load(t)
    if c: CFG[t] = c
B0 = P.B0


def sim(env, r0, T, est_mode, param=None, window=40, maxn=None):
    """
    est_mode:
      'orig'    原始（外推，无防护）
      'flat'    常数（已知会在 C++ 上死锁）
      'slopecap' 外推斜率上限 = 小年龄段实测斜率
      'minn'     样本数 < param 时，用【仍随 age 增长】的保守形式
      'window'   只用最近 window 个样本
      'robust'   先剔除离群（MAD）再取中位
    """
    know = defaultdict(lambda: deque(maxlen=window) if est_mode == "window" else [])
    levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1; n_rb = 0

    def med_robust(lst):
        if len(lst) < 4:
            return st.median(lst)
        m = st.median(lst)
        dev = [abs(x-m) for x in lst]
        mad = st.median(dev)
        if mad < 1e-9:
            return m
        keep = [x for x in lst if abs(x-m) <= 3.0*mad]
        return st.median(keep) if keep else m

    def slope_base(know, levels):
        """小年龄段（age=1,2）的实测斜率，作为斜率上限"""
        s = []
        for aa in (1, 2):
            if aa in know and know[aa]:
                s.append(st.median(list(know[aa])))
        return max(s) if s else None

    for t in range(1, T+1):
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            ks = sorted(k for k in know if know[k])
            delta = 0.0
            if age in know and know[age]:
                lst = list(know[age])
                delta = med_robust(lst) if est_mode == "robust" else st.median(lst)
            elif ks:
                if est_mode == "flat":
                    delta = st.median(list(know[ks[-1]]))
                else:
                    # 以最大已知年龄为基点，加上"每岁增长"的估计
                    a2 = ks[-1]
                    d2 = st.median(list(know[a2]))
                    # 每岁增长：优先用相邻两点，否则回退到 a2 自身的平均
                    if len(ks) >= 2:
                        a1 = ks[-2]
                        d1 = st.median(list(know[a1]))
                        sl = (d2-d1)/max(1e-9, a2-a1)
                    else:
                        sl = d2/max(1e-9, a2)
                    if est_mode == "slopecap":
                        sb = slope_base(know, levels)
                        if sb is not None:
                            sl = min(sl, sb)
                    elif est_mode == "minn":
                        need = param or 3
                        if len(know[a2]) < need:
                            # 仍随 age 增长，但用较保守的斜率（不放大污染）
                            sl = min(sl, d2/max(1e-9, a2))
                    sl = max(0.0, sl)
                    delta = d2 + sl*(age - a2)
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < B0 else (c, 1)
            levels.append(N); a = 1; held = t; n_rb += 1
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9:
                    if isinstance(know[a], deque): know[a].append(N-bm)
                    else: know[a].append(N-bm)
            a += 1
    return tot, n_rb


VARIANTS = [
    ("orig 外推",      dict(est_mode="orig")),
    ("flat 常数",      dict(est_mode="flat")),
    ("slopecap",      dict(est_mode="slopecap")),
    ("minn=3",        dict(est_mode="minn", param=3)),
    ("minn=5",        dict(est_mode="minn", param=5)),
    ("window=40",     dict(est_mode="window", window=40)),
    ("robust MAD",    dict(est_mode="robust")),
]

CAND = (1,2,3,4,5,6,8,10,13,20,30,50)
print("=" * 138)
print("★★★ delta 估计器变体对比（模型层）")
print("=" * 138)
print("  %-6s %8s" % ("配置", "K*") + "".join("%14s" % n for n, _ in VARIANTS))
print("  " + "-" * 134)
RES = {}
for tag in ORDER:
    cfg = CFG.get(tag)
    if not cfg: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    orc = P.sim_dp(env, r0, T)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    line = "  %-6s %8d" % (tag, kb)
    RES[tag] = {}
    for nm, kw in VARIANTS:
        c, nrb = sim(env, r0, T, **kw)
        reg = 100*(c/orc-1)
        RES[tag][nm] = (reg, nrb)
        line += "%13.2f%%" % reg
    print(line)
print("  " + "-" * 134)
print()
print("  %-14s %10s %10s %10s %12s   %s"
      % ("变体", "中位", "最小", "最大", "重建数中位", "判定"))
for nm, _ in VARIANTS:
    v = [RES[t][nm][0] for t in ORDER if t in RES]
    rb = [RES[t][nm][1] for t in ORDER if t in RES]
    if not v: continue
    verdict = "★死锁/灾难" if max(v) > 50 else ("可用" if st.median(v) < 8 else "偏弱")
    print("  %-14s %9.2f%% %9.2f%% %9.2f%% %12.0f   %s"
          % (nm, st.median(v), min(v), max(v), st.median(rb), verdict))
kk = []
for tag in ORDER:
    cfg = CFG.get(tag)
    if not cfg: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    orc = P.sim_dp(env, r0, T)
    fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
    kk.append(100*(fx[min(fx, key=fx.get)]/orc-1))
print("  %-14s %9.2f%% %9.2f%% %9.2f%%" % ("最优固定 K*", st.median(kk), min(kk), max(kk)))
print("=" * 138)
