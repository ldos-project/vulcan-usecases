#!/usr/bin/env python3
"""
Analyze listener usage across all program JSON files in a results directory.
Usage: python analyze_listeners.py <results_dir>
"""

import sys
import json
import re
from pathlib import Path
from collections import Counter, defaultdict


def extract_listeners(code: str) -> list[str]:
    """Extract all vulcan::listeners::* types from code."""
    return re.findall(r'vulcan::listeners::\w+::\w+', code)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <results_dir>")
        sys.exit(1)

    results_dir = Path(sys.argv[1])
    if not results_dir.exists():
        print(f"Error: {results_dir} does not exist")
        sys.exit(1)

    # Find all program JSON files (in checkpoints/*/programs/)
    json_files = list(results_dir.glob("**/programs/*.json"))
    print(f"Found {len(json_files)} program JSON files in {results_dir}\n")

    listener_counts = Counter()          # total occurrences across all programs
    programs_with_listener = Counter()   # how many distinct programs use each listener
    listener_by_cluster = defaultdict(Counter)

    seen_ids = set()  # deduplicate by program id
    total_programs = 0

    for path in json_files:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        prog_id = data.get("id")
        code = data.get("code", "")
        if not code:
            continue

        # Deduplicate: same program can appear in multiple checkpoints
        if prog_id and prog_id in seen_ids:
            continue
        if prog_id:
            seen_ids.add(prog_id)

        total_programs += 1
        cluster = path.parts[path.parts.index(results_dir.name) + 1] if results_dir.name in path.parts else "unknown"

        listeners = extract_listeners(code)
        for l in listeners:
            listener_counts[l] += 1
            listener_by_cluster[cluster][l] += 1
        for l in set(listeners):
            programs_with_listener[l] += 1

    print(f"Unique programs analyzed: {total_programs}\n")

    print("=== Listener Usage (total occurrences across all programs) ===")
    for listener, count in listener_counts.most_common():
        pct = 100 * programs_with_listener[listener] / total_programs if total_programs else 0
        print(f"  {listener:<55} {count:>5} occurrences  |  {programs_with_listener[listener]:>4} programs ({pct:.1f}%)")

    print(f"\n=== Listener Categories ===")
    category_counts = Counter()
    for listener, count in listener_counts.items():
        # e.g. vulcan::listeners::object or vulcan::listeners::global
        parts = listener.split("::")
        category = "::".join(parts[:3]) if len(parts) >= 3 else listener
        category_counts[category] += count
    for cat, count in category_counts.most_common():
        print(f"  {cat:<40} {count:>5} occurrences")

    print(f"\n=== Per-cluster breakdown ===")
    for cluster in sorted(listener_by_cluster):
        print(f"\n  {cluster}:")
        for listener, count in listener_by_cluster[cluster].most_common():
            print(f"    {listener:<55} {count:>4}")


if __name__ == "__main__":
    main()
