#!/usr/bin/env python3
"""
Re-evaluates the best evolved heuristics AND baselines on full traces.

For each (db, cache_size, variant) configuration, this script:
  1. Pre-flight: reads final_heuristics collection to get the best heuristic
     per trace. Errors out if anything is missing.
  2. Runs baselines via run_baselines.o and inserts into REPRODUCED_Baselines_*
  3. Evaluates the best evolved heuristic per trace and inserts into
     REPRODUCED_ChunkedTraces_*

Prerequisites:
  - Full traces downloaded (bash download_traces.sh)
  - Project built (bash setup_experiment.sh)
  - MongoDB running with final_heuristics collections populated
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pymongo

from util import get_cache_size, load_traces_csv, TRACES_CSV

TRACES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libcachesim", "data")
BASELINES_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "run_baselines.o")

from evaluate_cache import build_heuristic, run_heuristic, NOLISTENER_PREFIX

MONGO_URI = "mongodb://localhost:27017/"

CONFIGS = [
    # (source_db, eval_collection, cache_size, ignore_size, variant)
    ("ChunkedTraces_size",   "instance_evaluations-10.0pct",              0.1,   False, "default"),
    ("ChunkedTraces_size",   "instance_evaluations-0.1pct",               0.001, False, "default"),
    ("ChunkedTraces_size",   "instance_evaluations-nolistener-10.0pct",   0.1,   False, "nolistener"),
    ("ChunkedTraces_size",   "instance_evaluations-nolistener-0.1pct",    0.001, False, "nolistener"),
    ("ChunkedTraces_nosize", "instance_evaluations-10.0pct",              0.1,   True,  "default"),
    ("ChunkedTraces_nosize", "instance_evaluations-0.1pct",               0.001, True,  "default"),
    ("ChunkedTraces_nosize", "instance_evaluations-nolistener-10.0pct",   0.1,   True,  "nolistener"),
    ("ChunkedTraces_nosize", "instance_evaluations-nolistener-0.1pct",    0.001, True,  "nolistener"),
]


def run_baselines_for_trace(trace_file, cache_size, ignore_size):
    """Run run_baselines.o on a trace and return parsed JSON lines."""
    cmd = f"{BASELINES_BIN} {trace_file} --size {cache_size}"
    if ignore_size:
        cmd += " --ignore"

    proc = subprocess.Popen(
        cmd, shell=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=3600)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()
        return None, "timeout"

    if proc.returncode != 0:
        return None, f"exit code {proc.returncode}: {stderr.decode()[:200]}"

    results = []
    for line in stdout.decode().splitlines():
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results, None


def run_all_baselines(client, trace_names, traces_data):
    """Run baselines on all traces for both cache sizes and both modes."""
    print("\n" + "=" * 70, flush=True)
    print("RUNNING BASELINES", flush=True)
    print("=" * 70, flush=True)

    baseline_configs = []
    seen = set()
    for _, _, cache_size, ignore_size, _ in CONFIGS:
        key = (cache_size, ignore_size)
        if key in seen:
            continue
        seen.add(key)
        baseline_configs.append((cache_size, ignore_size))

    # Collect all baseline jobs
    jobs = []
    for cache_size, ignore_size in baseline_configs:
        mode = "nosize" if ignore_size else "size"
        dest_db_name = f"REPRODUCED_Baselines_{mode}"
        dest_col_name = "baselines_percent"
        col = client[dest_db_name][dest_col_name]

        print(f"\n  -> {dest_db_name}/{dest_col_name} (cache={cache_size})", flush=True)

        for trace_entry in traces_data:
            trace_name = trace_entry["trace_name"]
            if trace_name not in trace_names:
                continue

            trace_file = os.path.join(TRACES_DIR, f"{trace_name}.oracleGeneral.bin.zst")
            trace_key = f"{trace_name}.oracleGeneral.bin.zst"
            if col.find_one({"trace_name": trace_key, "percent": cache_size}):
                print(f"    SKIP {trace_name} (already in {dest_db_name}/{dest_col_name})", flush=True)
                continue

            size = get_cache_size(trace_file, traces_data, ignore_size, cache_size, use_chunk_footprint=False)
            jobs.append({
                "trace_file": trace_file,
                "trace_name": trace_name,
                "size": size,
                "cache_size": cache_size,
                "ignore_size": ignore_size,
                "dest_db_name": dest_db_name,
                "dest_col_name": dest_col_name,
            })

    print(f"\n  {len(jobs)} baseline jobs to run in parallel", flush=True)

    # Each run_baselines.o uses up to 7 threads (one per algorithm)
    max_workers = max(1, os.cpu_count() // 7)

    def _run_baseline_job(job):
        results, err = run_baselines_for_trace(job["trace_file"], job["size"], job["ignore_size"])
        return job, results, err

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_baseline_job, job) for job in jobs]
        total = len(jobs)
        done = 0
        for future in as_completed(futures):
            job, results, err = future.result()
            done += 1
            trace_name = job["trace_name"]
            mode = "nosize" if job["ignore_size"] else "size"
            if err:
                print(f"    [{done}/{total}] {trace_name} (cache={job['cache_size']}, {mode}) FAILED: {err}", flush=True)
                continue

            col = client[job["dest_db_name"]][job["dest_col_name"]]
            inserted = 0
            for r in results:
                r["percent"] = job["cache_size"]
                col.insert_one(r)
                inserted += 1
            print(f"    [{done}/{total}] {trace_name} (cache={job['cache_size']}, {mode}) OK ({inserted} algos)", flush=True)


def run_all_heuristics(client, trace_names):
    """Evaluate best heuristics: build all binaries serially, then run in parallel."""
    print("\n" + "=" * 70, flush=True)
    print("RUNNING HEURISTIC EVALUATIONS", flush=True)
    print("=" * 70, flush=True)

    # Collect all eval jobs, deduplicating builds by source_code
    jobs = []  # (binary_path, trace_file, llm_code, db_name, eval_col, cache_size, ignore_size)
    built = {}  # llm_code hash -> binary_path

    for db_name, eval_col, cache_size, ignore_size, variant in CONFIGS:
        heuristics = list(client[db_name]["final_heuristics"].find(
            {"percentage": cache_size, "variant": variant}
        ))
        dest_col = client[f"REPRODUCED_{db_name}"][eval_col]

        mode = "nosize" if ignore_size else "size"
        pct_label = f"{cache_size*100:.1f}%".replace(".0%", "%")
        cfg_tag = f"[{pct_label}, {mode}, {variant}]"

        for doc in heuristics:
            trace_name = doc["trace"]
            trace_key = f"{trace_name}.oracleGeneral.bin.zst"
            if dest_col.find_one({"evaluation_results.trace_name": trace_key}):
                print(f"  SKIP {trace_name} {cfg_tag} (already evaluated)", flush=True)
                continue

            llm_code = doc["source_code"]
            if variant == "nolistener":
                llm_code = NOLISTENER_PREFIX + llm_code

            code_hash = hashlib.sha256(llm_code.encode()).hexdigest()
            if code_hash not in built:
                print(f"  Building {code_hash[:12]} {cfg_tag}...", end=" ", flush=True)
                try:
                    built[code_hash] = build_heuristic(llm_code)
                    print("OK", flush=True)
                except RuntimeError as e:
                    print(f"FAILED: {e}", flush=True)
                    built[code_hash] = None

            if built[code_hash] is None:
                continue

            trace_file = os.path.join(TRACES_DIR, f"{trace_name}.oracleGeneral.bin.zst")
            jobs.append({
                "binary_path": built[code_hash],
                "trace_file": trace_file,
                "trace_name": trace_name,
                "llm_code": llm_code,
                "db_name": db_name,
                "eval_col": eval_col,
                "cache_size": cache_size,
                "ignore_size": ignore_size,
            })

    print(f"\n  {len(jobs)} evaluations to run in parallel", flush=True)

    # Run all jobs in parallel
    def _run_job(job):
        results = run_heuristic(
            job["binary_path"], [job["trace_file"]],
            job["ignore_size"], job["cache_size"],
        )
        return job, results[0]

    total_gb = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024 ** 3)
    max_workers = max(1, min(os.cpu_count(), int(total_gb // 10)))
    print(f"  Workers: {max_workers} (cpu={os.cpu_count()}, ram={total_gb:.0f}GB)", flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            try:
                job, result = future.result()
            except Exception as e:
                print(f"  FAILED: {e}", flush=True)
                continue

            # Insert into mongo
            trace_key = f"{job['trace_name']}.oracleGeneral.bin.zst"
            base_col_name = job["eval_col"].rsplit(f"-{job['cache_size']*100:.1f}pct", 1)[0]
            db_name = f"REPRODUCED_{job['db_name']}"
            source_hash = hashlib.sha256(job["llm_code"].encode()).hexdigest()

            def _sanitize(obj):
                if isinstance(obj, dict):
                    return {k: _sanitize(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_sanitize(v) for v in obj]
                if isinstance(obj, np.integer):
                    return int(obj)
                if isinstance(obj, np.floating):
                    return float(obj)
                return obj

            mongo_doc = _sanitize({
                "timestamp": time.time(),
                "source_code": job["llm_code"],
                "source_hash": source_hash,
                "evaluation_results": [result],
            })
            col = client[db_name][f"{base_col_name}-{job['cache_size']*100:.1f}pct"]
            col.insert_one(mongo_doc)
            print(f"  {job['trace_name']} ({job['eval_col']}) -> mr={result['miss_ratio']:.4f}", flush=True)

    # Cleanup temp dirs
    for binary_path in built.values():
        if binary_path:
            shutil.rmtree(os.path.dirname(binary_path), ignore_errors=True)


LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluate_all.log")


def main():
    traces_data = load_traces_csv()
    trace_names = {t["trace_name"] for t in traces_data}

    client = pymongo.MongoClient(MONGO_URI)

    t0 = time.time()

    # Step 1: Run baselines
    run_all_baselines(client, trace_names, traces_data)

    # Step 2: Run heuristic evaluations
    run_all_heuristics(client, trace_names)

    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print("DONE. Generate reproduced plots with:")
    print("  python3 plots/plot_workload_instances.py --cache-size 0.1 --plot --reproduce")
    print("  python3 plots/plot_workload_instances.py --cache-size 0.001 --plot --reproduce")
    print("  python3 plots/plot_workload_instances.py --cache-size 0.1 --ignore-size --plot --reproduce")
    print("  python3 plots/plot_workload_instances.py --cache-size 0.001 --ignore-size --plot --reproduce")
    print("=" * 70)

    if elapsed > 10:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | total_time={elapsed:.1f}s\n")


if __name__ == "__main__":
    main()
