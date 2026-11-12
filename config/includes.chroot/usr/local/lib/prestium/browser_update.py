# Prestium 2.1: Browser Updater library (no GTK). Used by the GUI (/usr/local/bin/prestium-browser-updater,
# as "user"), by the root helper (/usr/local/sbin/prestium-browser-install, for the verification and
# version rules only: it never downloads) and by tests/test_browser_update.py.
#
# What it does for the GUI, as the desktop user, through the transport the user clicked only:
#   Tor:  curl --socks5-hostname 127.0.0.1:9050 with a fresh random SOCKS username per job (Tor's
#         IsolateSOCKSAuth gives this job its own circuits). Proxy variables are never inherited.
#   I2P:  curl -x http://127.0.0.1:4444 (i2pd's "Web Browser HTTP Proxy", the one with the outproxy;
#         4450 has none). The outproxy operator sees the host names.
# curl never follows a redirect itself (no -L, --max-redirs 0): a Location is resolved here with
# urljoin and must be https on the browser's own publisher hosts before curl is run with it.
# Discovery metadata (Tor's update JSON, Mozilla's product-details) is only a hint: the version that
# is installed comes from the signed artefact (Tor Browser: the ChangeLog inside the signed tarball;
# Firefox: the signed SHA256SUMS; LibreWolf: the signed InRelease -> Packages -> .deb).
# Signatures: a throw-away GNUPGHOME with only the one publisher key, gpg --status-fd, then the
# shell policy sigstatus_ok from /usr/local/lib/prestium/sigcheck.sh (the same bytes as
# scripts/sigcheck.sh, which checks the build). Never the exit status of gpg alone.
import hashlib, json, os, re, secrets, shlex, shutil, signal, socket, subprocess, tempfile, time
import urllib.parse
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

MiB = 1 << 20

SIGCHECK = "/usr/local/lib/prestium/sigcheck.sh"
BASH = "/bin/bash"
CURL = "/usr/bin/curl"
GPG = "/usr/bin/gpg"
GPGCONF = "/usr/bin/gpgconf"
DPKG = "/usr/bin/dpkg"
SUDO = "/usr/bin/sudo"
HELPER = "/usr/local/sbin/prestium-browser-install"
MEMINFO = "/proc/meminfo"
STAMP_DIR = "/var/lib/prestium/browser-updates"
PACKAGES_LIST = "/usr/share/prestium/packages-2.0.txt"     # written at build time by hook 9990
CACHE_REL = ".cache/prestium/browser-updater"
UA = "Prestium-Browser-Updater"

BROWSERS = ("tor-browser", "librewolf", "firefox")
FIRST_RELEASE = ("tor-browser", "librewolf")                # Firefox (local pages) is a follow-up
TITLES = {"tor-browser": "Tor Browser", "librewolf": "I2P Browser (LibreWolf)",
          "firefox": "Firefox (local pages)"}

# publisher key (shipped in the image) and its pinned primary fingerprint
KEYS = {
    "tor-browser": ("/usr/share/prestium/keys/torbrowser.asc", "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"),
    "firefox": ("/usr/share/prestium/keys/mozilla.asc", "14F26682D0916CDD81E37B6D61B7B526D98F0353"),
    "librewolf": ("/usr/share/keyrings/librewolf.gpg", "662E3CDD6FE329002D0CA5BB40339DD82B12EF16"),
}

# Only these hosts are ever given to curl (each hop of a redirect is checked again).
# No CDN host is listed: none of these URLs redirected when this was written (2026-11-09).
ALLOWED_HOSTS = {
    "tor-browser": frozenset({"aus1.torproject.org", "dist.torproject.org"}),
    "firefox": frozenset({"product-details.mozilla.org", "archive.mozilla.org"}),
    "librewolf": frozenset({"repo.librewolf.net"}),
}
MAX_HOPS = 5

# sizes (unpacked: measured on Tor Browser 16.0 = 356 MiB, LibreWolf 157.0.1 Installed-Size 458 MiB)
ARTEFACT_CAP = 512 * MiB
META_CAP = 1 * MiB
PACKAGES_CAP = 8 * MiB
UNPACKED = {"tor-browser": 380 * MiB, "librewolf": 480 * MiB, "firefox": 320 * MiB}
CACHE_FREE_MIN = 700 * MiB
MEM_MIN = 1024 * MiB
MEM_RESERVE = 512 * MiB
# the helper's tmpfs: scratch on top of the copies and the tree, never less than FREE_MIN
SCRATCH = 100 * MiB
FREE_MIN = 700 * MiB
# download sizes before they are known (Tor Browser 16.0: 110 MB; LibreWolf 157: about 120 MB)
ARTEFACT_EST = {"tor-browser": 130 * MiB, "librewolf": 160 * MiB, "firefox": 100 * MiB}

