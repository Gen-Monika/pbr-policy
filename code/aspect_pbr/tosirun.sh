#!/bin/bash
# tosirun.sh <case N> <label> <end time> [env assignments...]
source /root/autodl-tmp/envs/dealenv.sh
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml
A=/root/autodl-tmp/envs/aspect-2.4
C=$1; L=$2; ET=$3; shift 3
W=/root/autodl-tmp/PBR/aspect_runs/tosi/C${C}_${L}
rm -rf $W && mkdir -p $W && cd $W
cp $A/benchmarks/tosi_et_al_2015_gcubed/Tosi_base.prm $A/benchmarks/tosi_et_al_2015_gcubed/Tosi_Case${C}.prm .
cp $A/build/benchmarks/tosi/libtosi_benchmark.so .
sed -i "s|^set End time .*|set End time = $ET|" Tosi_base.prm
export "$@" PBR_LOG=$W/trace.csv
/root/miniconda3/bin/python3 -c "
import subprocess,time
t0=time.time()
p=subprocess.run(['$A/build-pbr/aspect','Tosi_Case${C}.prm'],stdout=open('run.log','w'),stderr=subprocess.STDOUT)
open('run.log','a').write('External wall = %.3f EXIT=%d\n'%(time.time()-t0,p.returncode))
"
