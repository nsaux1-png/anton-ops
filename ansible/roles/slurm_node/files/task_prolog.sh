#!/bin/bash
# Managed by Ansible (ansible/roles/slurm_node), SOP-155. Slurm runs this as the job's user before each task;
# its "export" lines set the task's environment. Temporary files go to the job's own /tmp, even when the
# login node set TMPDIR to the customer's home folder (SOP-143).
echo "export TMPDIR=/tmp"
