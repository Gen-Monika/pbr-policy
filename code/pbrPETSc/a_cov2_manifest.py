#!/usr/bin/env python3
"""
★★★ cov2 产出归档清单（2026-10-12 12:10 停止）

═══ 为什么需要这个文件 ═══
cov2 被中途停止，产出里【混有截断文件】（被脚本里的 timeout 3600 杀死）。
截断不会让数据报错，只会让某个年龄的中位数在一个更短的窗口上算，
造成【窗口不一致】。若不显式标记，后续脚本会静默把它们当完整数据用。

本脚本生成清单，并对每个文件给出可用性判定。
用法：python a_cov2_manifest.py            # 打印清单
      python a_cov2_manifest.py --which ok # 只打印可用(完整)的 CSV 路径
"""
import sys, os, json
import statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → (基准步数, BASE, [(csv_prefix, logdir, Ks, rounds), ...], levels)
SPEC = {
    "l15":  (344, 100, [("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])], 15),
    "fine": (720, 100, [("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])], 20),
    "x3":   (1231, 100, [("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])], 20),
    "fl30": (720, 100, [("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])], 30),
    "sth":  (5866, 50,  [("cov2_sth", "cov2_sth", [20,30], [1,2,3])], 5),
}


def check(csv, log, base_n, base, K, levels):
    if not os.path.exists(csv):
        return dict(status="missing", nstep=0)
    if not os.path.exists(log):
        return dict(status="no_log", nstep=0)
    try:
        rr = P.rows(csv)
        seen = {}
        for x in rr:
            if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                seen[int(x["timeIndex"])] = x
        nstep = len(seen)
        nrb = sum(1 for t in seen if int(seen[t]["reused"]) == 0)
        lv = int(rr[0]["levels"]) if rr else -1
        nl = len(P.per_step_N(log))
        # 末行字段数（残行检测）
        with open(csv, errors="ignore") as f:
            lines = [x for x in f.read().split("\n") if x.strip()]
        lastf = len(lines[-1].split(","))
        exp_rb = base + max(0, (nstep-base))/float(K)
        rb_ok = abs(nrb - exp_rb) <= max(3, 0.03*exp_rb)
        short = nstep < base_n
        status = "ok"
        notes = []
        if short: status = "truncated"; notes.append("%d/%d=%.0f%%" % (nstep, base_n, 100.0*nstep/base_n))
        if nstep != nl: notes.append("csv≠log(%d/%d)" % (nstep, nl))
        if lastf != 25: notes.append("残行 %d 字段" % lastf)
        if not rb_ok: notes.append("K不自洽")
        if lv != levels: notes.append("levels=%d≠%d" % (lv, levels))
        return dict(status=status, nstep=nstep, nlog=nl, base_n=base_n, nrb=nrb,
                    levels=lv, lastf=lastf, notes=notes, K=K)
    except Exception as e:
        return dict(status="error", nstep=0, notes=[str(e)[:40]])


def main():
    REC = {}
    print("=" * 122)
    print("★★★ cov2 产出归档清单")
    print("=" * 122)
    for tag, (base_n, base, parts, levels) in SPEC.items():
        print("\n  ── %s ──  基准 %d 步  BASE=%d  期望 levels=%d" % (tag, base_n, base, levels))
        print("     %-36s %9s %9s %6s %8s  %s"
              % ("文件", "CSV步", "log步", "levels", "重建", "判定"))
        REC[tag] = []
        for prefix, logdir, Ks, rounds in parts:
            for K in Ks:
                for R in rounds:
                    csv = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                    log = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                    if not os.path.exists(csv) and not os.path.exists(log):
                        continue
                    r = check(csv, log, base_n, base, K, levels)
                    r.update(K=K, R=R, csv=csv)
                    REC[tag].append(r)
                    mark = "完整" if r["status"] == "ok" else "★" + r["status"]
                    note = "  ".join(r.get("notes", []))
                    print("     %-36s %9s %9s %6s %8s  %s %s"
                          % (os.path.basename(csv), r["nstep"],
                             r.get("nlog", "—"),
                             r.get("levels", "—"), r.get("nrb", "—"), mark, note))

        ok = [r for r in REC[tag] if r["status"] == "ok"]
        tr = [r for r in REC[tag] if r["status"] == "truncated"]
        print("     ⇒ 完整 %d 个，截断 %d 个，共 %d 个"
              % (len(ok), len(tr), len(REC[tag])))

    # 汇总
    print("\n" + "=" * 122)
    print("★★★ 汇总")
    print("=" * 122)
    print("  %-6s %10s %10s %10s   %s" % ("配置", "完整", "截断", "缺失", "可用性"))
    for tag, rs in REC.items():
        ok = sum(1 for r in rs if r["status"] == "ok")
        tr = sum(1 for r in rs if r["status"] == "truncated")
        ms = sum(1 for r in rs if r["status"] in ("missing", "no_log", "error"))
        avail = "全可用" if (ok and not tr and not ms) else \
                ("部分可用（需剔除截断）" if ok else "不可用")
        print("  %-6s %10d %10d %10d   %s" % (tag, ok, tr, ms, avail))

    with open(os.path.join(P2, "cov2_manifest.json"), "w") as f:
        json.dump({k: [{kk: vv for kk, vv in r.items() if kk != "csv"} for r in v]
                   for k, v in REC.items()}, f, indent=1, ensure_ascii=False)
    print("\n  清单已写入 cov2_manifest.json")

    if len(sys.argv) > 2 and sys.argv[1] == "--which":
        want = sys.argv[2]
        for tag, rs in REC.items():
            for r in rs:
                if r["status"] == want:
                    print(r["csv"])
    print("=" * 122)


main()
