#!/bin/bash
# ★★★ A2-any：任意配置的 C++ 在线验证（第一层的通用版）
#
# 与 a2_run_sth.sh 的区别：把 SRC / SOLVER / LEVELS / BASE / 起始目录处理
# 全部参数化，用 NAME 一次选定。全部取值照搬 a_phase_scan.sh（已验证）。
#
# 用法：NAME=fx  MODES="ONLs" NROUND=3 TAG=a2fx  bash a2_run_any.sh
#       NAME=fine MODES="ONLs" NROUND=3 TAG=a2fine bash a2_run_any.sh
#
# ⚠️ 不用 set -e（OpenFOAM 的 bashrc 末条命令返回 1）
# ⚠️ 固定周期组必须同时设 FREEZE_AT（否则退化为 K=1，已踩过）
# ⚠️ 只用 SETSID NOHUP 后台跑，且 stdin 接 /dev/null
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

P=/root/autodl-tmp/PBR
NAME=${NAME:?必须给 NAME}

# ★ 每个配置的源 / 求解器 / levels / B0（与 a_phase_scan.sh 逐字一致）
case "$NAME" in
  fx)   LVLD=10 SRC=$P/fixed    SOLV=interFoam DEF_B0=100 ;;
  l15)  LVLD=15 SRC=$P/l15      SOLV=interFoam DEF_B0=100 ;;
  l20)  LVLD=20 SRC=$P/l20      SOLV=interFoam DEF_B0=100 ;;
  fine) LVLD=20 SRC=$P/finerun  SOLV=interFoam DEF_B0=100 ;;
  x3)   LVLD=20 SRC=$P/x3run    SOLV=interFoam DEF_B0=100 ;;
  fl30) LVLD=30 SRC=$P/fl30run  SOLV=interFoam DEF_B0=100 ;;
  sth)  LVLD=5  SRC=$P/stefan   SOLV=interCondensatingEvaporatingFoam DEF_B0=100 ;;
  *) echo "未知 NAME=$NAME"; exit 1 ;;
esac
LEVELS=${LEVELS:-$LVLD}
BASE=${BASE:-$DEF_B0}
SOLVER=${SOLVER:-$SOLV}
NROUND=${NROUND:-3}
MODES=${MODES:-"ONLs"}
TAG=${TAG:-a2$NAME}
LVL=${LVL:-last}
D=$P/${TAG}_case
STORE=$P/${TAG}_store

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D"; cd "$D" || exit 1

# sth 的 endTime 固定为 20（源里可能是 100，是长批次残留）
if [ "$NAME" = "sth" ]; then
  foamDictionary system/controlDict -entry endTime -set 20 > /dev/null 2>&1
fi

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|1.36|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=$LEVELS
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

echo "=== $TAG/$NAME 开始 $(date '+%F %T')  MODES=[$MODES] NROUND=$NROUND LEVELS=$LEVELS BASE=$BASE SOLVER=$SOLVER SRC=$SRC ==="
for R in $(seq 1 $NROUND); do
  for MODE in $MODES; do
    clean_times
    if [ "$NAME" = "sth" ]; then
      rm -rf 1.36; cp -rf 0 1.36; setAlphaField > log.sf 2>&1
    else
      rm -rf 0 && cp -r 0.orig 0
      blockMesh > log.bm 2>&1; setFields > log.sf 2>&1
    fi

    unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_OUT
    unset PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN
    unset PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin
    case $MODE in
      K*)   export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=$BASE PBR_PETSC_FREEZE_K=${MODE#K} ;;
      ONLs) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=$BASE PBR_PETSC_ONLINE_RCOST=solve PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
      ONLp) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=$BASE PBR_PETSC_ONLINE_RCOST=step  PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
    esac
    [ -n "$PBR_PETSC_ONLINE" ] && export PBR_PETSC_ONLINE_OUT=$P/${TAG}_onl_${MODE}_r${R}.csv && rm -f $PBR_PETSC_ONLINE_OUT
    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=$P/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=$P/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT
    S=$(date +%s%3N)
    timeout 7200 $SOLVER > log.${MODE}.r${R} 2>&1
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
