#!/bin/bash
# 补实验：ILU(2) 在 b=100 冻结后【永不重建】，一次性拿到真实的大年龄曲线 N(a)。
# FREEZE_K 远大于总步数 ⇒ 周期性重建只在 b=100 发生一次。
set -e
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=2
export PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export PBR_PETSC_FREEZE_K=100000        # ⇒ b=100 之后永不重建
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/sbig
rm -rf $D && cp -r /root/autodl-tmp/PBR/damBreak_petsc $D
cd $D
for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

for REP in 1 2 3; do
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/sbig_r${REP}.csv
  rm -f "$PBR_PETSC_OUT"
  interFoam > log.big${REP} 2>&1
  st=$(grep -c '^Time = ' log.big${REP})
  et=$(grep -o 'ExecutionTime = [0-9.]* s' log.big${REP} | tail -1 | awk '{print $3}')
  echo "rep=$REP steps=$st et=${et}s"
done
echo BIG_DONE
