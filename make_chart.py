#!/usr/bin/env python3
"""Render the down-after sweep chart from results/sweep-down-after.csv.

Bar = mean client-observed write outage per down-after-milliseconds setting;
dots = individual reps. Writes images/chart_outage_window.png.
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
data = defaultdict(list)
with open(os.path.join(HERE, "results", "sweep-down-after.csv")) as f:
    for row in csv.DictReader(f):
        if row["outage_s"] not in ("", "NA"):
            data[int(row["down_after_ms"])].append(float(row["outage_s"]))

settings = sorted(data)
means = [sum(data[s]) / len(data[s]) for s in settings]

BG, FG, GRID = "#0d1117", "#e6edf3", "#21262d"
BAR, DOT, ACCENT = "#2f81f7", "#f0883e", "#7ee787"

fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

x = range(len(settings))
ax.bar(x, means, width=0.55, color=BAR, zorder=2,
       label="mean write outage (client-observed)")
for i, s in enumerate(settings):
    ax.scatter([i] * len(data[s]), data[s], color=DOT, s=55, zorder=3,
               label="individual runs" if i == 0 else None)
    ax.annotate("%.1fs" % means[i], (i, means[i]),
                textcoords="offset points", xytext=(0, 10),
                ha="center", color=ACCENT, fontsize=14, fontweight="bold")

ax.set_xticks(list(x))
ax.set_xticklabels(["%gs" % (s / 1000) for s in settings], fontsize=13, color=FG)
ax.set_xlabel("sentinel down-after-milliseconds", fontsize=12, color=FG)
ax.set_ylabel("write outage after killing the primary (seconds)", fontsize=12, color=FG)
ax.set_title("How long does a Redis Sentinel failover actually take?",
             fontsize=16, color=FG, fontweight="bold", pad=14)
ax.tick_params(colors=FG)
for spine in ax.spines.values():
    spine.set_color(GRID)
ax.grid(axis="y", color=GRID, zorder=0)
leg = ax.legend(facecolor=BG, edgecolor=GRID, fontsize=11)
for t in leg.get_texts():
    t.set_color(FG)
fig.text(0.99, 0.01, "1 primary + 2 replicas + 3 sentinels, Redis 8, Docker — kill primary, write every ~0.35s via Sentinel discovery",
         ha="right", color="#8b949e", fontsize=8)

os.makedirs(os.path.join(HERE, "images"), exist_ok=True)
out = os.path.join(HERE, "images", "chart_outage_window.png")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(out, facecolor=BG)
print("wrote", out)
