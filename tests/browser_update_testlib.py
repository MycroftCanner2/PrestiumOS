# Prestium 2.1: shared helpers for tests/test_browser_update.py and tests/test_browser_install.py
# (throw-away OpenPGP keys, a fake curl, fixture archives). No network, no root.
import sys as _sys
_sys.dont_write_bytecode = True   # no __pycache__ under config/includes.chroot (live-build would ship it)
import io, json, os, shutil, subprocess, sys, tarfile, tempfile, textwrap, importlib.machinery, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
INC = os.path.join(ROOT, "config", "includes.chroot")
LIB = os.path.join(INC, "usr", "local", "lib", "prestium")
HELPER = os.path.join(INC, "usr", "local", "sbin", "prestium-browser-install")
GUI = os.path.join(INC, "usr", "local", "bin", "prestium-browser-updater")
SIGCHECK = os.path.join(ROOT, "scripts", "sigcheck.sh")
FIX = os.path.join(HERE, "fixtures", "browser-update")

if LIB not in sys.path:
    sys.path.insert(0, LIB)
import browser_update as bu  # noqa: E402

bu.SIGCHECK = SIGCHECK


def load_helper():
    loader = importlib.machinery.SourceFileLoader("prestium_browser_install", HELPER)
    spec = importlib.util.spec_from_loader("prestium_browser_install", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def have(cmd):
    return shutil.which(cmd) is not None


class Keys:
    """Throw-away ed25519 keys: good, other (a valid key that is not the pinned one), expired."""
    def __init__(self, d):
        self.home = os.path.join(d, "gnupg")
        os.makedirs(self.home, mode=0o700)
        self.env = dict(os.environ, GNUPGHOME=self.home)
        self.fpr = {}
        self.pub = {}
        for name, fake, exp in (("good", None, "never"), ("other", None, "never"),
                                ("expired", "20200101T000000", "1y")):
            uid = "%s@prestium.invalid" % name
            self.gpg(["--quick-gen-key", uid, "ed25519", "sign", exp], fake)
            out = subprocess.run(["gpg", "--batch", "--with-colons", "--list-keys", uid], env=self.env,
                                 capture_output=True, text=True).stdout
            self.fpr[name] = [l.split(":")[9] for l in out.splitlines() if l.startswith("fpr")][0]
            self.pub[name] = os.path.join(d, name + ".asc")
            with open(self.pub[name], "wb") as f:
                f.write(subprocess.run(["gpg", "--batch", "--armor", "--export", self.fpr[name]],
                                       env=self.env, capture_output=True).stdout)

    def gpg(self, args, fake=None):
        cmd = ["gpg", "-q", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
        if fake:
            cmd += ["--faked-system-time", fake]
        r = subprocess.run(cmd + args, env=self.env, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode())
        return r

    def detach(self, key, data, out):
        if os.path.exists(out):
            os.unlink(out)
        fake = "20200601T000000" if key == "expired" else None
        self.gpg(["-u", self.fpr[key], "--armor", "--detach-sign", "-o", out, data], fake)

    def clearsign(self, key, data, out):
        fake = "20200601T000000" if key == "expired" else None
        self.gpg(["-u", self.fpr[key], "--clearsign", "-o", out, data], fake)

    def keys_for(self, browser, key="good", pin="good"):
        """A KEYS mapping: the browser's key file is `key`'s public key, pinned to `pin`'s fingerprint."""
        k = dict(bu.KEYS)
        k[browser] = (self.pub[key], self.fpr[pin])
        return k


CHANGELOG = open(os.path.join(FIX, "tor-browser-16.0-ChangeLog.txt")).read()


def changelog_for(v):
    # the real 16.0 ChangeLog with its version replaced (same first-line shape as the real file)
    return CHANGELOG.replace("Tor Browser 16.0 -", "Tor Browser %s -" % v, 1)


def add(tf, name, data=None, mode=0o644, typ=tarfile.REGTYPE, link="", uid=0, gid=0):
    ti = tarfile.TarInfo(name)
    ti.mode, ti.type, ti.linkname, ti.uid, ti.gid = mode, typ, link, uid, gid
    if data is not None:
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
    else:
        tf.addfile(ti)


def tor_tarball(path, v, top="tor-browser", extra=()):
    with tarfile.open(path, "w:xz") as tf:
        add(tf, top, typ=tarfile.DIRTYPE, mode=0o755)
        add(tf, top + "/Browser", typ=tarfile.DIRTYPE, mode=0o755)
        add(tf, top + "/Browser/firefox.real", b"#!/bin/sh\necho tor-browser %s\n" % v.encode(), 0o755)
        add(tf, top + "/Browser/libxul.so", b"lib", 0o755)
        add(tf, top + "/Browser/TorBrowser", typ=tarfile.DIRTYPE, mode=0o755)
        add(tf, top + "/Browser/TorBrowser/Docs", typ=tarfile.DIRTYPE, mode=0o755)
        add(tf, top + "/Browser/TorBrowser/Docs/ChangeLog.txt", changelog_for(v).encode())
        add(tf, top + "/Browser/distribution", typ=tarfile.DIRTYPE, mode=0o755)
        add(tf, top + "/Browser/distribution/policies.json", b'{"from": "tarball"}')
        add(tf, top + "/Browser/start-tor-browser", typ=tarfile.SYMTYPE, link="firefox.real")
        for e in extra:
            add(tf, *e[:1], **e[1])
    return path


def lw_deb(d, version, upstream=None, lib=False, wrapper="symlink", extra_files=(), depends="libc6"):
    """A librewolf-shaped .deb (Architecture amd64) built with dpkg-deb."""
    upstream = upstream or version.rsplit("-", 1)[0]
    r = os.path.join(d, "deb-" + version + ("-lib" if lib else "") + "-" + wrapper)
    shutil.rmtree(r, ignore_errors=True)
    os.makedirs(os.path.join(r, "DEBIAN"))
    with open(os.path.join(r, "DEBIAN", "control"), "w") as f:
        f.write("Package: librewolf\nVersion: %s\nArchitecture: amd64\nMaintainer: t <t@prestium.invalid>\n"
                "Depends: %s\nDescription: test package\n" % (version, depends))
    s = os.path.join(r, "usr/share/librewolf")
    os.makedirs(os.path.join(s, "distribution"))
    for n in ("librewolf", "librewolf-bin"):
        with open(os.path.join(s, n), "w") as f:
            f.write("#!/bin/sh\necho librewolf %s\n" % version)
        os.chmod(os.path.join(s, n), 0o755)
    with open(os.path.join(s, "application.ini"), "w") as f:
        f.write("[App]\nName=LibreWolf\nVersion=%s\n" % upstream)
    with open(os.path.join(s, "distribution", "policies.json"), "w") as f:
        f.write('{"from": "package"}')
    with open(os.path.join(s, "distribution", "package-only.txt"), "w") as f:
        f.write("must not survive")
    os.makedirs(os.path.join(r, "usr/bin"))
    if wrapper == "symlink":
        os.symlink("../share/librewolf/librewolf", os.path.join(r, "usr/bin/librewolf"))
    else:
        with open(os.path.join(r, "usr/bin/librewolf"), "w") as f:
            f.write("#!/bin/sh\nexec /usr/share/librewolf/librewolf \"$@\"\n")
        os.chmod(os.path.join(r, "usr/bin/librewolf"), 0o755)
    if lib:
        os.makedirs(os.path.join(r, "usr/lib/librewolf"))
        with open(os.path.join(r, "usr/lib/librewolf/libfoo.so"), "w") as f:
            f.write(version)
    os.makedirs(os.path.join(r, "etc/apparmor.d"))
    with open(os.path.join(r, "etc/apparmor.d/librewolf"), "w") as f:
        f.write("profile librewolf flags=(unconfined) {}\n")
    for rel, target in extra_files:
        p = os.path.join(r, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if target is None:
            open(p, "w").close()
        else:
            os.symlink(target, p)
    out = os.path.join(d, "librewolf_%s_amd64.deb" % version)
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zgzip", "-b", r, out], check=True,
                   capture_output=True)
    return out


def lw_repo(keys, d, debs, key="good", valid_until="Tue, 31 Jul 2029 00:59:21 +0000", tamper=False):
    """InRelease (clear-signed) + Packages for the given .debs; returns (inrelease, packages, stanzas)."""
    import hashlib
    stanzas = []
    for deb in debs:
        v = subprocess.run(["dpkg-deb", "-f", deb, "Version"], capture_output=True, text=True).stdout.strip()
        data = open(deb, "rb").read()
        stanzas.append("Package: librewolf\nVersion: %s\nArchitecture: amd64\nFilename: pool/%s\nSize: %d\n"
                       "SHA256: %s\n" % (v, os.path.basename(deb), len(data), hashlib.sha256(data).hexdigest()))
    packages = ("\n".join(stanzas)).encode()
    ph = hashlib.sha256(packages + (b"x" if tamper else b"")).hexdigest()
    rel = ("Origin: LibreWolf Software Repository\nSuite: librewolf\nCodename: librewolf\nComponents: main\n"
           "Architectures: amd64\nDate: Wed, 04 Nov 2026 00:59:21 +0000\n" +
           ("Valid-Until: %s\n" % valid_until if valid_until else "") +
           "SHA256:\n %s %d main/binary-amd64/Packages\n" % (ph, len(packages)))
    rp = os.path.join(d, "Release.txt")
    with open(rp, "w") as f:
        f.write(rel)
    inr = os.path.join(d, "InRelease")
    if os.path.exists(inr):
        os.unlink(inr)
    keys.clearsign(key, rp, inr)
    pk = os.path.join(d, "Packages")
    with open(pk, "wb") as f:
        f.write(packages)
    return inr, pk


FAKE_CURL = r'''#!%(py)s
# fake curl: answers from $HOME/fakecurl.json, logs every invocation (argv and env) to $HOME/fakecurl.log
import json, os, sys
home = os.environ.get("HOME", "/nonexistent")
a = sys.argv[1:]
with open(os.path.join(home, "fakecurl.log"), "a") as f:
    f.write(json.dumps({"argv": a, "env": dict(os.environ)}) + "\n")
url = a[-1]
hdr = a[a.index("-D") + 1]; outp = a[a.index("-o") + 1]
conf = json.load(open(os.path.join(home, "fakecurl.json")))
r = conf.get(url)
if r is None:
    sys.stderr.write("curl: (7) Failed to connect\n"); sys.exit(7)
if r.get("exit"):
    sys.stderr.write(r.get("stderr", "curl: error") + "\n"); sys.exit(r["exit"])
with open(hdr, "w") as f:
    if r.get("connect"):
        f.write("HTTP/1.1 200 Connection established\r\n\r\n")
    f.write("HTTP/1.1 %%d X\r\n" %% r["status"])
    if r.get("location"):
        f.write("Location: %%s\r\n" %% r["location"])
    f.write("\r\n")
with open(outp, "wb") as f:
    if r.get("body_file"):
        f.write(open(r["body_file"], "rb").read())
    else:
        f.write(r.get("body", "").encode())
sys.stdout.write(str(r["status"]))
'''


class FakeCurl:
    def __init__(self, d):
        self.home = d
        self.path = os.path.join(d, "fakecurl")
        with open(self.path, "w") as f:
            f.write(FAKE_CURL % {"py": sys.executable})
        os.chmod(self.path, 0o755)
        self.routes = {}
        self.save()

    def save(self):
        with open(os.path.join(self.home, "fakecurl.json"), "w") as f:
            json.dump(self.routes, f)

    def route(self, url, status=200, body="", body_file=None, location=None, **kw):
        self.routes[url] = dict(status=status, body=body, body_file=body_file, location=location, **kw)
        self.save()

    def calls(self):
        p = os.path.join(self.home, "fakecurl.log")
        if not os.path.exists(p):
            return []
        return [json.loads(l) for l in open(p)]


class NoProbe(bu.Transport):
    def probe(self, timeout=5):
        return None


# ------------------------------------------------------------------ root helper in a user+mount namespace
def unshare_ok():
    if not have("unshare"):
        return False
    r = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
    return r.returncode == 0


FAKE_APT = r'''#!/bin/sh
# fake apt-get: logs argv and env, prints $R/apt.out, exits with $R/apt.rc
printf '%%s\n' "$*" >> "%(r)s/apt.log"
env >> "%(r)s/apt.env"
cat "%(r)s/apt.out" 2>/dev/null
exit "$(cat "%(r)s/apt.rc" 2>/dev/null || echo 0)"
'''


def make_root(r, keys):
    """A fake system under r: factory Tor Browser 15.0.26 at r/opt/tor-browser, factory LibreWolf
    157.0.1-1 at r/usr/share/librewolf with /usr/bin/librewolf -> ../share/librewolf/librewolf."""
    os.makedirs(os.path.join(r, "opt"))
    tar = tor_tarball(os.path.join(r, "factory.tar.xz"), "15.0.26")
    with tarfile.open(tar) as tf:
        tf.extractall(os.path.join(r, "opt"), filter="tar")
    os.unlink(tar)
    s = os.path.join(r, "usr/share/librewolf")
    os.makedirs(os.path.join(s, "distribution"))
    for n in ("librewolf", "librewolf-bin"):
        with open(os.path.join(s, n), "w") as f:
            f.write("#!/bin/sh\necho factory\n")
        os.chmod(os.path.join(s, n), 0o755)
    with open(os.path.join(s, "application.ini"), "w") as f:
        f.write("[App]\nVersion=157.0.1\n")
    with open(os.path.join(s, "distribution/policies.json"), "w") as f:
        f.write('{"from": "factory"}')
    os.makedirs(os.path.join(r, "usr/bin"))
    os.symlink("../share/librewolf/librewolf", os.path.join(r, "usr/bin/librewolf"))
    os.makedirs(os.path.join(r, "usr/lib"))
    with open(os.path.join(r, "packages.txt"), "w") as f:
        f.write("librewolf\t157.0.1-1\n")
    for d in ("run/prestium/browsers", "var/lib/prestium/browser-updates", "proc", "etc"):
        os.makedirs(os.path.join(r, d), exist_ok=True)
    with open(os.path.join(r, "meminfo"), "w") as f:
        f.write("MemAvailable: %d kB\n" % (16 * 1024 * 1024))
    with open(os.path.join(r, "fakeapt"), "w") as f:
        f.write(FAKE_APT % {"r": r})
    os.chmod(os.path.join(r, "fakeapt"), 0o755)
    with open(os.path.join(r, "keys.json"), "w") as f:
        json.dump({"pub": keys.pub, "fpr": keys.fpr}, f)


def staging(r, name):
    p = os.path.join(r, "home/user/.cache/prestium/browser-updater/staging", name)
    shutil.rmtree(p, ignore_errors=True)
    os.makedirs(p)
    return p


def stage_tor(r, keys, v, key="good", tar_fn=None):
    d = staging(r, "tor-browser")
    n = "tor-browser-linux-x86_64-%s.tar.xz" % v
    p = os.path.join(d, n)
    (tar_fn or tor_tarball)(p, v)
    keys.detach(key, p, p + ".asc")
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"version": "999.0"}, f)        # unsigned hint: must be ignored by the helper
    return p


