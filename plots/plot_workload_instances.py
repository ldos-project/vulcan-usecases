#!/usr/bin/env python3
"""
Compare baseline cache algorithms vs Vulcan on the w* traces (instances of different workloads).
"""
import argparse
import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pymongo

MONGO = "mongodb://localhost:27017/"

TRACES = [
    "wMSR.oracleGeneral.bin.zst",
    "wMetaCDN.oracleGeneral.bin.zst",
    "wMetaKVCache.oracleGeneral.bin.zst",
    "wMetaStorage.oracleGeneral.bin.zst",
    "wTencent.oracleGeneral.bin.zst",
    "wTwemCacheCluster50.oracleGeneral.bin.zst",
    "wTwemCacheCluster53.oracleGeneral.bin.zst",
    "wWikiMedia.oracleGeneral.bin.zst",
]
BASE_ALGOS = ["FIFO", "Cacheus", "LRU", "Sieve", "S3FIFO-0.1000-2", "LHD", "GDSF", "LeCaR", "LRB-OMR", "ThreeLCache-BMR"]
PLOT_ALGOS = ["Cacheus", "LRU", "Sieve", "S3FIFO-0.1000-2", "LHD", "GDSF", "LeCaR", "LRB-OMR", "ThreeLCache-BMR", "VulcanPQEvolve", "VulcanPQEvolve-NoListener"]

ALGO_COLORS = {
    "GDSF":            "#2E86C1",
    "Sieve":           "#1A5276",
    "S3FIFO-0.1000-2": "#0D680A",
    "LHD":             "#AED6F1",
    "VulcanPQEvolve":  "#F39C12",
    "VulcanPQEvolve-NoListener": "#D35400",
    "Belady":          "#7D3C98",
    "BeladySize":      "#7D3C98",
    "LRU":             "#B03A2E",
    "Cacheus":         "#7D6608",
    "LeCaR":           "#16A085",
    "LRB-OMR":         "#E91E63",
    "ThreeLCache-BMR": "#34495E",
}

DISPLAY = {
    "S3FIFO-0.1000-2": "S3-FIFO",
    "LRB-OMR":         "LRB",
    "ThreeLCache-BMR": "3L-BMR",
    "VulcanPQEvolve":  "Vulcan",
    "VulcanPQEvolve-NoListener": "Vulcan-NL",
}

TRACE_DISPLAY = {
    "wMSR":          "MSR (Block)",
    "wMetaCDN":      "Meta (CDN)",
    "wMetaKVCache":  "Meta (KV)",
    "wMetaStorage":  "Meta (Block)",
    "wTencent":      "Tencent (Object)",
    "wTwemCacheCluster50": "Twitter (KV1)",
    "wTwemCacheCluster53": "Twitter (KV2)",
    "wWikiMedia":    "WikiMedia (CDN)",
}
ALGO_MARKERS = {
    "GDSF":            "o",
    "Sieve":           "s",
    "S3FIFO-0.1000-2": "D",
    "LHD":             "^",
    "VulcanPQEvolve":  "*",
    "VulcanPQEvolve-NoListener": (4, 1, 45),
    "Belady":          "X",
    "BeladySize":      "X",
    "ARC":             "P",
    "LRU":             "v",
    "Cacheus":         "h",
    "LeCaR":           "p",
    "LRB-OMR":         ">",
    "ThreeLCache-BMR": "<",
}

VULCAN_VARIANTS = ["VulcanPQEvolve", "VulcanPQEvolve-NoListener"]


def oracle_for(ignore_size: bool) -> str:
    return "Belady" if ignore_size else "BeladySize"

# cache_size -> list of (variant_algo_key, instance_evaluations collection name)
VULCAN_COLLECTIONS = {
    0.1: [
        ("VulcanPQEvolve",            "instance_evaluations-10.0pct"),
        ("VulcanPQEvolve-NoListener", "instance_evaluations-nolistener-10.0pct"),
    ],
    0.001: [
        ("VulcanPQEvolve",            "instance_evaluations-0.1pct"),
        ("VulcanPQEvolve-NoListener", "instance_evaluations-nolistener-0.1pct"),
    ],
}


