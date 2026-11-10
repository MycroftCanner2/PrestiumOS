#!/usr/bin/python3
"""Prestium 2.1: Browser Updater window (config/includes.chroot/usr/local/bin/prestium-browser-updater),
driven with a stand-in for GTK (no display needed): checks the window's logic, not its looks. Every
update/reset path calls the library and the helper the way the plan says, buttons are disabled while a
job runs, Cancel only before the root helper starts, and the messages carry the required wording."""
import importlib.machinery, importlib.util, os, sys, threading, types, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_update_testlib as T  # noqa: E402
from browser_update_testlib import bu  # noqa: E402


class Widget:
    """Accepts any constructor and call; remembers a few states the tests read."""
    def __init__(self, *a, **kw):
        self._label = kw.get("label")
        self._text = ""
        self._sensitive = True
        self._visible = True
        self._handlers = {}
        self._fraction = 0.0

    # the few calls whose results the window uses
    def connect(self, sig, cb, *a):
        self._handlers[sig] = (cb, a)

    def click(self):
        cb, a = self._handlers["clicked"]
        cb(self, *a)

    def set_text(self, t):
        self._text = t

    def get_text(self):
        return self._text

    def set_sensitive(self, v):
        self._sensitive = bool(v)

    def set_visible(self, v):
        self._visible = bool(v)

    def set_fraction(self, f):
        self._fraction = f

    def get_buffer(self):
        if not hasattr(self, "_buf"):
            self._buf = Buffer()
        return self._buf

    def add_button(self, label, resp):
        b = Widget(label=label); return b

    def create_pango_layout(self, t):
        return types.SimpleNamespace(get_pixel_size=lambda: (10, 17))

    def get_screen(self):
        return Widget()

    def get_size(self):
        return (600, 600)

    def get_content_area(self):
        return Widget()

    def hide(self):
        self._visible = False

    def show(self):
        self._visible = True

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return lambda *a, **kw: None


class Buffer:
    def __init__(self):
        self.text = ""

    def set_text(self, t):
        self.text = t

    def insert(self, it, t):
        self.text += t

    def get_end_iter(self):
        return None

    def get_start_iter(self):
        return None

    def get_line_count(self):
        return self.text.count("\n")

    def get_iter_at_line(self, n):
        return None

    def delete(self, a, b):
        pass


def fake_gi():
    gi = types.ModuleType("gi")
    gi.require_version = lambda *a: None
    rep = types.ModuleType("gi.repository")
    Gtk = types.SimpleNamespace()
    for n in ("Label", "Box", "Frame", "Button", "ProgressBar", "InfoBar", "TextView", "ScrolledWindow",
              "Expander", "Application", "ApplicationWindow"):
        setattr(Gtk, n, type(n, (Widget,), {}))
    Gtk.Orientation = types.SimpleNamespace(VERTICAL=1, HORIZONTAL=0)
    Gtk.PolicyType = types.SimpleNamespace(NEVER=0, AUTOMATIC=1)
    Gtk.ShadowType = types.SimpleNamespace(IN=1)
    Gtk.WrapMode = types.SimpleNamespace(WORD_CHAR=1, CHAR=2)
    Gtk.MessageType = types.SimpleNamespace(INFO="info", WARNING="warning", ERROR="error")
    Gdk = types.SimpleNamespace(Display=types.SimpleNamespace(get_default=lambda: None),
                                Geometry=lambda: types.SimpleNamespace(), WindowHints=types.SimpleNamespace(MAX_SIZE=1))
    GLib = types.SimpleNamespace(idle_add=lambda f, *a: f(*a), Error=Exception)
    Gio = types.SimpleNamespace(ApplicationFlags=types.SimpleNamespace(FLAGS_NONE=0, NON_UNIQUE=1))
    Pango = types.SimpleNamespace(WrapMode=types.SimpleNamespace(WORD_CHAR=1), EllipsizeMode=types.SimpleNamespace(END=1))
    rep.Gtk, rep.Gdk, rep.GLib, rep.Gio, rep.Pango = Gtk, Gdk, GLib, Gio, Pango
    gi.repository = rep
    return gi, rep


