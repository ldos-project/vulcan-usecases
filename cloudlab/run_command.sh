#!/bin/bash
# This script will run the given command on all nodes in a CloudLab experiment.
# Arguments:
# 1: Cloudlab username
# 2: Name of the experiment
# 3: Start node of experiment
# 4: End node of experiment

USER_NAME=$1
EXP_NAME=$2
END_NODE=$4
DOMAIN="wisc.cloudlab.us"
PROJECT_EXT="ldos-ut-PG0"

# Get the list of hostnames for all nodes in the experiment
i=$3
HOSTS=()
while [ "$i" -le "$END_NODE" ]; do
    HOSTS+=("$USER_NAME@node$i.$EXP_NAME.$PROJECT_EXT.$DOMAIN")
    i=$((i+1))
done

# Run command on every node
for host in "${HOSTS[@]}"; do
  echo $host
  # ssh -o StrictHostKeyChecking=no $host "rm -rf tiering_solutions"
  # ssh -o StrictHostKeyChecking=no $host "ls -lh /mnt/ssd/inputs"
  ssh -o StrictHostKeyChecking=no $host "
    sudo apt install autoconf libnuma-dev libdb++-dev libpmem-dev libaio-dev libssl-dev zlib1g-dev -y
    cd /mnt/data/workloads/silo/silo
    MODE=perf make -j dbtest"
  # ssh -o StrictHostKeyChecking=no $host "df -h"
  # ssh -o StrictHostKeyChecking=no $host "tmux kill-server 2>/dev/null || true"
done