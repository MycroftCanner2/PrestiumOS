#!/usr/bin/python3
"""Prestium 2.1: Browser Updater library (config/includes.chroot/usr/local/lib/prestium/browser_update.py).
Offline: a fake curl, throw-away OpenPGP keys, fixtures from real publisher files in
tests/fixtures/browser-update/ (Tor Browser 16.0 ChangeLog, Tor's update JSON, LibreWolf's InRelease and
Packages as published on 2026-11-04). No root, no network, no Tor or I2P."""
import hashlib, json, os, shutil, socket, subprocess, sys, tempfile, threading, unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_update_testlib as T  # noqa: E402
from browser_update_testlib import bu  # noqa: E402

MiB = bu.MiB
HAVE_GPG = T.have("gpg") and T.have("gpgconf")


class FakeDU:
    def __init__(self, free):
        self.free = free

    def __call__(self, path):
        return type("du", (), {"free": self.free, "total": self.free, "used": 0})()


def meminfo(d, kb):
    p = os.path.join(d, "meminfo-%d" % kb)
    with open(p, "w") as f:
        f.write("MemTotal: 4000000 kB\nMemFree: 1 kB\nMemAvailable: %d kB\n" % kb)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.old_env = dict(os.environ)
        os.environ["HOME"] = self.d

    def tearDown(self):
        os.environ.clear(); os.environ.update(self.old_env)
        shutil.rmtree(self.d, ignore_errors=True)