TOR_SOCKS = ("127.0.0.1", 9050)
I2P_HTTP = ("127.0.0.1", 4444)

KEY_EXPIRED_TEXT = "key expired, use a newer ISO"
TOR_DOWN = "Tor is not connected. Open the Tor Connection Assistant and connect, then try again."
I2P_DOWN = "The I2P HTTP proxy is not ready. Wait until I2P is connected, then try again."
RESET_HINT = "If the browser does not start after this update, press Reset to shipped copy."

# discovery and artefact locations
TB_JSON = "https://aus1.torproject.org/torbrowser/update_3/release/download-linux-x86_64.json"
FF_JSON = "https://product-details.mozilla.org/1.0/firefox_versions.json"
LW_BASE = "https://repo.librewolf.net/"
LW_INRELEASE = LW_BASE + "dists/librewolf/InRelease"
LW_PACKAGES = "main/binary-amd64/Packages"

# ------------------------------------------------------------------ errors
class UpdateError(Exception):
    pass

class TransportError(UpdateError):
    pass

class SignatureError(UpdateError):
    pass

class KeyExpiredError(SignatureError):
    pass

class ResourceError(UpdateError):
    pass

class VersionError(UpdateError):
    pass

class Cancelled(UpdateError):
    pass

# ------------------------------------------------------------------ versions
MOZ_VER = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$")          # Tor Browser 16.0, 15.0.26; Firefox 159.0.1
DEB_VER = re.compile(r"^(?:[0-9]+:)?[0-9][A-Za-z0-9.+~]*(?:-[A-Za-z0-9.+~]+)?$")
TB_NAME = re.compile(r"^tor-browser-linux-x86_64-([0-9]+(?:\.[0-9]+){1,3})\.tar\.xz$")
FF_NAME = re.compile(r"^firefox-([0-9]+(?:\.[0-9]+){1,3})\.tar\.xz$")
# tolerant: the first "Tor Browser <version>" line of the ChangeLog (16.0's first line is
# "Tor Browser 16.0 - October 28 2026"; no fixed separator is assumed)
TB_CHANGELOG = re.compile(r"^Tor Browser ([0-9]+(?:\.[0-9]+)+)\b", re.M)

def moz_key(v):
    if not isinstance(v, str) or not MOZ_VER.match(v):
        raise VersionError("not a release version: %r" % (v,))
    t = tuple(int(x) for x in v.split("."))
    return t + (0,) * (4 - len(t))

def moz_cmp(a, b):
    ka, kb = moz_key(a), moz_key(b)
    return (ka > kb) - (ka < kb)

def deb_valid(v):
    return isinstance(v, str) and len(v) <= 80 and bool(DEB_VER.match(v))

