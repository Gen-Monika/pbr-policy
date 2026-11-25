"""Count Krylov iterations from final residual indices, never residual-line totals."""
from pathlib import Path
import csv,json,re

P=Path('/root/autodl-tmp/PBR/moose_cases')
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
results={}
for p in sorted(P.glob('r[1-5]_*')):
    log=p/'run.log'
    if not log.exists():continue
    s=re.sub(r'\x1b\[[0-9;]*m','',log.read_text(errors='replace'))
    linear=[];current=None;residual_lines=0
    for line in s.splitlines():
        m=re.match(r'\s*(\d+) Linear \|R\|',line)
        if not m:continue
        residual_lines+=1;n=int(m[1])
        if n==0:
            if current is not None:linear.append(current)
            current=0
        else:
            assert current is not None and n==current+1,(str(p),current,n)
            current=n
    if current is not None:linear.append(current)
    if not linear:continue
    builds=len(re.findall(r'^PBR solve \d+ rebuild 1',s,re.M))
    gmres=re.search(r'^KSPGMRESOrthog\s+(\d+)',s,re.M)
    pcsetup=re.search(r'^PCSetUp\s+(\d+)',s,re.M)
    trace=p/'pbr.csv'
    rows=list(csv.DictReader(trace.open())) if trace.exists() else []
    result={'solves':len(linear),'iterations':sum(linear),'residual_lines':residual_lines,
            'gmres_orthog_count':int(gmres[1]) if gmres else None,
            'pcsetup_count':int(pcsetup[1]) if pcsetup else None,
            'trace_sum_plus_terminal':sum(int(r['its']) for r in rows)+linear[-1] if rows else None,
            'rebuilds_from_hook':builds or None}
    assert result['iterations']==result['residual_lines']-result['solves']
    if gmres:assert result['iterations']==int(gmres[1])
    if rows:assert result['trace_sum_plus_terminal']==result['iterations']
    results[p.name]=result
(R/'moose_history_count_audit.json').write_text(json.dumps(results,indent=2))
for k,v in results.items():
    if k.startswith('r1_'):print(k,v)
print('audited runs',len(results))
