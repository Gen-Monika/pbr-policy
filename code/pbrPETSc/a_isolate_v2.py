#!/usr/bin/env python3
"""
隔离实验：在【同一张 N 表】上跑两个在线策略实现，看是否等价。

变量共三个，必须一次只动一个：
   V1  N 表：v3 用旧 K 扫描数据 + 最近邻回退；pbrcost 用相位扫描表 + 形状迁移外推
   V2  在线实现：v3 的 sim_online（8 变体之一，P0）；pbrcost 的 sim_online_detail
   V3  变体选择：v3 在训练轮上从 8 变体里挑；单变体时固定 P0

本脚本：
   (A) 用 v3 自己的 build/mk 造 l20 的表，跑 v3 的 sim_online(P0) → 基准
   (B) 同一张表，跑 pbrcost 的 sim_online_detail → 若不同，V2 有差异
   (C) 打印两表在同一 (t,a) 上的取值差异 → 量化 V1
"""
import sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")

import importlib.util
spec = importlib.util.spec_from_file_location("v3", "/root/autodl-tmp/PBR/online_holdout_v3.py")
# 不执行整个 v3（它会跑全流程），只借它的函数：直接读源码片段手工重建
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


def mk(tab):
    """v3 的 N(t,a)：实测优先，缺失取【该行最近年龄】"""
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


def sim_online_v3(Nfn, r0, T, b0=100, target_age=0, force_every=0, lvl_mode="last", amax=99):
    """忠实抄自 v3（P0 参数下 target_age=0/force_every=0 使这两个分支不生效）"""
    know = defaultdict(list); levels = []
    tot = 0.0; it = 0.0; acc = 0.0; accn = 0; a = 0; held = -1; rb = 0
    for t in range(1, T + 1):
        if t < b0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc / accn if accn else tot / max(1, t - 1)
            lvl = levels[-1]
            delta = 0.0
            if age in know:
                delta = st.median(know[age])
            elif len(know) >= 1:
                ks = sorted(know)
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    sl = (d2 - d1) / (a2 - a1)
                    delta = max(0.0, d2 + sl * (age - a2))
                else:
                    delta = st.median(know[ks[-1]])
            est = lvl + max(0.0, delta)
            rebuild = est > avg
        if rebuild:
            tot += r0 + Nfn(t, 0); it += Nfn(t, 0); rb += 1
            acc, accn = r0 + Nfn(t, 0), 1
            levels.append(Nfn(t, 0)); held = t; a = 1
        else:
            nn = Nfn(t, a); tot += nn; it += nn; acc += nn; accn += 1; a += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a - 1].append(nn - bm)
    return tot, it, rb


def sim_fixed(Nfn, r0, K, T, b0=100):
    tot, a = 0.0, 0
    for t in range(1, T + 1):
        if (t < b0) or ((t - b0) % K == 0):
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


TAG, LOGDIR, ROUNDS, KS = "l20", "l20", [1, 2, 3, 4, 5], [1, 2, 3, 5, 8]
full = build(TAG, LOGDIR, ROUNDS, KS)
if not full:
    print("★ 数据缺失"); sys.exit(1)
Nv3, curve = mk(full["tab"])
T = full["nsteps"]; r_solve = full["r"]; fac = 2.99
print("=" * 116)
print("隔离实验：同一张 N 表上比较两个在线实现（%s）" % TAG)
print("=" * 116)
print("  表规模: %d 个 (t,a) 格   覆盖年龄 %s   T=%d   r_solve=%.2f"
      % (len(full["tab"]), sorted(curve)[:12], T, r_solve))

for lab, rho in (("r_solve=%.2f" % r_solve, r_solve), ("r_eff=s·r=%.2f" % (r_solve * fac), r_solve * fac)):
    print("\n  ── ρ = %s" % lab)
    # (A) v3 的实现
    c_v3, it_v3, rb_v3 = sim_online_v3(Nv3, rho, T)
    # (B) pbrcost 的实现（同一张表）
    sys.path.insert(0, "/root/autodl-tmp/PBR")
    from pbrcost import Env, sim_online_detail
    env = Env(full["tab"], sFact=fac)
    c_pc, it_pc, rb_pc, _, _ = sim_online_detail(env, rho, T, 100)
    # 最优固定周期
    bc, bk = min(((sim_fixed(Nv3, rho, k, T), k) for k in range(1, 9)))
    print("     v3 实现   : cost=%.0f iters=%d rb=%d   gap vs K%d = %+.2f%%"
          % (c_v3, it_v3, rb_v3, bk, 100.0 * (c_v3 - bc) / bc))
    print("     pbrcost   : cost=%.0f iters=%d rb=%d   gap vs K%d = %+.2f%%"
          % (c_pc, it_pc, rb_pc, bk, 100.0 * (c_pc - bc) / bc))
    print("     两者差    : cost %+.2f%%   iters %+d   rb %+d   %s"
          % (100.0 * (c_pc - c_v3) / c_v3, it_pc - it_v3, rb_pc - rb_v3,
             "✓ 等价" if abs(c_pc - c_v3) < 1e-6 else "★ 不等价 ⇒ V2 有差异"))
