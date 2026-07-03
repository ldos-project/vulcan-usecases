# openevolve_multi_region_strategy/evaluator.py

import os
import sys
import json
import subprocess
import logging
import re
import traceback
from typing import Dict, List, Tuple, Optional, Union

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "simulator")

MAIN_SIMULATOR_PATH = os.path.join(PROJECT_ROOT, 'main.py')
DATA_PATH = os.path.join(PROJECT_ROOT, "data/converted_multi_region_aligned")

TASK_DURATION_HOURS = 48
DEADLINE_HOURS = 52
RESTART_OVERHEAD_HOURS = 0.2
TIMEOUT_SECONDS = 300
WORST_POSSIBLE_SCORE = -1e9

VULCAN_DIR = os.path.join(SCRIPT_DIR, "vulcan")
VULCAN_WRAPPER = os.path.join(SCRIPT_DIR, "initial_vulcan.py")

# All test scenarios for the final evaluation stage
_ALL_SCENARIOS = [
    {"name": "2_zones_same_region", "regions": ["us-east-1a_v100_1", "us-east-1c_v100_1"], "traces": [f"{i}.json" for i in range(8)]},
    {"name": "2_regions_east_west", "regions": ["us-east-2a_v100_1", "us-west-2a_v100_1"], "traces": [f"{i}.json" for i in range(8)]},
    {"name": "3_regions_diverse", "regions": ["us-east-1a_v100_1", "us-east-2b_v100_1", "us-west-2c_v100_1"], "traces": [f"{i}.json" for i in range(6)]},
    {"name": "3_zones_same_region", "regions": ["us-east-1a_v100_1", "us-east-1c_v100_1", "us-east-1d_v100_1"], "traces": [f"{i}.json" for i in range(6)]},
    {"name": "5_regions_high_diversity", "regions": ["us-east-1a_v100_1", "us-east-1f_v100_1", "us-west-2a_v100_1", "us-west-2b_v100_1", "us-east-2b_v100_1"], "traces": [f"{i}.json" for i in range(4)]},
    {"name": "all_9_regions", "regions": ["us-east-2a_v100_1", "us-west-2c_v100_1", "us-east-1d_v100_1", "us-east-2b_v100_1", "us-west-2a_v100_1", "us-east-1f_v100_1", "us-east-1a_v100_1", "us-west-2b_v100_1", "us-east-1c_v100_1"], "traces": [f"{i}.json" for i in range(2)]}
]

_PER_CLASS_TRACES = [f"{i}.json" for i in range(10)]

_scenario_filter = os.environ.get("EVAL_SCENARIO_FILTER", "").strip()
if _scenario_filter:
    _allowed = {s.strip() for s in _scenario_filter.split(",") if s.strip()}
    FULL_TEST_SCENARIOS = [
        {**s, "traces": _PER_CLASS_TRACES}
        for s in _ALL_SCENARIOS if s["name"] in _allowed
    ]
else:
    FULL_TEST_SCENARIOS = _ALL_SCENARIOS

# A single, simple scenario for the quick first-stage evaluation
STAGE_1_SCENARIO = {
    "name": "stage_1_quick_check", 
    "regions": ["us-east-1a_v100_1", "us-east-1c_v100_1"], 
    "traces": ["0.json"]
}


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _is_cpp_program(program_path: str) -> bool:
    return program_path.endswith((".cpp", ".h", ".hpp"))


