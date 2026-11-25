import re
R=28.85
rows=[]
def get(path):
    t=open(path).read()
    its=sum(int(a)+int(b) for a,b in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',t))
    rb=len(re.findall(r'Rebuilding Stokes',t)); return its,rb
C='/root/autodl-tmp/PBR/aspect_runs/cmp_l5_t0.1/r1_'
G='/root/autodl-tmp/PBR/aspect_runs/kgrid_l5_t0.1/K'
for lab,p in [('K1',C+'K1'),('K10',C+'K10'),('K15',G+'15'),('K20',G+'20'),('K25',C+'K25'),('K35',G+'35'),('K50',G+'50'),('K75',G+'75'),('K100',G+'100'),('K150',G+'150'),('NEVER',C+'NEVER'),('ONLINE',C+'ONLINE')]:
    its,rb=get(p+'/run.log'); rows.append((lab,its,rb))
base=rows[0][1]+R*rows[0][2]
for rho_lab,rho in [('r',R),('3r',3*R),('r/3',R/3)]:
    print('rho=',rho_lab,round(rho,1))
    best=None
    for lab,its,rb in rows:
        c=its+rho*rb
        if lab not in('ONLINE',) and (best is None or c<best[1]): best=(lab,c)
    for lab,its,rb in rows:
        c=its+rho*rb
        print(f'  {lab:7s} its={its:6d} rb={rb:5d} cost={c:9.0f}  /K1={c/(rows[0][1]+rho*rows[0][2]):.3f}  /best={c/best[1]:.3f}')
    print('  best fixed:',best[0])
