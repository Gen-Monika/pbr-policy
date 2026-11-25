import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, Env, CFG, sim_online_detail

CAL = {"fx": 57.9, "l15": 77.7, "l20": 90.6, "fine": 115.2,
       "x3": 113.2, "fl30": 147.4, "sth": 17.0}
TARGET = {"fine": [387, 386], "x3": [629, 628], "sth": [867, 864, 1016]}

print("L4 细查：模型重建次数 rb(rho) 的取值谱")
print("（粗网格可能【跳过】目标值，看起来像无解，实际只是分辨率不够）")
for tag in ("fine", "x3", "sth"):
    d = load_phase(tag); lvl, T, B0 = CFG[tag]
    env = Env(d["tab"], sFact=d["s"])
    print()
    print("【%s】目标实测重建次数 = %s   标定 rho = %.1f" % (tag, TARGET[tag], CAL[tag]))
    grid = [5, 10, 15, 17, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 115,
            120, 130, 140, 150, 170, 200, 250, 300, 400, 600]
    vals = []
    for r in grid:
        c, it, rb, pred, mv = sim_online_detail(env, r, T, B0)
        vals.append((r, rb))
    print("   rho->rb :", " ".join("%d:%d" % (r, rb) for r, rb in vals))
    ts = set(TARGET[tag])
    hit = [r for r, rb in vals if rb in ts]
    print("   命中目标值的 rho: %s" % (hit if hit else "无（rb 在该网格上跳过了目标值）"))
    jumps = [(vals[i][0], vals[i][1], vals[i + 1][0], vals[i + 1][1])
             for i in range(len(vals) - 1) if abs(vals[i + 1][1] - vals[i][1]) > 3]
    print("   相邻网格点上 rb 跃变>3 的处数: %d" % len(jumps))
    if jumps:
        print("     例: rho %d->%d 时 rb %d->%d" % jumps[0])
