# 2026-10-21: douglas1 joins the cluster (build plan phases 4–7 on the GPU node)

## Why
douglas1 is back (ops log [2026-10-21-douglas1-back](2026-10-21-douglas1-back.md)). The user asked to carry on with the douglas1 steps, without reboots.

## Housekeeping first
- **A password in douglas1's shell history** (typed at the prompt by mistake, line 74 of papaya's `~/.bash_history`) was deleted at the user's request, without printing it. `histappend` is on, so the console session still logged in won't write it back.
  - The same password appears twice as a username in `/var/log/secure-20261018`, from login attempts at the console on 10-14 and 10-16. That log was left as it is. The user was told to change the password.
- **douglas1's console (`tty1`) is still logged in as papaya** since 2026-10-20 16:18. The user was asked whether to log it out.

## 1. System logs kept on disk (SOP-106, new)
- Neither machine had `/var/log/journal`, so journald kept logs in memory only. That's why the 10-19 failure left nothing.
- New role `journal` (every machine, tag `journal`), with live tests `tests/live/test_logs.py` (3 tests).
- Applied: `./cluster apply --tags journal`, log `20261021-162557-apply.log`, "Done and settled". Tests 3/3.
- **Proof run:**
  1. Undid it on both machines (the SOP's undo steps). The old journal folders were kept as `/var/log/journal-before-proof-20261021`.
  2. The tests failed on both machines, 6 failures as expected.
  3. One apply from the repo (`20261021-163031-apply.log`) fixed it. Tests 3/3 again.

## 2. douglas1's kernel options recorded (SOP-107, new)
- New role `kernel_args` (every machine, tag `kernel_args`). It adds the options listed in `config/nodes.yml` (`kernel_args`) to every boot entry with `grubby`, and takes off any listed in `kernel_args_remove`. It never reboots. Live tests: `tests/live/test_kernel.py` (3 tests).
- douglas1's eight extra options recorded as they were. The first apply changed nothing (`20261021-163430-apply.log`).
- **The proof run found a bug in `./cluster apply` itself:**
  1. With `initcall_debug` taken off by hand, the tests failed as expected.
  2. But the apply said **"Nothing to change"** and didn't put it back.
  3. Cause: the preview runs Ansible in check mode, which skips `command`/`shell` tasks without counting them as changes. A change made only by such a task was invisible to the preview, and to the "settled" check after an apply.
- **Same blind spot in three older roles:**
  - the initramfs rebuild (`nvidia_driver`)
  - enabling the NVIDIA driver stream (`nvidia_driver`)
  - the quota remount (`storage`)

  They only ever ran because other changes happened in the same run.
- **Fix:** the check task in front of each of these now reports the pending change in check mode (`changed_when: ansible_check_mode and ...`).
  - New code test `tests/code/test_roles.py`: every command/shell task in every role must be read-only, run its own `--check`, use `creates`/`removes`, be explicitly real-run only, or be gated on such a check task.
  - Run on the previous versions of the roles, it flags exactly those five tasks. Code tests: 110/110.
  - The billing `setup`/`sync` tasks stay real-run only, with a comment saying why: they follow the code and config the preview does show, and the hourly run repeats the sync.
- **Proof run again, from the start:**
  1. Applied (`20261021-164011-apply.log`): put back `initcall_debug`, "Done and settled". Tests 3/3.
  2. Took it off by hand: the tests failed (2).
  3. One apply (`20261021-164052-apply.log`) put it back, "Done and settled". Tests 3/3.
- The proof runs moved `initcall_debug` to the end of the options. Order doesn't matter.

## 3. Accounts, logins and shared storage on douglas1 (SOP-130, 141, 142)
- A spare SSH connection to douglas1 was kept open (`ssh -M`, a control socket), so a mistake in the login rules could be undone through it.
- `./cluster apply --limit douglas1 --dry-run`: 13 changes, all expected:
  - the test customers' groups and users
  - root-owned customer SSH keys and the customer `sshd` rules
  - process hiding for `sshd` and `user@.service`
  - the NFS client and the `/cluster` mount
- `./cluster apply --limit douglas1` (`20261021-164438-apply.log`): "Done and settled".
  - A new SSH login (not through the spare connection) works.
  - `/cluster` is mounted from `anton:/raiddrive/cluster` over NFS 4.2.
  - `zz01` has uid 10100, gid 20000, as on anton.
- **Full live suite: 116 tests pass, 1 skipped** (the per-user GPU limit, which needs Slurm on a GPU node).
  - That includes customer logins, process hiding, the same files on every node, accounts with the same IDs everywhere, and the customer network limits.
  - Since this was douglas1's first run of these roles, straight from the repo with no improvising, it also counts as their proof run on a compute node. They were proved on anton on 2026-10-20.
