"""Rounds are sequential; all six matched pairs within a round run together."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,time
import stepB_run as base
R=base.R
prior=json.loads((R/'regression_results.json').read_text())
assert len(prior)==6 and all(x['rc']==0 and x['guard'] is None for x in prior)
assert not (R/'full_results.json').exists()
# 12 solver processes at most. Conservative sum of prepared estimates: 19.4 GiB.
# Per-process and cgroup guards remain active in each runner.
results=[]
cases=['C1','C3','C4','C5','Blankenbach','MOOSE']
for round_ in range(1,6):
 order=cases if round_%2 else list(reversed(cases))
 if round_>3:order=['MOOSE']
 jobs=[]
 for case in order:
  variants=['old','index'] if round_%2 else ['index','old']
  jobs += [base.prepare(case,'full',round_,v,False) for v in variants]
 estimates=sum(j[3]['estimate']['memory_gib_each'] for j in jobs)
 assert len(jobs)<=16 and estimates<=40
 (R/f'round{round_}_preflight.json').write_text(json.dumps({'solver_processes':len(jobs),'memory_gib_sum_estimate':estimates,'estimated_seconds_max':max(j[3]['estimate']['seconds_each'] for j in jobs),'cases':order},indent=2))
 print('ROUND',round_,'START',time.strftime('%F %T'),'processes',len(jobs),'estimated GiB',estimates,flush=True)
 pair=[]
 with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
  fs=[pool.submit(base.run,j) for j in jobs]
  for f in as_completed(fs):
   value=f.result();results.append(value);pair.append(value)
   (R/'full_results.json').write_text(json.dumps(results,indent=2))
 print('ROUND',round_,'DONE',time.strftime('%F %T'),flush=True)
 if any(x['rc'] or x['guard'] for x in pair):
  print('STOP after failed/guarded round; rule unchanged',flush=True);break
else:(R/'full_done').write_text(time.strftime('%F %T'))
