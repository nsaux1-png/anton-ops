"""SOP-111: the NVIDIA driver on GPU nodes, and every GPU doing real work."""

import os
import re
import unittest
import uuid

import yaml

from helpers import REPO, hosts, run, var

NODES = hosts("gpu_nodes")
with open(os.path.join(REPO, "ansible/roles/nvidia_driver/defaults/main.yml")) as f:
    DRIVER = yaml.safe_load(f)
EXPECTED_VERSION = re.match(r"\d+:([\d.]+)-", DRIVER["nvidia_driver_version"]).group(1)
NVCC = f"/usr/local/cuda-{DRIVER['nvidia_test_cuda'].replace('-', '.')}/bin/nvcc"
with open(os.path.join(REPO, "tests/live/gpu/gpucheck.cu")) as f:
    GPUCHECK_SOURCE = f.read()


def smi(node, fields, gpu=None):
    """nvidia-smi query, one list of values per GPU."""
    which = f"-i {gpu} " if gpu is not None else ""
    r = run(node, f"nvidia-smi {which}--query-gpu={fields} --format=csv,noheader,nounits")
    return [[c.strip() for c in line.split(",")] for line in r.stdout.splitlines()]


class Driver(unittest.TestCase):
    def test_every_gpu_is_visible_with_the_pinned_driver(self):
        for node in NODES:
            with self.subTest(node=node):
                rows = smi(node, "index,name,driver_version")
                self.assertEqual(len(rows), var(node, "gpu_count"), rows)
                for index, name, version in rows:
                    self.assertEqual(name, var(node, "gpu_name"))
                    self.assertEqual(version, EXPECTED_VERSION)

    def test_nvidia_module_loaded_and_nouveau_not(self):
        for node in NODES:
            with self.subTest(node=node):
                modules = run(node, "lsmod | awk '{print $1}'").stdout.split()
                self.assertIn("nvidia", modules)
                self.assertNotIn("nouveau", modules)

    def test_open_kernel_modules_in_use(self):
        for node in NODES:
            with self.subTest(node=node):
                license_ = run(node, "modinfo -F license nvidia").stdout.strip()
                self.assertEqual(license_, "Dual MIT/GPL")

    def test_persistence_mode_is_on(self):
        for node in NODES:
            with self.subTest(node=node):
                self.assertEqual(run(node, "systemctl is-active nvidia-persistenced").stdout.strip(), "active")
                self.assertEqual({row[0] for row in smi(node, "persistence_mode")}, {"Enabled"})

    def test_driver_is_built_for_the_running_kernel(self):
        for node in NODES:
            with self.subTest(node=node):
                kernel = run(node, "uname -r").stdout.strip()
                status = run(node, "sudo dkms status").stdout
                self.assertRegex(status, rf"nvidia/{re.escape(EXPECTED_VERSION)}, {re.escape(kernel)}, x86_64: installed")

    def test_driver_packages_are_version_locked(self):
        for node in NODES:
            with self.subTest(node=node):
                locked = run(node, "dnf -q versionlock list").stdout
                for package in DRIVER["nvidia_driver_packages"]:
                    self.assertIn(f"{package}-{DRIVER['nvidia_driver_version']}", locked)

    def test_readings_work_on_these_cards(self):
        """GeForce cards don't support every reading; these are the ones billing and monitoring need."""
        for node in NODES:
            with self.subTest(node=node):
                for row in smi(node, "utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu"):
                    for value in row:
                        float(value)   # "[N/A]" would fail here

    def test_full_memory_window_is_mapped(self):
        """BAR1 the size of the GPU's memory means Above 4G decoding and Resizable BAR are on in the BIOS."""
        for node in NODES:
            with self.subTest(node=node):
                out = run(node, "nvidia-smi -q -d MEMORY").stdout
                bar1 = re.findall(r"BAR1 Memory Usage\s*\n\s*Total\s*:\s*(\d+) MiB", out)
                total = re.findall(r"FB Memory Usage\s*\n\s*Total\s*:\s*(\d+) MiB", out)
                self.assertEqual(len(bar1), var(node, "gpu_count"))
                for b, t in zip(bar1, total):
                    self.assertGreaterEqual(int(b), int(t) - 1024)


class GpuWork(unittest.TestCase):
    """Build a small CUDA program on each node and run it on every GPU."""

    @classmethod
    def setUpClass(cls):
        cls.dirs = {}
        for node in NODES:
            d = f"/tmp/gpucheck-{uuid.uuid4().hex}"
            r = run(node, f"mkdir {d} && cat > {d}/gpucheck.cu && "
                          f"{NVCC} -O2 -arch=sm_120 -o {d}/gpucheck {d}/gpucheck.cu", input=GPUCHECK_SOURCE)
            if r.returncode != 0:
                raise RuntimeError(f"building gpucheck on {node} failed: {r.stdout}{r.stderr}")
            cls.dirs[node] = d

    @classmethod
    def tearDownClass(cls):
        for node, d in cls.dirs.items():
            run(node, f"rm -rf {d}")

    def test_every_gpu_runs_a_cuda_program_correctly(self):
        for node in NODES:
            with self.subTest(node=node):
                r = run(node, f"{self.dirs[node]}/gpucheck 3", timeout=600)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                ok = [line for line in r.stdout.splitlines() if line.startswith("OK ")]
                self.assertEqual(len(ok), var(node, "gpu_count"), r.stdout)
                for line in ok:
                    self.assertIn("cc=12.0", line)   # Blackwell, so the CUDA 12.8+ build works

    def test_pcie_links_under_load_match_the_recorded_layout(self):
        """Idle GPUs slow their links down, so each GPU is measured while it works."""
        for node in NODES:
            expected = var(node, "gpu_pcie_links")
            for index in range(var(node, "gpu_count")):
                with self.subTest(node=node, gpu=index):
                    r = run(node, f"CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES={index} "
                                  f"{self.dirs[node]}/gpucheck 6 > /dev/null & sleep 4; "
                                  f"nvidia-smi -i {index} --query-gpu=pci.bus_id,pcie.link.gen.current,"
                                  f"pcie.link.width.current --format=csv,noheader,nounits; wait", timeout=120)
                    bus, gen, width = [c.strip() for c in r.stdout.strip().split(",")]
                    bus = bus.lower().replace("00000000:", "0000:")
                    self.assertEqual(f"gen{gen} x{width}", expected.get(bus), f"{bus} measured gen{gen} x{width}")


if __name__ == "__main__":
    unittest.main()
