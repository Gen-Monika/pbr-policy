set -eu
R=/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex
cd "$R"
test -e build_done
/root/miniconda3/bin/python3 - <<'PY'
import json
v=json.load(open('build_results.json'))
assert len(v)==2 and all(x['rc']==0 and x['guard'] is None for x in v),v
PY
test ! -e regression.pid
setsid nohup /root/miniconda3/bin/python3 stepB_run.py regression > regression.log 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" > regression.pid
printf 'Regression PID %s\n' "$pid"
