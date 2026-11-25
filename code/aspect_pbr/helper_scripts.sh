#!/bin/bash
# Blankenbach case 2a runner: ssrun.sh <label> <refinement> [extra prm file]
source /root/autodl-tmp/envs/dealenv.sh
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml
A=/root/autodl-tmp/envs/aspect-2.4
LBL=$1; LEV=$2
R=/root/autodl-tmp/PBR/aspect_runs/$LBL
rm -rf $R && mkdir -p $R && cd $R
cp $A/benchmarks/blankenbach/base_case2a.prm case.prm
mkdir -p plugin && cp $A/build/benchmarks/blankenbach/plugin/libblankenbach.so plugin/
cp $A/benchmarks/blankenbach/initial_temperature_case2a.txt .
sed -i "s|set Initial global refinement          = 4|set Initial global refinement          = $LEV|" case.prm
if [ -n "$3" ]; then cat "$3" >> case.prm; fi
start=$(date +%s)
${BIN:-$A/build/aspect} case.prm > run.log 2>&1
echo "EXIT=$? WALL=$(( $(date +%s) - start ))" >> run.log
#!/bin/bash
source /root/autodl-tmp/envs/dealenv.sh
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml
A=/root/autodl-tmp/envs/aspect-2.4
R=/root/autodl-tmp/PBR/aspect_runs/smoke_$1
rm -rf $R && mkdir -p $R && cd $R
cp $A/benchmarks/blankenbach/base_case2a.prm case.prm
mkdir -p plugin && cp $A/build/benchmarks/blankenbach/plugin/libblankenbach.so plugin/
cp $A/benchmarks/blankenbach/initial_temperature_case2a.txt .
sed -i "s|set Initial global refinement          = 5|set Initial global refinement          = 4|" case.prm
printf 'set End time = 0.004\n' >> case.prm
shift
export "$@"
PBR_LOG=$R/trace.csv $A/build-pbr/aspect case.prm > run.log 2>&1
echo "EXIT=$? MODE=$PBR_POLICY K=$PBR_K BASE=$PBR_BASE"
