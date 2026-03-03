#!/usr/bin/env python3

"""
Orchestrates an evolutionary search + instance evaluation for all clusters with >= min_traces traces.

For each qualifying cluster (not skipped):
  1. Runs the selected framework's runner (openevolve or shinka)
  2. Runs instance_evaluation.py from the repo root using the best evolved program
"""

import csv
import sys
import argparse
import subprocess

from collections import Counter
from pathlib import Path
from util import TRACES_CSV

REPO_ROOT = Path(__file__).parent
OPENEVOLVE_DIR = REPO_ROOT / "openevolve"
SHINKA_DIR = REPO_ROOT / "shinka"


def parse_args():
    parser = argparse.ArgumentParser(description="Run evolutionary search + evaluation pipeline for each cluster.")
    parser.add_argument("--framework", choices=["openevolve", "shinka"], default="openevolve",
                        help="Evolutionary search framework to use (default: openevolve)")
    parser.add_argument("--traces-csv", type=Path, default=TRACES_CSV,
                        help="Path to traces.csv (trace footprints and cluster mapping)")
    parser.add_argument("--traces-dir", required=True, type=Path,
                        help="Path to full traces directory (must have chunked/ subdir with chunked traces)")
    parser.add_argument("--config", type=Path, default=None,
                        help="Framework config file. Defaults: openevolve -> config.yaml, shinka -> shinka.yaml")
    parser.add_argument("--min-traces", type=int, default=50,
                        help="Minimum number of traces for a cluster to be included (default: 50)")
    parser.add_argument("--skip", type=int, nargs="+", default=[],
                        help="Cluster IDs to skip")
    parser.add_argument("--collection", default="instance_evaluations",
                        help="MongoDB collection for instance_evaluation (default: instance_evaluations)")
    parser.add_argument("--ignore-size", action="store_true", default=False,
                        help="Ignore object sizes (use object counts for cache sizing)")
    parser.add_argument("--output-dirname", default="results", type=str,
                        help="Name of directory (relative to framework dir) to save results (default: results)")
    parser.add_argument("--cache-size-percent", type=float, default=0.1,
                        help="Cache size as a fraction of the full trace footprint (default: 0.1)")
    parser.add_argument("--use_anvil", action="store_true", default=False,
                        help="Gate each candidate through anvil --gate.")
    return parser.parse_args()


def get_qualifying_clusters(traces_csv, min_traces):
    counts = Counter()
    with open(traces_csv, "r") as f:
        for row in csv.DictReader(f):
            counts[int(row["cluster"])] += 1
    return sorted(c for c, n in counts.items() if n >= min_traces)


def run(cmd, cwd):
    print(f"\n[running in {cwd}]\n  {' '.join(str(a) for a in cmd)}\n")
    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        print(f"Command failed with exit code {proc.returncode}", file=sys.stderr)
        sys.exit(proc.returncode)


def build_openevolve_cmd(args, cluster, chunked_traces_dir, output_dir, traces_csv, config):
    relative_config = config.resolve().relative_to(OPENEVOLVE_DIR.resolve())
    cmd = [
        "python", "openevolve_runner.py",
        "initial_program.cpp",
        "openevolve_evaluator.py",
        "--traces-dir", str(chunked_traces_dir.resolve()),
        "--traces-csv", str(traces_csv.resolve()),
        "--instance", str(cluster),
        "--insert-mongo",
        "--config", str(relative_config),
        "--cache-size-percent", str(args.cache_size_percent),
        "--output", str(output_dir.resolve()),
    ]
    if args.ignore_size:
        cmd.append("--ignore-size")
    if args.use_anvil:
        cmd.append("--use_anvil")
    return cmd, OPENEVOLVE_DIR, output_dir / "best" / "best_program.cpp"


def build_shinka_cmd(args, cluster, chunked_traces_dir, output_dir, traces_csv, config):
    relative_config = config.resolve().relative_to(SHINKA_DIR.resolve())
    cmd = [
        "python", "shinka_runner.py",
        "--traces-dir", str(chunked_traces_dir.resolve()),
        "--traces-csv", str(traces_csv.resolve()),
        "--instance", str(cluster),
        "--insert-mongo",
        "--config", str(relative_config),
        "--cache-size-percent", str(args.cache_size_percent),
        "--num_generations", str(50),
        "--task-dir", ".",
        "--results_dir", str(output_dir.resolve()),
    ]
    if args.ignore_size:
        cmd.append("--ignore-size")
    if args.use_anvil:
        cmd.append("--use_anvil")
    return cmd, SHINKA_DIR, output_dir / "best" / "main.cpp"


FRAMEWORK_DISPATCH = {
    "openevolve": {
        "dir": OPENEVOLVE_DIR,
        "default_config": "config.yaml",
        "build_cmd": build_openevolve_cmd,
    },
    "shinka": {
        "dir": SHINKA_DIR,
        "default_config": "shinka.yaml",
        "build_cmd": build_shinka_cmd,
    },
}


def main():
    args = parse_args()

    framework = FRAMEWORK_DISPATCH[args.framework]
    framework_dir = framework["dir"]
    config = args.config if args.config is not None else framework_dir / framework["default_config"]

    traces_csv = Path(args.traces_csv)
    if not traces_csv.exists():
        print(f"traces.csv not found at {traces_csv}. Please provide a valid path using --traces-csv.", file=sys.stderr)
        sys.exit(1)

    clusters = get_qualifying_clusters(traces_csv, args.min_traces)
    clusters = [c for c in clusters if c not in args.skip]

    if not clusters:
        print("No qualifying clusters found.")
        sys.exit(0)

    output_suffix = Path(traces_csv).stem
    print(f"Clusters to process: {clusters} (output suffix: {output_suffix})")

    chunked_traces_dir = args.traces_dir / "chunked"
    if not chunked_traces_dir.exists() or not chunked_traces_dir.is_dir():
        print(f"Chunked traces directory not found at {chunked_traces_dir}. Please ensure the chunked traces are located in a 'chunked' subdirectory of --traces-dir.", file=sys.stderr)
        sys.exit(1)

    for cluster in clusters:
        output_dir = framework_dir / args.output_dirname / f"cluster_{cluster}_{output_suffix}"

        # Step 1: evolutionary search
        cmd, cwd, best_program = framework["build_cmd"](args, cluster, chunked_traces_dir, output_dir, traces_csv, config)
        run(cmd, cwd=cwd)

        # Step 2: Instance evaluation on best evolved program
        eval_cmd = [
            "python", "instance_evaluation.py",
            "--file", str(best_program),
            "--insert-mongo",
            "--collection", args.collection,
            "--traces-csv", str(traces_csv.resolve()),
            "--instance", str(cluster),
            "--cache-size-percent", str(args.cache_size_percent),
            str(args.traces_dir.resolve()),
        ]
        if args.ignore_size:
            eval_cmd.append("--ignore-size")
        run(eval_cmd, cwd=REPO_ROOT)

        print(f"Cluster {cluster} done.")


if __name__ == "__main__":
    main()
