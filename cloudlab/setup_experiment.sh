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

echo "Hosts in the experiment:"
for host in "${HOSTS[@]}"; do
    echo "$host"
done

# Own all important directories
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Changing ownership on $host ..."
  ssh -o StrictHostKeyChecking=no $host "tmux new-session -d -s chown \"
    sudo chown -R \$USER: /mnt &&
    sudo chown -R \$USER: /usr/local/hemem
    \""
done
wait

# Clone the memory-tiering repository
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Setting up on $host ..."
  ssh -o StrictHostKeyChecking=no $host "tmux new-session -d -s setup \"
    git clone https://github.com/SujayYadalam94/tiering_solutions.git --branch vulcan-artifact &&
    pushd tiering_solutions &&
    git submodule update --init src/libvulcan/ &&
    ln -sfn /usr/local/hemem/linux linux &&
    popd
    \""
done
wait

# Push the gapbs.patch file to all nodes
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Pushing gapbs.patch to $host ..."
  scp -o StrictHostKeyChecking=no ./cloudlab/gapbs.patch $host:~/
done
wait

# Create the data/ directory and clone workloads.
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Cloning workloads on $host ..."
  ssh -o StrictHostKeyChecking=no $host "tmux new-session -d -s workloads \"
    set -ex  # Exit on any error
    exec > /tmp/workloads_setup.log 2>&1  # Log all output

    if [ ! -d \"/mnt/data\" ]; then
      echo 'Directory /mnt/data does not exist. setting up SSD...'
      echo -e \"n\\n\\n\\n\\nY\\nw\" | sudo fdisk /dev/sda
      # Check that the 4th partition was created successfully
      if [ ! -b /dev/sda4 ]; then
          echo 'Error: Failed to create 4th partition.'
          exit 1
      fi
      sudo mkfs.ext4 /dev/sda4
      sudo mkdir -p /mnt/data
      sudo mount /dev/sda4 /mnt/data
    fi

    sudo chown -R \$USER: /mnt/data

    sudo mkdir -p /mnt/data/inputs/
    sudo chown -R \$USER: /mnt/data/inputs
    
    cd /mnt/data
    if [ ! -d 'workloads' ]; then
      git clone --recursive https://github.com/SujayYadalam94/workloads.git
    fi
    sudo chown -R \$USER: workloads

    cd /mnt/data/workloads/gups_hemem
    make -j
    echo 'gups_hemem build complete'

    sudo apt-get update
    sudo apt install autoconf libnuma-dev libdb++-dev libpmem-dev libaio-dev libssl-dev zlib1g-dev -y
    cd /mnt/data/workloads/silo/silo
    MODE=perf make -j dbtest

    cd /mnt/data/workloads/gapbs
    git apply ~/gapbs.patch || echo 'Patch already applied or not found'
    make gen-twitter
    make -j
    mv benchmark/graphs/twitter.sg /mnt/data/inputs/
    \""
done
wait

# Wait until both the chown and setup tmux sessions are done
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Waiting for setup to complete on $host ..."
  ssh -o StrictHostKeyChecking=no $host "
    while tmux has-session -t chown 2>/dev/null || tmux has-session -t setup 2>/dev/null || tmux has-session -t workloads 2>/dev/null; do
      sleep 5
    done
    "
done
wait

# Add crontab entries on all nodes
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Setting up crontab on $host ..."
  ssh -o StrictHostKeyChecking=no $host "
    (sudo crontab -l 2>/dev/null; cat <<'EOF'
@reboot sudo ndctl create-namespace -f -e namespace0.0 --mode=devdax --align 2M
@reboot sudo ndctl create-namespace -f -e namespace1.0 --mode=devdax --align 2M
@reboot echo 1000000 > /proc/sys/vm/max_map_count
@reboot sudo modprobe msr
@reboot sudo wrmsr --processor 10 0x620 0x707
@reboot echo 0 | sudo tee /proc/sys/kernel/numa_balancing
@reboot echo 0 > /proc/sys/kernel/randomize_va_space
@reboot sudo grub-reboot \"Advanced options for Ubuntu>Ubuntu, with Linux 5.1.0-rc4+\"
EOF
) | sudo crontab -
  "
done
wait

# Update GRUB with memmap kernel boot parameter on all nodes
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Updating GRUB on $host ..."
  ssh -o StrictHostKeyChecking=no $host "
    sudo sed -i 's/GRUB_CMDLINE_LINUX=\"\(.*\)\"/GRUB_CMDLINE_LINUX=\"\1 memmap=36G!4G,80G!104G\"/' /etc/default/grub &&
    sudo update-grub
  "
done
wait

# Reboot all nodes to finalize setup
for i in "${!HOSTS[@]}"; do
  host=${HOSTS[$i]}
  echo "Rebooting $host ..."
  ssh -o StrictHostKeyChecking=no $host "sudo reboot"
done
wait

echo "Setup complete on all nodes."