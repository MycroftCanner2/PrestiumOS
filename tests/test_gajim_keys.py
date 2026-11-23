#!/usr/bin/env python3
"""Prestium 2.1: Gajim OpenPGP Keys (config/includes.chroot/usr/local/lib/prestium-keys/gajim_keys.py and
usr/local/bin/prestium-gajim-keys), with the real gpg in temporary home directories (no display, no
network). Statuses and checks for: a key as Gajim makes it, a key without an xmpp: user ID, one whose
first xmpp: user ID is another account, an expired, a revoked and a future-dated key (made with
--faked-system-time), one with no ownertrust, two secret keys, no key, a keyring folder that is not 700.
The Kleopatra import from a stand-in ~/.gnupg (pubring.kbx and keyboxd), which must stay byte for byte
and timestamp for timestamp unchanged; backups (wrapped or not) and their restore; Gajim's account list
from a settings.sqlite with Gajim 2.x's schema; the --check command line; and, when gajim-openpgp and
python3-gpg are installed, that Gajim's own plugin backend accepts the keys (and ignores a key without an
xmpp: user ID, which is why the import adds one). Needs gpg (gnupg 2.2 or later)."""
import importlib.machinery, importlib.util, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, unittest

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INC = os.path.join(R, "config", "includes.chroot")
BIN = os.path.join(INC, "usr", "local", "bin", "prestium-gajim-keys")
sys.dont_write_bytecode = True     # no __pycache__ in config/includes.chroot (live-build would ship it)
sys.path.insert(0, os.path.join(INC, "usr", "local", "lib", "prestium-keys"))
import gajim_keys as gk  # noqa: E402

JID = "alice@example.org"
PW = ["--pinentry-mode", "loopback", "--passphrase", "correct horse"]
HAVE_GPG = shutil.which("gpg") is not None


def raw(home, *args, data=None):
    """gpg as a test fixture would run it (not through the library)."""
    return subprocess.run(["gpg", "--homedir", home, "--batch", "--no-permission-warning", *args],
                          input=data, capture_output=True, check=True).stdout


def mkkey(home, uid, *extra, expire="never", passphrase=""):
    os.makedirs(home, mode=0o700, exist_ok=True)
    raw(home, "--pinentry-mode", "loopback", "--passphrase", passphrase, *extra,
        "--quick-generate-key", uid, "default", "default", expire)
    out = raw(home, "--with-colons", "--list-secret-keys", "--fixed-list-mode")
    return [l.split(":")[9] for l in out.decode().splitlines() if l.startswith("fpr:")][0]


@unittest.skipUnless(HAVE_GPG, "gpg missing")
class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="pgk-")
        self.home_dir = os.path.join(self.t, "home")
        self.saved = (gk.HOME, gk.DATA, gk.CONFIG, gk.OPENPGP, gk.SETTINGS, gk.GNUPG)
        gk.HOME = self.home_dir
        gk.DATA = os.path.join(self.home_dir, ".local/share/gajim")
        gk.CONFIG = os.path.join(self.home_dir, ".config/gajim")
        gk.OPENPGP = os.path.join(gk.DATA, "openpgp")
        gk.SETTINGS = os.path.join(gk.CONFIG, "settings.sqlite")
        gk.GNUPG = os.path.join(self.home_dir, ".gnupg")
        os.makedirs(os.path.join(self.home_dir, ".local/share"))
        gk.TEST_GPG_ARGS[:] = []

    def tearDown(self):
        gk.TEST_GPG_ARGS[:] = []
        for dp, dn, _ in os.walk(self.t):
            for d in dn:
                p = os.path.join(dp, d)
                if os.path.isdir(os.path.join(p, "private-keys-v1.d")) or os.path.exists(os.path.join(p, "pubring.kbx")):
                    gk.kill_agent(p)
        (gk.HOME, gk.DATA, gk.CONFIG, gk.OPENPGP, gk.SETTINGS, gk.GNUPG) = self.saved
        shutil.rmtree(self.t, ignore_errors=True)

    def status(self, jid=JID):
        return gk.account_status(gk.list_keys(gk.homedir(jid)), jid)

    def results(self, jid=JID, now=None):
        return {t.split(" (")[0]: r for r, t, _ in gk.checks(jid, now=now, gajim_is_running=False)}


