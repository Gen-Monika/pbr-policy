import re,csv
W='/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1'
t=open(f'{W}/r1_ONLINE/run.log').read()
# first rebuild occurrences: which timestep
steps=re.split(r'\*\*\* Timestep (\d+):',t)
rbsteps=[int(steps[i]) for i in range(1,len(steps),2) if 'Rebuilding Stokes' in steps[i+1]]
print('rebuild timesteps count',len(rbsteps),'first',rbsteps[:3],'n<100:',sum(s<100 for s in rbsteps))
# time at step 842
m=re.search(r'\*\*\* Timestep 842:\s+t=([0-9.e+-]+)',t); print('t at 842:',m.group(1) if m else None)
# K25 (ref5) age profile, steps 200-800
t2=open(f'{W}/r1_K25/run.log').read()
age=0;S={};C={};n=0
for line in t2.splitlines():
    if 'Rebuilding Stokes' in line: age=0
    elif 'Reusing Stokes' in line: age+=1
    m=re.search(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',line)
    if m:
        n+=1
        if 100<n<=800:
            S[age]=S.get(age,0)+int(m.group(1))+int(m.group(2)); C[age]=C.get(age,0)+1
print('ref5 K25 age-mean its, steps 100-800:', {a:round(S[a]/C[a],1) for a in sorted(S)})
# component timers ONLINE vs K25 for decision-independent parts
def sec(path,name):
    x=re.findall(re.escape(name)+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',open(path).read()); return float(x[-1])
for r in (1,2,3):
    o=sum(sec(f'{W}/r{r}_ONLINE/run.log',n) for n in ['Assemble temperature system','Postprocessing'])
    k=sum(sec(f'{W}/r{r}_K25/run.log',n) for n in ['Assemble temperature system','Postprocessing'])
    k10=sum(sec(f'{W}/r{r}_K10/run.log',n) for n in ['Assemble temperature system','Postprocessing'])
    print(f'r{r} decision-independent (asmT+post): ONLINE {o:.1f} K25 {k:.1f} K10 {k10:.1f}  ratio O/K25={o/k:.3f} O/K10={o/k10:.3f}')
