# Prestium 2.1: Gajim OpenPGP Keys, the library (no GTK). Used by the window and by
# "prestium-gajim-keys --check" (/usr/local/bin/prestium-gajim-keys), and by tests/test_gajim_keys.py.
#
# Gajim's OpenPGP plugin (gajim-openpgp 1.7, XEP-0373) keeps one GnuPG home directory per account,
# ~/.local/share/gajim/openpgp/<bare JID>/, and uses the first secret key in it. It accepts a key only if
# its first "xmpp:" user ID is exactly xmpp:<bare JID>, and it ignores every key in that keyring that has
# no "xmpp:" user ID at all and asks GnuPG to delete it (gajim-openpgp backend/gpgme.py get_keys(); for a
# secret key gpg-agent then asks for a confirmation, or the deletion fails). The keys it
# makes itself are GnuPG's default algorithm (ed25519 + cv25519), no expiry and no passphrase.
#
# Everything here runs the system gpg with --homedir; there is no crypto code of its own and no network
# (gpg is never asked to reach a keyserver). A passphrase is only ever typed into GnuPG's own prompt
# (pinentry, started by gpg-agent); this code never sees one.
#
# The user's own keyring (~/.gnupg, Kleopatra's) is only read, and never by gpg: its public keyring is
# copied into a private temporary directory, gpg lists and exports from the copy, and the secret key
# files (private-keys-v1.d/<keygrip>.key, still protected by their passphrase) are copied byte for byte
# into the account's keyring. Nothing in ~/.gnupg is written, locked or started (no gpg-agent, no
# keyboxd on ~/.gnupg). AppArmor (usr.local.bin.prestium-gajim-keys) enforces the same.
import json, os, re, shutil, sqlite3, stat, subprocess, tempfile, time

GPG = "/usr/bin/gpg"
GPGCONF = "/usr/bin/gpgconf"
HOME = os.path.expanduser("~")
# Gajim's own folders on Prestium (the session sets no XDG_*_HOME; the window points XDG_CONFIG_HOME at
# Prestium's GTK style, so it is not read here)
DATA = os.path.join(HOME, ".local", "share", "gajim")
CONFIG = os.path.join(HOME, ".config", "gajim")
OPENPGP = os.path.join(DATA, "openpgp")
SETTINGS = os.path.join(CONFIG, "settings.sqlite")
GNUPG = os.path.join(HOME, ".gnupg")
# backups are written only under this suffix (the AppArmor profile allows no other new file name)
BACKUP_SUFFIX = ".gajim-key.asc"
# a clock before this is wrong (Prestium 2.1 was built after it)
SANE_TIME = 1735689600  # 2025-01-01 00:00 UTC
# tests only: extra gpg options (e.g. a loopback passphrase); never set by the app
TEST_GPG_ARGS = []

READY = "Ready"
NO_KEY = "No key"
MULTIPLE = "Multiple secret keys"
MISSING_UID = "Missing xmpp: user ID"
EXPIRED = "Expired"
REVOKED = "Revoked"
FUTURE = "Key created in the future (clock wrong)"
NO_TRUST = "No ownertrust (validity unknown)"
NO_SECRET = "Secret key not on this computer"
NO_ENCRYPT = "Can't encrypt or sign"

JID_RE = re.compile(r"[^@/\s\x00-\x1f\\]{1,1023}@[^@/\s\x00-\x1f\\]{1,1023}")


class KeyError_(Exception):
    """A gpg or file operation failed; str() is a message for the user."""


def valid_jid(jid):
    """A bare JID (local@domain) that is also a safe single directory name."""
    if not jid or not JID_RE.fullmatch(jid):
        return False
    return not (jid.startswith(".") or ".." in jid)


def homedir(jid):
    if not valid_jid(jid):
        raise KeyError_("%r is not an XMPP address of the form name@server" % jid)
    return os.path.join(OPENPGP, jid)