def trace_root(t: str) -> str:
    return t.replace(".oracleGeneral", "").replace(".bin", "").replace(".zst", "").replace("_chunk_000", "")


def fmt_size(b: int) -> str:
    v, units = float(b), ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.2f}{units[i]}"


def fetch_baselines(client, cache_size: float, ignore_size: bool = False, reproduce: bool = False):
    prefix = "REPRODUCED_" if reproduce else ""
    db = f"{prefix}Baselines_{'nosize' if ignore_size else 'size'}"
    col = client[db]["baselines_percent"]
    algos = BASE_ALGOS + [oracle_for(ignore_size)]
    rows = col.find({
        "trace_name": {"$in": TRACES},
        "cache_name": {"$in": algos},
        "percent": cache_size,
    })
    tbl, sizes = {}, {}
    for r in rows:
        tbl.setdefault(r["trace_name"], {})[r["cache_name"]] = r["miss_ratio"]
        sizes[r["trace_name"]] = int(r["cache_size"])
    return tbl, sizes


def fetch_vulcan(client, cache_size: float, ignore_size: bool = False, reproduce: bool = False):
    """Best (lowest miss_ratio) non-chunked Vulcan result per trace root, per variant.

    Returns {variant_key: {trace_root: best_miss_ratio}}. Missing collections are
    skipped silently so variants without data simply contribute no points.
    """
    prefix = "REPRODUCED_" if reproduce else ""
    db = f"{prefix}ChunkedTraces_{'nosize' if ignore_size else 'size'}"
    existing = set(client[db].list_collection_names())
    out = {}
    for variant, coll_name in VULCAN_COLLECTIONS[cache_size]:
        out[variant] = {}
        if coll_name not in existing:
            continue
        col = client[db][coll_name]
        for d in col.find({}, {"evaluation_results": 1}):
            for e in d.get("evaluation_results", []):
                name = e["trace_name"]
                if "_chunk_" in name:
                    continue
                root = trace_root(name)
                mr = e["miss_ratio"]
                cur = out[variant].get(root)
                if cur is None or mr < cur:
                    out[variant][root] = mr
    return out


