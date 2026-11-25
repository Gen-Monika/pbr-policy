#!/usr/bin/env python3
"""
★★★ PBRLib：本项目的统一分析核心（2026-10-12 起）

═══ 为什么要有这个文件 ═══
oracle 的 bug 连续在三处独立出现（A1c、Stage D、drift 判别），根因是
【每个脚本各带一份 DP 实现】。本模块把所有环境构造与策略评估集中到一处，
并强制通过自检 —— 任何脚本直接 import，不再自己实现。

═══ 已修正的三个 bug（全部记录在案）═══
  bug 1（查表缺失回退）  Nfn 缺 (t,a) 时回退到"最近年龄" ⇒ 大年龄取到小年龄的值
                        ⇒ oracle 低于物理下界 2 倍。
                        修法：严格单调插值/外推，绝不"就近回退"。
  bug 2（AMAX 太小）     a+1 > AMAX 时只剩重建分支 ⇒ DP 被强迫周期重建
                        ⇒ oracle 虚高，frozen 下 regret 变负（−54%）。
                        修法：AMAX 必须覆盖该数据集真正需要的最大年龄；
                        real 用数据覆盖范围，frozen 用 T−b0。
  bug 3（入口状态）      V[t][a] 的 a 是"第 t 步开始前"的年龄 ⇒ 入口应 V[1][0]。
                        修法：显式声明语义，并在 docstring 里写死。

═══ 关于表稀疏性的显式处理 ═══
实测每个 t 上只有 1–5 个年龄有数据。因此 N(t,a) 必须由插值给出，
本模块提供四种插值模式（可切换、可做敏感性对比）：
  "step"   阶梯（取不超过 a 的最大可用年龄）—— 保守，最常用
  "linear" 对当前 t 的可用点做线性插值，超范围按末端斜率外推
  "curve"  一律用全局 (a→N) 曲线（完全忽略 t 依赖）
  "shape"  ★ 默认（2026-10-12 起）：形状迁移
             N(t,a) = N(t,0) × G(a)，G(a)=curve(a)/curve(0)
           实测值优先；缺失时用"水平×形状"填补。

═══ 为什么 "shape" 成为默认（陷阱 37）═══
"linear" 的超范围外推用【全局曲线末端斜率】gslope 去填【局部】空洞。
覆盖补到 age=29 后 gslope 涨到 383，于是 env(t=100, a=1) 返回 405，
而实测真值是 46 —— 高估 8.8 倍，把在线策略推入"每步重建"的退化，
regret 从 7% 跳到 106%。
改成 clamp（取端点值）则另一个极端：大年龄免费 ⇒ "建一次用到底"
比 DP oracle 还便宜 ⇒ 自检断言崩（fl30 / sth）。

"shape" 的物理依据：预条件子老化导致的迭代数增长主要取决于
【老化了多少步】，与【在哪一步老化】关系弱 ⇒ 形状可跨 t 迁移，
水平 N(t,0) 随 t 变化（保留非平稳性）。

验证（docs/shape_transfer_decision_2026-10-12.md）：
  · 留一年龄交叉验证：7/7 配置的预测/实测 中位偏差都在 ±7% 内，
    且方向不固定（无系统偏袒）
  · 压力测试 |ε|≤0.20：6/7 配置 regret 变化 <5 pp 且不崩
  · 自检：7/7 通过（clamp 在 fl30/sth 上失败）
  · 已知弱点：fl30 的最偏年龄(age=4, −37.5%)正在决策边界；
              sth 在 ε=−0.30 时自检崩
用法：interp="shape"；用 eps 参数做保形扰动压力测试。
"""
import os, re, statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

B0 = 100          # 预热期：t < B0 每步强制重建（PBR 冻结语义）


# ─────────────────────────── 数据读取 ───────────────────────────

