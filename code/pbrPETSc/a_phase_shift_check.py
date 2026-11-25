import sys, os, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, Env, CFG, sim_online_detail, _rows, _per_step_N

print("相位漂移检验：模型的重建步集合 与 实测的重建步集合 是否只差一个平移？")
print()
for tag, pre in (("fine", "a2fine"), ("fx", "a2fx"), ("sth", "a2sth")):
    d = load_phase(tag); lvl, T, B0 = CFG[tag]
    env = Env(d["tab"], sFact=d["s"]); rho = d["r1"]
    lg = "/root/autodl-tmp/PBR/%s_case/log.ONLs.r1" % pre
    pc = "/root/autodl-tmp/PBR/%s_pc_ONLs_r1.csv" % pre
    if not (os.path.exists(lg) and os.path.exists(pc)):
        print("%s: 缺文件" % tag); continue
    rr = _rows(pc); seen = {}
    for x in rr:
        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
            seen[int(x["timeIndex"])] = x
    steps = [seen[t] for t in sorted(seen)]
    Ns = _per_step_N(lg); n = min(len(steps), len(Ns))
    act = [int(steps[i]["reusedFrom"]) < 0 for i in range(n)]
    c, it, rb, pred, mv = sim_online_detail(env, rho, T, B0)
    M = [i + 1 for i in range(n) if pred[i]]
    A = [i + 1 for i in range(n) if act[i]]
    sm, sa = set(M), set(A)
    print("【%s】 rho=%.1f  模型重建 %d 次, 实测 %d 次" % (tag, rho, len(M), len(A)))
    print("    集合差 |模型\\实测|=%d  |实测\\模型|=%d" % (len(sm - sa), len(sa - sm)))
    k = min(len(M), len(A), 60)
    ds = [A[i] - M[i] for i in range(k)]
    print("    前%d个重建步的位置差(实测-模型): 中位=%.1f  范围=[%d,%d]  唯一值=%s"
          % (k, st.median(ds), min(ds), max(ds), sorted(set(ds))[:6]))
    # 逐步"是否需要重建"的分歧是否连续成段？
    dif = [i + 1 for i in range(n) if pred[i] != act[i]]
    runs = []
    if dif:
        s0 = dif[0]; prev = dif[0]
        for x in dif[1:]:
            if x != prev + 1:
                runs.append((s0, prev)); s0 = x
            prev = x
        runs.append((s0, prev))
    print("    分歧 %d 步，分成 %d 段，前3段=%s" % (len(dif), len(runs), runs[:3]))
    print()