def plot_mrr_bars(tbl, sizes, vulcan, cache_size, outpath, plot_algos):
    """Grouped bar chart of miss-ratio reduction over FIFO per trace."""
    traces = sorted(
        t for t in tbl.keys()
        if any(vulcan.get(var, {}).get(trace_root(t)) is not None for var in VULCAN_VARIANTS)
    )
    trace_labels = [TRACE_DISPLAY.get(trace_root(t), trace_root(t)) for t in traces]

    def mrr(trace, algo):
        f = tbl[trace].get("FIFO")
        if f is None or f == 0:
            return None
        if algo in VULCAN_VARIANTS:
            v = vulcan.get(algo, {}).get(trace_root(trace))
        else:
            v = tbl[trace].get(algo)
        if v is None:
            return None
        return (f - v) / f

    n_groups = len(traces)
    n_algos = len(plot_algos)
    bar_width = 0.8 / n_algos
    x = np.arange(n_groups)

    plt.figure(figsize=(max(8, n_groups * 2.2), 6.4))
    plt.rcParams.update({"font.size": 18})

    for i, algo in enumerate(plot_algos):
        offsets = x + (i - (n_algos - 1) / 2) * bar_width
        values = [mrr(t, algo) for t in traces]
        xs = [offsets[j] for j, v in enumerate(values) if v is not None]
        ys = [v for v in values if v is not None]
        plt.bar(
            xs, ys, width=bar_width,
            color=ALGO_COLORS.get(algo, "lightgrey"),
            edgecolor="black", linewidth=1.0,
            label=DISPLAY.get(algo, algo),
        )

    plt.axhline(y=0, color="black", linestyle="-", linewidth=0.8, alpha=0.4)
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.xticks(x, trace_labels, fontsize=18)
    plt.xlabel("Trace", fontsize=20)
    plt.ylabel("Miss Ratio Reduction\nfrom FIFO", fontsize=20)
    plt.title(f"cache_size = {cache_size}", fontsize=18)

    handles = [
        mpatches.Patch(facecolor=ALGO_COLORS.get(a, "lightgrey"),
                       edgecolor="black", label=DISPLAY.get(a, a))
        for a in plot_algos
    ]
    plt.legend(handles=handles, fontsize=16, ncol=(n_algos // 2 + 1),
               loc="upper center", bbox_to_anchor=(0.5, 1.22), frameon=False)

    plt.tight_layout()
    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    pdf_path = os.path.splitext(outpath)[0] + ".pdf"
    plt.savefig(pdf_path, bbox_inches="tight")
    print(f"Saved plot to {outpath} and {pdf_path}")


def plot_mrr_markers(tbl, sizes, vulcan, cache_size, outpath, plot_algos):
    """Per-trace miss-ratio reduction over FIFO shown as markers (one per algo)."""
    traces = sorted(
        t for t in tbl.keys()
        if any(vulcan.get(var, {}).get(trace_root(t)) is not None for var in VULCAN_VARIANTS)
    )
    trace_labels = [TRACE_DISPLAY.get(trace_root(t), trace_root(t)) for t in traces]

    def mrr(trace, algo):
        f = tbl[trace].get("FIFO")
        if f is None or f == 0:
            return None
        if algo in VULCAN_VARIANTS:
            v = vulcan.get(algo, {}).get(trace_root(trace))
        else:
            v = tbl[trace].get(algo)
        if v is None:
            return None
        return (f - v) / f

    n_groups = len(traces)
    y = np.arange(n_groups)

    # +0.31in over the original height makes room for the 3rd legend row so the
    # plotted area stays the size it had with the original 2-row legend.
    fig = plt.figure(figsize=(8.5, max(3.5, 1.5 + n_groups * 0.3) + 0.31))
    plt.rcParams.update({"font.size": 18})

    def draw(ax):
        """Draw the alternating row shading and every algo's markers on one axes."""
        for j in range(n_groups):
            if j % 2 == 0:
                ax.axhspan(j - 0.5, j + 0.5, color="lightgrey", alpha=0.25, zorder=0)
        hs = {}
        for algo in plot_algos:
            values = [mrr(t, algo) for t in traces]
            ys = [y[j] for j, v in enumerate(values) if v is not None]
            xs = [v for v in values if v is not None]
            is_vulcan = algo in VULCAN_VARIANTS
            hs[algo] = ax.scatter(
                xs, ys,
                marker=ALGO_MARKERS.get(algo, "o"),
                color=ALGO_COLORS.get(algo, "lightgrey"),
                edgecolor="black", linewidth=0.8,
                s=380 if is_vulcan else 180, alpha=0.7,
                label=DISPLAY.get(algo, algo), zorder=5 if is_vulcan else 3,
            )
        ax.axvline(x=0, color="black", linestyle="-", linewidth=0.8, alpha=0.4)
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        ax.set_ylim(-0.5, n_groups - 0.5)
        return hs

    # A single far-negative point (e.g. LRB collapsing on a trace) otherwise
    # stretches the x-axis and leaves a large empty band. Detect such points by
    # the gap that separates them from the bulk; when present, split the x-axis
    # into a narrow panel for the outliers and a wide panel for the bulk, joined
    # by diagonal break marks.
    all_x = [mrr(t, a) for a in plot_algos for t in traces if mrr(t, a) is not None]
    xs_sorted = sorted(all_x)
    xmax, span = xs_sorted[-1], xs_sorted[-1] - xs_sorted[0]
    left_clip = xs_sorted[0]
    for i in range(1, len(xs_sorted)):
        if xs_sorted[i - 1] < 0 and xs_sorted[i] - xs_sorted[i - 1] > 0.15 * span:
            left_clip = xs_sorted[i]
        else:
            break
    off_x = [v for v in all_x if v < left_clip]

    if off_x:
        omin, omax, w = min(off_x), max(off_x), xmax - left_clip
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 7], wspace=0.05)
        axL = fig.add_subplot(gs[0])
        axR = fig.add_subplot(gs[1], sharey=axL)
        draw(axL)
        handles = draw(axR)
        axL.set_xlim(omin - 0.06 * w, omax + 0.06 * w)
        axR.set_xlim(left_clip - 0.03 * w, xmax + 0.03 * w)
        axL.set_xticks(sorted({round(v, 2) for v in off_x}))
        axL.spines["right"].set_visible(False)
        axR.spines["left"].set_visible(False)
        axR.tick_params(axis="y", length=0)
        plt.setp(axR.get_yticklabels(), visible=False)
        axL.set_yticks(y)
        axL.set_yticklabels(trace_labels, fontsize=14)
        axL.set_ylabel("Trace", fontsize=20)
        main_ax, broken_axes = axR, (axL, axR)
    else:
        ax = fig.add_subplot(111)
        handles = draw(ax)
        ax.set_yticks(y)
        ax.set_yticklabels(trace_labels, fontsize=14)
        ax.set_ylabel("Trace", fontsize=20)
        ax.set_xlabel("Miss Ratio Reduction from FIFO", fontsize=20)
        main_ax, broken_axes = ax, None

    # 3-row legend with the partial last row centred as its own group. Measure
    # the height a full 3-row legend needs, reserve that band at the top, then
    # place the full rows and the centred remainder as two stacked legends in
    # figure coordinates inside it. The broken-axis figure is positioned by hand
    # (tight_layout can't handle the two-panel gridspec); the single axes keeps
    # tight_layout and is simply shrunk from the top to free the band.
    n_algos = len(plot_algos)
    ncol = -(-n_algos // 3)
    n_leg_rows = -(-n_algos // ncol)
    split = ncol * (n_leg_rows - 1)
    full_algos, rem_algos = plot_algos[:split], plot_algos[split:]
    lbls = lambda algos: [DISPLAY.get(a, a) for a in algos]
    cx = 0.35
    leg_kw = dict(fontsize=16, loc="lower center", frameon=False)

    tmp = main_ax.legend([handles[a] for a in plot_algos], lbls(plot_algos),
                         ncol=ncol, bbox_to_anchor=(0.5, 1.0),
                         bbox_transform=fig.transFigure, **leg_kw)
    fig.canvas.draw()
    band = tmp.get_window_extent().transformed(fig.transFigure.inverted()).height
    row_h = band / n_leg_rows
    tmp.remove()

    gap = 0.012
    if broken_axes is not None:
        axL, axR = broken_axes
        L, R, B = 0.16, 0.985, 0.16
        panel_top = 1 - band - gap
        H, W, wgap = panel_top - B, R - 0.16, 0.02
        wL = (W - wgap) / 15
        axL.set_position([L, B, wL, H])
        axR.set_position([L + wL + wgap, B, W - wL - wgap, H])
        fig.text((L + R) / 2, 0.045, "Miss Ratio Reduction from FIFO",
                 ha="center", va="center", fontsize=20)
        rx0, rx1, top = L, R, panel_top + gap
    else:
        plt.tight_layout()
        p = main_ax.get_position()
        main_ax.set_position([p.x0, p.y0, p.width, p.height - band - gap])
        rx0, rx1, top = p.x0, p.x1, main_ax.get_position().y1 + gap
    cx_fig = rx0 + cx * (rx1 - rx0)
    fkw = dict(bbox_transform=fig.transFigure, **leg_kw)
    if not full_algos or len(rem_algos) == ncol:
        main_ax.legend([handles[a] for a in plot_algos], lbls(plot_algos),
                       ncol=ncol, bbox_to_anchor=(cx_fig, top), **fkw)
    else:
        leg_rem = main_ax.legend([handles[a] for a in rem_algos], lbls(rem_algos),
                                 ncol=len(rem_algos), bbox_to_anchor=(cx_fig, top), **fkw)
        main_ax.add_artist(leg_rem)
        main_ax.legend([handles[a] for a in full_algos], lbls(full_algos),
                       ncol=ncol, bbox_to_anchor=(cx_fig, top + row_h), **fkw)

    if off_x:
        # diagonal break marks on the shared edge of the two panels
        d = 0.5
        mk = dict(marker=[(-1, -d), (1, d)], markersize=10, linestyle="none",
                  color="k", mec="k", mew=1, clip_on=False)
        axL.plot([1, 1], [0, 1], transform=axL.transAxes, **mk)
        axR.plot([0, 0], [0, 1], transform=axR.transAxes, **mk)

    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    pdf_path = os.path.splitext(outpath)[0] + ".pdf"
    plt.savefig(pdf_path, bbox_inches="tight")
    print(f"Saved plot to {outpath} and {pdf_path}")


def print_table(header, rows):
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    line = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths))
    print(line(header))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line(r))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-size", type=float, choices=list(VULCAN_COLLECTIONS), default=0.1,
                    help="Cache-size percent (0.1 or 0.001). Default: 0.1")
    ap.add_argument("--ignore-size", action="store_true", default=False,
                    help="Use Baselines_nosize / ChunkedTraces_nosize instead of the *_size DBs.")
    ap.add_argument("--plot", action="store_true", help="Also save a plot of MRR over FIFO.")
    ap.add_argument("--plot-type", choices=["bars", "markers"], default="markers",
                    help="Plot style: grouped bars or per-algo markers (default: markers).")
    ap.add_argument("--reproduce", action="store_true", default=False,
                    help="Use REPRODUCED_* databases instead of the originals.")
    args = ap.parse_args()

    client = pymongo.MongoClient(MONGO)
    oracle = oracle_for(args.ignore_size)
    tbl, sizes = fetch_baselines(client, args.cache_size, args.ignore_size, args.reproduce)
    vulcan = fetch_vulcan(client, args.cache_size, args.ignore_size, args.reproduce)

    algo_cols = list(BASE_ALGOS)
    disp_cols = [DISPLAY.get(a, a) for a in algo_cols]
    oracle_label = DISPLAY.get(oracle, oracle)

    traces_sorted = sorted(tbl.keys())

    variant_labels = [DISPLAY.get(v, v) for v in VULCAN_VARIANTS]
    mr_header = ["trace", "cache_size"] + disp_cols + variant_labels + [oracle_label]
    mr_rows = []
    for t in traces_sorted:
        row = [trace_root(t), fmt_size(sizes[t])]
        for a in algo_cols:
            v = tbl[t].get(a)
            row.append(f"{v:.4f}" if v is not None else "-")
        for var in VULCAN_VARIANTS:
            vk = vulcan.get(var, {}).get(trace_root(t))
            row.append(f"{vk:.4f}" if vk is not None else "-")
        b = tbl[t].get(oracle)
        row.append(f"{b:.4f}" if b is not None else "-")
        mr_rows.append(row)

    print(f"=== Miss ratios (cache_size={args.cache_size}) ===")
    print_table(mr_header, mr_rows)

    imp_header = ["trace", "cache_size"] + [c for c in disp_cols if c != "FIFO"] + variant_labels + [oracle_label]
    imp_rows = []
    for t in traces_sorted:
        f = tbl[t].get("FIFO")
        row = [trace_root(t), fmt_size(sizes[t])]
        pct = lambda v: f"{(f - v) / f * 100:+.2f}%" if (f and v is not None) else "-"
        for a in algo_cols:
            if a == "FIFO":
                continue
            row.append(pct(tbl[t].get(a)))
        for var in VULCAN_VARIANTS:
            row.append(pct(vulcan.get(var, {}).get(trace_root(t))))
        row.append(pct(tbl[t].get(oracle)))
        imp_rows.append(row)

    print()
    print(f"=== % improvement over FIFO (cache_size={args.cache_size}) ===")
    print_table(imp_header, imp_rows)

    if args.plot:
        pct_suffix = f"{args.cache_size * 100:.1f}pct"
        suffix = "_nosize" if args.ignore_size else ""
        prefix = "REPRODUCED_" if args.reproduce else ""
        outpath = f"figures/{prefix}comparison{suffix}_{pct_suffix}_{args.plot_type}.png"
        # plot_algos = PLOT_ALGOS + [oracle]
        plot_algos = PLOT_ALGOS
        plot_fn = plot_mrr_bars if args.plot_type == "bars" else plot_mrr_markers
        plot_fn(tbl, sizes, vulcan, args.cache_size, outpath, plot_algos)


if __name__ == "__main__":
    main()