class TestTransports(Base):
    def test_tor_args_and_env(self):
        os.environ.update(https_proxy="http://127.0.0.1:4450/", http_proxy="http://127.0.0.1:4450/",
                          ALL_PROXY="socks5://x:1", HTTPS_PROXY="http://127.0.0.1:4450/")
        t = bu.Transport("tor")
        a = t.curl_args()
        self.assertEqual(a[:2], ["--socks5-hostname", "127.0.0.1:9050"])
        self.assertEqual(a[2], "--proxy-user")
        self.assertRegex(a[3], r"^[0-9a-f]{32}:$")
        self.assertEqual(t.curl_args(), a, "one SOCKS username for every curl of a job")
        self.assertNotEqual(bu.Transport("tor").curl_args()[3], a[3], "a fresh username per job")
        env = t.env()
        for k in env:
            self.assertNotIn("proxy", k.lower())
        self.assertNotIn("4450", json.dumps(env) + " ".join(a))

    def test_i2p_args(self):
        t = bu.Transport("i2p")
        self.assertEqual(t.curl_args(), ["-x", "http://127.0.0.1:4444"])
        self.assertNotIn("--proxy-user", t.curl_args())
        self.assertNotIn("4450", " ".join(t.curl_args()))

    def test_probe_down(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        old = bu.TOR_SOCKS, bu.I2P_HTTP
        try:
            bu.TOR_SOCKS = bu.I2P_HTTP = ("127.0.0.1", port)
            with self.assertRaises(bu.TransportError) as c:
                bu.Transport("tor").probe(1)
            self.assertEqual(str(c.exception), bu.TOR_DOWN)
            with self.assertRaises(bu.TransportError) as c:
                bu.Transport("i2p").probe(1)
            self.assertEqual(str(c.exception), bu.I2P_DOWN)
        finally:
            bu.TOR_SOCKS, bu.I2P_HTTP = old

    def test_torrc_isolate_socks_auth(self):
        torrc = open(os.path.join(T.INC, "etc/tor/torrc")).read().splitlines()
        lines = [l for l in torrc if l.startswith("SocksPort 127.0.0.1:9050")]
        self.assertEqual(len(lines), 1)
        self.assertIn("IsolateSOCKSAuth", lines[0].split())
        self.assertNotIn("NoIsolateSOCKSAuth", lines[0])
        self.assertIn("SocksPort unix:/run/prestium-tbb/socks WorldWritable", torrc)

    @unittest.skipUnless(T.have("curl"), "curl missing")
    def test_real_curl_sends_socks_username(self):
        """The real curl with our arguments offers SOCKS5 username auth with the job's token."""
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        got = {}

        def serve():
            c, _ = srv.accept()
            d = c.recv(16)
            got["methods"] = d[2:2 + d[1]]
            c.send(b"\x05\x02")
            a = c.recv(600)
            got["user"] = a[2:2 + a[1]].decode()
            c.close()
        th = threading.Thread(target=serve, daemon=True); th.start()
        old = bu.TOR_SOCKS
        try:
            bu.TOR_SOCKS = ("127.0.0.1", srv.getsockname()[1])
            t = bu.Transport("tor")
            f = bu.Fetcher("tor-browser", t, curl="curl")
            with self.assertRaises(bu.UpdateError):
                f.fetch("https://dist.torproject.org/", os.path.join(self.d, "x"), 1024)
            th.join(5)
            self.assertEqual(got.get("user"), t.token)
        finally:
            bu.TOR_SOCKS = old
            srv.close()


class TestRedirects(Base):
    def setUp(self):
        super().setUp()
        self.c = T.FakeCurl(self.d)
        self.f = bu.Fetcher("tor-browser", bu.Transport("tor"), curl=self.c.path, poll=0.05)

    def urls(self):
        return [c["argv"][-1] for c in self.c.calls()]

    def test_no_location_flag(self):
        self.c.route("https://dist.torproject.org/a", body="hi")
        self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        a = self.c.calls()[0]["argv"]
        self.assertNotIn("-L", a); self.assertNotIn("--location", a)
        self.assertIn("--max-redirs", a); self.assertEqual(a[a.index("--max-redirs") + 1], "0")
        self.assertIn("--proto", a); self.assertEqual(a[a.index("--proto") + 1], "=https")
        self.assertEqual(a[0], "-q", "never read ~/.curlrc")
        self.assertNotIn("--insecure", a); self.assertNotIn("-k", a)
        self.assertEqual(open(os.path.join(self.d, "a")).read(), "hi")
        env = self.c.calls()[0]["env"]
        self.assertFalse([k for k in env if "proxy" in k.lower()], env)

    def test_redirect_off_list_refused(self):
        self.c.route("https://dist.torproject.org/a", 302, location="https://evil.example/x")
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertEqual(self.urls(), ["https://dist.torproject.org/a"])
        self.assertFalse(any("evil.example" in u for u in self.urls()))
        self.assertFalse(os.path.exists(os.path.join(self.d, "a")))

    def test_scheme_relative_off_list_refused(self):
        self.c.route("https://dist.torproject.org/a", 301, location="//evil.example/x")
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertFalse(any("evil.example" in u for u in self.urls()))

    def test_http_redirect_refused(self):
        self.c.route("https://dist.torproject.org/a", 302, location="http://dist.torproject.org/a")
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertEqual(len(self.urls()), 1)

    def test_relative_location_urljoin_first(self):
        self.c.route("https://dist.torproject.org/torbrowser/16.0/a", 302, location="/foo")
        self.c.route("https://dist.torproject.org/foo", 307, location="../bar/b")
        self.c.route("https://dist.torproject.org/bar/b", body="ok")
        self.f.fetch("https://dist.torproject.org/torbrowser/16.0/a", os.path.join(self.d, "a"), 100)
        self.assertEqual(self.urls(), ["https://dist.torproject.org/torbrowser/16.0/a",
                                       "https://dist.torproject.org/foo", "https://dist.torproject.org/bar/b"])

    def test_relative_location_to_other_allowed_host(self):
        self.c.route("https://aus1.torproject.org/x", 302, location="https://dist.torproject.org/y")
        self.c.route("https://dist.torproject.org/y", body="ok")
        self.f.fetch("https://aus1.torproject.org/x", os.path.join(self.d, "a"), 100)
        self.assertEqual(len(self.urls()), 2)

    def test_hop_limit(self):
        self.c.route("https://dist.torproject.org/a", 302, location="/a")
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertEqual(len(self.urls()), bu.MAX_HOPS + 1)

    def test_proxy_connect_block_ignored(self):
        self.c.route("https://dist.torproject.org/a", 302, location="/b", connect=True)
        self.c.route("https://dist.torproject.org/b", body="ok", connect=True)
        self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertEqual(self.urls()[-1], "https://dist.torproject.org/b")

    def test_off_list_never_requested(self):
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://evil.example/", os.path.join(self.d, "a"), 100)
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://repo.librewolf.net/", os.path.join(self.d, "a"), 100)  # other browser's host
        self.assertEqual(self.c.calls(), [])

    def test_size_cap(self):
        self.c.route("https://dist.torproject.org/a", body="x" * 200)
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        a = self.c.calls()[0]["argv"]
        self.assertEqual(a[a.index("--max-filesize") + 1], "100")
        self.assertFalse(os.path.exists(os.path.join(self.d, "a")))

    def test_expected_size(self):
        self.c.route("https://dist.torproject.org/a", body="x" * 10)
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100, expected_size=11)

    def test_http_error(self):
        self.c.route("https://dist.torproject.org/a", 404)
        with self.assertRaises(bu.UpdateError):
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)

    def test_transport_failure_message(self):
        self.c.route("https://dist.torproject.org/a", exit=97, stderr="curl: (97) connection to proxy closed")
        with self.assertRaises(bu.TransportError) as c:
            self.f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertIn(bu.TOR_DOWN, str(c.exception))

    def test_cancel(self):
        import threading
        ev = threading.Event(); ev.set()
        slow = os.path.join(self.d, "slowcurl")
        with open(slow, "w") as f:
            f.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(slow, 0o755)
        f = bu.Fetcher("tor-browser", bu.Transport("tor"), cancel=ev, curl=slow, poll=0.05)
        with self.assertRaises(bu.Cancelled):
            f.fetch("https://dist.torproject.org/a", os.path.join(self.d, "a"), 100)
        self.assertFalse(os.path.exists(os.path.join(self.d, "a.part")))


