"""The cluster's customer configuration (slurm-design.md section 2).

config/customers.yml is edited by admins. config/uids.yml is generated: every UID and GID is given
out once and never reused. This module loads and checks them, applies the defaults, picks new
usernames and customer codes, gives out IDs, and makes the small text edits ./cluster does to
customers.yml, so admins' comments and layout survive.
"""

import json
import os
import random
import re

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CUSTOMERS_FILE = os.path.join(REPO, "config", "customers.yml")
UIDS_FILE = os.path.join(REPO, "config", "uids.yml")

USER_UID_START = 10100     # customers' users; 10000-10099 stay free for the tests' made-up UIDs
GROUP_GID_START = 20000    # one group per customer; it carries the customer's storage limit

USERNAME_LETTERS = "abcdefghjkmnpqrstuvwxyz"   # no i, l or o: they look like 1, 1 and 0
TEST_USER_PREFIX = "zz"                        # zz01, zz02, ...: test accounts only
REAL_USERNAME_RE = re.compile(rf"^[{USERNAME_LETTERS}]{{2}}[0-9]{{2}}$")
TEST_USERNAME_RE = re.compile(r"^zz[0-9]{2}$")
CUSTOMER_RE = re.compile(r"^c[0-9]{4}$")
TEST_CUSTOMER_MAX = 99                         # c0001-c0099 are test customers
KEY_RE = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com"
                    r"|sk-ecdsa-sha2-nistp256@openssh\.com) [A-Za-z0-9+/]+=*( \S.*)?$")
STATUSES = ("active", "suspended", "removed")
ROLES = ("user", "manager")

CUSTOMER_FIELDS = {"name", "billing_email", "test", "storage_gb", "max_gpus", "rates", "discount_percent", "users"}
USER_FIELDS = {"name", "email", "ssh_key", "ssh_key_file", "status", "role", "max_gpus"}
DEFAULT_FIELDS = {"storage_gb", "max_gpus"}


class ConfigError(Exception):
    """customers.yml or uids.yml is wrong, or can't be edited automatically."""


# --- loading and checking ----------------------------------------------------------------------

def load(path=CUSTOMERS_FILE):
    with open(path) as f:
        return parse(f.read())


def parse(text):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"customers.yml isn't valid YAML: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError("customers.yml must have 'defaults:' and 'customers:' at the top")
    return data


