import glob,os,re,statistics as st
from collections import defaultdict
W=os.environ.get('W','/root/autodl-tmp/PBR/aspect_runs/cmp_l5')
d=defaultdict(list)
for run in sorted(glob.glob(W+'/r*_*/run.log')):
    lab=os.path.basename(os.path.dirname(run)).split('_',1)[1]
    t=open(run,errors='ignore').read()
    steps=len(re.findall(r'^\*\*\* Timestep',t,re.M))
    rb=len(re.findall(r'Rebuilding Stokes preconditioner',t))
    ru=len(re.findall(r'Reusing Stokes preconditioner',t))
    its=sum(int(a)+int(b) for a,b in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',t))
    def lastSec(name):
        m=re.findall(name+r'\s*\|\s*\d+\s*\|\s*([0-9.]+)s',t)
        return float(m[-1]) if m else None
    wall=re.search(r'External wall = ([0-9.]+)',t)
    d[lab].append(dict(steps=steps,rb=rb,ru=ru,its=its,
        tot=float(wall.group(1)) if wall else None,
        bs=lastSec('Build Stokes preconditioner'),
        sv=lastSec('Solve Stokes system'),
        asm=lastSec('Assemble Stokes system'),
        temp=lastSec('Assemble temperature system')))
order=['K1','K10','K50','NEVER','ONLINE']
print(f"{'mode':<8}{'n':>2}{'steps':>7}{'reb':>6}{'reuse':>7}{'its':>8}{'wall_med':>10}{'ms/step':>9}{'rel K1':>8}{'setup':>8}{'solve':>8}{'its/K1':>8}")
rows={}
for k in order:
    if k not in d: continue
    v=d[k]
    ms=[x['tot']/x['steps']*1000 for x in v if x['tot'] and x['steps']]
    rows[k]=dict(ms=ms,rb=st.median([x['rb'] for x in v]),its=st.median([x['its'] for x in v]),
        bs=st.median([x['bs'] for x in v if x['bs'] is not None]),
        sv=st.median([x['sv'] for x in v if x['sv'] is not None]),
        steps=st.median([x['steps'] for x in v]),
        tot=st.median([x['tot'] for x in v if x['tot']]), n=len(v))
k1ms=rows.get('K1',{}).get('ms') and st.median(rows['K1']['ms'])
k1its=rows.get('K1',{}).get('its')
for k in order:
    if k not in rows: continue
    r=rows[k]
    print(f"{k:<8}{r['n']:>2}{r['steps']:>7.0f}{r['rb']:>6.0f}{r['steps']-r['rb']:>7.0f}{r['its']:>8.0f}{r['tot']:>10.1f}"
          f"{st.median(r['ms']):>9.2f}{(st.median(r['ms'])/k1ms if k1ms else 0):>8.3f}{r['bs']:>8.2f}{r['sv']:>8.2f}{(r['its']/k1its if k1its else 0):>8.3f}")
    print(f"         ms/step per round: {[round(x,2) for x in r['ms']]}")
for k in order:
    if k in rows and k!='K1' and len(rows[k]['ms'])==len(rows.get('K1',{}).get('ms',[])):
        pr=[rows[k]['ms'][i]/rows['K1']['ms'][i] for i in range(len(rows[k]['ms']))]
        print(f"paired {k:<6}/K1: {[round(x,3) for x in pr]} median={st.median(pr):.3f}")