@unittest.skipUnless(HAVE_GPG, "gpg missing")
class TestSignatures(Base):
    @classmethod
    def setUpClass(cls):
        cls.kd = tempfile.mkdtemp()
        cls.keys = T.Keys(cls.kd)
        cls.data = os.path.join(cls.kd, "data")
        with open(cls.data, "w") as f:
            f.write("payload\n")
        for k in ("good", "other", "expired"):
            cls.keys.detach(k, cls.data, os.path.join(cls.kd, k + ".sig"))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--homedir", cls.keys.home, "--kill", "all"], capture_output=True)
        shutil.rmtree(cls.kd, ignore_errors=True)

    def verify(self, sig, key="good", pin="good", data=None):
        return bu.gpg_verify("data", "tor-browser", self.d, sig=os.path.join(self.kd, sig + ".sig"),
                             data=data or self.data, keys=self.keys.keys_for("tor-browser", key, pin))

    def test_good(self):
        st = self.verify("good")
        self.assertIn("VALIDSIG", st)
        self.assertEqual(os.listdir(self.d), [], "the throw-away GNUPGHOME is removed")

    def test_policy_is_called(self):
        calls = []
        real = bu.sigstatus_ok

        def spy(*a, **kw):
            calls.append(a); return real(*a, **kw)
        bu.sigstatus_ok = spy
        try:
            self.verify("good")
        finally:
            bu.sigstatus_ok = real
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], self.keys.fpr["good"])

    def test_tampered(self):
        bad = os.path.join(self.d, "bad")
        with open(bad, "w") as f:
            f.write("payload!\n")
        with self.assertRaises(bu.SignatureError):
            self.verify("good", data=bad)

    def test_wrong_key(self):
        # a good signature by a key that is not the pinned one (even when that key file is given)
        with self.assertRaises(bu.SignatureError) as c:
            self.verify("other", key="other", pin="good")
        self.assertNotIsInstance(c.exception, bu.KeyExpiredError)
        with self.assertRaises(bu.SignatureError):
            self.verify("other", key="good", pin="good")

    def test_expired_key_message(self):
        with self.assertRaises(bu.KeyExpiredError) as c:
            self.verify("expired", key="expired", pin="expired")
        self.assertIn(bu.KEY_EXPIRED_TEXT, str(c.exception))
        self.assertEqual(bu.KEY_EXPIRED_TEXT, "key expired, use a newer ISO")

    def test_empty_pin_refused(self):
        with self.assertRaises(ValueError):
            bu.sigstatus_ok("x", "[GNUPG:] GOODSIG A b\n[GNUPG:] VALIDSIG A", "")

    def test_status_fixtures_agree_with_sigcheck(self):
        F = "A" * 40
        cases = [
            ("[GNUPG:] GOODSIG X u\n[GNUPG:] VALIDSIG %s 2026 0 4 0 1 10 00 %s" % ("B" * 40, F), True, None),
            ("[GNUPG:] EXPKEYSIG X u\n[GNUPG:] VALIDSIG %s 2026 0 4 0 1 10 00 %s" % ("B" * 40, F), False,
             bu.KeyExpiredError),
            ("[GNUPG:] GOODSIG X u\n[GNUPG:] EXPSIG X\n[GNUPG:] VALIDSIG B 2026 %s" % F, False, bu.KeyExpiredError),
            ("[GNUPG:] REVKEYSIG X u\n[GNUPG:] VALIDSIG B %s" % F, False, bu.SignatureError),
            ("[GNUPG:] BADSIG X u", False, bu.SignatureError),
            ("[GNUPG:] VALIDSIG B %s" % F, False, bu.SignatureError),
            ("[GNUPG:] GOODSIG X u\n[GNUPG:] VALIDSIG %s 2026 0 4 0 1 10 00 %s" % ("B" * 40, "C" * 40), False,
             bu.SignatureError),
            ("[GNUPG:] KEYEXPIRED 1\n[GNUPG:] GOODSIG X u\n[GNUPG:] VALIDSIG B 2026 0 4 0 1 10 00 %s" % F, True, None),
        ]
        for st, ok, exc in cases:
            r, msg = bu.sigstatus_ok("t", st, F)
            self.assertEqual(r, ok, st)
            if not ok:
                e = bu.sig_failure(st, msg)
                self.assertIs(type(e), exc, st)
        self.assertNotIsInstance(bu.sig_failure("[GNUPG:] REVKEYSIG X\n[GNUPG:] EXPKEYSIG X", "m"),
                                 bu.KeyExpiredError)

    def test_real_librewolf_inrelease(self):
        """LibreWolf's real InRelease (2026-11-04) against the key shipped in the image."""
        out = os.path.join(self.d, "Release")
        work = tempfile.mkdtemp(dir=self.d)
        bu.gpg_verify("InRelease", "librewolf", work, clearsigned=os.path.join(T.FIX, "librewolf-InRelease"),
                      out=out, keys={"librewolf": (os.path.join(T.INC, "usr/share/keyrings/librewolf.gpg"),
                                                   bu.KEYS["librewolf"][1])})
        _, sums = bu.parse_release(open(out).read(), now=datetime(2026, 11, 9, tzinfo=timezone.utc))
        bu.check_packages(sums, open(os.path.join(T.FIX, "librewolf-Packages"), "rb").read())
        best = bu.lw_latest(bu.parse_packages(open(os.path.join(T.FIX, "librewolf-Packages")).read()))
        self.assertEqual(best["Version"], "159.0.1-1")
        self.assertEqual(best["Filename"], "pool/librewolf-159.0.1-1-linux-x86_64-deb.deb")


