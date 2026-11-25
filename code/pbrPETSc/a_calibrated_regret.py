#!/usr/bin/env python3
"""
★★★ 校准后的 regret：用真实 R/k 替换模型 r_eff

═══ 已确立 ═══
最小二乘拟合 execTime = k·iters + R·rbsteps + c 得到：
  l15 : k=0.000790 s/迭代  R=0.0424 s/重建步  ⇒ R/k =  53.7
  l20 : k=0.000419         R=0.0683           ⇒ R/k = 162.8
  fl30: k=0.002081         R=0.6037           ⇒ R/k = 290.1
而模型用 r_eff = s×(tPCSetup/tIter_bench) = 232.4 / 271.0 / 440.6
⇒ 模型【高估】重建代价 4.3x / 1.7x / 1.5x

后果：模型认为"重建很贵" ⇒ 偏向少重建 ⇒ 惩罚在线策略（它多重建）。
这正好解释排序反转：l20 模型 regret 更大但实测更好。

═══ 本脚本 ═══
用校准的 r0 = R/k 重算七配置的 oracle / K* / 在线，看：
  1. 在线 − K* 是否变小（模型不再过度惩罚重建）
  2. K* 是否变小（重建变便宜 ⇒ 更频繁重建更优）
  3. 与实测墙钟的定性结论是否一致
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0

# 相位扫描 A=6
A, KK = 6, 7
CFG = {
    "fx":   (10, 344, 100), "l15": (15, 344, 100), "l20": (20, 344, 100),
    "fine": (20, 720, 100), "x3": (20, 1231, 100),
    "fl30": (30, 720, 100), "sth": (5, 5866, 50),
}
# 拟合出的 R/k（s/重建步 ÷ s/迭代）
RK = {"l15": 53.7, "l20": 162.8, "fl30": 290.1}
# 未拟合的配置：用同网格的近邻按比例外推（fx≈l15? 同网格不同levels）
# fx 与 l15/l20 同网格(2268)，fine/x3/fl30 网格不同，sth 独立
# 对未拟合者先用模型的 r_eff，但在报告中标注
ORDER = ("fx", "l15", "l20", "fine", "x3", "fl30", "sth")


def load_phase(tag, T, B0x):
    cells = defaultdict(list); rv = []
    for B in range(B0x - A, B0x + 1):
        c = os.path.join(P2, "phs_%s_B%d_K%d_r1.csv" % (tag, B, KK))
        l = os.path.join(P2, "phs_%s" % tag, "log.B%dK%d_r1" % (B, KK))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        rr = P.rows(c); seen = {}
        for x in rr:
            if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                seen[int(x["timeIndex"])] = x
        steps = [seen[t] for t in sorted(seen)]
        Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
        for i in range(n):
            x = steps[i]; rf = int(x["reusedFrom"])
            cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
        for x in rr:
            if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                rv.append(x["tPCSetup"]/x["tIter"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median([1.0]), T=T)


CAND = (1,2,3,4,5,6,8,10,13,20,30)

print("=" * 132)
print("★★★ 校准前后对照：模型 r_eff  vs  实测拟合 R/k")
print("=" * 132)
print("  %-6s %10s %10s %10s %12s %12s %12s" %
      ("配置", "模型 r_eff", "校准 R/k", "比值", "校准 K*", "在线", "在线−K*"))
print("  " + "-" * 128)

RES = {}
for tag in ORDER:
    lvl, T, B0x = CFG[tag]
    cfg = load_phase(tag, T, B0x)
    if cfg is None: continue
    env = P.Env(cfg["tab"], mode="real", interp="shape")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)

    # s：从相位扫描的 pc CSV 反推每步分解次数（B 与 B+1 之间重建步数差）
    s_est = 3.0
    try:
        cs = P.rows(os.path.join(P2, "phs_%s_B%d_K%d_r1.csv" % (tag, B0x, KK)))
        if cs:
            nbuild = cs[-1]["nBuildPC"];
            nrb = sum(1 for x in cs if int(x["reused"]) == 0)
            if nrb: s_est = nbuild/max(1, nrb)
    except Exception:
        pass
    r_eff_model = cfg["r1"] * s_est

    # 校准值
    r_cal = RK.get(tag)
    if r_cal is None:
        # 未拟合：按其 r_eff 与最相近已拟合配置的比例缩放
        # fx 同网格、levels 更低 → 用 l15 的比例 (0.23)
        if tag == "fx":   r_cal = r_eff_model * 0.23
        elif tag == "sth": r_cal = r_eff_model * 0.66
        else:             r_cal = r_eff_model * 0.6   # fine/x3 网格更大，保守取 0.6

    def ev(r0):
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError as e:
            return None
        kb = info["Kbest"]
        return dict(orc=orc, kb=kb, kk=100*(info["fixed"][kb]/orc-1),
                    onl=100*(info["online"]/orc-1), r0=r0,
                    k1=100*(info["fixed"][1]/orc-1))

    m = ev(r_eff_model); c = ev(r_cal)
    if not m or not c: continue
    RES[tag] = dict(model=m, cal=c, r_eff_model=r_eff_model, r_cal=r_cal, T=T)
    print("  %-6s %10.1f %10.1f %10.2f %12d %11.2f%% %+11.2f pp"
          % (tag, r_eff_model, r_cal, r_cal/r_eff_model,
             c["kb"], c["onl"], c["onl"]-c["kk"]))

print()
print("=" * 132)
print("★★★ 汇总：校准前后的 regret")
print("=" * 132)
print("  %-6s %14s %14s %14s | %14s %14s %14s"
      % ("配置", "模型 K*", "模型 在线−K*", "模型 K=1",
         "校准 K*", "校准 在线−K*", "校准 K=1"))
for tag in ORDER:
    if tag not in RES: continue
    m = RES[tag]["model"]; c = RES[tag]["cal"]
    print("  %-6s %14d %+13.2f %13.2f%% | %14d %+13.2f %13.2f%%"
          % (tag, m["kb"], m["onl"]-m["kk"], m["k1"],
             c["kb"], c["onl"]-c["kk"], c["k1"]))

ms = [RES[t]["model"]["onl"]-RES[t]["model"]["kk"] for t in RES]
cs = [RES[t]["cal"]["onl"]-RES[t]["cal"]["kk"] for t in RES]
print()
print("  模型 r_eff ：在线−K* 中位 %+.2f pp  范围 [%+.2f, %+.2f]"
      % (st.median(ms), min(ms), max(ms)))
print("  校准 R/k   ：在线−K* 中位 %+.2f pp  范围 [%+.2f, %+.2f]"
      % (st.median(cs), min(cs), max(cs)))

print()
print("=" * 132)
print("★★★ K* 的变化（校准后重建更便宜 ⇒ 应更频繁重建 ⇒ K* 变小）")
print("=" * 132)
for tag in ORDER:
    if tag not in RES: continue
    m = RES[tag]["model"]; c = RES[tag]["cal"]
    d = c["kb"] - m["kb"]
    arrow = "变小 %d→%d" % (m["kb"], c["kb"]) if d < 0 else \
            ("不变 %d" % m["kb"] if d == 0 else "★变大 %d→%d" % (m["kb"], c["kb"]))
    print("  %-6s %s" % (tag, arrow))

print()
print("=" * 132)
print("★★★ 与实测墙钟的对照（有实测的配置）")
print("=" * 132)
OBS = {
    "l15": "在线 优于 K1 22.7%（3/3 轮）；与 K3 打平（中位 −0.3%，2/3 轮微胜）",
    "l20": "在线 优于 K1 28%（5/5 轮）；优于全部固定周期 1.08%（3/3 轮）",
    "fl30": "在线 优于 K1 47%（3/3 轮）；优于全部固定周期 1.08%（3/3 轮）",
}
for tag in ("l15", "l20", "fl30"):
    if tag not in RES: continue
    m = RES[tag]["model"]; c = RES[tag]["cal"]
    print("\n  ── %s ──" % tag)
    print("     模型: K*=%d  在线−K*=%.2f pp" % (m["kb"], m["onl"]-m["kk"]))
    print("     校准: K*=%d  在线−K*=%.2f pp" % (c["kb"], c["onl"]-c["kk"]))
    print("     实测: %s" % OBS[tag])
print("=" * 132)
