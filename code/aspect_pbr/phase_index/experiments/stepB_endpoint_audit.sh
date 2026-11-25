set -eu
export PATH=/root/miniconda3/bin:/usr/bin:/bin:$PATH
python3 - <<'PY'
from pathlib import Path
import json,re
R=Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
d=json.loads((R/'analysis.json').read_text())
for case,vals in d['fixed'].items():
 print(case,{k:v.get('final_step_time') for k,v in vals.items()})
for name,v in d['fixed']['C4'].items():
 p=Path(v['path']);s=(p/'run.log').read_text()
 headers=re.findall(r'^\*\*\* Timestep.*$',s,re.M)
 print(name,'last headers',headers[-3:])
 for f in p.glob('*.prm'):
  print(f.name,[l for l in f.read_text().splitlines() if 'End time' in l or 'include' in l or 'Initial global' in l])
print('C1 OFF initial residual at cap')
for l in Path(d['fixed']['C1']['C1_OFF']['path'],'run.log').read_text().splitlines():
 if 'after nonlinear iteration 30:' in l:print(l)
PY
