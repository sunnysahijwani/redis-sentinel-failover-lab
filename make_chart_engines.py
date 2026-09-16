#!/usr/bin/env python3
"""Render the engine-comparison chart from results/engines.csv (+ redis baseline
from results/sweep-down-after.csv at the same down-after setting).

The point of this chart is that the bars are the same height.
Writes images/chart_engines.png.
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SETTING = 5000

data = defaultdict(list)
with open(os.path.join(HERE, "results", "sweep-down-after.csv")) as f:
    for row in csv.DictReader(f):
        if int(row["down_after_ms"]) == SETTING and row["outage_s"] not in ("", "NA"):
            data["Redis 8"].append(float(row["outage_s"]))
with open(os.path.join(HERE, "results", "engines.csv")) as f:
    for row in csv.DictReader(f):
        if int(row["down_after_ms"]) == SETTING and row["outage_s"] not in ("", "NA"):
            name = {"valkey": "Valkey 8", "dragonfly": "Dragonfly"}[row["engine"]]
            data[name].append(float(row["outage_s"]))

engines = ["Redis 8", "Valkey 8", "Dragonfly"]
means = [sum(data[e]) / len(data[e]) for e in engines]

BG, FG, GRID = "#0d1117", "#e6edf3", "#21262d"
COLORS = ["#d9484c", "#4f9cf9", "#f0883e"]
ACCENT = "#7ee787"

fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

x = range(len(engines))
ax.bar(x, means, width=0.55, color=COLORS, zorder=2)
for i, e in enumerate(engines):
    ax.scatter([i] * len(data[e]), data[e], color=FG, s=45, zorder=3, alpha=0.85)
    ax.annotate("%.2fs" % means[i], (i, means[i]),
                textcoords="offset points", xytext=(0, 10),
                ha="center", color=ACCENT, fontsize=15, fontweight="bold")

ax.set_ylim(0, 9)
ax.set_xticks(list(x))
ax.set_xticklabels(engines, fontsize=14, color=FG)
ax.set_ylabel("write outage after killing the primary (seconds)", fontsize=12, color=FG)
fig.suptitle("Same sentinels, same kill, three engines — same outage",
             fontsize=16, color=FG, fontweight="bold", y=0.97)
ax.set_title("down-after-milliseconds=5000, quorum 2/3 (redis:8 sentinels for all), 3 runs each (dots)",
             fontsize=10, color="#8b949e", pad=10)
ax.tick_params(colors=FG)
for spine in ax.spines.values():
    spine.set_color(GRID)
ax.grid(axis="y", color=GRID, zorder=0)
fig.text(0.99, 0.01, "1 primary + 2 replicas + 3 sentinels, Docker — failover time is Sentinel's, not the engine's",
         ha="right", color="#8b949e", fontsize=8)

os.makedirs(os.path.join(HERE, "images"), exist_ok=True)
out = os.path.join(HERE, "images", "chart_engines.png")
fig.tight_layout(rect=(0, 0.03, 1, 0.93))
fig.savefig(out, facecolor=BG)
print("wrote", out)
