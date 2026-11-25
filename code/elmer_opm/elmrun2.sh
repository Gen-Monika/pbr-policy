#!/bin/bash
# elmrun2.sh <srcdir> <tag> <sif> <eq> <mode: K<n> | ONLINE> [env...]
source /root/autodl-tmp/envs/elmerenv.sh
SRC=$1; TAG=$2; SIF=$3; EQ=$4; MODE=$5; shift 5
W=$(dirname $SRC)/run_$(basename $SRC)_$TAG
rm -rf $W; cp -r $SRC $W; cd $W
/root/miniconda3/bin/python3 - "$SIF" "$EQ" "$MODE" <<'PY'
import sys,re
sif,eq,mode=sys.argv[1:4]
s=open(sif).read()
i=s.find('Equation = "%s"'%eq)
if i<0: i=s.find('Equation = %s'%eq)
j=s.find('\nEnd',i)
if mode=='ONLINE':
    add='\n  Linear System Precondition Online = Logical True\n'
else:
    add='\n  Linear System Precondition Recompute = Integer %d\n'%int(mode[1:])
add+='  Linear System Timing = Logical True\n  Linear System Residual Output = Integer 1\n'
s=s[:j]+add+s[j:]
s=re.sub(r'(Max Output Level\s*=\s*)\d+', r'\g<1>8', s, count=1)
open(sif,'w').write(s)
PY
export "$@" PBR_LOG=$W/pbr_trace.csv
start=$(date +%s.%N)
ElmerSolver $SIF > run.log 2>&1
rc=$?
/root/miniconda3/bin/python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> run.log
