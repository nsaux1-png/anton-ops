# Where things stand

**2026-10-22.** The cluster is ready for customers to be added and to work, end to end, as proven with a test customer onboarded through the real commands. What's left before the first *real* customer is mostly your decisions (bottom). Step-by-step status: [`build-plan.md`](build-plan.md). Every procedure: [`sop/`](sop/README.md). Every script and command: [`code-index.md`](code-index.md).

## What a customer gets
- **Logins** with their own SSH key, no passwords. Files go in with scp, rsync or sftp. The login node is for installing and submitting: 4 cores and 6 GB per user.
- **Storage:** a private home folder and a company project folder, with one limit per company (150 GB default), billed on the month's peak.
- **GPU jobs** through Slurm. Each GPU comes with 5 cores and 20 GB; one job's GPUs, memory and processes are private. Interactive sessions and job arrays work.
- **Scratch:** each job's private `/tmp` on douglas1's 4 TB NVMe, deleted when the job ends.
- **Software:**
  - shared and free: `module load pytorch` (PyTorch 2.14.1 for CUDA 13.0), `module load miniforge` (conda), and NVIDIA's PyTorch container image
  - their own packages on top of ours
  - Apptainer for any container image
  - compilers and Python 3.12
- **Jupyter** through a second SSH hop into their own job.
- **Credits:** prepaid, used oldest first, expire after 12 months. When credit runs out, a running job gets 10 minutes and a warning signal. Customers can see their own credit, usage, prices and storage.
- **No internet in jobs.** The login node has internet, but not the office network or the admin side.
- **The guide:** `/cluster/docs/guide.md` on the login node (from [`user-guide.md`](user-guide.md)).

## Adding a customer (SOP-210)
```bash
./cluster customer add --name "Acme Robotics" --billing-email ap@acme.example     # picks the code, commits, applies
./cluster user add c4821 --name "Alice Chen" --email alice@acme.example --key-file alice.pub --manager
./cluster credits topup c4821 500 --ref INV-1042                                  # once they've paid
```
Then send them their username, the login address and the guide.

## Checking on it
- `./cluster health`: one screen, exit code 1 if anything's wrong.
- `./cluster test`: the whole suite, code tests plus live tests on the machines. It also runs every Sunday at 03:00.

## Before the first real customer: your decisions
See the top of [`todo.md`](todo.md):
1. How customers reach the login node from outside: a public address or port forward. Then the login address goes in the guide.
2. Your own SSH login to anton, key or password (1.6). Password logins go off before anton is reachable from the internet.
3. Prices (D29) and what a credit is worth (D40), the terms, and a support contact.
4. Where alerts go (D34), and where off-site backups go (D39).
5. The one-hour full-load test of all 10 GPUs (D47), with someone near the machine.
6. A separate login machine (Q8).
7. douglas1's BMC (Linear COP-44, Albert). Until then, a reboot that goes wrong needs someone at the machine.
