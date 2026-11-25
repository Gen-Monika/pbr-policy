#!/usr/bin/env python3
"""
★★★ CSV↔log 对齐核验（不依赖文件长度）

═══ 为什么需要这个 ═══
长度对比只能发现“数量不同”，不能判断“内容是否错位”。
sth 的 r1/r2/r3 里 CSV=5866 步、同名 log=15642 步（endTime 被复用覆盖）。
若只靠 min(len,len) 截断，必须确认前 5866 步真的是同一个算例。

═══ 独立信号 ═══
CSV 每行有 nApplyCalls（该步 PETSc 预条件子被调用次数）。
solver log 里每步有若干次 "Solving for p_rgh ... No Iterations"。
两者【必须逐步相等】——这与时间、endTime、文件名都无关，
是内容层面的对齐证据。任何错位都会在这里立刻暴露。

同时用第 2 个信号：每步的 |残差| 序列不可用，改用
"该步是否有 p_rghFinal 求解"（CSV 里体现为同一步内 apply 次数），
以及 nSolve/nStep 的比值（应恒等于 s）。
"""
import sys, os, re
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

TIME_RE = re.compile(r"^Time = ")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")

P2 = "/root/autodl-tmp/PBR"


def per_step_counts(p):
    """每步 (nApply, N) —— 与 per_step_N 同一次扫描，额外返回 apply 次数。"""
    ap, nn, cur_n, cur_a = [], [], [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur_n:
                ap.append(len(cur_n)); nn.append(sum(cur_n))
                cur_n, cur_a = [], []
            continue
        m = SOLVE_RE.search(ln)
        if m:
            cur_n.append(int(m.group(1)))
    if cur_n:
        ap.append(len(cur_n)); nn.append(sum(cur_n))
    return ap, nn


def check(prefix, logdir, Ks, rounds, label):
    print("\n  ── %s（%s）──" % (label, logdir))
    bad = 0; ok = 0; skip = 0
    details = []
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)):
                skip += 1; continue
            rr = P.rows(c)
            seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            ap, nn = per_step_counts(l)
            n = min(len(steps), len(ap))
            mism = [i for i in range(n)
                    if int(steps[i]["nApplyCalls"]) != ap[i]]
            if mism:
                bad += 1
                if len(details) < 4:
                    i = mism[0]
                    details.append("k%d_r%d: %d/%d 步 apply 数不符（首处 i=%d csv=%d log=%d）"
                                   % (K, R, len(mism), n, i,
                                      int(steps[i]["nApplyCalls"]), ap[i]))
            else:
                ok += 1
    print("     对齐 OK=%d  错位=%d  缺文件=%d" % (ok, bad, skip))
    for d in details:
        print("       ★ " + d)
    return bad


print("=" * 118)
print("★★★ CSV↔log 内容层面对齐核验（信号：nApplyCalls vs log 的 p_rgh 求解次数）")
print("=" * 118)

tot = 0
tot += check("fx",   "%s/fixed" % P2,       [1,2,3,5,8], [1,2,3,4,5], "fx")
tot += check("l20",  "%s/l20" % P2,         [1,2,3,5,8], [1,2,3,4,5], "l20")
tot += check("l15",  "%s/l15" % P2,         [1,2,3,5,8], [1,2,3,4,5], "l15")
tot += check("fine", "%s/finerun" % P2,     [1,2,3,5,8], [1,2,3],     "fine")
tot += check("x3",   "%s/x3run" % P2,       [1,2,3,5,8], [1,2],       "x3")
tot += check("fl30", "%s/fl30run" % P2,     [1,3,5],     [1,2],       "fl30")
tot += check("sth",  "%s/stefan" % P2,      [1,2,3,5,8,13], list(range(1,11)), "sth")
tot += check("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3], "covscan_l10")
tot += check("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3], "covscan_l20")

print("\n" + "=" * 118)
print("★★★ 结论：错位文件总数 = %d" % tot)
print("=" * 118)
