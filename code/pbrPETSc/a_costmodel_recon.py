#!/usr/bin/env python3
"""
★★★ 成本模型核查：模型的 regret 为何与实测墙钟排序不一致

═══ 问题 ═══
  l15：模型 在线−K* = +3.36 pp，实测 在线 vs K3 打平（−0.3%）
  l20：模型 在线−K* = +4.72 pp，实测 在线【优于全部固定周期】1.08%
  ⇒ l20 的模型 regret【更大】但实测【更好】——排序反转。

═══ 待检验的假设 ═══
模型的成本 = 迭代数 + r_eff × 重建次数
             其中 r_eff = s × (tPCSetup / tIter_bench)
实测墙钟 = 分解 + 每次求解固定开销 + 迭代 + 其他物理

若 in-run 的每次迭代成本 k ≠ tIter_bench，则模型的
"重建代价/迭代代价" 比值就错了，regret 随之失真。

具体地：
  真实「重建相对代价」 = s·tPCSetup / k
  模型「重建相对代价」 = s·tPCSetup / tIter_bench = r_eff
  修正因子             = tIter_bench / k

若 tIter_bench < k（基准测量偏快），则 r_eff 被【低估】→ 模型以为重建便宜
若 tIter_bench > k（基准偏慢），则 r_eff 被【高估】→ 模型以为重建贵
                                          ⇒ 模型会过度惩罚"多重建"的策略
                                          而在线策略恰好多重建（221 vs K3 的 181）

本脚本：
  1. 列出每次运行的内建时序分量，核对它们与 execTime 是否闭合
  2. 最小二乘拟合 execTime = k·iters + R·rbsteps + c，得到 k 与 R
  3. 比较 R/k 与模型的 r_eff
  4. 用拟合出的成本重算 regret，与实测墙钟排序对照
"""
import sys, os, glob, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

CFGS = [
    ("l15",  "a2l15.log", "a2l15", 15, 232.4),
    ("l20",  "a2A.log",   "a2A",   20, 271.0),
    ("fl30", "a2B.log",   "a2B",   30, 440.6),
]


def parse_a2log(path):
    """解析 a2_run_v2.sh 的 round= 行"""
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
                rbsteps=int(kv["rbsteps"]), fatal=int(kv["fatal"]))
        except Exception:
            pass
    return out


def find_modes(pfx):
    modes = {}; rounds = set()
    for f in glob.glob(os.path.join(P2, pfx + "_pc_*.csv")):
        m = re.match(re.escape(pfx) + r"_pc_(.+?)_r(\d+)\.csv$",
                     os.path.basename(f))
        if m:
            modes.setdefault(m.group(1), 0)
            rounds.add(int(m.group(2)))
    return sorted(modes), sorted(rounds)


def csv_comp(path):
    if not os.path.exists(path): return None
    rows = P.rows(path)
    if not rows: return None
    last = rows[-1]
    ti = [x["tIter"] for x in rows if x["tIter"] > 0]
    rr = [x["r"] for x in rows if x["r"] > 0]
    ta = [x["tAssemble"] for x in rows if x["tAssemble"] > 0]
    tp = [x["tPCSetup"] for x in rows if x["tPCSetup"] > 0]
    return dict(nrows=len(rows),
                nBuild=last.get("nBuildPC", 0.0),
                tSetupAll=last.get("tSetupAll", 0.0),
                nApply=last.get("nApplyCalls", 0.0),
                tApply=last.get("tApplyAccum", 0.0),
                tIter=st.median(ti) if ti else 0.0,
                r=st.median(rr) if rr else 0.0,
                tAssemble=st.median(ta) if ta else 0.0,
                tPCSetup=st.median(tp) if tp else 0.0,
                first_tSetupAll=rows[0].get("tSetupAll", 0.0),
                first_nBuild=rows[0].get("nBuildPC", 0.0))


