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
