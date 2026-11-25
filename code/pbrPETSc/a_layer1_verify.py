#!/usr/bin/env python3
"""
★★★ a_layer1_verify.py —— 第一层（C++ 在线验证 7/7）的汇总审计

★ 设计要点：本脚本对每个配置同时检查四件事，任何一项不过就不许把该配置
  写成"已验证"：

  L1  跨轮确定性      —— iters/rbsteps 在各轮之间是否逐位相同？
                         （不是全局性质！sth/fine/x3 都有轮间差异，见陷阱 61）
  L2  决策序列比对    —— 模型的动作序列 vs 实测，并区分两种偏离：
                         (a) 一次性阈值穿越 ⇒ 之后整体相位偏移（fine 型）
                         (b) 零散反复翻转   ⇒ 判据在刀刃上（sth 型）
  L3  沿实测路径定价  —— 决策固定、只换 N 表，看模型的相对差
  L4  oracle 不等式   —— 用【该配置自己的实测重建次数】反查 ρ 是否与标定值相容

用法：python a_layer1_verify.py
"""
import sys, os, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (ORDER, CFG, load_phase, Env, sim_online_detail,
                     _rows, _per_step_N, P2)

CAL = {"fx": 57.9, "l15": 77.7, "l20": 90.6, "fine": 115.2,
       "x3": 113.2, "fl30": 147.4, "sth": 17.0}

# 实测运行：tag -> (前缀, 步数的 mode 名)
RUNS = {
    "fx":   ("a2fx",   "ONLs"),
    "l15":  ("a2l15",  "ONLs"),
    "l20":  ("a2A",    "ONLs"),
    "fine": ("a2fine", "ONLs"),
    "x3":   ("a2x3",   "ONLs"),
    "fl30": ("a2B",    "ONLs"),
    "sth":  ("a2sth",  "ONLs"),
}


def load_rounds(pre, mode, maxr=5):
    out = []
    for r in range(1, maxr + 1):
        pc = "%s/%s_pc_%s_r%d.csv" % (P2, pre, mode, r)
        lg = "%s/%s_case/log.%s.r%d" % (P2, pre, mode, r)
        if not (os.path.exists(pc) and os.path.exists(lg)): continue
        rr = _rows(pc); seen = {}
        for x in rr:
            if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                seen[int(x["timeIndex"])] = x
        steps = [seen[t] for t in sorted(seen)]
        Ns = _per_step_N(lg); n = min(len(steps), len(Ns))
        act = [int(steps[i]["reusedFrom"]) < 0 for i in range(n)]
        held = -1; ages = []
        for i in range(n):
            if act[i]: ages.append(0); held = i + 1
            else: ages.append(i + 1 - held)
        out.append(dict(r=r, n=n, it=sum(Ns[:n]),
                        rb=sum(1 for a in act if a), act=act, ages=ages))
    return out


def runs_of(seq):
    """把一组位置压成连续区间段。"""
    if not seq: return []
    out = []; s0 = seq[0]; prev = seq[0]
    for x in seq[1:]:
        if x != prev + 1:
            out.append((s0, prev)); s0 = x
        prev = x
    out.append((s0, prev))
    return out


