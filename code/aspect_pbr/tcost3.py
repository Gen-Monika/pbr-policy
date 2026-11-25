import re,sys,os
D='/root/autodl-tmp/PBR/aspect_runs/tosi'
def info(c,l,T):
    p=f'{D}/C{c}_{l}/run.log'
    if not os.path.exists(p): return None
    t=open(p,errors='ignore').read()
    blocks=re.split(r'(\*\*\* Timestep \d+:\s+t=[0-9.eE+-]+ seconds)',t)
    s=i=r=0; last=0
    for k in range(1,len(blocks),2):
        tm=float(re.search(r't=([0-9.eE+-]+)',blocks[k]).group(1)); last=tm
        if tm>T: break
        b=blocks[k+1]
        for a,cc in re.findall(r'Solving Stokes system\.\.\. (\d+)\+(\d+)',b): i+=int(a)+int(cc); s+=1
        r+=b.count('Rebuilding Stokes')
    bs=re.findall(r'Build Stokes preconditioner\s*\|\s*(\d+)\s*\|\s*([0-9.]+)s',t)
    sv=re.findall(r'Solve Stokes system\s*\|\s*(\d+)\s*\|\s*([0-9.]+)s',t)
    return s,i,r,last,(bs[-1] if bs else None),(sv[-1] if sv else None),'External wall' in t
c=sys.argv[1]; T=float(sys.argv[2])
labs=['OFF','V4','V8','V15','V30','NEVER','ONLv','ONLv_B20','ONLv_B50']
rows={l:info(c,l,T) for l in labs}; rows={k:v for k,v in rows.items() if v}
off=rows['OFF']
# r from OFF timers (cumulative to last print); its/solve from the window
nb,tb=int(off[4][0]),float(off[4][1]); ns,ts=int(off[5][0]),float(off[5][1])
R=(tb/nb)/((ts/ns)/(off[1]/off[0]))
print(f'Case {c}  window t<={T}  r={R:.1f}  reached:',{k:round(v[3],4) for k,v in rows.items()})
for l,(s,i,r,_,_,_,done) in rows.items():
    cpk=(i+R*r)/max(1,s)
    print(f'  {l:9s} solves={s:5d} its/solve={i/max(1,s):7.2f} rb={r:5d} cost/solve={cpk:7.2f} /OFF={cpk/((off[1]+R*off[2])/off[0]):.3f}')
