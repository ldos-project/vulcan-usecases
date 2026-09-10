import json
import numpy as np
import matplotlib.pyplot as plt

with open("results.json", "r") as f:
    data = json.load(f)

# Choose one primary metric per workload for plotting
preferred_metric = {
    "GUPS (33 8 30)": "MUPS",
    "GUPS (36 8 33)": "MUPS",
    "GapBS BC-8": "Total Time",
    "GapBS BC-16": "Total Time",
    "GapBS PR": "Total Time",
    "Silo TPCC": "Aggregate Throughput"
}

# Filter data to just the chosen (workload, metric) pairs
records = []
for item in data:
    wl = item["workload"]
    if wl in preferred_metric and item["metric"] == preferred_metric[wl]:
        print(item)
        records.append(item)

workloads = [r["workload"] for r in records]
thor10_norm = []
thor50_norm = []
thorf_norm = []
for r in records:
    if "Time" in r["metric"]:
        print(r["ARMS"], r["Thor_FirstIteration"], r["Thor_Best"])
        thor10_norm.append(r["ARMS"] / r["Thor_FirstIteration"])
        thor50_norm.append(r["ARMS"] / r["Thor_50"])
        thorf_norm.append(r["ARMS"] / r["Thor_Best"])
    else:
        thor10_norm.append(r["Thor_FirstIteration"] / r["ARMS"])
        thor50_norm.append(r["Thor_50"] / r["ARMS"])
        thorf_norm.append(r["Thor_Best"] / r["ARMS"])

x = np.arange(len(workloads))
width = 0.25  # bar width

fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(x - width, thor10_norm, width, label="Thor (10 iter.)", hatch='//')
ax.bar(x, thor50_norm, width, label="Thor (50 iter.)", hatch='\\\\')
ax.bar(x + width, thorf_norm, width, label="Thor (final)", hatch='xx')

# Reference line for ARMS (normalized = 1.0)
ax.axhline(1.0, linestyle="--", linewidth=1)

ax.set_ylabel("Normalized Performance", fontsize=18)
ax.set_xticks(x)
ax.set_xticklabels(workloads, rotation=30, ha="right", fontsize=16)
ax.tick_params(axis='y', labelsize=16)
ax.legend(fontsize=18, loc='upper center', bbox_to_anchor=(0.5, 1.2), ncol=3, frameon=False)

# Create broken axis effect to highlight 0.95-1.1 range
ax.set_ylim(0.9, 1.10)
ax.spines['left'].set_position(('outward', 10))

# Add a break mark on y-axis
d = 0.015  # size of diagonal lines
kwargs = dict(transform=ax.transAxes, color='k', clip_on=False, linewidth=1)
ax.plot((-d, +d), (-d, +d), **kwargs)        # bottom-left diagonal
ax.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # top-left diagonal

plt.tight_layout()
plt.savefig("thor_vs_arms_normalized.png")
plt.savefig("thor_vs_arms_normalized.pdf")
