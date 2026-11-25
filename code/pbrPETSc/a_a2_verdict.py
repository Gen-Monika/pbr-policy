#!/usr/bin/env python3
"""
A2 判定（最终）：把违反幅度相对化，得到可跨配置比较的 IFR 指标。

问题：绝对违反幅度不可比（x3 的 7.16 vs l20 的 0.83），因为 N 的量级差 4 倍。
做法：以"特征增量的变化尺度"为分母。特征尺度取 Δ(a) 的首末差：
    scale = |Δ_last − Δ_first|        （凸性要考察的总变化量）
    相对违反 = 最大回落量 / scale
若配置真是"凸 + 整数抖动"，相对违反应 ≪ 1；若结构性非凸，则 O(1)。

同时给一个直接的全局判据：
    R = Δ_last / Δ_first
    R > 1 ⇒ 末段增量大于初段（整体加速）
第二判据（对整数离散最稳健）：
    线性回归 G(a) 对 a，看残差是否系统性凹，以及二次项系数 b2 是否 > 0。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]


def _v(x):
    return float(st.median(x)) if isinstance(x, (list, tuple)) else float(x)


def curves(tab):
    by = {}
    for (t, a), v in tab.items():
        by.setdefault(int(t), {})[int(a)] = _v(v)
    return by


def quad_fit(xs, ys):
    """最小二乘二次拟合 y ≈ b0 + b1 x + b2 x^2，返回 (b1, b2)"""
    n = len(xs)
    if n < 3:
        return None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    s11 = sum((x - mx) ** 2 for x in xs)
    s12 = sum((x - mx) * (x * x - sum(z * z for z in xs) / n) for x in xs)
    s22 = sum((x * x - sum(z * z for z in xs) / n) ** 2 for x in xs)
    t1 = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    t2 = sum((x * x - sum(z * z for z in xs) / n) * (y - my) for x, y in zip(xs, ys))
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-15:
        return None, None
    b1 = (t1 * s22 - t2 * s12) / det
    b2 = (t2 * s11 - t1 * s12) / det
    return b1, b2


print("=" * 120)
print("★★★ A2 最终判定：相对化违反幅度 + 二次拟合曲率")
print("=" * 120)
print("  %-6s %-9s %-11s %-11s %-13s %-13s %s"
      % ("配置", "N(a=0)", "R=ΔL/ΔF", "相对违反", "平均曲线 b2", "逐t b2>0 比例", "判定"))

verdicts = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    by = curves(d["tab"])
    n0s = [c[0] for c in by.values() if 0 in c]
    R_list = []
    relviol = []
    b2pos = 0
    b2tot = 0
    allb2 = []
    for t, c in by.items():
        if 0 not in c or c[0] <= 0:
            continue
        ks = sorted(c)
        if len(ks) < 4:
            continue
        g0 = c[0]
        gg = [c[a] / g0 for a in ks]
        dd = [gg[i + 1] - gg[i] for i in range(len(gg) - 1)]
        if len(dd) < 3:
            continue
        scale = abs(dd[-1] - dd[0])
        w = max((dd[i] - dd[i + 1]) for i in range(len(dd) - 1))
        relviol.append(w / scale if scale > 1e-9 else float("inf"))
        R_list.append(dd[-1] / dd[0] if dd[0] > 1e-9 else float("nan"))
        _, b2 = quad_fit([float(a) for a in ks], gg)
        if b2 is not None:
            b2tot += 1
            b2pos += (1 if b2 > 0 else 0)
            allb2.append(b2)

    # 平均曲线（逐 t 归一化后取中位）
    amax = max(a for c in by.values() for a in c)
    gmed = {}
    for a in range(amax + 1):
        vs = [c[a] / c[0] for c in by.values() if 0 in c and a in c and c[0] > 0]
        if vs:
            gmed[a] = st.median(vs)
    xs = [float(a) for a in sorted(gmed)]
    ys = [gmed[a] for a in sorted(gmed)]
    _, b2med = quad_fit(xs, ys)
    rr = [x for x in R_list if x == x]
    rv = [x for x in relviol if x == x]

    ok = (b2med is not None and b2med > 0) and (
        (st.median(rv) < 0.5) if rv else False) and (
        (st.median(rr) > 1.0) if rr else False)
    verdicts.append((tag, ok, b2med, st.median(rr) if rr else float("nan"),
                     st.median(rv) if rv else float("nan"),
                     b2pos, b2tot))
    print("  %-6s %-9.1f %-11s %-11s %-13s %-13s %s"
          % (tag, st.median(n0s) if n0s else float("nan"),
             "%.2f" % (st.median(rr) if rr else float("nan")),
             "%.3f" % (st.median(rv) if rv else float("nan")),
             "%.4f" % (b2med if b2med is not None else float("nan")),
             "%.1f%%" % (100.0 * b2pos / b2tot if b2tot else 0),
             "✓ 支持 A2" if ok else "★ 不支持"))

print("\n  ★ 判据：b2>0（凸）、R>1（加速）、相对违反<0.5（非结构性的）。")
print("     三者同时满足 ⇒ A2 成立。")
