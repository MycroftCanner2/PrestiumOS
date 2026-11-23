#!/usr/bin/env python3
"""Prestium 2.1: Network > Refresh reseed (via Tor), prestium-i2p-reseed.

  * Every network step runs in a transient systemd unit as prestium-htp (systemd-run), never as a child
    of the helper: started from the panel's I2P button, the helper inherits the panel's sandbox
    (prestium-wl-broker.service, RestrictAddressFamilies=AF_UNIX AF_NETLINK), where socket(AF_INET)
    fails, so "uid prestium-htp cannot reach Tor's SOCKS port" although Tor was running.
  * The fallback: StormyCloud first, then the other reseed servers, each over Tor and pinned to its
    signer; a server that is down, slow, has a bad TLS certificate, or serves an invalid, wrongly signed
    or too old su3 is skipped with a reason; when all fail the current file stays (exit 2) and the
    reasons are listed; no clearnet attempt ever.
Offline: a patched copy with stubs for systemd-run (which plays the network), verify-su3, safefile,
systemctl and the onion-grater bootstrap query."""
import os, re, shutil, stat, subprocess, sys, tempfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
HELPER = os.path.join(I, "usr/local/sbin/prestium-i2p-reseed")
GUI = os.path.join(I, "usr/local/bin/prestium-i2p-reseed-gui")
fails = 0


def check(c, msg):
    global fails
    print(("OK   " if c else "FAIL ") + msg)
    fails += 0 if c else 1


src = open(HELPER).read()
sources = re.search(r"\nSOURCES=\(\n(.*?)\n\)\n", src, re.S).group(1).split("\n")
sources = [l.strip().strip('"').split(" ", 1) for l in sources]
hosts = [re.match(r"https://([^/]+)/", u).group(1) for u, _ in sources]

print("== static: the source list and the network path")
check(hosts[0] == "reseed.stormycloud.org", "StormyCloud is tried first")
check(len(hosts) >= 6 and len(set(hosts)) == len(hosts), "%d distinct reseed servers to fall back to" % len(hosts))
check(all(u.startswith("https://") and u.endswith("/i2pseeds.su3") for u, _ in sources), "every source is an HTTPS .su3 URL")
check(all(s and s != "any" and all(re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+", x) for x in s.split(","))
          for _, s in sources), "every source is pinned to named signers (never 'any')")
code = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith("#"))
check('runuser -u "$TORUID"' not in code and "runuser -u prestium-htp" not in code,
      "no runuser as prestium-htp: the network steps are not children of the helper")
check(code.count("/usr/bin/curl") == 1 and re.search(r"tor_run \d+ /usr/bin/curl", code),
      "curl runs only through tor_run (systemd-run)")
check("tor_run 20 /usr/bin/timeout 10 /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/9050'" in code,
      "the SOCKS check runs through tor_run too")
