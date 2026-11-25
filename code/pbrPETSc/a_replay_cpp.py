#!/usr/bin/env python3
"""
★★★ 逐决策重放：C++ 与 Python 模型到底在哪一步分道扬镳

═══ 背景 ═══
C++ 实测 ONLs（l20, damBreak）: 221 次重建 / 预热后 122 次 / 间隔中位 2
Python 模型（pbrlib, shape 口径, l20）: 39 次重建
两边差 5 倍以上。必须找出分歧点，否则：
  · 不能相信模型层的 regret
  · 不能相信"形状迁移修复了 l15"这个结论

═══ 方法 ═══
C++ 的 online CSV 记录了每一步的 prevN/prevFact/prevAge/rMed，
理论上传够了信息可离线重放。但更直接的做法是：
把 C++ 的逐步观测（rMed, est, avg, runAge, rebuild）与
Python 在【同一份实测数据】上算出的对应量逐步比较。

关键：C++ 用的是【运行时实测】的 dN 表，Python 用的是【形状迁移填充】的
env。两者对同一个 (t,a) 可能给出不同的 N — 这正是分歧的来源之一。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0


def read_online(path):
    rows = []
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append(dict(
                    t=int(float(q[idx["timeIndex"]])),
                    rb=int(float(q[idx["rebuild"]])),
                    age=int(float(q[idx["runAge"]])),
                    est=float(q[idx["est"]]),
                    avg=float(q[idx["avg"]]),
                    rMed=float(q[idx["rMed"]]),
                    pN=float(q[idx["prevN"]]),
                    pFact=float(q[idx["prevFact"]]),
                    pAge=float(q[idx["prevAge"]]),
                    dm=(q[idx["dm"]] if "dm" in idx else "?"),
                ))
            except (ValueError, KeyError):
                pass
    return rows


# ---------- 从 C++ 在线日志反推它看到的"每步迭代数" ----------
# prevN = 该步的 apply 次数（= 该步的 CG 迭代数），在下一步折叠时记录
def cpp_N_series(rows):
    """返回 {t: N} —— 用 prevN 反推（prevN 是【上一步】的 apply 数）"""
    out = {}
    for i, r in enumerate(rows):
        if i > 0 and r["pN"] > 0:
            out[rows[i-1]["t"]] = r["pN"]
    if rows: out[rows[-1]["t"]] = rows[-1]["est"]  # 末步不可知，占位
    return out


def main():
    onl = os.path.join(P2, "a2smoke3_onl_ONLs_r1.csv")
    if not os.path.exists(onl):
        print("★ 找不到 %s" % onl); return
    rows = read_online(onl)
    print("=" * 120)
    print("★★★ C++ ONLs（l20, damBreak）逐决策回放")
    print("=" * 120)
    tot_rb = sum(1 for r in rows if r["rb"] == 1)
    post = [r for r in rows if r["t"] > B0]
    rb_post = [r for r in post if r["rb"] == 1]
    print("  总步数=%d  总重建=%d  预热后重建=%d" % (len(rows), tot_rb, len(rb_post)))
    print("  末行: t=%d age=%d est=%.1f avg=%.1f dm=%s"
          % (rows[-1]["t"], rows[-1]["age"], rows[-1]["est"], rows[-1]["avg"], rows[-1]["dm"]))
    print()
    print("  前 25 步（预热期，应全部重建）:")
    for r in rows[:5]:
        print("    t=%-3d rb=%s age=%-3d est=%-9.1f avg=%-9.1f dm=%s"
              % (r["t"], r["rb"], r["age"], r["est"], r["avg"], r["dm"]))

    # 关键：C++ 的 est 与 avg 量级
    print()
    print("  === 预热后 (t>100) 的 est / avg 分布 ===")
    if post:
        ests = [r["est"] for r in post]
        avgs = [r["avg"] for r in post]
        ages = [r["age"] for r in post]
        print("    est: 中位=%.1f  范围=[%.1f, %.1f]" % (st.median(ests), min(ests), max(ests)))
        print("    avg: 中位=%.1f  范围=[%.1f, %.1f]" % (st.median(avgs), min(avgs), max(avgs)))
        print("    age: 中位=%d  最大=%d" % (st.median(ages), max(ages)))
        # est > avg 的比例
        gt = sum(1 for r in post if r["est"] > r["avg"])
        print("    est>avg 的步数: %d / %d (%.0f%%)  ← 这些步会重建"
              % (gt, len(post), 100.0*gt/len(post)))

    # C++ 的 N 序列 vs 形状迁移模型的预测
    Ns = cpp_N_series(rows)
    ts = sorted(Ns)
    print()
    print("  === C++ 实测的 N(t,0)（预热期）vs 模型 ===")
    for t in (1, 50, 99, 100, 101, 102, 103):
        if t in Ns:
            print("    t=%-4d C++ N=%.1f" % (t, Ns[t]))

    # 用 C++ 实测 N 序列构造 env，看模型在这种情况下会怎么做
    print()
    print("=" * 120)
    print("★★★ 用 C++ 实测的 N(t) 序列构造 env，再跑 Python 在线策略")
    print("=" * 120)
    # 读 rMed 作为 r 的估计
    rmed = [r["rMed"] for r in rows if r["rMed"] > 0]
    r_est = st.median(rmed) if rmed else 0.0
    print("  C++ 报告的 rMed 中位 = %.2f" % r_est)
    print("  （注意：C++ 的 rMed 是【单次分解】的 r，r_eff = s·r）")

    # 构造一个只含 age=0 的 env（因为 C++ 的 N 序列是每步重建的 N(t,0)）
    tab0 = {(t, 0): Ns[t] for t in ts if t in Ns}
    env0 = P.Env(tab0, mode="real", interp="shape")
    T = max(ts)
    for s in (1, 2, 3, 4):
        r_eff = r_est * s
        try:
            orc = P.sim_dp(env0, r_eff, T)
            onl_py = P.sim_online(env0, r_eff, T)
            fx1 = P.sim_fixed(env0, r_eff, 1, T)
            print("    s=%d  r_eff=%7.1f   oracle=%10.0f  K=1=%10.0f  在线=%10.0f  (在线/K1=%.3f)"
                  % (s, r_eff, orc, fx1, onl_py, onl_py/fx1))
        except AssertionError as e:
            print("    s=%d  ★自检失败" % s)


main()
