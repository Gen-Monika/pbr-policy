#!/usr/bin/env python3
"""
★★★ 相位扫描的覆盖完备性证明（跑实机之前必须先证明）

═══ 设计 ═══
base=B、period=K 时，重建步为 B, B+K, B+2K, ...，故年龄 a 出现在
    t = B + a + jK  (j ≥ 0)
取 K = A+1，令 B 扫过 {B0-A, ..., B0}（恰好 K 个连续值）。

═══ 命题 ═══
对任意 t ≥ B0 + A 与任意 a ∈ [1, A]，存在【唯一】的 B ∈ [B0-A, B0]
使该次运行在 t 处的年龄恰为 a。

证明：年龄 a 出现在 t 处 ⟺ B ≡ t - a (mod K)。B 取 K 个连续整数，
故模 K 下恰好命中一次。再验证不落在预热期：重建基点
b = t - a ≥ B0 + A - A = B0，故未被预热覆盖。

═══ 本脚本 ═══
不证明数学，而是【枚举模拟】C++ 的周期策略分支（照抄 PETScPreconditioner.C
的 freezeBase_/period_ 语义），逐 (t,a) 检查覆盖。这样既验证命题，
又验证我对 C++ 语义的理解是否正确。
"""
import sys

B0 = 100


def cpp_phase(T, B, K):
    """
    逐行模拟 PETScPreconditioner.C 的周期分支（line 313-337）：
      const label k = (timeIndex_ - b0)/period_;     // b0 == freezeBase_ == B
      const label b = b0 + k*period_;
      if (timeIndex_ > b) reuse from b; else rebuild
    返回 {t: age}，age=0 表示重建。整除按 C++ 的【向下取整】。
    """
    b0 = B                      # ★ freezeBase_ 就是本次运行的 B
    out = {}
    for t in range(1, T + 1):
        if t >= b0:
            k = (t - b0) // K
            b = b0 + k * K
            out[t] = (t - b) if t > b else 0
        else:
            out[t] = 0          # 预热期：t < b0 每步重建
    return out


def check(A, T, extra_bases=None, verbose=True):
    K = A + 1
    bases = list(range(B0 - A, B0 + 1))
    if extra_bases: bases += list(extra_bases)
    cover = {}
    for B in bases:
        for t, a in cpp_phase(T, B, K).items():
            cover.setdefault((t, a), set()).add(B)

    missing = []
    for t in range(B0 + A, T + 1):
        for a in range(1, A + 1):
            if (t, a) not in cover:
                missing.append((t, a))
    if verbose:
        print("  A=%-3d K=%-3d  bases=%d  检查域 t∈[%d, %d] × a∈[1, %d]"
              % (A, K, len(bases), B0 + A, T, A))
        print("    应有格子=%d  实测覆盖=%d  缺失=%d"
              % ((T - B0 - A + 1) * A, (T - B0 - A + 1) * A - len(missing), len(missing)))
        if missing:
            print("    ★ 缺失示例: %s" % missing[:10])
    return missing


print("=" * 100)
print("★★★ 1. 覆盖完备性（枚举模拟 C++ 周期分支）")
print("=" * 100)
for A in (3, 5, 7, 15, 29):
    for T in (344, 720, 1231):
        if T <= B0 + A + 5: continue
        m = check(A, T, verbose=(T == 344))
print()

print("=" * 100)
print("★★★ 2. 与 K 扫描的对比：同样运行次数能补多少格子")
print("=" * 100)
for A, T in ((3, 344), (7, 344), (15, 344)):
    K = A + 1
    # 相位扫描：A+1 次
    ph = set()
    for B in range(B0 - A, B0 + 1):
        for t, a in cpp_phase(T, B, K).items():
            if t >= B0 and a > 0: ph.add((t, a))
    # K 扫描：A+1 次（K=1..A+1）
    ks = set()
    for k in range(1, A + 2):
        for t, a in cpp_phase(T, B0, k).items():
            if t >= B0 and a > 0: ks.add((t, a))
    print("  A=%-3d 各 %d 次运行       相位扫描覆盖=%-7d  K扫描覆盖=%-7d  提升=%.1fx"
          % (A, A + 1, len(ph), len(ks), len(ph)/max(1, len(ks))))

print()
print("=" * 100)
print("★★★ 3. 关键格子检验：(t=100, a=1)（此前模型与 C++ 分歧的种子）")
print("=" * 100)
for B in range(B0 - 3, B0 + 1):
    ph = cpp_phase(200, B, 4)
    if ph.get(100, 0) == 1:
        print("  B=%-4d K=4  ⇒  在 t=100 处年龄 = 1  ✓  （填上种子）" % B)
print()
print("  ⇒ 相位扫描能直接测到 (100,1)，无需任何填充")
print("=" * 100)