def load_gui():
    gi, rep = fake_gi()
    with mock.patch.dict(sys.modules, {"gi": gi, "gi.repository": rep}):
        loader = importlib.machinery.SourceFileLoader("prestium_browser_updater", T.GUI)
        spec = importlib.util.spec_from_loader("prestium_browser_updater", loader)
        m = importlib.util.module_from_spec(spec)
        loader.exec_module(m)
    m.workarea = lambda win=None: (1366, 738)
    return m


class SyncThread:
    """threading.Thread stand-in that runs the target at start() (deterministic tests)."""
    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


class TestWindow(unittest.TestCase):
    def setUp(self):
        self.g = load_gui()
        self.g.threading.Thread = SyncThread
        self.p = []
        for name, val in (("installed_version", lambda n: {"version": "15.0.26" if n == "tor-browser" else "157.0.1",
                                                            "full": None if n == "tor-browser" else "157.0.1-1",
                                                            "updated": False}),
                          ("clean_staging", lambda n: self.calls.append(("clean", n)))):
            pt = mock.patch.object(bu, name, val); pt.start(); self.p.append(pt)
        pt = mock.patch.object(self.g, "browser_running", lambda n: False); pt.start(); self.p.append(pt)
        self.bound = set()
        pt = mock.patch.object(bu, "helper_bind_present", lambda n: n in self.bound); pt.start(); self.p.append(pt)
        self.calls = []
        self.w = self.g.Window(None)
        self.w.update_buttons()

    def tearDown(self):
        for pt in self.p:
            pt.stop()
        self.g.threading.Thread = threading.Thread

    def info(self):
        return self.w.info_view.get_buffer().text

    def test_layout_first_release(self):
        self.assertEqual(list(self.w.sections), ["tor-browser", "librewolf"])
        s = self.w.sections["tor-browser"]
        self.assertEqual(s.tor_btn._label, "Update using Tor")
        self.assertEqual(s.i2p_btn._label, "Update using I2P OutProxy")
        self.assertEqual(s.reset_btn._label, "Reset to shipped copy")
        self.assertIn("RAM", s.ram.get_text())
        self.assertIn("outproxy", s.help.get_text())
        self.assertIn("15.0.26", s.version.get_text())
        self.assertIn("157.0.1-1", self.w.sections["librewolf"].version.get_text())
        self.assertFalse(s.reset_btn._sensitive, "nothing to reset before an update")

    def test_update_success(self):
        seen = {}

        def prep(name, transport, cancel, progress, log):
            seen["prep"] = (name, transport)
            # all buttons disabled during the job; Cancel available while downloading
            seen["busy"] = [b._sensitive for s in self.w.sections.values() for b in (s.tor_btn, s.i2p_btn, s.reset_btn)]
            seen["cancel"] = self.w.sections[name].cancel_btn._sensitive
            progress("tor-browser-linux-x86_64-16.0.tar.xz", 42 * bu.MiB, 110 * bu.MiB)
            seen["progress"] = self.w.sections[name].progress.get_text()
            return {"status": "staged", "version": "16.0", "installed": "15.0.26"}

        def helper(cmd, name, on_event=None):
            seen["helper"] = (cmd, name)
            seen["cancel_in_helper"] = self.w.sections[name].cancel_btn._sensitive
            on_event({"event": "phase", "message": "Installing ..."})
            return {"ok": True, "version": "16.0", "message": "Tor Browser 16.0 is installed for this session. " + bu.RESET_HINT}
        with mock.patch.object(bu, "prepare_update", prep), mock.patch.object(bu, "run_helper", helper):
            self.w.sections["tor-browser"].tor_btn.click()
        self.assertEqual(seen["prep"], ("tor-browser", "tor"))
        self.assertEqual(seen["busy"], [False] * 6)
        self.assertTrue(seen["cancel"])
        self.assertIn("42 / 110 MB", seen["progress"])
        self.assertEqual(seen["helper"], ("install", "tor-browser"))
        self.assertFalse(seen["cancel_in_helper"], "no Cancel once the root helper runs")
        self.assertIn(("clean", "tor-browser"), self.calls)
        self.assertIn("Reset to shipped copy", self.info())
        self.assertIn("until Reset or reboot", self.info())
        self.assertIsNone(self.w.job)
        self.assertTrue(self.w.sections["librewolf"].tor_btn._sensitive)

    def test_i2p_transport(self):
        seen = {}

        def prep(name, transport, *a):
            seen["t"] = (name, transport)
            return {"status": "current", "version": "157.0.1-1", "installed": "157.0.1-1"}
        with mock.patch.object(bu, "prepare_update", prep):
            self.w.sections["librewolf"].i2p_btn.click()
        self.assertEqual(seen["t"], ("librewolf", "i2p"))
        self.assertIn("already installed", self.info())

    def test_key_expired_message(self):
        def prep(*a):
            raise bu.KeyExpiredError("Signature check failed: %s." % bu.KEY_EXPIRED_TEXT)
        with mock.patch.object(bu, "prepare_update", prep), mock.patch.object(bu, "run_helper") as h:
            self.w.sections["tor-browser"].tor_btn.click()
            h.assert_not_called()
        self.assertIn("key expired, use a newer ISO", self.info())

    def test_transport_down(self):
        def prep(*a):
            raise bu.TransportError(bu.TOR_DOWN)
        with mock.patch.object(bu, "prepare_update", prep), mock.patch.object(bu, "run_helper") as h:
            self.w.sections["tor-browser"].tor_btn.click()
            h.assert_not_called()
        self.assertIn("Tor Connection Assistant", self.info())

    def test_running_refused(self):
        with mock.patch.object(self.g, "browser_running", lambda n: True), \
                mock.patch.object(bu, "prepare_update") as p:
            self.w.sections["tor-browser"].tor_btn.click()
            p.assert_not_called()
        self.assertIn("Close it", self.info())

    def test_cancel(self):
        def prep(name, transport, cancel, progress, log):
            self.w.cancel_job()
            self.assertTrue(cancel.is_set())
            raise bu.Cancelled("cancelled")
        with mock.patch.object(bu, "prepare_update", prep), mock.patch.object(bu, "run_helper") as h:
            self.w.sections["tor-browser"].tor_btn.click()
            h.assert_not_called()
        self.assertIn("cancelled", self.info())

    def test_helper_failure_and_reset(self):
        with mock.patch.object(bu, "prepare_update", lambda *a: {"status": "staged", "version": "16.0", "installed": "15.0.26"}), \
                mock.patch.object(bu, "run_helper", lambda *a, **k: {"ok": False, "error": "boom", "code": 1}):
            self.w.sections["tor-browser"].tor_btn.click()
        self.assertIn("boom", self.info()); self.assertIn("Reset to shipped copy", self.info())
        self.assertIn(("clean", "tor-browser"), self.calls)
        self.w.sections["tor-browser"].updated = True
        seen = {}
        with mock.patch.object(bu, "run_helper", lambda cmd, name, on_event=None: seen.setdefault("c", (cmd, name)) and
                               {"ok": True, "message": "The shipped Tor Browser 15.0.26 is back."}):
            self.w.sections["tor-browser"].reset_btn.click()
        self.assertEqual(seen["c"], ("revert", "tor-browser"))
        self.assertIn("is back", self.info())

    def test_reset_available_while_a_bind_is_up(self):
        """No stamp (its write failed) but a helper bind on the factory path: Reset stays clickable and
        the label does not call the tree the USB copy."""
        s = self.w.sections["tor-browser"]
        self.assertFalse(s.reset_btn._sensitive)
        self.bound.add("tor-browser")
        s.refresh(); self.w.update_buttons()
        self.assertTrue(s.reset_btn._sensitive)
        self.assertNotIn("(the copy on the USB image)", s.version.get_text())
        self.assertIn("session update", s.version.get_text())

    def test_cancel_during_final_check_skips_helper(self):
        """Close or Cancel after the download, during the last signature check: the helper never runs."""
        def prep(name, transport, cancel, progress, log):
            self.w.on_delete()            # Close while prepare_update is still verifying
            return {"status": "staged", "version": "16.0", "installed": "15.0.26"}
        h = mock.Mock()
        with mock.patch.object(bu, "prepare_update", prep), mock.patch.object(bu, "run_helper", h):
            self.w.sections["tor-browser"].tor_btn.click()
        h.assert_not_called()
        self.assertIn(("clean", "tor-browser"), self.calls)

    def test_close_during_install_refused(self):
        self.w.job, self.w.can_cancel = ("tor-browser", "update", "tor"), False
        self.assertTrue(self.w.on_delete())
        self.w.job = None
        self.assertFalse(self.w.on_delete())


if __name__ == "__main__":
    unittest.main(verbosity=2)
