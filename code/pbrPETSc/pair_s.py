#!/usr/bin/env python3
"""逐轮配对：s=3 这轮扫描的 K* 是否稳定？与上一轮 fx.out 对比。"""
import re, statistics as st
from collections import defaultdict

WL = re.compile(r"s=(\d+)\s+round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+")
byS = defaultdict(lambda: defaultdict(dict))
for ln in open("s_scan.out"):
    m = WL.search(ln)
    if m:
        byS[int(m.group(1))][int(m.group(2))][int(m.group(3))] = int(m.group(4))/1000.0

for S in sorted(byS):
    ks = sorted({k for r in byS[S].values() for k in r})
    print("=" * 96)
    print("  s=%d  逐轮墙钟（秒）" % S)
    print("  " + "%4s" % "轮" + "".join("%8s" % ("K=%d" % k) for k in ks) + "%12s" % "该轮最优")
    wins = defaultdict(int)
    for r in sorted(byS[S]):
        d = byS[S][r]
        if len(d) < len(ks):
            continue
        bk = min(d, key=lambda k: d[k])
        wins[bk] += 1
        print("  " + "%4d" % r + "".join("%8.2f" % d[k] for k in ks) + "%12s" % ("K=%d" % bk))
    print("  ⇒ 各 K 夺冠次数: " + ", ".join("K=%d:%d" % (k, wins[k]) for k in sorted(wins)))
    # 配对：每个候选 K 与 K=1 的逐轮比较
    print("  -- 与 K=1 的逐轮配对 --")
    for k in ks:
        if k == 1: continue
        ds = [byS[S][r][k]/byS[S][r][1]-1 for r in sorted(byS[S])
              if len(byS[S][r]) == len(ks)]
        better = sum(1 for x in ds if x < 0)
        print("     K=%2d vs K=1: 中位 %+7.2f%%   优于K=1 的轮数 %d/%d   [%s]"
              % (k, st.median(ds)*100, better, len(ds),
                 " ".join("%+.1f%%" % (x*100) for x in ds)))

# 与 fx.out（上一轮 s=3, levels=10）对比
print()
print("=" * 96)
print("  ★ 与上一轮 fx.out（同为 s=3, levels=10）的对比")
FX = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")
old = defaultdict(dict)
try:
    for ln in open("fx.out"):
        m = FX.search(ln)
        if m:
            old[int(m.group(1))][int(m.group(2))] = int(m.group(3))/1000.0
except FileNotFoundError:
    print("  (fx.out 不在当前目录)")
if old:
    ks = sorted({k for r in old.values() for k in r})
    print("  fx.out 各 K 中位: " + ", ".join(
        "K=%d:%.2f" % (k, st.median([old[r][k] for r in old if k in old[r]])) for k in ks))
    ks2 = sorted({k for r in byS[3].values() for k in r})
    print("  s_scan(s=3) 各 K 中位: " + ", ".join(
        "K=%d:%.2f" % (k, st.median([byS[3][r][k] for r in byS[3] if k in byS[3][r]])) for k in ks2))
    print()
    common = sorted(set(ks) & set(ks2))
    print("  共同 K 的中位墙钟对比：")
    print("  %6s %12s %12s %10s" % ("K", "fx.out/s", "s_scan/s", "差异"))
    for k in common:
        a = st.median([old[r][k] for r in old if k in old[r]])
        b = st.median([byS[3][r][k] for r in byS[3] if k in byS[3][r]])
        print("  %6d %12.2f %12.2f %9.1f%%" % (k, a, b, (b/a-1)*100))
    ba = min(common, key=lambda k: st.median([old[r][k] for r in old if k in old[r]]))
    bb = min(common, key=lambda k: st.median([byS[3][r][k] for r in byS[3] if k in byS[3][r]]))
    print("\n  ⇒ fx.out 最优 K = %d ；s_scan(s=3) 最优 K = %d  ⇒ %s"
          % (ba, bb, "一致" if ba == bb else "★ 冲突！"))
