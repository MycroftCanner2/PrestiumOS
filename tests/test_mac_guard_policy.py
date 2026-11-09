#!/usr/bin/python3
"""2.0 r10: unit tests of prestium-mac-guard's policy (no NetworkManager needed)."""
import importlib.machinery, importlib.util, os, unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "includes.chroot",
                   "usr", "local", "sbin", "prestium-mac-guard")
loader = importlib.machinery.SourceFileLoader("macguard", SRC)
spec = importlib.util.spec_from_loader("macguard", loader)
g = importlib.util.module_from_spec(spec); loader.exec_module(g)
from gi.repository import GLib

REAL = "00:11:22:33:44:55"

class Policy(unittest.TestCase):
    def test_default_ok(self):
        self.assertEqual(g.mac_violations({"connection": {"id": "x"}, "802-11-wireless": {"ssid": b"x"}}), [])

    def test_preserve_random_ok(self):
        for v in ("preserve", "random", "PRESERVE"):
            self.assertEqual(g.mac_violations({"802-3-ethernet": {"assigned-mac-address": v}}), [])

    def test_permanent_refused(self):
        self.assertTrue(g.mac_violations({"802-3-ethernet": {"assigned-mac-address": "permanent"}}))

    def test_explicit_and_stable_refused(self):
        for v in (REAL, "stable", "aa:bb:cc:dd:ee:ff"):
            self.assertTrue(g.mac_violations({"802-11-wireless": {"assigned-mac-address": v}}), v)

    def test_legacy_cloned_bytes_refused(self):
        self.assertTrue(g.mac_violations({"802-3-ethernet": {"cloned-mac-address": [0, 17, 34, 51, 68, 85]}}))

    def test_legacy_randomization_never(self):
        self.assertTrue(g.mac_violations({"802-11-wireless": {"mac-address-randomization": 1}}))

    def test_mask_refused(self):
        self.assertTrue(g.mac_violations({"802-3-ethernet": {"assigned-mac-address": "random",
                                                              "generate-mac-address-mask": "FE:FF:FF:00:00:00"}}))

    def test_fixed_settings_clean(self):
        bad = {"802-3-ethernet": {"assigned-mac-address": "permanent", "cloned-mac-address": [1] * 6},
               "connection": {"id": "w"}}
        self.assertEqual(g.mac_violations(g.fixed_settings(bad)), [])

    def test_real_mac_detection(self):
        self.assertTrue(g.is_real_mac(REAL.upper(), REAL))
        self.assertFalse(g.is_real_mac("02:11:22:33:44:56", REAL))
        self.assertFalse(g.is_real_mac("00:00:00:00:00:00", "00:00:00:00:00:00"))
        self.assertFalse(g.is_real_mac("", ""))

    def test_nft_rules(self):
        r = g.nft_rules("wlp2s0", REAL.upper())
        self.assertIn('hook egress device "wlp2s0"', r)
        self.assertIn("ether saddr 00:11:22:33:44:55 counter drop", r)
        for bad in (("eth0; flush ruleset", REAL), ("eth0", "x"), ("", REAL)):
            with self.assertRaises(ValueError):
                g.nft_rules(*bad)

    def test_repaired_variant_keeps_secrets(self):
        raw = GLib.Variant("a{sa{sv}}", {
            "connection": {"id": GLib.Variant("s", "Home"), "type": GLib.Variant("s", "802-11-wireless")},
            "802-11-wireless": {"ssid": GLib.Variant("ay", b"Home"),
                                "assigned-mac-address": GLib.Variant("s", "permanent"),
                                "cloned-mac-address": GLib.Variant("ay", bytes(6))},
            "802-11-wireless-security": {"key-mgmt": GLib.Variant("s", "wpa-psk")}})
        sec = GLib.Variant("a{sa{sv}}", {"802-11-wireless-security": {"psk": GLib.Variant("s", "hunter22")}})
        out = g.repaired_variant(raw, [sec]).unpack()
        self.assertEqual(out["802-11-wireless"]["assigned-mac-address"], "preserve")
        self.assertNotIn("cloned-mac-address", out["802-11-wireless"])
        self.assertEqual(out["802-11-wireless-security"]["psk"], "hunter22")
        self.assertEqual(out["802-11-wireless-security"]["key-mgmt"], "wpa-psk")
        self.assertEqual(out["connection"]["id"], "Home")
        self.assertEqual(g.mac_violations(out), [])
        # and it can be wrapped as Update's argument
        GLib.Variant.new_tuple(g.repaired_variant(raw, [sec]))

if __name__ == "__main__":
    unittest.main(verbosity=1)
