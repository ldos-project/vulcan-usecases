# Setup instructions
0. Copy over your SSH key to all nodes (cloning the libvulcan repo might need it).
1. Create a Cloudlab job inside the `ldos-UT` project using the `ARMS` profile created by Sujay.
2. (from local machine) use `./cloudlab/setup_experiment.sh <cloudlab-username> <cloudlab-jobname> <start-node> <end-node>` to setup the machines.
3. Confirm that the nodes were setup properly:
    - expected Linux version (`uname -r`) is `5.1.0-rc4+`. 
    - `/mnt/data/` must be populated with `./workloads` and `./inputs/twitter.sg`.