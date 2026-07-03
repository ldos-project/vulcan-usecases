# Artifact for Vulcan Case Study on Multi-Region Spot VM Scheduling
This branch of the repo is built on top of the multi-region extension of the "Can't Be Late" problem from [ADRS](https://github.com/UCB-ADRS/ADRS). In this branch, you will be able to reproduce the results of Vulcan's Multi-Region Spot VM Scheduling case study (§7.1.2, Figure 7).

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
1. To create the plot in our paper, download `cbl_multi_results.tar.gz` from [our Zenodo repo for this paper](https://doi.org/10.5281/zenodo.20361338), and extract it into the current directory (`tar xzvf cbl_multi_results.tar.gz`).
2. Run `python3 plot_results.py` to recreate the main plot -- this script uses the precomputed results JSONs in `cbl_multi_results/` to create `multi-region-result.png`.
3. To run the synthesized heuristics yourself and confirm they match our pre-generated results files, run the following commands in the root of the repository:
```bash
mkdir -p results/

# Greedy baseline (UP-RR savings derive from this)
python full_eval.py initial_program.py --output results/full_eval_initial_program.json

# ADRS (unconstrained Python synthesis)
python full_eval.py paper_heuristics/adrs_best.py --output results/full_eval_python_generic.json

# Vulcan
./vulcan/build.sh paper_heuristics/vulcan_best.cpp
python full_eval.py initial_vulcan.py --output results/full_eval_vulcan_generic.json
```

Then re-plot against your regenerated JSONs with `python3 plot_results.py --results-dir results`.

## Running the search yourself
1. Setup LiteLLM to use AWS Bedrock for inference. Create a file called `aws.sh` using `aws.sh.template` as inspiration. We use (`claude-sonnet-4-5`, `claude-opus-4-5`). Start the proxy by doing:
   ```bash
   source aws.sh
   litellm --config litellm_config.yaml --port 4000 # model names exposed by LiteLLM: `claude-sonnet`, `claude-opus`.
   ```

2. **ADRS BASELINE: Pure Python-based search.** Run the baseline and evaluate it by doing:
```bash
mkdir -p results/python/
openevolve-run initial_program.py evaluator.py --config config.yaml --output results/python/generic/ --iterations 100 --log-level INFO
```

3. **Proposed approach: Vulcan.** Uses two composed libvulcan policies (RANK + VALUE) compiled to a shared library:
   - **VALUE** decides per tick: SPOT / ON_DEMAND / CHANGE_REGION (current-region info only)
   - **RANK** fires only on CHANGE_REGION, scores regions using cached per-object observations
   - No oracle: only the current region is observed each tick; other regions retain stale cached state

   Test if things build with `bash vulcan/build.sh`, then run:
```bash
mkdir -p results/vulcan/
openevolve-run vulcan/base_policy.cpp evaluator.py --config config_vulcan.yaml --output results/vulcan/generic/ --iterations 100 --log-level INFO
```
Once the runs complete, modify the eval commands and `plot_results.py` from above to analyze your search results.

## Scenarios
The multi-region benchmark from ADRS defines six scenarios, each with 100 evaluation traces (600 total):

| Scenario ID | Instance class | Description |
|---|---|---|
| S1 | `2_zones_same_region` | 2 correlated zones in us-east-1 |
| S2 | `2_regions_east_west` | 2 uncorrelated regions (us-east-2 + us-west-2) |
| S3 | `3_regions_diverse` | 3 cross-region (us-east-1 + us-east-2 + us-west-2) |
| S4 | `3_zones_same_region` | 3 zones in us-east-1 |
| S5 | `5_regions_high_diversity` | 5 diverse regions |
| S6 | `all_9_regions` | all 9 available regions |
