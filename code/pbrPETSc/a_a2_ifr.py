#!/usr/bin/env python3
"""
A2（上升加速 / IFR 类条件）的判决性测试 —— 纯用已有相位扫描数据，无新实验。

═══ 判据 ═══
IFR 的离散对应量：失效率递增。对"老化曲线" G_t(a)（把每个 t 归一化到自己的 a=0），
IFR/加速 ⇔ 增量 Δ_t(a) = G_t(a+1) − G_t(a) 递增（即 G_t 凸）。
替换理论的"单峰 c(k)、唯一内点最优"需要这一条。

★★ 关键：必须在【固定 t】上看凸性，不能把不同 t 的 N 混在一起取中位。
   因为漂移使 N(t,0) 本身随 t 变化（这就是非平稳），混起来会造出假的凸/凹。

三层证据：
  L1  逐 t 曲线中，Δ 递增（凸）的 t 占多少
  L2  t 平均曲线 Ḡ(a) 的 Δ 是否递增
  L3  Δ 的相对增长率（≈常数 ⇒ 几何增长 ⇒ 强凸）
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]


def _v(x):
    """格值可能是标量（只被 1 个 run 覆盖）或列表。"""
    return float(st.median(x)) if isinstance(x, (list, tuple)) else float(x)


def curves(tab):
    """→ {t: {a: N}}（格值取中位）"""
    by = {}
    for (t, a), v in tab.items():
        by.setdefault(int(t), {})[int(a)] = _v(v)
    return by


def norm_curve(curve, amax=None):
    """把 {a: N} 归一化到 a=0（若缺 a=0 返回 None）"""
    if 0 not in curve:
        return None
    g0 = curve[0]
    if g0 <= 0:
        return None
    ks = sorted(curve)
    if amax is not None:
        ks = [k for k in ks if k <= amax]
    return {a: curve[a] / g0 for a in ks}


def convexity(gg):
    """返回 (是否凸, Δ 列表, 违反年龄)"""
    ks = sorted(gg)
    if len(ks) < 4:
        return None, [], []
    cc = [gg[a] for a in ks]
    dd = [cc[i + 1] - cc[i] for i in range(len(cc) - 1)]
    viol = [ks[i] for i in range(len(dd) - 1) if dd[i + 1] < dd[i] - 1e-9]
    return (not viol), dd, viol


print("=" * 118)
print("★★★ A2 判决性测试：老化曲线的 IFR 型加速（凸性）")
print("=" * 118)
print("判据：固定 t，G_t(a)=N(t,a)/N(t,0)，Δ_t(a)=G_t(a+1)−G_t(a) 递增 ⇒ 凸 ⇒ A2 成立。\n")

summary = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        print("  %-5s ★ 无数据" % tag)
        continue
    by = curves(d["tab"])
    amax = max(a for c in by.values() for a in c)

    nconv = ntot = 0
    allres = []
    for t, c in by.items():
        gg = norm_curve(c)
        if gg is None:
            continue
        ok, dd, viol = convexity(gg)
        if ok is None:
            continue
        ntot += 1
        nconv += (1 if ok else 0)
        allres.append((t, gg, dd, viol))

    # L2：先逐 t 归一化，再对 G 取中位（正确的"平均曲线"）
    gmed = {}
    for a in range(amax + 1):
        vs = [gg[a] for _, gg, _, _ in allres if a in gg]
        if vs:
            gmed[a] = st.median(vs)
    ok2, dd2, viol2 = convexity(gmed)
    rel = [dd2[i + 1] / dd2[i] if dd2[i] > 1e-9 else float("nan")
           for i in range(len(dd2) - 1)]

    # 末段增量率（相对 a=0 的水平）
    lastrate = 100.0 * dd2[-1] if dd2 else float("nan")

    print("─" * 118)
    print("【%s】 覆盖年龄 a=0..%d ；有 a=0 的 t 数 = %d" % (tag, amax, ntot))
    print("   L2 t 归一化后的平均曲线 Ḡ(a) = %s"
          % "  ".join("%.3f" % gmed[a] for a in sorted(gmed)))
    print("      增量 Δ(a) = %s" % "  ".join("%.3f" % v for v in dd2))
    print("      L2 凸性: %s"
          % ("✓ Δ 单调递增" if ok2 else "★ 违反 %d 处（a=%s）" % (len(viol2), viol2)))
    print("   L3 Δ 增长率 = %s" % " ".join("%.2f" % v for v in rel))
    print("   L1 逐 t 凸比例 = %d/%d = %.1f%%"
          % (nconv, ntot, 100.0 * nconv / ntot if ntot else 0))
    summary.append((tag, amax, ntot, nconv, ok2, len(viol2), gmed, dd2, lastrate))

print("\n" + "=" * 118)
print("汇总")
print("=" * 118)
print("  %-6s %-8s %-14s %-16s %-14s %s"
      % ("配置", "a_max", "逐t凸比例", "平均曲线凸?", "末段 Δ", "覆盖 t 数"))
for tag, amax, ntot, nconv, ok2, nv, gmed, dd2, lr in summary:
    print("  %-6s %-8d %-14s %-16s %-14s %d"
          % (tag, amax,
             "%.1f%%" % (100.0 * nconv / ntot if ntot else 0),
             "✓" if ok2 else "✗ (%d 处违反)" % nv,
             "%.3f" % lr, ntot))
