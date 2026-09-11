#!/usr/bin/env python3
"""
Verify that the REPRODUCED_* databases written by evaluate_all.py agree with the
originals restored from the Zenodo dump.

Compares every cell that feeds the paper figures:
  - baselines:  Baselines_{size,nosize}.baselines_percent, per
                (trace, cache_name, percent), for the BASE_ALGOS actually
                plotted -- the Belady/ARC entries in the dump are not plotted
                and are ignored here.
  - heuristics: ChunkedTraces_{size,nosize}.instance_evaluations*, per
                (collection, trace), comparing the best (lowest) miss_ratio the
                plots would pick.

Miss ratios are compared to 3 decimal places; anything finer is run-to-run
noise. Missing databases, collections, or cells are reported as MISSING rather
than silently skipped -- a reproduction that is quietly incomplete looks
identical to one that matches if you only diff the numbers that are present.

Usage: python3 verify_reproduction.py [--tol 0.0005] [--verbose]

Exits 0 if everything matches, 1 if any cell differs or is missing.
"""
import argparse
import sys

import pymongo

from plot_workload_instances import (
    BASE_ALGOS,
    MONGO,
    TRACES,
    VULCAN_COLLECTIONS,
    trace_root,
)

CACHE_SIZES = [0.1, 0.001]
MODES = ["size", "nosize"]


def fmt(v):
    return "-" if v is None else f"{v:.6f}"


def check_baselines(client, mode, tol, rows):
    """Compare baseline miss ratios for one size-mode. Appends to rows."""
    db = f"Baselines_{mode}"
    ref, rep = client[db]["baselines_percent"], client[f"REPRODUCED_{db}"]["baselines_percent"]

    def index(col):
        out = {}
        for r in col.find({"trace_name": {"$in": TRACES},
                           "cache_name": {"$in": BASE_ALGOS}},
                          {"trace_name": 1, "cache_name": 1, "percent": 1, "miss_ratio": 1}):
            out[(r["percent"], trace_root(r["trace_name"]), r["cache_name"])] = r["miss_ratio"]
        return out

    a, b = index(ref), index(rep)
    for pct in CACHE_SIZES:
        for trace in [trace_root(t) for t in TRACES]:
            for algo in BASE_ALGOS:
                key = (pct, trace, algo)
                rows.append((f"baseline/{mode}", f"{pct*100:.1f}pct", trace, algo,
                             a.get(key), b.get(key), tol))


def check_heuristics(client, mode, tol, rows):
    """Compare best-per-trace Vulcan miss ratios for one size-mode."""
    db = f"ChunkedTraces_{mode}"
    ref_db, rep_db = client[db], client[f"REPRODUCED_{db}"]
    ref_cols, rep_cols = set(ref_db.list_collection_names()), set(rep_db.list_collection_names())

    def best(database, present, coll):
        """{trace_root: min miss_ratio}, or None if the collection is absent."""
        if coll not in present:
            return None
        out = {}
        for d in database[coll].find({}, {"evaluation_results": 1}):
            for e in d.get("evaluation_results", []):
                if "_chunk_" in e["trace_name"]:
                    continue
                root = trace_root(e["trace_name"])
                mr = e["miss_ratio"]
                if root not in out or mr < out[root]:
                    out[root] = mr
        return out

    for pct in CACHE_SIZES:
        for variant, coll in VULCAN_COLLECTIONS[pct]:
            a, b = best(ref_db, ref_cols, coll), best(rep_db, rep_cols, coll)
            if a is None or b is None:
                where = "original" if a is None else "REPRODUCED"
                print(f"  MISSING COLLECTION  {db}.{coll} absent from {where}")
                rows.append((f"heuristic/{mode}", f"{pct*100:.1f}pct", "(collection)",
                             coll, None, None, tol))
                continue
            for trace in [trace_root(t) for t in TRACES]:
                rows.append((f"heuristic/{mode}", f"{pct*100:.1f}pct", trace, variant,
                             a.get(trace), b.get(trace), tol))


def classify(orig, repro, tol):
    if orig is None and repro is None:
        return "MISSING-BOTH"
    if orig is None:
        return "EXTRA"
    if repro is None:
        return "MISSING"
    return "OK" if abs(orig - repro) <= tol else "DIFF"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tol", type=float, default=5e-4,
                    help="max allowed |miss_ratio| difference (default 5e-4, "
                         "i.e. agreement to 3 decimal places)")
    ap.add_argument("--verbose", action="store_true",
                    help="list every cell, not just problems")
    args = ap.parse_args()

    client = pymongo.MongoClient(MONGO)
    dbs = set(client.list_database_names())
    for mode in MODES:
        for req in [f"Baselines_{mode}", f"ChunkedTraces_{mode}"]:
            for name in [req, f"REPRODUCED_{req}"]:
                if name not in dbs:
                    print(f"MISSING DATABASE: {name}")

    rows = []
    for mode in MODES:
        check_baselines(client, mode, args.tol, rows)
        check_heuristics(client, mode, args.tol, rows)

    counts = {}
    problems = []
    for group, pct, trace, algo, orig, repro, tol in rows:
        verdict = classify(orig, repro, tol)
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict != "OK" or args.verbose:
            problems.append((verdict, group, pct, trace, algo, orig, repro))

    if problems:
        print(f"\n{'verdict':<13} {'group':<17} {'cache':<8} {'trace':<20} "
              f"{'algo':<28} {'original':>10} {'reproduced':>10} {'delta':>10}")
        print("-" * 122)
        for verdict, group, pct, trace, algo, orig, repro in problems:
            delta = f"{repro - orig:+.6f}" if (orig is not None and repro is not None) else "-"
            print(f"{verdict:<13} {group:<17} {pct:<8} {trace:<20} {algo:<28} "
                  f"{fmt(orig):>10} {fmt(repro):>10} {delta:>10}")

    print(f"\nCompared {len(rows)} cells at tol={args.tol:g}")
    for verdict in ["OK", "DIFF", "MISSING", "EXTRA", "MISSING-BOTH"]:
        if verdict in counts:
            print(f"  {verdict:<13} {counts[verdict]}")

    bad = sum(counts.get(v, 0) for v in ["DIFF", "MISSING", "EXTRA", "MISSING-BOTH"])
    print("\nRESULT:", "MATCH" if bad == 0 else f"MISMATCH ({bad} cells)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
