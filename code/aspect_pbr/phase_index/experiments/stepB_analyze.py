from pathlib import Path
import csv,hashlib,json,re,statistics
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex');P=Path('/root/autodl-tmp/PBR')
def med(v):return sorted(v)[len(v)//2] if v else None
def parse(path,code,window=None):
 s=(path/'run.log').read_text(errors='replace');trace=path/'trace.csv'
 if not trace.exists():trace=path/'pbr.csv'
 tr=list(csv.DictReader(trace.open())) if trace.exists() else []
 ratios=[]
 for r in tr:
  n=float(r['its']);b=float(r['build_ms']);t=float(r['solve_ms'])
  if b>0 and n>0 and t>0 and 0<b*n/t<1e7:ratios.append(b*n/t)
 result={'path':str(path),'trace_rows':len(tr),'rho_samples':ratios,'rho_median':med(ratios)}
 if code=='aspect':
  parts=re.split(r'(\*\*\* Timestep \d+:\s+t=[\d.eE+-]+ seconds)',s);rows=[];stages=[]
  for i in range(1,len(parts),2):
   t=float(re.search(r't=([\d.eE+-]+)',parts[i])[1])
   if window is not None and t>window:continue
   block=parts[i+1];stages.append(t)
   pending=False;j=0
   for line in block.splitlines():
    if 'Rebuilding Stokes preconditioner' in line:pending=True
    m=re.search(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',line)
    if m:rows.append({'N':sum(map(int,m.groups())),'rebuild':pending,'j':j,'t':t});pending=False;j+=1
  result.update(solves=len(rows),iterations=sum(x['N'] for x in rows),rebuilds=sum(x['rebuild'] for x in rows),steps=len(stages),final_step_time=stages[-1] if stages else None,phases=sorted({x['j'] for x in rows}),zero_solves=sum(x['N']==0 for x in rows))
  def timer(name):
   vals=re.findall(re.escape(name)+r'\s*\|\s*\d+\s*\|\s*([\d.eE+-]+)s',s);return float(vals[-1]) if vals else None
  result['setup_time']=timer('Build Stokes preconditioner');result['solve_time']=timer('Solve Stokes system')
  result['solver_wall']=sum([result['setup_time'],result['solve_time']]) if result['setup_time'] is not None and result['solve_time'] is not None else None
  result['failure_lines']=[l.strip() for l in s.splitlines() if 'No convergence' in l or 'did not converge' in l or 'Aborting' in l]
 else:
  clean=re.sub(r'\x1b\[[0-9;]*m','',s);rows=[];row=None;j=0
  for line in clean.splitlines():
   m=re.match(r'\s*(\d+) Nonlinear \|R\|',line)
   if m:j=int(m[1])
   m=re.match(r'PBR solve (\d+) rebuild (\d+)',line)
   if m:row={'solve':int(m[1]),'rebuild':bool(int(m[2])),'N':0,'j':j};rows.append(row)
   m=re.match(r'\s*(\d+) Linear \|R\|',line)
   if m and row is not None:row['N']=int(m[1])
  events={}
  for line in s.splitlines():
   m=re.match(r'^(\S+)\s+(\d+)\s+[\d.]+\s+([\d.eE+-]+)\s+[\d.]+\s+[\d.eE+-]+',line)
   if m:events[m[1]]={'count':int(m[2]),'time':float(m[3])}
  result.update(solves=len(rows),iterations=sum(x['N'] for x in rows),rebuilds=sum(x['rebuild'] for x in rows),phases=sorted({x['j'] for x in rows}),solver_wall=events.get('SNESSolve',{}).get('time'),events=events)
  result['failure_lines']=[l.strip() for l in clean.splitlines() if any(w in l for w in ['DIVERGED','Solve Did NOT Converge','*** ERROR ***'])]
 result['decision_sequence']=[(r.get('step',r.get('solve')),r['rebuild'],r['age']) for r in tr]
 if tr and 'q' in tr[0]:
  frozen=[r for r in tr if r['est_dsrc']!='warmup']
  result['q_by_phase']={j:sorted({float(r['q']) for r in frozen if r['phase']==j}) for j in sorted({r['phase'] for r in frozen},key=int)}
  result['unknown_phase_rows']=sum(r['phase_known']=='0' for r in frozen)
  result['negative_model_rows']=sum(float(r['model_its'])<0 for r in tr)
 res=path/'result.json'
 if res.exists():
  meta=json.loads(res.read_text());result.update({k:meta[k] for k in ['rc','wall_seconds','peak_rss_bytes','guard','start_epoch','end_epoch']})
 return result

def main():
 allruns={}
 for group in ['regression','full']:
  for p in sorted((R/group).glob('*/r*')):
   if (p/'result.json').exists():allruns[str(p.relative_to(R))]=parse(p,'moose' if p.parent.name=='MOOSE' else 'aspect')
 fixed={}
 for c in [1,3,4,5]:
  paths=list((P/'aspect_runs/tosi').glob(f'C{c}_V[0-9]*'))+[P/f'aspect_runs/tosi/C{c}_OFF']
  fixed[f'C{c}']={p.name:parse(p,'aspect',.0063) for p in paths if (p/'run.log').exists()}
 paths=list((P/'aspect_runs/cmp_l5_t0.1_fix').glob('r1_K*'))+list((P/'aspect_runs/kgrid_l5_t0.1').glob('K*'))
 fixed['Blankenbach']={p.name:parse(p,'aspect',.1) for p in paths if (p/'run.log').exists()}
 fixed['MOOSE']={p.name:parse(p,'moose') for p in (P/'moose_cases').glob('r1_K*') if (p/'run.log').exists()}
 # C4 historical fixed runs continue beyond the reporting cutoff, whereas
 # online runs end exactly at .0063 and therefore add a shortened terminal
 # step. Compare costs on their common complete-step prefix, retaining full
 # online counts/timers separately. This corrects endpoint accounting only.
 ends={v['final_step_time'] for v in fixed['C4'].values()}
 assert len(ends)==1, 'C4 fixed endpoints need manual audit'
 cutoff=ends.pop()
 for name,v in allruns.items():
  if name.startswith('full/C4/'):
   prefix=parse(Path(v['path']),'aspect',cutoff)
   v['cost_counts']={k:prefix[k] for k in ['solves','iterations','rebuilds','steps','final_step_time']}
   v['cost_window']=cutoff
 summary={'runs':allruns,'fixed':fixed}
 (R/'analysis.json').write_text(json.dumps(summary,indent=2))
 for name,v in allruns.items():
  print(name,{k:v.get(k) for k in ['solves','iterations','rebuilds','rho_median','solver_wall','wall_seconds','failure_lines','q_by_phase','unknown_phase_rows','negative_model_rows']})
 for case,vals in fixed.items():
  print('FIXED',case,{k:(v['solves'],v['iterations'],v['rebuilds']) for k,v in vals.items()})
 for case in ['C1','Blankenbach','MOOSE']:
  a=allruns.get(f'regression/{case}/r1_old');b=allruns.get(f'regression/{case}/r1_off')
  if a and b:
   print('REGRESSION',case,'decisions_identical',a['decision_sequence']==b['decision_sequence'],'iterations_identical',a['iterations']==b['iterations'])
if __name__=='__main__':main()