class Status(Base):
    def test_generated_like_gajim_is_ready(self):
        fpr = gk.generate(JID)
        self.assertEqual(self.status(), gk.READY)
        k = gk.list_keys(gk.homedir(JID))[0]
        self.assertEqual(k.fpr, fpr)
        self.assertEqual([u.text for u in k.uids], ["xmpp:" + JID])
        self.assertEqual(k.expires, 0)
        self.assertIn("E", k.caps); self.assertIn("S", k.caps)
        self.assertEqual(k.ownertrust, "u")
        self.assertIs(gk.key_protected(gk.homedir(JID), k), False)    # as Gajim: no passphrase
        self.assertEqual(oct(os.stat(gk.homedir(JID)).st_mode & 0o777), "0o700")
        r = self.results()
        self.assertTrue(all(v in ("pass", "info") for v in r.values()), r)
        text, ok = gk.report(JID)
        self.assertTrue(ok); self.assertIn("Status: Ready", text)

    def test_no_key_and_no_folder(self):
        self.assertEqual(self.status(), gk.NO_KEY)
        self.assertEqual(self.results()["Keyring folder"], "fail")
        os.makedirs(gk.homedir(JID), mode=0o700)
        self.assertEqual(self.results()["Secret key"], "fail")
        self.assertFalse(gk.report(JID)[1])

    def test_missing_xmpp_uid_then_added(self):
        h = gk.homedir(JID)
        fpr = mkkey(h, "Alice <alice@example.org>")
        self.assertEqual(self.status(), gk.MISSING_UID)
        self.assertEqual(self.results()["User ID xmpp:" + JID], "fail")
        gk.add_uid(h, fpr, "xmpp:" + JID)
        self.assertEqual(self.status(), gk.READY)

    def test_other_account_first(self):
        h = gk.homedir(JID)
        fpr = mkkey(h, "xmpp:bob@example.org")
        self.assertEqual(self.status(), gk.MISSING_UID)
        time.sleep(1.1)        # a newer self-signature, so the order is not decided by the second
        gk.add_uid(h, fpr, "xmpp:" + JID)
        gk.primary_uid(h, fpr, "xmpp:" + JID)
        self.assertEqual(gk.gajim_uid(gk.list_keys(h)[0]), "xmpp:" + JID)
        self.assertEqual(self.status(), gk.READY)
        gk.revoke_uid(h, fpr, "xmpp:bob@example.org")
        k = gk.list_keys(h)[0]
        self.assertTrue([u for u in k.uids if u.text == "xmpp:bob@example.org"][0].revoked)
        self.assertEqual(self.status(), gk.READY)
        # GnuPG keeps the last valid user ID (it can't be revoked)
        with self.assertRaises(gk.KeyError_):
            gk.revoke_uid(h, fpr, "xmpp:" + JID)
        self.assertEqual(self.status(), gk.READY)

    def test_expired(self):
        h = gk.homedir(JID)
        mkkey(h, "xmpp:" + JID, "--faked-system-time", str(int(time.time()) - 3 * 86400) + "!", expire="1d")
        self.assertEqual(self.status(), gk.EXPIRED)
        self.assertEqual(self.results()["Not expired"], "fail")

    def test_future_dated(self):
        h = gk.homedir(JID)
        mkkey(h, "xmpp:" + JID, "--faked-system-time", str(int(time.time()) + 30 * 86400) + "!")
        self.assertEqual(self.status(), gk.FUTURE)
        self.assertEqual(self.results()["Created in the past"], "fail")

    def test_clock_before_2025(self):
        gk.generate(JID)
        self.assertEqual(self.results(now=1600000000)["System clock"], "fail")

    def test_revoked(self):
        h = gk.homedir(JID)
        fpr = gk.generate(JID)
        rev = open(os.path.join(h, "openpgp-revocs.d", fpr + ".rev"), "rb").read().replace(b":-----BEGIN", b"-----BEGIN")
        raw(h, "--import", data=rev)
        self.assertEqual(self.status(), gk.REVOKED)
        self.assertEqual(self.results()["Not revoked"], "fail")

    def test_no_ownertrust_then_marked(self):
        other = os.path.join(self.t, "other")
        fpr = mkkey(other, "xmpp:" + JID)
        sec = raw(other, "--export-secret-keys", fpr)
        gk.kill_agent(other)
        h = gk.homedir(JID); os.makedirs(h, mode=0o700)
        raw(h, "--import", data=sec)
        self.assertEqual(self.status(), gk.NO_TRUST)
        self.assertEqual(self.results()["Ownertrust and validity"], "warn")
        gk.set_ultimate(h, fpr)
        self.assertEqual(self.status(), gk.READY)

    def test_multiple_secret_keys_and_delete(self):
        a = gk.generate(JID)
        b = gk.generate(JID)
        self.assertEqual(self.status(), gk.MULTIPLE)
        self.assertEqual(self.results()["Exactly one secret key"], "fail")
        gk.delete_key(gk.homedir(JID), b)
        self.assertEqual([k.fpr for k in gk.list_keys(gk.homedir(JID))], [a])
        self.assertEqual(self.status(), gk.READY)
        with self.assertRaises(gk.KeyError_):
            gk.delete_key(gk.homedir(JID), "alice")

    def test_folder_permissions(self):
        gk.generate(JID)
        os.chmod(gk.homedir(JID), 0o755)
        self.assertEqual(self.results()["Keyring folder permissions"], "fail")

    def test_jid_validation(self):
        for bad in ("", "alice", "../x@y", "a@b/res", "a b@c", ".x@y", "a@b@c", "x@y\n"):
            self.assertFalse(gk.valid_jid(bad), bad)
            with self.assertRaises(gk.KeyError_):
                gk.homedir(bad)
        self.assertTrue(gk.valid_jid("alice@example.org"))
        self.assertTrue(gk.valid_jid("x@abcdefghijklmnopqrstuvwxyz234567.onion"))


