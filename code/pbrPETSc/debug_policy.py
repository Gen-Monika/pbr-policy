#!/usr/bin/env python3
"""调试：在线策略为何退化为"每步重建"。"""
import re
import statistics as st


def load_N(logpath):
    pat = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    N = []
    for ln in open(logpath, errors="ignore"):
        if "p_rgh" not in ln:
            continue
        m = pat.search(ln)
        if m:
            N.append(int(m.group(1)))
    return N


N1 = load_N("s1/log.s1")
print(f"K=1 的 N 序列: len={len(N1)} 前10={N1[:10]} 均值={st.mean(N1):.2f}")

# 手工跑前 20 步的规则
R = 22.4
total = 0.0
a = 0
nreb = 0
hist = []
print(f"\n{'t':>3} {'a':>3} {'N(t,a)':>7} {'total':>9} {'avg=total/t':>12} "
      f"{'N1[t]':>6} {'规则判定':>10}")
for t in range(20):
    if t < 8:
        total += R + N1[t]
        nreb += 1
        a = 0
        hist.append(N1[t])
        print(f"{t:>3} {a:>3} {N1[t]:>7} {total:>9.1f} {'(warm)':>12} "
              f"{N1[t]:>6} {'重建(warm)':>10}")
        continue
    avg = total / t if t > 0 else 0.0
    pred = hist[-1]
    if a == 0 or pred >= avg:
        decision = "重建"
        total += R + N1[t]
        nreb += 1
        a = 0
        hist.append(N1[t])
    else:
        decision = "复用"
        total += N1[t]
        a += 1
        hist.append(N1[t])
    print(f"{t:>3} {a:>3} {N1[t]:>7} {total:>9.1f} {avg:>12.2f} "
          f"{N1[t]:>6} {decision:>10}")

print(f"\n⇒ 20 步后：total={total:.1f}  nreb={nreb}")
print(f"\n★ 问题所在：warm=8 时，前 8 步每步都重建，total=8×(22.4+~26)=~387")
print(f"  而 avg = total/t 在 t=8 时 = {387/8:.1f}，远高于 N≈26")
print(f"  ⇒ 判据 'pred >= avg' 恒为假 ⇒ 应进入'复用'分支")
print(f"  ⇒ 但 a 在 warm 结束时被设为 0，故 'a == 0' 恒为真 ⇒ 强制重建")
print()
print("★ 根因：warm 阶段末次重建后 a 被置 0，而下一步检查 'a == 0' 就立刻重建。")
print("  正确语义：a 应表示【已复用了几步】，重建当步之后 a 应置 1（该步已用新预条件子）。")