for p in ('User=$TORUID', 'IPAddressDeny=any', 'IPAddressAllow=127.0.0.1', 'RestrictAddressFamilies=AF_INET AF_UNIX',
          'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'ProtectHome=yes', 'ProtectSystem=strict'):
    check(('-p "%s"' % p) in code or ("-p %s " % p) in code or ('-p "%s" ' % p) in code, "transient unit sets %s" % p)
check('--proxy "socks5h://' in code and "@127.0.0.1:9050" in code and "--noproxy ''" in code
      and "--proto =https" in code and "--proto-redir =https" in code and "curl -q " in code,
      "curl: socks5h through 127.0.0.1:9050 only, no proxy bypass, HTTPS only (also redirects), no curlrc")

# ---------------------------------------------------------------- patched copy
W = tempfile.mkdtemp()
B = os.path.join(W, "bin"); os.makedirs(B)
VAR = os.path.join(W, "var/lib/i2pd"); os.makedirs(os.path.join(VAR, "netDb"))
LOG = os.path.join(W, "log")


def stub(name, body):
    p = os.path.join(B, name)
    open(p, "w").write("#!/bin/bash\n" + body)
    os.chmod(p, 0o755)
    return p


# systemd-run: records its properties, then plays the network from $NET (host=behaviour,...)
stub("systemd-run", r'''
props=(); while [ "$1" != "--" ]; do props+=("$1"); shift; done; shift
printf 'RUN %s ::' "${props[*]}" >> "$LOG"; printf ' %q' "$@" >> "$LOG"; echo >> "$LOG"
case " ${props[*]} " in *" User=prestium-htp "*) ;; *) echo "not as prestium-htp" >&2; exit 99;; esac
if [ "$1" = /usr/bin/timeout ]; then [ "${SOCKS:-ok}" = ok ] && exit 0
  echo "bash: line 1: socket: Address family not supported by protocol" >&2; exit 1; fi
url=${*: -1}; host=${url#https://}; host=${host%%/*}
b=$(tr ',' '\n' <<<"$NET" | sed -n "s/^$host=//p"); b=${b:-down}
case $b in
  down) echo "curl: (97) cannot complete SOCKS5 connection to $host. (4)" >&2; exit 97 ;;
  slow) echo "curl: (28) Operation timed out" >&2; exit 28 ;;
  tls)  echo "curl: (60) SSL certificate problem: certificate has expired" >&2; exit 60 ;;
  http) echo "curl: (22) The requested URL returned error: 503" >&2; exit 22 ;;
  *) printf '%s' "$b" ;;
esac
''')
stub("verify-su3", r'''
signers=; while [ $# -gt 2 ]; do case $1 in --signers) signers=$2; shift;; esac; shift; done
c=$(cat "$1")
case $c in
  good:*) s=${c#good:}; case ",$signers," in *",$s,"*) echo "OK SU3 signer=$s"; exit 0;; esac
          echo "ERROR: su3: unexpected signer '$s' (allowed: $signers)"; exit 1 ;;
  old:*)  echo "ERROR: su3: version is 40.0 days old (more than 14)"; exit 1 ;;
  unsigned:*) echo "ERROR: su3: signature does not verify against the signer's certificate"; exit 1 ;;
  *) echo "ERROR: su3: bad magic (not an SU3 file)"; exit 1 ;;
esac
''')
stub("safefile", r'''
d=${2/#\/var\/lib\/i2pd/$VAR}
case $1 in read) cat "$d/$3" ;; write) cat > "$d/$3" ;; esac
''')
stub("systemctl", 'echo "systemctl $*" >> "$LOG"\n')
stub("tor-bootstrap", 'echo "${TORPCT:-100}"\n')

s = src
for a, b in [
    ('if [ "$(id -u)" -ne 0 ]; then die 1', 'if false; then die 1'),
    ("PATH=/usr/sbin:/usr/bin:/sbin:/bin", "PATH=%s:/usr/sbin:/usr/bin:/sbin:/bin" % B),
    ("/usr/local/lib/prestium/safefile", os.path.join(B, "safefile")),
    ("VERIFY=/usr/local/lib/prestium/verify-su3", "VERIFY=" + os.path.join(B, "verify-su3")),
    ('python3 -I "$VERIFY"', '"$VERIFY"'),
    ("NETDB=/var/lib/i2pd/netDb", "NETDB=" + os.path.join(VAR, "netDb")),
    ("/run/prestium-i2p-reseed.lock", os.path.join(W, "lock")),
    ("mktemp -d /run/prestium-i2p-reseed.XXXXXX", "mktemp -d %s/t.XXXXXX" % W),
    ("env -i PATH=/usr/bin:/bin PYTHONNOUSERSITE=1 /usr/bin/python3 /usr/local/lib/prestium/tor-bootstrap.py",
     os.path.join(B, "tor-bootstrap")),
    ("install -d -o 2000 -g 2000 -m", "install -d -m"),
    ("sleep 5", "sleep 0"), ("sleep 2", "sleep 0"),
]:
    check(a in s, "patch point present: " + a[:60]); s = s.replace(a, b)
H = os.path.join(W, "prestium-i2p-reseed")
open(H, "w").write(s); os.chmod(H, 0o755)
CONF = "[reseed]\nverify = true\nfile = /var/lib/i2pd/i2pseeds.su3\n"
open(os.path.join(VAR, "i2pd.conf"), "w").write(CONF)


def run(net, **env):
    open(os.path.join(VAR, "i2pseeds.su3"), "w").write("previous")
    open(LOG, "w").close()
    e = dict(os.environ, LOG=LOG, VAR=VAR, NET=",".join("%s=%s" % kv for kv in net.items()), **env)
    p = subprocess.run(["bash", H], capture_output=True, text=True, env=e, timeout=120)
    return p.returncode, p.stdout + p.stderr, open(LOG).read(), open(os.path.join(VAR, "i2pseeds.su3")).read()


print("== StormyCloud works: installed from it, one download")
rc, out, log, dest = run({"reseed.stormycloud.org": "good:admin@stormycloud.org"})
check(rc == 0 and dest == "good:admin@stormycloud.org", "installed (rc %d)" % rc)
check(log.count("/usr/bin/curl") == 1, "only StormyCloud was asked")
check("systemctl restart i2pd" in log or "systemctl start i2pd" in log, "i2pd restarted")

print("== StormyCloud down: the next server over Tor")
rc, out, log, dest = run({hosts[1]: "good:" + sources[1][1].split(",")[0]})
check(rc == 0 and dest.startswith("good:"), "installed from %s (rc %d)" % (hosts[1], rc))
check("NOTE: download from reseed.stormycloud.org failed: Tor could not connect" in out, "StormyCloud's failure is explained")

print("== every way a server can fail, then one good server last")
bad = ["down", "slow", "tls", "http", "html", "old:x", "unsigned:x", "good:someone@else.example"]
net = {h: bad[i % len(bad)] for i, h in enumerate(hosts[:-1])}
net[hosts[-1]] = "good:" + sources[-1][1].split(",")[0]
rc, out, log, dest = run(net)
check(rc == 0 and dest == net[hosts[-1]], "the last server's file is installed (rc %d)" % rc)
check(log.count("/usr/bin/curl") == len(hosts), "all %d servers were tried in order" % len(hosts))
order = re.findall(r"https://([^/]+)/i2pseeds\.su3", log)
check(order == hosts, "tried in the listed order")

print("== all servers fail: nothing changes, every reason listed")
net = {h: bad[i % len(bad)] for i, h in enumerate(hosts)}
rc, out, log, dest = run(net)
check(rc == 2, "exit 2 (rc %d)" % rc)
check(dest == "previous" and "systemctl" not in log, "the current reseed file is kept, i2pd untouched")
fl = [l for l in out.split("\n") if l.startswith("FAIL: ")]
check(len(fl) == len(hosts), "one FAIL line per server (%d)" % len(fl))
for word in ("Tor could not connect", "timed out", "certificate is expired", "HTTP error", "bad magic",
             "days old", "signature does not verify", "unexpected signer"):
    check(any(word in l for l in fl), "reason shown: " + word)
check(re.search(r"^ERROR: no reseed server gave a valid file over Tor", out, re.M) is not None, "final error says so")

print("== SOCKS port unreachable: exit 3, no download, a clear reason")
rc, out, log, dest = run({}, SOCKS="fail")
check(rc == 3 and "/usr/bin/curl" not in log and dest == "previous", "exit 3, nothing downloaded (rc %d)" % rc)
check("Address family not supported by protocol" in out and "after 3 tries" in out, "the reason is in the message")
print("== Tor not bootstrapped: exit 3 before any network step")
rc, out, log, dest = run({}, TORPCT="45")
check(rc == 3 and "RUN" not in log and "45%" in out, "exit 3 (rc %d)" % rc)

print("== every network step was a prestium-htp unit with the sandbox")
rc, out, log, dest = run({"reseed.stormycloud.org": "good:admin@stormycloud.org"})
runs = [l for l in log.split("\n") if l.startswith("RUN ")]
check(runs and all("User=prestium-htp" in l and "IPAddressAllow=127.0.0.1" in l and "IPAddressDeny=any" in l
                   for l in runs), "%d units, all as prestium-htp, IPv4 to 127.0.0.1 only" % len(runs))

print("== F-07: a file is read as the desktop user named by the broker, never as root")
src_f = os.path.join(W, "f.su3"); open(src_f, "w").write("x")
e = dict(os.environ, LOG=LOG, VAR=VAR, NET="")
e.pop("SUDO_USER", None)
p = subprocess.run(["bash", H, "--file", src_f], capture_output=True, text=True, env=e, timeout=60)
check(p.returncode != 0 and "no desktop user to read the file as" in p.stdout + p.stderr, "no SUDO_USER: refused (rc %d)" % p.returncode)
p = subprocess.run(["bash", H, "--file", src_f], capture_output=True, text=True, env=dict(e, SUDO_USER="root"), timeout=60)
check(p.returncode != 0 and "no desktop user" in p.stdout + p.stderr, "SUDO_USER=root: refused")
check("exec sudo" not in code, "the helper no longer re-runs itself through sudo")
check(not os.path.exists(os.path.join(I, "etc/sudoers.d/prestium-i2p-reseed")), "no sudoers rule for the helper (F-07)")
check("/etc/sudoers.d/prestium-i2p-reseed" not in open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read(), "perms.txt: no sudoers entry")

print("== the GUI lists the reasons when every server failed")
g = open(GUI).read()
check('l.startswith("FAIL: ")' in g and "StormyCloud and reseed.onion.im" not in g, "rc 2 dialog shows the FAIL lines")
check('[WL, "i2p-reseed"] + args' in g and '"sudo"' not in g, "F-07: the GUI asks the broker (prestium-wl i2p-reseed), not sudo")
check("rc == 3" in g and '"error cancelled"' in g, "F-07: Cancel in the broker's dialog ends quietly")

shutil.rmtree(W)
print("%d failure(s)" % fails)
sys.exit(1 if fails else 0)