class Accounts(Base):
    def test_settings_and_folders(self):
        os.makedirs(gk.CONFIG)
        con = sqlite3.connect(gk.SETTINGS)
        con.execute("CREATE TABLE settings (name TEXT UNIQUE, settings TEXT)")
        con.execute("CREATE TABLE account_settings (account TEXT UNIQUE, settings TEXT)")
        con.execute("insert into account_settings values (?, ?)",
                    ("acc1", json.dumps({"account": {"address": JID, "account_label": "Work"}, "contact": {}})))
        con.execute("insert into account_settings values (?, ?)",
                    ("old", json.dumps({"account": {"name": "carol", "hostname": "example.net"}})))
        con.execute("insert into account_settings values (?, ?)", ("junk", "not json"))
        con.commit(); con.close()
        before = gk.tree_digest(gk.CONFIG)
        os.makedirs(os.path.join(gk.OPENPGP, "dave@example.com"), mode=0o700)
        os.makedirs(os.path.join(gk.OPENPGP, "not a jid"), mode=0o700)
        self.assertEqual(gk.gajim_accounts(), [(JID, "Work"), ("carol@example.net", "old"),
                                               ("dave@example.com", "dave@example.com")])
        self.assertEqual(gk.tree_digest(gk.CONFIG), before, "settings.sqlite was touched (journal, lock)")

    def test_shipped_settings_have_no_accounts(self):
        gk.SETTINGS = os.path.join(INC, "etc/skel/.config/gajim/settings.sqlite")
        self.assertEqual(gk.gajim_accounts(), [])

    def test_gajim_running(self):
        p = os.path.join(self.t, "proc")
        os.makedirs(os.path.join(p, "4242")); os.makedirs(os.path.join(p, "17"))
        open(os.path.join(p, "17", "cmdline"), "wb").write(b"/usr/bin/foot\0")
        self.assertFalse(gk.gajim_running(p))
        open(os.path.join(p, "4242", "cmdline"), "wb").write(b"/usr/bin/python3\0/usr/bin/gajim\0")
        self.assertTrue(gk.gajim_running(p))


