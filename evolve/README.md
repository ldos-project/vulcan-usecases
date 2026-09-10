# OpenEvolve for Memory Tiering Policy Search

Instance-optimal memory tiering policies with libVulcan.

## Setup LLMs
0. Create a file called `aws.sh` using `aws.sh.template`.
1. OpenEvolve unfortunately does not support AWS Bedrock directly. So, we'll be using LiteLLM (a local proxy) to act as our bridge. Run `source aws.sh && litellm --config configs/litellm_config.yaml --port 4000` to start the proxy (you have to `pip install litellm[proxy]`).
2. Test if your proxy works (change model name to `claude-opus` to test that as well):
  ```bash
  curl -s http://localhost:4000/v1/chat/completions \
    --header 'Authorization: Bearer sk-1234' \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"Reply with: a comma separated list of the seven colors in a rainbow and one fake, made up color. Output nothing else."}],"max_tokens":35}'
  ```

## Setup evaluator
1. You will have to create an evaluator configuration file based on `configs/evaluator_config.yaml.template`:
   - Copy the template: `cp configs/evaluator_config.yaml.template configs/evaluator_config_<myexp>.yaml` (replace `<myexp>` with your name).
   - Fill in your CloudLab credentials and experiment details (i.e. name of experiment, number of nodes, etc)
   - Set the benchmark name (`gups`, `gapbc` or `gappr`)
2. Make sure the `parallel_evaluations` in `configs/evaluator_config.yaml.template` is set to be equal to the number of cloudlab nodes that you have available.

Before running a full search, you can test the evaluation pipeline (e.g. for GUPS):

```bash
export EVALUATION_CONFIG="configs/evaluator_config_gups.yaml" # tells the evaluator class which task to test
python test_evaluation.py
```

This will run the configured evaluator (i.e. GUPS from the config file located at `EVALUATION_CONFIG`), using `init_simple.cpp` as the memory tiering policy and print evaluation metrics and artifacts -- useful to check that your evaluation setup is working as intended.

## Starting the search - OpenEvolve
0. Ensure MongoDB is running locally on port 27017 (required for storing evaluation results).
1. To run the evolutionary search, you need to set the `EVALUATION_CONFIG` environment variable to point to your evaluator configuration file:
   ```bash
   export EVALUATION_CONFIG="configs/evaluator_config_gups.yaml"
   python run.py init_programs/init_simple.cpp evaluator.py --iterations 150 --output ./results/run_gappr/
   ```
2. To visualize the search results, [clone the OpenEvolve repository](https://github.com/algorithmicsuperintelligence/openevolve) and use the visualizer tool:
   ```bash
      python openevolve/scripts/visualizer.py --path /path/to/your/checkpoint
   ```

## Starting the search - GEPA
Refine a seed C++ policy with GEPA (`refine.py`). Uses the same `EVALUATION_CONFIG` convention as `run.py`; output defaults to `./results/refine_<exp_name>/`.
```bash
export EVALUATION_CONFIG="configs/evaluator_config_gups.yaml"
python refine.py --seed-program init_programs/init_simple.cpp --budget 150
```
GEPA settings (reflection LM, minibatch size, selection strategy) live in `configs/refine_config.yaml`.

## Common errors
- **LiteLLM**: See [vulcan-usecases @ caching](https://github.com/rohitdwivedula/vulcan-usecases/tree/caching/openevolve) for more information on using LiteLLM.
- **CloudLab connection issues**: Verify your CloudLab credentials and node availability in the evaluator config file.
- **MongoDB errors**: Ensure MongoDB is running locally on port 27017.