# ------------------------------------------------------------------------------------------ accounts
def gajim_accounts(settings=None, openpgp=None):
    """[(jid, label)] from Gajim's settings (read-only: the file is read into memory, so sqlite never
    locks it or writes a journal next to it), then every keyring folder Gajim has made."""
    settings = settings or SETTINGS
    openpgp = openpgp or OPENPGP
    out, seen = [], set()
    try:
        with open(settings, "rb") as f:
            data = f.read()
        con = sqlite3.connect(":memory:")
        try:
            con.deserialize(data)
            rows = con.execute("select account, settings from account_settings").fetchall()
        finally:
            con.close()
    except (OSError, sqlite3.Error, AttributeError):
        rows = []
    for account, blob in rows:
        try:
            s = json.loads(blob).get("account", {})
        except (ValueError, AttributeError):
            continue
        jid = s.get("address") or ("%s@%s" % (s.get("name", ""), s.get("hostname", "")))
        jid = jid.strip()
        if valid_jid(jid) and jid not in seen:
            seen.add(jid)
            out.append((jid, s.get("account_label") or account))
    try:
        dirs = sorted(os.listdir(openpgp))
    except OSError:
        dirs = []
    for d in dirs:
        if valid_jid(d) and d not in seen and os.path.isdir(os.path.join(openpgp, d)):
            seen.add(d)
            out.append((d, d))
    return out


def gajim_running(proc="/proc"):
    """Is Gajim running for this user? (python3 /usr/bin/gajim, or a gajim executable)"""
    me = os.getpid()
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return False
    for p in pids:
        if int(p) == me:
            continue
        try:
            with open(os.path.join(proc, p, "cmdline"), "rb") as f:
                argv = f.read().split(b"\0")[:3]
        except OSError:
            continue
        names = [os.path.basename(a) for a in argv if a]
        if not names:
            continue
        if names[0] == b"gajim" or (names[0].startswith(b"python3") and b"gajim" in names[1:]):
            return True
    return False


# ------------------------------------------------------------------------------------------------ gpg
def _env():
    env = dict(os.environ)
    env.pop("GNUPGHOME", None)
    env["LC_MESSAGES"] = "C"
    return env


