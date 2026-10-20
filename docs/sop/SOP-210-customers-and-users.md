# SOP-210: Adding and changing customers and users
**Status:** the commands are tested in a sandbox (code tests). First real use: when the first customer is added.

## Purpose
The day-to-day way to change who can use the cluster. Each command:
1. shows the change to `config/customers.yml` and asks
2. commits it (the commit is pushed to GitHub)
3. applies it to every machine, with the usual preview and question

`--dry-run` only shows the change. `--yes` doesn't ask, for cron and agents. Every run is logged (SOP-001).

## Commands
| Task | Command |
|---|---|
| Add a customer | `./cluster customer add --name "Acme Robotics" --billing-email ap@acme.example [--storage-gb 500] [--max-gpus 8]`. It picks the code (`c` + four digits). |
| Change a customer | `./cluster customer set c4821 storage_gb 1000`. Fields: name, billing_email, storage_gb, max_gpus, discount_percent. |
| Add a user | `./cluster user add c4821 --name "Alice Chen" --email alice@acme.example --key "ssh-ed25519 AAAA…"` (or `--key-file`), plus `--manager` or `--max-gpus 6` if needed. **It picks the username** and prints it; send it to the person. |
| Change a user | `./cluster user set kx47 max_gpus 6`. Fields: name, email, ssh_key, role, max_gpus. |
| Suspend / resume | `./cluster user suspend kx47`, `./cluster user resume kx47`. A suspended user can't log in or run jobs, and their files are kept. |
| Remove | `./cluster user remove kx47`. Login and jobs are blocked for good; files are kept until the retention period ends (plan D18); the username and UID are never reused. |
| See | `./cluster user list [c4821] [--json]`, `./cluster customer list [--json]`. Not logged: they only read the file. |

## Before you start
- The repo has no uncommitted changes (`git -C ~/cluster status`).
- For a new user: their **SSH public key** (it starts with `ssh-ed25519` or `ssh-rsa`), their name and email.

## Expected result
"Done and settled", and the user can log in with their key: `ssh <username>@<login address>`.

## Checks
- `./cluster user list` shows the user with a UID.
- `./cluster test --live -k test_customers`.

## If something goes wrong
- **"customers.yml has problems":** the message lists each one. Fix them and commit; nothing was changed.
- **"isn't laid out the way ./cluster edits it":** someone hand-edited the file in another style. Make this change by hand, then `./cluster apply`.
- **The change committed but the apply failed or was declined:** the file is right; run `./cluster apply` again.

## History
- 2026-10-20: commands written; 10 end-to-end code tests (`tests/code/test_cluster_users.py`) in a sandbox copy of the repo.
