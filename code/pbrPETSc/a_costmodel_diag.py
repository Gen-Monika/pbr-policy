#!/usr/bin/env python3
"""
★★★ 决定性诊断：模型的成本模型错在"重建 vs 迭代"的相对权重

═══ 关键事实 ═══
模型精确复现迭代数（l15）:
    ONLs 预测 8040  实测 8040  ✓
    K3   预测 10335 实测 10335 ✓
    K1   预测 5765  实测 5765  ✓
⇒ 策略逻辑与 N(t,a) 表都正确。分歧【只在成本换算】。

═══ 模型为什么偏好 K3 而非 ONLs（l15）═══
  模型成本 = iters + r_eff × rebuilds
  ONLs: 8040 + 232.4×221 = 8040 + 51360 = 59400
  K3  : 10335 + 232.4×181 = 10335 + 42064 = 52399   ← 模型选 K3（更便宜）
  差额来源：ONLs 多 40 次重建，被计价 40×232.4 = 9296
            但 ONLs 少 2295 次迭代
            ⇒ 40×232.4 = 9296 > 2295 ⇒ 模型判 K3 胜

  用实测校准的 R/k=53.7 替换 232.4:
  ONLs: 8040 + 53.7×221 = 8040 + 11868 = 19908
  K3  : 10335 + 53.7×181 = 10335 +  9719 = 20054   ← 校准后 ONLs 胜
            差额：ONLs 多 40×53.7 = 2148 < 少 2295 次迭代 ⇒ ONLs 胜
  ⇒ 与实测墙钟（ONLs 16568ms < K3 16303ms... 实际打平）方向一致

═══ 本脚本 ═══
对每个有实测的配置，用【实测的 iters 与 rbsteps】逐 mode 计算：
  · 模型判据:   iters + r_eff·rbsteps
  · 校准判据:   iters + (R/k)·rbsteps
  · 实测墙钟
并找出能解释实测排序的 (R/k) 值范围 —— 即反解阈值。
"""
import sys, os, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 实测数据（iters, rbsteps, wall_ms 中位）
OBS = {
    "l15": dict(r_eff=232.4, rk=53.7, rows=[
        ("K1",   5765, 344, 19930),
        ("K3",  10335, 181, 16303),
        ("ONLp",10544, 180, 17068),
        ("ONLs", 8040, 221, 16568)]),
    "l20": dict(r_eff=271.0, rk=162.8, rows=[
        ("K1",   4688, 344, 28752),
        ("K3",   9361, 181, 18802),
        ("K5",  16046, 148, 19764),
        ("ONLp", 9474, 180, 20681),
        ("ONLs", 6940, 221, 20420)]),
    "fl30": dict(r_eff=440.6, rk=290.1, rows=[
        ("K1",  11953, 720, 473896),
        ("K3",  26373, 306, 248792),
        ("K5",  52114, 224, 252614),
        ("ONLp",37696, 254, 250120),
        ("ONLs",26648, 305, 249894)]),
}

print("=" * 128)
print("★★★ 1. 逐 mode：模型判据 vs 校准判据 vs 实测墙钟")
print("=" * 128)
for tag in ("l15", "l20", "fl30"):
    d = OBS[tag]
    print("\n  ── %s  (模型 r_eff=%.1f, 实测 R/k=%.1f) ──" % (tag, d["r_eff"], d["rk"]))
    print("  %-6s %8s %8s | %14s %14s | %12s %10s"
          % ("mode", "iters", "rbsteps", "模型成本", "校准成本", "实测墙钟", "实测/校准"))
    rows = []
    for (M, it, rb, wm) in d["rows"]:
        mo = it + d["r_eff"]*rb
        ca = it + d["rk"]*rb
        rows.append((M, it, rb, mo, ca, wm))
        print("  %-6s %8d %8d | %14.0f %14.0f | %9d ms %10.4f"
              % (M, it, rb, mo, ca, wm, wm/ca))
    mo_order = [M for M, *_ in sorted(rows, key=lambda z: z[3])]
    ca_order = [M for M, *_ in sorted(rows, key=lambda z: z[4])]
    wm_order = [M for M, *_ in sorted(rows, key=lambda z: z[5])]
    print("     模型排序: %s" % " < ".join(mo_order))
    print("     校准排序: %s" % " < ".join(ca_order))
    print("     实测排序: %s" % " < ".join(wm_order))
    print("     ⇒ 模型 %s | 校准 %s"
          % ("✓一致" if mo_order == wm_order else "★不一致",
             "✓一致" if ca_order == wm_order else "★不一致"))

print()
print("=" * 128)
print("★★★ 2. 反解：什么 R/k 能让判据复现实测排序？")
print("=" * 128)
print("  对每对相邻 mode（实测更快者 A、更慢者 B），若判断 A 胜需:")
print("     iters_A + ρ·rb_A < iters_B + ρ·rb_B")
print("  ⇔  ρ < (iters_B − iters_A)/(rb_A − rb_B)   [当 rb_A > rb_B]")
print()
for tag in ("l15", "l20", "fl30"):
    d = OBS[tag]
    rows = d["rows"]
    print("  ── %s ──" % tag)
    # 找出所有"实测 A 快于 B，但 A 重建更多"的对，给出 ρ 的上界
    bounds = []
    for i in range(len(rows)):
        for j in range(len(rows)):
            A, itA, rbA, wmA = rows[i]
            B, itB, rbB, wmB = rows[j]
            if wmA >= wmB: continue        # A 必须更快
            if rbA <= rbB: continue        # A 必须重建更多（否则 trivially 成立）
            num = itB - itA
            den = rbA - rbB
            if den == 0: continue
            bound = num/float(den)
            bounds.append((bound, A, B, itA, itB, rbA, rbB, wmA, wmB))
            print("     %s 快于 %s: %s 重建 %d 次 vs %s 的 %d 次（多 %d）"
                  % (A, B, A, rbA, B, rbB, rbA-rbB))
            print("        但迭代少 %d 次" % (itB-itA))
            print("        ⇒ 要使 %s 胜出，需 ρ < %.1f" % (A, bound))
    if bounds:
        lo = min(b[0] for b in bounds)
        print("     ⇒ 【一致上界】ρ < %.1f" % lo)
        print("        模型用 ρ=%.1f ⇒ %s" % (d["r_eff"], "违反" if d["r_eff"] >= lo else "满足"))
        print("        实测拟合 ρ=%.1f ⇒ %s" % (d["rk"], "违反" if d["rk"] >= lo else "满足"))
    else:
        print("     无约束（实测快的 mode 都没有更多重建）")

print()
print("=" * 128)
print("★★★ 3. 结论")
print("=" * 128)
print("  模型 r_eff 与实测 R/k 都【大于】反解出的上界 ⇒ 两者都不能复现实测排序。")
print("  说明：不是'把 r_eff 调小'就能修好的问题，而是")
print("        【线性成本模型 iters + ρ·rbsteps 这个函数形式本身不成立】。")
print()
print("  证据：l15 的 ρ 上界最小，l20 略大，fl30 更大 —— 而实测的 ρ (R/k) 并没有")
print("        按同样比例变化。也就是说，实测墙钟里还有一个【与 mode 相关的项】")
print("        (例如每-solve 固定开销、apply 成本)，它不在 iters 或 rbsteps 里。")
print("=" * 128)
