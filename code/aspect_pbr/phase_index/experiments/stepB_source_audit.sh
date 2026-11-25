set -eu
export PATH=/root/miniconda3/bin:/usr/bin:/bin:$PATH
python3 - <<'PY'
from pathlib import Path
import hashlib,json,re
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
A=Path('/root/autodl-tmp/envs/aspect-2.4')
for name in ['solver.cc','assembly.cc']:
 p=R/'aspect_source/source/simulator'/name
 ls=p.read_text().splitlines()
 print('CALL SITES',name)
 for i,l in enumerate(ls):
  if any(x in l for x in ['PBR::decide','PBR::beginSolve']):
   print('\n'.join(f'{k+1}: {ls[k]}' for k in range(max(0,i-3),min(len(ls),i+5))))
checks={}
before=json.loads((R/'reference/build_pbr2_manifest.json').read_text())
after={str(p.relative_to(A/'build-pbr2')):{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in (A/'build-pbr2').rglob('*') if p.is_file()}
checks['build_pbr2_file_count']=len(before)
checks['build_pbr2_manifest_identical']=before==after
checks['build_pbr2_changed']=[p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
checks['original_binary_hashes']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in json.loads((R/'reference/binary_hashes.json').read_text()).items()}
checks['moose_backup_hashes']={p:hashlib.sha256(Path(v['backup']).read_bytes()).hexdigest()==v['sha256'] for p,v in json.loads((R/'moose_backup/manifest.json').read_text()).items()}
checks['original_aspect_sources_unchanged']={new:hashlib.sha256((A/new).read_bytes()).hexdigest()==hashlib.sha256((R/'reference'/old).read_bytes()).hexdigest() for new,old in [('include/aspect/pbr_policy.h','pbr_policy_legacy.h'),('source/simulator/assembly.cc','assembly.before.cc'),('source/simulator/solver.cc','solver.before.cc')]}
checks['full_input_hashes_identical_to_archived']={}
checks['moose_library_maps']={}
for p in (R/'full').glob('*/r*/metadata.json'):
 m=json.loads(p.read_text());source=Path(m['source_input_dir'])
 checks['full_input_hashes_identical_to_archived'][str(p.parent.relative_to(R))]={n:hashlib.sha256((source/n).read_bytes()).hexdigest()==h for n,h in m['inputs_sha256'].items()}
 result=p.with_name('result.json')
 if m['case']=='MOOSE' and result.exists():checks['moose_library_maps'][str(p.parent.relative_to(R))]=json.loads(result.read_text()).get('loaded_moose_libraries')
(R/'provenance_audit.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
print('TOSI BASE')
print((R/'full/C1/r1_index/Tosi_base.prm').read_text())
PY
