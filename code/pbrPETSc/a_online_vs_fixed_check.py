#!/usr/bin/env python3
"""
★★★ 重要核查：在线策略是否真的"优于全部固定周期"？

═══ 触发 ═══
在核对成本模型时，实测墙钟出现：
  l15 : K3=16303   ONLs=16568   ⇒ K3 更快 1.6%
  l20 : K3=18802   ONLs=20420   ⇒ K3 更快 8.6%
  fl30: K3=248792  ONLs=249894  ⇒ K3 更快 0.4%

但此前的 A2 文档写的是「fl30 优于全部固定周期 incl. tuned K5 by 1.08% (3/3)」。
矛盾的可能原因：**当时的 mode 集合里没有 K3**（只跑了 K1 K5 ONLs ONLp），
而 K3 恰好比在线更快。

若成立，则"在线优于全部固定周期"这一主张**不能成立** —— 这是一个必须
在论文定稿前查清的硬问题。

═══ 本脚本 ═══
1. 列出每个配置【实际测过哪些 mode】
2. 给出完整的墙钟排序
3. 明确：在线 vs 全部已测固定周期 的最好者
4. 标注哪些固定周期从未被测过（补齐成本）
"""
import sys, os, glob, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

CASES = [("l15", "a2l15.log", "a2l15"),
         ("l20", "a2A.log", "a2A"),
         ("fl30", "a2B.log", "a2B"),
         ("l20-smoke", "a2smoke3.log", "a2smoke3")]


def parse_log(path):
    out = {}
    p = os.path.join(P2, path)
    if not os.path.exists(p): return out, []
    modes = []
    for ln in open(p, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=", 1) for x in ln.split() if "=" in x)
        M = kv.get("mode")
        if not M: continue
        if M not in modes: modes.append(M)
        try:
            out.setdefault(M, []).append(int(kv["wall_ms"]))
        except Exception:
            pass
    return out, modes


print("=" * 126)
print("★★★ 1. 每个配置实际测过的 mode 与墙钟")
print("=" * 126)
ALL = {}
for tag, logn, pfx in CASES:
    w, modes = parse_log(logn)
    if not w:
        print("\n  ── %-12s 无日志 ──" % tag); continue
    ALL[tag] = w
    print("\n  ── %s  （日志 %s）──" % (tag, logn))
    print("     测过的 mode: %s" % ", ".join(modes))
    print("     %-8s %12s %12s %12s   %s" % ("mode", "中位", "最小", "最大", "轮数"))
    for M in sorted(w, key=lambda m: st.median(w[m])):
        v = w[M]
        print("     %-8s %10d ms %10d ms %10d ms   %d" % (M, st.median(v), min(v), max(v), len(v)))

print()
print("=" * 126)
print("★★★ 2. 核心问题：在线 vs 已测固定周期的最好者")
print("=" * 126)
for tag in ALL:
    w = ALL[tag]
    fixed = {m: st.median(v) for m, v in w.items() if m.startswith("K")}
    onl = {m: st.median(v) for m, v in w.items() if m.startswith("ONL")}
    if not fixed or not onl: continue
    bf = min(fixed, key=fixed.get)
    bo = min(onl, key=onl.get)
    delta = onl[bo] - fixed[bf]
    verdict = ("在线胜出 %.2f%%" % (100*(-delta)/fixed[bf])) if delta < 0 else \
              ("★在线落后 %.2f%%" % (100*delta/fixed[bf]))
    print("\n  ── %s ──" % tag)
    print("     已测固定周期: %s" % ", ".join("%s=%d" % (m, fixed[m]) for m in sorted(fixed, key=fixed.get)))
    print("     在线       : %s" % ", ".join("%s=%d" % (m, onl[m]) for m in sorted(onl, key=onl.get)))
    print("     最好固定周期 = %s (%d ms)   最好在线 = %s (%d ms)" % (bf, fixed[bf], bo, onl[bo]))
    print("     ⇒ %s" % verdict)

print()
print("=" * 126)
print("★★★ 3. 逐轮对照（避免中位数掩盖翻转）")
print("=" * 126)
for tag in ALL:
    w = ALL[tag]
    fixed = [m for m in w if m.startswith("K")]
    if not fixed: continue
    bf = min(fixed, key=lambda m: st.median(w[m]))
    onls = [m for m in w if m.startswith("ONL")]
    if not onls: continue
    bo = min(onls, key=lambda m: st.median(w[m]))
    n = min(len(w[bf]), len(w[bo]))
    print("\n  ── %s: 最好固定周期 %s  vs  最好在线 %s ──" % (tag, bf, bo))
    win = 0
    for i in range(n):
        d = w[bo][i] - w[bf][i]
        if d < 0: win += 1
        print("     轮%d: %s=%-7d %s=%-7d  差 %+6d ms (%+.1f%%)"
              % (i+1, bf, w[bf][i], bo, w[bo][i], d, 100.0*d/w[bf][i]))
    print("     ⇒ 在线胜 %d/%d 轮" % (win, n))

print()
print("=" * 126)
print("★★★ 4. 缺口：哪些固定周期从未被测过")
print("=" * 126)
print("  若未测的 K 中有比在线更快的，则'优于全部固定周期'不成立。")
print()
for tag in ("l15", "l20", "fl30"):
    w = ALL.get(tag)
    if not w: continue
    tested = sorted(int(m[1:]) for m in w if m.startswith("K") and m[1:].isdigit())
    missing = [k for k in (2, 3, 4, 5, 6, 8, 10, 13) if k not in tested]
    print("  ── %s ──" % tag)
    print("     已测 K: %s" % tested)
    print("     ★ 未测 K: %s" % missing)
    onl = [st.median(v) for m, v in w.items() if m.startswith("ONL")]
    if onl:
        print("     在线最快 = %d ms" % min(onl))
print()
print("  ⇒ 此前'A2 fl30 优于全部固定周期'的结论，是在 mode 集合不含 K3 时得出的。")
print("     而 K3 实测比在线更快 ⇒ 该主张需要修正。")
print("=" * 126)
