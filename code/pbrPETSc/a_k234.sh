#!/bin/bash
# ★★★ 第二层：补 K=2 / K=4 的实测缺口（K*=3 的确认）
#
# ═══════════════════════════════════════════════════════════════════════
# 为什么要补
# ═══════════════════════════════════════════════════════════════════════
# 此前实测过的固定周期：
#   fx=[K1]  l15=[K1,K3]  l20=[K1,K3,K5]  fine=[K1,K3]
#   x3=[K1,K3]  fl30=[K1,K3,K5]  sth=[K6]
# ⇒ **K2 与 K4 从未在 C++ 里跑过。**
#
# 而模型说：
#   fx    K2=22870 < K3=23002   ← K2 才是最优！而 fx 从未测过 K2/K3
#   l15   K2=25223 vs K3=24400（差 3.4%）
#   fine  K2=70524 vs K3=66523（差 6.0%）
# ⇒ "K*=3" 这个结论【没有被实测确认过】。本脚本补上。
#
# ═══════════════════════════════════════════════════════════════════════
# ★ 计时口径（项目硬约束）
# ═══════════════════════════════════════════════════════════════════════
# 所有加速比实验必须在【同一机器、同一负载下交替跑，取重复测量中位数】，
# 不得跨轮比较总时间。
# ⇒ 即使 K1/K3/K5 已有历史数据，本脚本也【重新测一遍】，
#   让 K1..K5 全部落在同一批次内、同轮交错，才可互相比较。
#
# 用法：
#   NAME=fx MODES="K1 K2 K3 K4 K5" NROUND=3 TAG=k2fx bash a_k234.sh
#   或一次跑全部：bash a_k234_all.sh
#
# ⚠️ 固定周期组必须同时设 FREEZE_AT（否则走快照生成分支，退化为 K=1）
# ⚠️ 不用 set -e（OpenFOAM bashrc 末条命令返回 1）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

P=/root/autodl-tmp/PBR
NAME=${NAME:?必须给 NAME}

case "$NAME" in
  fx)   LVLD=10 SRC=$P/fixed    SOLV=interFoam DEF_B0=100 ;;
  l15)  LVLD=15 SRC=$P/l15      SOLV=interFoam DEF_B0=100 ;;
  l20)  LVLD=20 SRC=$P/l20      SOLV=interFoam DEF_B0=100 ;;
  fine) LVLD=20 SRC=$P/finerun  SOLV=interFoam DEF_B0=100 ;;
  x3)   LVLD=20 SRC=$P/x3run    SOLV=interFoam DEF_B0=100 ;;
  fl30) LVLD=30 SRC=$P/fl30run  SOLV=interFoam DEF_B0=100 ;;
  sth)  LVLD=5  SRC=$P/stefan   SOLV=interCondensatingEvaporatingFoam DEF_B0=50 ;;
  *) echo "未知 NAME=$NAME"; exit 1 ;;
esac
LEVELS=${LEVELS:-$LVLD}
BASE=${BASE:-$DEF_B0}
SOLVER=${SOLVER:-$SOLV}
NROUND=${NROUND:-3}
MODES=${MODES:-"K1 K2 K3 K4 K5"}
TAG=${TAG:-k234$NAME}
D=$P/${TAG}_case
STORE=$P/${TAG}_store

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D"; cd "$D" || exit 1
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

echo "=== $TAG/$NAME 开始 $(date '+%F %T')  MODES=[$MODES] NROUND=$NROUND LEVELS=$LEVELS BASE=$BASE SOLVER=$SOLVER ==="
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
    K=${MODE#K}
    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=$BASE PBR_PETSC_FREEZE_K=$K
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
    echo "round=$R mode=$MODE K=$K wall_ms=$((E-S)) execTime=$et iters=$iters nsteps=$nsteps rbsteps=$rbsteps fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
  done
done
echo "=== $TAG 结束 $(date '+%F %T') ==="
echo "${TAG}_DONE"
