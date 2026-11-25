from pathlib import Path
import json,re,time
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
print(time.strftime('%F %T'), 'load',Path('/proc/loadavg').read_text().strip(),
      'cgroup_GiB',round(int(Path('/sys/fs/cgroup/memory.current').read_text())/1024**3,3))
running=[]
for p in sorted((R/'full').glob('*/r*')):
    if (p/'result.json').exists():continue
    pidfile=p/'pid'
    if not pidfile.exists():continue
    pid=int(pidfile.read_text());proc=Path(f'/proc/{pid}')
    if not proc.exists():continue
    status=(proc/'status').read_text();rss=re.search(r'^VmRSS:\s+(\d+)',status,re.M)
    log=(p/'run.log').read_text(errors='replace')
    steps=re.findall(r'\*\*\* Timestep (\d+):\s+t=([\d.eE+-]+)',log)
    counts=re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',log)
    row={'run':str(p.relative_to(R)),'pid':pid,'MiB':round(int(rss[1])/1024,1) if rss else None,
         'last_timestep':steps[-1] if steps else None,'completed_solves':len(counts),
         'last_Krylov_iterations':sum(map(int,counts[-1])) if counts else None}
    running.append(row)
print(json.dumps(running,indent=2))
print('completed',len(list((R/'full').glob('*/r*/result.json'))),'done',(R/'full_done').exists())
