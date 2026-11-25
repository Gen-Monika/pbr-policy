"""Descriptive check of frozen offsets against all-rebuild archived controls."""
from pathlib import Path
import json,re
P=Path('/root/autodl-tmp/PBR/aspect_runs/tosi')
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
med=lambda v:sorted(v)[len(v)//2]
result={}
for case in ['C1','C3','C4','C5']:
    p=P/f'{case}_OFF';s=(p/'run.log').read_text()
    parts=re.split(r'(\*\*\* Timestep \d+:\s+t=[\d.eE+-]+ seconds)',s)
    rows=[]
    for i in range(1,len(parts),2):
        if float(re.search(r't=([\d.eE+-]+)',parts[i])[1])>.0063:continue
        ns=re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',parts[i+1])
        for j,v in enumerate(ns):rows.append({'j':j,'N':sum(map(int,v))})
    stats={}
    for label,section in [('first_100_solves',rows[:100]),('after_100_solves',rows[100:])]:
        positive=[v for v in section if v['N']>0]
        phases=sorted({v['j'] for v in positive})
        groups={j:[v['N'] for v in positive if v['j']==j] for j in phases}
        anchor=med(groups[0])
        stats[label]={j:{'positive_samples':len(v),'median':med(v),'relative_to_j0':med(v)-anchor} for j,v in groups.items()}
    result[case]={'source':str(p),'window':.0063,'phase_baselines':stats}
(R/'phase_drift_audit.json').write_text(json.dumps(result,indent=2))
for case,v in result.items():
    print(case,{label:{j:val for j,val in values.items() if j<4} for label,values in v['phase_baselines'].items()})
