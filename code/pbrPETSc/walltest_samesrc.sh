#!/bin/bash
# ★★ 墙钟与内部计时【同源】实验（levels=10）
#
# 为什么要重做：
#   上一轮墙钟实验设了 PBR_PETSC_BENCH=0，导致内部计时来自【另一次运行】。
#   而 tPCSetup 是双峰的（机器状态），跨运行借用会引入偏差。
#   ⇒ 本实验同时打开 BENCH=1，使墙钟与内部计时出自【同一个进程】。
#
# 并且增加 K 的取值（1,2,3,5,8），以便对
#   wall = O + a·ΣtPCSetup + b·n_rebuild 做多元拟合，
#   从"每次重建的未计时开销"中把装配项分离出来。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/samesrc
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for R in 1 2 3; do
  for K in 1 2 3 5 8; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/ss_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT"
    S=$(date +%s%3N)
    interFoam > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.r${R}k${K} | tail -1 | awk '{print $3}')
    st=$(grep -c '^Time = ' log.r${R}k${K})
    echo "round=$R K=$K wall_ms=${wall} execTime=${et} steps=$st"
  done
done
echo "SAMSRC_DONE"