def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur)); cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def load_config(tag, logdir, rounds, Ks):
    """从 K 扫描的 CSV+日志构建 (t, age) → N 的表，以及 r 与每步分解次数。"""
    cells = defaultdict(list); rv = []; fac = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c); seen = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                    seen[int(d["timeIndex"])] = d
            rr = [seen[t] for t in sorted(seen)]
            Ns = per_step_N(l); n = min(len(rr), len(Ns))
            if ns is None or n > ns: ns = n
            for i in range(n):
                d = rr[i]; t = i + 1
                rf = int(d["reusedFrom"])
                cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
            allr = rows(c)
            for d in allr:
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
            rbs = set(int(d["timeIndex"]) for d in allr if int(d["reused"]) == 0)
            nrs = sum(1 for d in allr if int(d["reused"]) == 0)
            if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


# ─────────────────────────── 环境构造 ───────────────────────────

class Env:
    """
    N(t, a) —— 时间步 t、预条件子年龄 a 时的该步迭代数。

    语义（写死，避免 bug 3 那类歧义）：
      real     : 用实测表，缺失点按 mode 插值
      scramble : 把实测表在 t 维随机置换（去时间结构，保留边际分布）
      frozen   : N(t,a) := N(t,0)，对所有 a 有定义（无劣化）

    插值模式 interp：
      "shape"  ★默认：形状迁移 N(t,0)×G(a)（见模块头说明）
      "step"   阶梯 / "linear" 线性插值+外推 / "curve" 全局曲线
    """

    def __init__(self, tab, mode="real", interp="shape", rng=None, eps=0.0):
        self.mode = mode
        self.interp = interp
        byt = defaultdict(dict)
        for (t, a), v in tab.items(): byt[t][a] = v
        self.Tmax = max(byt)
        real_t = sorted(t for t in byt if byt[t])

        if mode == "scramble":
            if rng is None: rng = __import__("random").Random(0)
            perm = real_t[:]; rng.shuffle(perm)
            byt = {dst: dict(byt[src]) for src, dst in zip(real_t, perm)}

        self.byt = byt
        self.sa = {t: sorted(d) for t, d in byt.items()}

        bya = defaultdict(list)
        for t, d in byt.items():
            for a, v in d.items(): bya[a].append(v)
        self.curve = {a: st.median(v) for a, v in bya.items()}
        ks = sorted(self.curve)
        self.amax_data = ks[-1]
        self.gslope = ((self.curve[ks[-1]] - self.curve[ks[-2]]) /
                       max(1e-9, ks[-1]-ks[-2])) if len(ks) >= 2 else 1.0
        self.gslope = max(1e-6, self.gslope)

        # ---- shape 模式的预计算 ----
        # G(a) = curve(a)/curve(0)：年龄增长因子（跨 t 汇总的形状）
        self._eps = eps                     # 保形扰动，用于压力测试
        self._g0 = self.curve.get(0)
        if not self._g0:
            self._g0 = st.median(list(self.curve.values())) if self.curve else 1.0
        self._g0 = max(1e-9, self._g0)
        self._gsl_shape = ((self.curve[ks[-1]] - self.curve[ks[-2]]) /
                           max(1e-9, ks[-1]-ks[-2])) if len(ks) >= 2 else 0.0
        self._gsl_shape = max(0.0, self._gsl_shape)

    def _G(self, a):
        """G(a)：a 岁的迭代数相对 a=0 的倍数（形状迁移用）。"""
        if a in self.curve:
            base = self.curve[a]/self._g0
        else:
            ks = sorted(self.curve)
            if a < ks[0]:
                base = self.curve[ks[0]]/self._g0
            else:
                # 超出实测范围：对形状做【单调延伸】，不用局部空洞的斜率
                ext = self.curve[ks[-1]] + self._gsl_shape*(a - ks[-1])
                base = max(ext, self.curve[ks[-1]])/self._g0
        # 保形扰动（ε 随年龄放大，反映"越老越不确定"）
        return base*(1.0 + self._eps*min(1.0, a/5.0))

    def __call__(self, t, a):
        if self.mode == "frozen":
            d = self.byt.get(t)
            if d: return d.get(0, self.curve[0])
            return self.curve.get(0, 1.0)

        if self.interp == "shape":
            d = self.byt.get(t)
            if d and a in d:
                return d[a]                      # 实测优先
            lvl = self.curve.get(0, 1.0)
            if d and 0 in d:
                lvl = d[0]                       # 水平用本 t 的 N(t,0)
            return max(1.0, lvl*self._G(a))

        d = self.byt.get(t)
        if not d:
            if self.interp == "curve" or True:
                if a in self.curve: return self.curve[a]
                return self.curve[self.amax_data] + self.gslope*(a - self.amax_data)

        if self.interp == "curve":
            if a in self.curve: return self.curve[a]
            return self.curve[self.amax_data] + self.gslope*(a - self.amax_data)

        ages = self.sa[t]
        if a in d: return d[a]

        if self.interp == "step":
            lo = [x for x in ages if x <= a]
            if lo: return d[lo[-1]]
            return d[ages[0]]

        # linear：对当前 t 的可用点插值，超范围按末端斜率外推
        if a <= ages[0]: return d[ages[0]]
        if a >= ages[-1]:
            if len(ages) >= 2:
                sl = (d[ages[-1]] - d[ages[-2]])/max(1e-9, ages[-1]-ages[-2])
            else:
                sl = self.gslope
            return d[ages[-1]] + max(sl, self.gslope)*(a - ages[-1])
        lo = max(x for x in ages if x <= a)
        hi = min(x for x in ages if x >= a)
        if hi == lo: return d[lo]
        w = (a - lo)/(hi - lo)
        return (1-w)*d[lo] + w*d[hi]

    def amax_for(self, T, dataset="real"):
        """
        ★ bug 2 的修法（含 off-by-one，2026-10-12 第二次修正）。

        DP 里 `a >= AMAX` 会强制重建，所以 AMAX 是【不可达】的首个年龄。
        要表达"年龄最大为 amax_data"的策略，必须令 AMAX = amax_data + 1。
        曾错写成 AMAX = amax_data ⇒ 连 age = amax_data 都不可达
        ⇒ 无法表达 K=5（fl30）或 K=13（Stefan）这类【数据里确实测过】的策略
        ⇒ oracle 反而比最优固定周期还贵。

           real/scramble：AMAX = 数据覆盖的最大年龄 + 1
           frozen       ：AMAX = T − B0（容纳"预热后永不再建"）
        """
        if self.mode == "frozen":
            return max(self.amax_data + 1, T - B0)
        return self.amax_data + 1


