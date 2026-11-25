#!/usr/bin/env python3
"""
★ 修正日志解析：每个时间步有 1 行 PETSc 报告 + 3 次 p_rgh 求解。

═══════════════════════════════════════════════════════════════════════
此前的方法错误（重要）
═══════════════════════════════════════════════════════════════════════
load_N() 抓取所有 "Solving for p_rgh" 行 ⇒ 得到 1032 条 (= 3 × 344)，
而 CSV 只有 344 行 (= 1 行/步)。
旧代码用 min(344, 1032) 截断 ⇒ 把【前 115 步】的迭代数当成全部 344 步，
使所有涉及 N 的结论（年龄曲线、在线策略、oracle）失去依据。

═══════════════════════════════════════════════════════════════════════
正确结构（由日志逐行核对确认）
═══════════════════════════════════════════════════════════════════════
    Time = <t>
    PIMPLE: iteration 1
    smoothSolver:  Solving for alpha.water ...
    PETSc ilu lvl=2 rebuild|REUSE@b : t_freeze=.. t_convert=.. t_pcsetup=.. r=..
    PETScILUPCG:  Solving for p_rgh ... No Iterations 32     ← 第 1 次（p_rgh）
    PETScILUPCG:  Solving for p_rgh ... No Iterations 6      ← 第 2 次（p_rghFinal?）
    PETScILUPCG:  Solving for p_rgh ... No Iterations 0      ← 第 3 次
    smoothSolver:  Solving for epsilon ...
    smoothSolver:  Solving for k ...
    Time = <t'>    ← 下一步

⇒ CSV 的一行对应一步；其 t_pcsetup 与【第 1 次】p_rgh 求解同段，
  故 N 的主要口径应取第 1 次。

本脚本提供三种口径：
  first : 只取每步第 1 次求解（与 CSV 的计时同段）
  sum   : 取每步 3 次之和（该步压力求解的总迭代代价）
  all   : 保留全部 1032 条（仅用于对照，不与 CSV 配对）
"""
import os
import re
import statistics as st
from collections import defaultdict

PETSC_RE = re.compile(r"PETSc ilu lvl=\d+\"?\s*(rebuild|\"REUSE@(\d+)\")")
SOLVE_RE = re.compile(r"(PETScILUPCG|DICPCG|GAMG|PCG):\s+Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")


def parse_log(path):
    """返回每步记录： [{t, reused, b, solves:[N1,N2,N3]}]"""
    steps = []
    cur = None
    for ln in open(path, errors="ignore"):
        m = TIME_RE.match(ln)
        if m:
            if cur is not None:
                steps.append(cur)
            cur = dict(t=float(m.group(1)), reused=None, b=None, solves=[])
            continue
        if cur is None:
            continue
        if "PETSc ilu lvl" in ln:
            if "REUSE@" in ln:
                cur["reused"] = 1
                mm = re.search(r"REUSE@(\d+)", ln)
                cur["b"] = int(mm.group(1)) if mm else None
            else:
                cur["reused"] = 0
                cur["b"] = None
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur["solves"].append(int(ms.group(2)))
    if cur is not None:
        steps.append(cur)
    # 补 b：对 reused 步骤，b 由 PETSc 行给出；对 rebuild 步，b = 自身序号
    for i, s in enumerate(steps, start=1):
        if s["reused"] == 0:
            s["b"] = i
    return steps


def load_csv(path):
    HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        cols = HDR if len(p) == 20 else (HDR[:11] + HDR[12:] if len(p) == 19 else None)
        if cols is None:
            continue
        d = {}
        try:
            for k, v in zip(cols, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def check(K, rep=1):
    steps = parse_log(f"s{K}/log.s{rep}")
    rows = load_csv(f"s_k{K}_r{rep}.csv")
    print(f"\n{'='*92}")
    print(f"K={K} rep={rep}: 日志 {len(steps)} 步 / CSV {len(rows)} 行")
    print(f"{'='*92}")

    nsolves = [len(s["solves"]) for s in steps]
    print(f"  每步求解次数分布: {dict(sorted({n: nsolves.count(n) for n in set(nsolves)}.items()))}")

    if len(steps) != len(rows):
        print(f"  ⚠️ 步数不匹配！")
        return None

    # 校验 reused 标志与 CSV 一致
    mism = 0
    for s, r in zip(steps, rows):
        if s["reused"] is not None and int(r["reused"]) != s["reused"]:
            mism += 1
    print(f"  reused 标志与 CSV 不一致的行: {mism}")

    # 口径
    first = [s["solves"][0] if s["solves"] else 0 for s in steps]
    total = [sum(s["solves"]) for s in steps]
    print(f"  first 口径: ΣN={sum(first)}  均值={st.mean(first):.2f}  "
          f"范围 [{min(first)}, {max(first)}]")
    print(f"  sum   口径: ΣN={sum(total)}  均值={st.mean(total):.2f}  "
          f"范围 [{min(total)}, {max(total)}]")

    # 抽查前 3 步与冻结点附近
    print(f"\n  {'步':>4} {'reused':>7} {'b':>6} {'solves':>22} {'first':>6} {'sum':>6}")
    for i in list(range(3)) + [len(steps) - 2, len(steps) - 1]:
        s = steps[i]
        print(f"  {i+1:>4} {str(s['reused']):>7} {str(s['b']):>6} "
              f"{str(s['solves']):>22} {first[i]:>6} {total[i]:>6}")

    # 冻结点
    firstreuse = next((i for i, s in enumerate(steps) if s["reused"] == 1), None)
    if firstreuse is not None:
        print(f"\n  首次复用出现在第 {firstreuse+1} 步（b={steps[firstreuse]['b']}）")
        print(f"  {'步':>4} {'reused':>7} {'b':>6} {'solves':>22} {'first':>6} {'sum':>6}")
        for i in range(max(0, firstreuse - 2), min(len(steps), firstreuse + 4)):
            s = steps[i]
            print(f"  {i+1:>4} {str(s['reused']):>7} {str(s['b']):>6} "
                  f"{str(s['solves']):>22} {first[i]:>6} {total[i]:>6}")
    return steps, rows, first, total


print("=" * 92)
print("★ 日志解析修正验证")
print("=" * 92)
allok = True
for K in (1, 2, 3, 5, 8):
    r = check(K, 1)
    if r is None:
        allok = False

print(f"\n{'='*92}")
print("★ 各 K 的 first 口径 ΣN 对比（这才是 344 步的真实总和）")
print(f"{'='*92}")
print(f"  {'K':>3} {'ΣN(first)':>11} {'均值':>8} {'ΣN(sum)':>11} {'重建数':>7}")
res = {}
for K in (1, 2, 3, 4, 5, 6, 8):
    if not os.path.exists(f"s_k{K}_r1.csv"):
        continue
    steps = parse_log(f"s{K}/log.s1")
    first = [s["solves"][0] if s["solves"] else 0 for s in steps]
    total = [sum(s["solves"]) for s in steps]
    nreb = sum(1 for s in steps if s["reused"] == 0)
    res[K] = (sum(first), sum(total), nreb)
    print(f"  {K:>3} {sum(first):>11} {st.mean(first):>8.2f} {sum(total):>11} {nreb:>7}")

if 1 in res:
    print(f"\n  相对 K=1 的 ΣN(first) 变化：")
    for K in sorted(res):
        print(f"    K={K}: {(res[K][0]/res[1][0]-1)*100:+7.2f}%")
