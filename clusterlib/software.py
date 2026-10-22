"""The shared software in /cluster/software (SOP-144): what config/versions.yml asks for, where each piece
lives, and its module file and README. No network or root in here, so it has code tests
(tests/code/test_software.py); clusterlib/software_cli.py does the building.

  /cluster/software/miniforge/<version>/            conda for everyone (environments go in their own folders)
  /cluster/software/pytorch/<version>/              a conda environment: Python plus PyTorch's own wheels
  /cluster/software/containers/<name>.sif           Apptainer images
  /cluster/software/modulefiles/<name>/<version>    what `module load` uses
  /cluster/software/README.md                       what's here and how to use it

Each built piece has a .cluster-built file next to it or inside it (when, which commit, what's in it) and is
never changed again. A customer's own environment can sit on top of a shared one:
  module load pytorch/<version>; python -m venv --system-site-packages ~/envs/mine
Their packages come first, the shared ones fill in. That works because each stack is a conda environment,
a Python of its own, not a venv: a venv made from a venv wouldn't see the first venv's packages.
"""

from dataclasses import dataclass, field

ROOT = "/cluster/software"
MARKER = ".cluster-built"
MINIFORGE_URL = "https://github.com/conda-forge/miniforge/releases/download/{v}/Miniforge3-{v}-Linux-x86_64.sh"


class SoftwareError(Exception):
    pass


@dataclass
class Stack:
    kind: str                 # miniforge, pytorch, container
    name: str                 # module name, or the image's name
    version: str
    path: str
    spec: dict = field(default_factory=dict)
    default: bool = False

    @property
    def module(self):
        """name/version for `module load`, or None (containers are used by path)."""
        return None if self.kind == "container" else f"{self.name}/{self.version}"

    @property
    def marker(self):
        return self.path + "." + MARKER.lstrip(".") if self.kind == "container" else f"{self.path}/{MARKER}"


def stacks(versions, root=ROOT):
    """Everything config/versions.yml asks for, in build order (miniforge first: the others need it)."""
    sw = versions.get("software") or {}
    out = []
    mf = sw.get("miniforge")
    if mf:
        out.append(Stack("miniforge", "miniforge", mf["version"], f"{root}/miniforge/{mf['version']}", mf, True))
    pytorch = sw.get("pytorch") or []
    if pytorch and not mf:
        raise SoftwareError("the pytorch stacks are built with miniforge: add software.miniforge")
    if sum(1 for p in pytorch if p.get("default")) > 1:
        raise SoftwareError("only one pytorch version can be the default")
    for p in pytorch:
        for key in ("version", "python", "index", "packages"):
            if key not in p:
                raise SoftwareError(f"pytorch {p.get('version', '?')}: missing {key}")
        out.append(Stack("pytorch", "pytorch", p["version"], f"{root}/pytorch/{p['version']}", p,
                         bool(p.get("default"))))
    for c in sw.get("containers") or []:
        if "@sha256:" not in c.get("image", ""):
            raise SoftwareError(f"container {c.get('name', '?')}: pin the image by digest (…@sha256:…)")
        out.append(Stack("container", c["name"], c["image"].rsplit("@sha256:", 1)[1][:12],
                         f"{root}/containers/{c['name']}.sif", c))
    names = [s.path for s in out]
    if len(names) != len(set(names)):
        raise SoftwareError("two entries in software: would build to the same place")
    return out


def module_text(stack, miniforge):
    """The module file for a stack. `miniforge` is the miniforge Stack (for conda's shell setup)."""
    head = f"#%Module1.0\n## Managed by cluster-software (SOP-144). Don't edit: it's rebuilt from config/versions.yml.\n"
    if stack.kind == "miniforge":
        return (head +
                f'module-whatis "conda and mamba (Miniforge {stack.version}). Your environments go in ~/.conda."\n'
                "conflict miniforge\n"
                f"source-sh bash {stack.path}/etc/profile.d/conda.sh\n")
    if stack.kind == "pytorch":
        pkgs = ", ".join(stack.spec["packages"])
        return (head +
                f'module-whatis "PyTorch: {pkgs}; Python {stack.spec["python"]}"\n'
                "proc ModulesHelp { } {\n"
                '    puts stderr "Add your own packages on top: python -m venv --system-site-packages ~/envs/mine"\n'
                "}\n"
                "conflict pytorch\n"
                f"prepend-path PATH {stack.path}/bin\n")
    raise SoftwareError(f"no module file for {stack.kind}")


def version_file_text(version):
    """modulefiles/<name>/.version: which version `module load <name>` picks."""
    return f'#%Module1.0\nset ModulesVersion "{version}"\n'


def readme_text(all_stacks, built):
    """/cluster/software/README.md: what's here (built ones only) and how to use it."""
    lines = ["# Shared software", "",
             "Built and kept by the cluster's admins. Free: none of it counts against your storage limit.",
             "Read-only: install your own packages in your home or project folder. See /cluster/docs/guide.md.", ""]
    mods = [s for s in all_stacks if s.module and s.path in built]
    if mods:
        lines += ["## Modules (`module avail`, `module load <name>`)", ""]
        lines += [f"- `module load {s.module}`" + (" (the default)" if s.default and s.kind == "pytorch" else "")
                  for s in mods]
        lines += ["", "Your own packages on top of a shared PyTorch:", "```bash",
                  "module load pytorch", "python -m venv --system-site-packages ~/envs/mine",
                  "source ~/envs/mine/bin/activate", "pip install transformers   # only your extras use your storage",
                  "```", ""]
    containers = [s for s in all_stacks if s.kind == "container" and s.path in built]
    if containers:
        lines += ["## Container images (Apptainer)", ""]
        lines += [f"- `{s.path}`: {s.spec.get('tag', s.spec['image'])}" for s in containers]
        lines += ["", "```bash", f"apptainer exec --nv {containers[0].path} python train.py", "```", ""]
    return "\n".join(lines) + "\n"