def gpg(home, *args, data=None, check=True, timeout=600):
    """Run gpg on one home directory; returns (stdout bytes, stderr text)."""
    cmd = [GPG, "--homedir", home, "--batch", "--no-greeting", "--no-permission-warning"] + list(TEST_GPG_ARGS) + list(args)
    try:
        p = subprocess.run(cmd, input=data, capture_output=True, env=_env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        raise KeyError_("GnuPG did not finish (was a passphrase prompt left open?)")
    except OSError as e:
        raise KeyError_("could not run GnuPG: %s" % e)
    err = p.stderr.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise KeyError_(_gpg_reason(err) or "GnuPG failed (exit %d)" % p.returncode)
    return p.stdout, err


def _gpg_reason(err):
    lines = [l.strip() for l in err.splitlines() if l.strip() and "WARNING: unsafe permissions" not in l]
    for l in lines:
        if "Operation cancelled" in l or "canceled" in l.lower():
            return "Cancelled at the passphrase prompt."
        if "Bad passphrase" in l:
            return "Wrong passphrase."
    return lines[-1].replace("gpg: ", "") if lines else ""


def kill_agent(home):
    """Stop the gpg-agent of one home directory (Gajim starts a fresh one), quietly."""
    try:
        subprocess.run([GPGCONF, "--homedir", home, "--kill", "all"], capture_output=True, env=_env(), timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


# --------------------------------------------------------------------------------------------- parsing
class Uid:
    def __init__(self, f):
        self.validity = f[1]
        self.created = int(f[5]) if f[5].isdigit() else 0
        self.text = _unescape(f[9])

    @property
    def revoked(self):
        return self.validity == "r"


class Key:
    def __init__(self):
        self.fpr = ""
        self.grip = ""
        self.validity = ""
        self.ownertrust = ""
        self.created = 0
        self.expires = 0
        self.caps = ""
        self.secret = ""        # "+": secret here; "#": a stub (card/offline); "": public only
        self.uids = []
        self.subkeys = []       # [(fpr, grip, validity, caps, secret)]

    def all_grips(self):
        return [g for g in [self.grip] + [s[1] for s in self.subkeys] if g]


def _unescape(s):
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)


def parse_colons(text):
    keys, cur, last = [], None, None
    for line in text.splitlines():
        f = line.split(":")
        f += [""] * max(0, 21 - len(f))
        t = f[0]
        if t in ("pub", "sec"):
            cur = Key(); keys.append(cur); last = "pri"
            cur.validity, cur.ownertrust = f[1], f[8]
            cur.created = int(f[5]) if f[5].isdigit() else 0
            cur.expires = int(f[6]) if f[6].isdigit() else 0
            cur.caps = f[11]
            # "+" (or empty): the secret key is here; "#" or a card serial number: it is not
            cur.secret = ("+" if f[14] in ("", "+") else "#") if t == "sec" else ""
        elif t in ("sub", "ssb") and cur is not None:
            sec = ("+" if f[14] in ("", "+") else "#") if t == "ssb" else ""
            cur.subkeys.append(["", "", f[1], f[11], sec]); last = "sub"
        elif t == "fpr" and cur is not None:
            if last == "pri" and not cur.fpr:
                cur.fpr = f[9]
            elif last == "sub" and cur.subkeys:
                cur.subkeys[-1][0] = f[9]
        elif t == "grp" and cur is not None:
            if last == "pri" and not cur.grip:
                cur.grip = f[9]
            elif last == "sub" and cur.subkeys:
                cur.subkeys[-1][1] = f[9]
        elif t == "uid" and cur is not None:
            cur.uids.append(Uid(f)); last = "uid"
    return keys


LIST = ("--with-colons", "--fixed-list-mode", "--with-fingerprint", "--with-keygrip")


def list_keys(home, secret=True):
    if not os.path.isdir(home):
        return []
    out, _ = gpg(home, *LIST, "--list-secret-keys" if secret else "--list-keys", check=False)
    keys = parse_colons(out.decode("utf-8", "replace"))
    if secret:
        # validity and ownertrust as the public listing reports them (trust database checked)
        pub = {k.fpr: k for k in list_keys(home, secret=False)}
        for k in keys:
            p = pub.get(k.fpr)
            if p:
                k.validity, k.ownertrust = p.validity, p.ownertrust
                k.uids = p.uids
    return keys


# ----------------------------------------------------------------------------------------- the checks
def xmpp_uids(key):
    return [u for u in key.uids if u.text.startswith("xmpp:")]


def gajim_uid(key):
    """The user ID Gajim's plugin takes (the first that starts with xmpp:, revoked or not)."""
    x = xmpp_uids(key)
    return x[0].text if x else None


def key_status(key, jid, now=None):
    now = time.time() if now is None else now
    if key.validity == "r":
        return REVOKED
    if key.validity == "e" or (key.expires and key.expires <= now):
        return EXPIRED
    if key.created > now + 60:
        return FUTURE
    if key.secret == "#":
        return NO_SECRET
    if gajim_uid(key) != "xmpp:" + jid or any(u.revoked for u in key.uids if u.text == "xmpp:" + jid):
        return MISSING_UID
    if "E" not in key.caps or "S" not in key.caps:
        return NO_ENCRYPT
    if key.ownertrust != "u":
        return NO_TRUST
    return READY


def account_status(keys, jid, now=None):
    if not keys:
        return NO_KEY
    if len(keys) > 1:
        return MULTIPLE
    return key_status(keys[0], jid, now)


def checks(jid, home=None, now=None, gajim_is_running=None):
    """[(result, title, detail)]; result is "pass", "fail", "warn" or "info"."""
    now = time.time() if now is None else now
    home = home or homedir(jid)
    res = []
    add = lambda r, t, d="": res.append((r, t, d))
    if gajim_is_running is None:
        gajim_is_running = gajim_running()

    if now < SANE_TIME:
        add("fail", "System clock", "The clock says %s, which is too early. Set the correct time (System menu, "
            "or Tor's time sync) before making or checking keys." % _date(now))
    else:
        add("pass", "System clock", "The clock says %s (UTC)." % _date(now))

    if not os.path.isdir(home):
        add("fail", "Keyring folder", "%s does not exist. Generate a key or import one; Gajim also creates it "
            "when the account connects." % home)
        add("info", "Published to the server", PUBLISH_NOTE)
        return res
    st = os.stat(home)
    mode = stat.S_IMODE(st.st_mode)
    if st.st_uid != os.getuid():
        add("fail", "Keyring folder permissions", "%s belongs to another user (uid %d)." % (home, st.st_uid))
    elif mode & 0o077:
        add("fail", "Keyring folder permissions", "%s is mode %o; GnuPG wants 700 (only you). Fix: "
            "chmod 700 '%s'" % (home, mode, home))
    else:
        add("pass", "Keyring folder permissions", "%s is mode 700." % home)

    try:
        keys = list_keys(home)
    except KeyError_ as e:
        add("fail", "Read the keyring", str(e))
        return res
    if not keys:
        add("fail", "Secret key", "There is no secret key for %s. Press Generate key… or import one." % jid)
        add("info", "Published to the server", PUBLISH_NOTE)
        return res
    if len(keys) > 1:
        add("fail", "Exactly one secret key", "There are %d secret keys. Gajim uses only the first one it lists "
            "(%s). Back up and delete the ones you don't want." % (len(keys), fmt_fpr(keys[0].fpr)))
    else:
        add("pass", "Exactly one secret key", fmt_fpr(keys[0].fpr))
    k = keys[0]
    tag = (" (%s)" % short_fpr(k.fpr)) if len(keys) > 1 else ""

    if k.validity == "r":
        add("fail", "Not revoked" + tag, "This key is revoked and can't be used. Generate or import another key.")
    else:
        add("pass", "Not revoked" + tag)
    if k.validity == "e" or (k.expires and k.expires <= now):
        add("fail", "Not expired" + tag, "It expired on %s. Generate a new key, or extend it with "
            "gpg --homedir '%s' --quick-set-expire %s 2y" % (_date(k.expires), home, k.fpr))
    elif k.expires and k.expires - now < 30 * 86400:
        add("warn", "Not expired" + tag, "It expires on %s, in less than 30 days." % _date(k.expires))
    else:
        add("pass", "Not expired" + tag, "Expires %s." % (_date(k.expires) if k.expires else "never"))
    if k.created > now + 60:
        add("fail", "Created in the past" + tag, "The key was made on %s, after the current time (%s). GnuPG "
            "treats it as not valid yet. The clock was ahead when it was made, or is behind now: set the "
            "correct time, or make a new key with the clock right." % (_date(k.created), _date(now)))
    else:
        add("pass", "Created in the past" + tag, "Created %s." % _date(k.created))
    if k.secret == "#":
        add("fail", "Secret key on this computer" + tag, "Only a stub is here (the key is on a smartcard or "
            "was exported without its secret part). Gajim needs the secret key in its own keyring.")
    else:
        add("pass", "Secret key on this computer" + tag)

    want = "xmpp:" + jid
    first = gajim_uid(k)
    good = [u for u in k.uids if u.text == want and not u.revoked]
    if not good:
        add("fail", "User ID %s" % want + tag, "The key has no user ID %s. Gajim's plugin only accepts a key "
            "whose user ID is exactly that; it ignores keys with no xmpp: user ID and tries to delete them. Press "
            "Add user ID… and add %s." % (want, want))
    elif first != want:
        add("fail", "User ID %s" % want + tag, "Gajim reads the first xmpp: user ID, which is %s. Make %s the "
            "primary user ID, or revoke the other one." % (first, want))
    else:
        add("pass", "User ID %s" % want + tag)
    bad = [u.text for u in k.uids if u.text.startswith("xmpp") and not re.match(r"^xmpp:[^\s<>]+@[^\s<>]+$", u.text)]
    if bad:
        add("warn", "User ID format" + tag, "These look like XMPP user IDs but are not of the form "
            "xmpp:name@server: %s" % ", ".join(bad))

    if "E" in k.caps and "S" in k.caps:
        add("pass", "Can encrypt and sign" + tag)
    else:
        add("fail", "Can encrypt and sign" + tag, "The key has no usable %s key (capabilities %r). Make a new "
            "key with Generate key…" % ("encryption" if "E" not in k.caps else "signing", k.caps))

    if k.ownertrust == "u" and k.validity == "u":
        add("pass", "Ownertrust and validity" + tag, "Ultimate (it is your own key).")
    else:
        add("warn", "Ownertrust and validity" + tag, "GnuPG does not mark this as your own key (ownertrust %r, "
            "validity %r). Gajim itself encrypts regardless, but GnuPG may warn or refuse. Press Mark as my "
            "key on the key card." % (k.ownertrust or "-", k.validity or "-"))

    if gajim_is_running:
        add("info", "Gajim is running", "Gajim reads its keyring when an account connects. After a change "
            "here, quit Gajim and start it again.")
    add("info", "Published to the server", PUBLISH_NOTE)
    return res


PUBLISH_NOTE = ("Not checked: this tool has no network access. Gajim publishes your public key when the account "
                "connects. To see it, open Gajim's XML console (Ctrl+Shift+X) and look for a publish to "
                "urn:xmpp:openpgp:0:public-keys, or ask a contact whether your key shows up for them.")


def report(jid, home=None, now=None):
    """The --check report: (text, ok)."""
    home = home or homedir(jid)
    try:
        keys = list_keys(home)
    except KeyError_:
        keys = []
    lines = ["Gajim OpenPGP key check for %s" % jid, "Keyring: %s" % home,
             "Status: %s" % account_status(keys, jid, now)]
    for k in keys:
        lines.append("Key %s" % fmt_fpr(k.fpr))
        lines.append("  created %s, expires %s" % (_date(k.created), _date(k.expires) if k.expires else "never"))
        for u in k.uids:
            lines.append("  user ID %s%s" % (u.text, " (revoked)" if u.revoked else ""))
    ok = True
    for r, t, d in checks(jid, home, now):
        ok = ok and r != "fail"
        lines.append("%-4s %s%s" % (r.upper(), t, (": " + d) if d else ""))
    return "\n".join(lines), ok


def fmt_fpr(f):
    return " ".join(f[i:i + 4] for i in range(0, len(f), 4))


def short_fpr(f):
    return f[-16:]


def _date(t):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)) if t else "-"


