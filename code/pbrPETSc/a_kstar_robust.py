#!/usr/bin/env python3
"""
第二层审计：ρ* 反解的分散度说明什么？

★ 一个反向检验（必须做，否则会过度解释）：
   若"真 ρ = s·r1"成立，则所有配置的实测 K* 应当一致地等于
   模型在 ρ=s·r1 下的 K*。实测是什么？

   实测 K*: fx=K3, l15=K5, fine=K5, l20=K5, x3=K5
   模型@ρ=s·r1: fx=?, l15=K4, fine=K4, l20=K4, x3=K4

   ⇒ 若四个配置实测都是 K5 而模型@上界只给 K4，那么"真 ρ = s·r1"
     仍然【低估】了重建代价。要解释 K5，ρ 必须超过 s·r1。

★ 但另一个解释同样成立且更保守：
   K5 与 K3 的差距只有 0.65–3.59%，而这些模式的轮间极差是 1.2–27%。
   ⇒ 实测 K* 本身在噪声内，不能断言"实测 K*=K5"。

本脚本给出【两种解释的判别】：用同一批次的墙钟，但按轮分开看，
  若每一轮的 K* 都是 K5，则 K5 的偏好是稳健的；
  若各轮的 K* 在 K3/K4/K5 之间跳，则 K5 是噪声赢家。
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


print("=" * 126)
print("★★★ 第二层审计：K* 的逐轮稳健性（K5 是真实偏好还是噪声赢家？）")
print("=" * 126)
print("  逐轮独立取 K*，看它是否稳定。若三轮都给同一个 K ⇒ 偏好稳健。\n")

for name, tag in TAGS.items():
    b = read_batch(tag)
    if not b:
        continue
    print("─" * 126)
    print("【%s】" % name)
    wins = []
    for r in sorted(b):
        d = b[r]
        order = sorted(d, key=d.get)
        best = order[0]
        second = order[1]
        gap = 100.0 * (d[second] - d[best]) / d[best]
        wins.append(best)
        print("   轮%d: 序 %s   → K*=%s（与次优差 %.2f%%）"
              % (r, " < ".join("%s(%.0fms)" % (m, d[m]) for m in order), best, gap))
    # 三轮合并的中位排序
    allmed = {m: st.median([b[r][m] for r in b if m in b[r]]) for m in b[min(b)]}
    print("   中位合并序: %s"
          % " < ".join("%s(%.0f)" % (m, allmed[m]) for m in sorted(allmed, key=allmed.get)))
    print("   逐轮 K* 集合 = {%s}   %s"
          % (",".join(sorted(set(wins))),
             "✓ 三轮一致" if len(set(wins)) == 1 else "★ 三轮不一致（K* 在噪声内）"))

print("\n" + "=" * 126)
print("★ 判读规则：")
print("   逐轮一致 ⇒ 该配置的 K* 偏好稳健（可主张）")
print("   逐轮不一致 ⇒ K* 不可辨识，只能主张「K3..K5 构成平坦区」")
