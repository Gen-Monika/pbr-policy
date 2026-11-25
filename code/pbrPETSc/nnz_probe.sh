#!/bin/bash
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export PBR_PETSC_FREEZE_K=8
export PBR_PETSC_NNZ=1

D=/root/autodl-tmp/PBR/nnz
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1
for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

for LV in 0 1 2 3 5 8 10 12 15 18 20 25 30; do
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  rm -rf 0 && cp -r 0.orig 0
  blockMesh > log.bm 2>&1
  setFields > log.sf 2>&1
  export PBR_PETSC_LEVELS=$LV
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/nnz_lv${LV}.csv
  timeout 90 interFoam > log.lv${LV} 2>&1
  NNZ=$(grep -m1 "PBR_NNZ" log.lv${LV})
  TP=$(grep -m1 "PETSc ilu" log.lv${LV} | grep -o "t_pcsetup=[0-9.]*" | head -1)
  echo "LV=$LV | $NNZ | firstbuild $TP"
done
echo NNZ_DONE
