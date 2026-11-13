#!/usr/bin/env python3
"""Pidgin and Gajim have both Tor and I2P proxies ready to use, and plain menu names.

menu.xml: the Communication entries are exactly "Pidgin" and "Gajim" (no "(...)" suffix).
Gajim (both settings.sqlite copies, identical): the proxies table holds Tor
(socks5 127.0.0.1:9050), I2P SOCKS (socks5 127.0.0.1:4447) and I2P HTTP
(http 127.0.0.1:4444), and global_proxy names one of them, so each proxy is
selectable per account / app-wide without typing host and port by hand.
Pidgin (both prefs.xml copies, identical): the global proxy is SOCKS5
127.0.0.1:9050 with remote DNS on (Tor); the pidgin-tor launcher starts
Pidgin when Tor OR i2pd is up, and in I2P-only mode swaps the global proxy
port to 4447 (I2P SOCKS, same host/remote DNS), so Tor and I2P are both
ready in Pidgin too. ferm lets the desktop user reach 9050 and 4447, and
both AppArmor profiles allow inet stream TCP."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

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
check("Pidgin" in labels and "Gajim" in labels, "menu: Pidgin and Gajim entries")
check(not any(l.startswith("Pidgin (") or l.startswith("Gajim (") for l in labels),
      "menu: no (Tor)/(Chat) suffix on Pidgin/Gajim")
check('command="prestium-run /usr/local/bin/pidgin-tor"' in menu
      and 'command="prestium-run gajim"' in menu, "menu: Pidgin/Gajim launchers unchanged")

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

# --- Pidgin: global Tor proxy, I2P ready through the launcher ---
prefs = {}
for where in ("etc/skel/.purple/prefs.xml", "home/user/.purple/prefs.xml"):
    root = ET.parse(os.path.join(I, where)).getroot()
    proxy = root.find("./pref[@name='purple']/pref[@name='proxy']")
    vals = {c.get("name") or "": c.get("value") or "" for c in (list(proxy) if proxy is not None else [])}
    prefs[where] = vals
    check(vals.get("type") == "socks5" and vals.get("host") == "127.0.0.1" and vals.get("port") == "9050",
          "%s: global proxy socks5 127.0.0.1:9050 (Tor)" % where)
    check(vals.get("socks4_remotedns") == "1", "%s: remote DNS on (proxy resolves .onion/.i2p names)" % where)
check(prefs["etc/skel/.purple/prefs.xml"] == prefs["home/user/.purple/prefs.xml"],
      "Pidgin prefs.xml: /etc/skel == home/user")

launcher = rd("usr/local/bin/pidgin-tor")
check(subprocess.run(["sh", "-n", os.path.join(I, "usr/local/bin/pidgin-tor")]).returncode == 0,
      "pidgin-tor launcher parses")
check("systemctl is-active -q i2pd" in launcher and "tor@default" in launcher,
      "pidgin-tor: starts when Tor or i2pd is up")
check("4447" in launcher and "9050" in launcher and "Neither Tor nor I2P" in launcher,
      "pidgin-tor: Tor 9050 and I2P 4447, error only when neither is up")

# --- network reachability and confinement ---
ferm = rd("etc/ferm/ferm.conf")
m = re.search(r"def \$user_ports = \(([^)]*)\);", ferm)
check(m and "9050" in m.group(1) and "4447" in m.group(1),
      "ferm: desktop user may reach Tor 9050 and I2P 4447")
for prof in ("usr.bin.pidgin", "usr.bin.gajim"):
    text = rd("etc/apparmor.d/" + prof)
    check(re.search(r"^  network inet stream,\s*$", text, re.M) is not None,
          "%s: inet stream TCP allowed (loopback proxies)" % prof)
    check("deny network inet," not in text, "%s: no blanket inet deny" % prof)

sys.exit(fail)