def stage_lw(r, keys, version, **kw):
    d = staging(r, "librewolf")
    work = os.path.join(r, "lwbuild-" + version)
    os.makedirs(work, exist_ok=True)
    deb = lw_deb(work, version, **kw)
    inr, pk = lw_repo(keys, work, [deb])
    shutil.copy(inr, os.path.join(d, "InRelease"))
    shutil.copy(pk, os.path.join(d, "Packages"))
    shutil.copy(deb, os.path.join(d, "librewolf.deb"))
    return deb


NS_PRE = r'''
import io, json, os, sys, contextlib
sys.path.insert(0, %(tests)r)
import browser_update_testlib as T
bu, m = T.bu, T.load_helper()
R = sys.argv[1]
k = json.load(open(os.path.join(R, "keys.json")))
bu.KEYS = {"tor-browser": (k["pub"]["good"], k["fpr"]["good"]), "librewolf": (k["pub"]["good"], k["fpr"]["good"]),
           "firefox": (k["pub"]["good"], k["fpr"]["good"])}
bu.DPKG = "/usr/bin/dpkg"; bu.PACKAGES_LIST = os.path.join(R, "packages.txt")
m.MOUNT = os.path.join(R, "run/prestium/browsers"); m.LOCK = os.path.join(R, "lock")
m.STAGING_ROOT = os.path.join(R, "home/user/.cache/prestium/browser-updater/staging")
m.STAMP_DIR = os.path.join(R, "var/lib/prestium/browser-updates")
m.HIGHEST_DIR = os.path.join(R, "var/lib/prestium/browser-updates-highest")
m.OVERLAY = os.path.join(T.INC, "usr/share/prestium/opt-overlay")
m.PROC = os.path.join(R, "proc"); m.MEMINFO = os.path.join(R, "meminfo")
m.PY = sys.executable; m.COPY_AS = []; m.APT_GET = os.path.join(R, "fakeapt")
m.UNITS = {"tor-browser": [("tor-browser", R + "/opt/tor-browser", "dir")],
           "firefox": [("firefox", R + "/opt/firefox", "dir")],
           "librewolf": [("librewolf", R + "/usr/share/librewolf", "dir"),
                         ("librewolf-lib", R + "/usr/lib/librewolf", "dir"),
                         ("librewolf-wrapper", R + "/usr/bin/librewolf", "file")]}
MOUNTS, UMOUNTS, RUNS = [], [], []
_mount, _umount, _run = m.do_mount, m.do_umount, m.run
import ctypes
_libc = ctypes.CDLL(None, use_errno=True)
def rec_mount(a):
    MOUNTS.append(list(a))
    if a[:1] == ["-o"] and a[1].startswith("remount,mode=") and a[2] == m.MOUNT:
        # mount(8) re-applies the tmpfs's uid= in a user namespace and fails; the kernel call with the
        # same options does what mount(8) does as real root (MS_REMOUNT|MS_NOSUID|MS_NODEV, no MS_NOEXEC)
        data = ",".join(o for o in a[1].split(",") if o.startswith(("size=", "mode=")))
        if _libc.mount(b"tmpfs", m.MOUNT.encode(), b"tmpfs", 32 | 2 | 4, data.encode()) != 0:
            raise m.MountError("remount: errno %%d" %% ctypes.get_errno())
        return None
    return _mount(a)
def rec_umount(t):
    UMOUNTS.append(t); return _umount(t)
def rec_run(cmd, **kw):
    RUNS.append(list(cmd)); return _run(cmd, **kw)
m.do_mount, m.do_umount, m.run = rec_mount, rec_umount, rec_run
def call(cmd, name):
    env = dict(os.environ)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m.main(["prestium-browser-install", cmd, name])
    os.environ.clear(); os.environ.update(env)
    lines = [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]
    return rc, lines[-1], lines
def binds(target):
    return [e for e in m.mounts() if e["target"] == target]
def tmpfs():
    return [e for e in m.mounts() if e["target"] == m.MOUNT]
def tbver():
    return bu.tree_version("tor-browser", R + "/opt/tor-browser")
def lwver():
    return bu.tree_version("librewolf", R + "/usr/share/librewolf")
RES = {}
def done():
    print("RESULT " + json.dumps(RES, default=list))
'''
