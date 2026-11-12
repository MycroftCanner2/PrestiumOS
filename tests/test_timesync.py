#!/usr/bin/python3
# 2.1: prestium-timesync (sdwdate design) and prestium-bootclock. Loads the real script and replaces
# only the network fetch, the clock setter and the flag, so nothing on this machine changes.
import importlib.machinery, importlib.util, os, re, sys, tempfile, time
sys.dont_write_bytecode = True   # never leave __pycache__ in config/includes.chroot (live-build would ship it)

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = R + "/config/includes.chroot"
fail = 0


def ok(m): print("OK   " + m)


def bad(m):
    global fail; print("FAIL " + m); fail = 1


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec); loader.exec_module(mod); return mod


os.environ["PRESTIUM_TIMESYNC_TEST"] = "1"
ts = load(I + "/usr/local/sbin/prestium-timesync", "ts")
ts.TEST = True
T = tempfile.mkdtemp()
NS = ts.NS

# the shipped pool list: 3 pools, every entry an onion v3 address, credit and licence kept
pools = ts.load_pools(I + "/usr/share/prestium/timesync/pools.conf")
sizes = {k: len(v) for k, v in pools.items()}
(ok if sorted(sizes) == ["one", "two", "zero"] and min(sizes.values()) >= 5 else bad)("pools: %s" % sizes)
txt = open(I + "/usr/share/prestium/timesync/pools.conf").read()
(ok if "AGPL-3+" in txt and "ENCRYPTED SUPPORT LLC" in txt and "be1db0ce" in txt else bad)("pools.conf: attribution and licence")
for badline in ("[pool a]\nhttp://example.com # x\n", "[pool a]\nhttps://abc.onion # v2\n"):
    p = T + "/bad.conf"; open(p, "w").write(badline)
    try:
        ts.load_pools(p); bad("accepted a non-onion-v3 source: %r" % badline)
    except ValueError:
        ok("refuses %r" % badline.splitlines()[1])

# fakes
build = int(time.time()) - 30 * 86400
open(T + "/build", "w").write("%d\n" % build)
ts.BUILD_FILE = T + "/build"; ts.STATE = T + "/state"; ts.MIN_FILES = (T + "/min",); ts.RUN = T + "/run"
now = int(time.time())
ts.consensus_window = lambda: (now - 3600, now + 7200)
answers = {}
ts.fetch = lambda url: answers.get(url, (lambda: None))()
out = []
ts.log = out.append


def run(per_pool, first=True):
    """per_pool: {pool: [callable per member, in order of members]}"""
    answers.clear(); out.clear()
    for name, members in pools.items():
        fs = per_pool.get(name, [])
        for i, member in enumerate(members):
            for url in member:
                answers[url] = fs[i] if i < len(fs) else (lambda: None)
    # the order members are tried is random: make it the file's order
    ts.random.SystemRandom = lambda: type("R", (), {"shuffle": lambda self, l: None, "randint": lambda self, a, b: a})()
    r = ts.one_round(pools, first)
    return r, "\n".join(out)


def at(off):
    return lambda: (int(time.time()) + off, time.clock_gettime_ns(time.CLOCK_REALTIME))


# median of three, not the mean: one pool off by 50 minutes does not move the clock
r, o = run({"zero": [at(10)], "one": [at(12)], "two": [at(3000)]})
m = re.search(r"SET (\d+) step", o)
(ok if r and m and abs(int(m.group(1)) - (time.time() + 12)) <= 3 else bad)("median used, liar ignored: " + o.replace("\n", " | ")[-200:])
(ok if re.search(r"skew 1[0-3]s", o) else bad)("log keeps the 'skew Ns' line prestium-vm-netcheck reads")
(ok if re.search(r"randomized by [+-]0\.\d{9}s", o) else bad)("up to 1 s of random nanoseconds")
(ok if open(T + "/state").read().strip().isdigit() else bad)("replay-protection time saved")
(ok if '"class": "synced"' in open(T + "/run/waybar.json").read() else bad)("panel status: synced (dot hidden)")

