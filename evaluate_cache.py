import argparse
import hashlib
import json
import numpy as np
import os
import pandas as pd
import pymongo
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from util import get_cache_size, load_traces_csv, TRACES_CSV

TRACES_DIR = os.getenv("TRACES_DIR", "./libcachesim/data/")

_ARTIFACT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ANVIL_BIN = os.path.join(_ARTIFACT_ROOT, "anvil", "anvil")


def anvil_gate(cpp_source: str) -> tuple[bool, str]:
    """Run `anvil --gate` on cpp_source. Returns (safe, error_tail)."""
    if not os.path.exists(_ANVIL_BIN):
        return False, f"anvil binary not found at {_ANVIL_BIN}"
    env = dict(os.environ, ANVIL_SKIP_BUILD="1")
    try:
        proc = subprocess.run(
            [_ANVIL_BIN, "--gate"],
            input=cpp_source,
            cwd=_ARTIFACT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "anvil gate timed out"
    except OSError as exc:
        return False, f"could not run anvil: {exc}"
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr.strip() or proc.stdout.strip())
    return False, "\n".join(err.splitlines()[-5:])

NOLISTENER_PREFIX = """\
config.add_listeners(f_curr_time, {vulcan::listeners::global::RollingWindow(1)});
config.add_listeners(f_ghost, {vulcan::listeners::global::RollingCount(100)});
config.add_listeners(f_size, {vulcan::listeners::object::RollingWindow(1)});
config.add_listeners(f_insertion_time, {vulcan::listeners::object::RollingWindow(1)});
config.add_listeners(f_last_access, {vulcan::listeners::object::RollingWindow(1)});
config.add_listeners(f_count, {vulcan::listeners::object::RollingWindow(1)});
"""

