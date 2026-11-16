#!/usr/bin/env python3
"""Gajim has Tor and I2P proxies ready to use, and a plain menu name.

menu.xml: the Communication entry is exactly "Gajim" (no "(...)" suffix).
Gajim (both settings.sqlite copies, identical): the proxies table holds Tor
(socks5 127.0.0.1:9050), I2P SOCKS (socks5 127.0.0.1:4447) and I2P HTTP
(http 127.0.0.1:4444), and global_proxy names one of them, so each proxy is
selectable per account / app-wide without typing host and port by hand.
ferm lets the desktop user reach 9050 and 4447, and the AppArmor profile
allows inet stream TCP."""
import json
import os
import re
import sqlite3
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fail
    fail = 1
    print("FAIL " + m)


def check(c, m):
    (ok if c else bad)(m)


def rd(p):
    with open(os.path.join(I, p), encoding="utf-8") as f:
        return f.read()


# --- menu: plain names, no "(...)" ---
menu = rd("etc/xdg/labwc/menu.xml")
labels = re.findall(r'<item label="([^"]+)"', menu)
check("Gajim" in labels, "menu: Gajim entry")
check("Pidgin" not in labels, "menu: no Pidgin entry")
check(not any(l.startswith("Gajim (") for l in labels),
      "menu: no (Tor)/(Chat) suffix on Gajim")
check('command="prestium-run gajim"' in menu, "menu: Gajim launcher unchanged")

# --- Gajim: both proxies in the settings database, both copies identical ---
db = {}
for where in ("etc/skel/.config/gajim/settings.sqlite", "home/user/.config/gajim/settings.sqlite"):
    path = os.path.join(I, where)
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    rows = dict(con.execute("select name, settings from settings"))
    con.close()
    db[where] = rows
    app = json.loads(rows["app"])
    proxies = json.loads(rows["proxies"])
    by_endpoint = {(p["type"], p["host"], p["port"]) for p in proxies.values()}
    check(("socks5", "127.0.0.1", 9050) in by_endpoint, "%s: Tor proxy socks5 127.0.0.1:9050" % where)
    check(("socks5", "127.0.0.1", 4447) in by_endpoint, "%s: I2P SOCKS proxy socks5 127.0.0.1:4447" % where)
    check(("http", "127.0.0.1", 4444) in by_endpoint, "%s: I2P HTTP proxy http 127.0.0.1:4444" % where)
    check(app.get("global_proxy") in proxies, "%s: global_proxy (%r) names a proxy profile" % (where, app.get("global_proxy")))
    check(app.get("last_save_dir") == "/home/user/Downloads", "%s: Gajim saves in ~/Downloads" % where)
check(db["etc/skel/.config/gajim/settings.sqlite"] == db["home/user/.config/gajim/settings.sqlite"],
      "Gajim settings.sqlite: /etc/skel == home/user")

# --- network reachability and confinement ---
ferm = rd("etc/ferm/ferm.conf")
m = re.search(r"def \$user_ports = \(([^)]*)\);", ferm)
check(m and "9050" in m.group(1) and "4447" in m.group(1),
      "ferm: desktop user may reach Tor 9050 and I2P 4447")
for prof in ("usr.bin.gajim",):
    text = rd("etc/apparmor.d/" + prof)
    check(re.search(r"^  network inet stream,\s*$", text, re.M) is not None,
          "%s: inet stream TCP allowed (loopback proxies)" % prof)
    check("deny network inet," not in text, "%s: no blanket inet deny" % prof)

sys.exit(fail)