# ------------------------------------------------------------------------------------------ changes
def ensure_home(jid):
    home = homedir(jid)
    os.makedirs(OPENPGP, mode=0o700, exist_ok=True)     # ~/.local/share/gajim/openpgp (Gajim never ran)
    if not os.path.isdir(home):
        os.mkdir(home, 0o700)
    os.chmod(home, 0o700)
    return home


def set_ultimate(home, fpr):
    gpg(home, "--import-ownertrust", data=("%s:6:\n" % fpr).encode())


def generate(jid, passphrase=False, home=None):
    """A new key as Gajim's plugin makes it: user ID xmpp:<jid>, GnuPG's default algorithm (ed25519
    signing + cv25519 encryption), no expiry. passphrase=True: gpg asks for one in its own prompt;
    False: no passphrase (as Gajim's plugin does)."""
    home = home or ensure_home(jid)
    uid = "xmpp:" + jid
    before = {k.fpr for k in list_keys(home)}
    # --yes: a second key with the same user ID (the window warns before that)
    args = ["--yes", "--quick-generate-key", uid, "default", "default", "never"]
    if not passphrase:
        args = ["--pinentry-mode", "loopback", "--passphrase", ""] + args
    gpg(home, *args)
    new = [k for k in list_keys(home) if k.fpr not in before]
    if not new:
        raise KeyError_("GnuPG made no key")
    set_ultimate(home, new[0].fpr)
    return new[0].fpr


