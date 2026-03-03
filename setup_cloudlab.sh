#!/bin/bash
# Copy over the necessary files to the CloudLab experiment.
# Then start the setup script on the CloudLab node.

if [ -z "$1" ]; then
    echo "Usage: $0 <remote_node>"
    exit 1
fi

REMOTE="$1"
TARBALL="/tmp/project.tar.gz"
REMOTE_DIR="~/vulcan-usecases"

# Create a tarball excluding .git/
tar --exclude='.git' --warning=no-file-changed -czf $TARBALL -C . . || true

# Copy tarball and setup script to remote node
scp $TARBALL $REMOTE:~/

# Extract and run setup on remote
ssh $REMOTE "mkdir -p $REMOTE_DIR && tar -xzf ~/project.tar.gz -C $REMOTE_DIR && bash ~/vulcan-usecases/setup_experiment.sh"

rm $TARBALL
