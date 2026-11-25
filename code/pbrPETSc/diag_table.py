#!/usr/bin/env python3
"""
诊断：插值表 N(t,a) 是否被跨 K 的池化污染。

疑点：年龄曲线本应随 a 增长（实测 K=8 在 step 340 是 279），
      但表算出的 N(a) 从 a=0 到 a=200 几乎恒为 28。
成因假设：(t,a) 处的中位数把不同 K 的样本混在一起，
         于是每一步都掺入了"该步若重建会是 28 次"的样本，
         把高年龄的信号拉平了。
"""
import re
import statistics as st
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


print("=" * 88)
print("1. 各 (t,a) 格子里到底有几个 K 贡献？")
print("=" * 88)
obs = defaultdict(list)
contrib = defaultdict(set)

for K in (1, 2, 3, 4, 5, 6, 8):
    for rep in (1, 2, 3):
        N = load_N(f"s{K}/log.s{rep}")
        csvp = f"s_k{K}_r{rep}.csv"
        if not N:
            continue
        last, i = None, 0
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
                a = t - last
                obs[(t, a)].append(N[i])
                contrib[(t, a)].add(K)
            i += 1

print(f"总格子数: {len(obs)}")
multi = {k: len(v) for k, v in contrib.items() if len(v) > 1}
print(f"被多个 K 共同占据的格子: {len(multi)}")
print(f"格子内 K 的个数分布: "
      f"{dict(sorted({n: sum(1 for v in contrib.values() if len(v)==n) for n in set(len(v) for v in contrib.values())}.items()))}")

print()
print("=" * 88)
print("2. ★ 关键：格子内的 N 值离散度（若很大，则中位数无意义）")
print("=" * 88)
print(f"  {'(t,a)':>14} {'样本数':>7} {'K集合':>14} {'min':>7} {'中位':>7} {'max':>7} {'极差':>7}")
worst = sorted(obs.items(), key=lambda kv: -(max(kv[1]) - min(kv[1])))[:15]
for (t, a), v in worst:
    print(f"  {f'({t},{a})':>14} {len(v):>7} {str(sorted(contrib[(t,a)])):>14} "
          f"{min(v):>7} {st.median(v):>7.1f} {max(v):>7} {max(v)-min(v):>7}")

print()
print("=" * 88)
print("3. ★ 按 K 分开统计：每个 K 自己的年龄曲线（这才是干净信号）")
print("=" * 88)
for K in (1, 2, 3, 5, 8):
    N = load_N(f"s{K}/log.s1")
    csvp = f"s_k{K}_r1.csv"
    if not N:
        continue
    last, i = None, 0
    bya = defaultdict(list)
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
            bya[t - last].append(N[i])
        i += 1
    print(f"  K={K}: " + "  ".join(f"a={a}:{st.median(v):.0f}" for a, v in sorted(bya.items())))

print()
print("=" * 88)
print("4. ★ 结论性检验：在【相同 t、不同 a】下比较 N（不受跨 K 池化影响）")
print("=" * 88)
print("  取 t=340 附近（漂移已充分展开），看各 K 在该步的 N：")
print(f"  {'t':>5} " + "".join(f"{'K='+str(K):>8}" for K in (1, 2, 3, 5, 8)) + "   年龄")
for t in (300, 310, 320, 330, 340):
    line = f"  {t:>5} "
    ages = []
    for K in (1, 2, 3, 5, 8):
        N = load_N(f"s{K}/log.s1")
        csvp = f"s_k{K}_r1.csv"
        last, i = None, 0
        val, age = "-", "-"
        for ln in open(csvp):
            p = ln.rstrip("\n").split(",")
            if len(p) != 20:
                continue
            if i >= len(N):
                break
            tt = int(float(p[0]))
            if int(float(p[8])) == 0:
                last = tt
            if tt == t and last is not None:
                val, age = N[i], t - last
            i += 1
        line += f"{str(val):>8}"
        ages.append(str(age))
    print(line + "   " + "/".join(ages))
