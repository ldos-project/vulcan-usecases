#!/usr/bin/env python3
"""Print a table of generation counts per trace per collection, with estimated # of runs."""
import pymongo

MONGO = "mongodb://localhost:27017/"
DBS = ["ChunkedTraces_size", "ChunkedTraces_nosize"]
TRACES = ["wMSR", "wMetaCDN", "wMetaKVCache", "wMetaStorage", "wTencent",
          "wTwemCacheCluster50", "wTwemCacheCluster53", "wWikiMedia"]
SHORT = {
    "wTwemCacheCluster50": "Tw50",
    "wTwemCacheCluster53": "Tw53",
}
GAP_THRESHOLD = 3600  # seconds between runs


def count_runs(timestamps):
    if not timestamps:
        return 0
    ts = sorted(timestamps)
    runs = 1
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] > GAP_THRESHOLD:
            runs += 1
    return runs


def main():
    client = pymongo.MongoClient(MONGO)

    for db_name in DBS:
        db = client[db_name]
        cols = sorted(c for c in db.list_collection_names() if c.startswith("generations"))
        if not cols:
            continue

        # header
        header_traces = [SHORT.get(t, t) for t in TRACES]
        col_width = max(len(c) for c in cols) + 2
        trace_width = 12
        print(f"\n=== {db_name} ===")
        print(f"{'collection':<{col_width}}", end="")
        for t in header_traces:
            print(f"{t:>{trace_width}}", end="")
        print()
        print("-" * (col_width + trace_width * len(TRACES)))

        for col_name in cols:
            col = db[col_name]
            # group timestamps by trace
            per_trace = {t: [] for t in TRACES}
            for doc in col.find({}, {"timestamp": 1, "evaluation_results.trace_name": 1}):
                ts = doc.get("timestamp")
                for er in doc.get("evaluation_results", []):
                    base = er["trace_name"].split("_chunk_")[0].split(".")[0]
                    if base in per_trace:
                        per_trace[base].append(ts)

            row = f"{col_name:<{col_width}}"
            for t in TRACES:
                n = len(per_trace[t])
                runs = count_runs(per_trace[t])
                if n == 0:
                    row += f"{'—':>{trace_width}}"
                else:
                    cell = f"{n}({runs})"
                    row += f"{cell:>{trace_width}}"
            print(row)


if __name__ == "__main__":
    main()
