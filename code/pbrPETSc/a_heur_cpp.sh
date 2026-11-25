#!/bin/bash
# ★★★ 启发式对照的 C++ 实测（第三优先）
#
# 目的：把论文 §7.5/§7.6 的启发式对照从"表上评估"升级为"C++ 实测"。
#
# 四条规则（均由 C++ 直接实现，见 PETScPreconditioner.C 的 PBR_PETSC_ONLINE_POLICY）：
#   online   : 本文策略（当前阈值的代价比较）
#   chalmers : N_prev > max(2·k0, 10)
#   reac     : N_prev > reac
#   ratio    : (N_prev − k0)/k0 > frac
#
# ★ 因果性与既有运行一致：先用 ONLs 的完整环境（DMODE=extrap DMINN=1 RCOST=solve）
#   跑一遍作为回归对照，确认与 a2<tag>_pc_ONLs_r* 逐位相同；
#   再跑三条启发式。
#
# 用法：TAG=fx SRC=fixed LVLD=10 bash a_heur_cpp.sh
#
# ⚠️ 不用 set -e（OpenFOAM bashrc 末条命令返回 1）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

P=/root/autodl-tmp/PBR
TAG=${TAG:?必须给 TAG}
SRC=${SRC:?必须给 SRC}
LEVELS=${LEVELS:-$LVLD}
NROUND=${NROUND:-3}
REAC=${REAC:-120}
FRAC=${FRAC:-0.20}
POLS=${POLS:-"ONLc ONLch ONLre ONLra"}   # 回归 + 三条启发式
D=$P/${TAG}_heur_case
STORE=$P/${TAG}_heur_store

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

export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=$LEVELS
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

echo "=== $TAG 启发式实测开始 $(date '+%F %T')  POLS=[$POLS] NROUND=$NROUND LEVELS=$LEVELS REAC=$REAC FRAC=$FRAC ==="
for R in $(seq 1 $NROUND); do
  for POL in $POLS; do
    clean_times; rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1; setFields > log.sf 2>&1

    # ---- 清空所有环境（避免跨轮污染）
    unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL
    unset PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN PBR_PETSC_ONLINE_POLICY
    unset PBR_PETSC_ONLINE_REAC PBR_PETSC_ONLINE_FRAC PBR_PETSC_ONLINE_FACTOR PBR_PETSC_ONLINE_FLOOR
    unset PBR_PETSC_ONLINE_OUT PBR_PETSC_OUT
    unset PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin

    case $POL in
      ONLc)  # 回归对照：与既有 ONLs 完全相同的设置
             export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100
             export PBR_PETSC_ONLINE_POLICY=online
             export PBR_PETSC_ONLINE_RCOST=solve PBR_PETSC_ONLINE_LVL=last
             export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
      ONLch) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100
             export PBR_PETSC_ONLINE_POLICY=chalmers ;;
      ONLre) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100
             export PBR_PETSC_ONLINE_POLICY=reac PBR_PETSC_ONLINE_REAC=$REAC ;;
      ONLra) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100
             export PBR_PETSC_ONLINE_POLICY=ratio PBR_PETSC_ONLINE_FRAC=$FRAC ;;
    esac

    # ★ 两个日志都要设：pc 主日志（含 reusedFrom，用于数重建步）
    #   与在线决策日志（含 est/avg/dm，用于诊断）
    export PBR_PETSC_OUT=$P/${TAG}_heur_pc_${POL}_r${R}.csv
    export PBR_PETSC_ONLINE_OUT=$P/${TAG}_heur_onl_${POL}_r${R}.csv
    export PBR_PETSC_STORE=$STORE
    rm -f $PBR_PETSC_OUT $PBR_PETSC_ONLINE_OUT

    S=$(date +%s%3N)
    timeout 7200 interFoam > log.${POL}.r${R} 2>&1
    E=$(date +%s%3N)

    it=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14)} END{print s+0}' log.${POL}.r${R})
    st=$(grep -c "^Time = " log.${POL}.r${R})
    rb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT 2>/dev/null)
    fatal=$(grep -c "FOAM FATAL" log.${POL}.r${R})
    echo "round=$R pol=$POL wall_ms=$((E-S)) iters=$it steps=$st rebuild_steps=$rb fatal=$fatal"
  done
done
echo "=== $TAG 启发式实测结束 $(date '+%F %T') ==="
echo "${TAG}_HEUR_DONE"
