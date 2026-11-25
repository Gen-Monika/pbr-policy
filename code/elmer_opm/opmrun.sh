#!/bin/bash
# usage: opmrun.sh <deck> <tag> [flow args...]
source /root/autodl-tmp/envs/opmenv.sh
D=$1; T=$2; shift 2
cd $(dirname $D)
O=out_$T; rm -rf $O; mkdir -p $O
start=$(date +%s.%N)
flow $(basename $D) --output-dir=$O "$@" > $O/log.txt 2>&1
rc=$?
/root/miniconda3/bin/python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> $O/log.txt
