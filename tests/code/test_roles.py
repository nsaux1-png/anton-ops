"""Every command or shell task in the Ansible roles can be seen by ./cluster apply's preview.

The preview (and the "settled" check after an apply) runs Ansible in check mode, which skips command and
shell tasks. A change made only by such a task is invisible there: the preview says "Nothing to change"
and the apply never runs (found by SOP-107's proof run, 2026-10-21). So each one must be one of:
- read-only (changed_when: false)
- run in the preview itself (check_mode: false), the tool doing its own --check
- guarded by creates/removes, which check mode reports
- explicitly real-run only (when: not ansible_check_mode), with the reason in a comment
- gated on a check task that reports the pending change in check mode (changed_when: ansible_check_mode and ...)
"""

import glob
import os
import re
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
COMMANDS = {"ansible.builtin.command", "ansible.builtin.shell", "command", "shell"}


class RoleLoader(yaml.SafeLoader):
    """YAML as Ansible reads it: !unsafe marks a string that isn't templated."""


RoleLoader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))


def flatten(tasks):
    for t in tasks or []:
        yield t
        for part in ("block", "rescue", "always"):
            yield from flatten(t.get(part))


def text(value):
    return " ".join(map(str, value)) if isinstance(value, list) else str(value or "")


def blind_tasks(tasks):
    """Names of command/shell tasks whose changes a check-mode preview can't see."""
    tasks = list(flatten(tasks))
    registered = {t["register"]: t for t in tasks if "register" in t}
    blind = []
    for t in tasks:
        module = next((k for k in t if k in COMMANDS), None)
        if module is None:
            continue
        args = dict(t.get("args") or {})
        if isinstance(t[module], dict):
            args.update(t[module])
        when = text(t.get("when"))
        gates = [registered[name] for name in registered if re.search(rf"\b{re.escape(name)}\b", when)]
        if (t.get("changed_when") in (False, "false")
                or t.get("check_mode") is False
                or "creates" in args or "removes" in args
                or re.search(r"\bnot ansible_check_mode\b", when)
                or any("ansible_check_mode" in text(g.get("changed_when")) for g in gates)):
            continue
        blind.append(t.get("name", "(unnamed)"))
    return blind


class PreviewSeesEveryCommand(unittest.TestCase):
    def test_every_role(self):
        files = sorted(glob.glob(os.path.join(REPO, "ansible", "roles", "*", "tasks", "*.yml")))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=os.path.relpath(path, REPO)):
                with open(path) as f:
                    self.assertEqual(blind_tasks(yaml.load(f, Loader=RoleLoader)), [])

    def test_the_check_catches_a_blind_task(self):
        tasks = [
            {"name": "check", "ansible.builtin.command": "probe", "register": "probe",
             "changed_when": False, "check_mode": False},
            {"name": "fix", "ansible.builtin.command": "fix", "when": "probe.stdout == '0'"},
            {"name": "always", "ansible.builtin.shell": "echo hi"},
        ]
        self.assertEqual(blind_tasks(tasks), ["fix", "always"])

    def test_the_allowed_shapes_pass(self):
        tasks = [
            {"name": "read-only", "ansible.builtin.command": "probe", "changed_when": False},
            {"name": "own check", "ansible.builtin.command": "tool --check", "check_mode": False,
             "register": "tool", "changed_when": "tool.stdout | length > 0"},
            {"name": "made once", "ansible.builtin.shell": "make-key", "args": {"creates": "/etc/key"}},
            {"name": "real run only", "ansible.builtin.command": "sync", "when": "not ansible_check_mode"},
            {"name": "check", "ansible.builtin.command": "probe", "register": "probe", "check_mode": False,
             "changed_when": "ansible_check_mode and probe.stdout == '0'"},
            {"name": "gated fix", "ansible.builtin.command": "fix", "when": "probe.stdout == '0'"},
            {"name": "in a block", "block": [
                {"name": "inner", "ansible.builtin.command": "probe", "changed_when": False}]},
        ]
        self.assertEqual(blind_tasks(tasks), [])


if __name__ == "__main__":
    unittest.main()
