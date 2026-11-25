#!/usr/bin/env python3
"""
第二层审计（二）：分离【稳健结论】与【噪声内的结论】。

逐轮 K* 在 5/5 配置上都不一致（见 a_kstar_robust.py）⇒ 不能主张"实测 K*=K5"。
但排序里有一个跨轮稳定的结构：K1 与 K2 总是垫底。

★ 配对比较（Wilson / 符号检验的思想）：
   对每一轮，比较 K1 vs 每个 K∈{3,4,5} 的墙钟。
   若 K1 每一轮都差 ⇒ 这是 3/3 一致，可以用符号检验说"方向稳健"。
   同时比较 K3/K4/K5 之间的差 —— 预期它们互有胜负。

这样得到两条【可主张】的结论：
   (A) K1（每步重建）显著劣 —— 收益是真实的
   (B) K3/K4/K5 之间不可分辨 —— 平坦区
   (C) K2 的位置：是否显著劣于 K3？
"""
import sys, os, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import P2

TAGS = {"fx": "k2fx", "l15": "k2l15", "fine": "k2fine",
        "l20": "k2l20", "x3": "k2x3"}
LOGRE = re.compile(r"round=(\d+) mode=(K\d) K=(\d+) wall_ms=(\d+) execTime=([\d.]+) "
                   r"iters=(\d+) nsteps=(\d+) rbsteps=(\d+)")


def read_batch(tag):
    f = "%s/%s.log" % (P2, tag)
    if not os.path.exists(f):
        return None
    out = {}
    for ln in open(f, errors="ignore"):
        m = LOGRE.search(ln)
        if not m:
            continue
        out.setdefault(int(m.group(1)), {})[m.group(2)] = int(m.group(4))
    return out


print("=" * 122)
print("★★★ 第二层：配对比较（跨轮一致性）—— 分离稳健结论 vs 噪声内结论")
print("=" * 122)

for name, tag in TAGS.items():
    b = read_batch(tag)
    if not b:
        continue
    rounds = sorted(b)
    print("\n" + "─" * 122)
    print("【%s】共 %d 轮" % (name, len(rounds)))

    # 逐轮 K1 vs 其他
    print("  ▸ K1（每步重建）相对其他 K 的差（正 = K1 更慢）:")
    for other in ("K2", "K3", "K4", "K5"):
        diffs = []
        for r in rounds:
            d = b[r]
            if "K1" in d and other in d:
                diffs.append(100.0 * (d["K1"] - d[other]) / d[other])
        if not diffs:
            continue
        wins = sum(1 for x in diffs if x > 0)
        print("     K1 vs %-3s : %s   逐轮正/总 = %d/%d   %s"
              % (other, " ".join("%+.1f%%" % x for x in diffs), wins, len(diffs),
                 "✓ 全轮 K1 更慢" if wins == len(diffs) else "★ 有反转"))

    # K2 vs K3（次优候选）
    diffs = []
    for r in rounds:
        d = b[r]
        if "K2" in d and "K3" in d:
            diffs.append(100.0 * (d["K2"] - d["K3"]) / d["K3"])
    if diffs:
        wins = sum(1 for x in diffs if x > 0)
        print("  ▸ K2 vs K3 （正 = K2 更慢）: %s   正/总 = %d/%d   %s"
              % (" ".join("%+.1f%%" % x for x in diffs), wins, len(diffs),
                 "✓ 全轮 K2 更慢" if wins == len(diffs) else "★ 有反转"))

    # K3/K4/K5 之间的胜负矩阵
    print("  ▸ K3/K4/K5 相互胜负（行 vs 列，正 = 行更快）:")
    grp = ["K3", "K4", "K5"]
    for a in grp:
        line = []
        for c in grp:
            if a == c:
                line.append("  --  ")
                continue
            diffs = []
            for r in rounds:
                d = b[r]
                if a in d and c in d:
                    diffs.append(d[c] - d[a])   # 正 = a 更快
            w = sum(1 for x in diffs if x > 0)
            line.append("%d/%d" % (w, len(diffs)))
        print("     %-4s %s" % (a, "  ".join(line)))

    # 中位合并下 K1 与 K5 的差（唯一可能显著的一组）
    allmed = {m: st.median([b[r][m] for r in rounds if m in b[r]]) for m in b[rounds[0]]}
    if "K1" in allmed and "K5" in allmed:
        print("  ▸ 中位合并: K1 vs K5 = %+.1f%%；K1 vs K3 = %+.1f%%"
              % (100.0 * (allmed["K1"] - allmed["K5"]) / allmed["K5"],
                 100.0 * (allmed["K1"] - allmed["K3"]) / allmed["K3"]))

print("\n" + "=" * 122)
print("★ 判读：")
print("   全轮一致的方向 ⇒ 可主张（3/3 或 4/4，符号检验 p≤0.25 是最弱的下界，")
print("                     配合效应量使用）")
print("   有反转的对比 ⇒ 不可主张，只能报「构成平坦区」")
