import csv
import os


TRACES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces.csv")


def load_traces_csv(path=TRACES_CSV):
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def get_cache_size(trace_path, footprint_data, ignore_size, cache_size_percent, use_chunk_footprint=False):
    trace_name = os.path.basename(trace_path)
    base_name = trace_name.split("_chunk_")[0].split(".")[0]

    entry = next((e for e in footprint_data if e.get("trace_name") == base_name), None)
    if entry is None:
        raise ValueError(f"Footprint entry not found for trace: {trace_name}")

    if use_chunk_footprint:
        mb_key, objs_key = "chunk_footprint_mb", "chunk_footprint_objs"
    else:
        mb_key, objs_key = "full_footprint_mb", "full_footprint_objs"

    if ignore_size:
        return int(float(entry[objs_key]) * cache_size_percent)
    else:
        return int(float(entry[mb_key]) * 1024 * 1024 * cache_size_percent)
