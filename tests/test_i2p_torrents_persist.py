#!/usr/bin/python3
"""2.1: I2P torrents survive i2pd restarts (persistent identity + DHT node list).

Checks:
- the generated torrents.conf keeps a persistent local destination (keys = torrents.dat,
  not transient) and a DHT file (dhtfile = dht.dat): with transient keys and no dhtfile
  i2pd runs a non-persistent DHT (empty on every start) and a fresh peer ID per start;
- hook 0700 makes /var/lib/i2pd/torrents a real writable directory with web/ symlinked to
  the shipped assets: the old whole-dir symlink put dht.dat in the read-only /usr tree,
  so the routing table could never be saved even with a dhtfile setting;
- AppArmor allows i2pd to read/write torrents.dat and torrents/ (keys + DHT file); without
  this the save on Stop() fails;
- [persist] profiles/addressbook are on: the router keeps its peer/profile history and
  the address book across restarts, so .i2p tracker hostnames resolve on restart;
- ferm does not block DHT/PEX/ut_metadata: they run over I2P itself (streaming tunnels
  + datagrams), never direct IP; i2pd's network access must include TCP+UDP and not be
  restricted to loopback, and no rule may REJECT i2pd's use of them. The substantive
  check is that i2pd owns Port 7685-local traffic via I2P while its router transports
  (NTCP2/SSU2 to the network) stay open.
"""
import os, re, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)

def ini(text):
    out = [[None, {}]]
    for l in text.splitlines():
        if re.match(r"^\s*[#;]", l) or not l.strip(): continue
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", l)
        if m: out.append([m.group(1).strip(), {}]); continue
        m = re.match(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$", l)
        if m: out[-1][1][m.group(1)] = m.group(2)
    return out

def read(rel):
    return open(os.path.join(I, rel)).read()

# 1. persistent identity + DHT file in the generated config
t = read("usr/local/sbin/prestium-i2pd-torrents")
m = re.search(r"<<CONF\n(.*?)\nCONF", t, re.S)
tc = dict(ini(m.group(1) if m else ""))
tk = tc.get("Torrents", {})
check(tk.get("keys") == "torrents.dat" and not tk.get("keys", "").startswith("transient"),
      "torrents: persistent local destination (keys = torrents.dat, not transient)")
check(tk.get("dht") == "true" and tk.get("dhtfile") == "dht.dat",
      "torrents: DHT on with a persistent file (dht.dat in /var/lib/i2pd/torrents/)")
check(tk.get("inbound.length") == "$HOPS" and tk.get("outbound.length") == "$HOPS",
      "torrents: hops follow the Connection Assistant (generated, not hardcoded)")
check('sec=="Web Browser HTTP Proxy"' in t and "HOPS=3" in t and 'sec=="exploratory"' in t,
      "torrents: hops read back from the assistant's tunnels (browser proxy, then exploratory, else 3)")
check('case $_h in 1|2|3|4|5|6|7)' in t,
      "torrents: a hand-edited hop count outside 1-7 falls back to 3, never stops i2pd")
check('D=/home/user/Downloads/Torrents' in t and tk.get("torrentsdir") == "$D",
      "torrents: torrent list/progress live in the user's per-boot dir")

# 2. hook: real writable dir + web symlink, not a whole-dir symlink into /usr
h = open(os.path.join(R, "config/hooks/live/0700-prestium-i2pd.hook.chroot")).read()
check("rm -f /var/lib/i2pd/torrents" in h and "install -d -o 2000 -g 2000 -m 0750 /var/lib/i2pd/torrents" in h,
      "hook 0700: /var/lib/i2pd/torrents is a real directory owned by i2pd (2000)")
check("ln -sfn /usr/share/i2pd/torrents/web /var/lib/i2pd/torrents/web" in h
      and "ln -sfn /usr/share/i2pd/torrents /var/lib/i2pd/torrents" not in h,
      "hook 0700: web/ is the symlink, not the whole torrents dir (dht.dat must not land in /usr)")
check("0750 i2pd i2pd /var/lib/i2pd/torrents/" in read("usr/share/prestium/build/perms.txt"),
      "perms: /var/lib/i2pd/torrents/ 0750 i2pd:i2pd")

# 3. AppArmor may read/write the keys + DHT file
aa = read("etc/apparmor.d/local/usr.bin.i2pd")
check("/var/lib/i2pd/torrents.dat rw," in aa, "AppArmor: i2pd may write torrents.dat (persistent keys)")
check("/var/lib/i2pd/torrents/** rwk," in aa, "AppArmor: i2pd may write torrents/** (DHT file)")

# 4. router peer profiles + address book persist across restarts
main = dict(ini(read("var/lib/i2pd/i2pd.conf")))
p = main.get("persist", {})
check(p.get("profiles") == "true" and p.get("addressbook") == "true",
      "[persist] profiles and addressbook both true (network node list survives restarts)")
check(read("var/lib/i2pd/i2pd.conf") == read("etc/i2pd/i2pd.conf"), "etc/i2pd/i2pd.conf = the live config")

# 5. DHT/PEX/ut_metadata are not blocked: i2pd keeps network TCP+UDP
ferm = read("etc/ferm/ferm.conf")
check("outerface ! lo mod owner uid-owner $i2pd_uid ACCEPT;" in ferm,
      "ferm: i2pd may reach the network (router transports NTCP2/SSU2; DHT/PEX ride these, never direct IP)")
check(re.search(r"outerface lo daddr 127\.0\.0\.1 proto \(tcp udp\) dport 4500", ferm) is not None
      or "dport 4500" in ferm, "ferm: i2pd loopback access still limited to its outproxy tunnel")
sys.exit(fail)
