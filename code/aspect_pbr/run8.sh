#!/bin/bash
# Interleaved wallclock comparison, Blankenbach case 2a. External wall timing via python.
source /root/autodl-tmp/envs/dealenv.sh
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml
PY=/root/miniconda3/bin/python3
A=/root/autodl-tmp/envs/aspect-2.4
LEV=${LEV:-5}; ENDF=${ENDF:-0.04}; ROUNDS=${ROUNDS:-3}
W=/root/autodl-tmp/PBR/aspect_runs/cmp_l${LEV}
rm -rf $W && mkdir -p $W && cd $W
cp $A/benchmarks/blankenbach/base_case2a.prm base.prm
mkdir -p plugin && cp $A/build/benchmarks/blankenbach/plugin/libblankenbach.so plugin/
cp $A/benchmarks/blankenbach/initial_temperature_case2a.txt .
sed -i "s|set Initial global refinement          = 4|set Initial global refinement          = $LEV|" base.prm
printf 'set End time = %s\n' $ENDF >> base.prm
O=$W/results.tsv; : > $O
run_one () {
  r=$1; lbl=$2; shift 2
  d=$W/r${r}_${lbl}; mkdir -p $d; cd $d
  cp $W/base.prm case.prm
  ln -sfn $W/plugin plugin; ln -sfn $W/initial_temperature_case2a.txt .
  export "$@" PBR_LOG=$d/trace.csv
  $PY -c "
import subprocess,time,sys,os
t0=time.time()
p=subprocess.run(['$A/build-pbr/aspect','case.prm'],stdout=open('run.log','w'),stderr=subprocess.STDOUT)
w=time.time()-t0
open('run.log','a').write('External wall = %.3f EXIT=%d\n'%(w,p.returncode))
" 
  echo -e "$r\t$lbl\t$(grep -c '^\*\*\* Timestep' run.log)\t$(grep -c 'Rebuilding Stokes' run.log)\t$(grep -c 'Reusing Stokes' run.log)" >> $O
  echo "done r$r $lbl steps=$(grep -c '^\*\*\* Timestep' run.log) wall=$(grep 'External wall' run.log)"
}
for ((r=1;r<=ROUNDS;r++)); do
  run_one $r K1     PBR_POLICY=off
  run_one $r K5     PBR_POLICY=fixed PBR_K=5
  run_one $r K10    PBR_POLICY=fixed PBR_K=10
  run_one $r K25    PBR_POLICY=fixed PBR_K=25
  run_one $r NEVER  PBR_POLICY=fixed PBR_K=0
  run_one $r ONLINE PBR_POLICY=online PBR_BASE=100
done
echo DONE >> $O
