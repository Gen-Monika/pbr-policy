#!/usr/bin/env python3
"""
★★★ cov2 产出体检：截断检测

动机：x3 的 K=20/K=30 在 cov2b.log 里显示 nsteps=759 / 365（期望 1231），
      且 wall_ms 恰好 = 3600xxx —— 被脚本里的 `timeout 3600` 杀掉了。

截断的危害分两层，必须分开判断：
  (A) 运行本身是否损坏：CSV 与 log 步数是否一致、最后一行是否残行
  (B) 对表格的影响：截断的 K 只贡献 t 的前缀，会在大年龄处造成缺口

本脚本对每个文件给出：
  - CSV 唯一步数 / log 步数 / 是否一致
  - 是否是完整运行（对照该配置的基准步数）
  - 最后一行是否合法（25 字段）
  - 重建次数与 BASE + (n-BASE)/K 的吻合度
  - 该文件能贡献的 t 范围与年龄范围
"""
import sys, os
import statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → (基准步数, BASE, {K: (csv, logdir)}, 轮数)
SPEC = {
    "l15":  (344, 100, {"cov2_l15": [13, 20, 30]}, [1, 2, 3]),
    "fine": (720, 100, {"cov2_fine": [13, 20, 30]}, [1, 2, 3]),
    "x3":   (1231, 100, {"cov2_x3": [13, 20, 30]}, [1, 2, 3]),
    "fl30": (720, 100, {"cov2_fl30": [8, 13, 20, 30]}, [1, 2, 3]),
    "sth":  (5866, 50, {"stefan": [1, 2, 3, 5, 8, 13], "cov2_sth": [20, 30]}, [1, 2, 3]),
}

print("=" * 132)
print("★★★ cov2 产出体检（截断 / 一致性 / 覆盖）")
print("=" * 132)

bad = []
for tag, (base_n, base, dirs, rounds) in SPEC.items():
    print("\n" + "#" * 132)
    print("#  [%s]  基准步数=%d  BASE=%d" % (tag, base_n, base))
    print("#" * 132)
    print("  %-34s %8s %8s %6s %9s %9s %10s  %s"
          % ("文件", "CSV步", "log步", "一致", "重建", "期望重建", "t范围", "判定"))

    for logdir_k, Ks in dirs.items():
        logdir = os.path.join(P2, logdir_k)
        if not os.path.isdir(logdir):
            print("     ★ 目录不存在: %s" % logdir); continue
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (logdir_k, K, R))
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not os.path.exists(c):
                    continue
                if not os.path.exists(l):
                    print("     %-34s ★ 缺 log" % os.path.basename(c)); continue

                # CSV 步数
                rr = P.rows(c)
                seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                nstep = len(seen)
                nrb = sum(1 for t in seen if int(seen[t]["reused"]) == 0)

                # log 步数
                nl = len(P.per_step_N(l))
                same = "OK" if nstep == nl else "★否"

                # 最后一行是否合法（残行检测）
                with open(c, errors="ignore") as f:
                    lines = f.read().split("\n")
                lines = [x for x in lines if x.strip()]
                lastf = len(lines[-1].split(","))

                exp_rb = base + max(0, (nstep - base))/float(K)
                rb_ok = abs(nrb - exp_rb) <= max(3, 0.03*exp_rb)

                short = nstep < base_n
                verdict = "完整" if not short else "★截断 %d/%d" % (nstep, base_n)
                if not rb_ok:
                    verdict += " ★K不自洽(%.0f)" % exp_rb
                if lastf != 25:
                    verdict += " ★残行(%d字段)" % lastf

                print("     %-34s %8d %8d %6s %9d %9.0f %10s  %s"
                      % (os.path.basename(c), nstep, nl, same, nrb, exp_rb,
                         "1..%d" % nstep, verdict))

                if short or not rb_ok or lastf != 25:
                    bad.append((tag, os.path.basename(c), nstep, base_n, lastf))

print("\n" + "=" * 132)
print("★★★ 截断 / 异常清单")
print("=" * 132)
if bad:
    for tag, name, n, base_n, lastf in bad:
        print("   %-6s %-34s 步 %d/%d (%.0f%%)  末行字段=%d"
              % (tag, name, n, base_n, 100.0*n/base_n, lastf))
else:
    print("   无")
print("=" * 132)
