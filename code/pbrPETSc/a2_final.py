#!/usr/bin/env python3
"""A2 最终汇总：ONL（a2_l20.log）vs K1/K3（a2b.log），逐轮配对。"""
import re, statistics as st

def walls(f):
    d = {}
    for ln in open(f, errors="ignore"):
        m = re.match(r"round=(\d+) mode=(\w+) wall_ms=(\d+)", ln.strip())
        if m:
            d.setdefault(m.group(2), {})[int(m.group(1))] = int(m.group(3))
    return d

def med(v):
    v = sorted(v)
    n = len(v)
    if not n:
        return float("nan")
    return v[n//2] if n % 2 else 0.5*(v[n//2-1] + v[n//2])

w1 = walls("a2_l20.log")   # ONL
w2 = walls("a2b.log")      # K1, K3

K1v = sorted(w2["K1"].values())
K3v = sorted(w2["K3"].values())
ONLv = sorted(w1["ONL"].values())
K1, K3, ONL = med(K1v), med(K3v), med(ONLv)

print("=" * 92)
print("★★★ A2 最终结果：在线策略的实机墙钟验证")
print("    算例 l20（damBreak, levels=20, PETScILU, 344 步）")
print("    协议：同机器、同负载、交错，5 轮取中位")
print("=" * 92)
print()
print("  组              墙钟中位/ms      各轮 ms")
print("  K=1 每步重建     %8.0f        %s" % (K1, K1v))
print("  K=3 最优固定周期 %8.0f        %s" % (K3, K3v))
print("  ONL 在线策略     %8.0f        %s" % (ONL, ONLv))
print()
print("  ★ 相对 K=1（每步重建）:  K=3 %+.2f%%     ONL %+.2f%%"
      % (100*(K3/K1-1), 100*(ONL/K1-1)))
print("  ★ 相对 K=3（调优后基线）: ONL %+.2f%%   ← 论文关键对比"
      % (100*(ONL/K3-1)))
print()
print("  ★ 逐轮配对（同一轮内，消除组间漂移）")
print("     %-6s %10s %10s %10s" % ("轮", "ONL/ms", "K3/ms", "ONL vs K3"))
win = 0
for R in sorted(w1["ONL"]):
    o = w1["ONL"][R]
    k = w2["K3"].get(R)
    if k:
        d = 100*(o/k-1)
        if o < k:
            win += 1
        print("     R%-5d %10d %10d %+9.2f%%" % (R, o, k, d))
print("     ⇒ 逐轮胜率：ONL 优于 K=3  %d/%d 轮" % (win, len(w1["ONL"])))
print()
print("  ★ 与 K=1 的逐轮配对")
win1 = 0
for R in sorted(w1["ONL"]):
    o = w1["ONL"][R]
    k = w2["K1"].get(R)
    if k:
        if o < k:
            win1 += 1
        print("     R%-5d ONL %6d  K1 %6d   %+9.2f%%" % (R, o, k, 100*(o/k-1)))
print("     ⇒ 逐轮胜率：ONL 优于 K=1  %d/%d 轮" % (win1, len(w1["ONL"])))
