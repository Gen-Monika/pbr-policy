#!/usr/bin/env python3
"""
★★★ A-终（七配置统一版，2026-10-12）

═══ 目的 ═══
七个配置在【统一的年龄覆盖 (~30)】下横向对比，回答：
  1. 在线策略相对 oracle 的 regret 有多大？
  2. 相对最优固定周期 K* 差多少 pp？
  3. 覆盖补足后，之前那些"在线差很多"的结论还成立吗？

═══ 相对旧版的修正 ═══
  (1) 显式 (csv_prefix, logdir) 映射 —— 修掉了 basename(logdir) 不等于 CSV 前缀
      导致 fx 静默丢掉 K=1..8 的 bug（当时 regret 假报 46.28%，真值 3.46%）
  (2) 强制核对每个批次实际载入的文件数，为 0 直接报警
  (3) 全部策略评估走 pbrlib 的 sim_dp / sim_fixed / sim_online + selfcheck()
      不再各脚本自带一份 DP
  (4) 候选 K 受数据边界限制（K ≤ amax_data + 1），避免用外推区造出假最优

═══ 关于 sth 的批次说明 ═══
  sth 的 CSV 步数 5866，而 stefan/ 里 K∈{1,5,8,13} 的 r1..r3 log 是 15642 步
  （目录被两个 endTime 批次复用，长批覆盖了同名 log）。
  已实测核验：短批与长批前 5866 步的迭代数序列【逐位完全相同】，
  min(len,len) 的截断无损。（见 docs/data_integrity_audit_sth_batch_2026-10-12.md）
  为保持各 K 的样本一致，sth 统一取 R=1,2,3。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → [(csv_prefix, logdir, Ks, rounds), ...]
MERGED = {
    "fx":   [("fx",      "%s/fixed" % P2,        [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3])],
    "l20":  [("l20",     "%s/l20" % P2,          [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3])],
    "l15":  [("l15",     "%s/l15" % P2,          [1,2,3,5,8], [1,2,3,4,5]),
             ("cov2_l15", "%s/cov2_l15" % P2,    [13,20,30], [1,2,3])],
    "fine": [("fine",    "%s/finerun" % P2,      [1,2,3,5,8], [1,2,3]),
             ("cov2_fine", "%s/cov2_fine" % P2,  [13,20,30], [1,2,3])],
    "x3":   [("x3",      "%s/x3run" % P2,        [1,2,3,5,8], [1,2]),
             ("cov2_x3", "%s/cov2_x3" % P2,      [13,20,30], [1,2,3])],
    "fl30": [("fl30",    "%s/fl30run" % P2,      [1,3,5],     [1,2]),
             ("cov2_fl30", "%s/cov2_fl30" % P2,  [8,13,20,30], [1,2,3])],
    "sth":  [("sth",     "%s/stefan" % P2,       [1,2,3,5,8,13], [1,2,3]),
             ("cov2_sth", "%s/cov2_sth" % P2,    [20,30], [1,2,3])],
}

# 期望的 r（校验用，来自各配置的历史测量）
R_EXP = {"fx": None, "l15": 78.02, "l20": 90.79, "fine": 114.83,
         "x3": 114.12, "fl30": 147.10, "sth": 16.7}


def load_merge(parts, tag):
    cells = defaultdict(list); rv = []; fac = []; ns = None
    counts = []
    for prefix, logdir, Ks, rounds in parts:
        got = 0
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c)
                seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                Ns = P.per_step_N(l)
                n = min(len(steps), len(Ns))
                if ns is None or n > ns: ns = n
                for i in range(n):
                    x = steps[i]; t = i + 1
                    rf = int(x["reusedFrom"])
                    cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
                for x in rr:
                    if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                        rv.append(x["tPCSetup"]/x["tIter"])
                rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
                got += 1
        counts.append((prefix, got, len(Ks)*len(rounds)))
    bad = [(p, g, e) for p, g, e in counts if g == 0]
    if bad:
        print("      ★★ 空批次: %s" % ", ".join("%s(期望%d)" % (p, e) for p, _, e in bad))
    print("      载入: " + "  ".join("%s=%d/%d" % (p, g, e) for p, g, e in counts))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac) if fac else 1.0,
                nsteps=ns or 0)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 126)
print("★★★ A-终（七配置统一覆盖）：oracle / 最优 K* / 在线")
print("=" * 126)

rows = []
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    print("\n" + "#" * 126)
    print("#  [%s]" % tag)
    print("#" * 126)
    cfg = load_merge(MERGED[tag], tag)
    if cfg is None:
        print("  ★ 加载失败，跳过"); continue

    T = cfg["nsteps"]; r0 = cfg["r1"] * cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="linear")
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    print("  T=%d  每次分解 r=%.2f  每步分解 s=%.2f  r_eff=s·r=%.1f  amax_data=%d  候选K=%s"
          % (T, cfg["r1"], cfg["fac"], r0, env.amax_data, list(Ks)))
    re_ = R_EXP.get(tag)
    if re_:
        print("  （历史 r 参考值 %.2f，偏差 %+.1f%%）" % (re_, 100*(cfg["r1"]/re_ - 1)))

    try:
        orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
    except AssertionError as e:
        print("  ★★ 自检失败: %s" % e); continue

    kb = info["Kbest"]
    print("\n  %-8s %14s %12s %11s" % ("K", "总成本", "每步", "相对oracle"))
    for K in Ks:
        c = info["fixed"][K]
        print("  %-8s %14.0f %12.1f %10.2f%%%s"
              % (K, c, c/T, 100*(c/orc-1), "  ← 最优 K*" if K == kb else ""))
    print("  %-8s %14.0f %12.1f %10.2f%%  ← oracle(DP)" % ("oracle", orc, orc/T, 0.0))
    print("  %-8s %14.0f %12.1f %10.2f%%  ← 本文在线"
          % ("在线", info["online"], info["online"]/T, 100*(info["online"]/orc-1)))

    # regret 分解
    k1 = info["fixed"][1]; kk = info["fixed"][kb]; onl = info["online"]
    print("\n  ⇒ K=1 每步重建 regret   %6.2f%%   (%.1f 次/步)"
          % (100*(k1/orc-1), k1/T))
    print("  ⇒ 最优固定周期 K*=%d     regret %6.2f%%   (%.1f 次/步)" % (kb, 100*(kk/orc-1), kk/T))
    print("  ⇒ 本文在线               regret %6.2f%%   (%.1f 次/步)" % (100*(onl/orc-1), onl/T))
    print("  ⇒ 在线 − K*  =  %+.2f pp      在线相对 K=1 收益 = %.2f pp"
          % (100*(onl/orc-1) - 100*(kk/orc-1), 100*(k1/orc-1) - 100*(onl/orc-1)))
    rows.append((tag, r0, cfg["fac"], T, orc, kb, kk, k1, onl, info["AMAX"], env.amax_data))

print("\n" + "=" * 126)
print("★★★ 汇总表（覆盖到年龄 %s）" % ", ".join(str(r[10]) for r in rows))
print("=" * 126)
print("  %-6s %8s %6s %7s %10s %8s %10s %10s %10s %10s" %
      ("配置", "r_eff", "s", "T", "amax_data", "K*", "K=1", "K*", "在线", "在线−K*"))
for (tag, r0, fac, T, orc, kb, kk, k1, onl, AMAX, amx) in rows:
    print("  %-6s %8.1f %6.2f %7d %10d %8d %9.2f%% %9.2f%% %9.2f%% %+9.2f pp"
          % (tag, r0, fac, T, amx, kb,
             100*(k1/orc-1), 100*(kk/orc-1), 100*(onl/orc-1),
             100*(onl/orc-1) - 100*(kk/orc-1)))

if rows:
    onl_v = [100*(r[8]/r[4]-1) for r in rows]
    kk_v = [100*(r[6]/r[4]-1) for r in rows]
    gap = [a-b for a, b in zip(onl_v, kk_v)]
    print("\n  在线 regret   ：中位 %.2f%%  范围 [%.2f%%, %.2f%%]"
          % (st.median(onl_v), min(onl_v), max(onl_v)))
    print("  最优K* regret ：中位 %.2f%%  范围 [%.2f%%, %.2f%%]"
          % (st.median(kk_v), min(kk_v), max(kk_v)))
    print("  在线 − K*     ：中位 %+.2f pp  范围 [%+.2f, %+.2f] pp"
          % (st.median(gap), min(gap), max(gap)))
    print("  ★ 在线优于 K* 的配置数：%d / %d"
          % (sum(1 for g in gap if g < 0), len(gap)))
print("=" * 126)
