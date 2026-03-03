#!/usr/bin/env python3
"""
Summarize how Vulcan ranks against baselines (and the Belady oracle) across all
workload instances.

An "instance" is a (trace, cache_size, size-mode) triple. For the TRACES list in
plot_workload_instances.py, cache sizes {0.1, 0.001}, and size-modes
{size, nosize}, we expect 10 * 2 * 2 = 40 instances (a few may be missing).

For each instance we bucket Vulcan into one of:
  - better: strictly beats every baseline
  - within-5% / within-10%: Vulcan miss_ratio <= 1.05x / 1.10x best baseline
  - worse: otherwise

Against the oracle (Belady for nosize, BeladySize for size) we additionally
report:
  - gap_pct     = (vulcan - oracle) / oracle * 100
  - mrr_recovered = (fifo - vulcan) / (fifo - oracle)   (1.0 == optimal)

Usage: python3 get_instance_aggregate.py [--oracle]
"""
import argparse
import pymongo

from plot_workload_instances import (
    BASE_ALGOS,
    DISPLAY,
    MONGO,
    TRACES,
    VULCAN_COLLECTIONS,
    VULCAN_VARIANTS,
    fetch_baselines,
    fetch_vulcan,
    oracle_for,
    trace_root,
)


CACHE_SIZES = [0.1, 0.001]
SIZE_MODES = [False, True]  # ignore_size flag

BASELINE_BUCKETS = ["better", "within-5%", "within-10%", "worse", "worse-than-all"]
ORACLE_BUCKETS = ["matches-or-beats", "within-5%", "within-10%", "worse"]


def classify_vs_baseline(vulcan_mr: float, best_mr: float, worst_mr: float) -> str:
    if vulcan_mr < best_mr:
        return "better"
    if vulcan_mr <= best_mr * 1.05:
        return "within-5%"
    if vulcan_mr <= best_mr * 1.10:
        return "within-10%"
    if vulcan_mr > worst_mr:
        return "worse-than-all"
    return "worse"


def classify_vs_oracle(vulcan_mr: float, oracle_mr: float) -> str:
    # Oracle is optimal; "better" would indicate data issues, so we fold it in.
    if vulcan_mr <= oracle_mr:
        return "matches-or-beats"
    if vulcan_mr <= oracle_mr * 1.05:
        return "within-5%"
    if vulcan_mr <= oracle_mr * 1.10:
        return "within-10%"
    return "worse"


