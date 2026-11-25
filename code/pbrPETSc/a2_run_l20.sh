#!/bin/bash
# ★★★ A2：在线策略的实机墙钟对照（l20，levels=20，ILU）
#
# 对照三组（同机器、同负载、交错）：
#   K=1  —— 每步重建（"永不复用"基线）
#   K=3  —— l20 的离线最优固定周期（调优后的基线）
#   ONL  —— 本文在线策略（严格因果，只用 t 之前的信息）
#
# 交错协议：每一轮内按 K=1 → K=3 → ONL 顺序各跑一次，跑多轮后取中位。
# 这样组间漂移（服务器负载起伏）落到所有组上，不会偏袒任一方。
#
# 关键口径：
#   - wall_ms        : 端到端墙钟（date +%s%3N 夹住 interFoam）
#   - ExecutionTime  : OpenFOAM 自报的求解时间
#   - cost_model     : Σ迭代数 + 重建次数 × r  （模型口径，用于与离线对照）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=20
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

NROUND=${NROUND:-5}
TAG=${TAG:-a2l20}
D=/root/autodl-tmp/PBR/${TAG}_case
STORE=/root/autodl-tmp/PBR/${TAG}_store

rm -rf "$D" "$STORE"
mkdir -p "$STORE"
cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG
foamDictionary system/controlDict -entry libs \
  -set "(libpbrSolverTimer.so libpbrPETSc.so)"
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

echo "=== A2 开始  $(date) ==="
echo "endTime=$(foamDictionary -entry endTime -value system/controlDict)  NROUND=$NROUND"

for R in $(seq 1 $NROUND); do
  for MODE in K1 K3 ONL; do
    clean_times
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1

    unset PBR_PETSC_ONLINE PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin

    case $MODE in
      K1)
        export PBR_PETSC_FREEZE_AT=1
        export PBR_PETSC_FREEZE_K=1
        export PBR_PETSC_FREEZE_BASE=100
        ;;
      K3)
        # ★ 必须同时给 FREEZE_AT：代码用 freezeAt_ < 0 判定"快照生成 pass"，
        #   只给 FREEZE_K 会让每步都走生成分支 => 退化成 K=1（已踩过）。
        export PBR_PETSC_FREEZE_AT=1
        export PBR_PETSC_FREEZE_K=3
        export PBR_PETSC_FREEZE_BASE=100
        ;;
      ONL)
        export PBR_PETSC_ONLINE=1
        export PBR_PETSC_ONLINE_BASE=100
        export PBR_PETSC_ONLINE_OUT=/root/autodl-tmp/PBR/${TAG}_onl_r${R}.csv
        rm -f $PBR_PETSC_ONLINE_OUT
        ;;
    esac

    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT

    S=$(date +%s%3N)
    interFoam > log.${MODE}.r${R} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.${MODE}.r${R} 2>/dev/null | tail -1 | awk '{print $3}')
    iters=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/); print substr($0,RSTART+14,RLENGTH-14)}' log.${MODE}.r${R} 2>/dev/null | paste -sd+ | bc)
    nsteps=$(grep -c "^Time = " log.${MODE}.r${R} 2>/dev/null)
    echo "round=$R mode=$MODE wall_ms=$wall execTime=$et iters=$iters nsteps=$nsteps"
  done
done
echo "=== A2 结束  $(date) ==="
echo A2_DONE
