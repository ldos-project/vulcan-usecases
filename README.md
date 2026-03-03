# Artifact for Vulcan Case Study on Cache Eviction
This branch of the repo reproduces the results of Vulcan's Cache Eviction case study.

## Installation
This project uses `uv` for Python dependency management (`pip3 install uv`) and requires CMake, GLib, and zstd for building libCacheSim.

```bash
# Clone submodules (libcachesim + anvil)
git submodule update --init --recursive

# Set up the Python environment
uv venv .cache && source .cache/bin/activate
uv pip install pymongo matplotlib numpy pandas openevolve shinka-evolve 'litellm[proxy]'

# Install system dependencies and build libCacheSim
bash setup_experiment.sh

# Build the Anvil safety-gate binary once (requires ocaml + dune + menhir + z3; see anvil/README.md).
# You can skip this step until you plan to run the search with --use_anvil.
(cd anvil && dune build ./bin/main.exe)
```

You will also need a running MongoDB instance (default: `mongodb://localhost:27017/`) to store and query results. [Install instructions for MongoDB](https://www.mongodb.com/docs/manual/installation/).

# Reproducing plots
## From precomputed results
1. Download `caching_results.tar.gz` from [our Zenodo repo for this paper](https://doi.org/10.5281/zenodo.20361338), and extract it into the current directory:
   ```bash
   tar xzvf caching_results.tar.gz
   ```
   This produces four MongoDB dump directories: `Baselines_size/`, `Baselines_nosize/`, `ChunkedTraces_size/`, and `ChunkedTraces_nosize/`.

2. Restore the dumps into your local MongoDB:
   ```bash
   mongorestore --db Baselines_size Baselines_size/
   mongorestore --db Baselines_nosize Baselines_nosize/
   mongorestore --db ChunkedTraces_size ChunkedTraces_size/
   mongorestore --db ChunkedTraces_nosize ChunkedTraces_nosize/
   ```

3. Generate the paper plots:
   ```bash
   # Main results — size-aware, 10% cache (Figure 8a)
   python3 plots/plot_workload_instances.py --cache-size 0.1 --plot

   # Main results — size-aware, 0.1% cache (Figure 8b)
   python3 plots/plot_workload_instances.py --cache-size 0.001 --plot

   # No-size variants (Figure 12a, 12b)
   python3 plots/plot_workload_instances.py --cache-size 0.1 --ignore-size --plot
   python3 plots/plot_workload_instances.py --cache-size 0.001 --ignore-size --plot
   ```


## Rerun identified heuristics
To independently rerun all results (baselines + evolved heuristics) on full traces:

1. Download traces from the [CMU PDL Trace Repository](https://ftp.pdl.cmu.edu/pub/datasets/) by running `bash download_traces.sh`. This downloads 8 traces (~4.5GB total) into `libcachesim/data/`.

2. Run `python3 evaluate_all.py`. This re-runs all baselines and evolved heuristics on full traces, inserting them into `REPRODUCED_*` databases. **Estimated runtime: ~10 hours** (baselines run all algorithms in a single multi-cache pass per trace; heuristic evaluations run sequentially across 8 scenarios x 8 traces).

3. Generate plots from reproduced data:
```bash
python3 plots/plot_workload_instances.py --cache-size 0.1 --plot --reproduce
python3 plots/plot_workload_instances.py --cache-size 0.001 --plot --reproduce
python3 plots/plot_workload_instances.py --cache-size 0.1 --ignore-size --plot --reproduce
python3 plots/plot_workload_instances.py --cache-size 0.001 --ignore-size --plot --reproduce
```

# Running the search yourself
## Download chunked traces
The evolutionary search operates on chunked traces (first 1M requests of each full trace) for faster iteration. Each chunk is the first 1M-request prefix of the corresponding full trace, with the oracle (`next_access_vtime`) recomputed for that window. Download the pre-computed chunks from Zenodo:

```bash
# Download chunk_data.tar.gz from our Zenodo repo (link above)
mkdir -p libcachesim/data/chunked
tar xzf chunk_data.tar.gz -C libcachesim/data/chunked/
```

This places 8 `_chunk_000.oracleGeneral.bin.zst` files into `libcachesim/data/chunked/`. `traces.csv` indexes traces by short name (e.g. `wMSR`), so symlink each chunk to its short name:

```bash
(cd libcachesim/data/chunked && for f in *_chunk_000.oracleGeneral.bin.zst; do ln -sf "$f" "${f%_chunk_000.oracleGeneral.bin.zst}.oracleGeneral.bin.zst"; done)
```

## LLM setup
Set up LiteLLM to bridge OpenEvolve/Shinka (OpenAI SDK clients) to AWS Bedrock. Create `aws.sh` at the repo root using `aws.sh.template` and export `AWS_DEFAULT_REGION` (e.g. `us-east-1`). The Vulcan paper uses `claude-sonnet-4-5` and `claude-opus-4-5` — already mapped in `openevolve/litellm_config.yaml` and re-used by both frameworks.

```bash
source aws.sh && export AWS_DEFAULT_REGION=us-east-1
litellm --config openevolve/litellm_config.yaml --port 4000
```

Note: `openevolve/litellm_config.yaml` points at a shared RDS for cost tracking. To run purely locally, drop the `database_url` line (see `cbl-artifact/litellm_config.yaml` for a minimal reference) — the proxy still works, just without persistent usage stats.

Smoke test in another terminal:

```bash
curl -s http://localhost:4000/v1/chat/completions -H 'Authorization: Bearer sk-1234' -H 'Content-Type: application/json' -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"pong"}],"max_tokens":10}'
```

## Anvil safety gate (`--use_anvil`)
With the flag on, every candidate is checked by `anvil --gate` before compilation. Rejected candidates score `-1` (same as any build/runtime failure) and the rejection reason is fed back to the LLM as an artifact; safe candidates compile and score normally. The prompt documents the Anvil DSL grammar (loaded from `libcachesim/libvulcan/prompts/vulcan_policy_prompt.md`) so the LLM writes Anvil directly. Off (the default), the loop behaves as it did before — plain C++ compile → run → score.

## Using OpenEvolve
```bash
cd openevolve && python openevolve_runner.py initial_program.cpp openevolve_evaluator.py --config config.yaml --traces-dir ../libcachesim/data/chunked --traces-csv ../traces.csv --instance 0 --cache-size-percent 0.1 --use_anvil --iterations 250 --output ./results/run1
```

Add `--insert-mongo` to persist every candidate + score into MongoDB (default `mongodb://localhost:27017/`).

## Using ShinkaEvolve
```bash
python shinka/shinka_runner.py --config-fname shinka.yaml --task-dir shinka/ --results_dir shinka/results/run1/ --traces-dir libcachesim/data/chunked --traces-csv traces.csv --instance 0 --cache-size-percent 0.1 --use_anvil --num_generations 50
```

## Full pipeline (all clusters)
```bash
python3 run_pipeline.py --framework openevolve --traces-dir libcachesim/data/ --min-traces 50 --use_anvil
```

## Development guide

### Testing the setup
Test if everything is working well:
```bash
python3 evaluate_cache.py --default
```
This creates a simple LRU policy in the Vulcan interface, copies it over to the `LLMCode.h` file, builds the code, and evaluates the performance of your cache replacement algorithm on a set of traces.

### Generating prompts
You can get an initial draft of the prompt to use for evolution:
```bash
PRINT_VULCAN_CACHE_PROMPT=1 ./build/run_algo.o ./libcachesim/data/wMSR.oracleGeneral.bin.zst 0.1 --ignore
```
This gives you info on the task, the features and corresponding listeners that can be attached, and the syntax of the expected policy.
