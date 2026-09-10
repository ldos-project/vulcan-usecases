#!/usr/bin/env python3
"""Run the memory-tiering experiment and write results.json.

For each policy it swaps the scoring function into ARMS (tiering_solutions/src/LLMCode.h),
rebuilds libarms.so, and runs each workload under ARMS. The three policies are
heuristics/{baseline_arms,seed,synthesized}.cpp. plot_paper_figure.py turns results.json
into the figure.

    python run_experiment.py --reps 5
"""
import argparse
import json
import pathlib
import re
import shutil
import statistics
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "tiering_solutions" / "src"
LIB = SRC / "libarms.so"
HEURISTICS = ROOT / "heuristics"
POLICIES = ["baseline_arms", "seed", "synthesized"]


def parse_gups(out):
    r = {}
    for ln in out.splitlines():
        if ln.startswith("GUPS ="):
            r["gups"] = float(ln.split("=")[1])
        elif ln.startswith("Elapsed time:"):
            r["elapsed_time_seconds"] = float(ln.split(":")[1].split()[0])
    return r


def parse_gapbs(out):
    r = {}
    for ln in out.splitlines():
        if "Average Time:" in ln:
            r["average_time_seconds"] = float(ln.split(":")[1].strip())
        elif "Elapsed (wall clock) time" in ln:
            m = re.search(r":\s*([\d:.]+)\s*$", ln)
            if m:
                parts = [float(x) for x in m.group(1).split(":")]
                r["elapsed_time_seconds"] = sum(v * 60 ** i for i, v in enumerate(reversed(parts)))
    return r


def parse_silo(out):
    r = {}
    for ln in out.splitlines():
        if "agg_throughput:" in ln:
            r["throughput"] = float(ln.split(":")[1].split()[0]) / 1000.0  # Kops/sec
    return r


# Per workload: the command to run under ARMS, its parser, and the primary metric.
WORKLOADS = {
    "gapbc": dict(
        cmd=f"/usr/bin/time -v numactl -N0 sudo DRAMSIZE=1558183936 NVMSIZE=21078474752 OMP_NUM_THREADS=16 MIN_INTERPOSE_MEM_SIZE=134217728 LD_PRELOAD={LIB} /mnt/data/workloads/gapbs/bc -n 16 -f /mnt/data/inputs/twitter.sg",
        parser=parse_gapbs, metric="average_time_seconds", higher_is_better=False),
    "gappr": dict(
        cmd=f"/usr/bin/time -v numactl -N0 sudo DRAMSIZE=1558183936 NVMSIZE=21078474752 OMP_NUM_THREADS=16 MIN_INTERPOSE_MEM_SIZE=134217728 LD_PRELOAD={LIB} /mnt/data/workloads/gapbs/pr -n 8 -f /mnt/data/inputs/twitter.sg",
        parser=parse_gapbs, metric="average_time_seconds", higher_is_better=False),
    "gups": dict(
        cmd=f"numactl -N0 sudo DRAMSIZE=7625244672 NVMSIZE=77311508480 LD_PRELOAD={LIB} /mnt/data/workloads/gups_hemem/gups-hotset-move 16 200000000 36 8 33",
        parser=parse_gups, metric="gups", higher_is_better=True),
    "silo": dict(
        cmd=f"cd /mnt/data/workloads/silo/silo && numactl -N0 sudo DRAMSIZE=9298771968 NVMSIZE=83022053376 LD_PRELOAD={LIB} ./out-perf.masstree/benchmarks/dbtest --verbose --bench tpcc --num-threads 20 --scale-factor 100 --runtime 120 --numa-memory 85899345920",
        parser=parse_silo, metric="throughput", higher_is_better=True),
}


def build(policy):
    """Swap in the policy's scoring function and rebuild libarms.so."""
    shutil.copy(HEURISTICS / f"{policy}.cpp", SRC / "LLMCode.h")
    subprocess.run(["make", "-C", str(SRC), "clean"], capture_output=True)
    r = subprocess.run(["make", "-C", str(SRC), "-j"], capture_output=True, text=True)
    if r.returncode != 0 or not LIB.exists():
        raise SystemExit(f"build failed for {policy}:\n{r.stderr[-2000:]}")


def run_once(workload):
    spec = WORKLOADS[workload]
    p = subprocess.run(spec["cmd"], shell=True, capture_output=True, text=True)
    return spec["parser"](p.stdout + "\n" + p.stderr)


def normalize(value, baseline, higher_is_better):
    return value / baseline if higher_is_better else baseline / value


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=5, help="Repetitions per (workload, policy).")
    ap.add_argument("--workloads", default=",".join(WORKLOADS))
    ap.add_argument("--policies", default=",".join(POLICIES))
    ap.add_argument("--out", default=str(ROOT / "results.json"))
    args = ap.parse_args()

    workloads = [w.strip() for w in args.workloads.split(",") if w.strip()]
    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    for w in workloads:
        if w not in WORKLOADS:
            raise SystemExit(f"Unknown workload: {w}")

    data = {w: {p: [] for p in policies} for w in workloads}
    for policy in policies:
        print(f"\n[build] {policy}")
        build(policy)
        for workload in workloads:
            metric = WORKLOADS[workload]["metric"]
            for rep in range(args.reps):
                print(f"[run ] {workload}/{policy} rep {rep + 1}/{args.reps}")
                res = run_once(workload)
                if metric not in res:
                    print(f"  FAILED (no {metric})")
                    data[workload][policy].append({"error": "parse", "raw": res})
                    continue
                print(f"  {metric}={res[metric]}")
                data[workload][policy].append(res)

    out = {
        "meta": {
            "reps": args.reps,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "workloads": workloads,
            "policies": policies,
            "primary_metric": {w: WORKLOADS[w]["metric"] for w in workloads},
            "higher_is_better": {w: WORKLOADS[w]["higher_is_better"] for w in workloads},
        },
        "data": data,
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")

    print("\n" + "=" * 52)
    print(f"{'workload':10}{'policy':14}{'norm. vs ARMS':>16}")
    print("=" * 52)
    for w in workloads:
        spec = WORKLOADS[w]
        base = [r[spec["metric"]] for r in data[w].get("baseline_arms", []) if spec["metric"] in r]
        bmean = statistics.fmean(base) if base else None
        for p in policies:
            vals = [r[spec["metric"]] for r in data[w][p] if isinstance(r, dict) and spec["metric"] in r]
            if not vals or bmean is None:
                print(f"{w:10}{p:14}{'(no data)':>16}")
                continue
            norm = [normalize(v, bmean, spec["higher_is_better"]) for v in vals]
            m = statistics.fmean(norm)
            s = statistics.stdev(norm) if len(norm) > 1 else 0.0
            print(f"{w:10}{p:14}{m:>11.3f} ± {s:.3f}")


if __name__ == "__main__":
    main()
