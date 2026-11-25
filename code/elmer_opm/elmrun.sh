#!/bin/bash
# elmrun.sh <srcdir> <tag> <sif> <solverEquationName> <recompute N>
source /root/autodl-tmp/envs/elmerenv.sh
SRC=$1; TAG=$2; SIF=$3; EQ=$4; N=$5
W=$(dirname $SRC)/run_$(basename $SRC)_$TAG
rm -rf $W; cp -r $SRC $W; cd $W
/root/miniconda3/bin/python3 - "$SIF" "$EQ" "$N" <<'PY'
import sys,re
sif,eq,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
s=open(sif).read()
i=s.find('Equation = "%s"'%eq)
if i<0: i=s.find('Equation = %s'%eq)
assert i>=0, 'equation not found'
j=s.find('\nEnd',i)
add='\n  Linear System Precondition Recompute = Integer %d\n  Linear System Timing = Logical True\n  Linear System Residual Output = Integer 1\n'%n
s=s[:j]+add+s[j:]
# raise verbosity so Prec-ILU timer (Level 8) is printed
s=re.sub(r'(Max Output Level\s*=\s*)\d+', r'\g<1>8', s, count=1)
if 'Max Output Level' not in s:
    s=s.replace('Simulation','Simulation\n  Max Output Level = 8',1)
open(sif,'w').write(s)
PY
start=$(date +%s.%N)
ElmerSolver $SIF > run.log 2>&1
rc=$?
/root/miniconda3/bin/python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> run.log
