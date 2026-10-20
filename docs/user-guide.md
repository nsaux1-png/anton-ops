# Using the cluster: a guide for customers

**Draft, 2026-10-20.** Items marked ⚠️ are still to be decided before the first customer: the login address and the prices.

## 1. Logging in
- You log in with **SSH and a key**, never a password. Send us your **public** key (the one ending in `.pub`). If you don't have one, run `ssh-keygen -t ed25519` on your computer.
- We send you a **username**: two letters and two digits, like `kx47`.
- Log in: `ssh kx47@<login address>` ⚠️ *(address to be announced)*.
- You can't add keys yourself. To change your key, send us the new public key.

## 2. Your files
| Path | What | Who can see it |
|---|---|---|
| `/cluster/home/<you>` | Your home folder | Only you |
| `/cluster/projects/<customer>` | Shared by everyone at your company | Your company's users |
| `/cluster/software` | Shared software we provide | Everyone |

- The same paths work on the login node and inside jobs.
- **Your company has one storage limit** (150 GiB unless agreed otherwise), shared by all its users' home folders and its project folder. `df -h ~` shows the limit, and `mystorage` shows your use. Writing past the limit fails with "Disk quota exceeded".
- **Storage is billed on the month's peak**: the most your company stored at any hour that month, times the price per GiB.
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

python train.py
```
Submit it with `sbatch train.sh`. Other useful commands:
- `squeue --me`: your jobs.
- `scancel <jobid>`: cancel a job.
- `sinfo`: the nodes and GPUs, and which are busy.
- `srun --gpus=1 --pty bash`: an interactive session on a GPU node.

**What's refused straight away, with a message saying why:**
- jobs that don't ask for a GPU
- more than 10 CPUs or 20 GB per GPU
- `--mem=0` and `--exclusive`

A waiting job's size can't be changed: cancel it and submit again. Your time limit can be changed (`scontrol update job=<id> TimeLimit=...`).

**Your limits:** how many GPUs you can use at once, and how many your company can use together, are set in your account. A job asking for more than your limit waits and won't start.

## 4. No internet inside jobs
Jobs **can't reach the internet**. Download datasets, code and packages **on the login node** first, into your home or project folder. Your jobs then use them from there. For example, `pip install --user ...` or `conda create ...` on the login node, then `conda activate ...` in your job script.

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

python train.py --checkpoint-dir ~/checkpoints &
PID=$!
wait "$PID"
```
In Python, handle the signal with `signal.signal(signal.SIGUSR1, handler)` and save in the handler.

## 6. Software and GPUs
- The GPUs are **NVIDIA GeForce RTX 5070 Ti** (Blackwell, 16 GB each). Code must be built with **CUDA 12.8 or newer**, or include PTX; older builds fail on these GPUs. Recent PyTorch builds for CUDA 12.8 or later work.
- Install your own Python packages with `pip --user` or conda, in your home or project folder.
- Containers (Apptainer) come later.

## 7. Credits and costs
You pay with **prepaid credits** (1 credit = 1 US dollar). Every job and your storage draw them down.
- **Compute:** charged per minute for what the job holds: GPUs, CPUs and memory, billed by whichever is the largest share of a node. With the standard 5 cores and 20 GB per GPU, that's simply the GPU price per hour. You pay for what you reserved, even if the job left it idle.
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
- Other customers can't see your jobs, files, processes or usage, and you can't see theirs.
- We keep your job scripts for 60 days, for troubleshooting and abuse investigations, then delete them. We don't keep your jobs' environment variables.
- No regulated data (health records, personal data) on this cluster.

## 9. Help
⚠️ *(support contact to be announced)*. Please include your username, the job ID and what you expected.
