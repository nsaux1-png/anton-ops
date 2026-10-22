"""Tests for clusterlib.software and the parts of cluster-software that don't need the network or root."""

import copy
import os
import sys
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, REPO)

from clusterlib import software as sw            # noqa: E402
from clusterlib import software_cli as cli        # noqa: E402

with open(os.path.join(REPO, "config", "versions.yml")) as f:
    VERSIONS = yaml.safe_load(f)


def config(**changes):
    v = copy.deepcopy(VERSIONS)
    v["software"].update(changes)
    return v


class Stacks(unittest.TestCase):
    def test_the_repos_config(self):
        stacks = sw.stacks(VERSIONS)
        self.assertEqual(stacks[0].kind, "miniforge", "miniforge comes first: the others are built with it")
        kinds = [s.kind for s in stacks]
        self.assertIn("pytorch", kinds)
        self.assertIn("container", kinds)
        for s in stacks:
            self.assertTrue(s.path.startswith(sw.ROOT + "/"))
        self.assertEqual(sum(1 for s in stacks if s.kind == "pytorch" and s.default), 1)

    def test_pytorch_needs_miniforge(self):
        v = copy.deepcopy(VERSIONS)
        del v["software"]["miniforge"]
        with self.assertRaises(sw.SoftwareError):
            sw.stacks(v)

    def test_one_default_only(self):
        two = [dict(VERSIONS["software"]["pytorch"][0]), dict(VERSIONS["software"]["pytorch"][0], version="9.9-x")]
        with self.assertRaises(sw.SoftwareError):
            sw.stacks(config(pytorch=two))

    def test_containers_are_pinned_by_digest(self):
        with self.assertRaises(sw.SoftwareError):
            sw.stacks(config(containers=[{"name": "x", "image": "docker://pytorch/pytorch:latest"}]))

    def test_missing_fields_are_refused(self):
        with self.assertRaises(sw.SoftwareError):
            sw.stacks(config(pytorch=[{"version": "2.0-x"}]))

    def test_two_entries_cant_share_a_folder(self):
        p = VERSIONS["software"]["pytorch"][0]
        with self.assertRaises(sw.SoftwareError):
            sw.stacks(config(pytorch=[p, dict(p, default=False)]))

    def test_module_names_and_markers(self):
        stacks = {s.kind: s for s in sw.stacks(VERSIONS)}
        self.assertEqual(stacks["pytorch"].module, f"pytorch/{stacks['pytorch'].version}")
        self.assertIsNone(stacks["container"].module)
        self.assertEqual(stacks["pytorch"].marker, stacks["pytorch"].path + "/.cluster-built")
        self.assertEqual(stacks["container"].marker, stacks["container"].path + ".cluster-built")


class ModuleFiles(unittest.TestCase):
    def test_pytorch_puts_its_python_first_and_conflicts_with_other_versions(self):
        stacks = {s.kind: s for s in sw.stacks(VERSIONS)}
        text = sw.module_text(stacks["pytorch"], stacks["miniforge"])
        self.assertTrue(text.startswith("#%Module1.0"))
        self.assertIn(f"prepend-path PATH {stacks['pytorch'].path}/bin", text)
        self.assertIn("conflict pytorch", text)
        self.assertIn("--system-site-packages", text)

    def test_miniforge_sets_up_conda_activate(self):
        mf = sw.stacks(VERSIONS)[0]
        self.assertIn(f"source-sh bash {mf.path}/etc/profile.d/conda.sh", sw.module_text(mf, mf))

    def test_default_version_file(self):
        self.assertEqual(sw.version_file_text("2.14.1-cu130"), '#%Module1.0\nset ModulesVersion "2.14.1-cu130"\n')

    def test_readme_lists_only_what_is_built(self):
        stacks = sw.stacks(VERSIONS)
        torch = next(s for s in stacks if s.kind == "pytorch")
        self.assertNotIn(torch.module, sw.readme_text(stacks, set()))
        text = sw.readme_text(stacks, {torch.path})
        self.assertIn(f"`module load {torch.module}` (the default)", text)
        self.assertIn("--system-site-packages", text)


class Publish(unittest.TestCase):
    def test_writes_module_files_for_built_stacks_once(self):
        with tempfile.TemporaryDirectory() as root:
            stacks = sw.stacks(VERSIONS, root=root)
            for s in stacks:
                if s.kind in ("miniforge", "pytorch"):
                    os.makedirs(s.path)
                    open(s.marker, "w").close()
            changed = cli.publish(stacks, root=root)
            torch = next(s for s in stacks if s.kind == "pytorch")
            self.assertIn(torch.module, changed)
            self.assertTrue(os.path.exists(f"{root}/modulefiles/{torch.module}"))
            with open(f"{root}/modulefiles/pytorch/.version") as f:
                self.assertIn(torch.version, f.read())
            self.assertEqual(cli.publish(stacks, root=root), [], "a second publish changes nothing")

    def test_remove_partial_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            s = next(x for x in sw.stacks(VERSIONS, root=root) if x.kind == "container")
            os.makedirs(os.path.dirname(s.path))
            for p in (s.path + ".partial", s.marker):
                open(p, "w").close()
            cli.remove_partial(s)
            self.assertEqual(os.listdir(os.path.dirname(s.path)), [])


if __name__ == "__main__":
    unittest.main()