def add_uid(home, fpr, uid):
    if not uid or "\n" in uid or len(uid) > 512:
        raise KeyError_("not a valid user ID")
    gpg(home, "--quick-add-uid", fpr, uid)


def revoke_uid(home, fpr, uid):
    gpg(home, "--quick-revoke-uid", fpr, uid)


def primary_uid(home, fpr, uid):
    gpg(home, "--quick-set-primary-uid", fpr, uid)


def delete_key(home, fpr):
    if not re.fullmatch(r"[0-9A-F]{40}|[0-9A-F]{64}", fpr or ""):
        raise KeyError_("not a full fingerprint")
    gpg(home, "--yes", "--delete-secret-and-public-key", fpr)


def key_protected(home, key):
    """True if the primary secret key file has a passphrase, False if not, None if unknown."""
    try:
        with open(os.path.join(home, "private-keys-v1.d", key.grip + ".key"), "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"protected-private-key" in data:
        return True
    if b"private-key" in data:
        return False
    return None


def backup(jid, fpr, dest, home=None):
    """Write the account's key (armored, secret and public) to dest, a new file named *.gajim-key.asc.
    A key with a passphrase is exported as it is (still protected by that passphrase; gpg asks for it).
    A key without one (Gajim's own keys) is encrypted with a new passphrase that gpg asks for, so the
    file is never an unprotected secret key. Returns True if it was wrapped that way."""
    home = home or homedir(jid)
    if not dest.endswith(BACKUP_SUFFIX):
        raise KeyError_("the backup file name must end in %s" % BACKUP_SUFFIX)
    key = [k for k in list_keys(home) if k.fpr == fpr]
    if not key:
        raise KeyError_("no such key")
    prot = key_protected(home, key[0])
    out, _ = gpg(home, "--armor", "--export-options", "backup", "--export-secret-keys", fpr)
    if not out.strip():
        raise KeyError_("GnuPG exported nothing")
    wrapped = prot is not True
    if wrapped:
        out, _ = gpg(home, "--armor", "--symmetric", "--cipher-algo", "AES256", "--s2k-digest-algo", "SHA512",
                     "--s2k-count", "65011712", "--output", "-", data=out)
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise KeyError_("%s already exists" % dest)
    except OSError as e:
        raise KeyError_("can't write %s: %s" % (dest, e.strerror))
    with os.fdopen(fd, "wb") as f:
        f.write(out)
    return wrapped


def import_file(jid, path, home=None):
    """Import a key file into the account's keyring: a backup made here (decrypted first; gpg asks for
    the passphrase) or any armored or binary key. Returns the fingerprints with a secret key."""
    home = home or ensure_home(jid)
    with open(path, "rb") as f:
        data = f.read(4 * 1024 * 1024)
    if b"-----BEGIN PGP MESSAGE-----" in data:
        data, _ = gpg(home, "--decrypt", data=data)
    before = {k.fpr for k in list_keys(home)}
    gpg(home, "--import", data=data)
    new = [k.fpr for k in list_keys(home) if k.fpr not in before]
    for f in new:
        set_ultimate(home, f)
    return new


# --------------------------------------------------------------------------- Kleopatra's keyring (~/.gnupg)
class SourceCopy:
    """A private, temporary copy of ~/.gnupg's public keyring for gpg to read (never ~/.gnupg itself)."""
    def __init__(self, src=None):
        self.src = src or GNUPG
        self.tmp = None

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="prestium-keys-", dir="/tmp")
        kbx = os.path.join(self.src, "pubring.kbx")
        db = os.path.join(self.src, "public-keys.d", "pubring.db")
        if _uses_keyboxd(self.src) and os.path.isfile(db):
            os.mkdir(os.path.join(self.tmp, "public-keys.d"), 0o700)
            for n in ("pubring.db", "pubring.db-wal"):
                p = os.path.join(self.src, "public-keys.d", n)
                if os.path.isfile(p):
                    _copy(p, os.path.join(self.tmp, "public-keys.d", n))
            with open(os.path.join(self.tmp, "common.conf"), "w") as f:
                f.write("use-keyboxd\n")
        elif os.path.isfile(kbx):
            _copy(kbx, os.path.join(self.tmp, "pubring.kbx"))
        elif os.path.isfile(os.path.join(self.src, "pubring.gpg")):
            _copy(os.path.join(self.src, "pubring.gpg"), os.path.join(self.tmp, "pubring.gpg"))
        return self

    def __exit__(self, *a):
        if self.tmp:
            kill_agent(self.tmp)
            shutil.rmtree(self.tmp, ignore_errors=True)

    def gpg(self, *args, **kw):
        return gpg(self.tmp, "--trust-model", "always", "--no-auto-check-trustdb", *args, **kw)


