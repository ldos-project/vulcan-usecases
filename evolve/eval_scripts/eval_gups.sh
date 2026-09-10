#!/bin/bash
# Evaluate the gups-hotset-move benchmark on Cloudlab and collect results.
# Arguments:
# 1: Host name
# 2: Output file to store results.

HOST=$1
OUTPUT_FILE=$2

echo "Host: $HOST"

# First delete the gups_results.txt and log.txt files on the remote host if they exist.
echo "Cleaning up previous results on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "rm -f \$HOME/gups_results.txt \$HOME/log.txt"

# Run the gups-hotset-move benchmark and collect results.
echo "Running gups-hotset-move benchmark on $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "tmux new-session -d -s gups_benchmark \"
    rm -f \$HOME/log.txt &&
    numactl -N0 sudo DRAMSIZE=7625244672 NVMSIZE=77311508480 LD_PRELOAD=\$HOME/tiering_solutions/src/libarms.so /mnt/data/workloads/gups_hemem/gups-hotset-move 16 200000000 36 8 33 > \$HOME/log.txt
    \""

# Sleep 60 seconds, then probe every 5 seconds until the tmux session is gone.
sleep 60
while ssh -o StrictHostKeyChecking=no $HOST "tmux has-session -t gups_benchmark" 2>/dev/null; do
    echo "Benchmark still running on $HOST, sleeping 5 seconds ..."
    sleep 5
done

# Get the statistics -- read the lines that contain "Elapsed Time" and "GUPS".
echo "Collecting results from $HOST ..."
ssh -o StrictHostKeyChecking=no $HOST "
    rm -f \$HOME/gups_results.txt &&
    grep 'Elapsed time' \$HOME/log.txt >> \$HOME/gups_results.txt &&
    grep 'GUPS' \$HOME/log.txt >> \$HOME/gups_results.txt
    "

# Copy the results back to the local machine.
echo "Copying results back to local machine ..."
scp -o StrictHostKeyChecking=no $HOST:~/gups_results.txt $OUTPUT_FILE
