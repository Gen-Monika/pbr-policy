#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B0 扫描的批次统计：同一配置在 B0=50 / B0=100 下各 8 轮的跨轮分散度。

用途：这是**负面结论**的证据——把预热拉长并没有让跨轮分散度变小，
样本里 B0=100 的方差反而更大（iters 43003 vs 6487）；且同配置两批之间的方差比
（16.2 倍）远高于两个 B0 之间的差，说明这些批次的分散主要由批次效应主导。

★ 因此本脚本的输出**不能**当作“B0 越大越稳定/越不稳定”的因果证据：
  n=8、批次非交错（先跑完一批再跑另一批）、且两批之间存在其它环境变化。
  历史上用 n=3 的跨轮极差（152）论证预热收益，已被 8 轮实测证伪（实际 17–55）。

输入：OpenFOAM 日志与 pc CSV 的命名约定
  <PBR_ROOT>/<TAG>_case/log.ONLs.r<R>        （R = 1..NROUND）
  <PBR_ROOT>/<TAG>_pc_ONLs_r<R>.csv          （列 0 = timeIndex，列 8 = reused）
路径由 --root / --tag 给出，脚本内不含硬编码路径。

用法：
  python3 b0_pilot_stats.py --root /root/autodl-tmp/PBR --tags p2sthB50 p2sthB100
"""
import argparse
import csv
import math
import os
import random
import re
import statistics as st

IRE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")


def iters(log):
    s = 0
    with open(log, errors="ignore") as fh:
        for ln in fh:
            m = IRE.search(ln)
            if m:
                s += int(m.group(1))
    return s


def nrb(pc):
    if not os.path.exists(pc):
        return None
    seen = set()
    with open(pc, errors="ignore") as fh:
        for row in csv.reader(fh):
            try:
                if int(row[8]) == 0:
                    seen.add(int(row[0]))
            except Exception:
                pass
    return len(seen)


def collect(root, tag, nround):
    its, rbs = [], []
    for R in range(1, nround + 1):
        f = os.path.join(root, "%s_case" % tag, "log.ONLs.r%d" % R)
        if os.path.exists(f):
            its.append(iters(f))
        b = nrb(os.path.join(root, "%s_pc_ONLs_r%d.csv" % (tag, R)))
        if b:
            rbs.append(b)
    return its, rbs


def boot_var(v, n=20000, seed=1):
    rnd = random.Random(seed)
    k = len(v)
    out = []
    for _ in range(n):
        s = [v[rnd.randrange(k)] for _ in range(k)]
        out.append(st.variance(s))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n)]


def f_test(v1, v2):
    """双侧方差齐性检验，log-F 正态近似；返回 (F, z, p)。"""
    s1, s2 = st.variance(v1), st.variance(v2)
    df1, df2 = len(v1) - 1, len(v2) - 1
    mu = math.log(s1 / s2)
    var = 2.0 / df1 + 2.0 / df2
    z = abs(mu) / math.sqrt(var)
    p = math.erfc(z / math.sqrt(2))
    return max(s1 / s2, s2 / s1), z, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="PBR 根目录（含 <TAG>_case 与 pc CSV）")
    ap.add_argument("--tags", nargs=2, default=["p2sthB50", "p2sthB100"],
                    metavar=("TAG_A", "TAG_B"))
    ap.add_argument("--rounds", type=int, default=8)
    a = ap.parse_args()

    data = {t: collect(a.root, t, a.rounds) for t in a.tags}
    for label, idx in (("iters", 0), ("rebuild", 1)):
        print("=" * 78)
        print("统计量：%s" % label)
        print("=" * 78)
        for t in a.tags:
            v = data[t][idx]
            if len(v) < 2:
                print("  %-10s 样本不足（n=%d）" % (t, len(v)))
                continue
            print("  %-10s n=%d mean=%.2f var=%.1f sd=%.2f CV=%.5f"
                  % (t, len(v), st.mean(v), st.variance(v), st.stdev(v),
                     st.stdev(v) / st.mean(v)))
            print("            样本: %s" % v)
            lo, hi = boot_var(v)
            print("            var 的 95%% bootstrap CI: [%.1f, %.1f]" % (lo, hi))
        A, B = data[a.tags[0]][idx], data[a.tags[1]][idx]
        if len(A) >= 2 and len(B) >= 2:
            F, z, p = f_test(A, B)
            print("  方差比 F=%.3f  log-F z=%.2f  p≈%.4f  -> %s"
                  % (F, z, p, "差异显著" if p < 0.05 else "差异不显著"))
            sa, sb = st.variance(A), st.variance(B)
            se = math.sqrt(sa / len(A) + sb / len(B))
            print("  均值差（Welch）: %.2f  se=%.2f  相对差 %+.2f%%"
                  % (st.mean(B) - st.mean(A), se, 100 * (st.mean(B) / st.mean(A) - 1)))
        print()
    print("解读限制：n=%d、批次非交错、批间存在其它环境变化；" % a.rounds)
    print("p 值只能说明这两批样本的分散不同，不能单独识别 B0 的作用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
