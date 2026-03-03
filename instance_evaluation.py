#!/usr/bin/env python3

"""
Run run_algo.o on chunked trace files for a given instance, using cache sizes
computed from full trace footprints. Delegates to evaluate_cache_algo for build,
execution, and optional MongoDB insertion.
"""

import sys
import csv
import argparse

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_cache import evaluate_cache_algo
from util import TRACES_CSV


def parse_args():
    parser = argparse.ArgumentParser(description=(
        "Run caches on chunked traces and optionally store results in MongoDB."))
    parser.add_argument(
        "full_trace_dir",
        type=Path,
        help="Directory containing the complete trace files (these are the instances)",
    )
    parser.add_argument(
        "--traces-csv",
        type=Path,
        default=TRACES_CSV,
        help="Path to traces.csv (trace footprints and cluster mapping)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to a .cpp file to use as LLMCode.h (if not set, uses current LLMCode.h)",
    )
    parser.add_argument(
        "--cache-size-percent",
        type=float,
        default=0.1,
        help="Cache size as a fraction of the full trace footprint (default: 0.1)",
    )
    parser.add_argument(
        "--collection",
        default="instance_evaluations",
        help="MongoDB collection name (default: instance_evaluations)",
    )
    parser.add_argument(
        "--ignore-size",
        action="store_true",
        help="Ignore object sizes (use object counts for cache sizing)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of parallel threads (default: 4)",
    )
    parser.add_argument(
        "--insert-mongo",
        action="store_true",
        help="Insert results into MongoDB",
    )
    parser.add_argument(
        "--instance",
        type=int,
        default=None,
        help="Cluster ID to run",
    )
    args = parser.parse_args()

    return args


def find_all_traces(trace_dir):
    if not trace_dir.exists() or not trace_dir.is_dir():
        raise NotADirectoryError(f"Invalid trace directory: {trace_dir}")
    return sorted([
        path for path in trace_dir.glob("*.zst") if path.is_file()
    ])


def get_traces_for_cluster(traces_csv, full_trace_dir, cluster_id):
    traces = []
    with open(traces_csv, "r") as f:
        for row in csv.DictReader(f):
            if int(row["cluster"]) != cluster_id:
                continue
            trace_file_name = row["trace_name"] + ".oracleGeneral.bin.zst"
            traces.append(full_trace_dir / trace_file_name)
    return traces


def main():
    args = parse_args()

    if args.instance is not None:
        try:
            trace_files = get_traces_for_cluster(args.traces_csv, args.full_trace_dir, args.instance)
        except Exception as exc:
            print(f"Error reading traces CSV: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            trace_files = find_all_traces(args.full_trace_dir)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    if not trace_files:
        print(f"No traces found.", file=sys.stderr)
        sys.exit(1)

    llm_code = None
    if args.file is not None:
        with open(args.file, "r") as f:
            llm_code = f.read()

    print(f"Running on {len(trace_files)} trace(s) using {args.threads} thread(s).")

    result = evaluate_cache_algo(
        llm_code=llm_code,
        traces=[str(tf.resolve()) for tf in trace_files],
        traces_csv_path=str(args.traces_csv),
        ignore_size=args.ignore_size,
        cache_size_percent=args.cache_size_percent,
        insert_into_mongo=args.insert_mongo,
        collection_name=args.collection,
        max_parallel_workers=args.threads,
    )
    print(result)


if __name__ == "__main__":
    main()
