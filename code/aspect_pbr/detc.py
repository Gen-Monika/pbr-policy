import re,csv,statistics as st
W='/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1'
def info(m,r=1):
    t=open(f'{W}/r{r}_{m}/run.log').read()
    its=sum(int(a)+int(b) for a,b in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',t))
    rb=len(re.findall(r'Rebuilding Stokes',t))
    return its,rb
# measured r from ONLINE traces (median of r samples ~ rMed at end)
rs=[]
for r in (1,2,3):
    rows=list(csv.DictReader(open(f'{W}/r{r}_ONLINE/trace.csv')))
    rs.append(float(rows[-1]['rMed']))
print('online-measured r (rMed at end, 3 rounds):',rs)
# timer-based r: build time per rebuild / solve time per iteration, per mode
for m in ['K1','K10','K25','NEVER','ONLINE']:
    vals=[]
    for r in (1,2,3):
        t=open(f'{W}/r{r}_{m}/run.log').read()
        g=lambda s: float(re.findall(re.escape(s)+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',t)[-1])
        its,rb=info(m,r)
        if rb>2: vals.append((g('Build Stokes preconditioner')/rb)/(g('Solve Stokes system')/its))
    if vals: print('timer r',m,[round(v,1) for v in vals])
R=st.median(rs)
print('r used =',R)
base=None
for m in ['K1','K10','K25','NEVER','ONLINE']:
    its,rb=info(m)
    c=its+R*rb
    if m=='K1': base=c
    print(f'{m:7s} its={its:6d} rb={rb:5d} cost={c:9.0f}  /K1={c/base:.3f}')