def build_heuristic(llm_code):
    """Write llm_code to LLMCode.h and build into a private, self-contained build
    dir. Returns the path to run_algo.o inside that dir; the caller is responsible
    for removing os.path.dirname(binary_path) when done. Raises RuntimeError on
    failure."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    libcachesim_dir = os.path.join(project_dir, "libcachesim")
    llm_code_path = os.path.join(libcachesim_dir, "libCacheSim", "include", "LLMCode.h")

    with open(llm_code_path, "w") as f:
        f.write(llm_code)

    build_dir = tempfile.mkdtemp(prefix="vulcan_build_")
    proc = subprocess.Popen(
        f"cmake -S {project_dir} -B {build_dir} && cmake --build {build_dir} -j",
        cwd=project_dir, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        shutil.rmtree(build_dir, ignore_errors=True)
        raise RuntimeError("Build timed out")

    if proc.returncode != 0:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise RuntimeError(f"Build failed (rc={proc.returncode}): {stderr.decode()[:500]}")

    return os.path.join(build_dir, "run_algo.o")


def run_heuristic(binary_path, traces, ignore_size, cache_size_percent,
                  eval_cmd_timeout=14400):
    """Run a pre-built binary on traces. Returns list of per-trace metric dicts."""
    results = []
    for trace in traces:
        cmd = f"{binary_path} {trace} --percent {cache_size_percent}"
        if ignore_size:
            cmd += " --ignore"
        output = run_eval_command(cmd, eval_cmd_timeout)
        results.append(get_miss_rate_reduction(load_json(output)))
    return results


def run_eval_command(cmd, eval_cmd_timeout=100, exit_on_error=True):
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=eval_cmd_timeout + 5)
    except subprocess.TimeoutExpired as t_err:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()
        if exit_on_error:
            raise t_err
        else:
            return ""
    if exit_on_error:
        if proc.returncode != 0:
            raise RuntimeError(f"Command '{cmd}' failed with error: {stdout.decode()} {stderr.decode()}")
    return stdout.decode()

def get_miss_rate_reduction(df):
    fifo_miss_rate = df.loc['FIFO'].miss_ratio
    algo_miss_rate = df.loc['VulcanPQEvolve'].miss_ratio

    if algo_miss_rate < fifo_miss_rate:
        mrr = (fifo_miss_rate - algo_miss_rate) / fifo_miss_rate
    else:
        mrr = (fifo_miss_rate - algo_miss_rate) / algo_miss_rate
    
    return {
        "miss_ratio": algo_miss_rate,
        "byte_miss_ratio": df.loc['VulcanPQEvolve'].byte_miss_ratio,
        "mrr": mrr,
        "num_req": df.loc['VulcanPQEvolve'].num_req,
        "runtime_seconds": df.loc['VulcanPQEvolve'].runtime_seconds,
        "trace_name": df.loc['VulcanPQEvolve'].trace_name
    }

def get_traces(traces, traces_dir=TRACES_DIR):
    return [f"{traces_dir}/{trace}.oracleGeneral.bin.zst" for trace in traces]

def load_json(data, exit_on_error=True):
    processed_data = []
    
    try:
        for line in data.splitlines():
            processed_data.append(json.loads(line))
        return pd.DataFrame(processed_data).set_index('cache_name')

    except json.JSONDecodeError as e:
        if exit_on_error:
            raise e
        else:
            print("Skipping invalid JSON data:", data)
            return {}

def evaluate_cache_algo(
    llm_code, verbose=True, traces=None, eval_cmd_timeout=3600,
    max_parallel_workers=10, exit_on_error=True, cache_size_percent=0.001,
    ignore_size=True, per_trace_metrics=False, insert_into_mongo=False,
    collection_name="generations", traces_csv_path=TRACES_CSV,
    mongo_db_prefix=None, use_anvil=False,
) -> dict:
    '''When `use_anvil=True`, the candidate is checked by `anvil --gate` first;
    if it fails, the run short-circuits with `build_status=False` and the gate's
    rejection reason in `message`.'''
    FINAL_RESULT_DICT = {"build_status": False, "run_status": False}

    if use_anvil:
        safe, err = anvil_gate(llm_code)
        if not safe:
            FINAL_RESULT_DICT["message"] = f"Anvil rejected candidate: {err}"
            return FINAL_RESULT_DICT

    try:
        binary_path = build_heuristic(llm_code)
    except RuntimeError as e:
        FINAL_RESULT_DICT["message"] = str(e)
        return FINAL_RESULT_DICT

    FINAL_RESULT_DICT["build_status"] = True
    if verbose:
        print("Build succeeded.")

    try:
        results = run_heuristic(binary_path, traces, ignore_size, cache_size_percent,
                                eval_cmd_timeout=eval_cmd_timeout)
    except RuntimeError as e:
        FINAL_RESULT_DICT["message"] = str(e)
        shutil.rmtree(os.path.dirname(binary_path), ignore_errors=True)
        return FINAL_RESULT_DICT

    shutil.rmtree(os.path.dirname(binary_path), ignore_errors=True)
    FINAL_RESULT_DICT["run_status"] = True

    if per_trace_metrics:
        FINAL_RESULT_DICT["evaluation_results"] = results
    FINAL_RESULT_DICT["total_eval_time"] = sum(r["runtime_seconds"] for r in results)

    if insert_into_mongo:
        source_hash = hashlib.sha256(llm_code.encode()).hexdigest()
        mongo_doc = {
            "timestamp": time.time(),
            "source_code": llm_code,
            "source_hash": source_hash,
            "evaluation_results": results,
        }

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

        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db_name = "ChunkedTraces_nosize" if ignore_size else "ChunkedTraces_size"
        if mongo_db_prefix:
            db_name = f"{mongo_db_prefix}{db_name}"
        try:
            col = client[db_name][f"{collection_name}-{cache_size_percent*100:.1f}pct"]
            col.insert_one(_sanitize(mongo_doc))
        except Exception as e:
            print(f"[WARN] Failed to insert into MongoDB: {e}")

    mrrs = [r['mrr'] for r in results]
    avg_mrr = sum(mrrs) / len(mrrs)

    if verbose:
        print(f"Avg MRR: {avg_mrr}")

    FINAL_RESULT_DICT["combined_score"] = round(avg_mrr, 3)
    if per_trace_metrics:
        FINAL_RESULT_DICT["eval_times"] = [r['runtime_seconds'] for r in results]
    FINAL_RESULT_DICT["wall_clock_time"] = round(sum(r["runtime_seconds"] for r in results), 3)
    FINAL_RESULT_DICT["message"] = f"We tested your algorithm on {len(traces)} traces. The min/avg/max miss ratio reductions over FIFO for this heuristic were: {round(min(mrrs), 2)} / {round(sum(mrrs)/len(mrrs), 2)} / {round(max(mrrs), 2)} over these {len(traces)} traces."

    return FINAL_RESULT_DICT

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--default", action="store_true", help="Use openevolve/initial_program.cpp as LLMCode.h")
    source_group.add_argument("--file", type=str, help="Path to a .cpp file to use as LLMCode.h")
    parser.add_argument("--traces", nargs="+", required=True)
    parser.add_argument("--insert-mongo", action="store_true", default=False)
    parser.add_argument("--ignore-size", action="store_true", default=False)
    parser.add_argument("--nolistener", action="store_true", default=False,
                        help="Prepend default listener config for nolistener heuristics")
    parser.add_argument("--traces-csv", type=str, default=TRACES_CSV)
    parser.add_argument("--collection", type=str, default=None)
    parser.add_argument("--use_anvil", action="store_true", default=False,
                        help="Gate the candidate through anvil --gate; reject unsafe.")
    args = parser.parse_args()

    if args.collection is not None and not args.insert_mongo:
        parser.error("--collection requires --insert-mongo")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    if args.default:
        print("Writing default code to LLMCode.h...")
        with open(os.path.join(current_dir, "openevolve/initial_program.cpp"), "r") as f:
            initial_code = f.read()
    else:
        print(f"Writing {args.file} to LLMCode.h...")
        with open(args.file, "r") as f:
            initial_code = f.read()

    if args.nolistener:
        initial_code = NOLISTENER_PREFIX + initial_code

    print(evaluate_cache_algo(initial_code, verbose=True, traces=args.traces, insert_into_mongo=args.insert_mongo,
                              ignore_size=args.ignore_size, traces_csv_path=args.traces_csv,
                              collection_name=args.collection or "generations",
                              use_anvil=args.use_anvil), file=sys.stderr)
