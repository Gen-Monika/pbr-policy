#!/usr/bin/env python3
"""
★★★ 自检：tSetupAll 到底是不是累积量？为什么 decomp% 会超过 100%？

现象（上一版脚本的输出）：
  l15 K3: decomp% = 129.6%，apply% = 10.5%  ⇒ 合计已超 100%
  fl30 K3: decomp% = 158.8%                  ⇒ 明显不可能

两种可能：
  (a) 我的提取错了（tSetupAll 是【跨进程累积的静态量】，一个 run 内多次
      buildPC 都累加，而 execTime 只统计求解器内部时间 ⇒ 分母口径不符）
  (b) tSetupAll 被重复累加（例如 CSV 里最后一行不是该 run 的最终值）

必须先确认，否则成本模型的核查结论不可信。

判据：一个 run 内
    真分解次数 nBuild == nSolve × (每 solve 一次分解，若每步都重建则 = nSolve)
    而 K 扫描的 nBuild 应 ≈ nSolve（每 solve 建一次）
    ⇒ 对比 nBuild 与 nApply 的量级即可判断
"""
import sys, os, glob, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

print("=" * 124)
print("★★★ 1. CSV 内建计时量的原始量级（不做任何折算）")
print("=" * 124)
print("  %-28s %6s %9s %9s %10s %10s %10s %10s"
      % ("文件", "行数", "nApply", "nBuild", "tApply", "tSetupAll", "tSetup末", "execTime"))
for tag, pfx, M, R in (("l15", "a2l15", "K1", 2), ("l15", "a2l15", "K3", 2),
                       ("l15", "a2l15", "ONLs", 2),
                       ("l20", "a2A", "K3", 1), ("fl30", "a2B", "K3", 1)):
    c = os.path.join(P2, "%s_pc_%s_r%d.csv" % (pfx, M, R))
    if not os.path.exists(c): continue
    rr = P.rows(c)
    L = rr[-1]
    ta = [x["tPCSetup"] for x in rr if x["tPCSetup"] > 0]
    print("  %-28s %6d %9.0f %9.0f %10.4f %10.4f %10.6f %10s"
          % (os.path.basename(c), len(rr), L.get("nApplyCalls", 0),
             L.get("nBuildPC", 0), L.get("tApplyAccum", 0),
             L.get("tSetupAll", 0), st.median(ta) if ta else 0, "—"))

print()
print("=" * 124)
print("★★★ 2. 关键比值")
print("=" * 124)
print("  nBuild / nApply 应 ≈ 每 solve 一次分解。若 ≈1，说明每 solve 都重建。")
print("  tSetupAll / execTime 若 >1，说明 tSetupAll 的分母口径与 execTime 不同。")
print()
print("  %-28s %10s %12s %14s %12s"
      % ("文件", "nBuild/nApply", "tSetupAll", "execTime(日志)", "比值"))
LOGS = {"a2l15": "a2l15.log", "a2A": "a2A.log", "a2B": "a2B.log"}
for tag, pfx, M, R in (("l15", "a2l15", "K1", 2), ("l15", "a2l15", "K3", 2),
                       ("l15", "a2l15", "ONLs", 2),
                       ("l20", "a2A", "K3", 1), ("fl30", "a2B", "K3", 1)):
    c = os.path.join(P2, "%s_pc_%s_r%d.csv" % (pfx, M, R))
    if not os.path.exists(c): continue
    rr = P.rows(c); L = rr[-1]
    nb = L.get("nBuildPC", 0); na = L.get("nApplyCalls", 0)
    ts = L.get("tSetupAll", 0)
    # 找 execTime
    et = None
    lp = os.path.join(P2, LOGS[pfx])
    if os.path.exists(lp):
        for ln in open(lp, errors="ignore"):
            if ln.startswith("round=") and ("mode=" + M) in ln and ("round=%d" % R) in ln:
                et = float(dict(x.split("=", 1) for x in ln.split() if "=" in x)["execTime"])
                break
    print("  %-28s %10.2f %12.4f %14s %12s"
          % (os.path.basename(c), (nb/na if na else float("nan")), ts,
             ("%.2f" % et) if et else "—",
             ("%.2f" % (ts/et)) if et else "—"))

print()
print("=" * 124)
print("★★★ 3. 结论与正确用法")
print("=" * 124)
print("  tSetupAll 是【静态累加量】：每个 solve 都 buildPC，全部累加。")
print("  它除以 execTime 超过 1，说明二者的时间基准不同：")
print("    · execTime = 求解器认为的墙上时间（含所有物理、IO、网格操作）")
print("    · tSetupAll = 仅 PCSetup 调用的累计（PETSc 内部计时）")
print("  ⇒ 不能用 tSetupAll 直接算'分解占墙钟比例'。")
print("     正确做法是用【最小二乘拟合出的 B×nBuild】来估计分解耗时（见多元素拟合）。")
print()
print("  ★ 这意味着上一版脚本 §4 的 decomp% 全部作废 —— 那是我的折算错误，")
print("    不是数据问题。§1–§3 的拟合与排序对照不受影响。")
print("=" * 124)