def deb_cmp(a, b, dpkg=None):
    """-1, 0, 1 like cmp(), by dpkg's own rules (dpkg --compare-versions)."""
    if not (deb_valid(a) and deb_valid(b)):
        raise VersionError("not a Debian version: %r / %r" % (a, b))
    dpkg = dpkg or DPKG
    env = {"PATH": "/usr/bin:/bin", "LANG": "C"}
    for op, r in (("lt", -1), ("eq", 0), ("gt", 1)):
        p = subprocess.run([dpkg, "--compare-versions", a, op, b], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode == 0:
            return r
    raise VersionError("dpkg cannot compare %r and %r" % (a, b))

def deb_upstream(v):
    v = v.split(":", 1)[1] if ":" in v else v
    return v.rsplit("-", 1)[0] if "-" in v else v

def tb_changelog_version(text):
    head = "\n".join(text.splitlines()[:64])
    m = TB_CHANGELOG.search(head)
    return m.group(1) if m else None

def ini_version(text):
    sect = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            sect = line
        elif sect == "[App]" and line.startswith("Version="):
            return line.split("=", 1)[1].strip()
    return None

def redact(args):
    """Command line for the Details log: the per-job SOCKS username is never written out."""
    out, hide = [], False
    for a in args:
        out.append("<per-job>:" if hide else a)
        hide = a == "--proxy-user"
    return out

def read_text(path, limit=1 * MiB):
    try:
        with open(path, "rb") as f:
            return f.read(limit).decode("utf-8", "replace")
    except OSError:
        return None

def read_stamp(name, stamp_dir=None):
    t = read_text(os.path.join(stamp_dir or STAMP_DIR, name), 65536)
    if not t:
        return None
    try:
        d = json.loads(t)
    except ValueError:
        return None
    return d if isinstance(d, dict) and isinstance(d.get("version"), str) else None

def factory_deb_version(pkg, path=None):
    t = read_text(path or PACKAGES_LIST, 4 * MiB) or ""
    for line in t.splitlines():
        f = line.split("\t")
        if len(f) == 2 and f[0] == pkg and deb_valid(f[1]):
            return f[1]
    return None

def tree_version(name, root):
    """Version of the browser tree at root (the factory path, or a staged tree)."""
    if name == "tor-browser":
        t = read_text(os.path.join(root, "Browser/TorBrowser/Docs/ChangeLog.txt"))
        return tb_changelog_version(t) if t else None
    t = read_text(os.path.join(root, "application.ini"))
    return ini_version(t) if t else None

FACTORY = {"tor-browser": "/opt/tor-browser", "firefox": "/opt/firefox", "librewolf": "/usr/share/librewolf"}

def installed_version(name, root=None, stamp_dir=None, packages_list=None):
    """What the factory path shows now: {"version", "full" (LibreWolf: Debian version when known),
    "updated" (a helper stamp for this version exists), "stamp"}. The dpkg database is not used for
    LibreWolf: this updater never changes it (the build-time package list describes the factory tree)."""
    root = root or FACTORY[name]
    v = tree_version(name, root)
    st = read_stamp(name, stamp_dir)
    info = {"version": v, "full": None, "updated": False, "stamp": st}
    if name == "librewolf":
        if st and v and deb_valid(st["version"]) and deb_upstream(st["version"]) == v:
            info.update(full=st["version"], updated=True)
        else:
            fv = factory_deb_version("librewolf", packages_list)
            if fv and v and deb_upstream(fv) == v:
                info["full"] = fv
    elif st and v and st["version"] == v:
        info["updated"] = True
    return info

BIND_ROOT = "/run/prestium/browsers"
UNIT_TARGETS = {"tor-browser": ("/opt/tor-browser",), "firefox": ("/opt/firefox",),
                "librewolf": ("/usr/share/librewolf", "/usr/lib/librewolf", "/usr/bin/librewolf")}
MOUNTINFO = "/proc/self/mountinfo"

def helper_bind_present(name, mountinfo=None):
    """True when a factory path of the unit has a mount from the helper's tmpfs (same device as the
    mount on BIND_ROOT). Read as the user from mountinfo; used to keep Reset available even when the
    helper's stamp is missing (the helper's revert is a no-op when nothing is mounted)."""
    try:
        with open(mountinfo or MOUNTINFO) as f:
            lines = f.read(4 * MiB).splitlines()
    except OSError:
        return False
    unesc = lambda x: re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), x)
    ms = []
    for line in lines:
        a = line.partition(" - ")[0].split()
        if len(a) >= 5:
            ms.append((a[2], unesc(a[4])))
    devs = {d for d, t in ms if t == BIND_ROOT}
    return any(d in devs and t in UNIT_TARGETS[name] for d, t in ms)

def compare_candidate(name, candidate, info):
    """1 newer, 0 same, -1 older than what is installed. Unknown installed version: VersionError."""
    if not info or not info.get("version"):
        raise VersionError("cannot read the installed %s version" % TITLES[name])
    if name == "librewolf":
        if info.get("full"):
            return deb_cmp(candidate, info["full"])
        return deb_cmp(deb_upstream(candidate), info["version"])
    return moz_cmp(candidate, info["version"])

# ------------------------------------------------------------------ resources
def mem_available(path=None):
    t = read_text(path or MEMINFO, 65536) or ""
    m = re.search(r"^MemAvailable:\s+([0-9]+) kB", t, re.M)
    if not m:
        raise ResourceError("cannot read MemAvailable")
    return int(m.group(1)) * 1024

def tmpfs_need(name, artefacts, unpacked=None):
    """Bytes the root helper's tmpfs needs for one install: its copies of the downloads, the
    unpacked tree and scratch, at least FREE_MIN. The helper and the window use this one formula."""
    return max(artefacts + (unpacked if unpacked else UNPACKED[name]) + SCRATCH, FREE_MIN)

def helper_mem_needed(name, artefacts, unpacked=None):
    """MemAvailable the helper requires when it runs (the downloads already sit in RAM then)."""
    return max(MEM_MIN, tmpfs_need(name, artefacts, unpacked) + MEM_RESERVE)

def window_mem_needed(name, artefacts=None, unpacked=None):
    """MemAvailable the window requires before downloading: what the helper will require, plus the
    downloads themselves, which take RAM in the cache before the helper starts."""
    a = artefacts if artefacts is not None else ARTEFACT_EST[name]
    return a + helper_mem_needed(name, a, unpacked)

