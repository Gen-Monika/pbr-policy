#!/usr/bin/env python3
"""
★★★ a_merge_phase.py —— 把两次相位扫描（K=7 与 K=10）合并成一张 N(t,a) 表

═══════════════════════════════════════════════════════════════════════
为什么需要合并
═══════════════════════════════════════════════════════════════════════
K=7 那次（A=6）覆盖年龄 0..6，但 sth 的在线策略实际用到年龄 9，
a=7..9 的格子是【形状迁移外推】出来的，贡献该配置 4.43% 的迭代代价。
K=10 那次（A=9）覆盖年龄 1..9（含全部 1..9），可把 a=7..9 换成实测。

═══════════════════════════════════════════════════════════════════════
★ 合并前必须审计的三件事（否则会静默引入矛盾）
═══════════════════════════════════════════════════════════════════════
M1  两次扫描在【重叠年龄】(1..6) 上测到的 N(t,a) 是否一致？
    - 注意：K=7 与 K=10 的"同一 (t,a)"由不同 B 产生，且所处时间步序列不同，
      所以不期望逐位相同；用【相对差分布】判定（|Δ|/N 的中位与 P95）。
M2  覆盖完整性：合并后 a=0..MAXAGE 的每个格子是否都有来源？
M3  a=0 的取值：两个扫描都必须给出一致的 N(t,0)（重建步，不依赖策略 → 应逐位相同）。

合并策略（写死，避免歧义）：
  · a ≤ 6  ：优先用 K=7（年龄覆盖更密、且是当前主结果的来源）
  · a ≥ 7  ：只能用 K=10
  · 若某 (t,a) 在 K=7 缺失，回退到 K=10
这样保证"合并前后，a≤6 的部分逐位不变"⇒ 主结果的前六个配置完全不受影响。
═══════════════════════════════════════════════════════════════════════
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import _rows, _per_step_N, CFG, P2


def load_scan(tag, A, K, prefix):
    """读一次相位扫描，返回 {(t,a): [N...]} 与 {(t,a): [来源B...]}。"""
    lvl, T, B0 = CFG[tag]
    cells = defaultdict(list); src = defaultdict(list)
    for B in range(B0 - A, B0 + 1):
        c = "%s/%s_%s_B%d_K%d_r1.csv" % (P2, prefix, tag, B, K)
        l = "%s/%s_%s/log.B%dK%d_r1" % (P2, prefix, tag, B, K)
        if not (os.path.exists(c) and os.path.exists(l)): continue
        try:
            rr = _rows(c); seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            Ns = _per_step_N(l); n = min(len(steps), len(Ns))
            for i in range(n):
                rf = int(steps[i]["reusedFrom"])
                a = 0 if rf < 0 else i + 1 - rf
                cells[(i + 1, a)].append(Ns[i]); src[(i + 1, a)].append(B)
        except Exception as e:
            print("   !! %s 读取失败: %s" % (c, e))
    return cells, src


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "sth"
    lvl, T, B0 = CFG[tag]
    print("=" * 112)
    print("★★★ 相位表合并审计：%s（T=%d B0=%d）" % (tag, T, B0))
    print("=" * 112)

    d7, s7 = load_scan(tag, 6, 7, "phs")
    print("\n  K=7 (A=6):  %d 个格子, 年龄 %s" %
          (len(d7), sorted(set(a for _, a in d7))))
    d10, s10 = load_scan(tag, 9, 10, "phsA9")
    print("  K=10(A=9):  %d 个格子, 年龄 %s" %
          (len(d10), sorted(set(a for _, a in d10))))

    if not d10:
        print("\n★ K=10 扫描还没产出，先退出"); return

    # ── M3 a=0 应逐位相同
    print()
    print("─" * 112)
    print("★ M3：a=0（重建步，不依赖策略）的取值应逐位相同")
    print("─" * 112)
    c7 = {t: v[0] for (t, a), v in d7.items() if a == 0}
    c10 = {t: v[0] for (t, a), v in d10.items() if a == 0}
    common = sorted(set(c7) & set(c10))
    diff = [t for t in common if c7[t] != c10[t]]
    print("   共同可比 t = %d, 不一致 = %d  %s"
          % (len(common), len(diff), "✓" if not diff else "★ 有矛盾！"))
    if diff[:8]:
        for t in diff[:8]:
            print("      t=%d  K7=%d  K10=%d" % (t, c7[t], c10[t]))

    # ── M1 重叠年龄（1..6）的一致性（用相对差分布）
    print()
    print("─" * 112)
    print("★ M1：重叠年龄 1..6 上，两次扫描的 N(t,a) 相对差分布")
    print("─" * 112)
    print("   %4s %8s %12s %12s %12s %12s" %
          ("age", "可比格数", "中位相对差%", "P95相对差%", "最大绝对差", "完全相同的比例"))
    for a in range(1, 7):
        pairs = [(d7[(t2, a)][0], d10[(t2, a)][0])
                 for (t2, a2) in d10 if a2 == a and (t2, a) in d7]
        if not pairs: continue
        rel = [100.0 * abs(x - y) / max(1.0, y) for x, y in pairs]
        same = 100.0 * sum(1 for x, y in pairs if x == y) / len(pairs)
        p95 = sorted(rel)[int(0.95 * (len(rel) - 1))]
        print("   %4d %8d %12.3f %12.3f %12d %11.1f%%" %
              (a, len(pairs), st.median(rel), p95,
               max(abs(x - y) for x, y in pairs), same))

    # ── M2 覆盖完整性 + 合并
    print()
    print("─" * 112)
    print("★ M2：合并后的覆盖完整性")
    print("─" * 112)
    merged = {}; prov = {}
    for (t, a), v in d7.items():
        merged[(t, a)] = st.median(v); prov[(t, a)] = "K7"
    for (t, a), v in d10.items():
        if (t, a) not in merged:
            merged[(t, a)] = st.median(v); prov[(t, a)] = "K10"
    ages_present = sorted(set(a for _, a in merged))
    print("   合并后格子数 = %d, 年龄 = %s" % (len(merged), ages_present))
    print("   来源统计: K7 = %d 格, K10 补充 = %d 格"
          % (sum(1 for v in prov.values() if v == "K7"),
             sum(1 for v in prov.values() if v == "K10")))
    maxage = max(ages_present)
    print()
    print("   %4s %10s %12s" % ("age", "格子数", "来源"))
    for a in ages_present:
        n7 = sum(1 for k, v in prov.items() if k[1] == a and v == "K7")
        n10 = sum(1 for k, v in prov.items() if k[1] == a and v == "K10")
        print("   %4d %10d %12s" % (a, n7 + n10,
                                    "K7×%d K10×%d" % (n7, n10)))

    # ── 写出合并表
    import json
    out = dict(tag=tag, T=T, B0=B0, maxage=maxage,
               tab={"%d,%d" % k: v for k, v in merged.items()},
               prov={"%d,%d" % k: v for k, v in prov.items()})
    fn = "%s/merged_%s.json" % (P2, tag)
    json.dump(out, open(fn, "w"))
    print("\n   已写出 %s" % fn)
    print("=" * 112)


main()
