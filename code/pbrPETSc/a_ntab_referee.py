#!/usr/bin/env python3
"""
裁判测试：两个 N 表，谁复现了 C++ 实测的在线策略决策？

判据（与第一层 L2 相同）：
   用该表 + 该插值器跑在线策略，与 C++ 实测的 online CSV 逐步比对。
   C++ 实测的在线运行：a2<tag>_case + ONLs（DMODE=extrap, DMINN=1）。

★ 两个候选：
   候选 A：旧 K 扫描表（l20_pc_k*.csv 等）+ 最近邻插值（v3 的 mk）
   候选 B：相位扫描表（phs_*）+ 形状迁移（pbrcost 的 Env）
   —— 而 C++ 用的既不是 A 也不是 B，是【逐年龄 dN 样本的中位数 + 线性外推】。

所以本测试同时回答：C++ 的决策能否被 A 或 B 复现。
"""
import sys, os, re, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import Env, sim_online_detail, load_phase, CFG

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


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


def cpp_online_decisions(csvpath):
    """读 C++ 的在线 log，返回逐 step 的 rebuild 布尔序列（索引 1..T）"""
    rr = rows(csvpath)
    if not rr: return None
    seen = {}
    for d in rr:
        t = int(d["timeIndex"])
        if t not in seen: seen[t] = d
    ts = sorted(seen)
    return [1 if int(seen[t]["reusedFrom"]) < 0 else 0 for t in ts], ts


def v3_table(tag, logdir, rounds, Ks):
    cells = defaultdict(list)
    for K in Ks:
        for R in rounds:
            c = "/root/autodl-tmp/PBR/%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join("/root/autodl-tmp/PBR", logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c); s2 = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in s2: s2[int(d["timeIndex"])] = d
            rr = [s2[t] for t in sorted(s2)]
            Ns = []
            cur = []
            for ln in open(l, errors="ignore"):
                if TIME_RE.match(ln):
                    if cur: Ns.append(sum(cur)); cur = []
                    continue
                m = SOLVE_RE.search(ln)
                if m: cur.append(int(m.group(1)))
            if cur: Ns.append(sum(cur))
            n = min(len(rr), len(Ns))
            for i in range(n):
                d = rr[i]; rf = int(d["reusedFrom"])
                cells[(i + 1, 0 if rf < 0 else i + 1 - rf)].append(Ns[i])
    return {k: st.median(v) for k, v in cells.items()} if cells else None


def mk_nearest(tab):
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
    return N


class Wrap:
    def __init__(self, Nfn, sFact, amax):
        self.N = Nfn; self.sFact = sFact; self.amax_data = amax
    def __call__(self, t, a):
        return self.N(t, a)


CONF = {
    "l20":  ("l20", "l20", [1, 2, 3, 4, 5], [1, 2, 3, 5, 8]),
    "fl30": ("fl30", "fl30run", [1, 2], [1, 3, 5]),
    "fx":   ("fx", "fixed", [1, 2, 3, 4, 5], [1, 2, 3, 5, 8]),
}
# ★ 名字映射已核实：a2A = l20（levels=20, T=344）；a2B = fl30（levels=30, T=720）
CPP = {"l20": "a2A_pc_ONLs_r1.csv",
       "fl30": "a2B_pc_ONLs_r1.csv",
       "fx": "a2fx_pc_ONLs_r1.csv"}

print("=" * 120)
print("★★★ 裁判：哪个 N 表能复现 C++ 实测的在线策略决策？")
print("=" * 120)
for tag, (t2, logdir, rounds, Ks) in CONF.items():
    cpp = cpp_online_decisions("/root/autodl-tmp/PBR/" + CPP[tag])
    if not cpp:
        print("\n【%s】★ C++ 在线 log 缺失（%s）" % (tag, CPP[tag])); continue
    cpp_dec, ts = cpp
    d = load_phase(tag)
    lvl, T, B0 = CFG[tag]
    # ★ C++ 的 ONLs（RCOST=solve）内部用 rMed（单次分解）做记账 ⇒ 对应 ρ=r1
    rho = d["r1"]

    print("\n" + "─" * 120)
    print("【%s】C++ 在线实测：%d 步、重建 %d 次  ρ=r1=%.1f（ONLs 用 RCOST=solve）"
          % (tag, len(cpp_dec), sum(cpp_dec), rho))
    for rlab, rho2 in (("ρ=r1", d["r1"]), ("ρ=s·r1", d["r1"]*d["s"])):
     rho = rho2
     # 候选 B：相位表 + 形状迁移
     envB = Env(d["tab"], sFact=d["s"])
    cB, itB, rbB, predB, _ = sim_online_detail(envB, rho, T, B0)
    n = min(len(predB), len(cpp_dec))
    agreeB = sum(1 for i in range(n) if int(predB[i]) == cpp_dec[i])
    print("   候选 B（相位表 + 形状迁移）：重建 %d 次（实测 %d）  决策一致 %d/%d = %.2f%%"
          % (rbB, sum(cpp_dec), agreeB, n, 100.0 * agreeB / n))
    # 候选 A：旧表 + 最近邻
    tabA = v3_table(t2, logdir, rounds, Ks)
    if tabA:
        NA = mk_nearest(tabA)
        envA = Wrap(NA, d["s"], max(a for _, a in tabA))
        cA, itA, rbA, predA, _ = sim_online_detail(envA, rho, T, B0)
        n2 = min(len(predA), len(cpp_dec))
        agreeA = sum(1 for i in range(n2) if int(predA[i]) == cpp_dec[i])
        print("   候选 A（旧 K 扫描表 + 最近邻）：重建 %d 次  决策一致 %d/%d = %.2f%%"
              % (rbA, agreeA, n2, 100.0 * agreeA / n2))
        print("   ⇒ 更接近实测的是：%s"
              % ("候选 B（相位表）" if agreeB > agreeA else "候选 A（旧表）"))
    else:
        print("   候选 A：数据缺失")

print("\n" + "=" * 120)
print("★ 判读：决策一致率更高的那个表才是【正确的建模口径】。")
print("  这决定「在线 vs 固定周期」该用哪张表来算。")
