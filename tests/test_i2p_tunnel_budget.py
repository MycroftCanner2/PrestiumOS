#!/usr/bin/python3
"""2.1 (startup tunnel budget): i2pd builds every tunnel pool at once after a cold boot, when builds fail
most. Checks that no pool falls back to i2pd's default of 5+5 (every tunnel in tunnels.conf, the
[socksproxy] SOCKS proxy, [exploratory], [shareddest] and the generated torrents tunnel set both
quantities), that the browser proxy (4444) keeps 2+2 and no other client pool has more, that sections
sharing one key file (one tunnel pool) agree, and that the total stays within the budget.
2.1 (I2P torrents): the torrent client is back at 5+5 (the 2+2 cut made downloads and magnet lookups
slow) and is the one pool allowed above 2+2; it gets common trackers, all inside I2P (.b32 for cold
boot, hostnames once the address book is warm), on the assistant's hops (default 3), with persistent keys/DHT file."""
import os, re, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)

BUDGET = 38          # tunnels kept ready at boot (2.0/2.1 before the budget: 68; 32 with torrents at 2+2)
DEFAULT_LEN = 3      # i2pd's default client tunnel length (the I2P Connection Assistant's default hops)

def ini(text):
    """[(section, {key: value})] in file order; comment lines ignored."""
    out = [[None, {}]]
    for l in text.splitlines():
        if re.match(r"^\s*[#;]", l) or not l.strip(): continue
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", l)
        if m: out.append([m.group(1).strip(), {}]); continue
        m = re.match(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$", l)
        if m: out[-1][1][m.group(1)] = m.group(2)
    return out

def qty(name, kv):
    q = (kv.get("inbound.quantity"), kv.get("outbound.quantity"))
    check(all(x is not None and x.isdigit() for x in q), "%s: inbound and outbound quantity set (%s)" % (name, q))
    return tuple(int(x) if x and x.isdigit() else 5 for x in q)

pools = {}   # pool id -> (in, out, in-length, out-length, name)
def pool(pid, name, q, length):
    if pid in pools:
        check(pools[pid][:2] == q, "%s shares a pool with %s: same quantities (%s vs %s)" % (name, pools[pid][4], q, pools[pid][:2]))
    else:
        pools[pid] = q + length + (name,)

for c in ("etc/i2pd/i2pd.conf", "var/lib/i2pd/i2pd.conf"):
    check(open(os.path.join(I, c)).read() == open(os.path.join(I, "var/lib/i2pd/i2pd.conf")).read(), "%s = the live config" % c)
main = dict((n, kv) for n, kv in ini(open(os.path.join(I, "var/lib/i2pd/i2pd.conf")).read()))
tun = ini(open(os.path.join(I, "var/lib/i2pd/tunnels.conf")).read())

# i2pd.conf
ex = main.get("exploratory", {})
check((ex.get("inbound.quantity"), ex.get("outbound.quantity")) == ("3", "3"), "exploratory: 3+3 (i2pd's default)")
pool("exploratory", "exploratory", qty("[exploratory]", ex), (int(ex.get("inbound.length", 2)), int(ex.get("outbound.length", 2))))
sd = main.get("shareddest", {})
pool("shareddest", "shared destination", qty("[shareddest]", sd), (int(sd.get("inbound.length", 3)), int(sd.get("outbound.length", 3))))
check(main.get("httpproxy", {}).get("enabled") == "false", "[httpproxy] off (the 4444 proxy is in tunnels.conf): no pool")
sp = main.get("socksproxy", {})
if sp.get("enabled", "true") == "true":
    pool("socksproxy", "SOCKS proxy " + sp.get("port", "4447"), qty("[socksproxy]", sp),
         (int(sp.get("inbound.length", DEFAULT_LEN)), int(sp.get("outbound.length", DEFAULT_LEN))))
check(main.get("sam", {}).get("enabled") == "false" and main.get("bob", {}).get("enabled", "false") == "false"
      and main.get("i2cp", {}).get("enabled", "false") == "false", "SAM, BOB and I2CP off (no extra pools)")

# tunnels.conf
browser = None
for name, kv in tun:
    if name is None or "type" not in kv: continue
    q = qty("tunnels.conf [%s]" % name, kv)
    keys = kv.get("keys", "transient")
    pid = ("tunnel", name) if keys == "transient" else ("keys", keys)
    # hops per tunnel, at most (a positive lengthVariance adds up to that many hops)
    hops = tuple(int(kv.get(d + ".length", DEFAULT_LEN)) + max(0, int(kv.get(d + ".lengthVariance", 0)))
                 for d in ("inbound", "outbound"))
    pool(pid, name, q, hops)
    if kv.get("port") == "4444": browser = q
    elif kv.get("type") in ("client", "udpclient", "httpproxy", "socks"):
        check(q == (1, 1), "[%s] (%s): 1+1" % (name, kv.get("port")))
    if name.startswith("socks-outproxy"):
        # the udp section shares the tcp section's pool (same keys), which sets the length
        check(all(kv.get(d + ".length", "1") == "1" for d in ("inbound", "outbound")), "[%s]: still 1 hop (+ variance)" % name)
check(browser == (2, 2), "browser proxy 4444: 2+2 (%s)" % (browser,))

# the torrent client's tunnel, written by prestium-i2pd-torrents at every i2pd start
t = open(os.path.join(I, "usr/local/sbin/prestium-i2pd-torrents")).read()
m = re.search(r"<<CONF\n(.*?)\nCONF", t, re.S)
tc = dict(ini(m.group(1) if m else ""))
tq = qty("torrents.conf [Torrents]", tc.get("Torrents", {}))
check(tq == (5, 5), "torrents: 5+5 (i2pd's default, restored: 2+2 made torrents slow)")
tk = tc.get("Torrents", {})
check(tk.get("inbound.length") == "$HOPS" and tk.get("outbound.length") == "$HOPS",
      "torrents: hops are generated from the assistant's setting (not a fixed length)")
tr = [x for x in tk.get("trackers", "").split(",") if x]
check(len(tr) >= 8, "torrents: common trackers set (%d), so a magnet without tr= still finds peers" % len(tr))
hosts = re.compile(r"(?:http://|udp://)([a-z0-9.-]+)(?::\d+)?(?:/\S*)?$")
b32s, names = [], []
for x in tr:
    m = hosts.fullmatch(x)
    h = m.group(1) if m else ""
    (b32s if re.fullmatch(r"[a-z2-7]{52}\.b32\.i2p", h) else names).append(x)
check(len(b32s) >= 4 and len(names) >= 2 and all(x.startswith("http://") or x.startswith("udp://") for x in tr),
      "torrents: all trackers inside I2P (%d .b32 for cold boot, %d hostnames once the address book is warm): %s" % (len(b32s), len(names), tr))
check(tk.get("dht") == "true" and tk.get("keys", "").startswith("torrents.dat") and tk.get("dhtfile") == "dht.dat",
      "torrents: DHT on, persistent keys + DHT file (identity and DHT node list survive i2pd restarts)")
pool("torrents", "torrents", tq, (DEFAULT_LEN, DEFAULT_LEN))

check(max(p[0] + p[1] for p in pools.values() if p[4] not in ("exploratory", "torrents")) <= 4,
      "no client pool but the torrent client has more tunnels than the browser's")
total = sum(p[0] + p[1] for p in pools.values())
reqs = sum(p[0] * p[2] + p[1] * p[3] for p in pools.values())
for p in sorted(pools.values(), key=lambda p: p[4]):
    print("     %-28s %d+%d" % (p[4], p[0], p[1]))
check(total <= BUDGET, "startup budget: %d tunnels (at most %d), about %d build requests at the default 3 hops" % (total, BUDGET, reqs))
sys.exit(fail)
