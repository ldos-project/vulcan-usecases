# Artifact for Vulcan Case Study on Memory Tiering

This branch of the repo reproduces the results of Vulcan's Memory Tiering case study (Figure 9): the normalized performance (vs the ARMS baseline = 1.0) of a no-op seed heuristic and a single Vulcan-synthesized heuristic — "Vulcan-GUPS", synthesized on GUPS and applied unchanged to all four workloads (`gapbc`, `gappr`, `gups`, `silo`).

The case study uses two environments. The search runs on a CloudLab `c220g5` node where the slow "CXL" tier is *emulated* by clamping a remote NUMA socket's uncore frequency to its minimum; the paper's final Figure 9 is then measured on a real CXL testbed (Micron CZ120). This artifact runs on the emulator, so it reproduces the **trends** of Figure 9 — the no-op seed well below ARMS, the synthesized heuristic matching or slightly exceeding ARMS — not the exact magnitudes (e.g. the synthesized GUPS gain is ~1–3% on the emulator vs 10.2% on real CXL).

The mechanism is a fork of [ARMS](https://www.arxiv.org/abs/2508.04417); the LLM synthesizes only the page-ranking scoring function (`tiering_solutions/src/LLMCode.h`), invoked by Vulcan's `rank_policy`.

## Reproducing the figure

`results_c220g5.csv` is a full c220g5 run (3 policies × 4 workloads × 5 reps); it reproduces the figure with no node and no build — clone the repo, then:

```bash
pip install numpy matplotlib
python plots/plot_paper_figure.py     # -> tiering_normalized.{png,pdf}
```

Normalized to ARMS = 1.0:

| workload | no-op seed | Vulcan-GUPS |
|----------|-----------:|------------:|
| gapbc    | 0.62       | 0.97        |
| gappr    | 0.97       | 1.00        |
| gups     | 0.68       | 1.02        |
| silo     | 0.87       | 1.03        |

As expected on the emulator, the no-op seed is below ARMS on every workload and the synthesized heuristic matches or slightly exceeds ARMS.

## Installation

Re-running the experiment (rather than plotting the committed results) needs a `c220g5` CloudLab node from the [ARMS profile](https://www.cloudlab.us/show-profile.php?uuid=b0839be4-bf29-11f0-90d9-e4434b2381fc), which provides the patched `5.1.0-rc4+` kernel, the `memmap` tier reservation, and the two persistent-memory namespaces.

```bash
git submodule update --init --recursive
uv venv .tiering && source .tiering/bin/activate
uv pip install numpy matplotlib            # reproduction; the search (evolve/) also needs: openevolve pymongo pyyaml 'litellm[proxy]'
(cd anvil && dune build ./bin/main.exe)      # Anvil checker; needs ocaml + dune + menhir + z3
```

## Provisioning the node

ARMS builds against the patched kernel's exported UAPI headers, so symlink them, then build:

```bash
ln -sfn /usr/local/hemem/linux tiering_solutions/linux    # patched kernel's exported UAPI headers
make -C tiering_solutions/src -j                          # -> tiering_solutions/src/libarms.so
```

Stage the workloads into `/mnt/data` (`gups`, `silo`, `gapbs` + the twitter graph; build commands in `cloudlab/setup_experiment.sh`), giving `/mnt/data/workloads/{gups_hemem,silo,gapbs}` and `/mnt/data/inputs/twitter.sg`.

Boot into the ARMS kernel and set the tier knobs (also registered as `@reboot` cron jobs):

```bash
sudo ndctl create-namespace -f -e namespace0.0 --mode=devdax --align 2M   # fast tier /dev/dax0.0
sudo ndctl create-namespace -f -e namespace1.0 --mode=devdax --align 2M   # slow tier /dev/dax1.0
sudo modprobe msr && sudo wrmsr --processor 10 0x620 0x707                 # clamp socket-1 uncore -> CXL-like latency
echo 0 | sudo tee /proc/sys/kernel/numa_balancing
sudo grub-reboot 'Advanced options for Ubuntu>Ubuntu, with Linux 5.1.0-rc4+' && sudo reboot
```

A provisioned node has `uname -r` == `5.1.0-rc4+`, both `/dev/dax0.0` and `/dev/dax1.0`, and the staged `/mnt/data`.

## Re-running the experiment

`run_experiment.py` swaps each policy into `tiering_solutions/src/LLMCode.h`, rebuilds `libarms.so`, and runs each workload under ARMS; the full matrix takes **~2 h** at `--reps 5`.

```bash
python run_experiment.py --reps 5      # -> results.json
python plots/plot_paper_figure.py results.json
```

## Heuristics

`heuristics/` holds the three scoring functions, in the Anvil subset of libVulcan (verify with `for f in heuristics/*.cpp; do anvil/anvil --gate < "$f"; done` — each prints `Safe.`):

- `seed.cpp` — no-op "promote nothing" (scores every page 0).
- `baseline_arms.cpp` — ARMS's dual-horizon EWMA reference policy.
- `synthesized.cpp` — Vulcan-GUPS (paper Listing 4).

## Running the search

See `evolve/README.md`: start a LiteLLM→Bedrock proxy, then `python evolve/run.py init_programs/init_simple.cpp evaluator.py --iterations 100 --output ...`.

## Layout

```
heuristics/          seed / baseline_arms / synthesized scoring functions
results_c220g5.csv   committed reference results
run_experiment.py    measures the 3 policies x 4 workloads on the node -> results.json
plots/               plot_paper_figure.py (figure), plot_results.py (older)
evolve/              the OpenEvolve search that produced the heuristics
cloudlab/            node provisioning scripts
tiering_solutions/   submodule: the ARMS mechanism (fork)
anvil/               submodule: the Anvil checker
```
