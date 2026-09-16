#!/usr/bin/env python3
"""Measure the client-observed write outage during a Sentinel failover.

Continuously writes demo:counter through whatever Sentinel currently reports
as master, kills the primary at KILL_AT seconds, and keeps writing until the
first successful write lands on a PROMOTED node (address != original master).

Prints one summary line to stdout:
  outage_s=<kill -> first OK on new master>
  first_fail_s=<kill -> first failed write>
  new_master=<ip> old_master=<ip>
Per-attempt trace goes to stderr.

Each write is a `docker exec redis-cli` round-trip (~0.1s overhead), so treat
sub-second precision as approximate — the signal here is seconds, not ms.
"""
import subprocess
import sys
import time

CLIENT = "redis-sentinel-1"   # exec redis-cli from a sentinel container: it survives the kill
INTERVAL = 0.25               # pause between write attempts
KILL_AT = 5.0                 # seconds of healthy writes before the kill
MAX_WAIT = 90.0


def sh(args, timeout):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, ""


def master_addr():
    ok, out = sh(["docker", "exec", CLIENT, "redis-cli", "-p", "26379",
                  "SENTINEL", "get-master-addr-by-name", "mymaster"], 2)
    return out.splitlines()[0].strip() if ok and out else ""


def write(addr, i):
    ok, out = sh(["docker", "exec", CLIENT, "redis-cli", "-h", addr,
                  "set", "demo:counter", str(i)], 2)
    return ok and out == "OK"


t0 = time.monotonic()
orig = master_addr()
if not orig:
    print("ERROR: sentinel has no master yet", file=sys.stderr)
    sys.exit(1)

t_kill = None
events = []
i = 0
while True:
    now = time.monotonic() - t0
    if t_kill is None and now >= KILL_AT:
        subprocess.run(["docker", "kill", "redis-primary"], capture_output=True)
        t_kill = time.monotonic() - t0
        events.append((t_kill, "KILL", ""))
    i += 1
    addr = master_addr()
    ok = write(addr, i) if addr else False
    t = time.monotonic() - t0
    events.append((t, "OK" if ok else "FAIL", addr))
    if t_kill is not None and ok and addr and addr != orig:
        break
    if time.monotonic() - t0 > MAX_WAIT:
        print("ERROR: no recovery within %ss" % MAX_WAIT, file=sys.stderr)
        for t, s, a in events:
            print("  [%6.2fs] %-4s %s" % (t, s, a), file=sys.stderr)
        sys.exit(1)
    time.sleep(INTERVAL)

recover_t, _, new_master = events[-1]
first_fail = next((t for t, s, _ in events if s == "FAIL" and t >= t_kill), None)
outage = recover_t - t_kill
ff = "%.2f" % (first_fail - t_kill) if first_fail is not None else "NA"
print("outage_s=%.2f first_fail_s=%s new_master=%s old_master=%s"
      % (outage, ff, new_master, orig))
for t, s, a in events:
    print("  [%6.2fs] %-4s %s" % (t, s, a), file=sys.stderr)
