import re,csv
R=28.85
def get(p):
    t=open(p+'/run.log').read()
    its=sum(int(a)+int(b) for a,b in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',t))
    rb=len(re.findall(r'Rebuilding Stokes',t)); ok='EXIT=0' in t; return its,rb,ok
best=26134
for b in (10,20,50):
    p=f'/root/autodl-tmp/PBR/aspect_runs/basesens_l5_t0.1/B{b}'
    its,rb,ok=get(p)
    rows=list(csv.DictReader(open(p+'/trace.csv')))
    post=[int(r['step']) for r in rows if r['rebuild']=='1' and int(r['step'])>=b]
    print(f'BASE={b:3d} ok={ok} its={its} rb={rb} cost(r)={its+R*rb:.0f} /best={ (its+R*rb)/best:.3f} /K1={(its+R*rb)/71023:.3f} post-warmup rebuilds={post}')
its,rb,ok=get('/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1/r1_ONLINE')
print(f'BASE=100 its={its} rb={rb} cost={its+R*rb:.0f} /best={(its+R*rb)/best:.3f}')
