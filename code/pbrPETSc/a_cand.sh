#!/bin/bash
# 候选算例判据 1：官方默认 p 求解器 vs DIC-PCG vs PETSc ILU(k)（K1 每步重建 / ONLp 本文在线）
# 只替换压力方程（p 或 p_rgh 及其 Final）的 solver/preconditioner，容差沿用官方原值
# 用法：CASE=slosh PF=p_rgh APP=interFoam LEVELS="10 20" NROUND=3 bash a_cand.sh
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH; export OMP_NUM_THREADS=1
P=/root/autodl-tmp/PBR/cand; CASE=${CASE:?}; PF=${PF:?}; APP=${APP:?}
LEVELS=${LEVELS:-"10 20"}; NROUND=${NROUND:-3}; ENDT=${ENDT:-}
MODES=${MODES:-"DEF DIC $(for l in $LEVELS; do echo -n "I${l}K1 I${l}ON "; done)"}
W=$P/${CASE}_run; rm -rf $W; cp -r $P/$CASE $W; cd $W || exit 1
cp system/fvSolution system/fvSolution.orig; cp system/controlDict system/controlDict.orig
[ -n "$ENDT" ] && foamDictionary system/controlDict.orig -entry endTime -set $ENDT > /dev/null
foamDictionary system/controlDict.orig -entry writeInterval -set 100000 > /dev/null 2>&1
mesh0=$(ls -d constant/polyMesh); cp -r constant/polyMesh /tmp/${CASE}_poly0
setup(){ # $1 = def|dic|pbr
  cp system/fvSolution.orig system/fvSolution; cp system/controlDict.orig system/controlDict
  for e in $PF ${PF}Final; do
    case $1 in
      dic) foamDictionary system/fvSolution -entry solvers.$e.solver -set PCG >/dev/null
           foamDictionary system/fvSolution -entry solvers.$e.preconditioner -set DIC >/dev/null ;;
      pbr) foamDictionary system/fvSolution -entry solvers.$e.solver -set PBRPCG >/dev/null
           foamDictionary system/fvSolution -entry solvers.$e.preconditioner -set PETScILU >/dev/null ;;
    esac
  done
  [ $1 = pbr ] && foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" >/dev/null
  export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
}
reset_case(){ for d in */; do d=${d%/}; case "$d" in 0|0.orig|system|constant) continue;; esac
  [[ "$d" =~ ^[0-9.e+-]+$ ]] && rm -rf -- "$d"; done
  rm -rf constant/polyMesh; cp -r /tmp/${CASE}_poly0 constant/polyMesh
  if [ -d 0.orig ]; then rm -rf 0 && cp -r 0.orig 0; [ -f system/setFieldsDict ] && setFields > log.sf 2>&1; fi; }
echo "=== $CASE start $(date '+%F %T') MODES=[$MODES] NROUND=$NROUND ==="
for R in $(seq 1 $NROUND); do for M in $MODES; do
  reset_case
  unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_BASE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_POLICY PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE PBR_PETSC_OUT
  case $M in
    DEF) setup def ;;  DIC) setup dic ;;
    I*K1) setup pbr; L=${M#I}; L=${L%K1}; export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=$L PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8 ;;
    I*ON) setup pbr; L=${M#I}; L=${L%ON}; export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=$L PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8 \
            PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=20 PBR_PETSC_ONLINE_POLICY=online PBR_PETSC_ONLINE_RCOST=step \
            PBR_PETSC_ONLINE_LVL=last PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 PBR_PETSC_STORE=$W/store
          mkdir -p $W/store; rm -f $W/store/*.bin ;;
  esac
  timeout 5400 $APP > log.$M.r$R 2>&1
  et=$(grep -o "ExecutionTime = [0-9.]* s" log.$M.r$R | tail -1 | awk '{print $3}')
  st=$(grep -c "^Time = " log.$M.r$R)
  it=$(awk -v f="$PF" '$0 ~ "Solving for "f","{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14); n++} END{print s+0, n+0}' log.$M.r$R)
  fatal=$(grep -c "FOAM FATAL" log.$M.r$R)
  echo "round=$R mode=$M execTime=$et steps=$st iters_solves=${it// /_} fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
done; done
echo "=== $CASE end $(date '+%F %T') ==="; echo "${CASE}_DONE"