class Kleopatra(Base):
    def source(self, keyboxd=False, passphrase="correct horse"):
        src = gk.GNUPG
        os.makedirs(src, mode=0o700)
        if keyboxd:
            open(os.path.join(src, "common.conf"), "w").write("use-keyboxd\n")
        fpr = mkkey(src, "Alice Example <alice@example.org>", passphrase=passphrase)
        mkkey(src, "Someone Else <else@example.org>", passphrase=passphrase)
        # a public-only key (a contact's) must not be offered
        other = os.path.join(self.t, "contact")
        cf = mkkey(other, "Contact <c@example.org>")
        raw(src, "--import", data=raw(other, "--export", cf))
        gk.kill_agent(other); gk.kill_agent(src)       # Kleopatra is closed: no agent or keyboxd writing
        time.sleep(0.2)
        return src, fpr, cf

    def run_import(self, keyboxd):
        src, fpr, cf = self.source(keyboxd)
        before = gk.tree_digest(src)
        keys = gk.source_keys()
        self.assertEqual(len(keys), 2)
        self.assertNotIn(cf, [k.fpr for k in keys])
        self.assertIn(fpr, [k.fpr for k in keys])
        gk.TEST_GPG_ARGS[:] = PW      # the passphrase prompt, answered (adding the user ID signs with the key)
        notes = gk.import_from_source(JID, fpr)
        gk.TEST_GPG_ARGS[:] = []
        self.assertTrue(any("Added the user ID" in n for n in notes), notes)
        self.assertEqual(self.status(), gk.READY)
        k = gk.list_keys(gk.homedir(JID))[0]
        self.assertEqual(k.fpr, fpr)
        self.assertEqual(gk.gajim_uid(k), "xmpp:" + JID)
        self.assertIn("Alice Example <alice@example.org>", [u.text for u in k.uids])
        self.assertIs(gk.key_protected(gk.homedir(JID), k), True)   # the copy keeps its passphrase
        for g in k.all_grips():
            self.assertEqual(open(os.path.join(src, "private-keys-v1.d", g + ".key"), "rb").read(),
                             open(os.path.join(gk.homedir(JID), "private-keys-v1.d", g + ".key"), "rb").read())
        self.assertEqual(gk.tree_digest(src), before, "the source keyring changed")
        # the source still has no xmpp: user ID (only Gajim's copy got it)
        out = raw(src, "--list-keys", "--with-colons", fpr).decode()
        self.assertNotIn("xmpp", out.replace("\\x3a", ":"))
        gk.kill_agent(src)

    def test_import_pubring_kbx(self):
        self.run_import(False)

    def test_import_keyboxd(self):
        self.run_import(True)

    def test_import_without_uid_and_temp_cleanup(self):
        src, fpr, _ = self.source(passphrase="")
        tmp_before = set(os.listdir(tempfile.gettempdir()))
        notes = gk.import_from_source(JID, fpr, add_xmpp_uid=False)
        self.assertTrue(any("will ignore it" in n for n in notes), notes)
        self.assertEqual(self.status(), gk.MISSING_UID)
        left = [d for d in set(os.listdir(tempfile.gettempdir())) - tmp_before if d.startswith("prestium-keys-")]
        self.assertEqual(left, [], "temporary keyring copy left behind")

    def test_stub_and_unknown(self):
        src, fpr, cf = self.source()
        with self.assertRaises(gk.KeyError_):
            gk.import_from_source(JID, cf)     # no secret key in the source


class Backup(Base):
    def test_unprotected_key_is_wrapped_and_restores(self):
        fpr = gk.generate(JID)
        dest = os.path.join(self.t, JID + gk.BACKUP_SUFFIX)
        gk.TEST_GPG_ARGS[:] = PW
        self.assertTrue(gk.backup(JID, fpr, dest))
        data = open(dest, "rb").read()
        self.assertIn(b"BEGIN PGP MESSAGE", data)
        self.assertNotIn(b"PRIVATE " + b"KEY BLOCK", data)
        self.assertEqual(oct(os.stat(dest).st_mode & 0o777), "0o600")
        with self.assertRaises(gk.KeyError_):
            gk.backup(JID, fpr, dest)                       # never overwrites
        new = gk.import_file("bob@example.org", dest)
        gk.TEST_GPG_ARGS[:] = []
        self.assertEqual(new, [fpr])
        self.assertEqual([k.fpr for k in gk.list_keys(gk.homedir("bob@example.org"))], [fpr])

    def test_protected_key_exported_as_is(self):
        h = gk.homedir(JID)
        fpr = mkkey(h, "xmpp:" + JID, passphrase="correct horse")
        gk.set_ultimate(h, fpr)
        dest = os.path.join(self.t, "a" + gk.BACKUP_SUFFIX)
        gk.TEST_GPG_ARGS[:] = PW
        self.assertFalse(gk.backup(JID, fpr, dest))
        gk.TEST_GPG_ARGS[:] = []
        self.assertIn(b"PRIVATE " + b"KEY BLOCK", open(dest, "rb").read())

    def test_name_must_end_in_suffix(self):
        fpr = gk.generate(JID)
        with self.assertRaises(gk.KeyError_):
            gk.backup(JID, fpr, os.path.join(self.t, "key.asc"))


