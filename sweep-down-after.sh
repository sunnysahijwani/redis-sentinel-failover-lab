#!/usr/bin/env bash
#
# sweep-down-after.sh — how long does a Sentinel failover ACTUALLY take?
# Runs the kill-the-primary experiment at several down-after-milliseconds
# settings, several reps each, and records the client-observed write outage.
#
# Output: results/sweep-down-after.csv (+ per-attempt trace in sweep-detail.log)
#
set -uo pipefail
cd "$(dirname "$0")"

SETTINGS=(1000 5000 10000)
REPS=3
OUT=results/sweep-down-after.csv
DETAIL=results/sweep-detail.log

mkdir -p results
echo "down_after_ms,rep,outage_s,first_fail_after_kill_s,old_master,new_master" > "$OUT"
: > "$DETAIL"

for s in "${SETTINGS[@]}"; do
  for r in $(seq 1 "$REPS"); do
    echo "=== down-after=${s}ms rep ${r}/${REPS} ==="
    DOWN_AFTER=$s docker compose down -v --remove-orphans >/dev/null 2>&1 || true
    DOWN_AFTER=$s docker compose up -d --force-recreate >/dev/null 2>&1

    # wait until the primary reports both replicas online
    ok_topo=0
    for _ in $(seq 1 30); do
      n=$(docker exec redis-primary redis-cli INFO replication 2>/dev/null | grep -c 'state=online')
      if [ "$n" = "2" ]; then ok_topo=1; break; fi
      sleep 1
    done
    if [ "$ok_topo" != "1" ]; then
      echo "    SKIP: replicas never came online" | tee -a "$DETAIL"
      echo "${s},${r},NA,NA,NA,NA" >> "$OUT"
      continue
    fi
    # sentinels poll INFO every 10s to discover replicas — give them time,
    # or the failover has no promotion candidates
    sleep 12

    echo "--- down-after=${s}ms rep=${r} ---" >> "$DETAIL"
    if line=$(python3 measure-outage.py 2>>"$DETAIL"); then
      echo "    $line"
      outage=$(echo "$line" | sed -n 's/.*outage_s=\([0-9.]*\).*/\1/p')
      ff=$(echo "$line"     | sed -n 's/.*first_fail_s=\([0-9.NA]*\).*/\1/p')
      newm=$(echo "$line"   | sed -n 's/.*new_master=\([0-9.]*\).*/\1/p')
      oldm=$(echo "$line"   | sed -n 's/.*old_master=\([0-9.]*\).*/\1/p')
      echo "${s},${r},${outage},${ff},${oldm},${newm}" >> "$OUT"
    else
      echo "    FAILED (see $DETAIL)"
      echo "${s},${r},NA,NA,NA,NA" >> "$OUT"
    fi
  done
done

DOWN_AFTER=5000 docker compose down -v --remove-orphans >/dev/null 2>&1 || true
echo
echo "Done. Results:"
column -s, -t < "$OUT"
