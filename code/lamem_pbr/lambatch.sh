#!/bin/bash
# lambatch.sh : 3 rounds; inside each round all configs run concurrently (same machine, same load).
ST=/root/autodl-tmp/PBR/lamem_cases/runs/STATUS
echo "start $(date)" > $ST
for R in 1 2 3; do
  echo "round $R start $(date)" >> $ST
  /root/lamrun.sh r${R}_orig  200 orig &
  /root/lamrun.sh r${R}_K1    200 pbr PBR_POLICY=fixed PBR_K=1 &
  /root/lamrun.sh r${R}_K2    200 pbr PBR_POLICY=fixed PBR_K=2 &
  /root/lamrun.sh r${R}_K3    200 pbr PBR_POLICY=fixed PBR_K=3 &
  /root/lamrun.sh r${R}_K5    200 pbr PBR_POLICY=fixed PBR_K=5 &
  /root/lamrun.sh r${R}_K10   200 pbr PBR_POLICY=fixed PBR_K=10 &
  /root/lamrun.sh r${R}_never 200 pbr PBR_POLICY=fixed PBR_K=0 &
  /root/lamrun.sh r${R}_on100 200 pbr PBR_POLICY=online PBR_BASE=100 &
  /root/lamrun.sh r${R}_on20  200 pbr PBR_POLICY=online PBR_BASE=20 &
  wait
  echo "round $R done $(date)" >> $ST
done
echo "ALL DONE $(date)" >> $ST
