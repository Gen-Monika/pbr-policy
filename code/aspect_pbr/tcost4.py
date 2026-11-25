import re,sys,os
D='/root/autodl-tmp/PBR/aspect_runs/tosi'
def seq(c,l,T):
    p=f'{D}/C{c}_{l}/run.log'
    if not os.path.exists(p): return None
    t=open(p,errors='ignore').read()
    blocks=re.split(r'(\*\*\* Timestep \d+:\s+t=[0-9.eE+-]+ seconds)',t)
    out=[]  # list of (its, rebuilt)
    pend=False
    for k in range(1,len(blocks),2):
        tm=float(re.search(r't=([0-9.eE+-]+)',blocks[k]).group(1))
        if tm>T: break
        for line in blocks[k+1].splitlines():
            if 'Rebuilding Stokes preconditioner' in line: pend=True
            if 'Solving Stokes system...' in line:
                m=re.search(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',line)
                reb = pend and ('Reusing' not in line)
                out.append((int(m.group(1))+int(m.group(2)), reb)); pend=False
    return out
c=sys.argv[1]; T=float(sys.argv[2]); R=float(sys.argv[3]); S0=int(sys.argv[4]) if len(sys.argv)>4 else 100
labs=['OFF','V4','V8','V15','V30','ONLv','ONLv_B20','ONLv_B50']
res={}
for l in labs:
    s=seq(c,l,T)
    if not s: continue
    tail=s[S0:]
    its=sum(x for x,_ in tail); rb=sum(1 for _,b in tail if b)
    res[l]=(len(tail),its,rb)
off=res['OFF']; base=(off[1]+R*off[2])/off[0]
best=min((v[1]+R*v[2])/v[0] for k,v in res.items() if k.startswith('V'))
print(f'Case {c}: solves after first {S0}  (n={off[0]})')
for l,(n,i,r) in res.items():
    cc=(i+R*r)/n
    print(f'  {l:9s} n={n:5d} its/solve={i/n:6.2f} rb={r:4d} cost/solve={cc:6.2f} /OFF={cc/base:.3f} /bestFixed={cc/best:.3f}')
