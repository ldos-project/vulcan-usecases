#!/bin/bash
# Evaluate the Silo TPCC benchmark on Cloudlab and collect results.
# Arguments:
# 1: Host name
# 2: Output file to store results.

HOST=$1
OUTPUT_FILE=$2

echo "Host: $HOST"

# First delete the silo_results.txt and log.txt files on the remote host if they exist.
echo "Cleaning up previous results on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "rm -f \$HOME/silo_results.txt \$HOME/log.txt"

# Also, kill any existing tmux sessions named silo_benchmark.
ssh -o StrictHostKeyChecking=no $HOST "tmux kill-session -t silo_benchmark 2>/dev/null || true"

# Run the Silo TPCC benchmark and collect results.
echo "Running Silo TPCC benchmark on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "tmux new-session -d -s silo_benchmark \"
    rm -f \$HOME/log.txt &&
    cd /mnt/data/workloads/silo/silo &&
    numactl -N0 sudo LD_PRELOAD=\$HOME/tiering_solutions/src/libarms.so DRAMSIZE=9298771968 NVMSIZE=83022053376 ./out-perf.masstree/benchmarks/dbtest --verbose --bench tpcc --num-threads 20 --scale-factor 100 --runtime 120 --numa-memory 85899345920 > \$HOME/log.txt 2>&1
    \""

# Sleep 210 seconds, then probe every 5 seconds until the tmux session is gone.
sleep 210
while ssh -o StrictHostKeyChecking=no $HOST "tmux has-session -t silo_benchmark" 2>/dev/null; do
    echo "Benchmark still running on $HOST, sleeping 5 seconds ..."
    sleep 5
done

# Get the statistics -- read the lines that contain 'agg_throughput'
# Also read the very last line containing 'DRAM reads:'
# Finally, read the line containing 'txn breakdown'
echo "Collecting results from $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "
    rm -f \$HOME/silo_results.txt &&
    grep 'agg_throughput' \$HOME/log.txt >> \$HOME/silo_results.txt &&
    grep 'DRAM reads:' \$HOME/log.txt | tail -n 1 >> \$HOME/silo_results.txt &&
    grep 'txn breakdown' \$HOME/log.txt >> \$HOME/silo_results.txt
    "

# Copy the results back to the local machine.
echo "Copying results back to local machine ..."
scp -o StrictHostKeyChecking=no $HOST:~/silo_results.txt $OUTPUT_FILE