def check_ram(name, artefacts=None, unpacked=None, meminfo=None):
    mem = mem_available(meminfo)
    need = window_mem_needed(name, artefacts, unpacked)
    if mem < need:
        raise ResourceError("Only %d MB of RAM available (%d MB needed). Close memory-heavy "
                            "applications and try again." % (mem // MiB, need // MiB))
    return mem

def check_resources(name, cache_dir, meminfo=None, disk_usage=shutil.disk_usage):
    """Before any download: 700 MB free where the download goes, and the RAM the whole update will
    need (window_mem_needed: the downloads, the helper's tmpfs, 512 MB for the rest of the session).
    The unpacked tree stays in RAM until Reset or reboot."""
    os.makedirs(cache_dir, mode=0o700, exist_ok=True)
    free = disk_usage(cache_dir).free
    if free < CACHE_FREE_MIN:
        raise ResourceError("Only %d MB free for the download (%d MB needed). Close memory-heavy "
                            "applications and try again." % (free // MiB, CACHE_FREE_MIN // MiB))
    return free, check_ram(name, meminfo=meminfo)

def ram_note(name):
    return ("The updated %s stays in RAM until Reset or reboot (about %d MB)."
            % (TITLES[name], UNPACKED[name] // MiB))

# ------------------------------------------------------------------ transports
class Transport:
    """name "tor" or "i2p". One instance per update job (the Tor SOCKS username is per job)."""
    def __init__(self, name):
        if name not in ("tor", "i2p"):
            raise ValueError(name)
        self.name = name
        self.token = secrets.token_hex(16) if name == "tor" else None

    def curl_args(self):
        if self.name == "tor":
            return ["--socks5-hostname", "%s:%d" % TOR_SOCKS, "--proxy-user", self.token + ":"]
        return ["-x", "http://%s:%d" % I2P_HTTP]

    def env(self):
        # built from scratch: no http_proxy/https_proxy/ALL_PROXY/... from /etc/environment
        return {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": os.environ.get("HOME", "/nonexistent")}

    def down_text(self):
        return TOR_DOWN if self.name == "tor" else I2P_DOWN

    def probe(self, timeout=5):
        addr = TOR_SOCKS if self.name == "tor" else I2P_HTTP
        try:
            with socket.create_connection(addr, timeout=timeout) as s:
                if self.name == "tor":
                    s.sendall(b"\x05\x01\x00")          # SOCKS5, one method: no authentication
                    r = s.recv(2)
                    if len(r) != 2 or r[0] != 5 or r[1] != 0:
                        raise TransportError(TOR_DOWN)
        except OSError:
            raise TransportError(self.down_text())

# ------------------------------------------------------------------ download
def check_url(url, allowed):
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port
    except ValueError:
        raise UpdateError("refusing a malformed URL")
    if p.scheme != "https" or p.username or p.password or port not in (None, 443):
        raise UpdateError("refusing %s (only https on the publisher's own hosts)" % url[:200])
    host = (p.hostname or "").lower()
    if host not in allowed:
        raise UpdateError("refusing %s: %s is not one of the publisher's hosts" % (url[:200], host or "?"))
    if any(c in url for c in "\r\n\t ") or url.startswith("-"):
        raise UpdateError("refusing a malformed URL")
    return host

def last_header_block(text):
    """Headers of the last response in a curl -D dump (a proxy's CONNECT reply comes first)."""
    blocks, cur = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("HTTP/"):
            cur = [line]; blocks.append(cur)
        elif cur is not None and line:
            cur.append(line)
    return blocks[-1] if blocks else []

def header(block, name):
    name = name.lower() + ":"
    for line in block[1:]:
        if line.lower().startswith(name):
            return line.split(":", 1)[1].strip()
    return None

class Fetcher:
    """curl through one transport, with our own redirect handling and size caps."""
    def __init__(self, browser, transport, cancel=None, progress=None, log=None, curl=None, poll=0.2):
        self.allowed = ALLOWED_HOSTS[browser]
        self.t, self.cancel = transport, cancel
        self.progress = progress or (lambda *a: None)
        self.log = log or (lambda *a: None)
        self.curl = curl or CURL
        self.poll = poll

    def fetch(self, url, dest, cap, label=None, expected_size=None):
        for _ in range(MAX_HOPS + 1):
            host = check_url(url, self.allowed)
            status, location = self._once(url, dest, cap, label or os.path.basename(dest), expected_size)
            if status == 200:
                return dest
            if status in (301, 302, 303, 307, 308):
                if not location:
                    raise UpdateError("%s answered %d without a Location" % (host, status))
                nxt = urllib.parse.urljoin(url, location)
                self.log("redirect %s -> %s" % (url, nxt))
                url = nxt
                continue
            raise UpdateError("%s answered HTTP %d" % (host, status))
        raise UpdateError("too many redirects")

    def _once(self, url, dest, cap, label, expected_size):
        part, hdr = dest + ".part", dest + ".hdr"
        for p in (part, hdr, dest):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
        cmd = [self.curl, "-q", "-sS", "--proto", "=https", "--max-redirs", "0", "--retry", "3",
               "--connect-timeout", "60", "-m", "1800", "-A", UA, "--max-filesize", str(cap),
               "-D", hdr, "-o", part, "-w", "%{http_code}"] + self.t.curl_args() + [url]
        self.log("curl " + " ".join(shlex.quote(c) for c in redact(cmd[1:])))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.t.env(),
                                start_new_session=True)
        total = expected_size
        try:
            while True:
                try:
                    out, err = proc.communicate(timeout=self.poll)
                    break
                except subprocess.TimeoutExpired:
                    pass
                size = os.path.getsize(part) if os.path.exists(part) else 0
                if self.cancel is not None and self.cancel.is_set():
                    raise Cancelled("cancelled")
                if size > cap:
                    raise UpdateError("%s is larger than %d MB" % (label, cap // MiB))
                if total is None and size:
                    # display only: the server's Content-Length (curl -D writes headers as they come)
                    blk = last_header_block(read_text(hdr, 65536) or "")
                    cl = header(blk, "content-length") if blk and " 200" in blk[0] else None
                    if cl and cl.isdigit() and 0 < int(cl) <= cap:
                        total = int(cl)
                self.progress(label, size, total)
        except BaseException:
            self._kill(proc)
            for p in (part, hdr):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
            raise
        rc = proc.returncode
        try:
            block = last_header_block(read_text(hdr, 65536) or "")
        finally:
            try:
                os.unlink(hdr)
            except FileNotFoundError:
                pass
        if rc != 0:
            try:
                os.unlink(part)
            except FileNotFoundError:
                pass
            msg = (err.decode("utf-8", "replace").strip().splitlines() or [""])[-1][:200]
            if rc == 63:
                raise UpdateError("%s is larger than %d MB" % (label, cap // MiB))
            if rc in (5, 7, 28, 35, 52, 56, 97):
                raise TransportError("%s could not be downloaded (%s). %s" % (label, msg or "curl %d" % rc,
                                                                               self.t.down_text()))
            raise UpdateError("%s could not be downloaded (%s)" % (label, msg or "curl %d" % rc))
        try:
            status = int(out.decode().strip() or "0")
        except ValueError:
            status = 0
        if status != 200:
            try:
                os.unlink(part)
            except FileNotFoundError:
                pass
            return status, header(block, "location")
        size = os.path.getsize(part)
        if size > cap:
            os.unlink(part)
            raise UpdateError("%s is larger than %d MB" % (label, cap // MiB))
        if expected_size is not None and size != expected_size:
            os.unlink(part)
            raise UpdateError("%s has %d bytes, the signed index says %d" % (label, size, expected_size))
        self.progress(label, size, expected_size if expected_size is not None else size)
        os.replace(part, dest)
        return 200, None

    @staticmethod
    def _kill(proc):
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()

# ------------------------------------------------------------------ signatures
FPR_RE = re.compile(r"^[0-9A-F]{40}$")

def sigstatus_ok(name, status, fpr, sigcheck=None, bash=None, detached=False):
    """The shell policy itself (sigcheck.sh), given the gpg status text as an argument (never
    interpolated into the script). detached: sigstatus_detached_ok (one signature, no embedded
    data). Returns (ok, message)."""
    if not FPR_RE.match(fpr or ""):
        raise ValueError("a pinned 40-hex fingerprint is required")      # empty FPR = any key
    fn = "sigstatus_detached_ok" if detached else "sigstatus_ok"
    res = subprocess.run([bash or BASH, "-c", '. "$4" && ' + fn + ' "$1" "$2" "$3"', "_",
                          name, status, fpr, sigcheck or SIGCHECK],
                         capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    return res.returncode == 0, (res.stdout or res.stderr).strip()

def sig_failure(status, msg):
    """The exception for a failed policy check: an expired key gets its own wording."""
    if re.search(r"^\[GNUPG:\] (REVKEYSIG|KEYREVOKED)( |$)", status, re.M):
        return SignatureError(msg or "signed by a revoked key")
    if re.search(r"^\[GNUPG:\] (EXPKEYSIG|EXPSIG)( |$)", status, re.M):
        return KeyExpiredError("Signature check failed: %s. (%s)" % (KEY_EXPIRED_TEXT, msg))
    return SignatureError("Signature check failed: %s" % (msg or "bad signature"))

def gpg_verify(name, browser, workdir, sig=None, data=None, clearsigned=None, out=None,
               keys=None, gpg=None, sigcheck=None):
    """Verify a detached signature (sig, data) or a clear-signed file (clearsigned -> out, the signed
    text only) with the browser's pinned publisher key in a throw-away GNUPGHOME."""
    key_file, fpr = (keys or KEYS)[browser]
    gpg = gpg or GPG
    home = tempfile.mkdtemp(prefix="gnupg.", dir=workdir)            # mode 0700
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "GNUPGHOME": home, "HOME": home}
    base = [gpg, "--batch", "--no-tty", "--no-autostart", "--no-auto-key-retrieve", "--homedir", home]
    try:
        r = subprocess.run(base + ["--import", key_file], capture_output=True, env=env)
        if r.returncode != 0:
            raise SignatureError("cannot import the %s key %s" % (TITLES[browser], key_file))
        if clearsigned:
            if os.path.lexists(out):
                os.unlink(out)
            cmd = base + ["--status-fd", "1", "--output", out, "--decrypt", clearsigned]
        else:
            cmd = base + ["--status-fd", "1", "--verify", sig, data]
        r = subprocess.run(cmd, capture_output=True, env=env)
        status = r.stdout.decode("utf-8", "replace")
        ok, msg = sigstatus_ok(name, status, fpr, sigcheck=sigcheck, detached=not clearsigned)
        if not ok:
            raise sig_failure(status, msg)
        if r.returncode != 0:
            raise SignatureError("Signature check failed: gpg exited %d on %s" % (r.returncode, name))
        if clearsigned and not os.path.isfile(out):
            raise SignatureError("no signed text in %s" % name)
        return status
    finally:
        subprocess.run([GPGCONF, "--homedir", home, "--kill", "all"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(home, ignore_errors=True)

def check_clearsigned_shape(data):
    """One clear-signed message and nothing around it (no text outside the signed part)."""
    t = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    if not t.startswith("-----BEGIN PGP SIGNED MESSAGE-----\n") \
            or t.count("-----BEGIN PGP SIGNED MESSAGE-----") != 1 \
            or t.count("\n-----BEGIN PGP SIGNATURE-----\n") != 1 \
            or not t.rstrip().endswith("-----END PGP SIGNATURE-----"):
        raise SignatureError("InRelease is not a single clear-signed message")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

# ------------------------------------------------------------------ Tor Browser
def tb_urls(v):
    moz_key(v)
    n = "tor-browser-linux-x86_64-%s.tar.xz" % v
    b = "https://dist.torproject.org/torbrowser/%s/%s" % (v, n)
    return n, b, b + ".asc"

def parse_tb_json(text):
    """The version hint and a check that the JSON points at the official dist URLs for it."""
    try:
        j = json.loads(text)
    except ValueError:
        raise UpdateError("Tor's update information is not valid JSON")
    v = j.get("version") if isinstance(j, dict) else None
    if not isinstance(v, str) or not MOZ_VER.match(v):
        raise UpdateError("Tor's update information has no release version (%r)" % (v,))
    _, b, s = tb_urls(v)
    if j.get("binary") != b or j.get("sig") != s:
        raise UpdateError("Tor's update information and the download URL disagree")
    return v

# ------------------------------------------------------------------ Firefox (follow-up; not in the GUI)
def ff_urls(v):
    moz_key(v)
    b = "https://archive.mozilla.org/pub/firefox/releases/%s/" % v
    n = "firefox-%s.tar.xz" % v
    return n, b + "linux-x86_64/en-US/" + n, b + "SHA256SUMS", b + "SHA256SUMS.asc"

def parse_ff_json(text):
    try:
        j = json.loads(text)
    except ValueError:
        raise UpdateError("Mozilla's version information is not valid JSON")
    v = j.get("LATEST_FIREFOX_VERSION") if isinstance(j, dict) else None
    if not isinstance(v, str) or not re.match(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$", v):
        raise UpdateError("Mozilla's version information has no release version (%r)" % (v,))
    return v

def ff_check_sums(sums_text, tar_sha256, v):
    """The tarball must be listed in the (already verified) SHA256SUMS under its release path."""
    want = "%s  linux-x86_64/en-US/firefox-%s.tar.xz" % (tar_sha256, v)
    if want not in sums_text.splitlines():
        raise SignatureError("firefox-%s.tar.xz is not in Mozilla's signed SHA256SUMS" % v)

# ------------------------------------------------------------------ LibreWolf (apt repository)
def parse_release(text, now=None):
    """Fields and SHA256 entries of the signed text of InRelease."""
    fields, sums, cur = {}, {}, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if cur == "SHA256":
                f = line.split()
                if len(f) == 3 and re.match(r"^[0-9a-f]{64}$", f[0]) and f[1].isdigit():
                    sums[f[2]] = (f[0], int(f[1]))
            continue
        k, _, v = line.partition(":")
        cur = k
        fields[k] = v.strip()
    if fields.get("Suite") != "librewolf" and fields.get("Codename") != "librewolf":
        raise SignatureError("InRelease is not for the librewolf suite")
    vu = fields.get("Valid-Until")
    if vu:
        try:
            until = parsedate_to_datetime(vu)
        except (TypeError, ValueError):
            raise SignatureError("InRelease has an unreadable Valid-Until")
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until < (now or datetime.now(timezone.utc)):
            raise SignatureError("InRelease expired on %s (replayed or stale repository data)" % vu)
    return fields, sums

def check_packages(sums, packages_bytes):
    ent = sums.get(LW_PACKAGES)
    if not ent:
        raise SignatureError("the signed InRelease does not list %s" % LW_PACKAGES)
    if hashlib.sha256(packages_bytes).hexdigest() != ent[0] or len(packages_bytes) != ent[1]:
        raise SignatureError("Packages does not match the signed InRelease")

def parse_packages(text):
    out, cur, last = [], {}, None
    for line in text.splitlines():
        if not line.strip():
            if cur:
                out.append(cur)
            cur, last = {}, None
        elif line[0] in " \t":
            if last:
                cur[last] += "\n" + line.strip()
        else:
            k, _, v = line.partition(":")
            last = k
            cur[k] = v.strip()
    if cur:
        out.append(cur)
    return out

LW_FILENAME = re.compile(r"^pool/[A-Za-z0-9][A-Za-z0-9._+~-]*\.deb$")

def lw_candidates(stanzas):
    c = []
    for s in stanzas:
        if s.get("Package") == "librewolf" and s.get("Architecture") == "amd64" \
                and LW_FILENAME.match(s.get("Filename", "")) and ".." not in s["Filename"] \
                and re.match(r"^[0-9a-f]{64}$", s.get("SHA256", "")) and s.get("Size", "").isdigit() \
                and deb_valid(s.get("Version")):
            c.append(s)
    return c

def lw_latest(stanzas, dpkg=None):
    best = None
    for s in lw_candidates(stanzas):
        if best is None or deb_cmp(s["Version"], best["Version"], dpkg) > 0:
            best = s
    if best is None:
        raise UpdateError("the LibreWolf repository lists no amd64 librewolf package")
    return best

# ------------------------------------------------------------------ staging
def cache_dir(home=None):
    return os.path.join(home or os.path.expanduser("~"), CACHE_REL)

def staging_dir(name, home=None):
    return os.path.join(cache_dir(home), "staging", name)

def clean_staging(name, home=None):
    shutil.rmtree(staging_dir(name, home), ignore_errors=True)

def lw_installed_size(st):
    """Installed-Size (KiB) of a Packages stanza in bytes, or None."""
    v = st.get("Installed-Size", "")
    return int(v) * 1024 if v.isdigit() and int(v) > 0 else None

def prepare_update(name, transport, cancel=None, progress=None, log=None, home=None,
                   fetcher=None, check=check_resources, meminfo=None):
    """Check, download and verify (first verification, as the user) into the fixed staging
    directory. Returns {"status": "staged"|"current"|"older", "version", "installed"}."""
    progress = progress or (lambda *a: None)
    log = log or (lambda *a: None)
    if name not in BROWSERS:
        raise ValueError(name)
    info = installed_version(name)
    if not info["version"]:
        raise VersionError("cannot read the installed %s version" % TITLES[name])
    cdir = cache_dir(home)
    check(name, cdir)
    t = transport if isinstance(transport, Transport) else Transport(transport)
    progress("Checking %s…" % ("Tor" if t.name == "tor" else "the I2P HTTP proxy"), 0, None)
    t.probe()
    f = fetcher or Fetcher(name, t, cancel, progress, log)
    sdir = staging_dir(name, home)
    shutil.rmtree(sdir, ignore_errors=True)
    os.makedirs(sdir, mode=0o700)
    work = tempfile.mkdtemp(prefix="work.", dir=cdir)
    ok = False
    try:
        progress("Checking for the latest version…", 0, None)
        if name == "tor-browser":
            meta = f.fetch(TB_JSON, os.path.join(work, "update.json"), 65536, "update information")
            v = parse_tb_json(read_text(meta))
            res = _compare(name, v, info)
            if res:
                return res
            n, url, asc = tb_urls(v)
            f.fetch(asc, os.path.join(sdir, n + ".asc"), 65536, "signature")
            f.fetch(url, os.path.join(sdir, n), ARTEFACT_CAP, n)
            progress("Verifying signature…", 0, None)
            gpg_verify(n, name, work, sig=os.path.join(sdir, n + ".asc"), data=os.path.join(sdir, n))
            sha = sha256_file(os.path.join(sdir, n))
            hint = {"version": v, "file": n, "url": url}
        elif name == "firefox":
            meta = f.fetch(FF_JSON, os.path.join(work, "versions.json"), 65536, "version information")
            v = parse_ff_json(read_text(meta))
            res = _compare(name, v, info)
            if res:
                return res
            n, url, sums, sasc = ff_urls(v)
            f.fetch(sums, os.path.join(sdir, "SHA256SUMS"), 4 * MiB, "SHA256SUMS")
            f.fetch(sasc, os.path.join(sdir, "SHA256SUMS.asc"), 65536, "signature")
            progress("Verifying signature…", 0, None)
            gpg_verify("SHA256SUMS", name, work, sig=os.path.join(sdir, "SHA256SUMS.asc"),
                       data=os.path.join(sdir, "SHA256SUMS"))
            f.fetch(url, os.path.join(sdir, n), ARTEFACT_CAP, n)
            sha = sha256_file(os.path.join(sdir, n))
            ff_check_sums(read_text(os.path.join(sdir, "SHA256SUMS"), 4 * MiB), sha, v)
            hint = {"version": v, "file": n, "url": url}
        else:
            inr = f.fetch(LW_INRELEASE, os.path.join(sdir, "InRelease"), META_CAP, "InRelease")
            with open(inr, "rb") as fh:
                check_clearsigned_shape(fh.read())
            progress("Verifying signature…", 0, None)
            plain = os.path.join(work, "Release")
            gpg_verify("InRelease", name, work, clearsigned=inr, out=plain)
            _, sums = parse_release(read_text(plain, META_CAP))
            pk = f.fetch(LW_BASE + "dists/librewolf/" + LW_PACKAGES, os.path.join(sdir, "Packages"),
                         PACKAGES_CAP, "Packages")
            with open(pk, "rb") as fh:
                pb = fh.read()
            check_packages(sums, pb)
            st = lw_latest(parse_packages(pb.decode("utf-8", "replace")))
            v = st["Version"]
            res = _compare(name, v, info)
            if res:
                return res
            size = int(st["Size"])
            if size > ARTEFACT_CAP:
                raise UpdateError("the LibreWolf package is larger than %d MB" % (ARTEFACT_CAP // MiB))
            # the signed index gives the real sizes: check the RAM again before the large download
            if check is check_resources:
                check_ram(name, size, lw_installed_size(st), meminfo=meminfo)
            deb = os.path.join(sdir, "librewolf.deb")
            f.fetch(LW_BASE + st["Filename"], deb, ARTEFACT_CAP, os.path.basename(st["Filename"]), size)
            progress("Verifying the package…", 0, None)
            sha = sha256_file(deb)
            if sha != st["SHA256"]:
                raise SignatureError("the LibreWolf package does not match the signed Packages index")
            hint = {"version": v, "file": st["Filename"]}
        # unsigned hint for the GUI only; the helper does not read it
        hint.update(sha256=sha, transport=t.name)
        with open(os.path.join(sdir, "meta.json"), "w") as fh:
            json.dump(hint, fh)
        ok = True
        return {"status": "staged", "version": v, "installed": info["version"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if not ok:
            shutil.rmtree(sdir, ignore_errors=True)

def _compare(name, v, info):
    c = compare_candidate(name, v, info)
    if c > 0:
        return None
    return {"status": "current" if c == 0 else "older", "version": v, "installed": info.get("full") or info["version"]}

# ------------------------------------------------------------------ root helper call
def run_helper(cmd, name, on_event=None, popen=subprocess.Popen):
    """sudo -n prestium-browser-install install|revert <name>; JSON lines, the last is the result."""
    if cmd not in ("install", "revert") or name not in BROWSERS:
        raise ValueError((cmd, name))
    p = popen([SUDO, "-n", HELPER, cmd, name], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
              text=True, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    last = None
    for line in p.stdout:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if "ok" in d:
            last = d
        elif on_event:
            on_event(d)
    err = p.stderr.read()
    p.wait()
    if last is None:
        last = {"ok": False, "error": (err or "the install helper gave no result").strip()[-400:]}
    last.setdefault("code", p.returncode)
    return last