# later rounds slew small differences, step big ones (the fake clock never moved, so drop the saved time)
os.path.exists(T + "/state") and os.remove(T + "/state")
r, o = run({"zero": [at(2)], "one": [at(2)], "two": [at(2)]}, first=False)
(ok if "slew" in o else bad)("small difference later in the boot: slewed")
os.path.exists(T + "/state") and os.remove(T + "/state")
r, o = run({"zero": [at(600)], "one": [at(600)], "two": [at(600)]}, first=False)
(ok if " step" in o else bad)("10-minute difference: stepped")
os.path.exists(T + "/state") and os.remove(T + "/state")
r, o = run({"zero": [at(30)], "one": [at(30)], "two": [at(30)]}, first=False)
(ok if " step" in o else bad)("30-second difference: stepped (over the 10 s slew limit)")
src = open(I + "/usr/local/sbin/prestium-timesync").read()
(ok if "libc.adjtime(" in src and "time.sleep(0.1)" not in src else bad)("slew: kernel adjtime, no stepping loop")
(ok if "calendar.timegm(" in src and "time.mktime" not in src else bad)("consensus times parsed as UTC with timegm")
os.path.exists(T + "/state") and os.remove(T + "/state")

# an answer outside Tor's consensus window is a failure; too many failures abort the round
r, o = run({"zero": [at(5)], "one": [at(5)], "two": [at(30 * 86400)] * 20})
(ok if r is False and "outside Tor's consensus window" in o and "round aborted" in o and "SET" not in o else bad)("consensus check and pool failure limit")
r, o = run({"zero": [at(5)], "one": [at(5)]})
(ok if r is False and "SET" not in o else bad)("a silent pool: no time set")

# replay protection: never before the last time set this boot or /etc/minimum-unixtime
open(T + "/min", "w").write("%d\n" % (now + 5 * 86400))
r, o = run({"zero": [at(3)], "one": [at(3)], "two": [at(3)]})
(ok if r is None and "SET" not in o and "FLAG" in o else bad)("earlier than minimum-unixtime: refused and flagged")
(ok if '"class": "failed"' in open(T + "/run/waybar.json").read() else bad)("panel status: failed")
os.remove(T + "/min")
open(T + "/build", "w").write("%d\n" % (now + 2 * 86400))
r, o = run({"zero": [at(3)], "one": [at(3)], "two": [at(3)]})
(ok if r is None and "SET" not in o else bad)("before the build date: refused")
open(T + "/build", "w").write("%d\n" % build)
os.path.exists(T + "/state") and os.remove(T + "/state")

# the real fetch: onion only, own circuit per request, unprivileged user, no redirects followed
src = open(I + "/usr/local/sbin/prestium-timesync").read()
(ok if '"runuser", "-u", HTP_USER' in src and "secrets.token_hex" in src and " -L" not in src and '"-L"' not in src else bad)("fetch: prestium-htp, fresh SOCKS username, no -L")

# boot clock randomization
bc = open(I + "/usr/local/sbin/prestium-bootclock").read()
(ok if "randbelow(100 * NS + 1) - 50 * NS" in bc else bad)("bootclock: uniform -50..+50 s with nanoseconds (inside i2pd's 60 s)")
import subprocess
o = subprocess.run([sys.executable, I + "/usr/local/sbin/prestium-bootclock", "--dry-run"], capture_output=True, text=True).stdout
m = re.search(r"by ([+-]\d+\.\d{9})s", o)
(ok if m and abs(float(m.group(1))) <= 50 else bad)("bootclock dry run: " + o.strip())

# units
U = I + "/etc/systemd/system"
b = open(U + "/prestium-bootclock.service").read()
for want in ("DefaultDependencies=no", "CapabilityBoundingSet=CAP_SYS_TIME\n", "PrivateNetwork=yes", "WantedBy=sysinit.target"):
    (ok if want in b else bad)("bootclock unit: " + want.strip())
(ok if re.search(r"^Before=.*tor@default\.service.*prestium-timesync\.service", b, re.M) else bad)("bootclock runs before Tor and the sync")
t = open(U + "/prestium-timesync.service").read()
for want in ("Type=simple", "Restart=on-failure", "StateDirectory=prestium-timesync", "/run/prestium/timesync"):
    (ok if want in t else bad)("timesync unit: " + want)
w = open(I + "/usr/share/prestium/build/systemd-wants.txt").read()
(ok if "sysinit.target.wants/prestium-bootclock.service" in w else bad)("bootclock enabled")
p = open(I + "/usr/share/prestium/build/perms.txt").read()
for f in ("/usr/local/sbin/prestium-bootclock", "/etc/systemd/system/prestium-bootclock.service", "/usr/share/prestium/timesync/pools.conf"):
    (ok if f in p else bad)("perms: " + f)

# panel: a clock dot that only shows while not synced
c = open(I + "/etc/xdg/waybar/config.jsonc").read()
(ok if '"custom/timesync"' in c and "/run/prestium/timesync/waybar.json" in c else bad)("waybar: clock-sync dot")
sys.exit(fail)
