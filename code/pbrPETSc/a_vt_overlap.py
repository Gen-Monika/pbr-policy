import os, collections, statistics as st, sys, json
P2="/root/autodl-tmp/PBR"; sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import CFG, ORDER, phase_scan_anchor, _rows, _per_step_N
A,K=6,7
out={}
for tag in ORDER:
    lvl,T,B0=CFG[tag]; Bscan=phase_scan_anchor(tag)
    cells=collections.defaultdict(list)
    for B in range(Bscan-A,Bscan+1):
        c=os.path.join(P2,"phs_%s_B%d_K%d_r1.csv"%(tag,B,K))
        l=os.path.join(P2,"phs_%s"%tag,"log.B%dK%d_r1"%(B,K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        rr=_rows(c); seen={}
        for x in rr:
            if int(x["rep"])>=0 and int(x["timeIndex"]) not in seen: seen[int(x["timeIndex"])]=x
        steps=[seen[t] for t in sorted(seen)]; Ns=_per_step_N(l); n=min(len(steps),len(Ns))
        for i in range(n):
            x=steps[i]; rf=int(x["reusedFrom"])
            cells[(i+1, 0 if rf<0 else i+1-rf)].append(Ns[i])
    multi={k:v for k,v in cells.items() if len(v)>1}
    if not multi: 
        out[tag]={"n_multi":0}; print(tag,"no multi-source cells"); continue
    spreads=[max(v)-min(v) for v in multi.values()]
    cvs=[st.pstdev(v)/st.mean(v) for v in multi.values() if st.mean(v)>0]
    out[tag]={"n_multi":len(multi),
              "spread_mean":round(st.mean(spreads),3),
              "spread_max":round(max(spreads),3),
              "cv_mean":round(st.mean(cvs),5),
              "cv_max":round(max(cvs),5),
              "n_identical":sum(1 for s in spreads if s==0)}
    print("%-5s 重叠格=%-4d 跨运行极差 均值=%-7.3f 最大=%-7.1f  CV 均值=%.5f 完全一致格=%d"%(
        tag,len(multi),out[tag]["spread_mean"],out[tag]["spread_max"],
        out[tag]["cv_mean"],out[tag]["n_identical"]))
json.dump(out,open("/root/autodl-tmp/PBR_vt_20261031/overlap.json","w"),indent=1)
