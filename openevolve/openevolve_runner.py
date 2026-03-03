#!/usr/bin/env python
"""
Entry point script for OpenEvolve.

Example:
  python openevolve_runner.py initial.cpp openevolve_evaluator.py \\
    --traces-dir /data/traces --traces-csv traces.csv --instance 0 --ignore-size --insert-mongo \\
    --config config.yaml
"""

import argparse
import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompt import create_config  # noqa: E402

from openevolve.cli import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--traces-dir", default=None)
    parser.add_argument("--instance", type=int, default=None)
    parser.add_argument("--traces-csv", default=None)
    parser.add_argument("--ignore-size", action="store_true", default=False)
    parser.add_argument("--insert-mongo", action="store_true", default=False)
    parser.add_argument("--cache-size-percent", type=float, default=0.1)
    parser.add_argument("--use_anvil", action="store_true", default=False,
                        help="Gate each candidate through anvil --gate.")
    eval_args, remaining = parser.parse_known_args(sys.argv[1:])

    if eval_args.traces_dir is not None:
        os.environ["EVAL_TRACES_DIR"] = eval_args.traces_dir
    if eval_args.instance is not None:
        os.environ["EVAL_INSTANCE"] = str(eval_args.instance)
    if eval_args.traces_csv is not None:
        os.environ["EVAL_TRACES_CSV"] = eval_args.traces_csv
    if eval_args.ignore_size:
        os.environ["EVAL_IGNORE_SIZE"] = "1"
    if eval_args.insert_mongo:
        os.environ["EVAL_INSERT_MONGO"] = "1"
    if eval_args.cache_size_percent is not None:
        os.environ["EVAL_CACHE_SIZE_PERCENT"] = str(eval_args.cache_size_percent)
    if eval_args.use_anvil:
        os.environ["EVAL_USE_ANVIL"] = "1"

    for i, tok in enumerate(remaining):
        if tok in ("-c", "--config") and i + 1 < len(remaining):
            src = remaining[i + 1]
            if "{{ANVIL_DSL}}" in open(src).read():
                dst = create_config(src)
                atexit.register(lambda p=dst: os.path.exists(p) and os.unlink(p))
                remaining[i + 1] = dst
            break

    sys.argv = [sys.argv[0]] + remaining
    sys.exit(main())
