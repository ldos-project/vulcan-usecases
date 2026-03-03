# OpenEvolve for cache search with Vulcan
0. Create a file called `aws.sh` using `aws.sh.template` (see parent directory).
1. OpenEvolve unfortunately does not support AWS Bedrock directly, I think. So, we'll be using LiteLLM (a local proxy) to act as our bridge. Run `source aws.sh && litellm --config openevolve/litellm_config.yaml --port 4000` to start the proxy (you have to `pip install litellm[proxy]`).
2. Test if your proxy works (change model name to `claude-opus` to test that as well):
  ```bash
  curl -s http://localhost:4000/v1/chat/completions \
    --header 'Authorization: Bearer sk-1234' \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"Reply with: a comma separated list of the seven colors in a rainbow and nothing else."}],"max_tokens":35}'
  ```
2. Run this command to start evolution:
  ```bash
  python openevolve_runner.py initial_program.cpp openevolve_evaluator.py --config config.yaml --iterations 250 --output ./results/run1
  ```
3. If you have `openevolve` cloned somewhere else, you can use their web visualizer to snoop on what is happening:
  ```bash
  python scripts/visualizer.py --path /absolute/path/to/your/results/run1/directory/
  ```

## Cost Tracking with LiteLLM
Instructions for Ubuntu. The config contains support to use cost tracking.

### One time setup
1. Install a postrges client: `sudo apt install postgresql-client`
2. Install required python dependencies: `pip3 install prisma`
3. Try logging into the AWS postgres client: `psql -h litellm.cabciae048ty.us-east-1.rds.amazonaws.com -U root -d litellm  -p 5432` (see passwd in LiteLLM config file)

### Regular use
1. In the `database_url` inside `litellm_config.yaml` change the name after the final `/` to change the db name. You can change this database name to something else for each run if you want to track stats independently. 
2. Try running the `curl` command to send a request:
  ```bash
  curl -s http://localhost:4000/v1/chat/completions \
    --header 'Authorization: Bearer sk-1234' \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"Reply with: a comma separated list of the seven colors in a rainbow and nothing else."}],"max_tokens":35}'
  ```
3. Go to `http://localhost:4000/ui/` and login with `admin` and `sk-1234` (both of these are in the `litellm_config.yaml`). You should see the request you just sent and the cost of that. 
4. You can also create a new key inside

### Common error
If you see an error like `Unable to find Prisma binaries. Please run 'prisma generate' first`, follow these steps:
lite
0. Stop the `litellm` proxy if it is running.

1. Find the  LiteLLM schema and the `prisma-client-py` -- both of these live inside your Python environment::
    ```bash
    find / -name "schema.prisma" -path "*/litellm/*"
    find / -name "prisma-client-py"
    ```

2. Then generate the client, substituting your actual paths:
    ```bash
    PATH="<dir containing prisma-client-py>:$PATH" prisma generate --schema <absolute path to schema.prisma>
    ```

3. Try tunning the proxy again. Should work now. 