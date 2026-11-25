#!/usr/bin/env python3
"""
隔离实验（第二层）：把插值口径单独拎出来。

上一版的两个实现差 6.2%，但那一次仍混了两个变量：
   · 决策逻辑（v3 的 sim_online vs pbrcost 的 sim_online_detail）
   · 缺失格的插值（v3 的 mk 用【最近邻】；Env 用【形状迁移 N(t,0)·G(a)】）

本脚本直接比较两个插值器在【同一张表】上给出的 N(t,a)，量化差异，
并把它对决策的影响单独算出来（用同一个决策逻辑跑两种插值）。
"""
import sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import Env

TIME_RE = None
import os, re
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
    for ln in open(path, errors="ignore"):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError:
            pass
    return o


def build(tag, logdir, rounds, Ks):
    cells = defaultdict(list); rv = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "/root/autodl-tmp/PBR/%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join("/root/autodl-tmp/PBR", logdir, "log.r%dk%d" % (R, K))
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
                cells[(t, 0 if rf < 0 else t - rf)].append(Ns[i])
            for d in rows(c):
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"] / d["tIter"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=st.median(rv) if rv else float("nan"), nsteps=ns)


def mk_nearest(tab):
    """v3 的插值：缺失取该行最近年龄"""
    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}
    def N(t, a):
        row = byt.get(t)
        if row is not None:
            return row[a] if a in row else row[min(sa[t], key=lambda x: abs(x - a))]
        return curve.get(a, curve[amx])
    return N, curve


TAG, LOGDIR, ROUNDS, KS = "l20", "l20", [1, 2, 3, 4, 5], [1, 2, 3, 5, 8]
full = build(TAG, LOGDIR, ROUNDS, KS)
tab = full["tab"]
Nnear, curve = mk_nearest(tab)
env = Env(tab, sFact=2.99)

print("=" * 118)
print("★ 隔离第二层：两个插值器的逐格差异（%s，同一张表）" % TAG)
print("=" * 118)
print("  表: %d 格，年龄覆盖 %s" % (len(tab), sorted(curve)))

# 逐格比较：仅比较【表中缺失】的 (t,a) —— 两者在这些格上会分岔
diffs = []
tm = max(t for (t, a) in tab)
for t in range(101, tm + 1):
    row = {a: v for (tt, a), v in tab.items() if tt == t}
    if not row: continue
    amax = max(row)
    for a in range(1, min(amax + 8, 30)):
        if a in row:
            continue  # 实测格，两者一致
        vn = Nnear(t, a)
        ve = env(t, a)
        if vn > 0:
            diffs.append(100.0 * (ve - vn) / vn)
print("  缺失格数（被比较的）= %d" % len(diffs))
if diffs:
    print("  形状迁移 vs 最近邻的相对差: 中位 %+.1f%%  均值 %+.1f%%  极差 [%+.1f%%, %+.1f%%]"
          % (st.median(diffs), st.mean(diffs), min(diffs), max(diffs)))
    print("  ★ 正 = 形状迁移给出【更大】的 N ⇒ 判据更倾向重建")

# 用两个插值器各跑一次【同一决策逻辑】（借 pbrcost 的实现，只换 N 函数）
from pbrcost import sim_online_detail, sim_fixed


class Wrap:
    """把 v3 的最近邻插值包装成 Env 的调用接口（只需可调用 + sFact + amax_data）"""
    def __init__(self, Nfn, sFact):
        self.N = Nfn; self.sFact = sFact
        self.amax_data = 7
    def __call__(self, t, a):
        return self.N(t, a)


print("\n  ── 同一决策逻辑下，只换插值器的后果：")
for lab, e in (("最近邻（v3 口径）", Wrap(Nnear, 2.99)), ("形状迁移（pbrcost）", env)):
    for rlab, rho in (("r_solve", 90.78), ("r_eff=s·r", 90.78 * 2.99)):
        c, it, rb, _, _ = sim_online_detail(e, rho, 344, 100)
        bc, bk = min(((sim_fixed(e, rho, k, 344, 100)[0], k) for k in range(1, 9)))
        print("     %-22s ρ=%-11s cost=%-8.0f iters=%-7d rb=%-5d  vs K%d: %+.2f%%"
              % (lab, rlab, c, it, rb, bk, 100.0 * (c - bc) / bc))
