import re
W='/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1'
secs=['Assemble Stokes system','Assemble temperature system','Build Stokes preconditioner','Build temperature preconditioner','Postprocessing','Solve Stokes system','Solve temperature system']
short=['asmS','asmT','bldS','bldT','post','solS','solT']
print('%-7s r %7s '%('mode','wall')+' '.join('%7s'%s for s in short)+'    sum  aspTot')
for m in ['K1','K10','K25','NEVER','ONLINE']:
  for r in (1,2,3):
    t=open(f'{W}/r{r}_{m}/run.log').read()
    wall=float(re.search(r'External wall = ([0-9.]+)',t).group(1))
    v=[]
    for s in secs:
        x=re.findall(re.escape(s)+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',t); v.append(float(x[-1]) if x else 0)
    tot=re.findall(r'Total wallclock time elapsed since start\s*\|\s*([0-9.]+)s',t)
    print('%-7s %d %7.1f '%(m,r,wall)+' '.join('%7.1f'%x for x in v)+'  %6.1f  %s'%(sum(v),tot[-1] if tot else '?'))
print()
import statistics as st
print('policy-attributable = Build Stokes preconditioner + Solve Stokes system (s)')
res={}
for m in ['K1','K10','K25','NEVER','ONLINE']:
  a=[]
  for r in (1,2,3):
    t=open(f'{W}/r{r}_{m}/run.log').read()
    g=lambda s: float(re.findall(re.escape(s)+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',t)[-1])
    a.append(g('Build Stokes preconditioner')+g('Solve Stokes system'))
  res[m]=a
  print('%-7s %s median=%.1f'%(m,[round(x,1) for x in a],st.median(a)))
for ref in ['K1','K10','K25','NEVER']:
  pr=[res['ONLINE'][i]/res[ref][i] for i in range(3)]
  print('ONLINE/%-6s paired %s median=%.3f'%(ref,[round(x,3) for x in pr],st.median(pr)))
