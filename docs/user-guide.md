# Using the cluster: a guide for customers

**Draft, 2026-10-21.** Items marked ⚠️ are still to be decided before the first customer: the login address, the prices and the support contact.

## 1. Logging in
- You log in with **SSH and a key**, never a password. Send us your **public** key (the one ending in `.pub`). If you don't have one, run `ssh-keygen -t ed25519` on your computer.
- We send you a **username**: two letters and two digits, like `kx47`.
- Log in: `ssh kx47@<login address>` ⚠️ *(address to be announced)*.
- You can't add keys yourself. To change your key, send us the new public key.
- **Copying files in and out:** `scp`, `rsync` and `sftp` work with the same key, for example `rsync -av data/ kx47@<login address>:/cluster/projects/<company>/data/`.
- **The login node is for installing, editing and submitting jobs.** Each user gets up to 4 cores and 6 GB of memory there, and a program over that is stopped. Training, data processing and big builds go in a job.

## 2. Your files
| Path | What | Who can see it |
|---|---|---|
| `/cluster/home/<you>` | Your home folder | Only you |
| `/cluster/projects/<company>` | Shared by everyone at your company | Your company's users |
| `/cluster/software` | Shared software we provide (section 6) | Everyone, read-only, free |
| `/tmp` inside a job | Your job's own fast local disk (below) | Only that job |

- The same paths work on the login node and inside jobs.
- **Your company has one storage limit** (150 GiB unless agreed otherwise), shared by all its users' home folders and its project folder. `df -h ~` shows the limit, and `mystorage` shows your use. Writing past the limit fails with "Disk quota exceeded".
- **Storage is billed on the month's peak**: the most your company stored at any hour that month, times the price per GiB.
- **Each job's `/tmp` is fast local disk on the GPU node**, private to the job and deleted when it ends. Use it for datasets you copy in at the start, temporary files and caches. Copy anything you want to keep back to your home or project folder before the job ends. If you need a lot of it, ask with `#SBATCH --tmp=500G`.
- We don't back up your files: keep copies of anything important elsewhere.

## 3. Jobs and GPUs
The cluster runs **Slurm**. You submit jobs; Slurm runs them when GPUs are free.

**Each GPU comes with 5 CPU cores (Slurm counts 10, since each core runs 2 threads) and 20 GB of memory.** That's what you get by default. You can ask for less, but not more. If you need more memory, ask for more GPUs.

A typical job script, `train.sh`:
```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --gpus=1                 # GPUs: 1 to your limit
#SBATCH --time=12:00:00          # how long it may run (up to 7 days; 1 hour if you don't say)
#SBATCH --signal=B:USR1@600      # warn this script 10 minutes before the job is stopped (section 5)
#SBATCH --output=%x-%j.out

module load pytorch
python train.py
```

Submit it with `sbatch train.sh`. Other useful commands:
- `squeue --me`: your jobs.
- `scancel <jobid>`: cancel a job.
- `sinfo`: the nodes and GPUs, and which are busy.
- `srun --gpus=1 --pty bash`: an interactive session on a GPU node.
- `sbatch --array=1-10 train.sh`: ten copies of a job, each with its own `$SLURM_ARRAY_TASK_ID`.
- `sacct -j <jobid>`: a finished job's state and time.

**What's refused straight away, with a message saying why:**
- jobs that don't ask for a GPU
- more than 10 CPUs or 20 GB per GPU
- `--mem=0` and `--exclusive`
- a time limit over 7 days
- job scripts with Windows line endings: convert them with `dos2unix`, or save them with Unix line endings

A waiting job's size can't be changed: cancel it and submit again. Your time limit can be changed (`scontrol update job=<id> TimeLimit=...`).

**Your limits:** how many GPUs you can use at once, and how many your company can use together, are set in your account. A job asking for more than your limit waits and won't start (`squeue --me` shows the reason).

**A job that uses more than its memory is stopped**, and `sacct` shows `OUT_OF_MEMORY`. Ask for more GPUs to get more memory.

## 4. Internet: on the login node, not in jobs
- **Jobs can't reach the internet.** Download datasets, code and packages **on the login node** first, into your home or project folder; your jobs use them from there. `pip install` inside a job fails with a network error.
- On the login node you can reach the internet, but not our office network or the cluster's own services.

## 5. When a job is stopped early: save your work
A job stops when its time limit ends, or **10 minutes after your company runs out of credit**. Either way:
1. If you asked for a warning (`#SBATCH --signal=B:USR1@600`), your script gets the `USR1` signal **10 minutes before** the end.
2. At the end it gets `SIGTERM` ("stop now"), and 60 seconds later it's killed.

Catch the warning and save a checkpoint:
```bash
#!/bin/bash
#SBATCH --gpus=1
#SBATCH --time=24:00:00
#SBATCH --signal=B:USR1@600

save_and_stop() {
  echo "warning received: saving a checkpoint"
  kill -USR1 "$PID"        # tell the program to save (it must handle USR1), or call your own save script
  wait "$PID"
}
trap save_and_stop USR1

module load pytorch
python train.py --checkpoint-dir ~/checkpoints &
PID=$!
wait "$PID"
```
In Python, handle the signal with `signal.signal(signal.SIGUSR1, handler)` and save in the handler.

