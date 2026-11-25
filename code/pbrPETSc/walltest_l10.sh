#!/bin/bash
# ★★ levels=10 严格交错墙钟实验（毫秒级计时）
#
# 为什么重做：
#   此前 levels=5 的墙钟用 `date +%s`，分辨率 1 秒，而总时长仅 11–12 秒
#   ⇒ 相对分辨率 ~8%，与待测效应同量级 ⇒ 不足以判定。
#
# 本次改进：
#   1. 用 date +%s%3N 取毫秒
#   2. levels=10 的 tPCSetup 达 8516 µs，占比应显著更高
#   3. 严格交错：每轮内轮流跑 K=1/2/3，重复 6 轮，取中位
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=0
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/l10wt
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for R in 1 2 3 4 5 6; do
  for K in 1 2 3; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l10wt_k${K}_r${R}.csv
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
echo "L10WALL_DONE"
