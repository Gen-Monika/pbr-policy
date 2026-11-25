#!/bin/bash
# Sequential: (1) online warm-up sensitivity, (2) interleaved wallclock rounds. Tosi Case 4, End time 0.0063.
R=/root/tosirun.sh; E=0.0063
$R 4 ONLv_B20 $E PBR_POLICY=online PBR_BASE=20
$R 4 ONLv_B50 $E PBR_POLICY=online PBR_BASE=50
for r in 1 2 3; do
  $R 4 W${r}_K1    $E PBR_POLICY=off
  $R 4 W${r}_V15   $E PBR_POLICY=fixed PBR_K=15
  $R 4 W${r}_ONLv  $E PBR_POLICY=online PBR_BASE=100
done
echo ALLDONE > /root/autodl-tmp/PBR/aspect_runs/tosi/wall.done
