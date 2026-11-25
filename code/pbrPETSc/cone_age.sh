#!/bin/bash
# movingCone 老化检查（只看迭代数与重建次数，确定性量，不计时）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH; export OMP_NUM_THREADS=1
P=/root/autodl-tmp/PBR/cand; W=$P/cone_age; rm -rf $W; cp -r $P/cone $W; cd $W
for e in p pFinal; do foamDictionary system/fvSolution -entry solvers.$e.solver -set PBRPCG >/dev/null; foamDictionary system/fvSolution -entry solvers.$e.preconditioner -set PETScILU >/dev/null; done
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" >/dev/null
foamDictionary system/controlDict -entry writeInterval -set 100000 >/dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
cp -r constant/polyMesh /tmp/cone_age_poly
export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8 PBR_PETSC_STORE=$W/store; mkdir -p store
for L in 10 20; do for M in K1 K7 NEVER ON; do
  rm -rf 0.* [1-9]* store/*.bin constant/polyMesh; cp -r /tmp/cone_age_poly constant/polyMesh
  unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_BASE PBR_PETSC_ONLINE_POLICY PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
  export PBR_PETSC_LEVELS=$L PBR_PETSC_OUT=$W/pc_${L}_${M}.csv; rm -f $PBR_PETSC_OUT
  case $M in
    K1)    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=20 PBR_PETSC_FREEZE_K=1 ;;
    K7)    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=20 PBR_PETSC_FREEZE_K=7 ;;
    NEVER) export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=20 PBR_PETSC_FREEZE_K=100000 ;;
    ON)    export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=20 PBR_PETSC_ONLINE_POLICY=online PBR_PETSC_ONLINE_RCOST=step PBR_PETSC_ONLINE_LVL=last PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
  esac
  pimpleFoam > log.$L.$M 2>&1
  it=$(awk '/Solving for p,/{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14)} END{print s}' log.$L.$M)
  rb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT 2>/dev/null)
  last=$(awk '/Solving for p,/{match($0,/No Iterations [0-9]+/); print substr($0,RSTART+14,RLENGTH-14)}' log.$L.$M | tail -40 | tr '\n' ' ')
  echo "L=$L mode=$M iters=$it rbsteps=$rb fatal=$(grep -c 'FOAM FATAL' log.$L.$M) tail40=[$last]"
done; done; echo CONE_AGE_DONE
