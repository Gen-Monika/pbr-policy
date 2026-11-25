set -eu
R=/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex
cd "$R"
test -e regression_done
test ! -e full.pid
setsid nohup /root/miniconda3/bin/python3 stepB_full_batch.py > full.log 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" > full.pid
printf 'Full batch PID %s\n' "$pid"
