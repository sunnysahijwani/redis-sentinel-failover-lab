# Redis Sentinel failover lab — kill the primary, measure the outage

How long does a Redis Sentinel failover *actually* take? This is a self-contained
Docker lab that answers it with a stopwatch instead of a diagram: **1 primary +
2 replicas + 3 sentinels**, a script that kills the primary while writing through
Sentinel discovery, and sweeps that measure the client-observed write outage
across `down-after-milliseconds` settings **and across engines** (Redis 8,
Valkey 8, Dragonfly — same sentinels every time).

**Full write-up:** [How long does a Redis Sentinel failover actually take? I measured it](https://two-techies.com/blog/redis-sentinel-failover-time)

## Measured result (Redis 8, Docker, 3 runs per setting)

| `down-after-milliseconds` | write outage (mean) |
|---:|---:|
| 1000 | 2.5s |
| 5000 | 7.3s |
| 10000 | 12.1s |

**Outage ≈ `down-after` + ~2s of quorum vote, leader election, and replica
promotion.** The ~2s is the fixed tax; `down-after` is the dial you control.

**And the engine doesn't matter.** Same kill at `down-after=5s` under identical
redis:8 sentinels, three runs each:

| engine | write outage (mean) |
|---|---:|
| Redis 8 | 7.33s |
| Valkey 8 | 7.37s |
| Dragonfly | 7.37s |

Failover time is a property of Sentinel, not of the data engine. (Garnet is
absent because it doesn't speak Sentinel — its HA is its own cluster mode.)

Raw data: [`results/sweep-down-after.csv`](results/sweep-down-after.csv) and
[`results/engines.csv`](results/engines.csv), per-attempt traces in
[`results/sweep-detail.log`](results/sweep-detail.log) / [`results/engines-detail.log`](results/engines-detail.log).

Measured on Docker-on-macOS with ~0.1s of `docker exec` overhead per write —
treat sub-second digits as approximate; the shape is the finding. Rerun it on
your hardware and tell me where I'm wrong.

## Quick start (5 minutes)

```bash
docker compose up -d      # start 1 primary + 2 replicas + 3 sentinels
./failover-demo.sh        # write keys, kill the primary, watch it self-heal
docker compose down       # tear everything down
```

The demo writes one key per second through whatever Sentinel currently reports
as master, kills the primary, and prints the write log across the whole event —
you can watch the master's IP change and the counter survive.

## Reproduce the measurement

```bash
./sweep-down-after.sh     # ~8 min: 3 settings × 3 reps, fresh cluster each run
python3 make_chart.py     # render images/chart_outage_window.png from the CSV
```

Each rep: fresh cluster, wait for replication + sentinel discovery, write every
~350ms via `SENTINEL get-master-addr-by-name`, kill the primary at t=5s, and
record the gap until the first successful write on a *promoted* node
(`measure-outage.py`).

Tune the sweep by editing `SETTINGS` / `REPS` in `sweep-down-after.sh`, or run a
single setting by hand:

```bash
DOWN_AFTER=2000 docker compose up -d --force-recreate
```

Engine variants (same sentinels, different data nodes):

```bash
./run-engine-reps.sh valkey    docker-compose.valkey.yml    5000 3
./run-engine-reps.sh dragonfly docker-compose.dragonfly.yml 5000 3
python3 make_chart_engines.py   # render images/chart_engines.png
```

Dragonfly note: it needs `--maxmemory` ≥ 256MiB × `--proactor_threads` or it
exits at startup; the compose file sets 1gb for 2 threads.

## Files

| file | purpose |
|---|---|
| `docker-compose.yml` | the cluster; `DOWN_AFTER` env parameterises `down-after-milliseconds` |
| `docker-compose.valkey.yml` | same lab, Valkey 8 data nodes (sentinels stay redis:8) |
| `docker-compose.dragonfly.yml` | same lab, Dragonfly data nodes (sentinels stay redis:8) |
| `failover-demo.sh` | narrative demo: kill the primary, watch the write log |
| `sweep-down-after.sh` | the measurement: settings × reps → `results/*.csv` |
| `run-engine-reps.sh` | same measurement per engine variant → `results/engines.csv` |
| `measure-outage.py` | one timed kill: outage = kill → first OK write on promoted node |
| `make_chart.py` / `make_chart_engines.py` | charts from the CSVs (need matplotlib) |

## Notes that matter in production

The lab disables persistence for clarity — in production run AOF on at least the
replicas. Failover is not zero data loss (replication is async), a hair-trigger
`down-after` buys false failovers, and your cache and your queue deserve separate
failover groups. The [article](https://two-techies.com/blog/redis-sentinel-failover-time)
covers these traps and the Laravel/Predis Sentinel wiring in detail.

## License

MIT — see [LICENSE](LICENSE).
