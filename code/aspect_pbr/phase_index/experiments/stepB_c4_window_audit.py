from pathlib import Path
import json,re
P=Path('/root/autodl-tmp/PBR');R=P/'stepB/phase_index_20261017_codex'
paths=[P/'aspect_runs/tosi/C4_OFF',P/'aspect_runs/tosi/C4_ONLv']+list((R/'full/C4').glob('r*'))
out={}
for p in paths:
    if p.parent.name=='C4' and not (p/'result.json').exists():continue
    s=(p/'run.log').read_text();parts=re.split(r'(\*\*\* Timestep \d+:\s+t=[\d.eE+-]+ seconds)',s);rows=[]
    for i in range(1,len(parts),2):
        t=float(re.search(r't=([\d.eE+-]+)',parts[i])[1])
        if t>.0063:continue
        block=parts[i+1];counts=[sum(map(int,v)) for v in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',block)]
        rows.append({'t':t,'solves':len(counts),'iterations':sum(counts),'rebuilds':block.count('Rebuilding Stokes preconditioner')})
    out[str(p)]={'last_three_steps':rows[-3:],
      't_le_0.0063':{k:sum(v[k] for v in rows) for k in ['solves','iterations','rebuilds']},
      'common_prefix_t_le_0.00629005':{k:sum(v[k] for v in rows if v['t']<=.00629005) for k in ['solves','iterations','rebuilds']}}
(R/'c4_window_audit.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
