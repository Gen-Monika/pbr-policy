set -eu
export PATH=/root/miniconda3/bin:/usr/bin:/bin:$PATH
python3 - <<'PY'
from pathlib import Path
import hashlib,json,shutil,difflib
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
A=Path('/root/autodl-tmp/envs/aspect-2.4');M=Path('/root/autodl-tmp/envs/moose/src')
S=R/'aspect_source'
S.mkdir(exist_ok=False)
for p in A.iterdir():
 if p.name.startswith('build') or p.name=='.git':continue
 if p.is_dir():shutil.copytree(p,S/p.name,symlinks=True)
 else:shutil.copy2(p,S/p.name)
shutil.copy2(R/'code/pbr_policy.h',S/'include/aspect/pbr_policy.h')
p=S/'source/simulator/assembly.cc';old=p.read_text();needle=': PBR::state().solveGen) == false)'
assert old.count(needle)==1
new=old.replace(needle,': PBR::state().solveGen, static_cast<long>(nonlinear_iteration)) == false)')
p.write_text(new)
(R/'code/aspect_phase_index.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/source/simulator/assembly.cc',tofile='b/source/simulator/assembly.cc')))
# Back up every library copy/symlink and the executable before rebuilding MOOSE.
B=R/'moose_backup';B.mkdir(exist_ok=False)
items=list(M.glob('framework/**/libmoose-opt.so*'))+[M/'framework/src/systems/NonlinearSystem.C',M/'framework/include/utils/pbr_policy.h',M/'tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction/darcy_thermo_mech-opt']
manifest={}
for p in items:
 q=B/p.relative_to(M);q.parent.mkdir(parents=True,exist_ok=True)
 if p.is_symlink():q.symlink_to(p.readlink())
 else:shutil.copy2(p,q)
 manifest[str(p)]={'backup':str(q),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'symlink':str(p.readlink()) if p.is_symlink() else None}
(B/'manifest.json').write_text(json.dumps(manifest,indent=2))
p=M/'framework/src/systems/NonlinearSystem.C';old=p.read_text()
new=old.replace('PetscErrorCode PBRPreSolve(KSP ksp, Vec, Vec, void *)','PetscErrorCode PBRPreSolve(KSP ksp, Vec, Vec, void *ctx)')
needle='  int rb = aspect::PBR::decide(pbr_solve) ? 1 : 0;'
assert new.count(needle)==1
new=new.replace(needle,'  PetscInt j = 0;\n  if (aspect::PBR::state().condIndex)\n    PetscCall(SNESGetIterationNumber(static_cast<SNES>(ctx), &j));\n  int rb = aspect::PBR::decide(pbr_solve, static_cast<long>(j)) ? 1 : 0;')
new=new.replace('KSPSetPreSolve(ksp, PBRPreSolve, nullptr)','KSPSetPreSolve(ksp, PBRPreSolve, snes)')
p.write_text(new);shutil.copy2(R/'code/pbr_policy.h',M/'framework/include/utils/pbr_policy.h')
(R/'code/moose_phase_index.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/framework/src/systems/NonlinearSystem.C',tofile='b/framework/src/systems/NonlinearSystem.C')))
print('source prepared; MOOSE backups:',len(manifest))
PY
