import re,sys,glob,os
T_END=float(sys.argv[1]) if len(sys.argv)>1 else 0.005
D='/root/autodl-tmp/PBR/aspect_runs/tosi'
def info(l):
    t=open(f'{D}/C4_{l}/run.log',errors='ignore').read()
    blocks=re.split(r'(\*\*\* Timestep \d+:\s+t=[0-9.eE+-]+ seconds)',t)
    s=i=r=0; last=0
    for k in range(1,len(blocks),2):
        tm=float(re.search(r't=([0-9.eE+-]+)',blocks[k]).group(1)); last=tm
        if tm>T_END: break
        b=blocks[k+1]
        for a,c in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',b): i+=int(a)+int(c); s+=1
        r+=b.count('Rebuilding Stokes')
    return s,i,r,last
labs=['OFF','V4','V6','V8','V12','V15','V20','V30','S2','S3','S5','S10','NEVER','ONLs','ONLv']
rows={l:info(l) for l in labs if os.path.exists(f'{D}/C4_{l}/run.log')}
print('reached t:',{l:round(v[3],4) for l,v in rows.items()})
R=float(sys.argv[2]) if len(sys.argv)>2 else 26.3
b=None
for l,(s,i,r,_) in rows.items():
    c=(i+R*r)/max(1,s)
    if b is None: b=c
    print(f'{l:6s} solves={s:5d} its={i:6d} rb={r:4d} its/solve={i/max(1,s):5.2f} cost/solve={c:6.2f} /OFF={c/b:.3f}')
