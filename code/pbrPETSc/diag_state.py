#!/usr/bin/env python3
"""
★ 关键检验：状态是 (t, a) 还是 (t, b)？

时间轨迹已验证【逐行相同】（各 K 的 Time 序列完全一致），
故 t=340 时各 K 面对的是同一个矩阵。
但 N 相差 10 倍（34 / 34 / 86 / 171 / 369）。
⇒ 差别只能来自预条件子的【构造时刻 b】，而非仅年龄 a = t − b。

本脚本在【同一个 t】上，把各 K 的 (a, b, N) 并列，直接检验这一点。
"""
import re
from collections import defaultdict


def load_N(logpath):
    pat = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    out = []
    for ln in open(logpath, errors="ignore"):
        if "p_rgh" not in ln:
            continue
        m = pat.search(ln)
        if m:
            out.append(int(m.group(1)))
    return out


def series(K, rep=1):
    """返回 [(t, b, a, N)]，b = 该步所用预条件子的构造步。"""
    N = load_N(f"s{K}/log.s{rep}")
    csvp = f"s_k{K}_r{rep}.csv"
    out, last, i = [], None, 0
    for ln in open(csvp):
        p = ln.rstrip("\n").split(",")
        if len(p) != 20:
            continue
        if i >= len(N):
            break
        t = int(float(p[0]))
        if int(float(p[8])) == 0:
            last = t
        if last is not None:
            out.append((t, last, t - last, N[i]))
        i += 1
    return out


print("=" * 96)
print("★ 同一 t、不同 K 的 (b, a, N) 并列")
print("=" * 96)
S = {K: series(K) for K in (1, 2, 3, 4, 5, 6, 8)}
idx = {K: {t: (b, a, n) for (t, b, a, n) in v} for K, v in S.items()}

for t in (250, 280, 300, 310, 320, 330, 340, 344):
    print(f"\n  ── t = {t} ──")
    print(f"    {'K':>3} {'b(构造步)':>10} {'a(年龄)':>8} {'N':>6}")
    rows = []
    for K in (1, 2, 3, 4, 5, 6, 8):
        if t in idx[K]:
            b, a, n = idx[K][t]
            rows.append((K, b, a, n))
            print(f"    {K:>3} {b:>10} {a:>8} {n:>6}")
    # 同龄不同 b 的对照
    bya = defaultdict(list)
    for K, b, a, n in rows:
        bya[a].append((K, b, n))
    multi = {a: v for a, v in bya.items() if len(v) > 1}
    if multi:
        print(f"    ★ 同龄不同 b 的对照：")
        for a, v in sorted(multi.items()):
            ns = [x[2] for x in v]
            print(f"       a={a}: " + ", ".join(f"K={K}(b={b}):{n}" for K, b, n in v)
                  + f"   ⇒ N 极差 {max(ns)-min(ns)}")

print()
print("=" * 96)
print("★ 用【同一个 b】的样本检验：b 相同、a 不同时 N 如何变")
print("=" * 96)
allobs = defaultdict(list)
for K in (1, 2, 3, 4, 5, 6, 8):
    for (t, b, a, n) in S[K]:
        allobs[(b, a)].append((K, n))

same_b = defaultdict(dict)
for (b, a), v in allobs.items():
    same_b[b][a] = [n for _, n in v]

print(f"  在各 K 中出现过的 b 值（取几个）:")
bs = sorted(same_b.keys())
print(f"    {bs[:20]} ... 共 {len(bs)} 个")
print()
for b in [100, 150, 200, 250, 280, 300, 320, 340]:
    if b not in same_b:
        continue
    d = same_b[b]
    ages = sorted(d.keys())
    print(f"  b={b}: " + "  ".join(f"a={a}:{int(sum(d[a])/len(d[a]))}" for a in ages[:12]))

print()
print("=" * 96)
print("★ 检验：N 是否只由 (t, b) 决定？（若是，则同 (t,b) 的 N 应一致）")
print("=" * 96)
consist = defaultdict(list)
for K in (1, 2, 3, 4, 5, 6, 8):
    for (t, b, a, n) in S[K]:
        consist[(t, b)].append((K, n))

bad = {k: v for k, v in consist.items() if len(set(n for _, n in v)) > 1}
print(f"  (t,b) 组合总数: {len(consist)}")
print(f"  其中 N 不一致的: {len(bad)}")
if bad:
    for k, v in sorted(bad.items(), key=lambda kv: -max(n for _, n in kv[1]))[:10]:
        print(f"    (t={k[0]}, b={k[1]}): " + ", ".join(f"K={K}:{n}" for K, n in v))