class TestMetadata(Base):
    def test_tor_json(self):
        self.assertEqual(bu.parse_tb_json(open(os.path.join(T.FIX, "tor-download-linux-x86_64.json")).read()), "16.0")
        j = json.load(open(os.path.join(T.FIX, "tor-download-linux-x86_64.json")))
        for k, v in (("binary", "https://evil.example/tor.tar.xz"), ("version", "16.0a1"), ("version", "16.0"),
                     ("sig", "https://dist.torproject.org/x.asc")):
            jj = dict(j); jj[k] = v
            if k == "version" and v == "16.0":
                jj["binary"] = jj["binary"].replace("16.0", "16.1")   # version and URL disagree
            with self.assertRaises(bu.UpdateError):
                bu.parse_tb_json(json.dumps(jj))

    def test_changelog_regex_real_fixture(self):
        self.assertEqual(bu.tb_changelog_version(T.CHANGELOG), "16.0")
        self.assertEqual(bu.tb_changelog_version("\n\nTor Browser 15.0.26 -- foo"), "15.0.26")
        self.assertIsNone(bu.tb_changelog_version("Firefox 140.0\n"))

    def test_ff_json(self):
        self.assertEqual(bu.parse_ff_json('{"LATEST_FIREFOX_VERSION": "159.0.1"}'), "159.0.1")
        for v in ("161.0b1", "153.6.0esr", "162.0a1", ""):
            with self.assertRaises(bu.UpdateError):
                bu.parse_ff_json(json.dumps({"LATEST_FIREFOX_VERSION": v}))

    def test_ff_sums(self):
        sums = "%s  linux-x86_64/en-US/firefox-159.0.1.tar.xz\n%s  linux-i686/en-US/firefox-159.0.1.tar.xz\n" % ("a" * 64, "b" * 64)
        bu.ff_check_sums(sums, "a" * 64, "159.0.1")
        for sha, v in (("b" * 64, "159.0.1"), ("c" * 64, "159.0.1"), ("a" * 64, "159.0.2")):
            with self.assertRaises(bu.SignatureError):
                bu.ff_check_sums(sums, sha, v)

    def test_release_and_packages(self):
        pk = b"Package: librewolf\nVersion: 1-1\n"
        rel = ("Suite: librewolf\nValid-Until: Tue, 31 Jul 2029 00:59:21 +0000\nSHA256:\n %s %d main/binary-amd64/Packages\n"
               % (hashlib.sha256(pk).hexdigest(), len(pk)))
        _, sums = bu.parse_release(rel)
        bu.check_packages(sums, pk)
        with self.assertRaises(bu.SignatureError):
            bu.check_packages(sums, pk + b"x")
        with self.assertRaises(bu.SignatureError):
            bu.parse_release(rel, now=datetime(2030, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(bu.SignatureError):
            bu.parse_release(rel.replace("librewolf", "other"))
        with self.assertRaises(bu.SignatureError):
            bu.check_packages({}, pk)

    def test_clearsigned_shape(self):
        good = open(os.path.join(T.FIX, "librewolf-InRelease"), "rb").read()
        bu.check_clearsigned_shape(good)
        for bad in (b"junk\n" + good, good + b"\nOrigin: evil\n", good + good):
            with self.assertRaises(bu.SignatureError):
                bu.check_clearsigned_shape(bad)

    def test_lw_candidates_filter(self):
        st = bu.parse_packages(open(os.path.join(T.FIX, "librewolf-Packages")).read())
        st.append(dict(st[0], Version="999-1", Filename="pool/../../evil.deb"))
        st.append(dict(st[0], Version="998-1", Architecture="arm64"))
        st.append(dict(st[0], Version="997-1", Package="librewolf-evil"))
        self.assertEqual(bu.lw_latest(st)["Version"], "159.0.1-1")


class TestVersions(Base):
    def test_moz(self):
        self.assertEqual(bu.moz_cmp("16.0", "15.0.26"), 1)
        self.assertEqual(bu.moz_cmp("15.0.26", "16.0"), -1)
        self.assertEqual(bu.moz_cmp("16.0", "16.0.0"), 0)
        self.assertEqual(bu.moz_cmp("16.0.10", "16.0.9"), 1)
        for bad in ("16", "16.0a1", "1.2.3.4.5", "", None):
            with self.assertRaises(bu.VersionError):
                bu.moz_key(bad)

    @unittest.skipUnless(T.have("dpkg"), "dpkg missing")
    def test_deb(self):
        self.assertEqual(bu.deb_cmp("159.0.1-1", "157.0.1-1", "dpkg"), 1)
        self.assertEqual(bu.deb_cmp("157.0.1-1", "157.0.1-2", "dpkg"), -1)
        self.assertEqual(bu.deb_cmp("157.0.1-1", "157.0.1-1", "dpkg"), 0)
        self.assertEqual(bu.deb_cmp("1:1.0-1", "157.0-1", "dpkg"), 1)
        with self.assertRaises(bu.VersionError):
            bu.deb_cmp("1.0; rm -rf /", "1", "dpkg")
        self.assertEqual(bu.deb_upstream("159.0.1-1"), "159.0.1")

    def tree(self, name, v):
        r = os.path.join(self.d, name)
        if name == "tor-browser":
            p = os.path.join(r, "Browser/TorBrowser/Docs"); os.makedirs(p)
            open(os.path.join(p, "ChangeLog.txt"), "w").write(T.changelog_for(v))
            open(os.path.join(r, "Browser/application.ini"), "w").write("[App]\nVersion=140.5.0\n")
        else:
            os.makedirs(r); open(os.path.join(r, "application.ini"), "w").write("[App]\nVersion=%s\n" % v)
        return r

    def test_installed_tor(self):
        r = self.tree("tor-browser", "15.0.26")
        sd = os.path.join(self.d, "stamps"); os.makedirs(sd)
        i = bu.installed_version("tor-browser", root=r, stamp_dir=sd)
        self.assertEqual((i["version"], i["updated"]), ("15.0.26", False))
        self.assertEqual(bu.compare_candidate("tor-browser", "16.0", i), 1)
        self.assertEqual(bu.compare_candidate("tor-browser", "15.0.26", i), 0)
        self.assertEqual(bu.compare_candidate("tor-browser", "15.0.25", i), -1)
        json.dump({"version": "15.0.26"}, open(os.path.join(sd, "tor-browser"), "w"))
        self.assertTrue(bu.installed_version("tor-browser", root=r, stamp_dir=sd)["updated"])

    @unittest.skipUnless(T.have("dpkg"), "dpkg missing")
    def test_installed_librewolf(self):
        r = self.tree("librewolf", "157.0.1")
        pl = os.path.join(self.d, "packages.txt"); open(pl, "w").write("librewolf\t157.0.1-1\n")
        sd = os.path.join(self.d, "stamps"); os.makedirs(sd)
        old = bu.DPKG; bu.DPKG = "dpkg"
        try:
            i = bu.installed_version("librewolf", root=r, stamp_dir=sd, packages_list=pl)
            self.assertEqual(i["full"], "157.0.1-1")
            self.assertEqual(bu.compare_candidate("librewolf", "157.0.1-2", i), 1)
            self.assertEqual(bu.compare_candidate("librewolf", "157.0.1-1", i), 0)
            self.assertEqual(bu.compare_candidate("librewolf", "156.0-1", i), -1)
            i = bu.installed_version("librewolf", root=r, stamp_dir=sd, packages_list=os.path.join(self.d, "none"))
            self.assertIsNone(i["full"])
            self.assertEqual(bu.compare_candidate("librewolf", "157.0.1-9", i), 0)
            with self.assertRaises(bu.VersionError):
                bu.compare_candidate("librewolf", "158.0-1", {"version": None})
        finally:
            bu.DPKG = old


class TestResources(Base):
    def test_cache_free(self):
        with self.assertRaises(bu.ResourceError):
            bu.check_resources("tor-browser", os.path.join(self.d, "c"), meminfo(self.d, 4000000),
                               FakeDU(699 * MiB))
        bu.check_resources("tor-browser", os.path.join(self.d, "c"), meminfo(self.d, 4000000), FakeDU(700 * MiB))
        self.assertEqual(os.stat(os.path.join(self.d, "c")).st_mode & 0o777, 0o700)

    def test_mem(self):
        c = os.path.join(self.d, "c")
        for kb, ok in ((1000 * 1024, False), (1023 * 1024, False), (1024 * 1024, True)):
            f = (lambda: bu.check_resources("tor-browser", c, meminfo(self.d, kb), FakeDU(800 * MiB)))
            if ok:
                f()
            else:
                self.assertRaises(bu.ResourceError, f)
        # LibreWolf: unpacked 480 MB + 512 MB reserve
        self.assertRaises(bu.ResourceError, bu.check_resources, "librewolf", c,
                          meminfo(self.d, (480 + 512) * 1024), FakeDU(800 * MiB))
        bu.check_resources("librewolf", c, meminfo(self.d, (480 + 513) * 1024 + 50000), FakeDU(800 * MiB))

    def test_refusal_before_curl(self):
        """prepare_update: a failed RAM or space check aborts before curl is invoked."""
        c = T.FakeCurl(self.d)
        tree = os.path.join(self.d, "tb")
        p = os.path.join(tree, "Browser/TorBrowser/Docs"); os.makedirs(p)
        open(os.path.join(p, "ChangeLog.txt"), "w").write(T.changelog_for("15.0.26"))
        old = dict(bu.FACTORY)
        bu.FACTORY["tor-browser"] = tree
        try:
            for mi, du in ((meminfo(self.d, 900 * 1024), FakeDU(10000 * MiB)), (meminfo(self.d, 4000000), FakeDU(600 * MiB))):
                with self.assertRaises(bu.ResourceError):
                    bu.prepare_update("tor-browser", T.NoProbe("tor"), home=self.d,
                                      fetcher=bu.Fetcher("tor-browser", bu.Transport("tor"), curl=c.path),
                                      check=lambda n, d: bu.check_resources(n, d, mi, du))
            self.assertEqual(c.calls(), [])
        finally:
            bu.FACTORY.update(old)

    def test_ram_note(self):
        self.assertIn("RAM", bu.ram_note("tor-browser"))
        self.assertIn("380 MB", bu.ram_note("tor-browser"))


@unittest.skipUnless(HAVE_GPG and T.have("dpkg-deb") and T.have("dpkg"), "gpg/dpkg missing")
class TestPrepare(Base):
    """prepare_update end to end with a fake curl serving signed fixtures."""
    @classmethod
    def setUpClass(cls):
        cls.kd = tempfile.mkdtemp()
        cls.keys = T.Keys(cls.kd)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--homedir", cls.keys.home, "--kill", "all"], capture_output=True)
        shutil.rmtree(cls.kd, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.c = T.FakeCurl(self.d)
        self.oldkeys, self.oldfac, self.olddpkg = bu.KEYS, dict(bu.FACTORY), bu.DPKG
        bu.DPKG = "dpkg"

    def tearDown(self):
        bu.KEYS = self.oldkeys; bu.FACTORY.clear(); bu.FACTORY.update(self.oldfac); bu.DPKG = self.olddpkg
        super().tearDown()

    def run_prepare(self, name):
        f = bu.Fetcher(name, bu.Transport("tor"), curl=self.c.path, poll=0.05)
        return bu.prepare_update(name, T.NoProbe("tor"), home=self.d, fetcher=f, check=lambda n, d: None)

    def tor_setup(self, installed="15.0.26", latest="16.0", sigkey="good", pin="good"):
        tree = os.path.join(self.d, "tb")
        p = os.path.join(tree, "Browser/TorBrowser/Docs"); os.makedirs(p, exist_ok=True)
        open(os.path.join(p, "ChangeLog.txt"), "w").write(T.changelog_for(installed))
        bu.FACTORY["tor-browser"] = tree
        bu.KEYS = self.keys.keys_for("tor-browser", sigkey if sigkey != "expired" else "expired", pin)
        n, url, asc = bu.tb_urls(latest)
        tar = T.tor_tarball(os.path.join(self.kd, n), latest)
        self.keys.detach(sigkey, tar, tar + ".asc")
        self.c.route(bu.TB_JSON, body=json.dumps({"version": latest, "binary": url, "sig": asc}))
        self.c.route(url, body_file=tar)
        self.c.route(asc, body_file=tar + ".asc")
        return n

    def test_tor_staged(self):
        n = self.tor_setup()
        r = self.run_prepare("tor-browser")
        self.assertEqual(r["status"], "staged")
        s = bu.staging_dir("tor-browser", self.d)
        self.assertEqual(sorted(os.listdir(s)), sorted([n, n + ".asc", "meta.json"]))
        self.assertEqual(json.load(open(os.path.join(s, "meta.json")))["version"], "16.0")

    def test_tor_current_and_older(self):
        self.tor_setup(installed="16.0", latest="16.0")
        self.assertEqual(self.run_prepare("tor-browser")["status"], "current")
        self.assertEqual(len(self.c.calls()), 1, "already up to date: nothing downloaded")
        shutil.rmtree(os.path.join(self.d, "tb"))
        self.tor_setup(installed="16.0.1", latest="16.0")
        self.assertEqual(self.run_prepare("tor-browser")["status"], "older")

    def test_tor_bad_signature_cleans_staging(self):
        self.tor_setup(sigkey="other", pin="good")
        with self.assertRaises(bu.SignatureError):
            self.run_prepare("tor-browser")
        self.assertFalse(os.path.exists(bu.staging_dir("tor-browser", self.d)))

    def test_tor_expired_key(self):
        self.tor_setup(sigkey="expired", pin="expired")
        with self.assertRaises(bu.KeyExpiredError) as c:
            self.run_prepare("tor-browser")
        self.assertIn(bu.KEY_EXPIRED_TEXT, str(c.exception))

    def ff_setup(self, sums_key="good", listed=True):
        tree = os.path.join(self.d, "ff"); os.makedirs(tree, exist_ok=True)
        open(os.path.join(tree, "application.ini"), "w").write("[App]\nVersion=158.0\n")
        bu.FACTORY["firefox"] = tree
        bu.KEYS = self.keys.keys_for("firefox", sums_key, "good")
        v = "159.0.1"
        n, url, sums, sasc = bu.ff_urls(v)
        tar = os.path.join(self.kd, n)
        open(tar, "wb").write(b"firefox tarball")
        sha = hashlib.sha256(b"firefox tarball").hexdigest() if listed else "0" * 64
        sp = os.path.join(self.kd, "SHA256SUMS")
        open(sp, "w").write("%s  linux-x86_64/en-US/%s\n" % (sha, n))
        self.keys.detach(sums_key, sp, sp + ".asc")
        self.c.route(bu.FF_JSON, body='{"LATEST_FIREFOX_VERSION": "159.0.1"}')
        self.c.route(sums, body_file=sp); self.c.route(sasc, body_file=sp + ".asc"); self.c.route(url, body_file=tar)
        return url

    def test_ff_staged(self):
        self.ff_setup()
        self.assertEqual(self.run_prepare("firefox")["status"], "staged")

    def test_ff_sums_verified_before_tarball(self):
        url = self.ff_setup(sums_key="other")
        with self.assertRaises(bu.SignatureError):
            self.run_prepare("firefox")
        self.assertNotIn(url, [c["argv"][-1] for c in self.c.calls()], "tarball not fetched before SHA256SUMS")

    def test_ff_not_in_sums(self):
        self.ff_setup(listed=False)
        with self.assertRaises(bu.SignatureError):
            self.run_prepare("firefox")

    def lw_setup(self, tamper=False, key="good", debs=("158.0-1",)):
        tree = os.path.join(self.d, "lw"); os.makedirs(tree, exist_ok=True)
        open(os.path.join(tree, "application.ini"), "w").write("[App]\nVersion=157.0.1\n")
        bu.FACTORY["librewolf"] = tree
        bu.KEYS = self.keys.keys_for("librewolf", key, "good")
        rd = os.path.join(self.kd, "repo-" + "-".join(debs)); os.makedirs(rd, exist_ok=True)
        files = [T.lw_deb(rd, v) for v in debs]
        inr, pk = T.lw_repo(self.keys, rd, files, key=key, tamper=tamper)
        self.c.route(bu.LW_INRELEASE, body_file=inr)
        self.c.route(bu.LW_BASE + "dists/librewolf/" + bu.LW_PACKAGES, body_file=pk)
        for f in files:
            self.c.route(bu.LW_BASE + "pool/" + os.path.basename(f), body_file=f)

    def test_lw_staged(self):
        self.lw_setup(debs=("158.0-1", "158.0.1-1"))
        r = self.run_prepare("librewolf")
        self.assertEqual((r["status"], r["version"]), ("staged", "158.0.1-1"))
        self.assertEqual(sorted(os.listdir(bu.staging_dir("librewolf", self.d))),
                         ["InRelease", "Packages", "librewolf.deb", "meta.json"])

    def test_lw_packages_not_in_inrelease(self):
        self.lw_setup(tamper=True)
        with self.assertRaises(bu.SignatureError):
            self.run_prepare("librewolf")
        self.assertFalse(any(c["argv"][-1].endswith(".deb") for c in self.c.calls()))

    def test_lw_wrong_key(self):
        self.lw_setup(key="other")
        with self.assertRaises(bu.SignatureError):
            self.run_prepare("librewolf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
