#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ux 迭代触顶统计：smoothSolver 的迭代数达到 maxIter=50 的次数，
以及其中末残差仍未达到 1e-7 的次数。

用途：论文 §8 里 sth 的边界证据之一——Ux 在部分时间步迭代触顶，
说明“模型给出的 N(t,a)”在这些步上是被求解器上限截断的量，
不是收敛所需的真实工作量。

用法：
  python3 b_ux_cap.py <OpenFOAM 日志...>
  日志路径由调用方给出（通常是 PBR_ROOT 下的 sthB100k_case/log.K* / sthB100a_case/log.*），
  本脚本不含任何硬编码路径。

说明：RE 只匹配 stdout 里 smoothSolver 的汇总行；被截断的步计为“触顶”，
      末残差 > tol 计入“未达容差”。maxIter=50 是 fvSolution 的设定值，非通用常数。
"""
import re
import sys

RE = re.compile(r"Solving for (Ux|Uy),\s*Initial residual = ([0-9.eE+-]+),\s*"
                r"Final residual = ([0-9.eE+-]+),\s*No Iterations (\d+)")
MAXITER = 50
TOL = 1e-7


def cap(path, var="Ux", limit=MAXITER, tol=TOL):
    """返回 (触顶次数, 其中末残差 > tol 的次数, 总求解次数)。"""
    hit = bad = total = 0
    with open(path, errors="ignore") as fh:
        for ln in fh:
            m = RE.search(ln)
            if not m or m.group(1) != var:
                continue
            total += 1
            if int(m.group(4)) >= limit:
                hit += 1
                if float(m.group(3)) > tol:
                    bad += 1
    return hit, bad, total


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    print("%-52s %6s %6s %8s" % ("log", "触顶", "未达容差", "Ux求解数"))
    print("-" * 78)
    for p in argv[1:]:
        hit, bad, tot = cap(p)
        print("%-52s %6d %6d %8d" % (p.split("/")[-1], hit, bad, tot))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
