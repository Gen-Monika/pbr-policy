"""Final read-only audits and an explicit, credential-free review bundle."""
from pathlib import Path
import csv,hashlib,json,os,re,subprocess,tarfile,time
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
assert (R/'full_done').exists(), 'Full batch is unfinished'
full=json.loads((R/'full_results.json').read_text())
assert len(full)==40 and all(v['rc']==0 and v['guard'] is None for v in full)
for script in ['stepB_analyze.py','stepB_summary.py','stepB_diagnostics.py',
               'stepB_convergence_audit.py','stepB_phase_join.py','stepB_c4_window_audit.py']:
    proc=subprocess.run(['/root/miniconda3/bin/python',str(R/script)],capture_output=True,text=True)
    (R/(script+'.final.log')).write_text(proc.stdout+proc.stderr)
    assert proc.returncode==0,(script,proc.stderr)
subprocess.run(['bash',str(R/'stepB_source_audit.sh')],stdout=(R/'provenance_audit.log').open('w'),check=True)
prov=json.loads((R/'provenance_audit.json').read_text())
assert prov['build_pbr2_manifest_identical']
assert all(prov['original_binary_hashes'].values())
assert all(prov['original_aspect_sources_unchanged'].values())
assert all(prov['moose_backup_hashes'].values())
assert all(all(x.values()) for x in prov['full_input_hashes_identical_to_archived'].values())
for name,libs in prov['moose_library_maps'].items():
    expected=str(R/'moose_backup/framework/libmoose-opt.so.0.0.0') if name.endswith('_old') else '/root/autodl-tmp/envs/moose/src/framework/libmoose-opt.so.0.0.0'
    assert libs==[expected],(name,libs,expected)
assert len(prov['moose_library_maps'])==10
active=[]
for p in (R/'full').glob('*/r*/pid'):
    pid=int(p.read_text());proc=Path(f'/proc/{pid}')
    if proc.exists():
        cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        if 'aspect' in cmd or 'darcy_thermo_mech' in cmd:active.append({'pid':pid,'cmd':cmd})
assert not active, active
sources={
    'prepared_header':R/'code/pbr_policy.h',
    'aspect_header':R/'aspect_source/include/aspect/pbr_policy.h',
    'moose_header':Path('/root/autodl-tmp/envs/moose/src/framework/include/utils/pbr_policy.h'),
}
hashes={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in sources.items()}
assert len(set(hashes.values()))==1
summary={'completed_runs':len(full),'all_rc_zero':True,'all_guards_clear':True,
         'max_process_rss_bytes':max(v['peak_rss_bytes'] for v in full),
         'longest_run_seconds':max(v['wall_seconds'] for v in full),
         'batch_elapsed_seconds':max(v['end_epoch'] for v in full)-min(v['start_epoch'] for v in full),
         'current_cgroup_memory_bytes':int(Path('/sys/fs/cgroup/memory.current').read_text()),
         'active_solver_processes':active,'header_hashes':hashes,'completed_at':time.strftime('%F %T')}
(R/'final_validation.json').write_text(json.dumps(summary,indent=2))

# Only explicit scientific output, metadata, inputs, code and reference files.
# No environment dump, source checkout, backup library or authentication file.
names=['metrics_plan.json','analysis_correction.json','analysis.json','paired_summary.json',
       'phase_diagnostics.json','convergence_audit.json','phase_join_audit.json',
       'phase_drift_audit.json','c4_window_audit.json','moose_count_audit.json',
       'moose_history_count_audit.json','provenance_audit.json','final_validation.json',
       'full_results.json','regression_results.json','build_results.json',
       'stepB_replay_validation.json','full.log','regression.log','build_controller.log',
       'build_aspect.log','build_moose.log','full_done','regression_done','build_done']
files=[R/n for n in names if (R/n).is_file()]
files+=list(R.glob('stepB_*.py'))+list(R.glob('stepB_*.sh'))+list(R.glob('round*_preflight.json'))
files+=[p for p in (R/'code').rglob('*') if p.is_file() and p.suffix in ['.h','.cpp','.diff','.md','.py','.sh','.json']]
files+=list((R/'reference').glob('*.json'))+list((R/'replay').glob('*.tsv'))+list((R/'replay').glob('*.json'))
for group in ['regression','full']:
    for run in (R/group).glob('*/r*'):
        files += [run/n for n in ['run.log','trace.csv','metadata.json','result.json'] if (run/n).is_file()]
        files += list(run.glob('*.prm'))+list(run.glob('*.i'))
files=sorted(set(files))
manifest={str(p.relative_to(R)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
(R/'review_bundle_manifest.json').write_text(json.dumps(manifest,indent=2))
archive=R/'stepB_review_bundle.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for p in files+[R/'review_bundle_manifest.json']:tar.add(p,arcname=str(p.relative_to(R)),recursive=False)
print(json.dumps(summary,indent=2))
print('bundle_files',len(files),'compressed_bytes',archive.stat().st_size,'sha256',hashlib.sha256(archive.read_bytes()).hexdigest())