# ─────────────────────────── 策略 ───────────────────────────

def sim_fixed(env, r0, K, T):
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < B0 or (t-B0) % K == 0:
            tot += r0 + env(t, 0); a = 1
        else:
            tot += env(t, a); a += 1
    return tot


def sim_dp(env, r0, T, AMAX=None):
    """
    真 oracle（DP 上界）。

    语义：V[t][a] = 从"第 t 步开始前、持有因子的年龄为 a"出发的最小剩余成本。
      · 第 t 步重建：付 r0 + env(t,0)，之后年龄变 1 ⇒ V[t+1][1]
      · 第 t 步复用：付 env(t,a)，之后年龄变 a+1 ⇒ V[t+1][a+1]
      · t ≤ B0 或 a ≥ AMAX 时强制重建（预热语义 / 数据边界）
      · 入口 V[1][0]：第 1 步开始前还没建过（★ bug 3）
    """
    if AMAX is None:
        AMAX = env.amax_for(T)
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            if t <= B0 or a >= AMAX:
                V[t][a] = r0 + env(t, 0) + V[t+1][1]
                continue
            V[t][a] = min(r0 + env(t, 0) + V[t+1][1],
                          env(t, a) + V[t+1][a+1])
    return V[1][0]


def sim_online(env, r0, T, lvl_mode="last"):
    """本文在线策略（P0 变体）：年龄驱动 + 运行平均，严格因果。"""
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    for t in range(1, T+1):
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if lvl_mode == "trend" and len(levels) >= 2:
                lvl = levels[-1] + (levels[-1] - levels[-2])
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < B0 else (c, 1)
            levels.append(N); a = 1; held = t
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot


