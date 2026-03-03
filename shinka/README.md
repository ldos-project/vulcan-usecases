## Shinka Evolve for cache search with Vulcan

NOTE: For some reason, the evolution **used to** gets stuck after 2-3 iterations. I think it should no longer happen. Let me know if it does.

0. Create a file called `aws.sh` using `aws.sh.template` (see parent directory) and then source it.
1. Install ShinkaEvolve: `pip install shinka-evolve`. 
2. Run evolution:
    - `python shinka/shinka_runner.py --config shinka.yaml --task-dir shinka/ --results_dir shinka/results/run1/ --num_generations 10`
3. Run `shinka_visualize --port 8888 --open` to see progress of the evolution.