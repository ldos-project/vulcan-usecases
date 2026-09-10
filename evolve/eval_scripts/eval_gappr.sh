#!/bin/bash
# Evaluate the GapBS (PR) benchmark on Cloudlab and collect results.
# Arguments:
# 1: Host name
# 2: Output file to store results.

HOST=$1
OUTPUT_FILE=$2

echo "Host: $HOST"

# First delete the gapbs_results.txt and log.txt files on the remote host if they exist.
echo "Cleaning up previous results on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "rm -f \$HOME/gapbs_results.txt \$HOME/log.txt"

# Also, kill any existing tmux sessions named gapbs_benchmark.
ssh -o StrictHostKeyChecking=no $HOST "tmux kill-session -t gapbs_benchmark 2>/dev/null || true"

# Run the GapBS (PR) benchmark and collect results.
echo "Running GapBS PR benchmark on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "tmux new-session -d -s gapbs_benchmark \"
    rm -f \$HOME/log.txt &&
    /usr/bin/time -v numactl -N0 sudo DRAMSIZE=1558183936 NVMSIZE=21078474752 LD_PRELOAD=\$HOME/tiering_solutions/src/libarms.so OMP_NUM_THREADS=16 MIN_INTERPOSE_MEM_SIZE=134217728 /mnt/data/workloads/gapbs/pr -n 8 -f /mnt/data/inputs/twitter.sg > \$HOME/log.txt 2>&1
    \""

# Sleep 120 seconds, then probe every 5 seconds until the tmux session is gone.
sleep 120
while ssh -o StrictHostKeyChecking=no $HOST "tmux has-session -t gapbs_benchmark" 2>/dev/null; do
    echo "Benchmark still running on $HOST, sleeping 5 seconds ..."
    sleep 5
done

# Get the statistics -- read the lines that contain 'Elapsed Time' and 'Average Time'
echo "Collecting results from $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "
    rm -f \$HOME/gapbs_results.txt &&
    grep 'Average Time' \$HOME/log.txt >> \$HOME/gapbs_results.txt &&
    grep 'Elapsed (wall clock) time' \$HOME/log.txt >> \$HOME/gapbs_results.txt
    "

# Copy the results back to the local machine.
echo "Copying results back to local machine ..."
scp -o StrictHostKeyChecking=no $HOST:~/gapbs_results.txt $OUTPUT_FILE
