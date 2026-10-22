"""cluster-software: builds and checks the shared software in /cluster/software, on the storage server
(SOP-144). Runs as root; admins use ./cluster software. Builds whatever config/versions.yml asks for that
isn't built yet, and never changes a built version. A failed build leaves nothing behind.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import yaml

from clusterlib import software as sw

VERSIONS = "/etc/cluster/config/versions.yml"
CONDARC = """# Managed by cluster-software (SOP-144). This conda is shared and read-only: your environments and the
# packages they're made from go in your own folder (they count against your storage limit).
channels: [conda-forge]
envs_dirs: [~/.conda/envs]
pkgs_dirs: [~/.conda/pkgs]
auto_activate_base: false
"""


def load(path=VERSIONS):
    with open(path) as f:
        return sw.stacks(yaml.safe_load(f))


def is_built(stack):
    return os.path.exists(stack.marker)


def say(text):
    print(text, flush=True)


def run(cmd, env=None):
    say("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_env(tmp):
    """Downloads and unpacking go to the build folder on the RAID, not anton's system disk."""
    return dict(os.environ, TMPDIR=tmp, APPTAINER_TMPDIR=tmp, PIP_NO_CACHE_DIR="1")


def write_marker(stack, **extra):
    info = {"built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "by": os.environ.get("SUDO_USER", "root"), "kind": stack.kind, "version": stack.version,
            "spec": stack.spec, **extra}
    with open(stack.marker, "w") as f:
        json.dump(info, f, indent=2)
        f.write("\n")


def build_miniforge(stack, tmp):
    url = sw.MINIFORGE_URL.format(v=stack.version)
    installer = os.path.join(tmp, "miniforge.sh")
    say(f"downloading {url}")
    urllib.request.urlretrieve(url, installer)
    digest = sha256(installer)
    if digest != stack.spec["sha256"]:
        raise sw.SoftwareError(f"miniforge {stack.version}: checksum {digest} isn't the pinned one")
    run(["bash", installer, "-b", "-p", stack.path], env=build_env(tmp))
    with open(os.path.join(stack.path, ".condarc"), "w") as f:
        f.write(CONDARC)
    write_marker(stack, sha256=digest)


def build_pytorch(stack, miniforge, tmp):
    env = build_env(tmp)
    env["CONDA_PKGS_DIRS"] = os.path.join(miniforge.path, "pkgs")   # the shared conda's own cache, while root builds
    run([os.path.join(miniforge.path, "bin", "conda"), "create", "-y", "-p", stack.path,
         f"python={stack.spec['python']}", "pip", "--override-channels", "-c", "conda-forge"], env=env)
    pip = os.path.join(stack.path, "bin", "pip")
    run([pip, "install", "--index-url", stack.spec["index"]] + list(stack.spec["packages"]), env=env)
    frozen = subprocess.run([pip, "freeze"], check=True, capture_output=True, text=True, env=env).stdout
    with open(os.path.join(stack.path, "cluster-packages.txt"), "w") as f:
        f.write(frozen)
    write_marker(stack, packages=frozen.split())


def build_container(stack, tmp):
    partial = stack.path + ".partial"
    os.makedirs(os.path.dirname(stack.path), exist_ok=True)
    run(["apptainer", "pull", "--disable-cache", partial, stack.spec["image"]], env=build_env(tmp))
    os.rename(partial, stack.path)
    write_marker(stack, sha256=sha256(stack.path))


def remove_partial(stack):
    for path in (stack.path, stack.path + ".partial", stack.marker):
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = open(path).read() if os.path.exists(path) else None
    if current != text:
        with open(path, "w") as f:
            f.write(text)
        return True
    return False


def publish(stacks, root=sw.ROOT):
    """Module files and the README for what's built, from versions.yml. Returns the files changed."""
    built = {s.path for s in stacks if is_built(s)}
    miniforge = next((s for s in stacks if s.kind == "miniforge"), None)
    changed = []
    for s in stacks:
        if s.module and s.path in built:
            if write_text(f"{root}/modulefiles/{s.module}", sw.module_text(s, miniforge)):
                changed.append(s.module)
            if s.default and write_text(f"{root}/modulefiles/{s.name}/.version", sw.version_file_text(s.version)):
                changed.append(f"{s.name} default")
    if write_text(f"{root}/README.md", sw.readme_text(stacks, built)):
        changed.append("README.md")
    return changed


def cmd_list(args, stacks):
    for s in stacks:
        state = "built" if is_built(s) else "not built"
        say(f"{s.kind:<10} {s.module or s.name:<40} {state:<10} {s.path}")
    return 0


def cmd_build(args, stacks):
    wanted = [s for s in stacks if not args.name or args.name in (s.name, s.module)]
    if args.name and not wanted:
        say(f"nothing called {args.name} in versions.yml")
        return 2
    miniforge = next((s for s in stacks if s.kind == "miniforge"), None)
    os.umask(0o022)
    tmp_root = os.path.join(sw.ROOT, ".build")
    os.makedirs(tmp_root, mode=0o700, exist_ok=True)
    built_now = []
    for s in wanted:
        if is_built(s):
            say(f"{s.module or s.name}: already built")
            continue
        if s.kind == "pytorch" and not is_built(miniforge):
            say(f"{s.module}: build miniforge first (./cluster software build miniforge)")
            return 1
        say(f"{s.module or s.name}: building in {s.path}")
        tmp = tempfile.mkdtemp(dir=tmp_root)
        try:
            {"miniforge": lambda: build_miniforge(s, tmp), "pytorch": lambda: build_pytorch(s, miniforge, tmp),
             "container": lambda: build_container(s, tmp)}[s.kind]()
        except (subprocess.CalledProcessError, sw.SoftwareError, OSError) as e:
            say(f"{s.module or s.name}: FAILED ({e}); removing what was half built")
            remove_partial(s)
            return 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        built_now.append(s.module or s.name)
    for f in publish(stacks):
        say(f"published {f}")
    say(f"built: {', '.join(built_now)}" if built_now else "nothing new to build")
    return 0


def cmd_check(args, stacks):
    """Exit 1 unless every stack is built, with its module file, and nothing is writable by customers."""
    problems = []
    for s in stacks:
        if not is_built(s):
            problems.append(f"{s.module or s.name}: not built")
            continue
        if s.module and not os.path.exists(f"{sw.ROOT}/modulefiles/{s.module}"):
            problems.append(f"{s.module}: no module file")
        mode = os.stat(s.path).st_mode
        if mode & 0o022:
            problems.append(f"{s.path}: writable by group or others")
    for p in problems:
        say(p)
    say("all shared software built and published" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cluster-software", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("build")
    p.add_argument("name", nargs="?", help="one stack (e.g. pytorch or pytorch/2.14.1-cu130); default: all")
    p.set_defaults(func=cmd_build)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    try:
        stacks = load()
    except sw.SoftwareError as e:
        say(f"cluster-software: {e}")
        return 2
    return args.func(args, stacks)