print("=" * 134)
print("★★★ 1. 逐运行的时序分量（CSV 内建计时，单位 秒）")
print("=" * 134)
DATA = {}
for tag, logname, pfx, lvl, reff in CFGS:
    runs = parse_a2log(logname)
    if not runs:
        print("\n  [%s] 无日志 %s" % (tag, logname)); continue
    modes, rounds = find_modes(pfx)
    print("\n  ── %s  levels=%d  模型 r_eff=%.1f ──" % (tag, lvl, reff))
    print("  %-6s %3s %9s %8s %8s | %9s %7s %9s %7s | %10s %9s"
          % ("mode", "轮", "execTime", "iters", "rbsteps",
             "tSetupAll", "nBuild", "tApply", "nApply", "tIter_bench", "tPCSetup"))
    for M in modes:
        for R in rounds:
            info = runs.get((M, R))
            cs = csv_comp(os.path.join(P2, "%s_pc_%s_r%d.csv" % (pfx, M, R)))
            if not info or not cs: continue
            DATA.setdefault(tag, []).append((M, R, info, cs))
            print("  %-6s %3d %9.2f %8d %8d | %9.4f %7.0f %9.4f %7.0f | %10.7f %9.7f"
                  % (M, R, info["execTime"], info["iters"], info["rbsteps"],
                     cs["tSetupAll"], cs["nBuild"], cs["tApply"], cs["nApply"],
                     cs["tIter"], cs["tPCSetup"]))

# ---------- 闭合检查 ----------
print()
print("=" * 134)
print("★★★ 2. 时序闭合检查：tSetupAll + tApply + iters×tIter 是否解释 execTime")
print("=" * 134)
print("  %-6s %3s %-6s %9s | %9s %9s %9s | %9s %8s"
      % ("配置", "轮", "mode", "execTime", "decomp", "apply", "iter×tIter", "残差", "残差%"))
for tag in DATA:
    for (M, R, info, cs) in DATA[tag]:
        if R != 1: continue
        decomp = cs["tSetupAll"]
        apply_ = cs["tApply"]
        itert = info["iters"] * cs["tIter"]
        resid = info["execTime"] - decomp - apply_ - itert
        print("  %-6s %3d %-6s %9.2f | %9.4f %9.4f %9.4f | %9.4f %7.1f%%"
              % (tag, R, M, info["execTime"], decomp, apply_, itert,
                 resid, 100.0*resid/info["execTime"]))

# ---------- 最小二乘拟合 ----------
print()
print("=" * 134)
print("★★★ 3. 最小二乘：execTime = k·iters + R·rbsteps + c")
print("=" * 134)
try:
    import numpy as np
    HAVE_NP = True
except Exception:
    HAVE_NP = False

FIT = {}
print("  %-6s %12s %14s %12s %14s | %s"
      % ("配置", "k (s/迭代)", "R (s/重建步)", "c (s)", "R/k (迭代当量)", "残差 RMS"))
for tag in DATA:
    recs = DATA[tag]
    if len(recs) < 3: continue
    # 按 (mode) 取中位，避免同 mode 多轮的噪声重复计权
    bym = {}
    for (M, R, info, cs) in recs:
        bym.setdefault(M, []).append((info["iters"], info["rbsteps"], info["execTime"]))
    pts = [(st.median([x[0] for x in v]), st.median([x[1] for x in v]),
            st.median([x[2] for x in v])) for v in bym.values()]
    if len(pts) < 3:
        print("  %-6s 只有 %d 个 mode，无法拟合 3 参数" % (tag, len(pts))); continue
    if HAVE_NP:
        A = np.array([[p[0], p[1], 1.0] for p in pts])
        b = np.array([p[2] for p in pts])
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        k, Rr, c = float(sol[0]), float(sol[1]), float(sol[2])
        pred = A @ sol
        rms = float(np.sqrt(np.mean((pred - b)**2)))
    else:
        continue
    FIT[tag] = (k, Rr, c)
    print("  %-6s %12.6f %14.4f %12.4f %14.1f | %.4f s"
          % (tag, k, Rr, c, (Rr/k if k else float("nan")), rms))

