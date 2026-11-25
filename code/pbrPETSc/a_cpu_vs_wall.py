#!/usr/bin/env python3
"""
★★★ CPU 时间 vs 墙钟：噪声对比验证

═══ 目的 ═══
判定「CPU 时间」能否替代墙钟作为主指标。三个待答问题：
  Q1  CPU 时间的离散度是否显著小于墙钟？
  Q2  墙钟的波动在多大程度上由【负载】解释？（r 之前算得 0.476）
  Q3  CPU 时间是否与负载无关？（若无关，说明它过滤掉了外部争抢）

═══ 方法（零风险：不改 C++）═══
用 Python 的 resource.getrusage(RUSAGE_CHILDREN) 包裹子进程，
拿到该子进程消耗的 user + sys CPU 时间。
  · 优点：不需要重编译那个已经验证过的 .so
  · 同时用 time.monotonic() 拿墙钟，两者在同一进程内一起测

═══ 关键设计 ═══
1. 同轮内交错（消除共性漂移）
2. 每轮记录 loadavg（前/后各一次，取均值）
3. taskset 固定到某个核（可选，消除迁移抖动）—— 分两组对照
4. 只跑 l20（单次 ~19s，噪声最大 17.5%），轮数 8

用法：python a_cpu_vs_wall.py            # 不绑核
      python a_cpu_vs_wall.py --taskset  # 绑核
"""
import sys, os, time, json, resource, statistics as st, subprocess
from collections import defaultdict

P = "/root/autodl-tmp/PBR"
SRC = P + "/damBreak_petsc"
TAG = "cpuw"
MODE = "K3"          # 单 mode，最大化轮数
NROUND = int(os.environ.get("NROUND", "8"))
USE_TASKSET = "--taskset" in sys.argv
CORE = os.environ.get("CORE", "64")


def loadavg():
    try:
        return float(open("/proc/loadavg").read().split()[0])
    except Exception:
        return float("nan")


def run_once(workdir, mode, rnd):
    """在 workdir 里跑一次 interFoam，返回 (wall_s, cpu_s, load_before, load_after)"""
    env = dict(os.environ)
    # 清掉可能残留的 PBR 变量（脚本里会重设）
    for k in ("PBR_PETSC_ONLINE", "PBR_PETSC_ONLINE_RCOST", "PBR_PETSC_ONLINE_LVL",
              "PBR_PETSC_ONLINE_OUT", "PBR_PETSC_ONLINE_DMODE", "PBR_PETSC_ONLINE_DMINN",
              "PBR_PETSC_FREEZE_K", "PBR_PETSC_FREEZE_AT", "PBR_PETSC_FREEZE_BASE"):
        env.pop(k, None)
    env["PBR_PETSC_KIND"] = "ilu"
    env["PBR_PETSC_LEVELS"] = "20"
    env["PBR_PETSC_BENCH"] = "1"
    env["PBR_PETSC_REPS"] = "8"
    env["OMP_NUM_THREADS"] = "1"
    env["PBR_PETSC_FREEZE_AT"] = "1"
    env["PBR_PETSC_FREEZE_BASE"] = "100"
    env["PBR_PETSC_FREEZE_K"] = "3"
    env["PBR_PETSC_STORE"] = P + "/" + TAG + "_store"
    env["PBR_PETSC_OUT"] = "%s/%s_pc_%s_r%d.csv" % (P, TAG, mode, rnd)
    env["PBR_SOLVER_OUT"] = "%s/%s_sv_%s_r%d.csv" % (P, TAG, mode, rnd)

    cmd = ["interFoam"]
    if USE_TASKSET:
        cmd = ["taskset", "-c", CORE] + cmd

    lb = loadavg()
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.monotonic()
    with open(os.path.join(workdir, "log.%s.r%d" % (mode, rnd)), "w") as lf:
        subprocess.run(cmd, cwd=workdir, env=env, stdout=lf, stderr=subprocess.STDOUT)
    t1 = time.monotonic()
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    la = loadavg()

    cpu = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
    return dict(wall=t1 - t0, cpu=cpu, user=r1.ru_utime - r0.ru_utime,
                sys=r1.ru_stime - r0.ru_stime, lb=lb, la=la,
                lbm=(lb + la)/2.0)


