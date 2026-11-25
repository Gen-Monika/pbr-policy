"""Matched old/new official-input experiments. Never deletes previous runs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,csv,hashlib,json,os,re,shutil,subprocess,time
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
P=Path('/root/autodl-tmp/PBR');A=Path('/root/autodl-tmp/envs/aspect-2.4');M=Path('/root/autodl-tmp/envs/moose/src')
APP=Path('tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction')
G=1024**3
def environment(code):
 if code=='aspect':
  raw=subprocess.check_output(['bash','-c','source /root/autodl-tmp/envs/dealenv.sh; /usr/bin/env -0'])
 else:
  raw=subprocess.check_output(['/root/autodl-tmp/envs/bin/micromamba','run','-p','/root/autodl-tmp/envs/moose-env','/usr/bin/env','-0'])
 env={k.decode():v.decode() for x in raw.split(b'\0') if b'=' in x for k,v in [x.split(b'=',1)]}
 for k in ['PBR_POLICY','PBR_K','PBR_BASE','PBR_LOG','PBR_UNIT','PBR_COND','LD_PRELOAD']:env.pop(k,None)
 env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',HWLOC_COMPONENTS='-opencl,-gl,-cuda,-nvml',PBR_POLICY='online',PBR_BASE='100',PBR_UNIT='solve')
 return env
ENVS={k:environment(k) for k in ['aspect','moose']}

def rss(pid):
 try:
  s=Path(f'/proc/{pid}/status').read_text();m=re.search(r'^VmRSS:\s+(\d+)',s,re.M)
  return int(m[1])*1024 if m else 0
 except FileNotFoundError:return 0

def prepare(case,group,round_,variant,short):
 out=R/group/case/f'r{round_}_{variant}';out.mkdir(parents=True,exist_ok=False)
 env=ENVS['moose' if case=='MOOSE' else 'aspect'].copy();env['PBR_COND']='index' if variant=='index' else 'off'
 env['PBR_LOG']=str(out/'trace.csv')
 if case.startswith('C'):
  old=P/'aspect_runs/tosi'/f'{case}_ONLv';input_name=f'Tosi_Case{case[1:]}.prm'
  for name in [input_name,'Tosi_base.prm','libtosi_benchmark.so']:shutil.copy2(old/name,out/name)
  if short:
   with (out/'Tosi_base.prm').open('a') as f:f.write('\nset End time = 0.002\n')
  exe=A/('build-pbr2' if variant=='old' else 'build-pbr3')/'aspect';cmd=[str(exe),input_name]
  estimate={'memory_gib_each':2,'seconds_each':1500 if case=='C4' else 900,'basis':'official 13764 or 54148 DoFs; prior full online times 65/467/745/259 s; paired conservative estimate'}
 elif case=='Blankenbach':
  old=P/'aspect_runs/cmp_l5_t0.1_fix/r1_ONLINE';input_name='case.prm'
  for name in ['case.prm','initial_temperature_case2a.txt']:shutil.copy2(old/name,out/name)
  shutil.copytree(old/'plugin',out/'plugin')
  if short:
   with (out/'case.prm').open('a') as f:f.write('\nset End time = 0.008\n')
  exe=A/('build-pbr2' if variant=='old' else 'build-pbr3')/'aspect';cmd=[str(exe),input_name]
  estimate={'memory_gib_each':1,'seconds_each':600,'basis':'same refinement 5 input, old full time 275 s'}
 else:
  old=M/APP/'problems';input_name='step6a_coupled.i'
  shutil.copytree(old,out,dirs_exist_ok=True)
  exe=(R/'moose_backup' if variant=='old' else M)/APP/'darcy_thermo_mech-opt'
  if variant=='old':env['LD_PRELOAD']=str(R/'moose_backup/framework/libmoose-opt.so.0.0.0')
  cmd=[str(exe),'-i',input_name,'Outputs/exodus=false','Executioner/reuse_preconditioner=true','Executioner/reuse_preconditioner_max_linear_its=1000000']
  if short:cmd+=['Executioner/num_steps=60']
  cmd+=['-log_view']
  estimate={'memory_gib_each':0.7,'seconds_each':180,'basis':'4422 unknowns, historical full runtime 75-90 s'}
 assert estimate['memory_gib_each']<8 and estimate['seconds_each']<1800
 files=[p for p in out.iterdir() if p.suffix in ['.prm','.i']]
 meta={'case':case,'variant':variant,'group':group,'round':round_,'short':short,'command':cmd,'environment':{k:v for k,v in env.items() if k.startswith('PBR_') or k=='LD_PRELOAD'},'estimate':estimate,'inputs_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'source_input_dir':str(old),'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'cgroup_memory_max':int(Path('/sys/fs/cgroup/memory.max').read_text())}
 (out/'metadata.json').write_text(json.dumps(meta,indent=2));return out,cmd,env,meta

def run(prepared):
 out,cmd,env,meta=prepared
 peak=0;reason=None;start=time.monotonic();meta['start_epoch']=time.time()
 meta['load_before']=Path('/proc/loadavg').read_text().strip()
 with (out/'run.log').open('w') as log:
  proc=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
  (out/'pid').write_text(str(proc.pid))
  while proc.poll() is None:
   peak=max(peak,rss(proc.pid));cg=int(Path('/sys/fs/cgroup/memory.current').read_text())
   if meta['case']=='MOOSE' and 'loaded_moose_libraries' not in meta:
    try:
     libs=sorted({l.split()[-1] for l in Path(f'/proc/{proc.pid}/maps').read_text().splitlines() if 'libmoose-opt.so' in l})
     if libs:meta['loaded_moose_libraries']=libs
    except FileNotFoundError:pass
   if peak>7*G:reason='single process >7 GiB guard'
   elif cg>40*G:reason='cgroup >40 GiB guard'
   elif time.monotonic()-start>1500:reason='25 minute probe guard'
   if reason:
    proc.terminate()
    try:proc.wait(timeout=8)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    break
   time.sleep(.5)
  rc=proc.wait();wall=time.monotonic()-start
  log.write(f'\nSTEPB_END rc={rc} elapsed={wall:.6f} peak_rss_bytes={peak} guard={reason}\n')
 meta.update(rc=rc,wall_seconds=wall,peak_rss_bytes=peak,guard=reason,end_epoch=time.time(),load_after=Path('/proc/loadavg').read_text().strip())
 (out/'result.json').write_text(json.dumps(meta,indent=2))
 print(meta['case'],meta['round'],meta['variant'],'RC',rc,'wall',round(wall,2),'MiB',round(peak/2**20,1),'guard',reason,flush=True)
 return meta

def main():
 ap=argparse.ArgumentParser();ap.add_argument('group',choices=['regression','full']);args=ap.parse_args()
 group=args.group
 cases=['Blankenbach','C1','MOOSE'] if group=='regression' else ['C1','C3','C4','C5','Blankenbach','MOOSE']
 results=[]
 for round_ in range(1,2 if group=='regression' else 6):
  order=cases if round_%2 else list(reversed(cases))
  for case in order:
   if group=='full' and case!='MOOSE' and round_>3:continue
   variants=['old','off'] if group=='regression' else ['old','index']
   if round_%2==0:variants.reverse()
   jobs=[prepare(case,group,round_,v,group=='regression') for v in variants]
   with ThreadPoolExecutor(max_workers=2) as pool:
    fs=[pool.submit(run,j) for j in jobs];pair=[f.result() for f in fs]
   results.extend(pair);(R/f'{group}_results.json').write_text(json.dumps(results,indent=2))
   if any(x['rc'] or x['guard'] for x in pair):
    print('STOP after failed/guarded pair; no further experiments',flush=True);return
 (R/f'{group}_done').write_text(time.strftime('%F %T'))

if __name__=='__main__':main()
