# add parent directory to path to enable evaluate_cache from being imported
import csv
import os
import sys
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluate_cache import evaluate_cache_algo, get_traces
from openevolve.evaluation_result import EvaluationResult

INSTANCE = os.environ.get("EVAL_INSTANCE", 0)
TRACES_CSV = os.environ.get("EVAL_TRACES_CSV", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "traces.csv"))
TRACES_DIR = os.environ.get("EVAL_TRACES_DIR", "./libcachesim/data/")
IGNORE_SIZE = os.environ.get("EVAL_IGNORE_SIZE", "0") == "1"
INSERT_MONGO = os.environ.get("EVAL_INSERT_MONGO", "0") == "1"
CACHE_SIZE_PERCENT = float(os.environ.get("EVAL_CACHE_SIZE_PERCENT", "0.1"))
USE_ANVIL = os.environ.get("EVAL_USE_ANVIL", "0") == "1"

def _get_traces():
    with open(TRACES_CSV, "r") as f:
        rows = list(csv.DictReader(f))
    cluster_traces = [row["trace_name"] for row in rows if int(row["cluster"]) == int(INSTANCE)]
    if not cluster_traces:
        raise ValueError(f"No traces found for cluster {INSTANCE} in {TRACES_CSV}")
    return get_traces(traces=cluster_traces, traces_dir=TRACES_DIR)


def evaluate(program_file: str, verbose=False) -> EvaluationResult:
    with open(program_file, "r") as f:
        src_code = f.read()
    try:
        eval_result = evaluate_cache_algo(
            src_code,
            verbose=verbose,
            traces=_get_traces(),
            ignore_size=IGNORE_SIZE,
            insert_into_mongo=INSERT_MONGO,
            traces_csv_path=TRACES_CSV,
            cache_size_percent=CACHE_SIZE_PERCENT,
            use_anvil=USE_ANVIL,
        )

        if eval_result["build_status"] and eval_result["run_status"]:
            return EvaluationResult(
                metrics={
                    "combined_score": eval_result["combined_score"],
                    "eval_time_seconds": eval_result["total_eval_time"]
                },
                artifacts={"message": eval_result["message"]}
            )
        else:
            return EvaluationResult(
                    metrics={"combined_score": -1.0},
                    artifacts={"error": eval_result["message"]}
                )
    except Exception as e:
        return EvaluationResult(
            metrics={"combined_score": -1.0},
            artifacts={"error": "Other runtime error during evaluation: " + traceback.format_exc()}
        )
