#!/usr/bin/env python3
"""
查「不重建 ⇒ 失效/不收敛」这个断言是否有实测支撑。

三路检索：
  S1  日志里有没有收敛失败的痕迹？（maxIter 打满、警告、p_rghFinal 兜底）
  S2  实测中出现过的【最大年龄】是多少？（不重建的直接含义是年龄无界）
  S3  最大年龄处的 N 相对基线涨了多少？
"""
import re, os, glob, statistics as st

P = "/root/autodl-tmp/PBR"
TRE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
NRE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
WARN = re.compile(r"(not converged|convergence|maxIter|Maximum number|"
                  r"bounding|FATAL|singular|diverg)", re.I)

CODES = {"fx":"fixed","l15":"l15","l20":"l20","fine":"finerun","x3":"x3run",
         "fl30":"fl30run","sth":"stefan"}

print("=" * 116)
print("S1 收敛失败痕迹检索（扫描全部 log，含相位扫描与 K 扫描）")
print("=" * 116)
hits = {}
files = []
for pat in ("%s/*/log.*" % P, "%s/*.log" % P):
    files += glob.glob(pat)
files = sorted(set(files))
print("  扫描 %d 个 log 文件" % len(files))
for f in files:
    try:
        txt = open(f, errors="ignore").read()
    except Exception:
        continue
    for m in WARN.finditer(txt):
        w = m.group(1).lower()
        hits.setdefault(w, []).append(os.path.basename(f))
if not hits:
    print("  ⇒ 未发现任何收敛失败痕迹")
else:
    for w, fs in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print("  %-16s 出现于 %3d 个文件，例: %s" % (w, len(fs), fs[:3]))

print()
print("=" * 116)
print("S2/S3 实测出现过的最大年龄与 N 的涨幅")
print("=" * 116)
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TRE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = NRE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out

print("  %-6s %-28s %-9s %-9s %-9s %s" % ("配置","文件","最大年龄","N@0","N@max","涨幅"))
for tag, d in CODES.items():
    best = None
    for f in glob.glob("%s/%s_pc_k*.csv" % (P, tag)) + glob.glob("%s/phs_%s_*.csv" % (P, tag)):
        try:
            rr = []
            for ln in open(f, errors="ignore"):
                q = ln.rstrip("\n").split(",")
                if len(q) != 25: continue
                x = dict(zip(CSV_HDR, q))
                try:
                    for k in x:
                        if k not in ("field","kind"): x[k] = float(x[k])
                except ValueError: continue
                rr.append(x)
        except Exception:
            continue
        if not rr: continue
        seen = {}
        for x in rr:
            t = int(x["timeIndex"])
            if t not in seen: seen[t] = x
        ts = sorted(seen)
        ages = [t - int(seen[t]["reusedFrom"]) if int(seen[t]["reusedFrom"]) >= 0 else 0 for t in ts]
        if not ages: continue
        amax = max(ages)
        if best is None or amax > best[0]:
            best = (amax, os.path.basename(f), ts, ages, seen)
    if not best: continue
    amax, fn, ts, ages, seen = best
    # N(age=0) 与 N(age=amax) 的实测
    n0 = [per_step_N("%s/%s/%s" % (P, "", "")) ] if False else None
    print("  %-6s %-28s %-9d" % (tag, fn, amax), end="")
    print("  (需结合 log 求 N；下表单独给)")
