#!/bin/bash
# ★★★ A2（修正版）：在线策略实机墙钟对照
#
# 组（同机器、同负载、每轮内交错，多轮取中位）：
#   K1    每步重建
#   K3    旧口径下的离线最优周期
#   K5    墙钟最优周期（criterion_accuracy 实测 l20：K5 17.60 s < K3 18.57 s）
#   ONLs  在线策略，重建代价 = r          （A1c 口径，离线已验证的那个策略）
#   ONLp  在线策略，重建代价 = 实测每步分解次数 × r（修正口径）
#
# 用法：MODES="K1 K3 K5 ONLs ONLp" NROUND=5 TAG=a2c LVL=last bash a2_run_v2.sh
#
# ⚠️ 固定周期组必须同时设 FREEZE_AT（否则走"快照生成"分支，退化为 K=1，已踩过）
# ⚠️ 不用 set -e；foamDictionary 后须重导 LD_LIBRARY_PATH；后台用 setsid nohup
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=${LEVELS:-20}
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

NROUND=${NROUND:-5}
MODES=${MODES:-"K1 K3 K5 ONLs ONLp"}
TAG=${TAG:-a2c}
LVL=${LVL:-last}
SRC=${SRC:-/root/autodl-tmp/PBR/damBreak_petsc}
P=/root/autodl-tmp/PBR
D=$P/${TAG}_case
STORE=$P/${TAG}_store

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D"; cd "$D" || exit 1

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

echo "=== $TAG 开始 $(date '+%F %T')  MODES=[$MODES] NROUND=$NROUND LEVELS=$PBR_PETSC_LEVELS LVL=$LVL SRC=$SRC ==="
for R in $(seq 1 $NROUND); do
  for MODE in $MODES; do
    clean_times; rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1; setFields > log.sf 2>&1
    unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_OUT
    unset PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN
    unset PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin
    case $MODE in
      K*)   export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=100 PBR_PETSC_FREEZE_K=${MODE#K} ;;
      # ★ 回归对照：ONLs/ONLp 显式钉死 DMODE=extrap，等价于修复前的行为。
      #   若它们逐位复现旧结果，说明新代码没有改变默认路径。
      ONLs) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100 PBR_PETSC_ONLINE_RCOST=solve PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
      ONLp) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100 PBR_PETSC_ONLINE_RCOST=step  PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
      # ★ 修复变体：flat 取值（不外推）+ 最小样本数 3（挡掉单样本自锁）
      ONLf) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100 PBR_PETSC_ONLINE_RCOST=solve PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=flat PBR_PETSC_ONLINE_DMINN=${DMINN:-3} ;;
    esac
    [ -n "$PBR_PETSC_ONLINE" ] && export PBR_PETSC_ONLINE_OUT=$P/${TAG}_onl_${MODE}_r${R}.csv && rm -f $PBR_PETSC_ONLINE_OUT
    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=$P/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=$P/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT
    S=$(date +%s%3N)
    interFoam > log.${MODE}.r${R} 2>&1
    E=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.${MODE}.r${R} | tail -1 | awk '{print $3}')
    iters=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14)} END{print s+0}' log.${MODE}.r${R})
    nsteps=$(grep -c "^Time = " log.${MODE}.r${R})
    rbsteps=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT)
    fatal=$(grep -c "FOAM FATAL" log.${MODE}.r${R})
    echo "round=$R mode=$MODE wall_ms=$((E-S)) execTime=$et iters=$iters nsteps=$nsteps rbsteps=$rbsteps fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
  done
done
echo "=== $TAG 结束 $(date '+%F %T') ==="
echo "${TAG}_DONE"
