"""Arrivals of the MQTT fleet after the broker's MQTT listener came up, the
2026-10-11 drill (paho's default schedule) against the 2026-11-25 drill
(proactor jm4: full jitter, 30 s cap). Writes arrivals-before-after.png.
Data: October from ../2026-10-11-prod-broker-outage-drill/reconnects-display.csv
(mqtt, held), November from evidence/broker-log-reduced.txt accepts.
    uv run --with matplotlib python arrivals_chart.py
"""

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

OCT = [46.3, 46.3, 46.3, 46.3, 46.3, 46.3, 47.0, 47.1, 47.9, 48.5, 98.7]
NOV = [3.1, 7.0, 8.5, 9.3, 11.4, 11.4, 12.0, 13.3, 14.7, 21.1, 23.5, 27.2]
BLUE, ORANGE = "#257de0", "#f47230"
TEXT, TEXT2, GRID = "#1f1f1f", "#6b6b6b", "#e6e6e6"

fig, ax = plt.subplots(figsize=(10, 3.6), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

rows = [
    (1, OCT, ORANGE, "2026-10-11 · paho default (1 s doubling to 120 s, no jitter)", 11),
    (0, NOV, BLUE, "2026-11-25 · proactor jm4 (full jitter, 30 s cap)", 12),
]
for y, xs, color, label, n in rows:
    ax.scatter(xs, [y] * len(xs), s=70, color=color, edgecolors="white",
               linewidths=1.5, zorder=3, label=label)
    ax.hlines(y, min(xs), max(xs), color=color, linewidth=2, alpha=0.35, zorder=2)
    ax.text(-2, y + 0.22, f"{label}", ha="left", va="bottom", color=TEXT, fontsize=9.5)
    ax.text(-2, y - 0.22, f"{n} clients · first {min(xs):.0f} s · last {max(xs):.0f} s",
            ha="left", va="top", color=TEXT2, fontsize=8.5)

ax.annotate("six LTNs within 42 ms", xy=(46.3, 1), xytext=(56, 1.05),
            color=TEXT2, fontsize=8.5, arrowprops={"arrowstyle": "-", "color": TEXT2, "lw": 0.8})
ax.annotate("oak scada, 99 s", xy=(98.7, 1), xytext=(88, 0.72), color=TEXT2, fontsize=8.5)
ax.axvspan(0, 30, color=BLUE, alpha=0.06, zorder=1)
ax.text(30.6, -0.55, "30 s cap", color=TEXT2, fontsize=8.5, ha="left", va="bottom")

ax.set_xlim(-3, 105)
ax.set_ylim(-0.7, 1.75)
ax.set_yticks([])
ax.set_xlabel("seconds after the broker's MQTT listener came up", color=TEXT2, fontsize=9.5)
ax.tick_params(axis="x", colors=TEXT2, labelsize=9)
ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.set_title("MQTT fleet return after a prod-broker stop: each dot is one scada or LTN accepted",
             loc="left", color=TEXT, fontsize=11, pad=12)
ax.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=TEXT)
fig.tight_layout()
fig.savefig("arrivals-before-after.png")
print("wrote arrivals-before-after.png")
