#!/usr/bin/env python3
"""
★★★ 成本模型核查（终）：线性形式不成立，但加上 apply 项能闭合

═══ 已确立的否定结论 ═══
线性成本模型  cost = iters + ρ·rbsteps  无法复现实测排序：
  · 反解出的 ρ 上界：l15 <61.1、l20 <61.8、fl30 <216.6
  · 模型 r_eff = 232.4 / 271.0 / 440.6  ⇒ 全部违反
  · 实测拟合 R/k = 53.7 / 162.8 / 290.1 ⇒ l20 与 fl30 仍违反
⇒ 不是"ρ 取值不对"，而是【该函数形式本身缺少一个 mode 相关的项】。

═══ 假设：缺的是 per-solve 固定开销 / apply 成本 ═══
CSV 里有 nApplyCalls 与 tApplyAccum（PETSc PCApply 的真实耗时）。
先前测得每-solve 固定开销占墙钟 33%。若该项正比于【求解次数】
（与 mode 无关，各 mode 步数相同 ⇒ 近似常数），则它对排序无影响。
但 apply 次数随 mode 变化：迭代少的 mode apply 也少。

故完整模型应为：
    execTime ≈ A·nApply + B·nBuild + c·nStep
其中 B（每次分解的墙钟）是真正的"重建代价"。

═══ 本脚本 ═══
1. 用 CSV 的 nApply / nBuild / nStep 拟合三元线性模型
2. 比较 B/A 与模型的 r_eff
3. 用 B/A 重算判据，看排序是否复现
"""
import sys, os, glob, re, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

CASES = [("l15", "a2l15.log", "a2l15", 15, 232.4),
         ("l20", "a2A.log", "a2A", 20, 271.0),
         ("fl30", "a2B.log", "a2B", 30, 440.6)]