def _is_int(value, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def problems(config):
    """Everything wrong with a parsed customers.yml, as a list of sentences. Empty means fine."""
    found = []
    extra = set(config) - {"defaults", "customers"}
    if extra:
        found.append(f"unknown top-level keys: {', '.join(sorted(extra))}")
    defaults = config.get("defaults") or {}
    for key in sorted(set(defaults) - DEFAULT_FIELDS):
        found.append(f"defaults: unknown field '{key}'")
    if not _is_int(defaults.get("storage_gb"), 1):
        found.append("defaults: storage_gb must be a whole number of GB, at least 1")
    if not _is_int(defaults.get("max_gpus"), 0):
        found.append("defaults: max_gpus must be a whole number, 0 or more")

    customers = config.get("customers")
    if not isinstance(customers, dict) or not customers:
        found.append("customers: must list at least one customer")
        return found

    seen_users = {}
    for code, c in customers.items():
        where = f"customer {code}"
        if not isinstance(code, str) or not CUSTOMER_RE.match(code):
            found.append(f"{where}: code must be 'c' and four digits, like c4821")
            continue
        if not isinstance(c, dict):
            found.append(f"{where}: must be a set of fields")
            continue
        for key in sorted(set(c) - CUSTOMER_FIELDS):
            found.append(f"{where}: unknown field '{key}'")
        if not isinstance(c.get("name"), str) or not c["name"].strip():
            found.append(f"{where}: needs a name")
        is_test = c.get("test", False)
        if not isinstance(is_test, bool):
            found.append(f"{where}: test must be true or false")
        number = int(code[1:])
        if is_test and number > TEST_CUSTOMER_MAX:
            found.append(f"{where}: test customers must be c0001-c0099")
        if not is_test and number <= TEST_CUSTOMER_MAX:
            found.append(f"{where}: c0001-c0099 are for test customers (set test: true or use another code)")
        if "storage_gb" in c and not _is_int(c["storage_gb"], 1):
            found.append(f"{where}: storage_gb must be a whole number of GB, at least 1")
        if "max_gpus" in c and not _is_int(c["max_gpus"], 0):
            found.append(f"{where}: max_gpus must be a whole number, 0 or more")
        users = c.get("users") or {}
        if not isinstance(users, dict):
            found.append(f"{where}: users must be a set of users")
            continue
        for username, u in users.items():
            uwhere = f"user {username} ({code})"
            if not isinstance(username, str):
                found.append(f"{uwhere}: username must be text")
                continue
            if is_test and not TEST_USERNAME_RE.match(username):
                found.append(f"{uwhere}: test customers' users are zz01-zz99")
            if not is_test and (not REAL_USERNAME_RE.match(username) or username.startswith(TEST_USER_PREFIX)):
                found.append(f"{uwhere}: usernames are two letters (not i, l or o) and two digits; zz is for tests")
            if username in seen_users:
                found.append(f"{uwhere}: also listed under {seen_users[username]}")
            seen_users[username] = code
            if not isinstance(u, dict):
                found.append(f"{uwhere}: must be a set of fields")
                continue
            for key in sorted(set(u) - USER_FIELDS):
                found.append(f"{uwhere}: unknown field '{key}'")
            if not isinstance(u.get("name"), str) or not u["name"].strip():
                found.append(f"{uwhere}: needs a name")
            if not isinstance(u.get("email"), str) or "@" not in u["email"]:
                found.append(f"{uwhere}: needs an email address")
            if "ssh_key_file" in u and not is_test:
                found.append(f"{uwhere}: ssh_key_file is only for test users; real users need ssh_key")
            if "ssh_key" in u and "ssh_key_file" in u:
                found.append(f"{uwhere}: give ssh_key or ssh_key_file, not both")
            if "ssh_key" in u and not (isinstance(u["ssh_key"], str) and KEY_RE.match(u["ssh_key"].strip())):
                found.append(f"{uwhere}: ssh_key doesn't look like an SSH public key")
            if "ssh_key" not in u and "ssh_key_file" not in u:
                found.append(f"{uwhere}: needs an ssh_key")
            if u.get("status", "active") not in STATUSES:
                found.append(f"{uwhere}: status must be one of {', '.join(STATUSES)}")
            if u.get("role", "user") not in ROLES:
                found.append(f"{uwhere}: role must be one of {', '.join(ROLES)}")
            if "max_gpus" in u and not _is_int(u["max_gpus"], 0):
                found.append(f"{uwhere}: max_gpus must be a whole number, 0 or more")
    return found


def check(config):
    found = problems(config)
    if found:
        raise ConfigError("customers.yml has problems:\n  - " + "\n  - ".join(found))
    return config


# --- effective settings (defaults applied) -------------------------------------------------------

def accounts(config, uids):
    """Customers and users with defaults applied and IDs attached: what every machine gets."""
    defaults = config["defaults"]
    customers, users = [], []
    for code, c in sorted(config["customers"].items()):
        if code not in uids["groups"]:
            raise ConfigError(f"customer {code} has no GID in uids.yml yet")
        customers.append({
            "code": code,
            "gid": uids["groups"][code],
            "test": c.get("test", False),
            "storage_gb": c.get("storage_gb", defaults["storage_gb"]),
            "max_gpus": c.get("max_gpus"),
        })
        for username, u in sorted((c.get("users") or {}).items()):
            if username not in uids["users"]:
                raise ConfigError(f"user {username} has no UID in uids.yml yet")
            users.append({
                "name": username,
                "customer": code,
                "uid": uids["users"][username],
                "gid": uids["groups"][code],
                "status": u.get("status", "active"),
                "role": u.get("role", "user"),
                "max_gpus": u.get("max_gpus", defaults["max_gpus"]),
                "test": c.get("test", False),
                "ssh_key": u.get("ssh_key"),
                "ssh_key_file": u.get("ssh_key_file"),
            })
    return {"customers": customers, "users": users}


# --- new names ------------------------------------------------------------------------------------

def new_username(taken, rng=random):
    """A random unused username: two letters (no i, l, o; never zz) and two digits."""
    for _ in range(100000):
        name = rng.choice(USERNAME_LETTERS) + rng.choice(USERNAME_LETTERS) + f"{rng.randrange(100):02d}"
        if not name.startswith(TEST_USER_PREFIX) and name not in taken:
            return name
    raise ConfigError("couldn't find a free username")


def new_customer_code(taken, rng=random):
    """A random unused customer code, c0100-c9999 (c0001-c0099 are test customers)."""
    for _ in range(100000):
        code = f"c{rng.randrange(TEST_CUSTOMER_MAX + 1, 10000):04d}"
        if code not in taken:
            return code
    raise ConfigError("couldn't find a free customer code")


def all_usernames(config, uids):
    """Every username ever used: current users and everyone who ever had a UID."""
    names = set(uids["users"])
    for c in config["customers"].values():
        names |= set((c.get("users") or {}))
    return names


# --- uids.yml ---------------------------------------------------------------------------------------

def load_uids(path=UIDS_FILE):
    if not os.path.exists(path):
        return {"users": {}, "groups": {}}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return {"users": dict(data.get("users") or {}), "groups": dict(data.get("groups") or {})}


def allocate(config, uids):
    """Give IDs to customers and users that don't have one yet. Returns (new uids, what was added).
    Existing entries never change and are never removed, so an ID is never given out twice."""
    out = {"users": dict(uids["users"]), "groups": dict(uids["groups"])}
    added = []
    next_gid = max([GROUP_GID_START - 1] + list(out["groups"].values())) + 1
    next_uid = max([USER_UID_START - 1] + list(out["users"].values())) + 1
    for code, c in sorted(config["customers"].items()):
        if code not in out["groups"]:
            out["groups"][code] = next_gid
            added.append(f"{code}={next_gid}")
            next_gid += 1
        for username in sorted(c.get("users") or {}):
            if username not in out["users"]:
                out["users"][username] = next_uid
                added.append(f"{username}={next_uid}")
                next_uid += 1
    return out, added


def format_uids(uids):
    lines = ["# Generated by ./cluster: don't edit by hand.",
             "# Every UID and GID is given out once and never reused, even after a user or customer is removed.",
             "groups:   # one per customer; GID " + str(GROUP_GID_START) + " and up"]
    lines += [f"  {code}: {gid}" for code, gid in sorted(uids["groups"].items(), key=lambda kv: kv[1])]
    lines += ["users:    # UID " + str(USER_UID_START) + " and up"]
    lines += [f"  {name}: {uid}" for name, uid in sorted(uids["users"].items(), key=lambda kv: kv[1])]
    return "\n".join(lines) + "\n"


# --- text edits to customers.yml --------------------------------------------------------------------
# customers.yml uses two spaces per level:
#   customers:
#     c4821:            (2)
#       name: ...       (4)
#       users:          (4)
#         kx47:         (6)
#           name: ...   (8)

def _yaml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))   # a JSON string is a valid YAML double-quoted string


