"""SOP-107: the extra kernel options in config/nodes.yml are on every boot entry, kept for kernels installed
later, and on the running kernel."""

import unittest

from helpers import hosts, run, var


def options(host, name):
    try:
        return var(host, name)
    except KeyError:
        return []


def machines():
    return [h for h in hosts() if options(h, "kernel_args") or options(h, "kernel_args_remove")]


class KernelOptions(unittest.TestCase):
    def check(self, host, lines, where):
        self.assertTrue(lines, f"nothing read from {where}")
        for arg in options(host, "kernel_args"):
            with self.subTest(host=host, where=where, arg=arg):
                self.assertTrue(all(arg in line for line in lines), f"{arg} missing")
        for arg in options(host, "kernel_args_remove"):
            with self.subTest(host=host, where=where, absent=arg):
                self.assertFalse(any(arg in line for line in lines), f"{arg} still there")

    def test_every_boot_entry_has_them(self):
        for host in machines():
            out = run(host, "sudo grubby --info=ALL").stdout
            lines = [l[len('args="'):].rstrip('"').split() for l in out.splitlines() if l.startswith("args=")]
            self.check(host, lines, "boot entries")

    def test_kernels_installed_later_get_them(self):
        for host in machines():
            grub = run(host, "sed -n 's/^GRUB_CMDLINE_LINUX=\"\\(.*\\)\"$/\\1/p' /etc/default/grub").stdout.split()
            lines = [grub]
            kernel_cmdline = run(host, "cat /etc/kernel/cmdline 2>/dev/null")
            if kernel_cmdline.returncode == 0:
                lines.append(kernel_cmdline.stdout.split())
            self.check(host, lines, "/etc/default/grub and /etc/kernel/cmdline")

    def test_running_kernel_has_them(self):
        """Fails after a change until the machine has rebooted: the options apply at boot."""
        for host in machines():
            self.check(host, [run(host, "cat /proc/cmdline").stdout.split()], "/proc/cmdline")


if __name__ == "__main__":
    unittest.main()
