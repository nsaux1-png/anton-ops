# SOP-191: The weekly test run
**Status:** timer installed 2026-10-20; first run Sunday 2026-10-25 03:00.

## Purpose
Every Sunday at 03:00, `cluster-tests-weekly.timer` runs `./cluster test`, which is every code test and every live test, as the admin account in `config/nodes.yml` (`test_runner`, from `test_repo`). The run is logged like any `./cluster` run (`/var/log/cluster-ops/*-test.log`, and `./cluster runs`). Failures show in `./cluster health` until the next good run. Email comes with alerts (plan D34).

The tests themselves are written in each build step, not here: `tests/code` (our own code) and `tests/live` (the real cluster). See `build-plan.md`.

## When
- by itself, weekly
- by hand after any change: `./cluster test`, or `./cluster test --live -k <area>` for one area

## Note
The timer runs as an admin account with sudo. When the temporary passwordless sudo is removed (build plan 11.3), the test runner needs its own limited sudo rules, written then.

## History
- 2026-10-20: timer installed (role `test_schedule`).