def _uses_keyboxd(src):
    try:
        with open(os.path.join(src, "common.conf")) as f:
            return any(l.split("#")[0].strip() == "use-keyboxd" for l in f)
    except OSError:
        return False


def _copy(a, b):
    with open(a, "rb") as fa, open(b, "xb") as fb:
        shutil.copyfileobj(fa, fb)
    os.chmod(b, 0o600)


def source_keys(src=None):
    """The keys in ~/.gnupg that have their secret key there: [Key] (secret="+" or "#" for a stub)."""
    src = src or GNUPG
    if not os.path.isdir(src):
        return []
    with SourceCopy(src) as c:
        out, _ = c.gpg(*LIST, "--list-keys", check=False)
    keys = parse_colons(out.decode("utf-8", "replace"))
    have = []
    for k in keys:
        f = os.path.join(src, "private-keys-v1.d", k.grip + ".key")
        if not os.path.isfile(f):
            continue
        k.secret = "#" if _is_stub(f) else "+"
        for s in k.subkeys:
            sf = os.path.join(src, "private-keys-v1.d", s[1] + ".key")
            s[4] = ("#" if _is_stub(sf) else "+") if os.path.isfile(sf) else ""
        have.append(k)
    return have


def _is_stub(path):
    try:
        with open(path, "rb") as f:
            return b"shadowed-private-key" in f.read()
    except OSError:
        return True


