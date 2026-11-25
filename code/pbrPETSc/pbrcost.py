#!/usr/bin/env python3
"""
★★★ pbrcost：机器无关指标的统一评估核心（2026-10-12）

═══ 指标定义 ═══
    cost(π ; ρ) = iters(π) + ρ · rbsteps(π)

  · iters    该策略下压力方程 CG 的累计迭代数
  · rbsteps  该策略下预条件子重建的次数
  · ρ        重建一次相对一次迭代的代价（无量纲当量）

═══ 为什么用它替代墙钟（见 docs/cpu_time_verification_negative_*.md）═══
实测证明：
  · CPU 时间的噪声与墙钟相同（降低倍数 0.92–0.94x），绑核无改善
  · CPU/墙钟 = 0.93–0.94 ⇒ 进程几乎未被剥夺 CPU
  ⇒ 10% 的波动来自内存带宽/缓存争用与频率浮动，是【计算本身变慢】，
    换指标（CPU 时间）与换机器都躲不开。
而 iters 与 rbsteps 是【机器无关】的确定性量。

★ 但"跨轮逐位相同"要逐配置核查，不是全局性质（2026-10-13 第一层审计）：
    fx / l15 / l20 / fl30  跨轮逐位相同 ✓
    fine   R3 差 116 次迭代（0.45%）、rbsteps 差 1
    x3     R3 差 192 次迭代（0.32%）、rbsteps 差 1
    sth    三轮互不相同（iters 2.87%、rbsteps 17.6%，刀刃判据所致）
  ⇒ 论文不得声称"我们的量是零噪声的"，应逐配置说明。
    见 docs/layer1_cpp_verification_7of7_2026-10-13.md。

═══ ρ 的地位 ═══
ρ 是【显式声明的标定参数】，不是物理常数。所有结论必须以
    「对 ρ ∈ [lo, hi]，……」
的形式给出。本模块提供：
  · cost(...)                  —— 指标本体
  · rho_interval_from_order()  —— 从实测排序反解 ρ 的可行区间
  · rho_interval_calib()       —— ★ 由标定值给出 ρ 的【物理区间】[r1, s·r1]
  · rho_sweep()                —— 在 ρ 网格上评估，输出结论的稳健范围

★★ 为什么 ρ 必须报区间而不是点值（2026-10-13，见
   docs/rho_underestimation_code_evidence_2026-10-13.md）：
   C++ 的 buildPC() 每个 SOLVE 调用一次（每步 s 次，实测 s=2.99–3.00），
   但 CSV 只在"每步第一次求解"时写一行，所以该行的 tPCSetup 只含 1/s 的
   分解时间。而 r = tPCSetup/tIter 用的就是这个值。于是：
     · 若"一次重建只付一次分解" ⇒ ρ = r1        （下界）
     · 若"一次重建付 s 次分解" ⇒ ρ = s·r1      （上界，C++ 的 RCOST=step）
   ⇒ 报 [r1, s·r1] 区间，并在整个区间上取 gap/regret 的 min/max。

   ⚠️ "真值更靠近哪一端"目前【无法判定】。曾用"实测最优 K 反解隐含 ρ*"来定它，
      但该反解已撤回（参照量本身不可辨识，见
      docs/layer2_kstar_undecidable_final_2026-10-13.md）。
      ⇒ 这正是必须以完整区间报结论的原因。

═══ 内建审计（本模块的强制部分，调用方无法绕过）═══
  A1 cost 记账一致性：sim_online 的返回值 == iters + ρ·rbsteps
  A2 oracle 自检：oracle ≤ 最优固定周期 ≤ K=1；AMAX > amax_data
  A3 DP 路径重构：从 V 表贪心回溯的成本 == V[1][0]，且 iters/rbsteps 自洽
  A4 模型预测的 iters 对实测（有 C++ 数据的配置）：应精确相等
"""
import os, re, statistics as st
from collections import defaultdict

P2 = "/root/autodl-tmp/PBR"

