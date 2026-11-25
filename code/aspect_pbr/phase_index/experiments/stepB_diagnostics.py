"""Audit phase traces and explain independent-run timing divergence."""
from pathlib import Path
import csv,json,re,subprocess

R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
diagnostics={}
for case in ['C1','C3','C4','C5','Blankenbach','MOOSE']:
    for n in range(1,6 if case=='MOOSE' else 4):
        pair={}
        for variant in ['old','index']:
            p=R/'full'/case/f'r{n}_{variant}'
            if not (p/'result.json').exists():continue
            rows=list(csv.DictReader((p/'trace.csv').open()))
            pair[variant]=rows
        if len(pair)!=2:continue
        name=f'{case}/r{n}'
        new=pair['index'];old=pair['old']
        frozen=[r for r in new if r['est_dsrc']!='warmup']
        warm=[r for r in new if int(r['step'])<100 and r['age']=='0' and float(r['its'])>0]
        phases=sorted({r['phase'] for r in warm},key=int)
        values={j:sorted(float(r['its']) for r in warm if r['phase']==j) for j in phases}
        expected={j:v[len(v)//2]-values['0'][len(values['0'])//2] for j,v in values.items()} if '0' in values else {}
        entry={'warmup_samples_by_phase':{j:len(v) for j,v in values.items()},
               'offsets_reconstructed_from_warmup':expected,
               'all_model_values_equal_raw_minus_q':all(float(r['model_its'])==float(r['its'])-float(r['q']) for r in new),
               'frozen_offsets_match_rule':all(float(r['q'])==expected.get(r['phase'],0.) for r in frozen),
               'unknown_phase_counts':{j:sum(r['phase']==j and r['phase_known']=='0' for r in frozen) for j in sorted({r['phase'] for r in frozen if r['phase_known']=='0'},key=int)}}
        a={r['step']:r for r in old};b={r['step']:r for r in new}
        keys=sorted(set(a)&set(b),key=int)
        different=[k for k in keys if a[k]['rebuild']!=b[k]['rebuild']]
        if different:
            first=different[0]
            entry['first_different_rebuild']={v:{k:r[k] for k in ['step','rebuild','heldBase','age','its','est','avg','rMed','est_dsrc']} for v,r in [('old',a[first]),('index',b[first])]}
            entry['all_raw_iterations_before_first_decision_difference_identical']=all(a[k]['its']==b[k]['its'] for k in keys if int(k)<int(first))
        else:entry['first_different_rebuild']=None
        if case=='Blankenbach':
            entry['all_phase_zero']=all(r['phase']=='0' and float(r['q'])==0 for r in new)
            for variant,rows in pair.items():
                target=R/'replay'/f'full_Blankenbach_r{n}_{variant}.tsv'
                target.write_text(''.join(f"{r['step']} 0 {r['its']} {r['build_ms']} {r['solve_ms']} {int(r['est_dsrc']=='forced_reset')} -1\n" for r in rows))
                p=subprocess.run([str(R/'replay/replay'),str(target),'zero'],text=True,capture_output=True)
                entry[f'{variant}_zero_replay']={'rc':p.returncode,'output':p.stdout.strip(),'stderr':p.stderr.strip()}
        diagnostics[name]=entry
(R/'phase_diagnostics.json').write_text(json.dumps(diagnostics,indent=2))
for k,v in diagnostics.items():
    print(k,'model OK',v['all_model_values_equal_raw_minus_q'],'offsets OK',v['frozen_offsets_match_rule'],'unknown',v['unknown_phase_counts'])
    if k.startswith('Blankenbach'):
        print(json.dumps(v,indent=2))
