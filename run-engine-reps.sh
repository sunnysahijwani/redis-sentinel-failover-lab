#!/usr/bin/env bash
#
# run-engine-reps.sh <engine-label> <compose-file> <down_after_ms> <reps>
# Same measurement as sweep-down-after.sh, but per engine variant.
# Appends to results/engines.csv.
#
set -uo pipefail
cd "$(dirname "$0")"

LABEL=${1:?engine label}
COMPOSE=${2:?compose file}
DOWN=${3:-5000}
REPS=${4:-3}
OUT=results/engines.csv
DETAIL=results/engines-detail.log

mkdir -p results
[ -f "$OUT" ] || echo "engine,down_after_ms,rep,outage_s,first_fail_after_kill_s,old_master,new_master" > "$OUT"

for r in $(seq 1 "$REPS"); do
  echo "=== engine=${LABEL} down-after=${DOWN}ms rep ${r}/${REPS} ==="
  COMPOSE_FILE=$COMPOSE DOWN_AFTER=$DOWN docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  COMPOSE_FILE=$COMPOSE DOWN_AFTER=$DOWN docker compose up -d --force-recreate >/dev/null 2>&1

  ok_topo=0
  for _ in $(seq 1 45); do
    # redis/valkey report replicas as state=online; dragonfly as state=stable_sync
    n=$(docker exec redis-primary redis-cli INFO replication 2>/dev/null | grep -c 'state=online\|state=stable_sync')
    if [ "$n" = "2" ]; then ok_topo=1; break; fi
    sleep 1
  done
  if [ "$ok_topo" != "1" ]; then
    echo "    SKIP: replicas never came online"
    docker exec redis-primary redis-cli INFO replication 2>&1 | head -12
    echo "${LABEL},${DOWN},${r},NA,NA,NA,NA" >> "$OUT"
    continue
  fi
  sleep 12   # sentinel INFO-poll discovery of replicas

  echo "--- engine=${LABEL} down-after=${DOWN} rep=${r} ---" >> "$DETAIL"
  if line=$(python3 measure-outage.py 2>>"$DETAIL"); then
    echo "    $line"
    outage=$(echo "$line" | sed -n 's/.*outage_s=\([0-9.]*\).*/\1/p')
    ff=$(echo "$line"     | sed -n 's/.*first_fail_s=\([0-9.NA]*\).*/\1/p')
    newm=$(echo "$line"   | sed -n 's/.*new_master=\([0-9.]*\).*/\1/p')
    oldm=$(echo "$line"   | sed -n 's/.*old_master=\([0-9.]*\).*/\1/p')
    echo "${LABEL},${DOWN},${r},${outage},${ff},${oldm},${newm}" >> "$OUT"
  else
    echo "    FAILED (see $DETAIL)"
    echo "${LABEL},${DOWN},${r},NA,NA,NA,NA" >> "$OUT"
  fi
done

COMPOSE_FILE=$COMPOSE docker compose down -v --remove-orphans >/dev/null 2>&1 || true
echo "done ${LABEL}"
