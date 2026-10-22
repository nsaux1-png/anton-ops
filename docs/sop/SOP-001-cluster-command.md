# SOP-001: Running `./cluster` commands
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-ansible.md))

## Purpose
`./cluster` is the one command for admin work on the cluster. It runs Ansible now, and later our own tools (credits, users, maintenance), and it logs every run.

## When
For any admin change to the machines. Don't change a machine by hand when a `./cluster` command covers it. If you have to (an emergency), write an ops-log entry, then bring the repo in line.

## Before you start
- You're logged into anton with your own admin account, not as root. `id` must show the group `wheel`.
- You're in the repo: `cd ~/cluster`.
- Ansible is installed (SOP-101).
- For `apply`, your changes are committed. `apply` refuses to run with uncommitted changes, so every run matches a commit.

## Commands
| Command | What it does |
|---|---|
| `./cluster ping` | Checks that Ansible reaches every machine in `config/nodes.yml` and can become root there. Changes nothing. |
| `./cluster apply` | Brings every machine in line with the repo. It first runs the code tests and stops if one fails. Then, in four parts: **1. Preview** shows exactly what would change, without changing anything. **2. Ask:** "Make the N change(s) shown above? [y/N]". **3. Apply.** **4. Check:** a second preview must find nothing left to change, which prints "Done and settled." |
| `./cluster apply --dry-run` | Only the preview. |
| `./cluster apply --yes` | Doesn't ask, for cron and agents. Without a terminal and without `--yes`, `apply` refuses. |
| `./cluster apply --limit douglas1` | Only some machines. `--tags` runs only some parts. |
| `./cluster apply --allow-dirty` | Runs with uncommitted changes. Only for discovery runs; the full diff goes in the run log. |
| `./cluster test` | Runs every test: the code tests (`tests/code`, our own code) and the live tests (`tests/live`, real checks on the cluster's machines). `--code` or `--live` runs only one kind; `-k NAME` runs only matching tests. |
| `./cluster runs` | Lists recent runs from `index.log`. |

**Exit codes:** 0 done, 1 failed, 2 refused (bad input, uncommitted changes, or not confirmed). A refused run changes nothing.

## Run logs
- One file per run in `/var/log/cluster-ops/`, e.g. `20261019-221202-apply.log`. It records:
  - who ran it, when, and on which machine
  - which commit, or `+uncommitted` together with the diff
  - the full output
  - the exit code and duration
- One line per run in `/var/log/cluster-ops/index.log`, tab-separated: time, operator, exit code, commit, command, log file.
- The folder is `root:wheel`, mode `2770`, and the logs are `0640`. Admins can read them; customers can't.

## Expected result
- `ping`: one `SUCCESS` per machine, then `exit=0`.
- `apply`: ends with "Done and settled." or "Nothing to change.", then `exit=0`.

## Checks
- `./cluster test --code`: the command's own tests, all `ok`.
- `./cluster runs` shows the run you just did.

## If something goes wrong
- **`Can't write the run log`:** run SOP-101 again, and check that `id` shows `wheel`.
- **`UNREACHABLE` in `ping`:** the machine is down, or SSH from anton fails. Try `ssh <machine>`.
- **`Not settled`:** a role reports changes on every run. That's a bug in the role; fix it before relying on it.
- **A mount Ansible made is missing for a service:** on a machine reached over SSH, Ansible runs inside sshd's own mount namespace (ProtectProc). Mounts must go through systemd mount units, and `tests/code/test_roles.py` checks this. See them as the host does with `sudo nsenter -t 1 -m findmnt`.
- **"Nothing to change", but something is wrong:** the preview skips `command` and `shell` tasks. A role must make each one visible in the preview (`tests/code/test_roles.py` checks every role). If a new role fails that test, fix the role.
- **Preview fails, but the real run would work:** Ansible's preview can't always predict a task that depends on an earlier change in the same run, such as configuring a package that isn't installed yet. The role must handle this, so fix the role.

## Undo
Nothing to undo for `ping`. For a change made by `apply`, see the SOP for that part.

## History
- 2026-10-19: first version with `ping`, `apply` and `runs`. Commit 5634478.
- 2026-10-21: the preview couldn't see changes made only by `command`/`shell` tasks. Fixed in the four roles affected; `tests/code/test_roles.py` keeps it that way ([ops log](../ops-log/2026-10-21-douglas1-setup.md)).