def summary_row(bucket_name, rows, denom, width=12):
    n = len(rows)
    share = (n / denom * 100) if denom else 0.0
    print(f"{bucket_name:<{width}} {n:>6} {share:>7.1f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oracle", action="store_true",
                    help="Also analyze Vulcan vs the Belady/BeladySize oracle.")
    ap.add_argument("--detail", action="store_true",
                    help="Print the per-instance detail table for each variant.")
    args = ap.parse_args()

    client = pymongo.MongoClient(MONGO)

    fetched = {}
    for cache_size in CACHE_SIZES:
        if cache_size not in VULCAN_COLLECTIONS:
            continue
        for ignore_size in SIZE_MODES:
            tbl, _ = fetch_baselines(client, cache_size, ignore_size)
            vulcan_all = fetch_vulcan(client, cache_size, ignore_size)
            fetched[(cache_size, ignore_size)] = (tbl, vulcan_all)

    per_variant_results = {}
    for variant in VULCAN_VARIANTS:
        baseline_buckets = {b: [] for b in BASELINE_BUCKETS}
        oracle_buckets = {b: [] for b in ORACLE_BUCKETS}
        instances = []
        missing = []

        for (cache_size, ignore_size), (tbl, vulcan_all) in fetched.items():
            mode = "nosize" if ignore_size else "size"
            oracle_algo = oracle_for(ignore_size)
            vulcan = vulcan_all.get(variant, {})

            for trace in TRACES:
                root = trace_root(trace)
                baselines = tbl.get(trace)
                v_mr = vulcan.get(root)
                if baselines is None or v_mr is None:
                    missing.append((trace, cache_size, mode, "no vulcan/baseline row"))
                    continue

                baseline_mrs = {
                    a: baselines[a]
                    for a in BASE_ALGOS
                    if a in baselines and a != oracle_algo
                }
                if not baseline_mrs:
                    missing.append((trace, cache_size, mode, "no baseline algos"))
                    continue

                best_algo, best_mr = min(baseline_mrs.items(), key=lambda kv: kv[1])
                worst_mr = max(baseline_mrs.values())
                b_bucket = classify_vs_baseline(v_mr, best_mr, worst_mr)

                oracle_mr = baselines.get(oracle_algo) if args.oracle else None
                fifo_mr = baselines.get("FIFO") if args.oracle else None
                o_bucket = None
                gap_pct = None
                mrr_recovered = None
                if args.oracle and oracle_mr is not None:
                    o_bucket = classify_vs_oracle(v_mr, oracle_mr)
                    gap_pct = (v_mr - oracle_mr) / oracle_mr * 100 if oracle_mr > 0 else None
                    if fifo_mr is not None and fifo_mr > oracle_mr:
                        mrr_recovered = (fifo_mr - v_mr) / (fifo_mr - oracle_mr)

                rec = {
                    "trace": root,
                    "cache_size": cache_size,
                    "mode": mode,
                    "vulcan": v_mr,
                    "best_algo": best_algo,
                    "best_mr": best_mr,
                    "delta_pct": (v_mr - best_mr) / best_mr * 100,
                    "oracle_algo": oracle_algo,
                    "oracle_mr": oracle_mr,
                    "gap_pct": gap_pct,
                    "mrr_recovered": mrr_recovered,
                    "b_bucket": b_bucket,
                    "o_bucket": o_bucket,
                }
                instances.append(rec)
                baseline_buckets[b_bucket].append(rec)
                if o_bucket is not None:
                    oracle_buckets[o_bucket].append(rec)

        per_variant_results[variant] = {
            "baseline_buckets": baseline_buckets,
            "oracle_buckets": oracle_buckets,
            "instances": instances,
            "missing": missing,
        }

    for variant in VULCAN_VARIANTS:
        res = per_variant_results[variant]
        baseline_buckets = res["baseline_buckets"]
        oracle_buckets = res["oracle_buckets"]
        instances = res["instances"]
        missing = res["missing"]
        label = DISPLAY.get(variant, variant)

        print("#" * 72)
        print(f"# {label}  ({variant})")
        print("#" * 72)

        total = len(instances) + len(missing)
        print(f"Total instances examined: {total}")
        print(f"Classified: {len(instances)}   Missing data: {len(missing)}")
        print()

        print(f"--- {label} vs best non-oracle baseline ---")
        print(f"{'Bucket':<12} {'Count':>6} {'Share':>8}")
        print("-" * 28)
        for b in BASELINE_BUCKETS:
            summary_row(b, baseline_buckets[b], len(instances))
        print()

        if args.oracle:
            oracle_classified = sum(len(v) for v in oracle_buckets.values())
            print(f"--- {label} vs oracle ({oracle_classified} instances with oracle data) ---")
            print(f"{'Bucket':<18} {'Count':>6} {'Share':>8}")
            print("-" * 34)
            for b in ORACLE_BUCKETS:
                summary_row(b, oracle_buckets[b], oracle_classified, width=18)

            gaps = [r["gap_pct"] for r in instances if r["gap_pct"] is not None]
            mrrs = [r["mrr_recovered"] for r in instances if r["mrr_recovered"] is not None]
            if gaps:
                gaps_sorted = sorted(gaps)
                mid = len(gaps_sorted) // 2
                median = (gaps_sorted[mid] if len(gaps_sorted) % 2
                          else 0.5 * (gaps_sorted[mid - 1] + gaps_sorted[mid]))
                print()
                print(f"Gap to oracle: mean {sum(gaps) / len(gaps):+.2f}%   "
                      f"median {median:+.2f}%   "
                      f"min {min(gaps):+.2f}%   max {max(gaps):+.2f}%")
            if mrrs:
                print(f"FIFO->oracle MRR recovered: mean {sum(mrrs) / len(mrrs):.3f}   "
                      f"min {min(mrrs):.3f}   max {max(mrrs):.3f}   (1.0 == optimal)")
            print()

        if args.detail:
            print("=== per-instance detail ===")
            header = (f"{'trace':<22} {'cache':>7} {'mode':>7} "
                      f"{'vulcan':>9} {'best':>9} {'best_algo':<18} {'Δbase%':>8} "
                      f"{'vs-base':<11}")
            if args.oracle:
                header += f" {'oracle':>9} {'gap%':>8} {'recov':>7} {'vs-oracle':<18}"
            print(header)
            for r in sorted(instances, key=lambda r: (r["cache_size"], r["mode"], r["trace"])):
                line = (f"{r['trace']:<22} {r['cache_size']:>7} {r['mode']:>7} "
                        f"{r['vulcan']:>9.4f} {r['best_mr']:>9.4f} {r['best_algo']:<18} "
                        f"{r['delta_pct']:>+8.2f} "
                        f"{r['b_bucket']:<11}")
                if args.oracle:
                    oracle_mr = f"{r['oracle_mr']:.4f}" if r["oracle_mr"] is not None else "-"
                    gap = f"{r['gap_pct']:+.2f}" if r["gap_pct"] is not None else "-"
                    recov = f"{r['mrr_recovered']:.3f}" if r["mrr_recovered"] is not None else "-"
                    o_bucket = r["o_bucket"] or "-"
                    line += f" {oracle_mr:>9} {gap:>8} {recov:>7} {o_bucket:<18}"
                print(line)
            print()

        if missing:
            print(f"=== missing ({len(missing)}) ===")
            for trace, cache_size, mode, reason in missing:
                print(f"  {trace_root(trace)}  cache={cache_size}  mode={mode}  ({reason})")
            print()

    if "VulcanPQEvolve" in per_variant_results and "VulcanPQEvolve-NoListener" in per_variant_results:
        thor_idx = {(r["cache_size"], r["mode"], r["trace"]): r["vulcan"]
                    for r in per_variant_results["VulcanPQEvolve"]["instances"]}
        nolist_idx = {(r["cache_size"], r["mode"], r["trace"]): r["vulcan"]
                      for r in per_variant_results["VulcanPQEvolve-NoListener"]["instances"]}

        thor_label = DISPLAY.get("VulcanPQEvolve", "VulcanPQEvolve")
        nolist_label = DISPLAY.get("VulcanPQEvolve-NoListener", "VulcanPQEvolve-NoListener")

        print("#" * 72)
        print(f"# {thor_label} vs {nolist_label}")
        print("#" * 72)

        pairs = []
        for key, thor_mr in thor_idx.items():
            nolist_mr = nolist_idx.get(key)
            if nolist_mr is None or nolist_mr == 0:
                continue
            improvement = (nolist_mr - thor_mr) / nolist_mr * 100
            pairs.append((key, thor_mr, nolist_mr, improvement))

        if not pairs:
            print(f"No overlapping instances between {thor_label} and {nolist_label}.")
            print()
        else:
            improvements = [p[3] for p in pairs]
            improvements_sorted = sorted(improvements)
            mid = len(improvements_sorted) // 2
            median = (improvements_sorted[mid] if len(improvements_sorted) % 2
                      else 0.5 * (improvements_sorted[mid - 1] + improvements_sorted[mid]))
            n_better = sum(1 for v in improvements if v > 0)
            print(f"Overlapping instances: {len(pairs)}   "
                  f"{thor_label} better in {n_better}/{len(pairs)}")
            print(f"Improvement of {thor_label} over {nolist_label} (miss_ratio):")
            print(f"  mean   {sum(improvements) / len(improvements):+.2f}%")
            print(f"  median {median:+.2f}%")
            print(f"  min    {min(improvements):+.2f}%   max {max(improvements):+.2f}%")
            print()

            if args.detail:
                print("=== per-instance Thor vs Thor-NoListener ===")
                print(f"{'trace':<22} {'cache':>7} {'mode':>7} "
                      f"{'thor':>9} {'no-list':>9} {'Δ%':>8}")
                for (cs, mode, trace), thor_mr, nolist_mr, imp in sorted(pairs):
                    print(f"{trace:<22} {cs:>7} {mode:>7} "
                          f"{thor_mr:>9.4f} {nolist_mr:>9.4f} {imp:>+8.2f}")
                print()


if __name__ == "__main__":
    main()
