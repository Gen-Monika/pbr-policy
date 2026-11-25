#!/bin/bash
# A2 补跑：K1 与 K3 两组（修正 FREEZE_AT 后）
# ONL 组已在 a2_l20.log 中有效，此处只补对照组。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=20
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

NROUND=${NROUND:-5}
TAG=a2b
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

echo "=== A2b 开始  $(date) ==="

for R in $(seq 1 $NROUND); do
  for MODE in K1 K3; do
    clean_times
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1

    unset PBR_PETSC_ONLINE PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin

    export PBR_PETSC_FREEZE_AT=1
    export PBR_PETSC_FREEZE_BASE=100
    if [ "$MODE" = "K1" ]; then export PBR_PETSC_FREEZE_K=1; else export PBR_PETSC_FREEZE_K=3; fi

    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT

    S=$(date +%s%3N)
    interFoam > log.${MODE}.r${R} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.${MODE}.r${R} 2>/dev/null | tail -1 | awk '{print $3}')
    nrb=$(awk -F, 'NR>1 && $9==0 {n++} END{print n+0}' $PBR_PETSC_OUT 2>/dev/null)
    echo "round=$R mode=$MODE wall_ms=$wall execTime=$et nrebuild=$nrb"
  done
done
echo "=== A2b 结束  $(date) ==="
echo A2B_DONE
