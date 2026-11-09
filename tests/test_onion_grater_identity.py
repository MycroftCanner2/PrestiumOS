#!/usr/bin/python3
"""2.0 r9: onion-grater must recognise Tor Browser (and OnionShare) by the file they really run,
not by a path that an unprivileged mount namespace can fake.

Needs bwrap and sudo (creates /opt/tor-browser/Browser/firefox.real and /usr/bin/onionshare for the
test when they don't exist, and removes them afterwards). Runs the real identify() from
config/includes.chroot/usr/local/sbin/prestium-onion-grater against processes inside bwrap.
"""
import importlib.machinery, importlib.util, os, shutil, socket, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "config", "includes.chroot", "usr", "local", "sbin", "prestium-onion-grater")
PY = os.path.realpath("/usr/bin/python3")
TB = "/opt/tor-browser/Browser/firefox.real"
OS_SCRIPT = "/usr/bin/onionshare"


def load():
    loader = importlib.machinery.SourceFileLoader("og", SRC)
    spec = importlib.util.spec_from_loader("og", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    m.USER_UID = os.getuid()
    m.LOCALWEB_GID = None
    return m


CLIENT = "import socket,sys,time; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[-1]); time.sleep(3)"


class Identity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.og = load()
        cls.tmp = tempfile.mkdtemp()
        os.chmod(cls.tmp, 0o755)
        cls.created = []
        if not os.path.exists(TB):
            subprocess.run(["sudo", "-n", "install", "-D", "-m", "0755", PY, TB], check=True)
            cls.created.append(TB)
        if not os.path.exists(OS_SCRIPT):
            src = os.path.join(cls.tmp, "client.py"); open(src, "w").write(CLIENT + "\n")
            subprocess.run(["sudo", "-n", "install", "-m", "0644", src, OS_SCRIPT], check=True)
            cls.created.append(OS_SCRIPT)
        cls.fake = os.path.join(cls.tmp, "fake-python")
        shutil.copy(PY, cls.fake)
        cls.fake_script = os.path.join(cls.tmp, "fake-onionshare")
        open(cls.fake_script, "w").write("# not onionshare\n" + CLIENT + "\n")

    @classmethod
    def tearDownClass(cls):
        for f in cls.created:
            subprocess.run(["sudo", "-n", "rm", "-f", f])
        subprocess.run(["sudo", "-n", "rmdir", "-p", "--ignore-fail-on-non-empty", os.path.dirname(TB)],
                       stderr=subprocess.DEVNULL)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_client(self, binds, argv):
        path = os.path.join(self.tmp, "ctl")
        if os.path.exists(path):
            os.unlink(path)
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(path); srv.listen(1)
        cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/", "/",
               "--proc", "/proc", "--dev", "/dev", "--bind", self.tmp, self.tmp] + binds + ["--"] + argv + [path]
        p = subprocess.Popen(cmd)
        try:
            srv.settimeout(10)
            conn, _ = srv.accept()
            return self.og.identify(conn)
        finally:
            p.wait(timeout=20); srv.close()

    def test_real_tor_browser(self):
        who = self.run_client([], [TB, "-c", CLIENT])[0]
        self.assertEqual(who, "tor-browser")

    def test_real_tor_browser_bind_mounted(self):
        # the sandbox binds /opt/tor-browser at the same path: same file, still recognised
        who = self.run_client(["--ro-bind", "/opt/tor-browser", "/opt/tor-browser"], [TB, "-c", CLIENT])[0]
        self.assertEqual(who, "tor-browser")

    def test_fake_tor_browser_refused(self):
        who, why, _ = self.run_client(["--ro-bind", self.fake, TB], [TB, "-c", CLIENT])
        self.assertIsNone(who); self.assertIn("fake", why)

    def test_real_onionshare(self):
        who = self.run_client([], [PY, OS_SCRIPT])[0]
        self.assertEqual(who, "onionshare")

    def test_fake_onionshare_script_refused(self):
        who, why, _ = self.run_client(["--ro-bind", self.fake_script, OS_SCRIPT], [PY, OS_SCRIPT])
        self.assertIsNone(who); self.assertIn("not the system file", why)

    def test_real_python_fake_exe_path_refused(self):
        # a different binary bound over /usr/bin/python3.X
        who, why, _ = self.run_client(["--ro-bind", self.fake, PY], [PY, OS_SCRIPT])
        self.assertIsNone(who); self.assertIn("fake", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
