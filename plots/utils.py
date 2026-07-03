import pandas as pd
import json

def load_results(paths: dict[str, str]) -> pd.DataFrame:
    """Load multiple result JSONs into a single DataFrame.
    
    Args:
        paths: mapping of label -> filepath, e.g.
               {"python": "results/python/results_python.json",
                "vulcan": "results/vulcan/results_vulcan_all.json"}
    
    Returns:
        DataFrame with one row per (scenario, trace_name), columns:
          scenario, trace_name, duration, deadline, overhead,
          baseline_cost, and one cost column per label (e.g. cost_python, cost_vulcan)
    """
    base_df = None
    for label, path in paths.items():
        with open(path) as f:
            data = json.load(f)
        traces = data["baselines"][0]["comparison"]["per_trace"]
        rows = []
        for t in traces:
            rows.append({
                "scenario": t["scenario"],
                "trace_name": t["trace_name"],
                "duration": t["config"]["duration"],
                "deadline": t["config"]["deadline"],
                "overhead": t["config"]["overhead"],
                "baseline_cost": t["baseline_cost"],
                f"cost_{label}": t["new_cost"],
            })
        df = pd.DataFrame(rows)
        if base_df is None:
            base_df = df
        else:
            base_df = base_df.merge(
                df[["scenario", "trace_name", f"cost_{label}"]],
                on=["scenario", "trace_name"],
            )
    return base_df