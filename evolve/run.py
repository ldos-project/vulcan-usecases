#!/usr/bin/env python
"""
Entry point script for OpenEvolve.

Reads the benchmark from the evaluator config pointed to by the
EVALUATION_CONFIG environment variable, renders configs/config.yaml from
configs/config.yaml.template + configs/system_prompt.template (with the
workload-specific description injected), then hands off to openevolve.
"""
import os
import sys

import yaml
from openevolve.cli import main

WORKLOAD_DESCRIPTIONS = {
    "gups": "GUPS: Random accesses following a zipfian distribution with hotset changing over time.",
    "gapbc": "Gapbs-BC: Graph workload running betweeness centrality algorithm on social media graphs.",
    "gappr": "Gapbs-PR: Graph workload running PageRank algorithm on social media graphs.",
    "silo": "Silo-TPCC: In-memory database running with an insert-heavy client workload that follows latest distribution.",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_TEMPLATE = os.path.join(SCRIPT_DIR, "configs", "config.yaml.template")
SYSTEM_PROMPT_TEMPLATE = os.path.join(SCRIPT_DIR, "configs", "system_prompt.template")
OPENEVOLVE_OUTPUT_FORMAT_TEMPLATE = os.path.join(SCRIPT_DIR, "configs", "openevolve_output_format.template")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "configs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "config.yaml")

SYSTEM_PROMPT_PLACEHOLDER = "###SYSTEM-PROMPT-HERE###"
TASK_INFO_PLACEHOLDER = "###TASK-SPECIFIC-INFO###"


def _load_benchmark() -> str:
    eval_config_path = os.environ.get("EVALUATION_CONFIG")
    if not eval_config_path:
        sys.exit("ERROR: EVALUATION_CONFIG environment variable is not set.")
    if not os.path.isfile(eval_config_path):
        sys.exit(f"ERROR: EVALUATION_CONFIG points to missing file: {eval_config_path}")

    with open(eval_config_path) as f:
        eval_cfg = yaml.safe_load(f) or {}

    try:
        benchmark = eval_cfg["memory_tiering_search"]["benchmark"]
    except (KeyError, TypeError):
        sys.exit(
            f"ERROR: '{eval_config_path}' is missing memory_tiering_search.benchmark."
        )

    if benchmark not in WORKLOAD_DESCRIPTIONS:
        sys.exit(
            f"ERROR: Unknown benchmark '{benchmark}'. "
            f"Expected one of: {sorted(WORKLOAD_DESCRIPTIONS)}."
        )
    return benchmark


def _render_system_prompt(benchmark: str) -> str:
    """Shared domain-knowledge prompt (intro + features + listeners), with the
    benchmark-specific workload description substituted in. Consumed by both
    openevolve (run.py) and GEPA (refine.py)."""
    with open(SYSTEM_PROMPT_TEMPLATE) as f:
        prompt = f.read()
    task_info = f"The target workload for this search is {WORKLOAD_DESCRIPTIONS[benchmark]}"
    return prompt.replace(TASK_INFO_PLACEHOLDER, task_info)


def _render_openevolve_system_message(benchmark: str) -> str:
    """openevolve-specific system message: shared domain knowledge plus the
    'Expected Output' format guidance that tells the LLM how to structure its
    brainstorm → listener config → scoring function response."""
    with open(OPENEVOLVE_OUTPUT_FORMAT_TEMPLATE) as f:
        output_format = f.read()
    return _render_system_prompt(benchmark).rstrip() + "\n\n" + output_format


def _render_config(system_prompt: str) -> str:
    with open(CONFIG_TEMPLATE) as f:
        template = f.read()

    rendered_lines = []
    for line in template.splitlines():
        idx = line.find(SYSTEM_PROMPT_PLACEHOLDER)
        if idx == -1:
            rendered_lines.append(line)
            continue
        leading = line[:idx]
        for prompt_line in system_prompt.splitlines():
            rendered_lines.append(leading + prompt_line if prompt_line else "")
    return "\n".join(rendered_lines) + "\n"


def generate_config() -> str:
    benchmark = _load_benchmark()
    system_prompt = _render_openevolve_system_message(benchmark)
    config_yaml = _render_config(system_prompt)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(config_yaml)
    print(f"[run.py] Wrote {OUTPUT_PATH} (benchmark={benchmark})")
    return OUTPUT_PATH


if __name__ == "__main__":
    smoketest = "--smoketest" in sys.argv
    out_path = generate_config()
    if "--config" in sys.argv:
        sys.exit("ERROR: do not pass --config; run.py generates configs/config.yaml automatically.")
    sys.argv.extend(["--config", out_path])
    if smoketest:
        sys.exit(0)
    sys.exit(main())