def main():
    print("=" * 124)
    print("★★★ 第一层汇总：C++ 在线验证 7/7（ONLs 模式）")
    print("=" * 124)
    print()
    print("  %-6s %8s %6s %-26s %-10s %10s" %
          ("配置", "ρ标定", "轮数", "各轮 (iters, rbsteps)", "跨轮一致", "maxage"))
    summary = {}
    for tag in ORDER:
        pre, mode = RUNS[tag]
        rounds = load_rounds(pre, mode)
        if not rounds:
            print("  %-6s %8.1f %6s %-26s %-10s %10s" %
                  (tag, CAL[tag], "0", "（无实测）", "—", "—"))
            summary[tag] = None
            continue
        its = [x["it"] for x in rounds]
        rbs = [x["rb"] for x in rounds]
        det = (len(set(its)) == 1 and len(set(rbs)) == 1)
        disp = " / ".join("(%d,%d)" % (a, b) for a, b in zip(its, rbs))
        mx = max(max(x["ages"]) for x in rounds)
        print("  %-6s %8.1f %6d %-26s %-10s %10d" %
              (tag, CAL[tag], len(rounds), disp,
               "✓ 逐位相同" if det else "★ 有差异", mx))
        summary[tag] = dict(rounds=rounds, det=det, its=its, rbs=rbs)

    # ── L2 决策序列
    print()
    print("─" * 124)
    print("★ L2：模型的动作序列 vs 实测（用第 1 轮；并区分偏离类型）")
    print("─" * 124)
    print("  %-6s %10s %10s %12s %-34s %s" %
          ("配置", "模型重建", "实测重建", "决策一致率", "偏离结构", "类型"))
    for tag in ORDER:
        s = summary.get(tag)
        if not s: continue
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"]); rho = CAL[tag]
        c, it, rb, pred, mv = sim_online_detail(env, rho, T, B0)
        r0 = s["rounds"][0]
        n = min(r0["n"], T)
        act = r0["act"][:n]
        dif = [i + 1 for i in range(n) if pred[i] != act[i]]
        agr = 100.0 * (n - len(dif)) / n
        segs = runs_of(dif)
        if not dif:
            kind = "完全复现"
        elif len(segs) <= 3:
            kind = "一次性穿越（相位偏移）"
        else:
            kind = "★ 刀刃反复翻转"
        print("  %-6s %10d %10d %11.2f%% %-34s %s" %
              (tag, rb, r0["rb"], agr,
               "%d 步 / %d 段%s" % (len(dif), len(segs),
                                    ("，首段 %s" % (segs[0],)) if segs else ""),
               kind))

    # ── L3 沿实测路径定价
    print()
    print("─" * 124)
    print("★ L3：沿【实测动作序列】定价（决策固定，只换 N 表）")
    print("─" * 124)
    print("  %-6s %s" % ("配置", "各轮相对差%"))
    for tag in ORDER:
        s = summary.get(tag)
        if not s: continue
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        rels = []
        for r0 in s["rounds"]:
            n = r0["n"]; tot = 0.0; held = -1
            for i in range(n):
                if r0["act"][i]: tot += env(i + 1, 0); held = i + 1
                else: tot += env(i + 1, i + 1 - held)
            rels.append(100.0 * (tot - r0["it"]) / r0["it"])
        print("  %-6s %s   （|最大| = %.3f%%）" %
              (tag, "  ".join("%+.3f" % x for x in rels),
               max(abs(x) for x in rels)))

    # ── L4 ρ 相容性：实测重建次数落在哪个 ρ 上
    print()
    print("─" * 124)
    print("★ L4：用实测重建次数反查 ρ（该配置自己的实测行为隐含的 ρ）")
    print("─" * 124)
    print("  %-6s %10s %-28s %s" % ("配置", "实测重建", "能复现该次数的 ρ 区间", "标定值落在其中？"))
    grid = list(range(5, 400, 5))
    for tag in ORDER:
        s = summary.get(tag)
        if not s: continue
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        target = st.median(s["rbs"])
        ok = []
        for r in grid:
            c, it, rb, pred, mv = sim_online_detail(env, r, T, B0)
            if rb == target: ok.append(r)
        if not ok:
            print("  %-6s %10d %-28s —" % (tag, target, "（网格内无解）"))
            continue
        seg = "%d–%d" % (min(ok), max(ok))
        cal = CAL[tag]
        inside = (min(ok) <= cal <= max(ok))
        print("  %-6s %10d %-28s %s" % (tag, target, seg,
                                        "✓ 是" if inside else "★ 否（标定值 %.1f）" % cal))
    print()
    print("=" * 124)


main()
