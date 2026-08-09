#!/usr/bin/env bash
# Supervisor for the corpus sweep. Restarts the harness if it dies.
#
# The sweep is resumable by construction -- every finished line is already in
# results.jsonl and is skipped on the next start -- so a restart costs only the
# lines that were in flight. That is what makes a dumb retry loop safe here.
#
#   tmux new -d -s hs 'evals/hs_classification/supervise.sh 8 runs/hs_deepseek --provider deepseek'
#   tmux attach -t sweep
set -u
cd "$(dirname "$0")/../.."

WORKERS="${1:-6}"
OUT="${2:-sweep_out}"
MAX_RESTARTS=50

mkdir -p "$OUT"
for attempt in $(seq 1 "$MAX_RESTARTS"); do
  echo "=== supervisor: start #$attempt ($(date '+%F %T')) workers=$WORKERS ==="
  .venv/bin/python -m evals.hs_classification.run --workers "$WORKERS" --out "$OUT" "${@:3}"
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "=== supervisor: sweep completed cleanly ($(date '+%F %T')) ==="
    exit 0
  fi
  # 130 = SIGINT, 143 = SIGTERM: a human stopped it, so do not fight them.
  if [ "$code" -eq 130 ] || [ "$code" -eq 143 ]; then
    echo "=== supervisor: interrupted (exit $code), not restarting ==="
    exit "$code"
  fi
  echo "=== supervisor: exit $code -- restarting in 30s ==="
  sleep 30
done
echo "=== supervisor: gave up after $MAX_RESTARTS restarts ==="
exit 1
