#!/usr/bin/env python3
"""
★★★ a_k234_verdict.py —— 第二层裁决：实测 K* vs 模型预测的 K*

★ 硬约束（项目计时口径）：
   所有比较必须在【同一批次、同轮交错】内进行，取重复测量的中位数。
   本脚本只读本批次（TAG=k2<name>）的 log，不与历史批次混合比较。

★ 判据（两项都要过才算"K* 确认"）：
   V1  实测最优 K 是否在统计上与模型的 K* 相容？（用中位墙钟 + 轮间极差）
   V2  iters/rbsteps 是否复现模型预测？（这是机器无关的量，应精确）
"""
import sys, os, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, Env, CFG, sim_fixed, P2

CAL = {"fx": 57.9, "l15": 77.7, "l20": 90.6, "fine": 115.2,
       "x3": 113.2, "fl30": 147.4, "sth": 17.0}
TAGS = {"fx": "k2fx", "l15": "k2l15", "fine": "k2fine",
        "l20": "k2l20", "x3": "k2x3"}

LOGRE = re.compile(r"round=(\d+) mode=(K\d) K=(\d+) wall_ms=(\d+) execTime=([\d.]+) "
                   r"iters=(\d+) nsteps=(\d+) rbsteps=(\d+)")


def read_batch(tag):
    """读一个配置本批次的全部 log，返回 {mode: [dict,...]}"""
    f = "%s/%s.log" % (P2, tag)
    if not os.path.exists(f): return None
    out = {}
    for ln in open(f, errors="ignore"):
        m = LOGRE.search(ln)
        if not m: continue
        r, mode = int(m.group(1)), m.group(2)
        out.setdefault(mode, []).append(
            dict(r=r, wall=int(m.group(4)), et=float(m.group(5)),
                 iters=int(m.group(6)), nsteps=int(m.group(7)),
                 rb=int(m.group(8))))
    return out


def main():
    print("=" * 122)
    print("★★★ 第二层裁决：K=2 / K=4 补测 —— 实测 K* vs 模型预测")
    print("=" * 122)
    for name, tag in TAGS.items():
        b = read_batch(tag)
        if not b:
            print("\n【%s】本批次还没产出" % name); continue
        d = load_phase(name); lvl, T, B0 = CFG[name]
        env = Env(d["tab"], sFact=d["s"]); rho = CAL[name]
        modes = sorted(b, key=lambda x: int(x[1:]))

        print("\n" + "─" * 122)
        print("【%s】levels=%d T=%d ρ=%.1f  本批次轮数=%d"
              % (name, lvl, T, rho, max(len(v) for v in b.values())))
        print("  %-5s %12s %12s %12s %10s %10s" %
              ("mode", "墙钟中位ms", "轮间极差%", "iters中位", "rbsteps", "模型iters"))
        rows = {}
        for m in modes:
            v = b[m]
            w = [x["wall"] for x in v]
            it = [x["iters"] for x in v]
            rb = [x["rb"] for x in v]
            K = int(m[1:])
            _, p_it, p_rb = sim_fixed(env, rho, K, T, B0)
            med = st.median(w)
            rng = 100.0 * (max(w) - min(w)) / med
            rows[m] = dict(med=med, rng=rng, it=st.median(it), rb=st.median(rb),
                           model_it=p_it, model_rb=p_rb, n=len(v))
            print("  %-5s %12.0f %11.1f%% %12.0f %10d %10d" %
                  (m, med, rng, st.median(it), st.median(rb), p_it))
        # 实测最优
        best = min(rows, key=lambda m: rows[m]["med"])
        srt = sorted(rows, key=lambda m: rows[m]["med"])
        print()
        print("  实测排序（墙钟中位，快→慢）: %s"
              % " < ".join("%s(%.0f)" % (m, rows[m]["med"]) for m in srt))
        gap = 100.0 * (rows[srt[1]]["med"] - rows[best]["med"]) / rows[best]["med"]
        print("  实测最优 = %s；与次优差 %.2f%%；该模式轮间极差 %.1f%%"
              % (best, gap, rows[best]["rng"]))
        # 模型最优（用同一 ρ 与同一 N 表）
        Ks = tuple(k for k in (1, 2, 3, 4, 5, 6) if k <= env.amax_data + 1)
        cm = {("K%d" % K): sim_fixed(env, rho, K, T, B0)[0] for K in Ks}
        mb = min(cm, key=cm.get)
        print("  模型最优 = %s（cost=%.0f）" % (mb, cm[mb]))
        print("  V1 实测 K* 与模型 K* 一致？ %s" %
              ("✓ 是" if best == mb else "★ 否（实测 %s / 模型 %s）" % (best, mb)))
        # V2 迭代数复现
        worst = 0.0; worst_m = None
        for m in rows:
            r = rows[m]
            if r["model_it"] and r["it"]:
                rel = 100.0 * (r["it"] - r["model_it"]) / r["model_it"]
                if abs(rel) > abs(worst): worst = rel; worst_m = m
        print("  V2 迭代数复现：最大相对差 = %+.4f%%（在 %s）  %s"
              % (worst, worst_m, "✓ 通过(<0.1%)" if abs(worst) < 0.1 else "★ 超阈"))
    print()
    print("=" * 122)


main()