def _compile_vulcan_policy(program_path: str) -> tuple:
    build_sh = os.path.join(VULCAN_DIR, "build.sh")
    try:
        result = subprocess.run(
            ["bash", build_sh, os.path.abspath(program_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return False, f"Compilation failed:\n{result.stderr}\n{result.stdout}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out"
    except Exception as exc:
        return False, str(exc)


def run_simulation(program_path: str, trace_files: List[str]) -> Dict[str, Union[float, str, None]]:
    """
    Runs the main.py simulation and returns a result dictionary.
    """
    cmd = [
        sys.executable,
        os.path.basename(MAIN_SIMULATOR_PATH),
        f"--strategy-file={program_path}",
        "--env=multi_trace",
        f"--task-duration-hours={TASK_DURATION_HOURS}",
        f"--deadline-hours={DEADLINE_HOURS}",
        f"--restart-overhead-hours={RESTART_OVERHEAD_HOURS}",
        "--trace-files",
    ] + trace_files

    try:
        # Using subprocess.run to execute the simulation
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True, # Will raise CalledProcessError for non-zero exit codes
            timeout=TIMEOUT_SECONDS,
            cwd=PROJECT_ROOT,
        )

        output = result.stdout + result.stderr
        match = re.search(r"mean:\s*([\d.]+)", output)
        
        if match:
            return {"status": "success", "cost": float(match.group(1)), "output": output}
        
        error_msg = f"Could not parse 'mean:' cost from simulation output."
        return {"status": "failure", "error": error_msg, "output": output}

    except subprocess.CalledProcessError as e:
        error_msg = f"Simulation failed with exit code {e.returncode}."
        return {"status": "failure", "error": error_msg, "stdout": e.stdout, "stderr": e.stderr}
    except subprocess.TimeoutExpired as e:
        error_msg = f"Simulation timed out after {TIMEOUT_SECONDS}s."
        return {"status": "failure", "error": error_msg, "stdout": e.stdout, "stderr": e.stderr}
    except Exception:
        # Catch any other unexpected errors during simulation execution
        error_msg = "An unexpected error occurred during simulation execution."
        return {"status": "failure", "error": error_msg, "traceback": traceback.format_exc()}

def evaluate_stage1(program_path: str) -> Dict[str, Union[float, str]]:
    """
    First-stage evaluation: A quick check to see if the program can run a single,
    simple scenario without crashing. This filters out basic syntax and runtime errors.
    For C++ programs, this compiles the policy .so and runs a quick simulation.
    """
    logger.info(f"--- Stage 1: Quick Check for {os.path.basename(program_path)} ---")

    if _is_cpp_program(program_path):
        ok, err = _compile_vulcan_policy(program_path)
        if not ok:
            logger.warning(f"Stage 1 FAILED. Compilation error: {err}")
            return {"runs_successfully": 0.0, "error": err, "combined_score": WORST_POSSIBLE_SCORE}
        absolute_program_path = os.path.abspath(VULCAN_WRAPPER)
    else:
        absolute_program_path = os.path.abspath(program_path)

    try:
        trace_files = [os.path.join(DATA_PATH, region, STAGE_1_SCENARIO["traces"][0]) for region in STAGE_1_SCENARIO["regions"]]

        if not all(os.path.exists(p) for p in trace_files):
            return {"runs_successfully": 0.0, "error": f"Missing trace files for Stage 1 {trace_files}.", "combined_score": WORST_POSSIBLE_SCORE}

        sim_result = run_simulation(absolute_program_path, trace_files)

        if sim_result["status"] == "success":
            logger.info("Stage 1 PASSED.")
            return {"runs_successfully": 1.0}
        else:
            logger.warning(f"Stage 1 FAILED. Reason: {sim_result.get('error')}")
            return {
                "runs_successfully": 0.0,
                "error": sim_result.get("error"),
                "stdout": sim_result.get("stdout"),
                "stderr": sim_result.get("stderr"),
                "traceback": sim_result.get("traceback"),
                "combined_score": WORST_POSSIBLE_SCORE,
            }

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Stage 1 evaluator itself failed: {tb}")
        return {"runs_successfully": 0.0, "error": "Evaluator script failure", "traceback": tb, "combined_score": WORST_POSSIBLE_SCORE}

def evaluate_stage2(program_path: str, output_all: bool = False) -> Dict[str, Union[float, str]]:
    """
    Second-stage evaluation: The full, comprehensive evaluation across all test scenarios.
    This is only run for programs that have passed Stage 1.
    For C++ programs, stage 1 already compiled the .so; we run via the Python wrapper.
    """
    if _is_cpp_program(program_path):
        absolute_program_path = os.path.abspath(VULCAN_WRAPPER)
    else:
        absolute_program_path = os.path.abspath(program_path)
    logger.info(f"--- Stage 2: Full Evaluation for {os.path.basename(program_path)} ---")
    
    scenario_costs = []
    all_trace_results = []
    last_error = "No scenarios were successfully evaluated in Stage 2."

    for scenario in FULL_TEST_SCENARIOS:
        scenario_name = scenario["name"]
        total_scenario_cost = 0
        successful_runs_in_scenario = 0

        logger.info(f"--- Evaluating Scenario: {scenario_name} ---")

        for trace_file_name in scenario["traces"]:
            trace_files = [os.path.join(DATA_PATH, region, trace_file_name) for region in scenario["regions"]]

            if not all(os.path.exists(p) for p in trace_files):
                last_error = f"Missing trace files for {scenario_name}, trace {trace_file_name}."
                logger.warning(last_error)
                if output_all:
                    all_trace_results.append({"scenario": scenario_name, "trace": trace_file_name, "status": "missing"})
                continue

            sim_result = run_simulation(absolute_program_path, trace_files)

            if sim_result["status"] == "failure":
                last_error = f"Error in scenario '{scenario_name}': {sim_result.get('error')}"
                if output_all:
                    all_trace_results.append({"scenario": scenario_name, "trace": trace_file_name, "status": "failure", "error": sim_result.get("error")})
                break

            cost = sim_result.get("cost", 0.0)
            total_scenario_cost += cost
            successful_runs_in_scenario += 1
            if output_all:
                all_trace_results.append({"scenario": scenario_name, "trace": trace_file_name, "status": "success", "cost": cost})

        if successful_runs_in_scenario > 0:
            average_scenario_cost = total_scenario_cost / successful_runs_in_scenario
            scenario_costs.append(average_scenario_cost)
            logger.info(f"Scenario '{scenario_name}' Average Cost: ${average_scenario_cost:.2f}")
        else:
            scenario_costs.append(float('inf'))
            logger.warning(f"Scenario '{scenario_name}' failed completely. Last error: {last_error}")

    valid_costs = [c for c in scenario_costs if c != float('inf')]
    if not valid_costs:
        logger.error(f"All Stage 2 evaluation scenarios failed. Last error: {last_error}")
        result = {"runs_successfully": 1.0, "cost": float('inf'), "combined_score": WORST_POSSIBLE_SCORE, "error": last_error}
        if output_all:
            result["trace_results"] = all_trace_results
        return result

    final_average_cost = sum(valid_costs) / len(valid_costs)
    score = -final_average_cost

    logger.info(f"--- Evaluation Summary ---")
    logger.info(f"Final Average Cost across all scenarios: ${final_average_cost:.2f}")
    logger.info(f"Final Combined Score: {score:.4f}")

    result = {"runs_successfully": 1.0, "combined_score": score}
    if output_all:
        result["trace_results"] = all_trace_results
    return result

def evaluate(program_path: str) -> Dict[str, Union[float, str]]:
    """
    Main entry point for the evaluator, required by the OpenEvolve framework.
    When cascade evaluation is enabled, this function is effectively a placeholder,
    as the stages (`evaluate_stage1`, `evaluate_stage2`, etc.) are called directly.
    """
    return {"runs_successfully": 1.0, "overall_score": 0.0}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python openevolve_multi_region_strategy/evaluator.py <path_to_program_file>")
        sys.exit(1)
    
    test_program_path = sys.argv[1]
    if not os.path.exists(test_program_path):
        print(f"Error: Program file not found at {test_program_path}")
        sys.exit(1)

    print(f"Running evaluator in standalone mode with program: {test_program_path}...")
    
    # Simulating the cascade for standalone testing
    print("\n--- Running Stage 1 ---")
    stage1_result = evaluate_stage1(test_program_path)
    print(json.dumps(stage1_result, indent=2))

    if stage1_result.get("runs_successfully", 0.0) > 0:
        print("\n--- Running Stage 2 ---")
        stage2_result = evaluate_stage2(test_program_path)
        print("\n--- Final Result ---")
        print(json.dumps(stage2_result, indent=2))
    else:
        print("\n--- Stage 1 Failed. Skipping Stage 2. ---")