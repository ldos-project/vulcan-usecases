"""
Get footprints for all traces in a directory using the get_footprint binary.
Results are saved as a pickle file in the same src/ directory as this script.
"""

#!/usr/bin/env python3

import argparse
import json
import pickle
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Get footprints for all traces in a directory using the get_footprint binary"
    )
    parser.add_argument(
        "traces_dir", type=Path, help="Directory containing trace files"
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output pickle file path (default: src/footprints.pkl)"
    )

    args = parser.parse_args()
    traces_dir = args.traces_dir

    if not traces_dir.exists() or not traces_dir.is_dir():
        print(
            f"Error: traces_dir '{traces_dir}' is not a valid directory path",
            file=sys.stderr,
        )
        sys.exit(1)

    # Locate the get_footprint binary -- ./build/get_footprint.o relative to this script
    get_footprint_binary = Path(__file__).parent / "build" / "get_footprint.o"
    if not get_footprint_binary.exists():
        print(
            f"Error: get_footprint binary not found at {get_footprint_binary}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Output pickle path
    if not args.output:
        output_path = Path(__file__).parent / "footprints.pkl"
    else:
        output_path = args.output

    # Find all trace files
    trace_files = sorted(list(traces_dir.glob("*.zst")))

    if not trace_files:
        print(f"Warning: no trace files found in {traces_dir}", file=sys.stderr)
        return

    print(f"Found {len(trace_files)} trace file(s)")

    results = []
    failed_traces = []

    for i, trace_file in enumerate(trace_files, 1):
        print(f"[{i}/{len(trace_files)}] {trace_file.name}...", end=" ", flush=True)

        cmd = [str(get_footprint_binary), str(trace_file)]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(result.stdout.strip())
            results.append(data)
            print(f"footprint_mb={data.get('footprint_mb', '?'):.2f}, footprint_objs={data.get('footprint_objs', '?')}")
        except subprocess.CalledProcessError as e:
            print(f"FAILED", file=sys.stderr)
            if e.stderr:
                print(f"  stderr: {e.stderr.strip()}", file=sys.stderr)
            failed_traces.append(trace_file.name)
        except json.JSONDecodeError as e:
            print(f"FAILED (bad JSON)", file=sys.stderr)
            failed_traces.append(trace_file.name)
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            failed_traces.append(trace_file.name)

    print(f"\n{'='*60}")
    print(f"Done. {len(results)}/{len(trace_files)} traces succeeded.")

    with open(output_path, "wb") as f:
        pickle.dump(results, f)
    print(f"Saved {len(results)} footprint records to {output_path}")

    if failed_traces:
        print(f"\nFailed traces ({len(failed_traces)}):", file=sys.stderr)
        for trace in failed_traces:
            print(f"  - {trace}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