## 6. Software
**Shared software, ready to use and free** (it doesn't count against your storage):
- `module avail` lists it.
- `module load pytorch`: PyTorch 2.14.1 for CUDA 13.0, with torchvision, on Python 3.12.
- `module load miniforge`: `conda` and `mamba`. Your environments and conda's downloads go in `~/.conda` and count against your storage.
- `/cluster/software/containers/`: container images, for example NVIDIA's PyTorch image (`ls` to see them).
- `cat /cluster/software/README.md` for what's there now.

**Your own packages on top of the shared PyTorch** (only your extras use your storage):
```bash
module load pytorch
python -m venv --system-site-packages ~/envs/mine
source ~/envs/mine/bin/activate
pip install transformers datasets      # your versions win over ours
```
In a job script: `source ~/envs/mine/bin/activate`, then `python train.py`.

**Your own environment from scratch:** `module load miniforge`, then `conda create -p ~/envs/x python=3.11 ...`, or `pip` and `venv` with any Python. An environment in `/cluster/projects/<company>` is shared by your whole company and counts once.

**Models and datasets from Hugging Face (and similar):** they keep big downloads in `~/.cache`.
- To keep one copy for your whole company, put `export HF_HOME=/cluster/projects/<company>/hf-cache` in your `~/.bashrc`.
- Download on the login node, for example `huggingface-cli download <model>`.
- In job scripts, add `export HF_HUB_OFFLINE=1`, so the libraries use what's there instead of trying the internet.

**Containers (Apptainer)**, for any Docker or NVIDIA image, without root:
```bash
apptainer pull ~/myimage.sif docker://pytorch/pytorch:latest          # on the login node
srun --gpus=1 apptainer exec --nv ~/myimage.sif python train.py        # in a job: --nv gives it the GPUs
```
Containers see all of `/cluster` (your home, project folder and the shared software).

**GPUs and CUDA:** the GPUs are **NVIDIA GeForce RTX 5070 Ti** (Blackwell, 16 GB each). Code must be built with **CUDA 12.8 or newer**, or include PTX; older builds fail on these GPUs. The shared PyTorch already is.

**Compiling:** compilers (`gcc`, `g++`, `gfortran`, `make`, `cmake`) and common libraries are on the login node and in jobs. A program built on the login node runs in a job. Big builds go in a job (4 cores and 6 GB on the login node).

**Jupyter or VS Code:**
- **VS Code (Remote-SSH):** connect to the login node, for editing and light work.
- **Jupyter on a GPU:**
  1. Start it in a job, for example `sbatch --gpus=1 --time=4:00:00 --wrap "source ~/envs/mine/bin/activate; jupyter lab --no-browser --port=8888"` (`pip install jupyterlab` in your environment first).
  2. When the job runs, `squeue --me` shows its node, for example `douglas1`.
  3. From your computer, `ssh -J kx47@<login address> -L 8888:localhost:8888 kx47@douglas1`, then open the address Jupyter printed in the job's output.

  You can log in to a GPU node only while you have a job there, and your login runs inside that job.

## 7. Credits and costs
You pay with **prepaid credits** (1 credit = 1 US dollar). Every job and your storage draw them down.
- **Compute:** charged per second for what the job holds: GPUs, CPUs and memory, billed by whichever is the largest share of a node. With the standard 5 cores and 20 GB per GPU, that's simply the GPU price per hour. You pay for what you reserved, even if the job left it idle.
- **Storage:** the month's peak × the price per GiB-month.
- **Credit expires 12 months after purchase.** The oldest credit is used first.
- **Out of credit:** new jobs wait, and running jobs get 10 more minutes (section 5). Files stay, and storage keeps being charged. After 30 days at a negative balance, with emails before then, files may be deleted.
- If a job fails because of **our** hardware, it's refunded automatically.

Commands on the login node (each shows only your own data; add `--json` for scripts):
| Command | Shows |
|---|---|
| `credits` | Your company's available credit, and each purchase with its expiry date. Managers also see the month's statement. |
| `myusage` | Your jobs this month and what each cost (managers: everyone in your company). `--month 2026-10` for another month. |
| `prices` | Your prices, and every earlier price with the date it took effect. |
| `mystorage` | Your company's storage use, limit, this month's peak and its cost. |

Prices ⚠️ *(to be announced)*.

## 8. Privacy
- Other customers can't see your jobs, files, processes, temporary files or usage, and you can't see theirs.
- We keep your job scripts for 60 days, for troubleshooting and abuse investigations, then delete them. We don't keep your jobs' environment variables.
- No regulated data (health records, personal data) on this cluster.

## 9. Help
⚠️ *(support contact to be announced)*. Please include your username, the job ID and what you expected.
