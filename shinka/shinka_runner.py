#!/usr/bin/env python
"""
Entry point script for ShinkaEvolve

Example:
  python shinka_runner.py \\
    --traces-dir /data/traces --traces-csv traces.csv --instance 0 --ignore-size --insert-mongo \\
    --config shinka.yaml
"""
import argparse
import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompt import create_config  # noqa: E402

from shinka.cli.run import main


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
        os.environ["EVAL_TRACES_DIR"] = os.path.abspath(eval_args.traces_dir)
    if eval_args.instance is not None:
        os.environ["EVAL_INSTANCE"] = str(eval_args.instance)
    if eval_args.traces_csv is not None:
        os.environ["EVAL_TRACES_CSV"] = os.path.abspath(eval_args.traces_csv)
    if eval_args.ignore_size:
        os.environ["EVAL_IGNORE_SIZE"] = "1"
    if eval_args.insert_mongo:
        os.environ["EVAL_INSERT_MONGO"] = "1"
    if eval_args.cache_size_percent is not None:
        os.environ["EVAL_CACHE_SIZE_PERCENT"] = str(eval_args.cache_size_percent)
    if eval_args.use_anvil:
        os.environ["EVAL_USE_ANVIL"] = "1"

    os.environ["SHINKA_TASK_DIR"] = os.path.dirname(os.path.abspath(__file__))

    # shinka resolves --config-fname relative to --task-dir, so re-anchor
    # the relative path before we swap in a temp copy.
    for i, tok in enumerate(remaining):
        if tok == "--config-fname" and i + 1 < len(remaining):
            src = remaining[i + 1]
            if not os.path.isabs(src):
                task_dir = next(
                    (remaining[j + 1] for j, t in enumerate(remaining)
                     if t == "--task-dir" and j + 1 < len(remaining)),
                    os.path.dirname(os.path.abspath(__file__)),
                )
                src = os.path.join(task_dir, src)
            if "{{ANVIL_DSL}}" in open(src).read():
                dst = create_config(src)
                atexit.register(lambda p=dst: os.path.exists(p) and os.unlink(p))
                remaining[i + 1] = dst
            break

    sys.argv = [sys.argv[0]] + remaining
    sys.exit(main())
