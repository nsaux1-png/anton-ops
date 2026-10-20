"""A throwaway copy of the repo for testing the ./cluster command itself.

It has its own git history, a sample customers.yml (no real people) and stand-ins for ansible and
ansible-playbook. Commands run in it really edit, commit and "apply" without touching the real repo,
the real run log or any machine.
"""

import os
import shutil
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOlIa7dt5DISYUNqy1KetIR7aipepSVvgF5WjS1QB/5c test@laptop"

# Stand-in for ansible-playbook: a check run reports 1 change until a real run has happened.
FAKE_PLAYBOOK = """#!/bin/bash
echo "ansible-playbook $*" >> "$FAKE_CALLS"
if [[ " $* " == *" --check "* ]]; then
  if [[ -f "$FAKE_STATE" ]]; then c=0; else c=1; fi
else
  touch "$FAKE_STATE"; c=1
fi
echo "PLAY RECAP *********************************************************"
echo "anton                      : ok=2    changed=$c    unreachable=0    failed=0    skipped=0"
"""

FAKE_ANSIBLE = """#!/bin/bash
echo "ansible $*" >> "$FAKE_CALLS"
echo "anton | SUCCESS"
exit "${FAKE_EXIT:-0}"
"""


class Sandbox:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self._tmp.name
        self.root = os.path.join(base, "repo")
        os.makedirs(os.path.join(self.root, "config"))
        os.makedirs(os.path.join(self.root, "ansible"))
        for name in ("cluster", ".gitignore"):
            shutil.copy(os.path.join(REPO, name), self.root)
        shutil.copytree(os.path.join(REPO, "clusterlib"), os.path.join(self.root, "clusterlib"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.test_key_file = os.path.join(base, "zz01.pub")
        with open(self.test_key_file, "w") as f:
            f.write(KEY + "\n")
        self.write("config/customers.yml", f"""defaults:
  storage_gb: 150
  max_gpus: 4

customers:
  c0001:
    name: Test customer
    test: true
    users:
      zz01:
        name: Test user
        email: t@localhost
        ssh_key_file: {self.test_key_file}
  c4821:
    name: Acme
    users:
      kx47:
        name: Alice
        email: alice@acme.example
        ssh_key: {KEY}
""")
        shutil.copy(os.path.join(REPO, "config", "rates.yml"), os.path.join(self.root, "config", "rates.yml"))
        for name in ("ansible/site.yml", "ansible/upgrade.yml", "config/nodes.yml"):
            self.write(name, "")
        bin_dir = os.path.join(base, "bin")
        os.mkdir(bin_dir)
        for name, body in (("ansible-playbook", FAKE_PLAYBOOK), ("ansible", FAKE_ANSIBLE)):
            with open(os.path.join(bin_dir, name), "w") as f:
                f.write(body)
            os.chmod(os.path.join(bin_dir, name), 0o755)
        self.logs = os.path.join(base, "logs")
        os.mkdir(self.logs)
        self.calls = os.path.join(base, "calls")
        self.state = os.path.join(base, "applied")
        self.env = dict(os.environ, CLUSTER_LOG_DIR=self.logs, CLUSTER_SKIP_CODE_TESTS="1",
                        PYTHONDONTWRITEBYTECODE="1", FAKE_CALLS=self.calls, FAKE_STATE=self.state,
                        PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@test",
                        GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@test")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    def cleanup(self):
        self._tmp.cleanup()

    def write(self, relative, text):
        with open(os.path.join(self.root, relative), "w") as f:
            f.write(text)

    def read(self, relative):
        with open(os.path.join(self.root, relative)) as f:
            return f.read()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.root, *args], env=getattr(self, "env", None),
                              capture_output=True, text=True, check=True).stdout

    def commits(self):
        return self.git("log", "--format=%s").splitlines()

    def cluster(self, *args, **env):
        return subprocess.run(["/usr/bin/python3", os.path.join(self.root, "cluster"), *args],
                              env=dict(self.env, **env), stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def calls_made(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls) as f:
            return f.read().splitlines()
