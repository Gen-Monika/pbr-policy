#!/bin/bash
# Clean sequential batch: (A) Tosi C4 wallclock 3 rounds (K1/V15/V30/ONLv), (B) Blankenbach fixed-code wallclock 3 rounds.
R=/root/tosirun.sh; E=0.0063
for r in 1 2 3; do
  $R 4 W${r}_K1    $E PBR_POLICY=off
  $R 4 W${r}_V15   $E PBR_POLICY=fixed PBR_K=15
  $R 4 W${r}_V30   $E PBR_POLICY=fixed PBR_K=30
  $R 4 W${r}_ONLv  $E PBR_POLICY=online PBR_BASE=100
done
echo TOSI_DONE >> /root/autodl-tmp/PBR/aspect_runs/wallbatch.status
LEV=5 ENDF=0.1 ROUNDS=3 /root/run9fix.sh
echo BB_DONE >> /root/autodl-tmp/PBR/aspect_runs/wallbatch.status
