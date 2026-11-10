#!/usr/bin/python3
"""Prestium 2.1: the Browser Updater's root helper (config/includes.chroot/usr/local/sbin/prestium-browser-install).

Unprivileged: the mount tests run the real helper code in a user + mount namespace (unshare -rm), on a
fake system tree in a temporary directory, with the real mount/umount: a real tmpfs at
<tmp>/run/prestium/browsers, real bind mounts over <tmp>/opt/tor-browser and the LibreWolf paths, and
the flags read back from /proc/self/mountinfo. Signatures use throw-away keys. This is not the live-VM
test (overlay root, real /proc, AppArmor); that must still be run before a release."""
import io, json, os, shutil, stat, subprocess, sys, tarfile, tempfile, textwrap, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_update_testlib as T  # noqa: E402
from browser_update_testlib import bu  # noqa: E402

HAVE_TOOLS = T.have("gpg") and T.have("dpkg-deb") and T.have("dpkg")
NS = T.unshare_ok() and HAVE_TOOLS
MiB = bu.MiB


class Unit(unittest.TestCase):
    def setUp(self):
        self.m = T.load_helper()
        self.d = tempfile.mkdtemp()
        self.m.STAGING_ROOT = os.path.join(self.d, "staging")
        os.makedirs(self.m.STAGING_ROOT)
        self.m.PY = sys.executable
        self.m.COPY_AS = []

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    # ---------------------------------------------------------------- argv / sudoers
    def test_argv(self):
        for a in ([], ["install"], ["install", "tor-browser", "x"], ["frob", "tor-browser"],
                  ["install", "/home/user/x.tar.xz"], ["install", "../tor-browser"], ["revert", "tor-browser;id"],
                  ["--file", "/x"], ["install", "chromium"]):
            buf = io.StringIO()
            sys_stdout, sys.stdout = sys.stdout, buf
            try:
                rc = self.m.main(["prestium-browser-install"] + a)
            finally:
                sys.stdout = sys_stdout
            self.assertEqual(rc, 2, a)
            self.assertFalse(json.loads(buf.getvalue().splitlines()[-1])["ok"])

    def test_sudoers(self):
        p = os.path.join(T.INC, "etc/sudoers.d/prestium-browser-updater")
        rules = [l for l in open(p) if l.strip() and not l.startswith("#")]
        self.assertEqual(len(rules), 1)
        who, cmds = rules[0].split("NOPASSWD:", 1)
        self.assertEqual(who.split(), ["user", "ALL=(root)"])
        cmds = [c.strip() for c in cmds.split(",")]
        H = "/usr/local/sbin/prestium-browser-install"
        self.assertEqual(sorted(cmds), sorted("%s %s %s" % (H, c, b) for c in ("install", "revert")
                                              for b in ("tor-browser", "librewolf")))
        for c in cmds:
            self.assertNotIn("*", c); self.assertNotIn("firefox", c)
            self.assertNotEqual(c, H)
        perms = open(os.path.join(T.INC, "usr/share/prestium/build/perms.txt")).read().splitlines()
        for line in ("0440 root root /etc/sudoers.d/prestium-browser-updater",
                     "0755 root root /usr/local/sbin/prestium-browser-install",
                     "0755 root root /var/lib/prestium/browser-updates",
                     "0644 root root /usr/share/prestium/keys/torbrowser.asc",
                     "0755 root root /usr/share/prestium/opt-overlay"):
            self.assertIn(line, perms)
        if shutil.which("visudo"):
            r = subprocess.run(["visudo", "-c", "-f", p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ---------------------------------------------------------------- staging copy (as the user)
    def test_staging_paths(self):
        S = self.m.STAGING_ROOT
        for bad in (S + "/../x", "staging/tor-browser/x", "/tmp/x", S + "/a\nb", S + "/a//b", S + "/./a", S):
            with self.assertRaises(self.m.Fail):
                self.m.check_staging_path(bad)
        self.m.check_staging_path(S + "/tor-browser/x.tar.xz")

    def test_copy_as_user(self):
        S = os.path.join(self.m.STAGING_ROOT, "tor-browser"); os.makedirs(S)
        w = os.path.join(self.d, "work"); os.makedirs(w)
        open(os.path.join(S, "f"), "w").write("data")
        self.m.copy_as_user(os.path.join(S, "f"), os.path.join(w, "f"), 100)
        self.assertEqual(open(os.path.join(w, "f")).read(), "data")
        secret = os.path.join(self.d, "secret"); open(secret, "w").write("s")
        os.symlink(secret, os.path.join(S, "link"))
        os.mkdir(os.path.join(S, "dir"))
        os.mkfifo(os.path.join(S, "fifo"))
        open(os.path.join(S, "big"), "w").write("x" * 101)
        for n in ("link", "dir", "fifo", "big", "missing"):
            with self.assertRaises(self.m.Fail, msg=n):
                self.m.copy_as_user(os.path.join(S, n), os.path.join(w, n), 100)
            self.assertFalse(os.path.exists(os.path.join(w, n)), n)
        with self.assertRaises(self.m.Fail):
            self.m.copy_as_user(secret, os.path.join(w, "s"), 100)        # outside the staging dir

    def test_helper_ram_formula_matches_window(self):
        """ensure_tmpfs refuses below bu.helper_mem_needed and goes ahead at it (the window's figure
        minus the downloads already in RAM)."""
        art = 120 * bu.MiB
        need = bu.helper_mem_needed("tor-browser", art)
        mem = os.path.join(self.d, "meminfo")
        self.m.MOUNT = os.path.join(self.d, "mnt"); os.makedirs(self.m.MOUNT)
        self.m.tmpfs_entry = lambda ms=None: None
        calls = []

        def fake_mount(a):
            calls.append(a); raise self.m.MountError("stop")
        self.m.do_mount = fake_mount
        self.m.MEMINFO = mem
        lst = os.lstat
        os_lstat = lambda p, *a, **k: os.stat_result((0o40755, 0, 0, 0, 0, 0, 0, 0, 0, 0)) if p == self.m.MOUNT else lst(p, *a, **k)
        with mock.patch.object(self.m.os, "lstat", os_lstat):
            open(mem, "w").write("MemAvailable: %d kB\n" % (need // 1024 - 1))
            with self.assertRaises(self.m.Fail) as e:
                self.m.ensure_tmpfs(bu.tmpfs_need("tor-browser", art))
            self.assertIn("RAM", str(e.exception)); self.assertEqual(calls, [])
            open(mem, "w").write("MemAvailable: %d kB\n" % (need // 1024))
            with self.assertRaises(self.m.MountError):
                self.m.ensure_tmpfs(bu.tmpfs_need("tor-browser", art))
            self.assertEqual(len(calls), 1)

    def test_helper_never_reads_bytecode(self):
        self.assertTrue(self.m.sys.dont_write_bytecode)
        self.assertEqual(self.m.sys.pycache_prefix, "/nonexistent/prestium-pycache")
        src = open(T.HELPER).read()
        self.assertLess(src.index("sys.pycache_prefix"), src.index("import browser_update"))

    def test_lister_reports_sizes(self):
        S = os.path.join(self.m.STAGING_ROOT, "tor-browser"); os.makedirs(S)
        open(os.path.join(S, "a.tar.xz"), "wb").write(b"x" * 1234)
        open(os.path.join(S, "a.tar.xz.asc"), "wb").write(b"y" * 10)
        files = self.m.list_as_user(S)
        self.assertEqual(files, {"a.tar.xz": 1234, "a.tar.xz.asc": 10})
        self.assertEqual(self.m.staged_sizes(files, ["a.tar.xz", "a.tar.xz.asc", "missing"]), 1244)

    def test_copy_never_opens_user_path_in_helper(self):
        """The helper process itself never opens the staged path (the copier subprocess does)."""
        import builtins
        S = os.path.join(self.m.STAGING_ROOT, "tor-browser"); os.makedirs(S)
        src = os.path.join(S, "f"); open(src, "w").write("data")
        w = os.path.join(self.d, "work"); os.makedirs(w)
        opened, real_open, real_osopen = [], builtins.open, os.open

        def spy_open(p, *a, **kw):
            opened.append(str(p)); return real_open(p, *a, **kw)

        def spy_osopen(p, *a, **kw):
            opened.append(str(p)); return real_osopen(p, *a, **kw)
        builtins.open, os.open = spy_open, spy_osopen
        try:
            self.m.copy_as_user(src, os.path.join(w, "f"), 100)
            self.m.list_as_user(S)
        finally:
            builtins.open, os.open = real_open, real_osopen
        self.assertNotIn(src, opened)
        self.assertFalse([p for p in opened if p.startswith(self.m.STAGING_ROOT)], opened)

    # ---------------------------------------------------------------- archives
    def tar(self, entries, top="tor-browser"):
        p = os.path.join(self.d, "t%d.tar.xz" % len(os.listdir(self.d)))
        with tarfile.open(p, "w:xz") as tf:
            T.add(tf, top, typ=tarfile.DIRTYPE, mode=0o755)
            for e in entries:
                T.add(tf, **e)
        with tarfile.open(p) as tf:
            return tf.getmembers()

    def test_copy_as_user_bounded(self):
        """2.1 audit: the copier runs as the user, who can hold its pipes open or flood stderr."""
        S = os.path.join(self.m.STAGING_ROOT, "tor-browser"); os.makedirs(S)
        w = os.path.join(self.d, "work"); os.makedirs(w)
        open(os.path.join(S, "f"), "w").write("data")
        self.m.COPY_TIMEOUT = 2
        self.m.COPIER = "import time; time.sleep(60)"
        with self.assertRaises(self.m.Fail) as c:
            self.m.copy_as_user(os.path.join(S, "f"), os.path.join(w, "hang"), 100)
        self.assertIn("too long", str(c.exception))
        self.assertFalse(os.path.exists(os.path.join(w, "hang")))
        self.m.COPY_TIMEOUT = 30
        self.m.COPIER = "import sys; sys.stderr.write('E' * (8 << 20)); sys.exit(1)"
        with self.assertRaises(self.m.Fail) as c:
            self.m.copy_as_user(os.path.join(S, "f"), os.path.join(w, "flood"), 100)
        self.assertLess(len(str(c.exception)), self.m.COPY_ERR_CAP + 200)

    def test_tar_rules(self):
        F = tarfile
        ok = [dict(name="tor-browser/a", data=b"x"), dict(name="tor-browser/l", typ=F.SYMTYPE, link="a"),
              dict(name="tor-browser/d", typ=F.DIRTYPE, mode=0o755),
              dict(name="tor-browser/d/l2", typ=F.SYMTYPE, link="../a")]
        self.m.check_tar(self.tar(ok), "tor-browser")
        bad = [
            [dict(name="tor-browser/../evil", data=b"x")],
            [dict(name="/etc/evil", data=b"x")],
            [dict(name="tor-browser/l", typ=F.SYMTYPE, link="../../etc/passwd")],
            [dict(name="tor-browser/l", typ=F.SYMTYPE, link="/etc/passwd")],
            [dict(name="tor-browser/l", typ=F.SYMTYPE, link="x/../../..")],
            [dict(name="tor-browser/dev", typ=F.CHRTYPE)],
            [dict(name="tor-browser/blk", typ=F.BLKTYPE)],
            [dict(name="tor-browser/fifo", typ=F.FIFOTYPE)],
            [dict(name="tor-browser/a", data=b"x"), dict(name="tor-browser/h", typ=F.LNKTYPE, link="tor-browser/a")],
            [dict(name="tor-browser/suid", data=b"x", mode=0o4755)],
            [dict(name="tor-browser/sgid", data=b"x", mode=0o2755)],
            # 2.1 audit: duplicates, owners other than root, group/world-writable entries
            [dict(name="tor-browser/l", typ=F.SYMTYPE, link="/etc"), dict(name="tor-browser/l", typ=F.SYMTYPE, link="a")],
            [dict(name="tor-browser/a", data=b"x"), dict(name="tor-browser/a", data=b"y")],
            [dict(name="tor-browser/u", data=b"x", uid=1000)],
            [dict(name="tor-browser/g", data=b"x", gid=1000)],
            [dict(name="tor-browser/w", data=b"x", mode=0o666)],
            [dict(name="tor-browser/gw", data=b"x", mode=0o664)],
            [dict(name="tor-browser/wd", typ=F.DIRTYPE, mode=0o777)],
            [dict(name="other/a", data=b"x")],
            [dict(name="tor-browser/l", typ=F.SYMTYPE, link="."), dict(name="tor-browser/l/x", data=b"x")],
            # chained symlinks that escape only after the second hop
            [dict(name="tor-browser/a", typ=F.SYMTYPE, link="b/.."), dict(name="tor-browser/b", typ=F.SYMTYPE, link=".."),
             dict(name="tor-browser/c", typ=F.SYMTYPE, link="a/../etc")],
        ]
        for b in bad:
            with self.assertRaises(self.m.Fail, msg=b):
                self.m.check_tar(self.tar(b), "tor-browser")
        with self.assertRaises(self.m.Fail):
            self.m.check_tar(self.tar([], top="firefox"), "tor-browser")

    def test_extract_names_the_directory_itself(self):
        self.m.MOUNT = self.d
        p = T.tor_tarball(os.path.join(self.d, "tb.tar.xz"), "16.0")
        tree = self.m.extract_tarball(p, os.path.join(self.d, "unpack"), "tor-browser")
        self.assertEqual(tree, os.path.join(self.d, "unpack", "tor-browser"))
        self.assertTrue(os.path.isfile(os.path.join(tree, "Browser/firefox.real")))
        self.assertFalse(os.path.exists(os.path.join(tree, "tor-browser")))
        self.assertEqual(bu.tree_version("tor-browser", tree), "16.0")

    def test_changelog_real_fixture(self):
        self.assertEqual(bu.tb_changelog_version(open(os.path.join(T.FIX, "tor-browser-16.0-ChangeLog.txt")).read()),
                         "16.0")

    @unittest.skipUnless(HAVE_TOOLS, "dpkg-deb missing")
    def test_deb_listing(self):
        deb = T.lw_deb(self.d, "158.0-1")
        r = subprocess.run(["dpkg-deb", "-c", deb], capture_output=True, text=True)
        listing, total = self.m.parse_deb_listing(r.stdout)
        self.assertEqual(listing["usr/bin/librewolf"], ("l", "../share/librewolf/librewolf"))
        self.assertIn("etc/apparmor.d/librewolf", listing)
        # absolute symlink inside the allowed trees: accepted
        deb2 = T.lw_deb(os.path.join(self.d), "158.0-2",
                        extra_files=[("usr/share/librewolf/abs", "/usr/lib/librewolf/libfoo.so")])
        self.m.parse_deb_listing(subprocess.run(["dpkg-deb", "-c", deb2], capture_output=True, text=True).stdout)
        for target in ("/etc/shadow", "/usr/local/bin/x", "../../../../etc/passwd", "../../bin/sh"):
            d = os.path.join(self.d, "bad%d" % abs(hash(target)))
            os.makedirs(d)
            deb3 = T.lw_deb(d, "158.0-3", extra_files=[("usr/share/librewolf/evil", target)])
            with self.assertRaises(self.m.Fail, msg=target):
                self.m.parse_deb_listing(subprocess.run(["dpkg-deb", "-c", deb3], capture_output=True, text=True).stdout)

    def test_deb_listing_special_files(self):
        L = "%s 0/0 %s 2026-10-08 00:03 %s"
        good = [L % ("drwxr-xr-x", "0", "./"), L % ("drwxr-xr-x", "0", "./usr/"),
                L % ("-rwxr-xr-x", "5", "./usr/share/librewolf/librewolf")]
        self.m.parse_deb_listing("\n".join(good))
        for line in (L % ("crw-r--r--", "1,3", "./usr/share/librewolf/null"),
                     L % ("brw-r--r--", "8,0", "./usr/share/librewolf/sda"),
                     L % ("prw-r--r--", "0", "./usr/share/librewolf/fifo"),
                     L % ("hrw-r--r--", "0", "./usr/share/librewolf/h link to ./usr/share/librewolf/librewolf"),
                     L % ("-rwsr-xr-x", "5", "./usr/share/librewolf/suid"),
                     L % ("-rwxr-sr-x", "5", "./usr/share/librewolf/sgid"),
                     L % ("-rwxr-xr-x", "5", "./usr/share/librewolf/../../../etc/x"),
                     L % ("-rwxr-xr-x", "5", "/etc/x"),
                     L % ("lrwxrwxrwx", "0", "./usr/share/librewolf/l -> /etc"),
                     L % ("-rwxr-xr-x", "5", "./usr/share/librewolf/a -> b"),
                     # 2.1 audit
                     L % ("-rwxr-xr-x", "5", "./usr/share/librewolf/librewolf"),             # listed twice
                     L % ("-rw-rw-r--", "5", "./usr/share/librewolf/gw"),
                     L % ("drwxrwxrwx", "0", "./usr/share/librewolf/wd/"),
                     "-rwxr-xr-x 1000/1000 5 2026-10-08 00:03 ./usr/share/librewolf/user-owned",
                     "garbage line"):
            with self.assertRaises(self.m.Fail, msg=line):
                self.m.parse_deb_listing("\n".join(good + [line]))

    def test_walk_check_listing_mismatch(self):
        r = os.path.join(self.d, "u"); os.makedirs(os.path.join(r, "usr/share/librewolf"))
        open(os.path.join(r, "usr/share/librewolf/a"), "w").close()
        exp = {"usr": ("d", None), "usr/share": ("d", None), "usr/share/librewolf": ("d", None),
               "usr/share/librewolf/a": ("-", None)}
        self.m.walk_check(r, self.m.lw_tree_ok, True, exp)
        open(os.path.join(r, "usr/share/librewolf/extra"), "w").close()
        with self.assertRaises(self.m.Fail):
            self.m.walk_check(r, self.m.lw_tree_ok, True, exp)

    # ---------------------------------------------------------------- apt simulation
    def fake_apt(self, out, rc=0):
        open(os.path.join(self.d, "apt.out"), "w").write(out)
        open(os.path.join(self.d, "apt.rc"), "w").write(str(rc))
        p = os.path.join(self.d, "fakeapt")
        open(p, "w").write(T.FAKE_APT % {"r": self.d})
        os.chmod(p, 0o755)
        self.m.APT_GET = p
        self.m.DPKG_DEB = shutil.which("dpkg-deb") or self.m.DPKG_DEB

    @unittest.skipUnless(HAVE_TOOLS, "dpkg-deb missing")
    def test_apt_inst_parsing(self):
        deb = T.lw_deb(self.d, "158.0-1")
        I = "Inst librewolf [157.0.1-1] (158.0-1 local-deb [amd64])\nConf librewolf (158.0-1 local-deb [amd64])\n"
        N = "N: Download is performed unsandboxed as root as file '%s' couldn't be accessed by user '_apt'.\n" % deb
        for out, rc, ok in ((I, 0, True), (N + I, 0, True), (I + "Inst libfoo (1 Debian:13 [amd64])\n", 0, False),
                            ("Inst libfoo (1 x [amd64])\n" + I, 0, False), ("", 0, False), ("Conf librewolf\n", 0, False),
                            (I + "E: Something\n", 0, False), (I, 100, False), (I + "Remv libbar [1]\n", 0, False),
                            (I + I, 0, False)):
            self.fake_apt(out, rc)
            if ok:
                self.assertEqual(self.m.apt_simulate(deb), "librewolf")
            else:
                with self.assertRaises(self.m.Fail, msg=out):
                    self.m.apt_simulate(deb)
        log = open(os.path.join(self.d, "apt.log")).read().splitlines()[-1]
        self.assertEqual(log, "-s --no-download install %s" % deb)
        env = open(os.path.join(self.d, "apt.env")).read()
        self.assertNotIn("proxy", env.lower())
        self.assertIn("HOME=/nonexistent", env)
        with self.assertRaises(self.m.Fail):
            self.m.apt_simulate("librewolf.deb")            # relative path

    @unittest.skipUnless(T.have("apt-get"), "apt-get missing")
    def test_apt_unmet_fixture_real(self):
        """The real apt-get refuses the fixture whose Depends is not installable (dpkg --dry-run -i
        accepts it, which is why it is not used)."""
        self.m.APT_GET = shutil.which("apt-get")
        self.m.DPKG_DEB = shutil.which("dpkg-deb")
        deb = os.path.join(self.d, "unmet.deb")
        shutil.copy(os.path.join(T.FIX, "unmet-depends.deb"), deb)
        with self.assertRaises(self.m.Fail) as c:
            self.m.apt_simulate(deb)
        self.assertIn("prestium-no-such-package", str(c.exception))
        dry = subprocess.run(["dpkg", "--dry-run", "-i", deb], capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, "dpkg --dry-run -i does not report the unmet dependency")

    # ---------------------------------------------------------------- running-process scan
    def scan_setup(self):
        self.m.PROC = os.path.join(self.d, "proc")
        tgt = os.path.join(self.d, "opt/tor-browser")
        os.makedirs(os.path.join(tgt, "Browser"))
        exe = os.path.join(tgt, "Browser/firefox.real"); open(exe, "w").write("x")
        self.m.MOUNT = os.path.join(self.d, "mnt"); os.makedirs(self.m.MOUNT)
        self.m.UNITS = {"tor-browser": [("tor-browser", tgt, "dir")]}
        self.m.STAMP_DIR = os.path.join(self.d, "stamps")
        return exe

    def proc(self, pid, target):
        p = os.path.join(self.m.PROC, str(pid)); os.makedirs(p, exist_ok=True)
        os.symlink(target, os.path.join(p, "exe"))

    def test_scan_by_inode(self):
        exe = self.scan_setup()
        os.makedirs(self.m.PROC)
        other = os.path.join(self.d, "elsewhere/firefox.real"); os.makedirs(os.path.dirname(other))
        os.link(exe, other)                                   # same inode, different path text
        copy = os.path.join(self.d, "copy/Browser/firefox.real"); os.makedirs(os.path.dirname(copy))
        shutil.copy(exe, copy)                                # same path tail, different inode
        self.proc(10, copy); self.proc(11, os.path.join(self.d, "gone"))
        os.makedirs(os.path.join(self.m.PROC, "self")); os.makedirs(os.path.join(self.m.PROC, "2"))
        self.assertEqual(self.m.running("tor-browser"), [])
        self.proc(12, other)
        self.assertEqual(self.m.running("tor-browser"), [12])
        with self.assertRaises(self.m.Fail) as c:
            self.m.refuse_if_running("tor-browser")
        self.assertEqual(c.exception.code, 3)

    def test_scan_permission_error_refuses(self):
        exe = self.scan_setup()
        os.makedirs(self.m.PROC)
        self.proc(20, exe)
        real = os.stat

        def deny(p, *a, **kw):
            if str(p).endswith("/20/exe"):
                raise PermissionError(13, "denied", p)
            return real(p, *a, **kw)
        os.stat = deny
        try:
            with self.assertRaises(self.m.Fail) as c:
                self.m.running("tor-browser")
            self.assertIn("cannot check", str(c.exception))
        finally:
            os.stat = real

        def deny_target(p, *a, **kw):
            if str(p) == exe:
                raise PermissionError(13, "denied", p)
            return real(p, *a, **kw)
        os.stat = deny_target
        try:
            with self.assertRaises(self.m.Fail):
                self.m.running("tor-browser")
        finally:
            os.stat = real

    def test_scan_vanishing_process(self):
        self.scan_setup()
        os.makedirs(self.m.PROC)
        real = os.stat

        def gone(p, *a, **kw):
            if str(p).endswith("/30/exe"):
                raise ProcessLookupError(3, "gone")
            return real(p, *a, **kw)
        self.proc(30, "/nonexistent")
        os.stat = gone
        try:
            self.assertEqual(self.m.running("tor-browser"), [])
        finally:
            os.stat = real

    def test_no_rmtree_of_factory_path(self):
        src = open(T.HELPER).read()
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        for bad in ('rmtree("/opt', "rmtree('/opt", "umount -l", '"-l"', '"--lazy"', '"--force"', '"dpkg"',
                    "DPKG,", '"--install"', "dpkg-divert", "update-alternatives", "apparmor_parser", "/var/lib/dpkg",
                    "upperdir", "/run/live/overlay", "noexec,"):
            self.assertFalse(bad in code, bad)
        self.assertIn("r = run([UMOUNT_BIN, target])", code)
        self.assertEqual(code.count("UMOUNT_BIN"), 2)


@unittest.skipUnless(NS, "needs unshare -rm (user+mount namespaces), gpg and dpkg-deb")
class Mounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kd = tempfile.mkdtemp()
        cls.keys = T.Keys(cls.kd)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--homedir", cls.keys.home, "--kill", "all"], capture_output=True)
        shutil.rmtree(cls.kd, ignore_errors=True)

    def setUp(self):
        self.R = tempfile.mkdtemp()
        T.make_root(self.R, self.keys)

    def tearDown(self):
        subprocess.run(["chmod", "-R", "u+w", self.R], capture_output=True)
        shutil.rmtree(self.R, ignore_errors=True)

    def ns(self, body):
        code = T.NS_PRE % {"tests": os.path.dirname(os.path.abspath(__file__))} + textwrap.dedent(body) + "\ndone()\n"
        r = subprocess.run(["unshare", "-rm", sys.executable, "-W", "ignore", "-c", code, self.R],
                           capture_output=True, text=True, timeout=600)
        res = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
        if r.returncode != 0 or not res:
            self.fail("namespace child failed (%d):\n%s\n%s" % (r.returncode, r.stdout[-4000:], r.stderr[-4000:]))
        return json.loads(res[-1][7:])

    def stage_tor(self, v, **kw):
        return T.stage_tor(self.R, self.keys, v, **kw)

    # ---------------------------------------------------------------- Tor Browser
    def test_tor_first_install(self):
        self.stage_tor("16.0")
        r = self.ns(r'''
        T_ = R + "/opt/tor-browser"
        rc, last, lines = call("install", "tor-browser")
        RES["rc1"], RES["last1"] = rc, last
        RES["ver1"] = tbver()
        RES["binds1"] = [sorted(e["opts"]) for e in binds(T_)]
        RES["tmpfs"] = [sorted(e["opts"]) + [e["fstype"]] for e in tmpfs()]
        RES["mounts1"] = MOUNTS[:]
        RES["packaged"] = os.path.exists(T_ + "/Browser/is-packaged-app")
        RES["nested"] = os.path.exists(T_ + "/tor-browser")
        RES["policies"] = open(T_ + "/Browser/distribution/policies.json").read()
        RES["ublock"] = os.path.exists(T_ + "/Browser/distribution/extensions/uBlock0@raymondhill.net.xpi")
        st = os.stat(T_ + "/Browser/firefox.real")
        RES["exe_mode"] = [st.st_uid, st.st_mode & 0o7777]
        bad = []
        for dp, dns, fns in os.walk(T_):
            for n in dns + fns:
                s = os.lstat(os.path.join(dp, n))
                if not (s.st_mode & 0o170000 == 0o120000) and (s.st_mode & 0o6022 or s.st_uid != 0):
                    bad.append(n)
        RES["badperm"] = bad
        RES["stamp"] = json.load(open(m.STAMP_DIR + "/tor-browser"))
        RES["exec_ok"] = os.access(T_ + "/Browser/firefox.real", os.X_OK)
        RES["run_out"] = __import__("subprocess").run([T_ + "/Browser/firefox.real"], capture_output=True, text=True).stdout
        ''')
        self.assertEqual(r["rc1"], 0, r["last1"])
        self.assertTrue(r["last1"]["ok"])
        self.assertEqual(r["ver1"], "16.0")
        self.assertEqual(len(r["binds1"]), 1, "exactly one bind on the factory path")
        for o in ("ro", "nosuid", "nodev"):
            self.assertIn(o, r["binds1"][0])
        self.assertNotIn("noexec", r["binds1"][0])
        self.assertEqual(r["tmpfs"][0][-1], "tmpfs")
        self.assertNotIn("noexec", r["tmpfs"][0]); self.assertIn("nosuid", r["tmpfs"][0]); self.assertIn("nodev", r["tmpfs"][0])
        M = r["mounts1"]
        mnt = self.R + "/run/prestium/browsers"
        self.assertEqual(M[0][:3], ["-t", "tmpfs", "-o"])
        self.assertRegex(M[0][3], r"^mode=0755,exec,nosuid,nodev,size=[0-9]+M$")
        self.assertEqual(M[0][4:], ["tmpfs", mnt])
        self.assertIn(["--bind", mnt + "/tor-browser", self.R + "/opt/tor-browser"], M)
        self.assertIn(["-o", "remount,bind,ro,exec,nosuid,nodev", self.R + "/opt/tor-browser"], M)
        self.assertFalse([a for a in M if any("noexec" in x for x in a)])
        self.assertTrue(r["packaged"]); self.assertFalse(r["nested"])
        self.assertEqual(r["policies"], open(os.path.join(T.INC, "usr/share/prestium/opt-overlay/tor-browser/Browser/distribution/policies.json")).read())
        self.assertTrue(r["ublock"])
        self.assertEqual(r["exe_mode"], [0, 0o755])
        self.assertEqual(r["badperm"], [])
        self.assertEqual(r["stamp"]["version"], "16.0")
        self.assertRegex(r["stamp"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(r["exec_ok"])
        self.assertIn("tor-browser 16.0", r["run_out"], "the bind is exec: the new binary runs")

    def run_steps(self, steps):
        """steps: list of ("stage", v) | ("install"|"revert", name) | ("py", code). Stage steps are
        prepared in advance into numbered directories and moved into place inside the namespace."""
        prep = []
        body = ["T_ = R + '/opt/tor-browser'", "RES['steps'] = []", "import shutil"]
        for i, s in enumerate(steps):
            if s[0] == "stage":
                src = self.stage_tor(s[1], **(s[2] if len(s) > 2 else {}))
                d = os.path.dirname(src)
                keep = os.path.join(self.R, "stage%d" % i)
                shutil.move(d, keep)
                body.append("shutil.rmtree(m.STAGING_ROOT + '/tor-browser', ignore_errors=True); "
                            "shutil.copytree(%r, m.STAGING_ROOT + '/tor-browser')" % keep)
            elif s[0] == "stage-lw":
                T.stage_lw(self.R, self.keys, s[1], **(s[2] if len(s) > 2 else {}))
                keep = os.path.join(self.R, "stage%d" % i)
                shutil.move(os.path.join(self.R, "home/user/.cache/prestium/browser-updater/staging/librewolf"), keep)
                body.append("shutil.rmtree(m.STAGING_ROOT + '/librewolf', ignore_errors=True); "
                            "shutil.copytree(%r, m.STAGING_ROOT + '/librewolf')" % keep)
            elif s[0] in ("install", "revert"):
                body.append("rc, last, _ = call(%r, %r); RES['steps'].append([rc, last])" % (s[0], s[1]))
            else:
                body.append(textwrap.dedent(s[1]))
        return self.ns("\n".join(body))

    def state(self):
        return '''
RES.setdefault("state", []).append({"tb": tbver(), "lw": lwver(), "binds": {t[len(R):]: len(binds(t)) for t in (R + "/opt/tor-browser", R + "/usr/share/librewolf", R + "/usr/lib/librewolf", R + "/usr/bin/librewolf")},
  "tmpfs": len(tmpfs()), "src": sorted(os.listdir(m.MOUNT)) if tmpfs() else None,
  "stamp": sorted(os.listdir(m.STAMP_DIR))})
'''

    def test_tor_reupdate_rollback_reset(self):
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"), ("py", st),
            ("stage", "16.0.1"), ("install", "tor-browser"), ("py", st),
            # a failing confirmation after the bind of the next update: roll back to 16.0.1, not the factory
            ("stage", "16.0.2"),
            ("py", "_c = m.confirm\ndef bad(name, srcs, v=None):\n    if v == '16.0.2': raise m.MountError('injected')\n    return _c(name, srcs, v)\nm.confirm = bad"),
            ("install", "tor-browser"), ("py", st),
            # a failing remount: the same
            ("py", "m.confirm = _c\n_m2 = m.do_mount\n_once = [1]\ndef badm(a):\n    if a[:2] == ['-o', 'remount,bind,ro,exec,nosuid,nodev'] and _once:\n        _once.pop(); raise m.MountError('injected remount')\n    return _m2(a)\nm.do_mount = badm"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.do_mount = _m2"),
            # not newer: equal and older
            ("stage", "16.0.1"), ("install", "tor-browser"),
            ("stage", "16.0"), ("install", "tor-browser"),
            ("revert", "tor-browser"), ("py", st),
            ("revert", "tor-browser"),
        ])
        s, steps = r["state"], r["steps"]
        self.assertEqual(steps[0][0], 0, steps[0])
        self.assertEqual(s[0], {"tb": "16.0", "lw": "157.0.1", "binds": {"/opt/tor-browser": 1, "/usr/share/librewolf": 0,
                                "/usr/lib/librewolf": 0, "/usr/bin/librewolf": 0}, "tmpfs": 1,
                                "src": [".work", "tor-browser"], "stamp": ["tor-browser"]})
        self.assertEqual(steps[1][0], 0, steps[1])
        self.assertEqual((s[1]["tb"], s[1]["binds"]["/opt/tor-browser"], s[1]["src"]), ("16.0.1", 1, [".work", "tor-browser"]))
        self.assertEqual(steps[2][0], 1)
        self.assertIn("previous update of this session is still in place", steps[2][1]["error"])
        self.assertEqual((s[2]["tb"], s[2]["binds"]["/opt/tor-browser"]), ("16.0.1", 1), "not the factory 15.0.26")
        self.assertEqual(steps[3][0], 1)
        self.assertEqual((s[3]["tb"], s[3]["binds"]["/opt/tor-browser"], s[3]["src"]), ("16.0.1", 1, [".work", "tor-browser"]))
        self.assertEqual(steps[4][0], 4); self.assertIn("already installed", steps[4][1]["error"])
        self.assertEqual(steps[5][0], 4); self.assertIn("not downgrading", steps[5][1]["error"])
        self.assertEqual(steps[6][0], 0, steps[6])
        self.assertEqual(s[4], {"tb": "15.0.26", "lw": "157.0.1", "binds": {"/opt/tor-browser": 0, "/usr/share/librewolf": 0,
                                "/usr/lib/librewolf": 0, "/usr/bin/librewolf": 0}, "tmpfs": 0, "src": None, "stamp": []})
        self.assertEqual(steps[7][0], 0); self.assertTrue(steps[7][1].get("nothing"))

    def test_no_older_release_after_reset(self):
        """2.1 audit: Reset brings back the shipped copy, not the right to install a superseded release."""
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0.1"), ("install", "tor-browser"),
            ("revert", "tor-browser"), ("py", st),
            ("stage", "16.0"), ("install", "tor-browser"), ("py", st),
            ("stage", "16.0.1"), ("install", "tor-browser"), ("py", st),
        ])
        s, steps = r["state"], r["steps"]
        self.assertEqual(steps[0][0], 0, steps[0])
        self.assertEqual(steps[1][0], 0, steps[1])
        self.assertEqual(s[0]["tb"], "15.0.26")
        self.assertEqual(steps[2][0], 4, steps[2])
        self.assertIn("earlier in this session", steps[2][1]["error"])
        self.assertEqual(s[1]["tb"], "15.0.26")
        self.assertEqual(steps[3][0], 0, steps[3])          # the same release again is fine
        self.assertEqual(s[2]["tb"], "16.0.1")

    def test_perms_set_before_tree_is_visible(self):
        """2.1 audit: overlay and fix_perms run inside the root-only work directory."""
        r = self.run_steps([
            ("py", "_fp = m.fix_perms\nRES['fp'] = []\ndef rec(p):\n    RES['fp'].append(os.path.relpath(p, m.MOUNT)); return _fp(p)\nm.fix_perms = rec"),
            ("stage", "16.0.1"), ("install", "tor-browser"),
            ("py", "m.fix_perms = _fp"),
        ])
        self.assertEqual(r["steps"][0][0], 0, r["steps"][0])
        self.assertTrue(r["fp"], "fix_perms was called")
        for p in r["fp"]:
            self.assertTrue(p.startswith(".work/"), p)

    def test_rename_failure_rebinds_previous(self):
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("stage", "16.0.1"),
            ("py", "_ren = os.rename\n_once = [1]\ndef badren(a, b):\n    if str(a).endswith('tor-browser.next') and _once:\n        _once.pop(); raise OSError(5, 'injected rename')\n    return _ren(a, b)\nos.rename = badren"),
            ("install", "tor-browser"), ("py", st),
            ("py", "os.rename = _ren"),
            ("install", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[1][0], 1); self.assertIn("previous update of this session is still in place", S[1][1]["error"])
        self.assertEqual((s[0]["tb"], s[0]["binds"]["/opt/tor-browser"]), ("16.0", 1))
        self.assertEqual(S[2][0], 0, S[2]); self.assertEqual(s[1]["tb"], "16.0.1")

    def test_first_install_failure_leaves_factory(self):
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"),
            ("py", "_m2 = m.do_mount\ndef badm(a):\n    if a[:1] == ['--bind']: raise m.MountError('injected bind')\n    return _m2(a)\nm.do_mount = badm"),
            ("install", "tor-browser"), ("py", st)])
        self.assertEqual(r["steps"][0][0], 1)
        self.assertIn("shipped copy is still in place", r["steps"][0][1]["error"])
        self.assertEqual(r["state"][0]["tb"], "15.0.26")
        self.assertEqual(r["state"][0]["binds"]["/opt/tor-browser"], 0)
        self.assertEqual(r["state"][0]["tmpfs"], 0, "a failed first install releases the tmpfs")
        self.assertEqual(r["state"][0]["stamp"], [])

    def test_running_browser(self):
        st = self.state()
        proc = "os.makedirs(m.PROC + '/4242', exist_ok=True); os.path.lexists(m.PROC + '/4242/exe') and os.unlink(m.PROC + '/4242/exe'); os.symlink(%s, m.PROC + '/4242/exe')"
        r = self.run_steps([
            ("stage", "16.0"),
            ("py", proc % "T_ + '/Browser/firefox.real'"),         # factory Tor Browser running
            ("install", "tor-browser"), ("py", st),
            ("py", "import shutil; shutil.rmtree(m.PROC + '/4242', ignore_errors=True)"),
            # started after the first scan, before the bind (first install): nothing bound
            ("py", "_b = m.build_tarball_unit\ndef late(*a):\n    r = _b(*a)\n    " + (proc % "T_ + '/Browser/firefox.real'") + "\n    return r\nm.build_tarball_unit = late"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.build_tarball_unit = _b; shutil.rmtree(m.PROC + '/4242', ignore_errors=True)"),
            ("install", "tor-browser"), ("py", st),
            # re-update with the updated browser started mid-way: roll back to the session update
            ("stage", "16.0.1"),
            ("py", "def late2(*a):\n    r = _b(*a)\n    " + (proc % "T_ + '/Browser/firefox.real'") + "\n    return r\nm.build_tarball_unit = late2"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.build_tarball_unit = _b"),
            ("revert", "tor-browser"), ("py", st),          # still running: revert refused
            ("py", "shutil.rmtree(m.PROC + '/4242', ignore_errors=True)"),
            # busy without a matching exe (an open file): umount fails cleanly, no lazy unmount
            ("py", "fh = open(T_ + '/Browser/libxul.so')"),
            ("revert", "tor-browser"), ("py", st),
            ("py", "fh.close()"),
            ("revert", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[0][0], 3); self.assertIn("is running", S[0][1]["error"])
        self.assertEqual((s[0]["tb"], s[0]["tmpfs"]), ("15.0.26", 0))
        self.assertEqual(S[1][0], 3)
        self.assertEqual((s[1]["tb"], s[1]["binds"]["/opt/tor-browser"]), ("15.0.26", 0))
        self.assertEqual(S[2][0], 0, S[2]); self.assertEqual(s[2]["tb"], "16.0")
        self.assertEqual(S[3][0], 3)
        self.assertEqual((s[3]["tb"], s[3]["binds"]["/opt/tor-browser"]), ("16.0", 1))
        self.assertEqual(S[4][0], 3); self.assertEqual(s[4]["tb"], "16.0")
        self.assertEqual(S[5][0], 3, S[5]); self.assertIn("still in use", S[5][1]["error"])
        self.assertEqual((s[5]["tb"], s[5]["binds"]["/opt/tor-browser"]), ("16.0", 1))
        self.assertEqual(S[6][0], 0); self.assertEqual((s[6]["tb"], s[6]["tmpfs"]), ("15.0.26", 0))

    def test_resources_and_flags(self):
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"),
            ("py", "open(m.MEMINFO, 'w').write('MemAvailable: %d kB\\n' % (1200 * 1024))"),   # < need + 512 MB
            ("install", "tor-browser"), ("py", st),
            ("py", "open(m.MEMINFO, 'w').write('MemAvailable: %d kB\\n' % (16 * 1024 * 1024))"),
            ("py", "_du = m.shutil.disk_usage\nm.shutil.disk_usage = lambda p: type('d', (), {'free': 500 * 2**20})() if p == m.MOUNT else _du(p)"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.shutil.disk_usage = _du"),
            # a tmpfs that is already there but noexec (not ours to fix): refused
            ("py", "_mount('-t tmpfs -o mode=0755,noexec,nosuid,nodev,size=900M tmpfs'.split() + [m.MOUNT])"),
            ("install", "tor-browser"), ("py", st),
            ("py", "_umount(m.MOUNT)"),
            ("install", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[0][0], 1); self.assertIn("RAM", S[0][1]["error"]); self.assertEqual(s[0]["tmpfs"], 0)
        self.assertEqual(S[1][0], 1); self.assertIn("MB free", S[1][1]["error"])
        self.assertEqual((s[1]["tb"], s[1]["tmpfs"]), ("15.0.26", 0))
        self.assertEqual(S[2][0], 1); self.assertIn("exec,nosuid,nodev", S[2][1]["error"])
        self.assertEqual(s[2]["binds"]["/opt/tor-browser"], 0)
        self.assertEqual(S[3][0], 0, S[3]); self.assertEqual(s[3]["tb"], "16.0")

    def test_interrupted_earlier_run(self):
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            # simulate a crash between bind and remount: a second, read-write bind on top
            ("py", "_mount(['--bind', m.MOUNT + '/tor-browser', T_])"),
            ("stage", "16.0.1"), ("install", "tor-browser"), ("py", st),
            ("install", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[1][0], 1); self.assertIn("interrupted", S[1][1]["error"])
        self.assertEqual((s[0]["tb"], s[0]["binds"]["/opt/tor-browser"]), ("15.0.26", 0), "never stacked")
        self.assertEqual(S[2][0], 0, S[2]); self.assertEqual((s[1]["tb"], s[1]["binds"]["/opt/tor-browser"]), ("16.0.1", 1))

    def test_bad_archives_refused(self):
        st = self.state()

        def evil(p, v):
            with tarfile.open(p, "w:xz") as tf:
                T.add(tf, "tor-browser", typ=tarfile.DIRTYPE, mode=0o755)
                T.add(tf, "tor-browser/../evil", b"x")
        def nested(p, v):
            T.tor_tarball(p, v, top="firefox")
        r = self.run_steps([
            ("stage", "16.0", {"tar_fn": evil}), ("install", "tor-browser"), ("py", st),
            ("py", "RES['evil'] = os.path.exists(R + '/run/prestium/evil') or os.path.exists(R + '/evil')"),
            ("stage", "16.0", {"tar_fn": nested}), ("install", "tor-browser"), ("py", st),
            ("stage", "16.0", {"key": "other"}), ("install", "tor-browser"), ("py", st),
            # the staged tarball replaced by a symlink to a file elsewhere
            ("stage", "16.0"),
            ("py", "p = m.STAGING_ROOT + '/tor-browser/tor-browser-linux-x86_64-16.0.tar.xz'; os.rename(p, R + '/moved.tar.xz'); os.symlink(R + '/moved.tar.xz', p)"),
            ("install", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        for i in range(4):
            self.assertEqual(S[i][0], 1, S[i])
            self.assertEqual((s[i]["tb"], s[i]["binds"]["/opt/tor-browser"], s[i]["tmpfs"]), ("15.0.26", 0, 0))
        self.assertIn("unsafe archive member", S[0][1]["error"])
        self.assertIn("outside the single top-level directory", S[1][1]["error"])
        self.assertIn("Signature check failed", S[2][1]["error"])
        self.assertIn("cannot use the staged", S[3][1]["error"])
        self.assertFalse(r["evil"])

    # ---------------------------------------------------------------- LibreWolf
    def lw_state(self):
        return self.state() + '''
RES["state"][-1].update({"dist": sorted(os.listdir(R + "/usr/share/librewolf/distribution")),
  "policies": open(R + "/usr/share/librewolf/distribution/policies.json").read(),
  "lib": sorted(os.listdir(R + "/usr/lib/librewolf")) if os.path.isdir(R + "/usr/lib/librewolf") else None,
  "wrapper": os.readlink(R + "/usr/bin/librewolf") if os.path.islink(R + "/usr/bin/librewolf") else open(R + "/usr/bin/librewolf").read(),
  "apparmor": os.path.exists(R + "/etc/apparmor.d/librewolf"),
  "runs": [r for r in RUNS if "dpkg" in r[0] or "apt" in r[0]]})
del RUNS[:]
'''

    def apt_ok(self, version):
        open(os.path.join(self.R, "apt.out"), "w").write(
            "N: Download is performed unsandboxed as root\nInst librewolf [157.0.1-1] (%s local-deb [amd64])\n"
            "Conf librewolf (%s local-deb [amd64])\n" % (version, version))

    def test_librewolf_unit(self):
        st = self.lw_state()
        self.apt_ok("158.0-1")
        r = self.run_steps([
            ("stage-lw", "158.0-1"), ("install", "librewolf"), ("py", st),
            ("py", "_t = open(R + '/apt.out').read(); open(R + '/apt.out', 'w').write(_t.replace('158.0-1', '158.0.1-1'))"),
            ("stage-lw", "158.0.1-1"), ("install", "librewolf"), ("py", st),
            ("revert", "librewolf"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[0][0], 0, S[0])
        ov = os.path.join(T.INC, "usr/share/prestium/opt-overlay/librewolf/distribution")
        self.assertEqual(s[0]["lw"], "158.0")
        self.assertEqual(s[0]["dist"], sorted(os.listdir(ov)), "Prestium's sealed distribution/, nothing from the package")
        self.assertEqual(s[0]["policies"], open(os.path.join(ov, "policies.json")).read())
        self.assertEqual(s[0]["binds"], {"/opt/tor-browser": 0, "/usr/share/librewolf": 1, "/usr/lib/librewolf": 0,
                                         "/usr/bin/librewolf": 0}, "the symlink /usr/bin/librewolf is never mounted on")
        self.assertEqual(s[0]["wrapper"], "../share/librewolf/librewolf")
        self.assertFalse(s[0]["apparmor"])
        runs = s[0]["runs"]
        flat = [" ".join(x) for x in runs]
        self.assertFalse([x for x in flat if x.split()[0].endswith("dpkg") and ("-i" in x.split() or "--install" in x)], flat)
        ic = [i for i, x in enumerate(runs) if x[1:2] == ["-c"]]
        ix = [i for i, x in enumerate(runs) if x[1:2] == ["-x"]]
        ia = [i for i, x in enumerate(runs) if x[0].endswith("fakeapt")]
        self.assertTrue(ic and ix and ia and ia[0] < ic[0] < ix[0], flat)
        self.assertEqual(runs[ia[0]][1:4], ["-s", "--no-download", "install"])
        self.assertTrue(os.path.isabs(runs[ia[0]][4]))
        self.assertEqual(S[1][0], 0, S[1]); self.assertEqual((s[1]["lw"], s[1]["binds"]["/usr/share/librewolf"]), ("158.0.1", 1))
        self.assertEqual(S[2][0], 0, S[2])
        self.assertEqual((s[2]["lw"], s[2]["tmpfs"], s[2]["stamp"]), ("157.0.1", 0, []))
        self.assertEqual(s[2]["wrapper"], "../share/librewolf/librewolf")

    def test_librewolf_lib_and_wrapper(self):
        st = self.lw_state()
        self.apt_ok("158.0-1")
        swap = "_t = open(R + '/apt.out').read(); open(R + '/apt.out', 'w').write(_t.replace(%r, %r))"
        r = self.run_steps([
            # factory has /usr/lib/librewolf (old library) and a regular-file /usr/bin/librewolf
            ("py", "os.makedirs(R + '/usr/lib/librewolf'); open(R + '/usr/lib/librewolf/libold.so', 'w').write('old')\n"
                   "os.unlink(R + '/usr/bin/librewolf'); open(R + '/usr/bin/librewolf', 'w').write('factory wrapper')"),
            # 1: new package without lib, wrapper a file: hide the factory lib, bind the wrapper file
            ("stage-lw", "158.0-1", {"wrapper": "file"}), ("install", "librewolf"), ("py", st),
            # 2: with lib
            ("py", swap % ("158.0-1", "158.1-1")),
            ("stage-lw", "158.1-1", {"wrapper": "file", "lib": True}), ("install", "librewolf"), ("py", st),
            # 3: without lib again: the previous lib bind must not stay mixed in
            ("py", swap % ("158.1-1", "158.2-1")),
            ("stage-lw", "158.2-1", {"wrapper": "file"}), ("install", "librewolf"), ("py", st),
            # 4: with lib, but the wrapper bind fails: the whole previous unit (share, lib hide, wrapper) returns
            ("py", swap % ("158.2-1", "158.3-1")),
            ("stage-lw", "158.3-1", {"wrapper": "file", "lib": True}),
            ("py", "_m2 = m.do_mount\n_once = [1]\ndef badm(a):\n    if a[:1] == ['--bind'] and a[-1].endswith('/usr/bin/librewolf') and _once:\n        _once.pop(); raise m.MountError('injected')\n    return _m2(a)\nm.do_mount = badm"),
            ("install", "librewolf"), ("py", st),
            ("py", "m.do_mount = _m2"),
            # 5: a symlink wrapper in the package while the image's is a file: refused
            ("stage-lw", "158.3-1", {"lib": True}), ("install", "librewolf"), ("py", st),
            ("revert", "librewolf"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[0][0], 0, S[0])
        self.assertEqual(s[0]["binds"], {"/opt/tor-browser": 0, "/usr/share/librewolf": 1, "/usr/lib/librewolf": 1,
                                         "/usr/bin/librewolf": 1})
        self.assertEqual(s[0]["lib"], [], "factory lib hidden by an empty directory")
        self.assertIn("exec /usr/share/librewolf/librewolf", s[0]["wrapper"])
        self.assertEqual(S[1][0], 0, S[1]); self.assertEqual((s[1]["lw"], s[1]["lib"]), ("158.1", ["libfoo.so"]))
        self.assertEqual(S[2][0], 0, S[2]); self.assertEqual((s[2]["lw"], s[2]["lib"]), ("158.2", []))
        self.assertEqual(s[2]["binds"]["/usr/lib/librewolf"], 1)
        self.assertEqual(S[3][0], 1, S[3]); self.assertIn("previous update of this session is still in place", S[3][1]["error"])
        self.assertEqual((s[3]["lw"], s[3]["lib"]), ("158.2", []))
        self.assertEqual(s[3]["binds"], {"/opt/tor-browser": 0, "/usr/share/librewolf": 1, "/usr/lib/librewolf": 1,
                                         "/usr/bin/librewolf": 1})
        self.assertEqual(S[4][0], 1); self.assertIn("does not match this image's (a regular file)", S[4][1]["error"])
        self.assertEqual(S[5][0], 0, S[5])
        self.assertEqual((s[5]["lw"], s[5]["lib"], s[5]["wrapper"], s[5]["tmpfs"]), ("157.0.1", ["libold.so"], "factory wrapper", 0))

    def test_two_browsers_tmpfs_lifetime(self):
        st = self.lw_state()
        self.apt_ok("158.0-1")
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("stage-lw", "158.0-1"), ("install", "librewolf"), ("py", st),
            ("revert", "tor-browser"), ("py", st),
            ("revert", "librewolf"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual([x[0] for x in S], [0, 0, 0, 0], S)
        self.assertEqual((s[0]["tb"], s[0]["lw"], s[0]["tmpfs"]), ("16.0", "158.0", 1))
        self.assertEqual((s[1]["tb"], s[1]["lw"], s[1]["tmpfs"]), ("15.0.26", "158.0", 1), "another browser still bound")
        self.assertEqual((s[2]["tb"], s[2]["lw"], s[2]["tmpfs"]), ("15.0.26", "157.0.1", 0), "last reset frees the RAM")

    def test_librewolf_apt_refusal(self):
        st = self.lw_state()
        open(os.path.join(self.R, "apt.out"), "w").write(
            "Inst libnew (1 Debian [amd64])\nInst librewolf [157.0.1-1] (158.0-1 local-deb [amd64])\n")
        r = self.run_steps([("stage-lw", "158.0-1"), ("install", "librewolf"), ("py", st)])
        self.assertEqual(r["steps"][0][0], 1)
        self.assertIn("other package changes", r["steps"][0][1]["error"])
        self.assertEqual((r["state"][0]["lw"], r["state"][0]["tmpfs"]), ("157.0.1", 0))
        self.assertFalse([x for x in r["state"][0]["runs"] if x[1:2] == ["-x"]], "not unpacked")


    # ---------------------------------------------------------------- review fixes (2026-11-09)
    def test_bind_fail_and_indexerror_roll_back(self):
        """bind() raising Fail (tmpfs_entry) or a missing mountinfo line: the previous update is bound
        again, never left in .prev with the factory copy visible."""
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("stage", "16.0.1"),
            ("py", "_te = m.tmpfs_entry\n_arm = [0]\n_m2 = m.do_mount\n"
                   "def armm(a):\n    r = _m2(a)\n    if a[:1] == ['--bind'] and a[1].endswith('/tor-browser') and _arm[0] == 0: _arm[0] = 1\n    return r\n"
                   "def te(ms=None):\n    if _arm[0] == 1:\n        _arm[0] = 2; raise m.Fail('injected tmpfs_entry')\n    return _te(ms)\n"
                   "m.do_mount, m.tmpfs_entry = armm, te"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.tmpfs_entry = _te\n_ea = m.entries_at\n_arm2 = [0]\n"
                   "def armr(a):\n    r = _m2(a)\n    if a[:2] == ['-o', 'remount,bind,ro,exec,nosuid,nodev'] and _arm2[0] == 0: _arm2[0] = 1\n    return r\n"
                   "def ea(t, ms=None):\n    if t == T_ and _arm2[0] == 1:\n        _arm2[0] = 2; return []\n    return _ea(t, ms)\n"
                   "m.do_mount, m.entries_at = armr, ea"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.entries_at, m.do_mount = _ea, _m2"),
            ("install", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[1][0], 1, S[1]); self.assertIn("previous update of this session is still in place", S[1][1]["error"])
        self.assertEqual((s[0]["tb"], s[0]["binds"]["/opt/tor-browser"]), ("16.0", 1))
        self.assertEqual(S[2][0], 1, S[2]); self.assertIn("previous update of this session is still in place", S[2][1]["error"])
        self.assertEqual((s[1]["tb"], s[1]["binds"]["/opt/tor-browser"]), ("16.0", 1))
        self.assertEqual(S[3][0], 0, S[3]); self.assertEqual(s[2]["tb"], "16.0.1")

    def test_rollback_never_stacks(self):
        """The new bind cannot be removed (remount failed, then umount failed): rollback does not bind
        the previous unit on top of it; the next Reset clears everything."""
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("stage", "16.0.1"),
            ("py", "_m2, _u2 = m.do_mount, m.do_umount\n_fail = [0]\n"
                   "def badm(a):\n    if a[:2] == ['-o', 'remount,bind,ro,exec,nosuid,nodev'] and not _fail[0]:\n        _fail[0] = 2; raise m.MountError('injected remount')\n    return _m2(a)\n"
                   "def badu(t):\n    if t == T_ and _fail[0] > 0:\n        _fail[0] -= 1; raise m.MountError('injected busy')\n    return _u2(t)\n"
                   "m.do_mount, m.do_umount = badm, badu"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.do_mount, m.do_umount = _m2, _u2"),
            ("revert", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[1][0], 1, S[1])
        self.assertIn("was not mounted again", S[1][1]["error"])
        self.assertEqual(s[0]["binds"]["/opt/tor-browser"], 1, "no second bind stacked")
        self.assertEqual(S[2][0], 0, S[2])
        self.assertEqual((s[1]["tb"], s[1]["binds"]["/opt/tor-browser"], s[1]["tmpfs"]), ("15.0.26", 0, 0))

    def test_stamp_failure_after_publish(self):
        """The bind is up but the stamp cannot be written: success with a warning, a re-update is
        refused (fail closed: the factory facts are unknown), Reset works."""
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"),
            ("py", "_ws = m.write_stamp\ndef bad(*a, **k):\n    raise OSError(28, 'No space left on device')\nm.write_stamp = bad"),
            ("install", "tor-browser"), ("py", st),
            ("py", "m.write_stamp = _ws"),
            ("stage", "16.0.1"), ("install", "tor-browser"), ("py", st),
            ("revert", "tor-browser"), ("py", st),
        ])
        S, s = r["steps"], r["state"]
        self.assertEqual(S[0][0], 0, S[0]); self.assertTrue(S[0][1]["ok"])
        self.assertIn("could not be recorded", S[0][1]["message"]); self.assertIn("warning", S[0][1])
        self.assertEqual((s[0]["tb"], s[0]["binds"]["/opt/tor-browser"], s[0]["stamp"]), ("16.0", 1, []))
        self.assertEqual(S[1][0], 1); self.assertIn("record is missing", S[1][1]["error"])
        self.assertEqual(s[1]["tb"], "16.0")
        self.assertEqual(S[2][0], 0, S[2]); self.assertEqual((s[2]["tb"], s[2]["tmpfs"]), ("15.0.26", 0))

    def test_signals_shielded_during_swap(self):
        """SIGTERM between unmount and bind is held until the new unit is bound and stamped."""
        import signal as _s
        st = self.state()
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("stage", "16.0.1"),
            ("py", "import signal\nRES['sig'] = []\n"
                   "def h(n, f):\n    RES['sig'].append([tbver(), [sorted(e['opts']) for e in binds(T_)], sorted(os.listdir(m.STAMP_DIR)), json.load(open(m.STAMP_DIR + '/tor-browser'))['version']])\n"
                   "signal.signal(signal.SIGTERM, h)\n_u2 = m.do_umount\n_once = [1]\n"
                   "def ku(t):\n    r = _u2(t)\n    if t == T_ and _once:\n        _once.pop(); os.kill(os.getpid(), signal.SIGTERM)\n    return r\nm.do_umount = ku"),
            ("install", "tor-browser"), ("py", st),
        ])
        S = r["steps"]
        self.assertEqual(S[1][0], 0, S[1])
        self.assertEqual(len(r["sig"]), 1, "the signal was delivered once, after the swap")
        v, opts, stamps, sv = r["sig"][0]
        self.assertEqual((v, sv, stamps), ("16.0.1", "16.0.1", ["tor-browser"]))
        self.assertEqual(len(opts), 1); self.assertIn("ro", opts[0])

    def test_signals_shielded_during_reset(self):
        """SIGTERM right after Reset's unmount is held until the stamp is gone, the tmpfs is released
        and the result is printed."""
        r = self.run_steps([
            ("stage", "16.0"), ("install", "tor-browser"),
            ("py", "import signal, sys as _sy\nRES['sig'] = []\n"
                   "def h(n, f):\n    _sy.__stdout__.flush()\n    RES['sig'].append([tbver(), len(binds(T_)), sorted(os.listdir(m.STAMP_DIR)), len(tmpfs())])\n"
                   "signal.signal(signal.SIGTERM, h)\n_u2 = m.do_umount\n_once = [1]\n"
                   "def ku(t):\n    r = _u2(t)\n    if t == T_ and _once:\n        _once.pop(); os.kill(os.getpid(), signal.SIGTERM)\n    return r\nm.do_umount = ku"),
            ("revert", "tor-browser"),
        ])
        S = r["steps"]
        self.assertEqual(S[1][0], 0, S[1]); self.assertIn("is back", S[1][1]["message"])
        self.assertEqual(r["sig"], [["15.0.26", 0, [], 0]], "delivered once, after stamp removal and tmpfs release")

    def test_lw_tmpfs_grows_to_real_size(self):
        """The fixed LibreWolf estimate is too small: once the package listing is known the tmpfs is
        enlarged (remount) instead of failing with "Not enough space"."""
        st = self.lw_state()
        self.apt_ok("158.0-1")
        r = self.run_steps([
            ("py", "bu.UNPACKED['librewolf'] = 0; bu.SCRATCH = 0; bu.FREE_MIN = 0; m.FREE_MIN = 0; m.SCRATCH = 24 * bu.MiB"),
            ("stage-lw", "158.0-1"), ("install", "librewolf"), ("py", st),
            ("py", "RES['remounts'] = [a for a in MOUNTS if a[:1] == ['-o'] and a[1].startswith('remount,mode=')]"),
        ])
        self.assertEqual(r["steps"][0][0], 0, r["steps"][0])
        self.assertEqual(r["state"][0]["lw"], "158.0")
        self.assertTrue(r["remounts"], "the tmpfs was enlarged")


class Image(unittest.TestCase):
    def test_shipped_copies(self):
        import filecmp
        self.assertTrue(filecmp.cmp(T.SIGCHECK, os.path.join(T.LIB, "sigcheck.sh"), shallow=False))
        for k in ("torbrowser.asc", "mozilla.asc"):
            self.assertTrue(filecmp.cmp(os.path.join(T.ROOT, "thirdparty/keys", k),
                                        os.path.join(T.INC, "usr/share/prestium/keys", k), shallow=False), k)
        a = os.path.join(T.INC, "usr/share/librewolf/distribution")
        b = os.path.join(T.INC, "usr/share/prestium/opt-overlay/librewolf/distribution")
        cmp = filecmp.dircmp(a, b)

        def same(c):
            return not (c.left_only or c.right_only or c.diff_files or c.funny_files) and all(same(s) for s in c.subdirs.values())
        self.assertTrue(same(cmp), "the sealed LibreWolf overlay is a copy of usr/share/librewolf/distribution")

    @unittest.skipUnless(T.have("gpg"), "gpg missing")
    def test_pinned_fingerprints_in_shipped_keys(self):
        for b, (path, fpr) in bu.KEYS.items():
            p = os.path.join(T.INC, path.lstrip("/"))
            out = subprocess.run(["gpg", "--show-keys", "--with-colons", p], capture_output=True, text=True).stdout
            fprs = [l.split(":")[9] for l in out.splitlines() if l.startswith("fpr")]
            self.assertEqual(fprs[0] if fprs else None, fpr, b)

    def test_cleanup_keeps_opt_overlay(self):
        h = open(os.path.join(T.ROOT, "config/hooks/live/9990-prestium-cleanup.hook.chroot")).read()
        rm = [l for l in h.splitlines() if l.startswith("rm ")]
        self.assertFalse([l for l in rm if "opt-overlay" in l], rm)
        t = open(os.path.join(T.INC, "usr/lib/tmpfiles.d/prestium-safety.conf")).read()
        self.assertIn("d /run/prestium/browsers 0755 root root -", t)
        h4 = open(os.path.join(T.ROOT, "config/hooks/live/0400-prestium-system.hook.chroot")).read()
        self.assertIn("install -d -m 0755 -o root -g root /var/lib/prestium/browser-updates", h4)
        self.assertIn("\nVERSION=2.0\n", h4)

    def test_menu_and_desktop(self):
        menu = open(os.path.join(T.INC, "etc/xdg/labwc/menu.xml")).read()
        a = menu.index('label="Tor Connection Assistant"')
        b = menu.index('label="Browser Updater"')
        self.assertLess(a, b)
        between = menu[a:b]
        self.assertEqual(between.count("<item"), 1, "immediately after the Tor Connection Assistant")
        self.assertIn('command="prestium-run /usr/local/bin/prestium-browser-updater"', menu[b:b + 200])
        d = open(os.path.join(T.INC, "usr/share/applications/prestium-browser-updater.desktop")).read()
        for l in ("Name=Browser Updater", "Exec=/usr/local/bin/prestium-browser-updater", "Icon=system-software-update",
                  "StartupNotify=true", "Categories=Network;"):
            self.assertIn(l, d.splitlines())

    def test_gui_first_release_scope(self):
        src = open(T.GUI).read()
        self.assertIn("FIRST_RELEASE", src)
        self.assertNotIn('run_helper("install", "firefox"', src)
        self.assertEqual(bu.FIRST_RELEASE, ("tor-browser", "librewolf"))
        self.assertIn("Reset to shipped copy", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
