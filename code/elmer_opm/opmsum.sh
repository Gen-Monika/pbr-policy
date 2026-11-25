#!/bin/bash
# summarize all out_* dirs in given case dir
cd $1
for o in out_*; do
  f=$o/log.txt
  printf "%-14s " ${o#out_}
  grep -E 'Total time \(seconds\)|Linear solve time|Linear setup|Overall Linearizations|Overall Newton Iterations|Overall Linear Iterations|EXTWALL' $f | sed -E 's/\(Failed.*//; s/ +/ /g; s/\(seconds\)//' | awk -F: '{printf "%s=%s; ", $1, $2}' | sed 's/  */ /g'
  echo
done