def _block_end(lines, start, indent):
    """Index just past the block that starts at lines[start] (lines indented more than indent)."""
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
            break
        i += 1
    while i > start + 1 and not lines[i - 1].strip():   # leave trailing blank lines outside the block
        i -= 1
    return i


def _find(lines, key, indent, start=0, end=None):
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:(\s|$)")
    for i in range(start, len(lines) if end is None else end):
        if pattern.match(lines[i]):
            return i
    return None


def _layout_error():
    return ConfigError("customers.yml isn't laid out the way ./cluster edits it (two spaces per level, "
                       "as in the example at the top). Make this change by hand instead.")


def add_customer_text(text, code, fields):
    """customers.yml with a new customer block added at the end of 'customers:'."""
    lines = text.splitlines()
    top = _find(lines, "customers", 0)
    if top is None:
        raise _layout_error()
    end = _block_end(lines, top, 0)
    block = [f"  {code}:"] + [f"    {k}: {_yaml_value(v)}" for k, v in fields.items()] + ["    users: {}"]
    new = lines[:end] + ([""] if lines[end - 1].strip() else []) + block + lines[end:]
    result = "\n".join(new) + "\n"
    after = parse(result)
    if code not in (after.get("customers") or {}):
        raise _layout_error()
    return result


def add_user_text(text, customer, username, fields):
    """customers.yml with a new user added to the customer's users."""
    lines = text.splitlines()
    top = _find(lines, "customers", 0)
    c = _find(lines, customer, 2, top + 1 if top is not None else 0) if top is not None else None
    if c is None:
        raise ConfigError(f"customer {customer} isn't in customers.yml")
    c_end = _block_end(lines, c, 2)
    block = [f"      {username}:"] + [f"        {k}: {_yaml_value(v)}" for k, v in fields.items()]
    u = _find(lines, "users", 4, c + 1, c_end)
    if u is None:
        new = lines[:c_end] + ["    users:"] + block + lines[c_end:]
    elif re.match(r"^    users:\s*(#.*)?$", lines[u]):
        new = lines[:u + 1] + block + lines[u + 1:]
    elif re.match(r"^    users:\s*\{\s*\}\s*(#.*)?$", lines[u]):
        new = lines[:u] + [re.sub(r"\{\s*\}\s*", "", lines[u]).rstrip()] + block + lines[u + 1:]
    else:
        raise _layout_error()
    result = "\n".join(new) + "\n"
    after = parse(result)
    if username not in ((after.get("customers") or {}).get(customer, {}).get("users") or {}):
        raise _layout_error()
    return result