# 配置 → (levels, T, B0)
# ★ 2026-10-30：sth 的 B0 由 50 改为 100，使七个 OpenFOAM 配置使用同一参数值。
#   理由与实际部署场景一致：预热步数到「覆盖多少求解次数」的换算关系（sth 的 s=4）
#   事前未知，按覆盖量去调 B0 本身就是针对算例的调参；取同一参数值才是零超参数。
#   相位扫描文件不动（锚点见 PHASE_B0_SCAN），故此处改动不影响 N(t,a) 表的来源。
CFG = {
    "fx":   (10, 344, 100),
    "l15":  (15, 344, 100),
    "l20":  (20, 344, 100),
    "fine": (20, 720, 100),
    "x3":   (20, 1231, 100),
    "fl30": (30, 720, 100),
    "sth":  (5, 5866, 100),
}
ORDER = ("fx", "l15", "l20", "fine", "x3", "fl30", "sth")
PHASE_A = 6
PHASE_K = 7

# ★ 相位扫描的「锚点」与策略的「B0」是两件事，必须分开（2026-10-30）。
#
#   相位表 N(t,a) 只依赖「在物理步 t、预条件子年龄 a 时的迭代数」，与扫描从哪个
#   相位起无关。所以现有那批扫描文件（锚点 B0_scan）覆盖的是 t ≳ B0_scan - A 之后
#   的完整 (t,a) 网格；只要策略用的 B0 ≤ B0_scan，就落在已覆盖范围内，无需重扫。
#
#   历史教训：原先把两者绑在 CFG 的同一个 B0 上，改策略的 B0 会让 load_phase 去找
#   一批不存在的 phs_<tag>_B{B0-A..B0} 文件，静默返回 None。
#
#   sth 的扫描锚点是 50（phs_sth_B44..B50_K7 / phsA9_sth B41..B50_K10）；
#   CFG 里的 sth B0 于 2026-10-30 由 50 改为 100（统一七个配置的参数值），
#   但扫描文件不动 —— 见 paper/.manual_backups/20261030_pre_sth_B0_100/README.md。
PHASE_B0_SCAN = {
    "sth": 50,   # 其余配置的 CFG B0 与扫描锚点一致，无需单列
}


def phase_scan_anchor(tag):
    """相位扫描文件所用的锚点 B0（与策略配置的 B0 解耦）。"""
    return PHASE_B0_SCAN.get(tag, CFG[tag][2])


# ───────────────────────────── 数据加载 ─────────────────────────────

