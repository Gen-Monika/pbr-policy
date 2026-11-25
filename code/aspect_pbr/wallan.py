import re,statistics as st,sys
def get(d):
    t=open(d+'/run.log',errors='ignore').read()
    g=lambda s: float(re.findall(re.escape(s)+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',t)[-1])
    its=sum(int(a)+int(b) for a,b in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',t))
    rb=t.count('Rebuilding Stokes'); w=float(re.search(r'External wall = ([0-9.]+)',t).group(1))
    steps=len(re.findall(r'^\*\*\* Timestep',t,re.M))
    return dict(stokes=g('Build Stokes preconditioner')+g('Solve Stokes system'),wall=w,its=its,rb=rb,steps=steps)
def report(title,dirs,modes,base,R):
    print('==',title)
    D={m:[get(dirs(r,m)) for r in (1,2,3)] for m in modes}
    for m in modes:
        v=D[m]
        ps=[v[i]['stokes']/D[base][i]['stokes'] for i in range(3)]
        pw=[v[i]['wall']/D[base][i]['wall'] for i in range(3)]
        cost=[(x['its']+R*x['rb']) for x in v]
        print(f"{m:7s} rb={[x['rb'] for x in v]} its={[x['its'] for x in v]} steps={v[0]['steps']} stokes={[round(x['stokes'],1) for x in v]} /base={[round(p,3) for p in ps]} med={st.median(ps):.3f} | wall/base={[round(p,3) for p in pw]} med={st.median(pw):.3f} | cost={cost}")
    return D
B='/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1_fix'
report('Blankenbach fixed code', lambda r,m:f'{B}/r{r}_{m}', ['K1','K10','K25','NEVER','ONLINE'],'K1',28.85)
T='/root/autodl-tmp/PBR/aspect_runs/tosi'
report('Tosi C4 (t<=0.0063)', lambda r,m:f'{T}/C4_W{r}_{m}', ['K1','V15','V30','ONLv'],'K1',24.8)