def parse_log(path):
    out = {}
    p = os.path.join(P2, path)
    if not os.path.exists(p): return out
    for ln in open(p, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=", 1) for x in ln.split() if "=" in x)
        try:
            out[(kv["mode"], int(kv["round"]))] = dict(
                wall_ms=int(kv["wall_ms"]), execTime=float(kv["execTime"]),
                iters=int(kv["iters"]), nsteps=int(kv["nsteps"]),
                rbsteps=int(kv["rbsteps"]))
        except Exception:
            pass
    return out


def csv_last(csvpath):
    if not os.path.exists(csvpath): return None
    rows = P.rows(csvpath)
    if not rows: return None
    L = rows[-1]
    return dict(nApply=L.get("nApplyCalls", 0.0),
                nBuild=L.get("nBuildPC", 0.0),
                tApply=L.get("tApplyAccum", 0.0),
                tSetup=L.get("tSetupAll", 0.0))


def modes_rounds(pfx):
    ms, rs = set(), set()
    for f in glob.glob(os.path.join(P2, pfx + "_pc_*.csv")):
        m = re.match(re.escape(pfx) + r"_pc_(.+?)_r(\d+)\.csv$", os.path.basename(f))
        if m:
            ms.add(m.group(1)); rs.add(int(m.group(2)))
    return sorted(ms), sorted(rs)


try:
    import numpy as np
    NP = True
except Exception:
    NP = False

print("=" * 130)
print("★★★ 1. 数据收集：每 mode 的 nApply / nBuild / nStep / execTime")
print("=" * 130)
DATA = {}
for tag, logn, pfx, lvl, reff in CASES:
    log = parse_log(logn)
    ms, rs = modes_rounds(pfx)
    print("\n  ── %s  levels=%d  模型 r_eff=%.1f ──" % (tag, lvl, reff))
    print("  %-6s %8s %9s %9s %10s %9s %10s"
          % ("mode", "execTime", "iters", "nApply", "nBuild", "rbsteps", "tApply"))
    recs = []
    for M in ms:
        vals = []
        for R in rs:
            info = log.get((M, R))
            cs = csv_last(os.path.join(P2, "%s_pc_%s_r%d.csv" % (pfx, M, R)))
            if info and cs: vals.append((info, cs))
        if not vals: continue
        et = st.median([v[0]["execTime"] for v in vals])
        it = st.median([v[0]["iters"] for v in vals])
        na = st.median([v[1]["nApply"] for v in vals])
        nb = st.median([v[1]["nBuild"] for v in vals])
        rb = st.median([v[0]["rbsteps"] for v in vals])
        ta = st.median([v[1]["tApply"] for v in vals])
        nst = st.median([v[0]["nsteps"] for v in vals])
        recs.append((M, et, it, na, nb, rb, ta, nst))
        print("  %-6s %8.2f %9d %9.0f %9.0f %9.0f %10.4f"
              % (M, et, it, na, nb, rb, ta))
    DATA[tag] = recs

print()
print("=" * 130)
print("★★★ 2. 拟合 execTime = A·nApply + B·nBuild + C·nStep + D")
print("=" * 130)
FIT = {}
for tag, recs in DATA.items():
    if not NP or len(recs) < 4:
        print("  %-6s 样本不足" % tag); continue
    X = np.array([[r[3], r[4], r[7], 1.0] for r in recs])   # nApply, nBuild, nStep, 1
    y = np.array([r[1] for r in recs])
    sol, *_ = np.linalg.lstsq(X, y, rcond=None)
    A, B, C, D = [float(x) for x in sol]
    pred = X @ sol
    rms = float(np.sqrt(np.mean((pred - y)**2)))
    rel = 100.0*rms/float(np.mean(y))
    FIT[tag] = (A, B, C, D)
    print("  %-6s A=%.3e s/apply  B=%.4f s/build  C=%.4f s/step  D=%.3f  | RMS=%.2fs (%.1f%%)"
          % (tag, A, B, C, D, rms, rel))
    print("        B/A = %.1f  （每次分解相当于多少次 apply）" % (B/A if A else float("nan")))

print()
print("=" * 130)
print("★★★ 3. 排序对照：三种成本模型 vs 实测墙钟")
print("=" * 130)
for tag, recs in DATA.items():
    reff = dict((c[0], c[4]) for c in CASES)[tag]
    rk = {"l15": 53.7, "l20": 162.8, "fl30": 290.1}.get(tag)
    print("\n  ── %s ──" % tag)
    print("  %-6s %9s %9s %9s | %14s %14s %14s | %10s"
          % ("mode", "iters", "rbsteps", "nApply", "模型(iters+ρ·rb)",
             "校准(iters+R/k·rb)", "多元(拟合)", "实测墙钟"))
    rows = []
    for (M, et, it, na, nb, rb, ta, nst) in recs:
        mo = it + reff*rb
        ca = it + rk*rb if rk else float("nan")
        if tag in FIT:
            A, B, C, D = FIT[tag]
            mv = A*na + B*nb + C*nst + D
        else:
            mv = float("nan")
        rows.append((M, it, rb, na, mo, ca, mv, et*1000))
        print("  %-6s %9d %9d %9.0f | %14.0f %14.0f %14.3f | %9.0f ms"
              % (M, it, rb, na, mo, ca, mv, et*1000))
    mo_o = [r[0] for r in sorted(rows, key=lambda z: z[4])]
    ca_o = [r[0] for r in sorted(rows, key=lambda z: z[5])] if rk else []
    mv_o = [r[0] for r in sorted(rows, key=lambda z: z[6])] if tag in FIT else []
    wm_o = [r[0] for r in sorted(rows, key=lambda z: z[7])]
    print("     实测  : %s" % " < ".join(wm_o))
    print("     模型  : %s  %s" % (" < ".join(mo_o), "✓" if mo_o == wm_o else "★不一致"))
    if ca_o:
        print("     校准  : %s  %s" % (" < ".join(ca_o), "✓" if ca_o == wm_o else "★不一致"))
    if mv_o:
        print("     多元  : %s  %s" % (" < ".join(mv_o), "✓" if mv_o == wm_o else "★不一致"))

print()
print("=" * 130)
print("★★★ 4. 各成本分量占墙钟的比例（解释为什么线性形式不成立）")
print("=" * 130)
for tag, recs in DATA.items():
    print("\n  ── %s ──" % tag)
    print("  %-6s %10s %12s %12s %12s" % ("mode", "execTime", "decomp%", "apply%", "残差%"))
    for (M, et, it, na, nb, rb, ta, nst) in recs:
        dp = 100.0*ta/et if et else 0      # tApplyAccum 是 apply 的累计真实耗时
        # 用拟合的 B 估计分解耗时
        if tag in FIT:
            A, B, C, D = FIT[tag]
            dec = 100.0*(B*nb)/et if et else 0
        else:
            dec = float("nan")
        print("  %-6s %10.2f %11.1f%% %11.1f%% %11.1f%%"
              % (M, et, dec, dp, 100.0 - dec - dp))
print("=" * 130)
