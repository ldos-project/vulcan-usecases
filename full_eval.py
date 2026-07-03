#!/usr/bin/env python3
"""Run the multi-region evaluator against all 100 available traces per scenario
(not just the 2-8 used during evolution) and dump the results.

Usage:
    python full_eval.py initial_program.py --output results/baseline.json
"""

import argparse
import json
import logging
from contextlib import contextmanager

import evaluator as base_evaluator

logger = logging.getLogger(__name__)

ALL_TRACES = [f"{i}.json" for i in range(100)]


@contextmanager
def _full_traces():
    """Override scenario trace lists to use all available traces."""
    original_scenarios = base_evaluator.FULL_TEST_SCENARIOS
    try:
        base_evaluator.FULL_TEST_SCENARIOS = [
            {**s, "traces": ALL_TRACES} for s in base_evaluator._ALL_SCENARIOS
        ]
        yield
    finally:
        base_evaluator.FULL_TEST_SCENARIOS = original_scenarios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program_path", help="Path to the strategy to evaluate")
    parser.add_argument("--output", required=True, help="Path to write JSON report")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if base_evaluator._is_cpp_program(args.program_path):
        ok, err = base_evaluator._compile_vulcan_policy(args.program_path)
        if not ok:
            logger.error("Compilation failed: %s", err)
            raise SystemExit(1)

    with _full_traces():
        result = base_evaluator.evaluate_stage2(args.program_path, output_all=True)

    with open(args.output, "w") as fh:
        json.dump(result, fh, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
