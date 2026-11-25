set -eu
export PATH=/root/miniconda3/bin:/usr/bin:/bin:$PATH
python3 - <<'PY'
from pathlib import Path
import hashlib,json,shutil
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
R.mkdir(exist_ok=False)
(R/'reference').mkdir()
A=Path('/root/autodl-tmp/envs/aspect-2.4')
M=Path('/root/autodl-tmp/envs/moose/src')
files={'pbr_policy_legacy.h':A/'include/aspect/pbr_policy.h','assembly.before.cc':A/'source/simulator/assembly.cc','solver.before.cc':A/'source/simulator/solver.cc','NonlinearSystem.before.C':M/'framework/src/systems/NonlinearSystem.C','aspect_CMakeCache.txt':A/'build-pbr2/CMakeCache.txt'}
for name,p in files.items():shutil.copy2(p,R/'reference'/name)
manifest={str(p.relative_to(A/'build-pbr2')):{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in (A/'build-pbr2').rglob('*') if p.is_file()}
(R/'reference/build_pbr2_manifest.json').write_text(json.dumps(manifest,indent=2))
bins=[A/'build-pbr2/aspect']+list((A/'build-pbr2').glob('*.so*'))
(R/'reference/binary_hashes.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bins if p.is_file()},indent=2))
print('created',R,'protected build-pbr2 files',len(manifest))
PY
