#!/usr/bin/env python3
"""2.0 r7 regression: prestium-tor-mode failure handling, run against the real helper code.

No root, no Tor, no ferm: the module is loaded with its paths pointed into a temp dir and
systemctl/tor calls replaced by recorders. Checks:
  - a failed firewall reload during apply never reports success and never starts Tor
  - when the restore's firewall reload also fails, Tor stays stopped and the state says why
  - restore() puts back the complete previous state (files that did not exist are removed)
  - revert with a failed firewall reload fails closed
"""
import importlib.machinery, importlib.util, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(HERE, "..", "config", "includes.chroot", "usr", "local", "sbin", "prestium-tor-mode")


def load(tmp):
    loader = importlib.machinery.SourceFileLoader("tormode_%d" % id(tmp), HELPER)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    m.DROPIN = os.path.join(tmp, "torrc.d", "50-prestium-assistant.conf")
    m.FERM_INC = os.path.join(tmp, "ferm", "prestium-tor-pt.conf")
    m.RUN = os.path.join(tmp, "run")
    m.STATE = m.RUN + "/tor-mode.json"
    m.PIDFILE = m.RUN + "/tor-mode-apply.pid"
    m.LOCK = m.RUN + "/tor-mode.lock"
    m.PREV = m.RUN + "/tor-mode.prev"
    m.HOSTS = os.path.join(tmp, "hosts")
    open(m.HOSTS, "w").write("127.0.0.1\tlocalhost prestium\n")
    m.calls = []

    def tor(action):
        m.calls.append(("tor", action))
        return True, ""
    m.tor = tor
    m.tor_verify_config = lambda: (True, "")
    m.parse_request = lambda: ("direct", True, [], 0)
    m.resolve = lambda hosts: ({}, {})
    m.ferm_results = []          # queue of booleans; default success

    real_firewall_error = m.FirewallError

    def ferm_reload():
        ok = m.ferm_results.pop(0) if m.ferm_results else True
        m.calls.append(("ferm", ok))
        if not ok:
            raise real_firewall_error("simulated ferm failure")
    m.ferm_reload = ferm_reload
    return m


def run(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            rc = fn()
        except SystemExit as e:
            rc = e.code
    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    return rc, json.loads(lines[-1]) if lines else {}


class TorModeFailures(unittest.TestCase):
    def setUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.m = load(self.tmpd.name)

    def tearDown(self):
        self.tmpd.cleanup()

    def test_failed_reload_never_reports_success(self):
        m = self.m
        m.ferm_results = [False, True]           # apply's reload fails, restore's reload works
        rc, res = run(m.cmd_apply)
        self.assertNotEqual(rc, 0)
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("reverted"))
        # Tor only started again after the previous firewall was verifiably reloaded
        i_fail = m.calls.index(("ferm", False))
        i_ok = m.calls.index(("ferm", True))
        starts = [i for i, c in enumerate(m.calls) if c == ("tor", "start")]
        self.assertTrue(all(i > i_ok > i_fail for i in starts), m.calls)

    def test_double_reload_failure_fails_closed(self):
        m = self.m
        m.ferm_results = [False, False]
        rc, res = run(m.cmd_apply)
        self.assertEqual(rc, 4)
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("tor_stopped"))
        self.assertIn("firewall_error", res)
        self.assertNotIn(("tor", "start"), m.calls)
        self.assertIn("firewall_error", json.load(open(m.STATE)))

    def test_restore_removes_files_that_did_not_exist(self):
        m = self.m
        os.makedirs(m.RUN, exist_ok=True)
        m.backup()                                # nothing exists yet
        m.atomic_write(m.DROPIN, "UseBridges 1\n")
        m.atomic_write(m.FERM_INC, "# new\n")
        self.assertTrue(m.restore())
        self.assertFalse(os.path.exists(m.DROPIN))
        self.assertFalse(os.path.exists(m.FERM_INC))
        self.assertTrue(os.path.exists(m.HOSTS))   # /etc/hosts is never removed

    def test_incomplete_snapshot_is_not_restored(self):
        m = self.m
        os.makedirs(m.PREV, exist_ok=True)
        open(os.path.join(m.PREV, "dropin"), "w").write("old\n")
        self.assertFalse(m.restore())             # no .complete marker
        self.assertFalse(os.path.exists(m.DROPIN))

    def test_revert_failed_reload_fails_closed(self):
        m = self.m
        os.makedirs(m.RUN, exist_ok=True)
        m.backup()
        m.ferm_results = [False]
        rc, res = run(m.cmd_revert)
        self.assertEqual(rc, 4)
        self.assertTrue(res.get("tor_stopped"))
        self.assertNotIn(("tor", "restart"), m.calls)
        self.assertIn(("tor", "stop"), m.calls)


if __name__ == "__main__":
    unittest.main()
