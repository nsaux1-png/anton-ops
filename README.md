# Cluster

Configuration, scripts and records for our Slurm cluster.

- **anton** is the head node: Slurm controller, accounting database, login point, shared storage, and gateway for the cluster network.
- **douglas1** is the first compute node (10 GPUs). More GPU and dual-socket CPU nodes will follow.

Users log into anton and submit jobs. Every job is recorded in Slurm's accounting database, and that record is what we bill from.

## Rules for this repo

1. **Change the machines only through this repo.** Adding a user, node, GPU or disk means editing the source-of-truth files and re-running the scripts, never a one-off manual fix. If something has to be done by hand in an emergency, write it in `docs/ops-log/` the same day and fold it into the scripts afterwards.
2. **Every script is safe to re-run.** Running it twice gives the same result as running it once.
3. **Every run is logged:** when, who, which commit, and the output.
4. **Decisions go in [`docs/decisions.md`](docs/decisions.md)** with the date and the reason.

## Layout

| Path | Contents |
|---|---|
| `docs/plan.md` | The full plan (draft, decisions D1–D39 being worked through) |
| `docs/architecture.md` | How the cluster is put together |
| `docs/machines.md` | Hardware and network details for each machine |
| `docs/decisions.md` | Decision log |
| `docs/todo.md` | The to-do list |
| `docs/open-questions.md` | Things we still need to find out or decide |
| `docs/ops-log/` | Dated records of work done on the machines |

The Ansible code and the `./cluster` command will be added here as they are built.
