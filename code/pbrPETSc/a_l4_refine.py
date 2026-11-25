import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, Env, CFG, sim_online_detail

CAL = {"fx": 57.9, "l15": 77.7, "l20": 90.6, "fine": 115.2,
       "x3": 113.2, "fl30": 147.4, "sth": 17.0}
TGT = {"fx": [221], "l15": [221], "l20": [221], "fine": [386, 387],
       "x3": [628, 629], "fl30": [305], "sth": [864, 867, 1016]}


def rb_at(env, r, T, B0):
    return sim_online_detail(env, r, T, B0)[2]


print("★ L4 精修：能复现实测重建次数的 ρ 区间（二分细化，步长 0.5）")
print("  %-6s %10s %-30s %10s %-8s" %
      ("配置", "实测rb", "可行 ρ 区间", "区间宽度", "标定值"))
rows = []
for tag in CAL:
    d = load_phase(tag); lvl, T, B0 = CFG[tag]
    env = Env(d["tab"], sFact=d["s"])
    tg = set(TGT[tag])
    ok = []
    x = 5.0
    while x <= 400.0:
        if rb_at(env, x, T, B0) in tg: ok.append(x)
        x += 0.5
    if ok:
        wid = max(ok) - min(ok)
        # 找出所有连续段
        segs = []; s0 = ok[0]; prev = ok[0]
        for v in ok[1:]:
            if v - prev > 0.6:
                segs.append((s0, prev)); s0 = v
            prev = v
        segs.append((s0, prev))
        ss = " / ".join("%.1f–%.1f" % s for s in segs)
        print("  %-6s %10s %-30s %9.1f  %8.1f" % (tag, TGT[tag], ss, wid, CAL[tag]))
        rows.append((tag, wid, segs, CAL[tag]))
    else:
        print("  %-6s %10s %-30s %9s  %8.1f" % (tag, TGT[tag], "无", "—", CAL[tag]))
        rows.append((tag, 0.0, [], CAL[tag]))

print()
print("★ 判读：可行 ρ 区间的宽度 = 模型能复现实测行为的容错幅度")
print("  宽度大  ⇒ 结论稳健，ρ 的标定误差不影响策略")
print("  宽度小  ⇒ 策略对 ρ 敏感，该配置的结果不宜强主张")
for tag, wid, segs, cal in sorted(rows, key=lambda x: -x[1]):
    lvl = "宽（稳健）" if wid >= 20 else ("中等" if wid >= 5 else "★ 极窄（敏感）")
    print("   %-6s 宽度=%6.1f   %s" % (tag, wid, lvl))
