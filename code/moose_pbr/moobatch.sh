#!/bin/bash
# moobatch.sh : MOOSE darcy_thermo_mech step6a_coupled.i (official input, unchanged).
# 5 rounds; within a round all configs run concurrently (same machine, same load).
# Patched configs set MOOSE's own reuse switch with an unreachable threshold so that
# libMesh keeps one KSP object and never rebuilds by itself; the PBR hook decides.
B=/root/autodl-tmp/PBR/moose_cases
ST=$B/BATCH_STATUS
echo "start $(date)" > $ST
COMMON="Outputs/exodus=false"
KEEP="Executioner/reuse_preconditioner=true Executioner/reuse_preconditioner_max_linear_its=1000000"
run() { # label env... -- args...
  local L=$1; shift; local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
  env "${envs[@]}" PBR_LOG=$B/$L/pbr.csv /root/moorun.sh $L step6a_coupled.i $COMMON "$@" -log_view   # -log_view must be last: PETSc takes the next token as its viewer
}
for R in 1 2 3 4 5; do
  echo "round $R start $(date)" >> $ST
  run r${R}_orig        X=1 -- &
  run r${R}_moose25     X=1 -- Executioner/reuse_preconditioner=true &
  run r${R}_moose10     X=1 -- Executioner/reuse_preconditioner=true Executioner/reuse_preconditioner_max_linear_its=10 &
  run r${R}_moose50     X=1 -- Executioner/reuse_preconditioner=true Executioner/reuse_preconditioner_max_linear_its=50 &
  run r${R}_K1    PBR_POLICY=fixed PBR_K=1  -- $KEEP &
  run r${R}_K2    PBR_POLICY=fixed PBR_K=2  -- $KEEP &
  run r${R}_K3    PBR_POLICY=fixed PBR_K=3  -- $KEEP &
  run r${R}_K5    PBR_POLICY=fixed PBR_K=5  -- $KEEP &
  run r${R}_K10   PBR_POLICY=fixed PBR_K=10 -- $KEEP &
  run r${R}_never PBR_POLICY=fixed PBR_K=0  -- $KEEP &
  run r${R}_on100 PBR_POLICY=online PBR_BASE=100 -- $KEEP &
  run r${R}_on20  PBR_POLICY=online PBR_BASE=20  -- $KEEP &
  wait
  echo "round $R done $(date)" >> $ST
done
echo "ALL DONE $(date)" >> $ST
