"""Shared helpers for the live tests, which run real commands on the cluster's machines.

Commands run as the admin running ./cluster test: locally on a machine with ansible_connection
local (the head node), over SSH on the others. as_customer() wraps a command so it runs under a
made-up customer UID, so no account is needed.
"""

import functools
import ipaddress
import json
import os
import shlex
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
INVENTORY = os.path.join(REPO, "config", "nodes.yml")
PRETEND_CUSTOMER_UID = 10001   # in the customer range (plan section 6) and never assigned: uids.yml starts higher


@functools.lru_cache(maxsize=None)
def _inventory():
    out = subprocess.run(["ansible-inventory", "-i", INVENTORY, "--list"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def hosts(group="all"):
    """Machines in a group of config/nodes.yml, including its child groups."""
    inv = _inventory()
    if group == "all":
        return sorted(inv["_meta"]["hostvars"])
    found = set(inv.get(group, {}).get("hosts", []))
    for child in inv.get(group, {}).get("children", []):
        found |= set(hosts(child))
    return sorted(found)


def var(host, name):
    return _inventory()["_meta"]["hostvars"][host][name]


def head():
    return hosts("head")[0]


def run(host, command, timeout=120, input=None):
    """Run a bash command on host, with optional text on its stdin. Returns the CompletedProcess."""
    if _inventory()["_meta"]["hostvars"][host].get("ansible_connection") == "local":
        argv = ["bash", "-c", command]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=input)


def as_customer(command, uid=PRETEND_CUSTOMER_UID):
    """The command, run under a customer UID through sudo + setpriv."""
    return f"sudo setpriv --reuid={uid} --regid={uid} --clear-groups bash -c {shlex.quote(command)}"


def can_connect(host, address, port, customer=False, seconds=5):
    """Whether a TCP connection from host to address:port succeeds, as admin or as a pretend customer."""
    probe = f"timeout {seconds} bash -c 'echo > /dev/tcp/{address}/{port}'"
    return run(host, as_customer(probe) if customer else probe).returncode == 0


def first_host_address(network):
    return str(next(ipaddress.ip_network(network, strict=False).hosts()))


def wait_until(check, seconds=90, every=3):
    """Call check() until it returns a true value or time runs out. Returns the last result."""
    deadline = time.time() + seconds
    while True:
        result = check()
        if result or time.time() > deadline:
            return result
        time.sleep(every)