def load_phase(tag, A=PHASE_A, K=PHASE_K, verbose=False):
    """读相位扫描的 CSV+log，构建 N(t,a) 实测表。

    ★ 文件查找用 phase_scan_anchor(tag)，返回值里的 B0 用 CFG[tag]（策略口径）。
      两者解耦的原因见 PHASE_B0_SCAN 的注释。
    """
    lvl, T, B0 = CFG[tag]
    Bscan = phase_scan_anchor(tag)
    cells = defaultdict(list); rv = []; facs = []; nfile = 0
    # ★ s = 每步的压力方程求解次数（C++ 的 stepFact）。
    #   直接可测：相位 log 里 "Solving for p_rgh" 的条数 / Time 块数。
    #   【不要】用 nBuildPC 除以重建步数 —— nBuildPC 是跨次求解的静态累加器
    #   （陷阱 32），那样会得到 1.0–2.6 这种错值，进而让 ONLp 口径的模型
    #   偏差 20%+，看起来像模型坏了。
    for B in range(Bscan - A, Bscan + 1):
        c = os.path.join(P2, "phs_%s_B%d_K%d_r1.csv" % (tag, B, K))
        l = os.path.join(P2, "phs_%s" % tag, "log.B%dK%d_r1" % (B, K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        try:
            rr = _rows(c)
            seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            Ns = _per_step_N(l); n = min(len(steps), len(Ns))
            for i in range(n):
                x = steps[i]; rf = int(x["reusedFrom"])
                cells[(i + 1, 0 if rf < 0 else i + 1 - rf)].append(Ns[i])
            for x in rr:
                if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                    rv.append(x["tPCSetup"] / x["tIter"])
            nrb = sum(1 for x in rr if int(x["reused"]) == 0)
            if nrb:
                npg, nblk = _count_p_rgh(l)
                if nblk: facs.append(float(npg) / nblk)
            nfile += 1
        except Exception:
            pass
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=(st.median(rv) if rv else float("nan")),
                s=(st.median(facs) if facs else 3.0),
                T=T, B0=B0, nfile=nfile, lvl=lvl)


_TRE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
_SRE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
        "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
        "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def _per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if _TRE.match(ln):
            if cur: out.append(sum(cur)); cur = []
            continue
        m = _SRE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def _count_p_rgh(p):
    """
    返回 (压力方程 solve 总条数, Time 块数) —— 两者相除即每步分解次数 s。

    ⚠️ 必须用子串匹配：求解器前缀随配置变（PETScILUPCG / PBRPCG / DICPCG …），
    `^Solving for p_rgh` 会一条都匹配不到、静默返回 0。
    """
    npg = 0; nblk = 0
    for ln in open(p, errors="ignore"):
        if _TRE.match(ln):
            nblk += 1
        elif "Solving for p_rgh" in ln:
            npg += 1
    return npg, nblk


def _rows(path):
    o = []
    for ln in open(path, errors="ignore"):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError:
            pass
    return o


# ───────────────────────────── 环境（形状迁移） ─────────────────────────────

class Env:
    """
    N(t,a)。实测优先；缺失用形状迁移 N(t,0)·G(a)。
    与 pbrlib.Env(interp="shape") 逐位等价（下方 A0 审计强制核对）。
    """
    def __init__(self, tab, sFact=1.0):
        self.sFact = sFact
        self.byt = defaultdict(dict)
        for (t, a), v in tab.items(): self.byt[t][a] = v
        bya = defaultdict(list)
        for t, d in self.byt.items():
            for a, v in d.items(): bya[a].append(v)
        self.curve = {a: st.median(v) for a, v in bya.items()}
        ks = sorted(self.curve)
        self.amax_data = ks[-1]
        self._g0 = max(1e-9, self.curve.get(0, 1.0))
        self._gsl = ((self.curve[ks[-1]] - self.curve[ks[-2]]) /
                     max(1e-9, ks[-1] - ks[-2])) if len(ks) >= 2 else 0.0
        self._gsl = max(0.0, self._gsl)
        self.Tmax = max(self.byt)

    def _G(self, a):
        if a in self.curve:
            return self.curve[a] / self._g0
        ks = sorted(self.curve)
        if a < ks[0]:
            return self.curve[ks[0]] / self._g0
        ext = self.curve[ks[-1]] + self._gsl * (a - ks[-1])
        return max(ext, self.curve[ks[-1]]) / self._g0

    def __call__(self, t, a):
        d = self.byt.get(t)
        if d and a in d: return d[a]
        lvl = d[0] if (d and 0 in d) else self.curve.get(0, 1.0)
        return max(1.0, lvl * self._G(a))

    def amax_for(self, T, rho=None, B0=None, reach=None):
        """
        DP 的年龄上限 AMAX（`a >= AMAX` 处强制重建）。

        ★★ 2026-10-12 审计发现的设计缺陷（陷阱 52）：
          曾经写死 `AMAX = amax_data + 1`，即"数据覆盖的最大年龄 + 1"。
          但那【不是】策略会用的最大年龄 —— 在线策略在 sth 上实际用到了
          年龄 10（rebuild 后一直复用），被 AMAX=7 卡住后，DP 无法表达
          "让因子老到 10 岁以上"，于是算出一个比在线还贵的"假 oracle"，
          oracle ≤ 在线 这条硬约束在 sth 上 13 个 ρ 里被违反 11 个。

        AMAX 必须同时覆盖两件事：
          (a) 数据覆盖的年龄（超出部分靠形状迁移外推）
          (b) 在线策略实际达到的年龄（否则 DP 的决策空间比被测策略还小）
        取两者的较大者，再加一点余量，使 DP 真能代表"允许更老"的选项。

        实测稳定性：sth 在 AMAX=50 与 AMAX=1500 上 oracle 完全相同（246049），
        从 20 到 1500 单调不增后收敛 ⇒ 取值不是拟合出来的。
        """
        base = self.amax_data + 1
        if reach is not None and reach + 1 > base:
            return reach + 1
        return base


# ───────────────────────────── 策略（返回 cost/iters/rbsteps） ─────────────────────────────

def sim_fixed(env, rho, K, T, B0):
    it = 0.0; rb = 0; a = 0
    for t in range(1, T + 1):
        if t < B0 or (t - B0) % K == 0:
            it += env(t, 0); rb += 1; a = 1
        else:
            it += env(t, a); a += 1
    return it + rho * rb, it, rb


def sim_online(env, rho, T, B0, stop=None):
    """
    本文在线策略（P0/T0 变体，严格因果）。

    ★ 2026-10-12 审计修正：运行平均 avg 【必须含 ρ·rbsteps】（即"代价"口径），
      不是纯迭代数口径。C++ 的 `onlineDecide()` 用的是 `S.tot`（含 rc），
      写成 `it/(t-1)` 会让决策在 t=B0 附近翻转、并产生相位差 1 的整段偏移
      （l20 决策一致率从 100% 掉到 29%，fl30 掉到 43%）。
    返回 (cost, iters, rbsteps)。需要逐步动作时用 sim_online_detail()。
    """
    c, it, rb, _, _ = sim_online_detail(env, rho, T, B0, stop=stop)
    return c, it, rb


def sim_online_detail(env, rho, T, B0, stop=None, step_cost=False, rho_of_t=None,
                      trace=None):
    """
    在线策略的**唯一**实现（含逐步动作），返回 (cost, iters, rbsteps, pred, mv)。
      · pred[t-1] = 该步是否重建
      · mv[t-1]   = 该步模型给出的 N(t, age)
      · step_cost = True 复现 C++ 的 RCOST=step（ONLp）口径：一次重建的代价
        记作 s·ρ 而不是 ρ（s = 每步分解次数，实测 2.99–3.00）。
      · rho_of_t  = 可选的 ρ 扰动钩子 rho_of_t(t) -> 该步实际使用的 ρ。
        用于「ρ̂ 的标定误差如何影响决策序列」的敏感性实验（2026-10-31 加）。
        因为 MCP 里唯一实现只有这一处，扰动必须插在这里，不能另写一份循环。
      · trace     = 可选列表；传入时逐步 append (t, lhs, avg, margin)，
        margin = lhs - avg（>0 重建），用于「离平局多近」的敏感度分析。
        同样只能在这里取内部状态，不允许另写一份决策循环（2026-10-31 加）。
    其它模块【不得】重写这段逻辑 —— 重复实现曾直接导致一个真实缺陷。
    """
    know = defaultdict(list); levels = []
    it = 0.0; rb = 0; a = 0; acc = 0.0; accn = 0; held = -1; tot = 0.0
    pred = []; mv = []
    n = T if stop is None else stop
    for t in range(1, n + 1):
        rho_t = rho if rho_of_t is None else rho_of_t(t)
        rc1 = rho_t * (env.sFact if step_cost else 1.0)
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            # ★ 代价口径：hist 与 C++ 的 S.tot 一致（含 rho*rbsteps 项）
            avg = acc / accn if accn else tot / max(1, t - 1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2 - d1) / max(1e-9, a2 - a1) * (age - a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            lhs = lvl + max(0.0, delta)
            rebuild = lhs > avg
            if trace is not None:
                trace.append((t, lhs, avg, lhs - avg))
        pred.append(rebuild)
        if rebuild:
            N = env(t, 0); it += N; rb += 1; tot += rc1 + N
            mv.append(N)
            acc, accn = (0.0, 0) if t < B0 else (rc1 + N, 1)
            levels.append(N); a = 1; held = t
        else:
            N = env(t, a); it += N; tot += N
            mv.append(N)
            acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot, it, rb, pred, mv


def sim_dp(env, rho, T, B0, AMAX=None, reach=None):
    """
    最优策略（在下述决策空间内）：
      · 每步可重建，或复用当前因子
      · 年龄 a 达到 AMAX 时强制重建
    AMAX 默认由 env.amax_for(T, reach=reach) 给出 —— ★ 必须把 reach（在线策略
    实际达到的最大年龄）传进来，否则会得到"假 oracle"（陷阱 52）。
    返回 (cost, iters, rbsteps, 路径)。
    """
    if AMAX is None: AMAX = env.amax_for(T, reach=reach)
    INF = float("inf")
    V = [[INF] * (AMAX + 1) for _ in range(T + 2)]
    for a in range(AMAX + 1): V[T + 1][a] = 0.0
    for t in range(T, 0, -1):
        e0 = env(t, 0)
        for a in range(AMAX + 1):
            # ★ 预热边界必须与 sim_fixed / sim_online 一致，都用 `t < B0`（2026-10-30 修）。
            #   原先此处写 `t <= B0`，比另两个策略多强制重建一步 t=B0，
            #   使 DP oracle 系统性偏贵 0.015%–0.127%（七个配置全部如此），
            #   regret 因此被系统性低估。论文 figdata 里的 orc 值用的是 `t < B0`，
            #   即当前仓库代码与已发表数字不一致 —— 按 figdata 对齐。
            if t < B0 or a >= AMAX:
                V[t][a] = rho + e0 + V[t + 1][1]
                continue
            V[t][a] = min(rho + e0 + V[t + 1][1],
                          env(t, a) + V[t + 1][a + 1])
    # 前向回溯重构路径（同时是审计 A3）
    it = 0.0; rb = 0; a = 0; path = []
    for t in range(1, T + 1):
        if t < B0 or a >= AMAX:
            it += env(t, 0); rb += 1; path.append((t, "R")); a = 1; continue
        e0 = env(t, 0); ea = env(t, a)
        if rho + e0 + V[t + 1][1] <= ea + V[t + 1][a + 1]:
            it += e0; rb += 1; path.append((t, "R")); a = 1
        else:
            it += ea; path.append((t, "u")); a += 1
    return it + rho * rb, it, rb, path


# ───────────────────────────── ρ 可行区间 ─────────────────────────────

def rho_interval_from_order(points):
    """
    points: [(name, iters, rbsteps, measured_metric)]
    反解出所有满足「实测更优者 cost 更低」的 ρ。
    返回 (lo, hi, constraints)；lo>hi 表示区间为空。
    """
    lo, hi = float("-inf"), float("inf"); cons = []
    n = len(points)
    for i in range(n):
        for j in range(n):
            if i == j: continue
            ni, ii, ri, wi = points[i]
            nj, ij, rj, wj = points[j]
            if wi >= wj: continue
            d = ri - rj; num = ij - ii
            if abs(d) < 1e-12:
                if num < 0:
                    cons.append(("不可行", ni, nj, None))
                    return 1.0, -1.0, cons
                continue
            b = num / float(d)
            if d > 0: hi = min(hi, b); cons.append(("上界", ni, nj, b))
            else:     lo = max(lo, b); cons.append(("下界", ni, nj, b))
    return lo, hi, cons


def rho_interval_calib(r1, s):
    """
    ★ ρ 的【物理区间】[r1, s·r1]。

      r1 = median(tPCSetup / tIter)   —— CSV 记录的单次分解 / 单次迭代
      s  = 每步重建实际产生的分解次数（实测 2.99–3.00）

    下界的依据："一次重建只付一次分解"（若 CSV 的门控写入恰好覆盖了全部代价）。
    上界的依据："一次重建付 s 次分解"（C++ 的 RCOST=step 分支就是这么算的）。

    ★ 真值在区间内，但【不】等于任一端点。依据是【代码级】的，不依赖任何 K* 反解：

      1) buildPC() 每个 SOLVE 调用一次（每步 s 次），而 CSV 在"每步第一次求解"
         处设了门控，所以该行的 tPCSetup 只含 1/s 的分解时间（源码 355–361 行注释）。
      2) r = tPCSetup_ / tIter 用的就是这个单次值（源码 1068 行）。
      3) s 独立实测 = 2.99–3.00（相位 log 里 "Solving for p_rgh" 条数 / Time 块数）。
      4) C++ 里两个口径都存在：RCOST=solve 用 r，RCOST=step 用 r*stepFact。
         实测中 ONLs 重建 221 次、ONLp 重建 180 次，两者确实不同。

    ⚠️ 2026-10-13：此前这里还引用过"四配置反解的隐含 ρ* 与 s·r1 之比 0.75–1.12"。
      那个反解已被撤回 —— 它依赖"实测 K*=K5"，而逐轮取 K* 时 5/5 配置都不一致
      （在 K3/K4/K5 间翻转，最接近的一轮差 0.03%）。参照量不存在 ⇒ 反解无效。
      见 docs/layer2_kstar_undecidable_final_2026-10-13.md。
    ⇒ 区间 [r1, s·r1] 的成立不依赖该反解；但"真值更靠近哪一端"目前【无法判定】。
      所以按整个区间报结论，不得取点值 —— 这个要求反而更强了。
    """
    return (float(r1), float(r1) * float(s))


def interval_stats(env, rho_lo, rho_hi, T, B0, npts=13, Ks=None, AMAX_slack=0):
    """
    在 ρ ∈ [rho_lo, rho_hi] 上评估一组策略，返回【区间形式】的统计量。

    返回 dict：
      rho_lo / rho_hi     报告的 ρ 区间（即物理标定区间）
      rho_grid            实际取样的 ρ 点（含两端点）
      gap_lo / gap_hi     在线相对【该 ρ 下的最优固定周期】的差，随 ρ 的 min/max
      reg_lo / reg_hi     在线相对 oracle 的 regret，随 ρ 的 min/max
      k1o_lo / k1o_hi     K=1 / 在线的倍数，随 ρ 的 min/max
      kstar_set           最优固定周期 K* 随 ρ 取到的全部值（★ 必须显式报告）
      per_rho             逐 ρ 明细（审计用）
    """
    if rho_hi < rho_lo: rho_lo, rho_hi = rho_hi, rho_lo
    if Ks is None:
        Ks = tuple(k for k in (1, 2, 3, 4, 5, 6) if k <= env.amax_data + 1)
    # 均匀取样，保证含两端点
    grid = sorted(set([rho_lo, rho_hi] +
                      [rho_lo + (rho_hi - rho_lo) * i / float(npts - 1)
                       for i in range(npts)]))

    gaps = []; regs = []; k1o = []; ks = set(); per = []
    for r in grid:
        fx = {K: sim_fixed(env, r, K, T, B0) for K in Ks}
        kb = min(fx, key=lambda k: fx[k][0])
        reach = online_max_age(env, r, T, B0)
        orc = sim_dp(env, r, T, B0, reach=reach)
        onl = sim_online(env, r, T, B0)
        g = 100.0 * (onl[0] / fx[kb][0] - 1.0)
        rg = 100.0 * (onl[0] / orc[0] - 1.0)
        k1r = fx[1][0] / onl[0]
        gaps.append(g); regs.append(rg); k1o.append(k1r); ks.add(kb)
        per.append(dict(rho=r, kstar=kb, c_kst=fx[kb][0], c_onl=onl[0],
                        c_orc=orc[0], it_onl=onl[1], rb_onl=onl[2],
                        gap=g, regret=rg, k1_over_onl=k1r))
    return dict(rho_lo=rho_lo, rho_hi=rho_hi, rho_grid=grid,
                gap_lo=min(gaps), gap_hi=max(gaps),
                reg_lo=min(regs), reg_hi=max(regs),
                k1o_lo=min(k1o), k1o_hi=max(k1o),
                kstar_set=sorted(ks), ks=Ks, per_rho=per)


# ───────────────────────────── 审计 ─────────────────────────────

def online_max_age(env, rho, T, B0):
    """在线策略实际达到的最大年龄（DP 的 AMAX 必须覆盖它）。"""
    _, _, _, pred, _ = sim_online_detail(env, rho, T, B0)
    held = -1; mx = 0
    for t in range(1, T + 1):
        if pred[t - 1]: held = t
        else:
            if held >= 0: mx = max(mx, t - held)
    return mx


def audit_all(cfg, rho, T, B0, cpp_modes=None, tag=""):
    """
    返回 (ok, messages)。任何一条失败都必须在调用方显式处理。
    内建 A1–A4 四项。
    """
    msgs = []; ok = True
    env = cfg["env"]

    # A1 cost 记账一致性
    for nm, f in (("online", lambda: sim_online(env, rho, T, B0)),
                  ("K=1", lambda: sim_fixed(env, rho, 1, T, B0)),
                  ("K=3", lambda: sim_fixed(env, rho, 3, T, B0))):
        c, it, rb = f()
        lhs = it + rho * rb
        if abs(c - lhs) > 1e-6:
            ok = False; msgs.append("★A1 cost 记账不符 (%s): %.4f vs %.4f" % (nm, c, lhs))

    # A2 oracle 自检
    # ★ 先量出在线策略实际达到的最大年龄 —— DP 的决策空间必须不小于它，
    #   否则会得到一个比在线还贵的"假 oracle"（陷阱 52）。
    reach = online_max_age(env, rho, T, B0)
    AMAX = env.amax_for(T, reach=reach)
    if AMAX <= env.amax_data:
        ok = False; msgs.append("★A2 AMAX(%d) <= amax_data(%d)" % (AMAX, env.amax_data))
    # ★ 关键：数据覆盖不到 reach 时，DP 必须能走到 reach+1，否则是假 oracle。
    #   （此处刻意【不】要求 AMAX > reach，因为 amax_for 会在 reach+1 与
    #    amax_data+1 中取较大者，二者相等是合法情形。）
    if max(AMAX, env.amax_data + 1) <= reach:
        ok = False; msgs.append("★A2 AMAX(%d) 无法覆盖在线最大年龄(%d) ⇒ 假 oracle"
                                % (AMAX, reach))
    orc = sim_dp(env, rho, T, B0, AMAX)
    Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data + 1)
    fx = {K: sim_fixed(env, rho, K, T, B0)[0] for K in Ks}
    kb = min(fx, key=fx.get)
    if orc[0] > fx[kb] + 1e-6:
        ok = False; msgs.append("★A2 oracle(%.1f) > 最优固定 K=%d(%.1f)" % (orc[0], kb, fx[kb]))
    if orc[0] > fx[1] + 1e-6:
        ok = False; msgs.append("★A2 oracle(%.1f) > K=1(%.1f)" % (orc[0], fx[1]))
    onl = sim_online(env, rho, T, B0)[0]
    if orc[0] > onl + 1e-6:
        ok = False; msgs.append("★A2 oracle(%.1f) > 在线(%.1f)" % (orc[0], onl))
    # 单次重建后再也不建（t* = B0）也是可达策略
    c_once = sum(rho + env(t, 0) for t in range(1, B0 + 1))
    c_once += sum(env(t, t - B0) for t in range(B0 + 1, T + 1))
    if orc[0] > c_once + 1e-6:
        ok = False; msgs.append("★A2 oracle(%.1f) > 建一次再用到底(%.1f)" % (orc[0], c_once))

    # A3 DP 路径重构自洽
    c_path = orc[1] + rho * orc[2]
    if abs(c_path - orc[0]) > 1e-6:
        ok = False; msgs.append("★A3 路径重构成本(%.4f) != V[1][0](%.4f)" % (c_path, orc[0]))

    # A4 模型预测对实测（★ 分层判据，见陷阱 49）
    #   决策序列：必须 100% 一致 —— 这是可断言的
    #   累计 iters：相对差必须 < 0.1% —— ±1 的翻面会在总量上正负相消
    if cpp_modes:
        for name, (m_it, m_rb) in cpp_modes.items():
            if name.startswith("K") and name[1:].isdigit():
                _, p_it, p_rb = sim_fixed(env, rho, int(name[1:]), T, B0)
            elif name == "ONLs":
                _, p_it, p_rb = sim_online(env, rho, T, B0)
            else:
                continue
            if p_rb != m_rb:
                ok = False
                msgs.append("★A4 %s rbsteps 预测=%d 实测=%d" % (name, p_rb, m_rb))
            rel = 100.0 * (p_it - m_it) / max(1, m_it)
            if abs(rel) > 0.1:
                ok = False
                msgs.append("★A4 %s iters 相对差 %.4f%% (预测=%d 实测=%d) 超过 0.1%%"
                            % (name, rel, p_it, m_it))
    if ok: msgs.append("A1–A4 全部通过")
    return ok, msgs


def rho_sweep(cfg, rhos, T, B0, Ks=None):
    """在 ρ 网格上评估。返回 {ρ: dict(K*, fx, orc, onl, ...)}"""
    env = cfg["env"]
    if Ks is None:
        Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data + 1)
    out = {}
    for r in rhos:
        fx = {K: sim_fixed(env, r, K, T, B0) for K in Ks}
        kb = min(fx, key=lambda k: fx[k][0])
        # ★ 每个 ρ 都要重新量 reach —— 在线达到的最大年龄随 ρ 变
        reach = online_max_age(env, r, T, B0)
        orc = sim_dp(env, r, T, B0, reach=reach)
        onl = sim_online(env, r, T, B0)
        out[r] = dict(Ks=Ks, fx=fx, kb=kb, kk=fx[kb], orc=orc, onl=onl,
                      k1=fx[1], rho=r, reach=reach,
                      amax=env.amax_for(T, reach=reach))
    return out
