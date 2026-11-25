#!/usr/bin/env python3
"""
★★★ a_win2_verdict.py —— 证据链 (b)：跨【真实物理阶段】的 K* 是否移动

═══════════════════════════════════════════════════════════════════════
与 (a) 的本质区别
═══════════════════════════════════════════════════════════════════════
(a) 在同一个 344 步窗口内切半 —— 段间无系统性物理变化
    ⇒ 结果：K* 漂移存在但 penalty ≤ 1.3%（否定性）

(b) 用 endTime=2 的实跑，跨【物理时刻 1.0】切分：
      窗口 1 = [0, 1]   溃坝 → 撞击壁面（快漂移）
      窗口 2 = [1, 2]   反弹 → 衰减（慢漂移）
    ⇒ 这才对应 Stefan 那类真实的阶段变化

═══════════════════════════════════════════════════════════════════════
★ 方法：完全绕开相位表与模型，纯用实测
═══════════════════════════════════════════════════════════════════════
对每个 K、每一轮：
    cost_K(W) = Σ_{t∈W} N_measured(t) + ρ · |{t∈W : 该步重建}|
其中
    N_measured(t)  来自该 K 的 log（No Iterations 按 Time 块求和）
    是否重建        来自该 K 的 pc CSV（reusedFrom < 0）
    ρ              取该配置的标定区间 [r1, s·r1]

★ 这样做的理由：相位表只覆盖 T=344，无法为窗口 2 提供 N(t,a)；
  而实跑本身已经包含了"用这个 K 会付出什么"的全部信息。
  ⇒ 无需模型、无需外推，是【直接测量】。

═══════════════════════════════════════════════════════════════════════
审计项
═══════════════════════════════════════════════════════════════════════
W1  窗口 1（t ∈ [0,1]）的前 344 步是否与既有 k2<name> 数据逐位一致？
    （若一致 ⇒ endTime 延长没有污染前段，两批数据可直接比较）
W2  窗口 2 的步数是否合理（预期与窗口 1 同量级）
W3  rbsteps 是否等于解析式（周期结构不依赖求解器）
W4  K* 在窗口 1 与窗口 2 是否不同（核心问题）
W5  跨窗口用单一 K 的 penalty（决定"自适应是否必要"）
"""
import sys, os, re, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, _rows

P = "/root/autodl-tmp/PBR"
CAL = {"fx": (57.9, 3.0), "l20": (90.6, 3.0)}
KS = (1, 2, 3, 4, 5, 6)
TRE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
NRE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")


def read_run(tag, K, r):
    """返回 (phys_times, per_step_N, per_step_rebuild) 三个等长列表。"""
    pre = "w2" + tag          # 产出前缀是 w2fx / w2l20
    lg = "%s/%s_case/log.K%d.r%d" % (P, pre, K, r)
    pc = "%s/%s_pc_K%d_r%d.csv" % (P, pre, K, r)
    if not (os.path.exists(lg) and os.path.exists(pc)): return None
    times = []; Ns = []
    cur = []
    for ln in open(lg, errors="ignore"):
        m = TRE.match(ln)
        if m:
            if Ns or cur: Ns.append(sum(cur)); cur = []
            times.append(float(m.group(1)))
            continue
        mm = NRE.search(ln)
        if mm: cur.append(int(mm.group(1)))
    if cur: Ns.append(sum(cur))
    # Ns 可能比 times 多 1（末尾），对齐
    n = min(len(times), len(Ns))
    times, Ns = times[:n], Ns[:n]

    rr = _rows(pc); seen = {}
    for x in rr:
        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
            seen[int(x["timeIndex"])] = x
    steps = [seen[t] for t in sorted(seen)]
    reb = [int(steps[i]["reusedFrom"]) < 0 for i in range(len(steps))]
    m = min(n, len(reb))
    return times[:m], Ns[:m], reb[:m]


def window_split(times, tsplit=1.0):
    """按物理时刻切分，返回两个下标列表。"""
    w1 = [i for i, t in enumerate(times) if t <= tsplit]
    w2 = [i for i, t in enumerate(times) if t > tsplit]
    return w1, w2


