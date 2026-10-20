"""Ansible filters over the customer configuration, using clusterlib.config (tested in tests/code).

  cluster_accounts(customers, uids)  customers and users with defaults applied and IDs attached;
                                     test users' public keys are read from their key files
  cluster_quota_spec(accounts)       input for the cluster-quota script (SOP-141)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))

from clusterlib import config as cfg   # noqa: E402


def cluster_accounts(customers, uids):
    accounts = cfg.accounts(cfg.check(customers), uids)
    for user in accounts["users"]:
        if user["ssh_key_file"]:
            with open(user["ssh_key_file"]) as f:
                user["ssh_key"] = f.read().strip()
    return accounts


def cluster_quota_spec(accounts):
    return cfg.quota_spec(accounts)


class FilterModule:
    def filters(self):
        return {"cluster_accounts": cluster_accounts, "cluster_quota_spec": cluster_quota_spec}
