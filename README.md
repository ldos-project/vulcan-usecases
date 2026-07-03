# Artifact for Vulcan Case Study on Spot VM Scheduling
This branch of the repo is built on top of [this folder from the ADRS repo](https://github.com/UCB-ADRS/ADRS/tree/main/openevolve/examples/ADRS/cant-be-late). In this branch, you will be able to reproduce the results of Vulcan's Single Region Spot VM Scheduling case study.

## Installation
This project uses the `uv` package manager, which you can install via `pip3 install uv`.

```bash
uv venv .cbl && source .cbl/bin/activate
cd simulator
uv sync --active
mkdir -p data
[ -d data/real ] || tar -xzf real_traces.tar.gz -C data
```

# Reproducing results from the paper
1. To create the plots in our paper, download `cbl_results.tar.gz` from [our Zenodo repo for this paper](https://doi.org/10.5281/zenodo.20361338), and extract it into the current directory (`tar xzvf cbl_results.tar.gz`).
2. Run `python3 plot_main_result.py` and `python3 plot_evolution_comparison.py` to recreate the two main plots -- these scripts will use precomputed results JSONs which are present in the `cbl_results.tar.gz` to create files `cbl-single-region.svg` and `evolution-comparison-cbl.svg` respectively.
3. To run the synthesized heuristics yourself and confirm they match our pre-generated results files, run the following commands in the root of the repository:
```bash
mkdir -p results/
python full_eval.py referenced_up.py --output results/results_referenced_up.json --progress

# ADRS
python full_eval.py cbl_results/adrs_openevolve/best/best_program.py --baseline-cache results/results_referenced_up.json --output results/results_adrs.json --progress

# Vulcan
./vulcan/build.sh cbl_results/vulcan/best/best_program.cpp
python full_eval.py initial_vulcan.py --baseline-cache results/results_referenced_up.json --output results/results_vulcan.json --progress

# Vulcan (no listeners)
./vulcan/build.sh cbl_results/vulcan_no_listeners/best/best_program.cpp
python full_eval.py initial_vulcan.py --baseline-cache results/results_referenced_up.json --output results/results_vulcan_no_listeners.json --progress
```

## Running the search yourself
1. Setup LiteLLM to use AWS Bedrock for inference. Create a file called `aws.sh` using `aws.sh.template` as inspiration . We use (`claude-sonnet-4-5`, `claude-opus-4-5`). Start the proxy by doing:
   ```bash
   source aws.sh
   litellm --config litellm_config.yaml --port 4000 # model names exposed by LiteLLM: `claude-sonnet`, `claude-opus`.
   ```

2. **ADRS BASELINE: Pure Python-based search.** Run the baseline and evaluate it by doing:
```bash
mkdir -p results/adrs/
openevolve-run initial_greedy.py evaluator.py --config config.yaml --output results/adrs/ --iterations 100  --log-level INFO
```

3. **Proposed approach: Vulcan**
```bash
mkdir -p results/vulcan/
openevolve-run vulcan/base_policy.cpp evaluator.py   --config config_vulcan.yaml   --output results/vulcan/out_all_instances   --iterations 100   --log-level INFO
```
Once the runs complete, you can modify the eval commands and the plotting scripts from above to analyze the results of your search.