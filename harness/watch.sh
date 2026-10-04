#!/bin/bash
# Exits when N more runs are done, when the schedule completes, or when the scheduler dies.
B=/tmp/krypta-bench; N=${1:-9}
count() { grep -l '"status": "done"' $B/results/*/meta.json 2>/dev/null | wc -l | tr -d ' '; }
start=$(count)
while true; do
  now=$(count)
  if [ -f $B/schedule.done ]; then echo "schedule complete: $now runs done"; exit 0; fi
  if [ $((now - start)) -ge "$N" ]; then echo "progress: $now runs done"; exit 0; fi
  if ! kill -0 "$(cat $B/schedule.pid 2>/dev/null)" 2>/dev/null; then echo "scheduler not running: $now runs done"; exit 1; fi
  sleep 60
done
