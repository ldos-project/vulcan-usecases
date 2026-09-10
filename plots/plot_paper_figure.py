#!/usr/bin/env python3
"""Reproduce the memory-tiering paper figure from run_experiment.py output.

Grouped bar chart of *normalized performance* (relative to the ARMS baseline = 1.0)
for each workload: the naive `seed` heuristic vs the Vulcan `synthesized` heuristic.
Higher is better; the dashed line marks the ARMS baseline.

Usage:
    python plots/plot_paper_figure.py [results.json] [--out tiering_normalized]
"""
import argparse
import csv
import json
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Fixed left-to-right workload order, matching the paper figure.
ORDER = ["gapbc", "gappr", "gups", "silo"]

# Paper aesthetic: gray seed bar, steel-blue synthesized bar, black edges.
COLORS = {"seed": "#c9c9c9", "synthesized": "#4a7fb5"}
LABELS = {"seed": "seed heuristic", "synthesized": "synthesized heuristic"}


def load_results(path):
    """Return (meta, data) from either a run_experiment.py JSON or a results CSV.

    CSV columns: workload,policy,rep,metric,value,higher_is_better,normalized_vs_arms
    (the committed reference `results_c220g5.csv` uses this form).
    """
    if str(path).endswith(".csv"):
        data, pm, hib = {}, {}, {}
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                wl, pol, metric = row["workload"], row["policy"], row["metric"]
                data.setdefault(wl, {}).setdefault(pol, []).append({metric: float(row["value"])})
                pm[wl] = metric
                hib[wl] = str(row["higher_is_better"]).strip().lower() == "true"
        return {"primary_metric": pm, "higher_is_better": hib}, data
    with open(path) as f:
        blob = json.load(f)
    return blob["meta"], blob["data"]


def normalize(value, baseline, higher_is_better):
    if value is None or baseline in (None, 0):
        return None
    return value / baseline if higher_is_better else baseline / value


def series(data, meta, workload, policy):
    """Normalized (mean, std) for one (workload, policy) vs its ARMS baseline."""
    metric = meta["primary_metric"][workload]
    hib = meta["higher_is_better"][workload]

    def vals(p):
        return [r[metric] for r in data[workload].get(p, [])
                if isinstance(r, dict) and metric in r]

    base = vals("baseline_arms")
    base_mean = statistics.fmean(base) if base else None
    norm = [n for n in (normalize(v, base_mean, hib) for v in vals(policy))
            if n is not None]
    if not norm:
        return None, None
    return statistics.fmean(norm), (statistics.stdev(norm) if len(norm) > 1 else 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="?", default="results_c220g5.csv",
                    help="results CSV (default: the committed results_c220g5.csv) "
                         "or a run_experiment.py results.json")
    ap.add_argument("--out", default="tiering_normalized",
                    help="Output basename (writes .png and .pdf)")
    args = ap.parse_args()

    meta, data = load_results(args.results)

    workloads = [w for w in ORDER if w in data] + [w for w in data if w not in ORDER]

    fig, ax = plt.subplots(figsize=(7, 4))
    width = 0.38
    x = np.arange(len(workloads))

    for i, policy in enumerate(["seed", "synthesized"]):
        means, errs = [], []
        for w in workloads:
            m, s = series(data, meta, w, policy)
            means.append(np.nan if m is None else m)
            errs.append(0.0 if s is None else s)
        offset = (i - 0.5) * width
        ax.bar(x + offset, means, width, yerr=errs, capsize=3,
               color=COLORS[policy], edgecolor="black", linewidth=0.8,
               label=LABELS[policy], error_kw=dict(lw=1))

    ax.axhline(1.0, linestyle="--", color="black", linewidth=1.2,
               label="baseline (ARMS)", zorder=0)

    ax.set_ylabel("Normalized perf.", fontsize=16)
    ax.set_xticks(x)
    ax.set_xticklabels(workloads, fontsize=15)
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.set_ylim(0.0, 1.28)
    ax.tick_params(axis="y", labelsize=13)
    # Baseline dashed first, then seed (gray), then synthesized (blue).
    handles, labels = ax.get_legend_handles_labels()
    order = [labels.index("baseline (ARMS)"), labels.index("seed heuristic"),
             labels.index("synthesized heuristic")]
    ax.legend([handles[i] for i in order], [labels[i] for i in order],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3,
              frameon=False, fontsize=12)

    plt.tight_layout()
    for ext in ("png", "pdf"):
        path = f"{args.out}.{ext}"
        plt.savefig(path, bbox_inches="tight", dpi=200)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
