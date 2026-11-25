import re,os,json,glob
BASE="/root/autodl-tmp/PBR/elmer_cases"
rows=[]
for d in sorted(glob.glob(os.path.join(BASE,"run_fssa_*"))):
    log=os.path.join(d,"run.log")
    if not os.path.exists(log): continue
    t=open(log,errors="ignore").read()
    nc=t.count("did not converge")
    iters=[int(x) for x in re.findall(r"after (\d+) iters",t)]
    res=re.findall(r"True residual norm::\s*([0-9.E+-]+)",t)
    wall=re.search(r"SOLVER TOTAL TIME\(CPU,REAL\):\s*([\d.]+)\s*([\d.]+)",t)
    done="ALL DONE" in t
    passed="PASSED all" in t
    # 触顶发生在第几次 solve
    first_nc_solve=None
    if nc:
        idx=t.find("did not converge")
        pre=t[:idx]
        gcr=len(re.findall(r"IterMethod_GCR: Iterated residual",pre))
        first_nc_solve=gcr+1
    rows.append(dict(run=os.path.basename(d), nonconv=nc, max_iter=max(iters) if iters else None,
                     nsolve=len(res), final_res=res[-1] if res else None,
                     wall=float(wall.group(2)) if wall else None,
                     completed=done, ref_passed=passed, first_nc_at_solve=first_nc_solve))
for r in rows:
    print("%-18s 未收敛 %3d  最大迭代 %4s  求解数 %3s  末残差 %-10s 墙钟 %6s 完成%s 参考%s"%(
        r["run"],r["nonconv"],r["max_iter"],r["nsolve"],r["final_res"],r["wall"],
        r["completed"],r["ref_passed"]))
json.dump(rows,open("/root/autodl-tmp/PBR_vt_20261031/elmer_safety.json","w"),ensure_ascii=False,indent=1)
