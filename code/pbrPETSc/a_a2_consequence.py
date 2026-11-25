#!/usr/bin/env python3
"""
A2 后果检验（修正版）：用【实测口径】验证 c(k) 单峰、内点最优唯一。

★ 前一版的错误：我用了 c(k) = (ρ + N̄(k)) / k，即"年龄 k 的基线水平 ÷ k"。
  这是年龄替换模型在【寿命分布 L 未知时】的形式，它隐含假定
  "因子活到 k 岁就正好在下一次重建时被替换"。
  但本文的设定是【固定周期策略】：真正决定成本的是该周期下
  【平均每步迭代数】，即年龄 0..K−1 的混合平均，不是"年龄 K 的水平"。

  正确口径（与主结果表一致）：
     对固定周期 K，用实测 N(t, a_K(t)) 累加：
         cost_K = Σ_t N(t, a_K(t)) + ρ · |{t : a_K(t)=0}|
         c(k)   = cost_K / T                      （每步平均成本）
  这就是 a_cost_interval.py 用的口径。

判据：c(k) 在 K=1..Kmax 上是否单峰，且极小是否在【内点】。
      Kmax 取实测覆盖 a_max（=6，sth 9），不外推。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, CFG

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]


def _v(x):
    return float(st.median(x)) if isinstance(x, (list, tuple)) else float(x)


def build(tab):
    """→ {t: {a: N}}"""
    by = {}
    for (t, a), v in tab.items():
        by.setdefault(int(t), {})[int(a)] = _v(v)
    return by


def cost_fixed(by, K, rho, B0):
    """固定周期 K 的成本（实测口径，覆盖内）。"""
    tot = 0.0
    nrb = 0
    for t, c in by.items():
        if t < B0:
            a = 0
        else:
            r = (t - B0) % K
            a = 0 if r == 0 else r
        if a not in c:
            return None
        tot += c[a]
        if a == 0:
            nrb += 1
    return tot + rho * nrb, tot, nrb


print("=" * 124)
print("★★★ A2 后果检验（实测口径）：c(k) 的单峰性与内点最优")
print("   c(k) = [ Σ_t N(t, a_k(t)) + ρ·#{a=0} ] / T      K ≤ a_max（不外推）")
print("=" * 124)
print("  %-6s %-8s %-8s %-9s %-11s %-13s %s"
      % ("配置", "ρ口径", "ρ值", "k*", "c(k*)", "单峰?（1..%s）" % "", "判定"))

summary = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    by = build(d["tab"])
    B0 = d["B0"]
    amax = max(a for c in by.values() for a in c)
    kmax = amax
    r1, s = d["r1"], d["s"]

    # 只保留覆盖完整的 t（所有 a=0..kmax 都有）
    full = {t: c for t, c in by.items() if all(a in c for a in range(kmax + 1))}
    if not full:
        print("  %-6s ★ 无完整覆盖" % tag)
        continue

    for lab, rho in (("r1", r1), ("s·r1", r1 * s)):
        vals = {}
        for k in range(1, kmax + 1):
            r = cost_fixed(full, k, rho, B0)
            if r:
                vals[k] = r[0]
        ks = sorted(vals)
        sk = min(vals, key=vals.get)
        i = ks.index(sk)
        left = all(vals[ks[j]] > vals[ks[j + 1]] for j in range(i))
        right = all(vals[ks[j]] < vals[ks[j + 1]] for j in range(i, len(ks) - 1))
        uni = left and right
        interior = 1 < sk < kmax
        ok = uni and interior
        summary.append((tag, lab, sk, vals[sk], uni, interior, ok, kmax, len(full)))
        print("  %-6s %-8s %-8.1f K=%-7d %-11.1f %-13s %s"
              % (tag, lab, rho, sk, vals[sk],
                 "✓" if uni else "✗(%s)" % ("左" if not left else "右"),
                 "✓ 内点唯一" if ok else
                 ("★ 边界 K=%d（上界）" % sk if sk == kmax else "★ 边界 K=1")))

print("\n" + "=" * 124)
print("小结")
print("=" * 124)
from collections import defaultdict
g = defaultdict(lambda: [0, 0])
for tag, lab, sk, ck, uni, inte, ok, kmax, nfull in summary:
    g[tag][1] += 1
    g[tag][0] += (1 if ok else 0)
for tag in TAGS:
    if tag in g:
        a, b = g[tag]
        print("  %-6s %d/%d 组合满足「单峰 + 内点唯一」" % (tag, a, b))

print("\n  ★ 与主结果表的交叉核对：主结果说 K*=K3/K5（依 ρ 定）。")
print("    若本表给出同一个 K*，说明 c(k) 的口径与主结果一致——这是必须通过的核对。")
