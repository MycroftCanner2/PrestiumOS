#!/usr/bin/python3
"""Gajim keeps account passwords in its own settings, never in GNOME Keyring (user decision after the
compatibility audit: app-confine keeps org.freedesktop.secrets out of Gajim's bus, so with use_keyring on
Gajim could not store a password at all).

How: Gajim's own, supported mechanism, /etc/gajim/app-overrides.json ({"use_keyring": false}). Gajim
applies it over every profile's settings.sqlite at each start, so it covers new profiles (the seeded
/etc/skel and live-home copies) and existing persistent ones alike without rewriting their other
settings; Gajim refuses to change an overridden setting from its preferences.

Static: the override file, its perms.txt line, the AppArmor read rule (Gajim opens the file unguarded,
so a denied read would stop it at start), and that the bus policy still names no keyring or secrets.
Functional (skips without the gajim package): Gajim's own Settings and passwords modules on a temporary
profile: a copy of the shipped settings.sqlite with use_keyring forced on and a custom setting, as an
existing profile would have. use_keyring reads back False, the other settings survive, a saved password
lands in settings.sqlite (account_settings) and reads back, the keyring backend is never asked, and
Gajim refuses to turn use_keyring back on.
"""
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config", "includes.chroot")
OV = os.path.join(I, "etc/gajim/app-overrides.json")
fails = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fails
    fails += 1
    print("FAIL " + m)


def chk(c, g, f):
    ok(g) if c else bad(f)


try:
    ov = json.load(open(OV))
except (OSError, ValueError) as e:
    ov = None
    bad("app-overrides.json: %s" % e)
chk(ov == {"use_keyring": False}, "app-overrides.json: use_keyring false, nothing else", "app-overrides.json: %r" % ov)
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
chk("0644 root root /etc/gajim/app-overrides.json\n" in perms, "perms.txt: 0644 root", "perms.txt lacks app-overrides.json")
prof = open(os.path.join(I, "etc/apparmor.d/usr.bin.gajim")).read()
chk(re.search(r"^\s*/etc/gajim/app-overrides\.json r,$", prof, re.M), "gajim profile may read the override",
    "gajim profile lacks /etc/gajim/app-overrides.json r")
chk(not re.search(r"/etc/gajim/\S*\s+[a-z]*w", prof), "gajim profile: no write in /etc/gajim", "gajim profile writes /etc/gajim")
pol = open(os.path.join(I, "usr/share/prestium/app-confine/gajim.policy")).read()
pol += open(os.path.join(I, "usr/share/prestium/app-confine/pinentry.inc")).read()
pol = "\n".join(l for l in pol.splitlines() if not l.lstrip().startswith("#"))
chk(not re.search(r"freedesktop\.secrets|org\.gnome\.keyring(?!\.SystemPrompter)|kwallet", pol),
    "gajim's bus: still no keyring or Secret Service", "gajim's bus names a keyring")

if importlib.util.find_spec("gajim") is None or importlib.util.find_spec("keyring") is None:
    print("SKIP functional check: gajim / python3-keyring not installed")
    sys.exit(1 if fails else 0)

PROBE = r'''
import json, os, pathlib, shutil, sqlite3, sys
seed, ov, root = sys.argv[1:4]
from gajim.common import configpaths
configpaths.init()
configpaths.create_paths()
db = str(configpaths.get("SETTINGS"))
shutil.copy(seed, db)
con = sqlite3.connect(db)
app_s = json.loads(con.execute("SELECT settings FROM settings WHERE name='app'").fetchone()[0])
app_s.update(use_keyring=True, confirm_close_muc=False)  # an existing profile: keyring on, a custom setting
con.execute("UPDATE settings SET settings=? WHERE name='app'", (json.dumps(app_s),))
con.commit(); con.close()
import keyring
asked = []
for n in ("get_password", "set_password", "delete_password"):
    setattr(keyring, n, lambda *a, _n=n: asked.append(_n))
from gajim.common import app, settings as S
S.OVERRIDES_PATH = pathlib.Path(ov)
app.settings = S.Settings()
app.settings.init()
out = {"use_keyring": app.settings.get("use_keyring"),
       "custom": app.settings.get("confirm_close_muc"),
       "proxy": app.settings.get("global_proxy")}
app.settings.add_account("probe")
app.settings.set_account_setting("probe", "savepass", True)
from gajim.common import passwords
out["saved"] = passwords.save_password("probe", "s3cret-probe")
out["read"] = passwords.get_password("probe")
app.settings.set("use_keyring", True)
out["after_set"] = app.settings.get("use_keyring")
app.settings.save()  # what the scheduled commit (200 ms) does in a running Gajim
app.settings._con.close()
con = sqlite3.connect(db)
acc = json.loads(con.execute("SELECT settings FROM account_settings WHERE account='probe'").fetchone()[0])
out["in_db"] = acc.get("account", {}).get("password") if "account" in acc else acc.get("password")
out["raw"] = "s3cret-probe" in json.dumps(acc)
out["asked"] = asked
print("RESULT " + json.dumps(out))
'''
T = tempfile.mkdtemp(prefix="gajim-nokr-")
try:
    env = dict(os.environ, HOME=T, XDG_CONFIG_HOME=T + "/c", XDG_DATA_HOME=T + "/d", XDG_CACHE_HOME=T + "/k",
               XDG_STATE_HOME=T + "/s", DBUS_SESSION_BUS_ADDRESS="unix:path=" + T + "/no-bus")
    seed = os.path.join(I, "etc/skel/.config/gajim/settings.sqlite")
    p = subprocess.run([sys.executable, "-c", PROBE, seed, OV, T], env=env, capture_output=True, text=True,
                       timeout=120)
    line = [l for l in p.stdout.splitlines() if l.startswith("RESULT ")]
    if not line:
        bad("Gajim's settings probe failed: %s" % (p.stderr[-800:] or p.stdout[-800:]))
    else:
        r = json.loads(line[0][7:])
        chk(r["use_keyring"] is False, "existing profile with use_keyring on: reads back False", "use_keyring %r" % r["use_keyring"])
        chk(r["custom"] is False and r["proxy"], "its other settings survive (custom value, global proxy %r)" % r["proxy"],
            "settings lost: %r" % r)
        chk(r["saved"] is True and r["read"] == "s3cret-probe", "password saved and read back through Gajim",
            "password: saved %r read %r" % (r["saved"], r["read"]))
        chk(r["raw"], "the password is in settings.sqlite (account_settings)", "password not in settings.sqlite")
        chk(r["asked"] == [], "the keyring was never asked", "keyring calls: %r" % r["asked"])
        chk(r["after_set"] is False, "Gajim refuses to turn use_keyring back on", "use_keyring changed to %r" % r["after_set"])
        sq = sqlite3.connect(seed).execute("SELECT settings FROM settings WHERE name='app'").fetchone()[0]
        chk("use_keyring" not in sq, "the seeded settings.sqlite is untouched (the override does the work)",
            "seeded settings.sqlite sets use_keyring itself")
finally:
    shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if fails else 0)
