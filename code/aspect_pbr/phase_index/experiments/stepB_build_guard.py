from pathlib import Path
import json,os,subprocess,time
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
G=1024**3
def processes():
 out={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   d=dict(x.split(':',1) for x in (p/'status').read_text().splitlines() if ':' in x)
   out[int(p.name)]=(int(d['PPid']),int(d.get('VmRSS','0 kB').split()[0])*1024,d['Name'].strip())
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return out
results=[]
for name in ['aspect','moose']:
 start=time.monotonic();peak=0;peakchild=0;reason=None
 with (R/f'build_{name}.log').open('w') as log:
  p=subprocess.Popen(['bash',str(R/f'stepB_build_{name}.sh')],stdout=log,stderr=subprocess.STDOUT)
  (R/f'build_{name}.pid').write_text(str(p.pid))
  while p.poll() is None:
   procs=processes();own={p.pid}
   while True:
    more={i for i,(pp,_,_) in procs.items() if pp in own}-own
    if not more:break
    own|=more
   rss=[procs[i][1] for i in own if i in procs];peak=max(peak,sum(rss));peakchild=max([peakchild]+rss)
   if max(rss or [0])>7.5*G:reason='single process >7.5 GiB'
   if int(Path('/sys/fs/cgroup/memory.current').read_text())>40*G:reason='cgroup >40 GiB'
   if reason:
    for i in sorted(own,reverse=True):
     try:os.kill(i,15)
     except ProcessLookupError:pass
    break
   time.sleep(2)
  rc=p.wait()
 result={'build':name,'rc':rc,'seconds':time.monotonic()-start,'peak_tree_bytes':peak,'peak_process_bytes':peakchild,'guard':reason}
 results.append(result);(R/'build_results.json').write_text(json.dumps(results,indent=2));print(result,flush=True)
 if rc or reason:break
(R/'build_done').write_text(time.strftime('%F %T'))
