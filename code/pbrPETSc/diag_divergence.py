#!/usr/bin/env python3
"""
量化各 K 运行的场差异：是"真实轨迹分岔"还是"浮点末位噪声"？

时间步序列【完全相同】⇒ 物理时间表一致。
但场文件哈希不同 ⇒ 必有差异。关键在幅度：
  - 若差异 ~1e-15（机器精度）⇒ 只是浮点末位，轨迹实质相同
  - 若差异 ~1e-3 以上 ⇒ 真实分岔，各 K 面对的是不同矩阵
"""
import os
import re


def read_foam_field(path):
    """读 OpenFOAM 标量/矢量场文件，返回数值列表。"""
    vals = []
    with open(path, errors="ignore") as f:
        txt = f.read()
    # 去掉注释块与 // 行
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    lines = [re.sub(r"//.*", "", l) for l in txt.split("\n")]
    body = []
    started = False
    for l in lines:
        if l.strip().startswith("("):
            started = True
            continue
        if started and l.strip() == ")":
            break
        if started:
            body.append(l)
    for l in body:
        for tok in l.replace("(", " ").replace(")", " ").split():
            try:
                vals.append(float(tok))
            except ValueError:
                pass
    return vals


def compare(t, field, Ks=(1, 2, 3, 5, 8)):
    base = None
    print(f"\n  ── t={t}  {field} ──")
    print(f"  {'K':>3} {'元素数':>8} {'与 K=1 的最大绝对差':>22} {'最大相对差':>14} {'L2 相对差':>14}")
    for K in Ks:
        p = f"s{K}/{t}/{field}"
        if not os.path.exists(p):
            continue
        v = read_foam_field(p)
        if base is None:
            base = v
        if len(v) != len(base):
            print(f"  {K:>3} {len(v):>8}   (长度不同，无法比较)")
            continue
        if not v:
            print(f"  {K:>3} {0:>8}   (空)")
            continue
        maxabs = max(abs(a - b) for a, b in zip(v, base))
        scale = max(abs(a) for a in base) or 1.0
        num = sum((a - b) ** 2 for a, b in zip(v, base)) ** 0.5
        den = sum(a * a for a in base) ** 0.5 or 1.0
        print(f"  {K:>3} {len(v):>8} {maxabs:>22.6e} {maxabs/scale:>14.6e} {num/den:>14.6e}")


print("=" * 96)
print("各 K 运行的场差异幅度（K=1 为基准）")
print("=" * 96)

print("\n【冻结前】这些时刻各 K 的决策完全相同（K=1 每步重建，其余在 100 步前也每步重建）")
print("  ⇒ 若此处已有显著差异，则来源不是冻结策略，而是数值噪声累积")
for t in ("0.05", "0.1", "0.2"):
    if os.path.exists(f"s1/{t}/U"):
        compare(t, "U")

print("\n【冻结后】")
for t in ("0.5", "1"):
    if os.path.exists(f"s1/{t}/U"):
        compare(t, "U")
    if os.path.exists(f"s1/{t}/alpha.water"):
        compare(t, "alpha.water")

print()
print("=" * 96)
print("判读标准")
print("=" * 96)
print("  相对差 < 1e-12  ⇒ 浮点末位噪声，轨迹实质相同")
print("  相对差 ~1e-6    ⇒ 弱分岔（线性发散）")
print("  相对差 > 1e-3   ⇒ 强分岔，各 K 面对不同矩阵")
print("  ★ 若【冻结前】就已有 ~1e-3 以上差异，则 100 步内的歧义足以让")
print("    后 244 步的矩阵完全不同 ⇒ (t,a) 不是充分状态，必须含 b。")