def import_from_source(jid, fpr, src=None, add_xmpp_uid=True, home=None):
    """Copy one key from ~/.gnupg into the account's keyring: the public key through a temporary copy,
    the secret key files byte for byte (they keep their passphrase; no prompt). ~/.gnupg is only read.
    With add_xmpp_uid, adds xmpp:<jid> to the copy if missing (gpg asks for the key's passphrase).
    Returns a list of notes for the user."""
    src = src or GNUPG
    home = home or ensure_home(jid)
    notes = []
    key = [k for k in source_keys(src) if k.fpr == fpr]
    if not key:
        raise KeyError_("that key has no secret key in %s" % src)
    key = key[0]
    if key.secret == "#":
        raise KeyError_("only a stub of that secret key is in %s (smartcard?); it can't be copied" % src)
    with SourceCopy(src) as c:
        pub, _ = c.gpg("--export", fpr)
    if not pub:
        raise KeyError_("GnuPG exported nothing from the copy of %s" % src)
    gpg(home, "--import", data=pub)
    kd = os.path.join(home, "private-keys-v1.d")
    if not os.path.isdir(kd):
        os.mkdir(kd, 0o700)
    copied = 0
    for g in key.all_grips():
        s = os.path.join(src, "private-keys-v1.d", g + ".key")
        d = os.path.join(kd, g + ".key")
        if os.path.isfile(s) and not _is_stub(s) and not os.path.exists(d):
            _copy(s, d)
            copied += 1
    set_ultimate(home, fpr)
    if not any(k.fpr == fpr for k in list_keys(home)):
        raise KeyError_("the secret key did not arrive in Gajim's keyring")
    if "E" not in key.caps:
        notes.append("This key has no encryption subkey; Gajim can't use it to encrypt.")
    want = "xmpp:" + jid
    k2 = [k for k in list_keys(home) if k.fpr == fpr][0]
    if not any(u.text == want and not u.revoked for u in k2.uids):
        if add_xmpp_uid:
            add_uid(home, fpr, want)
            notes.append("Added the user ID %s to Gajim's copy (your key in Kleopatra is unchanged)." % want)
        else:
            notes.append("The key has no user ID %s; Gajim will ignore it, and try to delete it, unless you add it." % want)
    k2 = [k for k in list_keys(home) if k.fpr == fpr][0]
    if any(u.text == want and not u.revoked for u in k2.uids) and gajim_uid(k2) != want:
        primary_uid(home, fpr, want)
        notes.append("Made %s the primary user ID in Gajim's copy." % want)
    return notes


def tree_digest(path):
    """{relative path: (mode, size, mtime_ns, sha256)} of a directory (tests: the source stays unchanged)."""
    import hashlib
    out = {}
    for dp, dn, fn in os.walk(path):
        for n in dn + fn:
            p = os.path.join(dp, n)
            st = os.lstat(p)
            h = ""
            if stat.S_ISREG(st.st_mode):
                with open(p, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
            out[os.path.relpath(p, path)] = (st.st_mode, st.st_size, st.st_mtime_ns, h)
    return out
