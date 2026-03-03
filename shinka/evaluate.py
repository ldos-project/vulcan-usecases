import argparse
import json
import os
import sys
import csv

SHINKA_TASK_DIR = os.environ.get("SHINKA_TASK_DIR", os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(SHINKA_TASK_DIR))

from evaluate_cache import evaluate_cache_algo, get_traces

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
    return get_traces(cluster_traces, traces_dir=TRACES_DIR)


def evaluate(program_path: str, results_dir: str) -> dict:
    os.makedirs(results_dir, exist_ok=True)

    print(f"Evaluating program at path: {program_path}")
    with open(program_path, "r") as f:
        src_code = f.read()
    
    try:
        result = evaluate_cache_algo(
            src_code,
            verbose=False,
            traces=_get_traces(),
            ignore_size=IGNORE_SIZE,
            insert_into_mongo=INSERT_MONGO,
            traces_csv_path=TRACES_CSV,
            cache_size_percent=CACHE_SIZE_PERCENT,
            use_anvil=USE_ANVIL,
        )

        if result["build_status"] and result["run_status"]:
            metrics = {
                "combined_score": result["combined_score"],
                "public": {
                    "avg_mrr": result["combined_score"],
                    "eval_time_seconds": result["total_eval_time"],
                },
                "private": {
                    "wall_clock_time": result["wall_clock_time"],
                },
                "text_feedback": result["message"],
            }
            correct = True
            error = None
        else:
            metrics = {
                "combined_score": -1.0,
                "public": {"error": True},
                "text_feedback": result["message"],
            }
            correct = False
            error = result["message"]

    except Exception as e:
        metrics = {
            "combined_score": -1.0,
            "public": {"error": True},
            "text_feedback": f"Exception during evaluation: {e}",
        }
        correct = False
        error = str(e)
    
    # recursively go through all elems in metrics and if they are an np.float64, convert them to float using .item()
    def convert_np_float64(obj):
        if isinstance(obj, dict):
            return {k: convert_np_float64(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_np_float64(elem) for elem in obj]
        elif isinstance(obj, float):
            return float(obj)
        else:
            return obj
    metrics = convert_np_float64(metrics)
    
    with open(os.path.join(results_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=4)

    with open(os.path.join(results_dir, "correct.json"), "w") as f:
        json.dump({"correct": correct, "error": error}, f, indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", required=True)
    parser.add_argument("--results_dir", required=True)
    args = parser.parse_args()
    evaluate(args.program_path, args.results_dir)