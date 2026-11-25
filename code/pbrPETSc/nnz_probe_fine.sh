#!/bin/bash
# fine 网格（9072 单元）上的填充度探针：找 r 衰减点
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=100 PBR_PETSC_FREEZE_K=8
export PBR_PETSC_NNZ=1

D=/root/autodl-tmp/PBR/nnz_fine
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1
for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -f log.*
# 网格加密 2 倍
/root/miniconda3/bin/python - << "PYEOF"
p = "/root/autodl-tmp/PBR/nnz_fine/system/blockMeshDict"
s = open(p).read()
old = """    hex (0 1 5 4 12 13 17 16) (23 8 1) simpleGrading (1 1 1)
    hex (2 3 7 6 14 15 19 18) (19 8 1) simpleGrading (1 1 1)
    hex (4 5 9 8 16 17 21 20) (23 42 1) simpleGrading (1 1 1)
    hex (5 6 10 9 17 18 22 21) (4 42 1) simpleGrading (1 1 1)
    hex (6 7 11 10 18 19 23 22) (19 42 1) simpleGrading (1 1 1)"""
new = """    hex (0 1 5 4 12 13 17 16) (46 16 1) simpleGrading (1 1 1)
    hex (2 3 7 6 14 15 19 18) (38 16 1) simpleGrading (1 1 1)
    hex (4 5 9 8 16 17 21 20) (46 84 1) simpleGrading (1 1 1)
    hex (5 6 10 9 17 18 22 21) (8 84 1) simpleGrading (1 1 1)
    hex (6 7 11 10 18 19 23 22) (38 84 1) simpleGrading (1 1 1)"""
assert old in s
open(p, "w").write(s.replace(old, new))
PYEOF
rm -rf 0 constant/polyMesh && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

for LV in 5 8 10 12 15 18 20 25 30; do
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  rm -rf 0 && cp -r 0.orig 0
  blockMesh > log.bm 2>&1
  setFields > log.sf 2>&1
  export PBR_PETSC_LEVELS=$LV
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/nnzf_lv${LV}.csv
  timeout 120 interFoam > log.lv${LV} 2>&1
  echo "LV=$LV | $(grep -m1 PBR_NNZ log.lv${LV})"
done
echo NNZF_DONE
