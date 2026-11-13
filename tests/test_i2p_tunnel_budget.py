#!/usr/bin/python3
"""2.1 (startup tunnel budget): i2pd builds every tunnel pool at once after a cold boot, when builds fail
most. Checks that no pool falls back to i2pd's default of 5+5 (every tunnel in tunnels.conf, the
[socksproxy] SOCKS proxy, [exploratory], [shareddest] and the generated torrents tunnel set both
quantities), that the browser proxy (4444) keeps 2+2 and nothing else has more, that sections sharing
one key file (one tunnel pool) agree, and that the total stays within the budget."""
import os, re, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)

BUDGET = 32          # tunnels kept ready at boot (2.0/2.1 before this change: 68)
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
check(tq == (2, 2), "torrents: 2+2 (published destination; one lease would drop off the DHT)")
pool("torrents", "torrents", tq, (DEFAULT_LEN, DEFAULT_LEN))

check(max(p[0] + p[1] for p in pools.values() if p[4] not in ("exploratory",)) <= 4,
      "no client pool has more tunnels than the browser's")
total = sum(p[0] + p[1] for p in pools.values())
reqs = sum(p[0] * p[2] + p[1] * p[3] for p in pools.values())
for p in sorted(pools.values(), key=lambda p: p[4]):
    print("     %-28s %d+%d" % (p[4], p[0], p[1]))
check(total <= BUDGET, "startup budget: %d tunnels (at most %d), about %d build requests at the default 3 hops" % (total, BUDGET, reqs))
sys.exit(fail)