def _user_line(lines, username):
    top = _find(lines, "customers", 0)
    if top is None:
        raise _layout_error()
    found = [i for i in range(top + 1, len(lines)) if re.match(rf"^      {re.escape(username)}:\s*$", lines[i])]
    if len(found) != 1:
        raise ConfigError(f"user {username} isn't in customers.yml (or is listed twice)")
    return found[0]


def set_user_field_text(text, username, field, value):
    """customers.yml with one field of one user set (added if missing)."""
    if field not in USER_FIELDS:
        raise ConfigError(f"users have no field '{field}'")
    lines = text.splitlines()
    u = _user_line(lines, username)
    end = _block_end(lines, u, 6)
    i = _find(lines, field, 8, u + 1, end)
    line = f"        {field}: {_yaml_value(value)}"
    if i is None:
        lines.insert(end, line)
    else:
        comment = re.search(r"\s+#.*$", lines[i]) if not lines[i].rstrip().endswith('"') else None
        lines[i] = line + (comment.group(0) if comment else "")
    result = "\n".join(lines) + "\n"
    after = parse(result)
    for c in after["customers"].values():
        if username in (c.get("users") or {}):
            if c["users"][username].get(field) != value:
                raise _layout_error()
            return result
    raise _layout_error()


def set_customer_field_text(text, code, field, value):
    """customers.yml with one field of one customer set (added if missing)."""
    if field not in CUSTOMER_FIELDS - {"users"}:
        raise ConfigError(f"customers have no field '{field}' that can be set this way")
    lines = text.splitlines()
    top = _find(lines, "customers", 0)
    c = _find(lines, code, 2, top + 1) if top is not None else None
    if c is None:
        raise ConfigError(f"customer {code} isn't in customers.yml")
    end = _block_end(lines, c, 2)
    i = _find(lines, field, 4, c + 1, end)
    line = f"    {field}: {_yaml_value(value)}"
    if i is None:
        lines.insert(c + 1, line)
    else:
        lines[i] = line
    result = "\n".join(lines) + "\n"
    if parse(result)["customers"][code].get(field) != value:
        raise _layout_error()
    return result


def find_user(config, username):
    """(customer code, user fields) for a username, or raise."""
    for code, c in config["customers"].items():
        if username in (c.get("users") or {}):
            return code, c["users"][username]
    raise ConfigError(f"user {username} isn't in customers.yml")


def quota_spec(accounts_, mount="/raiddrive", base="/raiddrive/cluster"):
    """What ansible/roles/customer_storage/files/cluster-quota needs: each customer's group ID, limit
    and folders (its project folder and its users' home folders)."""
    spec = []
    for c in accounts_["customers"]:
        homes = [f"{base}/home/{u['name']}" for u in accounts_["users"] if u["customer"] == c["code"]]
        spec.append({"gid": c["gid"], "limit_gb": c["storage_gb"], "dirs": [f"{base}/projects/{c['code']}"] + homes})
    return {"mount": mount, "customers": spec}
