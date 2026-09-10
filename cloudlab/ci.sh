#!/bin/bash
# This script sets up the environment for a CloudLab experiment.
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

# Push the src/ directory to all nodes
TARBALL="src.tar.gz"
tar -czf $TARBALL tiering_solutions/src/
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Copying source to $host ..."
  scp -o StrictHostKeyChecking=no $TARBALL $host:~/
  ssh -o StrictHostKeyChecking=no $host "
    tar -xzf $TARBALL &&
    rm $TARBALL"
done
wait
rm $TARBALL

# Make the source.
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Building source on $host ..."
  ssh -o StrictHostKeyChecking=no $host "
    pushd tiering_solutions/src &&
    make &&
    make libllmcode.so &&
    popd"
done
wait

echo "Source setup complete on all nodes."