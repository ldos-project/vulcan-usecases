#!/usr/bin/env python3
import matplotlib.pyplot as plt
import numpy as np
import json

SYSTEM_NAME = "Vulcan"

# Load data
with open('cbl_results/results_referenced_up.json') as f:
    up = json.load(f)
with open('cbl_results/results_adrs.json') as f:
    adrs = json.load(f)
with open('cbl_results/results_vulcan.json') as f:
    vulcan_all = json.load(f)
with open('cbl_results/results_vulcan_no_listeners.json') as f:
    no_listeners = json.load(f)

# Extract data
def get_stats(data):
    improvements = [t['improvement'] for t in data['baselines'][0]['comparison']['per_trace']]
    rel_improvements = [t['improvement_ratio'] * 100 for t in data['baselines'][0]['comparison']['per_trace']]
    return {
        'abs_mean': np.mean(improvements),
        'rel_mean': np.mean(rel_improvements),
        'improvements': improvements
    }

up_stats = get_stats(up)
adrs_stats = get_stats(adrs)
no_listener_stats = get_stats(no_listeners)
vulcan_stats = get_stats(vulcan_all)

policies = {"UP": '#4C72B0', "ADRS": '#DD8452', f"{SYSTEM_NAME}-NL": '#8172B3', f"{SYSTEM_NAME}": '#55A868'}

# Computed values
avg_usd_saved = [up_stats['abs_mean'], adrs_stats['abs_mean'], no_listener_stats['abs_mean'], vulcan_stats['abs_mean']]
avg_relative_improvement = [up_stats['rel_mean'], adrs_stats['rel_mean'], no_listener_stats['rel_mean'], vulcan_stats['rel_mean']]

def add_bar_labels(ax, values, fmt):
    ymin, ymax = ax.get_ylim()
    span = ymax - ymin

    ax.set_ylim(
        ymin - 0.12 * span if min(values) < 0 else ymin,
        ymax + 0.12 * span,
    )

    ymin, ymax = ax.get_ylim()
    span = ymax - ymin

    for bar, value in zip(ax.patches, values):
        x_pos = bar.get_x() + bar.get_width() / 2

        if value >= 0:
            y_pos = value + 0.025 * span
            va = "bottom"
        else:
            y_pos = value - 0.035 * span
            va = "top"

        ax.text(
            x_pos,
            y_pos,
            fmt.format(value),
            ha="center",
            va=va,
            fontsize=10,
        )

x = np.arange(len(policies.keys()))

fig = plt.figure(figsize=(7, 2.35), constrained_layout=True)
gs = fig.add_gridspec(1, 2, width_ratios=[0.35, 0.65], wspace=0.1)
axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]

# Left: bar plot (same as before)
axes[0].bar(x, avg_usd_saved, color=[policies[key] for key in policies.keys()])
axes[0].set_xticks(x)
axes[0].set_xticklabels(policies.keys(), rotation=30, ha='right', fontsize=14)
axes[0].set_ylabel("Avg. USD saved\n(per scenario)", size=16)
axes[0].set_title("(a) Absolute savings", size=16)
axes[0].axhline(0, linewidth=0.8)
axes[0].grid(axis="y", alpha=0.3, linewidth=0.6)

add_bar_labels(axes[0], avg_usd_saved, "${:.2f}")

# Right: categorical binning (symmetric thresholds at $10)
def categorize_improvement(improvements):
    big_loss = sum(1 for x in improvements if x < -10)
    small_loss = sum(1 for x in improvements if -10 <= x < 0)
    small_gain = sum(1 for x in improvements if 0 <= x < 10)
    big_gain = sum(1 for x in improvements if x >= 10)
    total = len(improvements)
    return [100*big_loss/total, 100*small_loss/total, 100*small_gain/total, 100*big_gain/total]

up_cats = categorize_improvement(up_stats['improvements'])
vulcan_cats = categorize_improvement(vulcan_stats['improvements'])

categories = ['Big\nloss', 'Small\nloss', 'Small\ngain', 'Big\ngain']
x_cat = np.arange(len(categories))
width = 0.35

bars1 = axes[1].bar(x_cat - width/2, up_cats, width, label='UP',
                    color=policies["UP"], edgecolor='black', linewidth=0.8, hatch='//')
axes[1].legend(fontsize=12)

bars2 = axes[1].bar(x_cat + width/2, vulcan_cats, width, label=f"{SYSTEM_NAME}",
                    color=policies[SYSTEM_NAME], edgecolor='black', linewidth=0.8, hatch='\\\\')

# Add percentage labels OUTSIDE bars (above them)
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        if height > 0.5:  # Only label if > 0.5%
            axes[1].text(bar.get_x() + bar.get_width()/2., height + 0.8,
                        f'{height:.0f}%',
                        ha='center', va='bottom', fontsize=9, weight='bold')

axes[1].set_ylabel('%age of traces', size=16)
axes[1].set_title('(b) Distribution of savings', size=16)
axes[1].set_xticks(x_cat)
axes[1].set_xticklabels(categories, fontsize=14)
axes[1].grid(axis='y', alpha=0.3, linewidth=0.6)
axes[1].set_ylim(0, 66)
axes[1].legend(fontsize=12, loc='upper center', framealpha=0.95, ncol=2)

fig.savefig("cbl-single-region.svg", bbox_inches="tight")

print(f"Saved to cbl-single-region.svg")
print(f"\nComputed values:")
print(f"  UP: ${up_stats['abs_mean']:.2f} ({up_stats['rel_mean']:.2f}%)")
print(f"  ADRS: ${adrs_stats['abs_mean']:.2f} ({adrs_stats['rel_mean']:.2f}%)")
print(f"  {SYSTEM_NAME} (no listeners): ${no_listener_stats['abs_mean']:.2f} ({no_listener_stats['rel_mean']:.2f}%)")
print(f"  {SYSTEM_NAME}: ${vulcan_stats['abs_mean']:.2f} ({vulcan_stats['rel_mean']:.2f}%)")