# ---------- 与模型 r_eff 比较 ----------
print()
print("=" * 134)
print("★★★ 4. 关键比较：真实「重建相对代价」 vs 模型 r_eff")
print("=" * 134)
print("  模型 r_eff = s × (tPCSetup / tIter_bench)")
print("  真实 R/k   = (每次重建步的分解秒数) / (每次迭代秒数)")
print()
print("  %-6s %10s %14s %14s %10s   %s"
      % ("配置", "s", "模型 r_eff", "真实 R/k", "比值", "含义"))
for tag, logname, pfx, lvl, reff in CFGS:
    if tag not in FIT: continue
    recs = DATA[tag]
    cs0 = recs[0][3]
    s_est = 3.0
    for (M, R, info, cs) in recs:
        if info["rbsteps"] > 0 and M == "K1":
            s_est = cs["nBuild"]/info["rbsteps"]
            break
    k, Rr, c = FIT[tag]
    true_r = Rr/k if k else float("nan")
    ratio = true_r/reff if reff else float("nan")
    verdict = "一致" if abs(ratio-1) < 0.2 else \
              ("★模型【高估】重建代价 %.1fx → 过度惩罚多重建" % ratio if ratio > 1
               else "★模型【低估】重建代价 %.1fx" % ratio)
    print("  %-6s %10.2f %14.1f %14.1f %10.2f   %s"
          % (tag, s_est, reff, true_r, ratio, verdict))

# ---------- 用两种成本重算 regret 并比排序 ----------
print()
print("=" * 134)
print("★★★ 5. 排序对照：模型成本 vs 拟合成本 vs 实测墙钟")
print("=" * 134)
for tag in DATA:
    if tag not in FIT: continue
    k, Rr, c = FIT[tag]
    reff = dict((t, r) for t, _, _, _, r in CFGS)[tag]
    bym = {}
    for (M, R, info, cs) in DATA[tag]:
        bym.setdefault(M, []).append(info)
    print("\n  ── %s  (k=%.6f s/迭代, R=%.4f s/重建步) ──" % (tag, k, Rr))
    print("  %-6s %8s %8s | %14s %14s | %10s %10s"
          % ("mode", "iters", "rbsteps", "模型成本", "拟合成本(ms)", "实测墙钟", "实测/拟合"))
    rows_ = []
    for M in sorted(bym):
        infos = bym[M]
        it = st.median([x["iters"] for x in infos])
        rb = st.median([x["rbsteps"] for x in infos])
        wm = st.median([x["wall_ms"] for x in infos])
        model = it + reff*rb
        fitms = 1000.0*(k*it + Rr*rb + c)
        rows_.append((M, it, rb, model, fitms, wm))
    for (M, it, rb, model, fitms, wm) in rows_:
        print("  %-6s %8d %8d | %14.0f %14.0f | %9d ms %10.3f"
              % (M, it, rb, model, fitms, wm, wm/fitms))
    # 排序
    mo = [M for M, *_ in sorted(rows_, key=lambda z: z[3])]
    fo = [M for M, *_ in sorted(rows_, key=lambda z: z[4])]
    wo = [M for M, *_ in sorted(rows_, key=lambda z: z[5])]
    print("    模型排序(快→慢): %s" % " < ".join(mo))
    print("    拟合排序(快→慢): %s" % " < ".join(fo))
    print("    实测排序(快→慢): %s" % " < ".join(wo))
    print("    ⇒ 拟合 vs 实测 %s ；模型 vs 实测 %s"
          % ("一致 ✓" if fo == wo else "★不一致",
             "一致 ✓" if mo == wo else "★不一致"))
print("=" * 134)