def main():
    wd = os.path.join(P, TAG + "_case")
    if not os.path.isdir(wd):
        print("★ 工作目录不存在: %s" % wd)
        print("   请先用 a2_run_v2.sh 准备，或由本脚本自动复制")
        return
    os.makedirs(os.path.join(P, TAG + "_store"), exist_ok=True)

    print("=" * 116)
    print("★★★ CPU 时间 vs 墙钟   mode=%s  轮数=%d  taskset=%s  核=%s"
          % (MODE, NROUND, USE_TASKSET, CORE if USE_TASKSET else "—"))
    print("=" * 116)
    print("  %-5s %10s %10s %10s %8s %10s %10s"
          % ("轮", "墙钟(s)", "CPU(s)", "CPU/墙钟", "线程数", "负载(前)", "负载(后)"))
    recs = []
    for R in range(1, NROUND + 1):
        d = run_once(wd, MODE, R)
        recs.append(d)
        print("  %-5d %10.3f %10.3f %10.3f %8s %10.2f %10.2f"
              % (R, d["wall"], d["cpu"], d["cpu"]/d["wall"],
                 "%.3f" % (d["cpu"]/d["wall"]), d["lb"], d["la"]))

    w = [d["wall"] for d in recs]
    c = [d["cpu"] for d in recs]
    ld = [d["lbm"] for d in recs]

    def report(nm, v):
        md = st.median(v)
        return dict(med=md, mn=min(v), mx=max(v),
                    rng=100.0*(max(v) - min(v))/md if md else float("nan"),
                    sd=st.pstdev(v) if len(v) > 1 else 0.0,
                    rsd=100.0*st.pstdev(v)/md if len(v) > 1 and md else float("nan"))

    rw, rc = report("wall", w), report("cpu", c)
    print()
    print("  %-8s %12s %12s %12s %10s %10s"
          % ("指标", "中位", "最小", "最大", "极差%", "相对SD%"))
    print("  %-8s %12.3f %12.3f %12.3f %9.1f%% %9.2f%%"
          % ("墙钟(s)", rw["med"], rw["mn"], rw["mx"], rw["rng"], rw["rsd"]))
    print("  %-8s %12.3f %12.3f %12.3f %9.1f%% %9.2f%%"
          % ("CPU(s)", rc["med"], rc["mn"], rc["mx"], rc["rng"], rc["rsd"]))
    print()
    print("  ⇒ 噪声降低倍数（极差）: %.2fx" % (rw["rng"]/rc["rng"] if rc["rng"] else float("nan")))
    print("  ⇒ 噪声降低倍数（相对SD）: %.2fx" % (rw["rsd"]/rc["rsd"] if rc["rsd"] else float("nan")))

    # 与负载的相关性
    def corr(x, y):
        mx, my = st.median(x), st.median(y)
        num = sum((a-mx)*(b-my) for a, b in zip(x, y))
        dx = sum((a-mx)**2 for a in x)**0.5
        dy = sum((b-my)**2 for b in y)**0.5
        return num/(dx*dy) if dx*dy > 0 else float("nan")

    print()
    print("  %-8s %16s %16s" % ("指标", "r(值, 负载)", "与负载的斜率"))
    for nm, v in (("墙钟", w), ("CPU", c)):
        if len(set(ld)) > 1:
            mx, my = st.median(ld), st.median(v)
            num = sum((a-mx)*(b-my) for a, b in zip(ld, v))
            den = sum((a-mx)**2 for a in ld)
            sl = num/den if den else float("nan")
            print("  %-8s %16.3f %16.4f s/负载单位" % (nm, corr(ld, v), sl))
        else:
            print("  %-8s 负载无变化，无法算相关" % nm)

    out = dict(wall=w, cpu=c, load=ld, taskset=USE_TASKSET)
    with open(os.path.join(P, "cpu_vs_wall%s.json" % ("_ts" if USE_TASKSET else "")), "w") as f:
        json.dump(out, f, indent=1)
    print()
    print("  已写出 cpu_vs_wall%s.json" % ("_ts" if USE_TASKSET else ""))
    print("=" * 116)


main()
