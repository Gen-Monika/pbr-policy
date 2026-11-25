import re,sys,statistics as st
# generic: per linear solve of the target solver, count Krylov iterations from residual output lines
# Elmer prints "   <method>:  <iter>  <res>  <rel>" with Residual Output = 1
def parse(path, prec):
    t=open(path,errors='ignore').read().splitlines()
    solves=[]; cur=None; pend=None; last=None
    pat=re.compile(r'^\s*(gcr|bicgstabl|bicgstab|gmres|cg|bicgstab2|idrs)\s*:\s+(\d+)\s', re.I)
    for line in t:
        m=re.match(r'\s*Prec-'+prec+r': Elapsed REAL time:\s+([0-9.]+)',line)
        if m: pend=float(m.group(1))
        m=pat.match(line)
        if m:
            k=int(m.group(2))
            if cur is None or k<=last:
                cur={'its':k,'fact':pend}; solves.append(cur); pend=None
            cur['its']=k; last=k
        if re.search(r'Linear system time',line): cur=None; last=None
    return solves
if __name__=='__main__':
    prec=sys.argv[1]
    for p in sys.argv[2:]:
        s=parse(p,prec); its=[x['its'] for x in s]; f=[x['fact'] for x in s if x['fact'] and x['fact']>0]
        print(p.split('/')[-2], 'solves',len(s),'its',sum(its),'rebuilds',len(f),'fact_med_ms',round(1000*st.median(f),2) if f else 0, 'its/solve med', st.median(its) if its else 0)
