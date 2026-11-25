"""Check the phase passed to policy against each solver's printed iteration."""
from pathlib import Path
import csv,json,re
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
results={}
for p in sorted((R/'full').glob('*/r*_index')):
    if not (p/'result.json').exists():continue
    s=re.sub(r'\x1b\[[0-9;]*m','',(p/'run.log').read_text())
    rows=[]
    if p.parent.name=='MOOSE':
        j=0;row=None
        for l in s.splitlines():
            m=re.match(r'\s*(\d+) Nonlinear \|R\|',l)
            if m:j=int(m[1])
            m=re.match(r'PBR solve (\d+) rebuild (\d+)',l)
            if m:row={'j':j,'N':0};rows.append(row)
            m=re.match(r'\s*(\d+) Linear \|R\|',l)
            if m and row is not None:row['N']=int(m[1])
    else:
        for block in re.split(r'\*\*\* Timestep \d+:\s+t=[\d.eE+-]+ seconds',s)[1:]:
            counts=[sum(map(int,v)) for v in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',block)]
            js=[int(x)-1 for x in re.findall(r'after nonlinear iteration (\d+):',block)]
            if js:assert len(counts)==len(js),(str(p),len(counts),len(js))
            else:js=[0]*len(counts)
            rows.extend({'j':j,'N':n} for j,n in zip(js,counts))
    trace=list(csv.DictReader((p/'trace.csv').open()))
    mismatch=[]
    for r in trace:
        observed=rows[int(r['step'])]
        if observed!={'j':int(r['phase']),'N':int(r['its'])}:
            mismatch.append({'step':r['step'],'log':observed,'trace':{'j':r['phase'],'N':r['its']}})
    results[str(p.relative_to(R))]={'recorded_rows':len(trace),'solver_solves':len(rows),'mismatches':mismatch}
    assert not mismatch,(str(p),mismatch[:3])
(R/'phase_join_audit.json').write_text(json.dumps(results,indent=2))
print('PASS phase/iteration joins',len(results),'runs,',sum(v['recorded_rows'] for v in results.values()),'recorded rows')
