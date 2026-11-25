from pathlib import Path
import json,re
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
results={}
for p in sorted((R/'full').glob('*/r*')):
    if not (p/'result.json').exists():continue
    s=(p/'run.log').read_text(errors='replace')
    result={'rc':json.loads((p/'result.json').read_text())['rc']}
    if p.parent.name=='MOOSE':
        clean=re.sub(r'\x1b\[[0-9;]*m','',s)
        result['nonlinear_converged_messages']=len(re.findall(r'Solve Converged!',clean))
        result['failures']=[l.strip() for l in clean.splitlines() if any(k in l for k in ['DIVERGED','Solve Did NOT Converge','*** ERROR ***'])]
    else:
        parts=re.split(r'(\*\*\* Timestep \d+:\s+t=[\d.eE+-]+ seconds)',s)
        terminal=[]
        for i in range(1,len(parts),2):
            head=parts[i];body=parts[i+1]
            values=re.findall(r'Relative nonlinear residual \(total system\) after nonlinear iteration (\d+):\s+([\d.eE+-]+)',body)
            if values:
                step=int(re.search(r'Timestep (\d+)',head)[1]);t=float(re.search(r't=([\d.eE+-]+)',head)[1])
                j,res=values[-1];terminal.append({'step':step,'t':t,'last_nonlinear_iteration':int(j),'residual':float(res)})
        result['steps_with_nonlinear_residual']=len(terminal)
        result['last_step']=terminal[-1] if terminal else None
        result['steps_above_tosi_tolerance_1e5']=[v for v in terminal if v['residual']>1e-5] if p.parent.name.startswith('C') else []
        result['failures']=[l.strip() for l in s.splitlines() if any(k in l.lower() for k in ['no convergence','did not converge','failed to converge','aborting','exception'])]
    results[str(p.relative_to(R))]=result
(R/'convergence_audit.json').write_text(json.dumps(results,indent=2))
for name,r in results.items():
    if r['failures'] or r.get('steps_above_tosi_tolerance_1e5'):print(name,r)
print('completed audited runs',len(results),'MOOSE convergence messages',sorted({r['nonlinear_converged_messages'] for r in results.values() if 'nonlinear_converged_messages' in r}))
