import re
import os
import time
import yaml
import fcntl
import pymongo
import hashlib
import pathlib
import tempfile
import subprocess
from openevolve.evaluation_result import EvaluationResult

def run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, printing it, and fail fast on error."""
    print(f"+ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)
    return result


def get_githash_and_diff():
    try:
        githash = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd="../", stderr=subprocess.STDOUT
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        githash = "unknown"

    try:
        diff = (
            subprocess.check_output(
                ["git", "diff"], cwd="../", stderr=subprocess.STDOUT
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        diff = "unknown"

    return githash, diff


def compile_and_check(program_file: str, host: str) -> tuple[bool, str | None]:
    # Push the source code file to the node and check if it compiles.
    program_file = pathlib.Path(program_file).resolve()
    try:
        run_cmd(
            [
                "scp",
                "-o",
                "StrictHostKeyChecking=no",
                str(program_file),
                f"{host}:~/tiering_solutions/src/LLMCode.h",
            ]
        )
    except subprocess.CalledProcessError as e:
        error_msg = f"SCP failed with return code {e.returncode}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr}"
        if e.stdout:
            error_msg += f"\nStdout: {e.stdout}"
        print(f"Error: {error_msg}")

        # Returning True as it is likely a problem with scp.
        return False, error_msg

    try:
        # Build tiering_solutions on remote.
        remote_build_cmd = """
                    set -e
                    pushd tiering_solutions/src
                    make clean
                    make -j
                    popd
                    """
        result = run_cmd(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                host,
                remote_build_cmd,
            ]
        )
        print("Build succeeded.")
        if result.stdout:
            print(f"Build output: {result.stdout}")
        return True, None
    except subprocess.CalledProcessError as e:
        error_msg = f"Compilation failed with return code {e.returncode}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr}"
        if e.stdout:
            error_msg += f"\nStdout: {e.stdout}"
        print(f"Error: {error_msg}")
        return False, error_msg


def run_and_get_results(host: str, benchmark: str) -> tuple[bool, str | None]:
    # Call the eval script on the local node.
    current_file_dir = pathlib.Path(__file__).parent.resolve()
    eval_scripts_dir = current_file_dir / "eval_scripts"
    local_results_file = tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".txt"
    )

    success = False
    try:
        if benchmark == "gups":
            result = run_cmd(
                [f"{eval_scripts_dir}/eval_gups.sh", host, local_results_file.name],
                cwd=str(eval_scripts_dir),
            )
        elif benchmark == "gapbc":
            result = run_cmd(
                [f"{eval_scripts_dir}/eval_gapbc.sh", host, local_results_file.name],
                cwd=str(eval_scripts_dir),
            )
        elif benchmark == "gappr":
            result = run_cmd(
                [f"{eval_scripts_dir}/eval_gappr.sh", host, local_results_file.name],
                cwd=str(eval_scripts_dir),
            )
        elif benchmark == "silo":
            result = run_cmd(
                [f"{eval_scripts_dir}/eval_silo.sh", host, local_results_file.name],
                cwd=str(eval_scripts_dir),
            )
        else:
            raise ValueError(f"Unknown benchmark: {benchmark}")

        print("Evaluation succeeded.")
        if result.stdout:
            print(f"Evaluation output: {result.stdout}")

        with open(local_results_file.name, "r") as f:
            results_content = f.read()
        success = True
    except subprocess.CalledProcessError as e:
        error_msg = f"Evaluation failed with return code {e.returncode}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr}"
        if e.stdout:
            error_msg += f"\nStdout: {e.stdout}"
        print(f"Error: {error_msg}")
        results_content = error_msg
    finally:
        local_results_file.close()
        os.unlink(local_results_file.name)

    return success, results_content


def parse_gups_results(results_content: str) -> tuple[float, dict, dict]:
    # Parse the results content.
    # Format:
    # Elapsed time: <time_in_seconds> seconds.
    # GUPS = <gups_value>
    results_lines = results_content.strip().split("\n")

    gups_value = None
    elapsed_time = None
    for line in results_lines:
        if line.startswith("GUPS ="):
            gups_value = float(line.split("=")[1].strip())
        elif line.startswith("Elapsed time:"):
            elapsed_time = float(line.split(":")[1].strip().split()[0])
    assert gups_value is not None, "GUPS value not found in results."
    assert elapsed_time is not None, "Elapsed time not found in results."

    results = {
        "gups": gups_value,
        "elapsed_time_seconds": elapsed_time,
    }
    artifacts_dict = {
        "gups_value": f"We tested your scoring function on a GUPS benchmark. The GUPS value for this scoring function was {gups_value} (higher is better).",
        "elapsed_time": f"We tested your scoring function on a GUPS benchmark. The elapsed time for this scoring function was {elapsed_time} seconds.",
    }
    combined_score = gups_value * 1000

    return combined_score, results, artifacts_dict


def parse_gapbs_results(results_content: str) -> tuple[float, dict, dict]:
    # Parse the results content.
    # Format:
    # Average Time: <time_in_seconds>
    # Elapsed (wall clock) time (h:mm:ss or m:ss): 1:31.56
    results_lines = results_content.strip().split("\n")

    average_time = None
    elapsed_time = None
    for line in results_lines:
        if "Average Time:" in line:
            average_time = float(line.split(":")[1].strip())
        elif "Elapsed (wall clock) time" in line:
            # Extract the time substring
            match = re.search(r":\s*([\d:.]+)$", line)
            if not match:
                raise ValueError("Could not parse elapsed time")

            # Split based on number of colons (m:ss or h:mm:ss)
            time_str = match.group(1)
            parts = time_str.split(":")
            if len(parts) == 2:  # m:ss
                minutes = int(parts[0])
                seconds = float(parts[1])
                elapsed_time = minutes * 60 + seconds
            elif len(parts) == 3:  # h:mm:ss
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                elapsed_time = hours * 3600 + minutes * 60 + seconds
            else:
                raise ValueError(f"Unexpected time format: {time_str}")

    print(f"Parsed average_time: {average_time}, elapsed_time: {elapsed_time}")

    assert average_time is not None, "Average time not found in results."
    assert elapsed_time is not None, "Elapsed time not found in results."

    results = {
        "average_time_seconds": average_time,
        "elapsed_time_seconds": elapsed_time,
    }
    artifacts_dict = {
        "average_time": f"We tested your scoring function on a GAPBS benchmark. The average time for one iteration was {average_time} seconds.",
        "elapsed_time": f"We tested your scoring function on a GAPBS benchmark. The total elapsed time for the benchmark was {elapsed_time} seconds.",
    }
    combined_score = 1000 / elapsed_time if elapsed_time > 0 else 0

    return combined_score, results, artifacts_dict


def parse_silo_results(results_content: str) -> tuple[float, dict, dict]:
    # Parse the results content.
    # Format:
    # agg_throughput: <throughput_value> ops/sec
    # DRAM reads:[<dram_reads>] NVM reads:[<nvm_reads>] Writes:[<writes>] throttle/unthrottle_cnt:[<throttle_cnt>/<unthrottle_cnt>] cools:[<cools>]
    results_lines = results_content.strip().split("\n")

    throughput_value = None
    reads_line = None
    txn_breakdown_line = None
    for line in results_lines:
        if "agg_throughput:" in line:
            throughput_value = (
                float(line.split(":")[1].strip().split()[0]) / 1000
            )  # Convert to Kops/sec
        if "DRAM reads:" in line:
            reads_line = line.strip()
        if "txn breakdown" in line:
            txn_breakdown_line = line.strip()
    assert throughput_value is not None, "Throughput value not found in results."

    results = {
        "throughput": throughput_value,
    }

    artifacts_dict = {
        "throughput_value": f"We tested your scoring function on a TPCC benchmark. The aggregate throughput for this scoring function was {throughput_value} Kops/sec (higher is better).",
        "accesses_breakdown": f"The accesses made for this TPCC benchmark were: {reads_line}. Use this information to develop a better heuristic.",
        "txn_breakdown": f"The transaction breakdown from the TPCC benchmark was: {txn_breakdown_line}. Use this information to develop a better heuristic.",
    }
    combined_score = throughput_value

    return combined_score, results, artifacts_dict


def evaluate(program_file: str) -> EvaluationResult:
    if not os.getenv("EVALUATION_CONFIG"):
        raise ValueError("EVALUATION_CONFIG environment variable not set.")
        
    try:
        eval_result, _ = evaluate_internal(program_file)
        return eval_result
    except Exception as e:
        return EvaluationResult(
            metrics={"combined_score": 0.0}, artifacts={"error": str(e)}
        )


def evaluate_internal(
    program_file: str, insert_into_mongo=True
) -> tuple[EvaluationResult, dict]:
    assert program_file.endswith(".cpp"), "Program file must be a .cpp file."
    MONGO_RESULT_DICT = {}
    MONGO_RESULT_DICT["timestamp"] = time.time()
    MONGO_RESULT_DICT["githash"], MONGO_RESULT_DICT["diff"] = get_githash_and_diff()
    METRICS_DICT = {"combined_score": 0.0}

    # Get the evaluation config from environment variable.
    config_path = os.getenv("EVALUATION_CONFIG")
    if config_path:
        print(f"[INFO] Reading config from {config_path}...")
        with open(config_path, "r") as f:
            eval_config = yaml.safe_load(f)
    else:
        raise ValueError("EVALUATION_CONFIG environment variable not set.")

    # Read experiment name and cloudlab config file from config.memory_tiering_search.
    benchmark = eval_config["memory_tiering_search"]["benchmark"]
    exp_name = eval_config["memory_tiering_search"]["exp_name"]

    # Validate benchmark (currently only "gups", "gapbc", "gappr", and "silo" are supported).
    assert benchmark in ["gups", "gapbc", "gappr", "silo"], f"Unknown benchmark: {benchmark}"
    
    MONGO_RESULT_DICT["benchmark"] = benchmark

    # Read cloudlab config from evaluator.yaml to get the number of nodes.
    cloudlab_config = eval_config["cloudlab_config"]
    user_name = cloudlab_config["user_name"]
    cloudlab_exp_name = cloudlab_config["exp_name"]
    domain = cloudlab_config["domain"]
    start_node = cloudlab_config["start_node"]
    num_nodes = cloudlab_config["num_nodes"]

    # Acquire lock and read the cloudlab node index to use.
    cloudlab_node_file = pathlib.Path(__file__).parent / "results" / f"{exp_name}_node_index.txt"
    cloudlab_lock_file = pathlib.Path(__file__).parent / "results" / f"{exp_name}_node_index.lock"
    with open(cloudlab_lock_file, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)

        # Read the cloudlab node index to use.
        if cloudlab_node_file.exists():
            with open(cloudlab_node_file, "r") as f:
                node_index = int(f.read().strip())
        else:
            node_index = start_node

        # Write the next node index back to the file.
        next_node = (node_index - start_node + 1) % num_nodes + start_node
        with open(cloudlab_node_file, "w") as f:
            f.write(str(next_node))  # using num_nodes from config

        fcntl.flock(lock_f, fcntl.LOCK_UN)
    host = f"{user_name}@node{node_index}.{cloudlab_exp_name}.{domain}"
    print(f"Using cloudlab node: {host}")

    # Compile and build the given program.
    program_file = os.path.realpath(program_file)
    success, msg = compile_and_check(program_file, host)
    if not success:
        if "SCP failed" in msg:
            # SCP failed, likely a transient error - we should retry later.
            raise RuntimeError(f"SCP failed: {msg}")

        return (
            EvaluationResult(
                metrics=METRICS_DICT,
                artifacts={"error": f"Compilation failed: {msg}"},
            ),
            MONGO_RESULT_DICT,
        )

    # Run the evaluation on the remote node.
    success, results_content = run_and_get_results(host, benchmark)
    if not success:
        return (
            EvaluationResult(
                metrics=METRICS_DICT,
                artifacts={"error": f"Evaluation failed: {results_content}"},
            ),
            MONGO_RESULT_DICT,
        )

    print(f"[INFO] Evaluation results:\n{results_content}")
    if benchmark == "gups":
        combined_score, results, artifacts_dict = parse_gups_results(results_content)
    elif benchmark == "gapbc" or benchmark == "gappr":
        combined_score, results, artifacts_dict = parse_gapbs_results(results_content)
    elif benchmark == "silo":
        combined_score, results, artifacts_dict = parse_silo_results(results_content)
    else:
        # Ideally should not reach here due to earlier check.
        raise ValueError(f"Unknown benchmark: {benchmark}")
    print(f"Combined Score: {combined_score}\nResults: {results}")

    # Update METRICS_DICT.
    METRICS_DICT["combined_score"] = combined_score
    METRICS_DICT["evaluation_node"] = host

    # Save the code and results to MONGO_RESULT_DICT.
    with open(program_file, "r") as f:
        MONGO_RESULT_DICT["source_code"] = f.read()
    MONGO_RESULT_DICT["source_hash"] = hashlib.sha256(
        MONGO_RESULT_DICT["source_code"].encode()
    ).hexdigest()
    MONGO_RESULT_DICT["results"] = results

    # Insert into mongo
    if insert_into_mongo:
        print("[INFO] Inserting evaluation result into MongoDB...")
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client["MemoryTieringSearch"]
        try:
            collection = db[f"{exp_name}_evaluations"]
            collection.insert_one(MONGO_RESULT_DICT)
        except Exception as e:
            print(f"[WARN] Failed to insert evaluation result into MongoDB: {str(e)}")

    return (
        EvaluationResult(metrics=METRICS_DICT, artifacts=artifacts_dict),
        MONGO_RESULT_DICT,
    )
