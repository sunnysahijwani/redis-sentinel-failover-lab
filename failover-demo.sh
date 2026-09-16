#!/usr/bin/env bash
#
# failover-demo.sh — prove Redis Sentinel auto-failover with your own eyes.
# Starts the cluster, writes keys through the live master, kills the primary,
# and watches Sentinel promote a replica while writes resume automatically.
#
# Run from inside the lab folder:  ./failover-demo.sh
# The sentinel container doubles as our "app client" — it stays alive the whole time.
#
set -uo pipefail
cd "$(dirname "$0")"

CLIENT=redis-sentinel-1          # jump box we exec redis-cli from (survives the kill)
say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
master_addr() { docker exec "$CLIENT" redis-cli -p 26379 \
                  SENTINEL get-master-addr-by-name mymaster 2>/dev/null | head -1 | tr -d '\r'; }

say "Starting cluster: 1 primary + 2 replicas + 3 sentinels"
docker compose up -d
echo "Waiting for replication + sentinel discovery to settle..."
sleep 10

say "Replication topology — primary should list 2 connected replicas"
docker exec redis-primary redis-cli INFO replication \
  | grep -E "role:|connected_slaves|slave[0-9]:ip" | tr -d '\r'

say "Sentinel's view of the master"
echo "master = $(master_addr)   (172.28.0.10 = redis-primary)"

say "Writing one key/sec through whatever Sentinel says is master (log below is live)"
LOG=./failover.log; : > "$LOG"
# timeout 2 bounds each write so a dead master fails FAST instead of hanging on TCP timeout,
# keeping the once-per-second cadence so you can see the outage window clearly.
( i=0
  while true; do
    i=$((i+1)); addr=$(master_addr)
    if [ -n "$addr" ] && timeout 2 docker exec "$CLIENT" redis-cli -h "$addr" set demo:counter "$i" >/dev/null 2>&1; then
      printf "   [%03d] wrote to master %-12s OK\n"                    "$i" "$addr" >> "$LOG"
    else
      printf "   [%03d] write FAILED  (no reachable master yet)\n"    "$i"        >> "$LOG"
    fi
    sleep 1
  done ) &
WRITER=$!
disown "$WRITER" 2>/dev/null || true   # keep the shell from printing "Terminated" when we stop it
trap 'kill "$WRITER" 2>/dev/null' EXIT

sleep 5
say "💥 KILLING THE PRIMARY:  docker kill redis-primary"
docker kill redis-primary >/dev/null
echo "down-after-milliseconds is 5s → expect a few FAILED writes, then auto-recovery."

sleep 22
kill $WRITER 2>/dev/null || true

say "The write log across the whole event (watch the master IP change):"
cat "$LOG"

say "Sentinel has re-elected. New master:"
NEW=$(master_addr)
echo "master = $NEW   ($([ "$NEW" = "172.28.0.10" ] && echo 'STILL OLD — check logs' || echo 'a promoted replica ✅'))"

say "Confirm the promoted node now reports role:master"
docker exec "$CLIENT" redis-cli -h "$NEW" INFO replication \
  | grep -E "role:|connected_slaves" | tr -d '\r'

say "And the value we were writing survived the failover:"
echo "demo:counter = $(docker exec "$CLIENT" redis-cli -h "$NEW" get demo:counter | tr -d '\r')"

kill $WRITER 2>/dev/null || true
say "Done. Tear down with:  docker compose down"
