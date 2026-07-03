"""Plot the multi-region CBL results figure (Figure 7 in the paper).

Reads three full-eval JSONs (initial/greedy, ADRS, Vulcan), merges by
(scenario, trace), and produces a grouped bar chart of average cost per
scenario plus an "All" bar averaged across scenarios.

Usage:
    python plot_results.py --results-dir results --out multi-region-result.png
"""
import argparse
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCENARIO_LABELS = {
    "2_zones_same_region": "S1",
    "2_regions_east_west": "S2",
    "3_regions_diverse": "S3",
    "3_zones_same_region": "S4",
    "5_regions_high_diversity": "S5",
    "all_9_regions": "S6",
    "__all_scenarios__": "All",
}


def load(results_dir, name):
    with open(os.path.join(results_dir, name)) as f:
        return pd.DataFrame(json.load(f)["trace_results"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="cbl_multi_results")
    parser.add_argument("--out", default="multi-region-result.png")
    args = parser.parse_args()

    initial = load(args.results_dir, "full_eval_initial_program.json")
    adrs = load(args.results_dir, "full_eval_python_generic.json")
    vulcan = load(args.results_dir, "full_eval_vulcan_generic.json")

    df = (
        initial[["scenario", "trace", "cost"]].rename(columns={"cost": "initial"})
        .merge(adrs[["scenario", "trace", "cost"]].rename(columns={"cost": "adrs"}), on=["scenario", "trace"])
        .merge(vulcan[["scenario", "trace", "cost"]].rename(columns={"cost": "vulcan"}), on=["scenario", "trace"])
    )

    metrics = ["initial", "adrs", "vulcan"]
    order = [s for s in SCENARIO_LABELS if s in set(df["scenario"])]
    plot_df = df.groupby("scenario")[metrics].mean().reindex(order).reset_index()
    overall = pd.DataFrame([{"scenario": "__all_scenarios__", **df[metrics].mean().to_dict()}])
    plot_df = pd.concat([plot_df, overall], ignore_index=True)

    x = np.arange(len(plot_df))
    width = 0.2
    fig, ax = plt.subplots(figsize=(10, 4))
    for col, label, color, hatch, offset in [
        ("initial", "UP-RR", "#4C72B0", "...", -0.5 * width - width),
        ("adrs", "ADRS", "#DD8452", "\\\\\\", -0.5 * width),
        ("vulcan", "Vulcan", "#55A868", "xxx", 0.5 * width),
    ]:
        ax.bar(x + offset, plot_df[col], width, label=label,
               color=color, edgecolor="black", linewidth=1.0, hatch=hatch)

    ax.set_ylabel("Average cost (USD$)", fontsize=22)
    ax.set_xlabel("Scenario", fontsize=22)
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in plot_df["scenario"]], fontsize=20)
    ax.tick_params(axis="y", labelsize=20)
    ax.legend(frameon=True, fontsize=20, ncol=3, loc="upper center")
    ax.grid(axis="y", linestyle=":", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 190)

    fig.tight_layout()
    fig.savefig(args.out, dpi=200)
    print(f"wrote {args.out}")
    print()
    print(plot_df.assign(scenario=plot_df["scenario"].map(SCENARIO_LABELS)).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