def cost_of(Ns, reb, idx, rho):
    it = sum(Ns[i] for i in idx)
    rb = sum(1 for i in idx if reb[i])
    return it + rho * rb, it, rb


def main():
    print("=" * 122)
    print("★★★ 证据链 (b)：跨真实物理阶段的 K* 移动（endTime 2，窗口 = [0,1] vs [1,2]）")
    print("=" * 122)

    for tag in ("fx", "l20"):
        r1, sfac = CAL[tag]
        print("\n" + "─" * 122)
        print("【%s】ρ ∈ [%.1f, %.1f]" % (tag, r1, r1 * sfac))

        data = {}
        for K in KS:
            for r in (1, 2, 3):
                out = read_run(tag, K, r)
                if out: data.setdefault((K, r), out)
        if not data:
            print("   ★ 本配置还没产出"); continue

        # ── W2 步数与切分
        t1, N1, b1 = data[(1, 1)]
        w1, w2 = window_split(t1)
        print("   W2 总步数=%d  窗口1(t≤1.0)=%d 步  窗口2(t>1.0)=%d 步  物理终点=%.4f"
              % (len(t1), len(w1), len(w2), t1[-1]))

        # ── W1 与既有 k2<tag> 的前段比对（审计延长是否污染前段）
        old = "%s/k2%s.log" % (P, tag)
        oldn = None
        if os.path.exists(old):
            for ln in open(old, errors="ignore"):
                m = re.search(r"mode=K1 K=1 .*iters=(\d+) nsteps=(\d+)", ln)
                if m: oldn = (int(m.group(1)), int(m.group(2))); break
        if oldn:
            n_new = sum(N1[i] for i in w1)
            print("   W1 前段一致性: 既有 K=1 iters=%d(%d 步) vs 本次窗口1 iters=%d(%d 步)  %s"
                  % (oldn[0], oldn[1], n_new, len(w1),
                     "✓ 一致" if abs(n_new - oldn[0]) <= 2 else "★ 不一致（延长可能污染前段）"))

        # ── W3 rbsteps 解析式核对
        bad = []
        for (K, r), (tt, NN, bb) in data.items():
            nrb = sum(1 for x in bb if x)
            # 解析：t<B0 全建；t>=B0 且 (t-B0)%K==0 建。B0=100
            B0 = 100
            exp = sum(1 for i in range(1, len(bb) + 1)
                      if i < B0 or (i - B0) % K == 0)
            if nrb != exp: bad.append((K, r, nrb, exp))
        print("   W3 rbsteps 解析式核对：%d 组，不符 %d 组%s"
              % (len(data), len(bad), ("  ★ " + str(bad[:3])) if bad else " ✓"))

        # ── W4 两个窗口的 K*
        for lab, rho in (("ρ=r1", r1), ("ρ=s·r1", r1 * sfac)):
            rows = []
            for K in KS:
                c1 = []; c2 = []
                for r in (1, 2, 3):
                    if (K, r) not in data: continue
                    tt, NN, bb = data[(K, r)]
                    ia, ib = window_split(tt)
                    c1.append(cost_of(NN, bb, ia, rho)[0])
                    c2.append(cost_of(NN, bb, ib, rho)[0])
                if not c1: continue
                rows.append((K, st.median(c1), st.median(c2)))
            if not rows: continue
            k1 = min(rows, key=lambda x: x[1])[0]
            k2 = min(rows, key=lambda x: x[2])[0]
            single = min(rows, key=lambda x: x[1] + x[2])[0]
            seg = min(x[1] for x in rows) + min(x[2] for x in rows)
            wh = min(x[1] + x[2] for x in rows)
            pen = 100.0 * (wh - seg) / seg if seg else 0.0
            print("   %-9s 窗口1 K*=%d   窗口2 K*=%d   单K跨两窗最优=%d   penalty=%.3f%%   %s"
                  % (lab, k1, k2, single, pen, "★ 漂移" if k1 != k2 else "无漂移"))
            print("            各 K 成本: %s"
                  % "  ".join("K%d=(%.0f,%.0f)" % (K, a, b) for K, a, b in rows))

    print()
    print("=" * 122)


main()
