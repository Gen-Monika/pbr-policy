#!/usr/bin/env python3
"""
裁判测试（最终版）：哪个 N 表能复现 C++ 实测的在线策略决策？

★ 关键口径：C++ 的 ONLs = RCOST=solve，内部记账用 rMed（单次分解）
   ⇒ 对应模型里的 ρ = r1，不是 s·r1。
   第一层审计已确认：ρ=r1 时 l20 模型重建 221 次 = C++ 实测 221 次。
   本脚本两个 ρ 都报，用 ρ=r1 作判据。

候选：
   A  旧 K 扫描表 + 最近邻插值（v3 的 mk）—— v3 得到 7/7 时用的就是这个
   B  相位扫描表 + 形状迁移（pbrcost 的 Env）—— 已通过第一层验收的表
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
        if len(q) != 25:
            continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"):
                    d[k] = float(d[k])
            o.append(d)
        except ValueError:
            pass
    return o


def cpp_dec(path):
    rr = rows(path)
    if not rr:
        return None
    seen = {}
    for d in rr:
        t = int(d["timeIndex"])
        if t not in seen:
            seen[t] = d
    ts = sorted(seen)
    return [1 if int(seen[t]["reusedFrom"]) < 0 else 0 for t in ts]


def v3_table(tag, logdir, rounds, Ks):
    cells = defaultdict(list)
    for K in Ks:
        for R in rounds:
            c = "/root/autodl-tmp/PBR/%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join("/root/autodl-tmp/PBR", logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)):
                continue
            rr = rows(c); s2 = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in s2:
                    s2[int(d["timeIndex"])] = d
            rr = [s2[t] for t in sorted(s2)]
            Ns = []; cur = []
            for ln in open(l, errors="ignore"):
                if TIME_RE.match(ln):
                    if cur:
                        Ns.append(sum(cur)); cur = []
                    continue
                m = SOLVE_RE.search(ln)
                if m:
                    cur.append(int(m.group(1)))
            if cur:
                Ns.append(sum(cur))
            n = min(len(rr), len(Ns))
            for i in range(n):
                d = rr[i]; rf = int(d["reusedFrom"])
                cells[(i + 1, 0 if rf < 0 else i + 1 - rf)].append(Ns[i])
    return {k: st.median(v) for k, v in cells.items()} if cells else None


def mk_nearest(tab):
    bya = defaultdict(list)
    for (t, a), v in tab.items():
        bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)
    byt = defaultdict(dict)
    for (t, a), v in tab.items():
        byt[t][a] = v
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


CONF = [
    ("l20",  "l20",     [1, 2, 3, 4, 5],  [1, 2, 3, 5, 8],      "a2A_pc_ONLs_r1.csv"),
    ("fl30", "fl30run", [1, 2],           [1, 3, 5],            "a2B_pc_ONLs_r1.csv"),
    ("fx",   "fixed",   [1, 2, 3, 4, 5],  [1, 2, 3, 5, 8],      "a2fx_pc_ONLs_r1.csv"),
    ("l15",  "l15",     [1, 2, 3, 4, 5],  [1, 2, 3, 5, 8],      "a2l15_pc_ONLs_r1.csv"),
    ("fine", "finerun", [1, 2, 3],        [1, 2, 3, 5, 8],      "a2fine_pc_ONLs_r1.csv"),
    ("x3",   "x3run",   [1, 2],           [1, 2, 3, 5, 8],      "a2x3_pc_ONLs_r1.csv"),
    ("sth",  "stefan",  list(range(1, 11)), [1, 2, 3, 5, 8, 13], "a2sth_pc_ONLs_r1.csv"),
]

print("=" * 122)
print("★★★ 裁判：哪个 N 表能复现 C++ 实测的在线决策？")
print("    ONLs = RCOST=solve ⇒ 对应 ρ=r1（判据用这一行）")
print("=" * 122)
print("  %-6s %-9s | %-28s | %s" % ("配置", "实测重建", "候选B 相位表+形状迁移", "候选A 旧表+最近邻"))

tally = {"B": 0, "A": 0, "n": 0}
for tag, logdir, rounds, Ks, cppfile in CONF:
    cpp = cpp_dec("/root/autodl-tmp/PBR/" + cppfile)
    if not cpp:
        print("  %-6s ★ log 缺失（%s）" % (tag, cppfile))
        continue
    d = load_phase(tag)
    lvl, T, B0 = CFG[tag]
    rho = d["r1"]           # ★ 判据口径
    tabA = v3_table(tag, logdir, rounds, Ks)

    envB = Env(d["tab"], sFact=d["s"])
    _, _, rbB, predB, _ = sim_online_detail(envB, rho, T, B0)
    n = min(len(predB), len(cpp))
    agB = 100.0 * sum(1 for i in range(n) if int(predB[i]) == cpp[i]) / n

    sA = "（数据缺失）"
    agA = -1
    rbA = -1
    if tabA:
        envA = Wrap(mk_nearest(tabA), d["s"], max(a for _, a in tabA))
        _, _, rbA, predA, _ = sim_online_detail(envA, rho, T, B0)
        n2 = min(len(predA), len(cpp))
        agA = 100.0 * sum(1 for i in range(n2) if int(predA[i]) == cpp[i]) / n2
        sA = "rb=%-4d 一致 %5.2f%%%s" % (rbA, agA, "  ←胜" if agA > agB else "")

    print("  %-6s %-9d | rb=%-4d 一致 %5.2f%%%-8s | %s"
          % (tag, sum(cpp), rbB, agB, "  ←胜" if agB >= agA else "", sA))
    tally["n"] += 1
    if agB >= agA:
        tally["B"] += 1
    else:
        tally["A"] += 1

print("\n  ★ 胜出统计（ρ=r1 口径）：候选B(相位表) %d / 候选A(旧表) %d（共 %d 配置）"
      % (tally["B"], tally["A"], tally["n"]))
print("  ★ 同时看重建次数：C++ 实测的重建次数才是硬目标。")
