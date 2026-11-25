import re,sys,statistics as st
def parse(path, prec='ilu1'):
    t=open(path,errors='ignore').read().splitlines()
    solves=[]; cur=None; pending_fact=None
    for line in t:
        m=re.match(r'\s*Prec-'+prec+r': Elapsed REAL time:\s+([0-9.]+)',line)
        if m: pending_fact=float(m.group(1))
        m=re.match(r'\s*gcr:\s+(\d+)\s',line)
        if m:
            k=int(m.group(1))
            if k==1:
                cur={'its':1,'fact':pending_fact}; solves.append(cur); pending_fact=None
            else: cur['its']=k
        m=re.search(r'Linear system time \(CPU,REAL\) for flow solution:\s+([0-9.]+)\s+([0-9.]+)',line)
        if m and solves and 'lt' not in solves[-1]: solves[-1]['lt']=float(m.group(2))
    return solves
for p in sys.argv[1:]:
    s=parse(p)
    its=[x['its'] for x in s]; facts=[x['fact'] for x in s if x['fact'] is not None]
    lts=[x.get('lt') for x in s if x.get('lt') is not None]
    tot=sum(its)
    print(p.split('/')[-2], 'solves',len(s),'its_total',tot,'facts',len(facts),'fact_med_ms',round(1000*st.median(facts),2) if facts else None,
          'linsys_med_ms', round(1000*st.median(lts),1) if lts else None)
    if facts and lts:
        per_it=st.median(lts)/st.median(its)
        print('   r ~ fact/per_it =', round(st.median(facts)/per_it,2), ' its per solve median', st.median(its))
    # its by blocks of 30 solves
    print('   its per 30-solve block:', [round(sum(its[i:i+30])/len(its[i:i+30]),1) for i in range(0,len(its),30)])

def cost_table(paths, R):
    rows=[]
    for p in paths:
        s=parse(p); its=sum(x['its'] for x in s); nf=sum(1 for x in s if x['fact'] and x['fact']>0.0005)
        rows.append((p.split('/')[-2].replace('run_fssa_',''),len(s),its,nf))
    base=None
    for lab,ns,its,nf in rows:
        c=its+R*nf
        if base is None: base=c
        print(f'  {lab:6s} solves={ns:4d} its={its:7d} rebuilds={nf:4d} cost={c:9.1f} /K1={c/base:.3f}')
