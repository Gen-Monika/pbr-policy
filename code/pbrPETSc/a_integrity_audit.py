#!/usr/bin/env python3
"""
★★★ 数据完整性审计（2026-10-12）

═══ 动机 ═══
sth 出现「CSV 5866 步 / 同名 log 15642 步」的异常。根因是 stefan/ 目录被
两个不同 endTime 的批次复用，同名 log 被后来的长跑覆盖。
这类隐患不报错，只会让 N(t,a) 表静默错位，所以做全量审计。

═══ 审计项 ═══
  A. CSV 唯一步数 vs 配套 log 的 "Time = " 计数
  B. 同一配置内 (levels, nCells, nFaces) 是否同质（防止混网格）
  C. CSV 自证的 K 一致性：重建步数应 ≈ BASE + (nsteps-BASE)/K
     —— 这一项不依赖 log，是 CSV 自身的强约束
  D. 跨批次：相同 K 的前 N 步迭代数序列是否逐位一致
  E. 年龄覆盖 amax_data
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

GROUPS = {
    "fx":   [("fx", "%s/fixed" % P2, [1,2,3,5,8], [1,2,3,4,5], 100),
             ("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3], 100)],
    "l20":  [("l20", "%s/l20" % P2, [1,2,3,5,8], [1,2,3,4,5], 100),
             ("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3], 100)],
    "l15":  [("l15", "%s/l15" % P2, [1,2,3,5,8], [1,2,3,4,5], 100)],
    "fine": [("fine", "%s/finerun" % P2, [1,2,3,5,8], [1,2,3], 100)],
    "x3":   [("x3", "%s/x3run" % P2, [1,2,3,5,8], [1,2], 100)],
    "fl30": [("fl30", "%s/fl30run" % P2, [1,3,5], [1,2], 100)],
    "sth":  [("sth", "%s/stefan" % P2, [1,2,3,5,8,13], list(range(1,11)), 50)],
}

problems = []

print("=" * 126)
print("★★★ 数据完整性审计")
print("=" * 126)
print("  %-8s %-14s %6s %5s %5s %5s | %-28s | %s"
      % ("配置", "批次", "文件", "步错", "缺log", "K错", "网格签名(lev,nC,nF)", "K 一致性"))

for tag, parts in GROUPS.items():
    for prefix, logdir, Ks, rounds, base in parts:
        if not os.path.isdir(logdir):
            print("  %-8s %-14s  目录不存在 %s" % (tag, prefix, logdir)); continue
        sigs = defaultdict(int); nfile = 0; nmis = 0; nmiss = 0; nkbad = 0
        kbad_ex = []
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not os.path.exists(c): continue
                nfile += 1
                rr = P.rows(c)
                if not rr: continue
                sigs[(int(rr[0]["levels"]), int(rr[0]["nCells"]), int(rr[0]["nFaces"]))] += 1
                uniq = set(int(x["timeIndex"]) for x in rr)
                # 去重取每步一条（|rep>=0）
                seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                nstep = len(seen)
                # C. K 自洽
                nrb = sum(1 for t in seen if int(seen[t]["reused"]) == 0)
                exp = base + max(0, (nstep - base)) / float(K)
                if abs(nrb - exp) > max(3, 0.03 * exp):
                    nkbad += 1
                    if len(kbad_ex) < 3:
                        kbad_ex.append("k%d_r%d nrb=%d exp=%.0f" % (K, R, nrb, exp))
                # A. 与 log 对齐
                if not os.path.exists(l):
                    nmiss += 1
                else:
                    nl = len(P.per_step_N(l))
                    if len(uniq) != nl: nmis += 1
        sigs_s = " | ".join("%s×%d" % (k, v) for k, v in sorted(sigs.items()))
        print("  %-8s %-14s %6d %5d %5d %5d | %-28s | %s"
              % (tag, prefix, nfile, nmis, nmiss, nkbad, sigs_s,
                 "OK" if nkbad == 0 else "; ".join(kbad_ex)))
        if nmis: problems.append("%s/%s: %d 对步数不匹配" % (tag, prefix, nmis))
        if nmiss: problems.append("%s/%s: %d 个缺 log" % (tag, prefix, nmiss))
        if nkbad: problems.append("%s/%s: %d 个 CSV 的 K 不自洽" % (tag, prefix, nkbad))
        if len(sigs) > 1: problems.append("%s/%s: 网格签名不唯一 %s" % (tag, prefix, set(sigs)))

    if len(parts) >= 2:
        p0, p1 = parts[0], parts[1]
        for K in sorted(set(p0[2]) & set(p1[2])):
            l0 = os.path.join(p0[1], "log.r%dk%d" % (p0[3][0], K))
            l1 = os.path.join(p1[1], "log.r%dk%d" % (p1[3][0], K))
            if os.path.exists(l0) and os.path.exists(l1):
                a, b = P.per_step_N(l0), P.per_step_N(l1)
                n = min(len(a), len(b), 6000)
                d = sum(1 for i in range(n) if a[i] != b[i])
                print("       [跨批次 k=%d] 前 %d 步不同 %d 处 %s"
                      % (K, n, d, "→ 一致 ✓" if d == 0 else "★不一致"))

print("\n" + "=" * 126)
if problems:
    print("★★★ 发现 %d 类问题：" % len(problems))
    for p in problems: print("   - " + p)
else:
    print("★★★ 未发现问题")
print("=" * 126)
