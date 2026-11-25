set -eu
export PATH=/root/miniconda3/bin:/usr/bin:/bin:$PATH
cd /root/autodl-tmp/PBR/stepB/phase_index_20261017_codex
mkdir -p replay
python3 - <<'PY'
from pathlib import Path
import csv,json,re
R=Path('/root/autodl-tmp/PBR'); dest=Path('replay');manifest={}
paths={f'Tosi_C{c}':R/f'aspect_runs/tosi/C{c}_ONLv/trace.csv' for c in [1,3,4,5]}
paths.update(Blankenbach=R/'aspect_runs/cmp_l5_t0.1_fix/r1_ONLINE/trace.csv',MOOSE=R/'moose_cases/r1_on100/pbr.csv')
for name,path in paths.items():
 rows=list(csv.DictReader(path.open()));out=[]
 for r in rows:
  # Existing CSV omits zero solves and its terminal row. Preserve recorded
  # index gaps; this is an identical-observation compatibility replay, not a
  # reconstruction of missing timing or a counterfactual performance result.
  i=int(r['step']);out.append(f"{i} {i%3} {int(float(r['its']))} {r['build_ms']} {r['solve_ms']} {int(r['est_dsrc']=='forced_reset')} -1\n")
 (dest/f'{name}.tsv').write_text(''.join(out));manifest[name]={'source':str(path),'recorded_events':len(rows),'phase_in_off_test':'arbitrary varying j; off must ignore it','phase_in_zero_test':'all zero'}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
PY
g++ -std=c++11 -O2 code/phase_index/replay.cpp -o replay/replay
replay/replay --unit
for data in replay/*.tsv; do
 replay/replay "$data" off
 replay/replay "$data" zero
done