class CommandLine(Base):
    def run_cli(self, *args):
        env = dict(os.environ, HOME=self.home_dir)
        return subprocess.run([sys.executable, "-I", BIN, "--check", *args], capture_output=True, text=True, env=env)

    def test_check(self):
        gk.generate(JID)
        p = self.run_cli(JID)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Status: Ready", p.stdout)
        self.assertIn("PASS User ID xmpp:" + JID, p.stdout)
        self.assertIn("INFO Published to the server", p.stdout)
        p = self.run_cli("nobody@example.org")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Status: No key", p.stdout)
        p = self.run_cli()          # all accounts: the folder found under openpgp/
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn(JID, p.stdout)
        self.assertEqual(self.run_cli("../etc@x").returncode, 2)

    def test_gui_module_imports(self):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
        except (ImportError, ValueError):
            self.skipTest("GTK 3 introspection not installed")
        saved = sys.argv[:], os.environ.get("XDG_CONFIG_HOME")
        try:
            sys.argv = [BIN]
            loader = importlib.machinery.SourceFileLoader("prestium_gajim_keys_gui", BIN)
            mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
            loader.exec_module(mod)
        finally:
            sys.argv = saved[0]
            if saved[1] is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = saved[1]
        self.assertTrue(hasattr(mod, "Window") and hasattr(mod, "App"))
        self.assertEqual(mod.APP_ID, "org.prestium.GajimKeys")


PLUGINS = "/usr/share/gajim/plugins"


def have_plugin():
    if not os.path.isfile(os.path.join(PLUGINS, "openpgp", "backend", "gpgme.py")):
        return False
    return all(importlib.util.find_spec(m) is not None for m in ("gpg", "nbxmpp", "gajim"))


@unittest.skipUnless(HAVE_GPG and have_plugin(), "gajim-openpgp, python3-gpg or python3-nbxmpp not installed")
class GajimPlugin(Base):
    """Gajim's own OpenPGP backend (gajim-openpgp's backend/gpgme.py) on the keyrings made here, in a
    separate Python (Gajim loads GTK 4; the window test above loads GTK 3)."""
    SCRIPT = r"""
import json, sys
sys.path.insert(0, %r)
import gajim.common.modules  # first, or the plugin's imports are circular
from pathlib import Path
from openpgp.backend.gpgme import GPGMe
from nbxmpp.protocol import JID
jid, home = sys.argv[1], sys.argv[2]
b = GPGMe(jid, Path(home))
own = b.get_own_key_details()[0]
items = b.get_keys()
print(json.dumps({"own": own, "keys": [i.fingerprint for i in items],
                  "valid": [i.is_valid(JID.from_string(jid)) for i in items]}))
""" % PLUGINS

    def backend(self, jid=JID):
        p = subprocess.run([sys.executable, "-c", self.SCRIPT, jid, gk.homedir(jid)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_generated_key_accepted(self):
        fpr = gk.generate(JID)
        self.assertEqual(self.backend(), {"own": fpr, "keys": [fpr], "valid": [True]})

    def test_kleopatra_import_accepted(self):
        src = gk.GNUPG; os.makedirs(src, mode=0o700)
        fpr = mkkey(src, "Alice <alice@example.org>")
        gk.kill_agent(src)
        gk.import_from_source(JID, fpr)
        self.assertEqual(self.backend(), {"own": fpr, "keys": [fpr], "valid": [True]})

    def test_gajim_ignores_key_without_xmpp_uid(self):
        h = gk.homedir(JID)
        fpr = mkkey(h, "Alice <alice@example.org>")
        r = self.backend()
        self.assertEqual((r["own"], r["keys"]), (fpr, []))
        # it also asks GnuPG to delete it; without force a secret key needs gpg-agent's confirmation
        # prompt, which a test can't answer, so the key stays here (on the desktop the prompt appears)
        self.assertEqual(self.status(), gk.MISSING_UID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