def sim_reac(env, r0, T, reac):
    """Code_Aster REAC_PRECOND：迭代数超过 reac 则重分解。"""
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < B0 or a == 0: rebuild = True
        else: rebuild = env(t, a) > reac
        if rebuild:
            tot += r0 + env(t, 0); a = 1
        else:
            tot += env(t, a); a += 1
    return tot


def sim_chalmers(env, r0, T, factor=2.0, floor=10.0):
    """Chalmers：迭代数超过 max(factor·k₀, floor) 则重建。"""
    tot = 0.0; a = 0; k0 = None
    for t in range(1, T+1):
        N = env(t, 0 if a == 0 else a)
        if t < B0 or a == 0: rebuild = True
        else: rebuild = N > max(factor*(k0 if k0 else N), floor)
        if rebuild:
            k0 = env(t, 0); tot += r0 + env(t, 0); a = 1
        else:
            tot += N; a += 1
    return tot


# ─────────────────────────── 自检 ───────────────────────────

def selfcheck(env, r0, T, AMAX=None, label="", Ks=None):
    """
    ★ 强制自检（bug 9 的教训：自检必须由函数本体执行，不能靠调用方自觉）。
    返回 (orc, 各策略成本 dict)，任一自检失败即抛异常。
    """
    if AMAX is None: AMAX = env.amax_for(T)
    orc = sim_dp(env, r0, T, AMAX)

    # ★ 候选 K 必须受数据边界限制（默认取数据覆盖的最大年龄 + 1）
    if Ks is None:
        Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30,50)
                   if k <= env.amax_data + 1)
    fx = {K: sim_fixed(env, r0, K, T) for K in Ks}
    kb = min(fx, key=fx.get)
    onl = sim_online(env, r0, T)

    # 不可达下界（仅作参考信息）：假设"每步只付 env(t,0) 而不付重建费"
    lb_soft = sum(env(t, 0) for t in range(1, T+1))

    # 「预热后在 t* 建一次再永不复用」也是可达策略，必须一并检查
    once = []
    for tstar in (B0, B0 + (T-B0)//4, B0 + (T-B0)//2, B0 + 3*(T-B0)//4):
        c = sum(r0 + env(t, 0) for t in range(1, tstar+1))
        c += sum(env(t, t - tstar) for t in range(tstar+1, T+1))
        once.append(c)
    c_once_min = min(once)

    fails = []
    if orc > fx[kb] + 1e-6:
        fails.append("oracle(%.0f) > 最优固定周期 K=%d(%.0f) 差%.0f"
                     % (orc, kb, fx[kb], orc - fx[kb]))
    if orc > onl + 1e-6:
        fails.append("oracle(%.0f) > 在线(%.0f) 差%.0f" % (orc, onl, orc - onl))
    if orc > c_once_min + 1e-6:
        fails.append("oracle(%.0f) > 建一次再用到底(%.0f) 差%.0f"
                     % (orc, c_once_min, orc - c_once_min))
    if AMAX <= env.amax_data:
        fails.append("AMAX(%d) 必须 > 数据覆盖(%d)" % (AMAX, env.amax_data))
    if fails:
        raise AssertionError("[自检失败 %s] " % label + "; ".join(fails))

    return orc, dict(fixed=fx, Kbest=kb, c_Kbest=fx[kb], online=onl,
                     lb_soft=lb_soft, c_once=c_once_min, AMAX=AMAX,
                     ratios=dict(orc_per_step=orc/T, K1_per_step=fx[1]/T,
                                 onl_per_step=onl/T))


# ─────────────────────────── 配置清单 ───────────────────────────

CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8]),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8]),
    ("fl30", "fl30run", [1,2],             [1,3,5]),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8]),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13]),
]
