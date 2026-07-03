import json
import os
import pandas as pd
from utils import load_results

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

def build_per_instance_lookup() -> dict[tuple[str, str], float]:
    """Build a (scenario, trace_name) -> new_cost map using each VM family's
    specialized heuristic result file."""
    families = [
        "us-west-2a_k80_1", "us-west-2a_k80_8",
        "us-west-2a_v100_1", "us-west-2a_v100_8",
        "us-west-2b_k80_1", "us-west-2b_k80_8",
        "us-west-2b_v100_1", "us-west-2b_v100_8",
    ]
    lookup: dict[tuple[str, str], float] = {}
    for family in families:
        path = os.path.join(RESULTS, "vulcan", f"results_vulcan_{family}.json")
        with open(path) as f:
            data = json.load(f)
        relevant_results = filter(lambda t: t["scenario"].split("|")[0] == family, data["baselines"][0]["comparison"]["per_trace"])
        for t in relevant_results:
            lookup[(t["scenario"], t["trace_name"])] = t["new_cost"]
    return lookup

def build_comparison_df() -> pd.DataFrame:
    df = load_results({
        "reference_up": os.path.join(RESULTS, "python", "results_referenced_up.json"),
        "python_all":   os.path.join(RESULTS, "python", "results_python.json"),
        "vulcan_all":   os.path.join(RESULTS, "vulcan", "results_vulcan_all.json"),
    })

    per_instance = build_per_instance_lookup()
    assert len(per_instance) == 21_600, "Missing some records"

    df["cost_vulcan_per_instance"] = df.apply(
        lambda r: per_instance[(r["scenario"], r["trace_name"])], axis=1
    )

    return df[["scenario", "trace_name",
               "baseline_cost",
               "cost_reference_up",
               "cost_python_all",
               "cost_vulcan_all",
               "cost_vulcan_per_instance"]].rename(columns={"baseline_cost": "cost_greedy"})


if __name__ == "__main__":
    df = build_comparison_df()
    print(df.shape)
    print(df.head())
