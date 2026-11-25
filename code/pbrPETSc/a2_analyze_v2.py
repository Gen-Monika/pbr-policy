#!/usr/bin/env python3
"""
A2 分析（v2）：多组对照 + 逐轮配对
用法： python a2_analyze_v2.py <run.log> [组名...]
"""
import re, sys, statistics as st

log = sys.argv[1]
MODES = sys.argv[2:] or None

wall, execT, iters, rbsteps, load = {}, {}, {}, {}, {}
order = []
for ln in open(log, errors="ignore"):
    m = re.match(r"round=(\d+) mode=(\w+) wall_ms=(\d+) execTime=(\S*) iters=(\d+) "
                 r"nsteps=(\d+) rbsteps=(\d+) fatal=(\d+) load=(\S+)", ln.strip())
    if not m:
        continue
    R, M = int(m.group(1)), m.group(2)
    wall.setdefault(M, {})[R] = int(m.group(3))
    execT.setdefault(M, {})[R] = float(m.group(4)) if m.group(4) not in ("", "-") else None
    iters.setdefault(M, {})[R] = int(m.group(5))
    rbsteps.setdefault(M, {})[R] = int(m.group(7))
    load.setdefault(M, {})[R] = float(m.group(9))
    if M not in order:
        order.append(M)

if MODES:
    order = [m for m in MODES if m in wall]

def med(d):
    v = sorted(x for x in d.values() if x is not None)
    if not v:
        return float("nan")
    n = len(v)
    return v[n//2] if n % 2 else 0.5*(v[n//2-1] + v[n//2])

print("=" * 104)
print("★★★ A2 实机墙钟对照     日志 %s" % log)
print("=" * 104)
print("  %-6s %11s %11s %10s %10s %9s %8s" %
      ("组", "墙钟中位/ms", "ExecTime/s", "Σ迭代数", "重建步数", "各轮 ms", "均负载"))
for M in order:
    w = [wall[M][R] for R in sorted(wall[M])]
    print("  %-6s %11.0f %11.2f %10.0f %10.0f  %s  %.1f"
          % (M, med(wall[M]), med(execT[M]), med(iters[M]), med(rbsteps[M]),
             str(w), med(load[M])))

if "K1" in wall:
    print("\n  ★ 相对 K=1（每步重建）")
    for M in order:
        if M == "K1":
            continue
        print("     %-6s %+7.2f%%   迭代数 %+8.2f%%" %
              (M, 100*(med(wall[M])/med(wall["K1"])-1),
               100*(med(iters[M])/med(iters["K1"])-1)))

ref = None
for c in ("K5", "K3"):
    if c in wall:
        ref = c
        break
if ref:
    print("\n  ★ 相对 %s（调优后的固定周期基线）—— 论文关键对比" % ref)
    for M in order:
        if M == ref or M.startswith("K"):
            continue
        print("     %-6s %+7.2f%%   ExecutionTime %+7.2f%%   迭代数 %+8.2f%%"
              % (M, 100*(med(wall[M])/med(wall[ref])-1),
                 100*(med(execT[M])/med(execT[ref])-1),
                 100*(med(iters[M])/med(iters[ref])-1)))
    print("\n  ★ 逐轮配对（同一轮内比较，消除组间漂移）")
    for M in order:
        if M == ref or M.startswith("K"):
            continue
        win = tot = 0
        print("     %-6s:" % M, end="")
        for R in sorted(wall[ref]):
            if R not in wall[M]:
                continue
            tot += 1
            d = 100*(wall[M][R]/wall[ref][R]-1)
            if d < 0:
                win += 1
            print("  R%d %+.1f%%" % (R, d), end="")
        print("   ⇒ %d/%d 轮胜" % (win, tot))
    # 同一组内的极差，用来判断信噪比
    print("\n  ★ 组内离散度（max-min 相对中位）")
    for M in order:
        v = [wall[M][R] for R in sorted(wall[M])]
        print("     %-6s %5.1f%%" % (M, 100*(max(v)-min(v))/med(wall[M])))
