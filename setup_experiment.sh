#!/bin/bash
# This script sets up the CloudLab environment for running the experiments.
# It installs necessary packages and configures the environment.

set -eux

# Set PROJECT_DIR to "~/vulcan-usecases" if environment variable is not set
PROJECT_DIR="${PROJECT_DIR:-$HOME/vulcan-usecases}"

sudo apt-get update
sudo apt-get install -y ca-certificates gpg wget

# Install CMake
wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | sudo tee /usr/share/keyrings/kitware-archive-keyring.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ jammy main' | sudo tee /etc/apt/sources.list.d/kitware.list >/dev/null
sudo apt-get update
sudo apt-get install -y kitware-archive-keyring
sudo apt-get install -y cmake

# Install necessary dependencies for the project
cp $PROJECT_DIR/openevolve/initial_program.cpp $PROJECT_DIR/libcachesim/libCacheSim/cache/eviction/cpp/LLMCode.h
cd $PROJECT_DIR/libcachesim/
cd scripts && bash install_dependency.sh

# Compile the project
cd $PROJECT_DIR
rm -rf build && mkdir -p build && cd build
cmake .. && make -j$(nproc)
