#!/usr/bin/python3
"""2.1: prestium-mac-guard's nft egress filter is re-installed on every device check, so a new permanent
address under the same interface name, or a ruleset flushed/failed earlier, is put right on the next
event. nft is a stub that records its input and exits with the code in a file (no real nft needed)."""
import importlib.machinery, importlib.util, os, tempfile, unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "includes.chroot",
                   "usr", "local", "sbin", "prestium-mac-guard")
loader = importlib.machinery.SourceFileLoader("macguard", SRC)
spec = importlib.util.spec_from_loader("macguard", loader)
g = importlib.util.module_from_spec(spec); loader.exec_module(g)
g.log = lambda *a, **k: None

A, B = "00:11:22:33:44:55", "66:77:88:99:aa:bb"

class Egress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.calls = os.path.join(self.tmp, "calls"); self.rc = os.path.join(self.tmp, "rc")
        self.nft = os.path.join(self.tmp, "nft")
        with open(self.nft, "w") as f:
            f.write('#!/bin/sh\n{ cat; echo ===; } >> %s\nexit $(cat %s 2>/dev/null || echo 0)\n' % (self.calls, self.rc))
        os.chmod(self.nft, 0o755)
        self.e = g.EgressFilters(self.nft)

    def set_rc(self, n):
        with open(self.rc, "w") as f:
            f.write(str(n))

    def installs(self):
        try:
            return [c for c in open(self.calls).read().split("===\n") if c.strip()]
        except OSError:
            return []

    def test_replug_same_name_new_permanent_address(self):
        self.assertTrue(self.e.ensure("/dev/1", "eth0", A))
        self.e.removed("/dev/1")
        self.assertTrue(self.e.ensure("/dev/2", "eth0", B))     # same name, new card
        ins = self.installs()
        self.assertEqual(len(ins), 2)
        self.assertIn("ether saddr %s counter drop" % A, ins[0])
        self.assertIn("ether saddr %s counter drop" % B, ins[1])
        self.assertIn('flush chain netdev prestium_mac egress_eth0', ins[1])
        self.assertEqual(self.e.installed, {"/dev/2": ("eth0", B)})

    def test_new_permanent_address_without_device_removed(self):
        self.e.ensure("/dev/1", "eth0", A); self.e.ensure("/dev/1", "eth0", B)
        self.assertIn("ether saddr %s" % B, self.installs()[-1])

    def test_failed_install_is_retried_on_next_event(self):
        self.set_rc(1)
        self.assertFalse(self.e.ensure("/dev/1", "eth0", A))
        self.assertNotIn("/dev/1", self.e.installed)
        self.set_rc(0)
        self.assertTrue(self.e.ensure("/dev/1", "eth0", A))
        self.assertEqual(len(self.installs()), 2)

    def test_reinstalled_after_flush_even_when_recorded(self):
        # "nft flush ruleset" by someone else is invisible to the guard; the next event installs again
        self.e.ensure("/dev/1", "eth0", A); self.e.ensure("/dev/1", "eth0", A)
        self.assertEqual(len(self.installs()), 2)

    def test_missing_nft_binary_is_logged_not_raised(self):
        e = g.EgressFilters(os.path.join(self.tmp, "no-such-nft"))
        self.assertFalse(e.ensure("/dev/1", "eth0", A))

    def test_unsafe_ifname_still_refused(self):
        self.assertFalse(self.e.ensure("/dev/1", 'eth0"; flush ruleset; "', A))
        self.assertEqual(self.installs(), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
