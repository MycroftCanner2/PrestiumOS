#!/usr/bin/python3
# 2.1 (HiddenForge review): Landlock for Prestium's own Python helpers (prestium_landlock.py).
#  - the module: degrades (logs, returns False, never raises) without Landlock or on bad input; skips
#    missing paths; with Landlock it denies what is not listed (reads, writes, programs, TCP ports)
#  - each helper: calls landlock() first in main(), only for its installed copy, and its ruleset allows
#    what the helper does (checked in a child process on this machine's kernel, when it has Landlock)
#  - onion-grater and the Wayland broker do not use it (Landlock refuses them other processes' /proc)
import importlib.machinery, importlib.util, os, re, socket, subprocess, sys, tempfile
sys.dont_write_bytecode = True
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot"); LIB = os.path.join(I, "usr/local/lib/prestium")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; fail = 1; print("FAIL " + m)
def check(c, m): ok(m) if c else bad(m)
def load(path, name):
    ld = importlib.machinery.SourceFileLoader(name, path); sp = importlib.util.spec_from_loader(name, ld)
    m = importlib.util.module_from_spec(sp); ld.exec_module(m); return m
L = load(os.path.join(LIB, "prestium_landlock.py"), "prestium_landlock")
HELPERS = ["prestium-timesync", "prestium-mac-guard", "prestium-logs", "prestium-network-logs"]

## static: each helper
for h in HELPERS:
    src = open(os.path.join(I, "usr/local/sbin", h)).read()
    check(re.search(r"^def main\([^)]*\):\n    landlock\(\)\n", src, re.M), h + ": landlock() is the first line of main()")
    check('os.path.realpath(__file__) != "/usr/local/sbin/%s"' % h in src, h + ": only the installed copy restricts itself")
    check('"/usr/local/lib/prestium/prestium_landlock.py"' in src, h + ": loads the module by its installed path (no sys.path change)")
    m = re.search(r"^LANDLOCK = dict\(", src, re.M); check(m, h + ": has a LANDLOCK ruleset")
for h in ("prestium-onion-grater", "prestium-wl-broker"):
    check("prestium_landlock" not in open(os.path.join(I, "usr/local/sbin", h)).read(),
          h + ": no Landlock (it reads other processes' /proc/<pid>, which Landlock refuses)")
pm = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
check("0644 root root /usr/local/lib/prestium/prestium_landlock.py" in pm, "perms.txt: the module is 0644 root")
for h in HELPERS:
    u = open(os.path.join(I, "etc/systemd/system", h + ".service")).read()
    check(re.search(r"^NoNewPrivileges=yes$", u, re.M), h + ".service: NoNewPrivileges=yes (Landlock needs no_new_privs)")

## module without Landlock: logs and returns False
orig = L.abi_version
L.abi_version = lambda: 0
check(L.restrict("t") is False, "no Landlock in the kernel: restrict() returns False")
L.abi_version = lambda: 1 / 0
check(L.restrict("t") is False, "an internal error: restrict() returns False, no exception")
L.abi_version = orig

abi = L.abi_version()
if abi < 1:
    print("SKIP runtime checks: this kernel has no Landlock (ABI %d)" % abi)
else:
    ok("this kernel has Landlock ABI %d" % abi)
    T = tempfile.mkdtemp(prefix="ll-"); W = os.path.join(T, "w"); os.mkdir(W)
    secret = os.path.join(T, "secret"); open(secret, "w").write("x")
    exe = os.path.join(T, "prog"); open(exe, "w").write("#!/bin/sh\nexit 0\n"); os.chmod(exe, 0o755)
    lis = socket.socket(); lis.bind(("127.0.0.1", 0)); lis.listen(4); open_port = lis.getsockname()[1]
    other = socket.socket(); other.bind(("127.0.0.1", 0)); other.listen(4); other_port = other.getsockname()[1]
    PROBE = r'''
import json, os, socket, subprocess, sys
sys.dont_write_bytecode = True
import importlib.machinery, importlib.util
ld = importlib.machinery.SourceFileLoader("pl", sys.argv[1]); sp = importlib.util.spec_from_loader("pl", ld)
L = importlib.util.module_from_spec(sp); ld.exec_module(L)
rules = json.loads(sys.argv[2]); a = json.loads(sys.argv[3])
res = {"restricted": L.restrict("probe", **rules)}
def t(k, f):
    try: f(); res[k] = "allowed"
    except PermissionError: res[k] = "denied"
    except subprocess.CalledProcessError: res[k] = "denied"      # the program ran and could not
    except OSError as e: res[k] = "error %s" % e.errno
def conn(p):
    s = socket.socket(); s.settimeout(3); s.connect(("127.0.0.1", p)); s.close()
t("read_etc", lambda: open("/etc/passwd").read())
t("read_usr", lambda: open(os.__file__).read())
t("read_secret", lambda: open(a["secret"]).read())
t("write_allowed", lambda: (open(os.path.join(a["w"], ".t"), "w").write("1"), os.replace(os.path.join(a["w"], ".t"), os.path.join(a["w"], "t")), os.unlink(os.path.join(a["w"], "t"))))
t("write_other", lambda: open(os.path.join(os.path.dirname(a["secret"]), "new"), "w").write("1"))
t("devnull", lambda: subprocess.run(["/usr/bin/true"], stdout=subprocess.DEVNULL, check=True))
t("exec_usr", lambda: subprocess.run(["/usr/bin/env", "true"], check=True))
t("exec_other", lambda: subprocess.run([a["exe"]], check=True))
t("child_reads_secret", lambda: subprocess.run(["/usr/bin/cat", a["secret"]], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
t("tcp_listed", lambda: conn(a["open"]))
t("tcp_other", lambda: conn(a["other"]))
print(json.dumps(res))
'''
    import json
    def probe(rules):
        args = {"secret": secret, "w": W, "exe": exe, "open": open_port, "other": other_port}
        r = subprocess.run([sys.executable, "-I", "-c", PROBE, os.path.join(LIB, "prestium_landlock.py"), json.dumps(rules), json.dumps(args)],
                           capture_output=True, text=True, timeout=60)
        try: return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception: bad("probe failed: %s %s" % (r.stdout[-300:], r.stderr[-300:])); return {}
    # the module itself, with a test ruleset
    got = probe(dict(read=list(L.SYSTEM_READ), write=[W], connect_tcp=[open_port]))
    want = {"restricted": True, "read_etc": "allowed", "read_usr": "allowed", "read_secret": "denied", "write_allowed": "allowed",
            "write_other": "denied", "devnull": "allowed", "exec_usr": "allowed", "exec_other": "denied",
            # child_reads_secret: a program it starts can't read outside the ruleset either
            "child_reads_secret": "denied", "tcp_listed": "allowed"}
    for k, v in want.items():
        check(got.get(k) == v, "module: %s %s (%s)" % (k, v, got.get(k)))
    if abi >= 4: check(got.get("tcp_other") == "denied", "module: TCP to a port not listed is denied (%s)" % got.get("tcp_other"))
    got = probe(dict(read=list(L.SYSTEM_READ) + ["/nonexistent/prestium"], write=[W, "/nonexistent/x"]))
    check(got.get("restricted") is True and got.get("read_etc") == "allowed", "module: paths that don't exist are skipped")
    if abi >= 4: check(got.get("tcp_listed") == "denied", "module: no connect_tcp means no TCP at all (%s)" % got.get("tcp_listed"))
    # each helper's own ruleset: the system readable, programs from /usr, nothing in a home or /tmp
    for h in HELPERS:
        src = open(os.path.join(I, "usr/local/sbin", h)).read()
        ns = {}
        exec(re.search(r"^LANDLOCK = dict\((?:.|\n)*?\)\)?\n(?=\n)", src, re.M).group(0), ns)
        rules = ns["LANDLOCK"]
        got = probe(rules)
        check(got.get("restricted") is True, h + ": ruleset accepted by the kernel")
        for k in ("read_etc", "read_usr", "devnull", "exec_usr"):
            check(got.get(k) == "allowed", "%s: %s allowed (%s)" % (h, k, got.get(k)))
        for k in ("read_secret", "write_other", "exec_other", "write_allowed"):
            check(got.get(k) == "denied", "%s: %s denied (%s)" % (h, k, got.get(k)))
        if abi >= 4:
            check(got.get("tcp_other") == "denied", "%s: TCP to another port denied (%s)" % (h, got.get("tcp_other")))
        check(not any(p.startswith(("/home", "/root", "/tmp", "/media", "/opt")) for k in ("read", "write", "execute") for p in rules.get(k, ())),
              h + ": nothing in /home, /root, /tmp, /media or /opt")
        check(tuple(rules.get("execute", ("/usr",))) == ("/usr",), h + ": programs only from /usr")
    ts = open(os.path.join(I, "usr/local/sbin/prestium-timesync")).read()
    check("connect_tcp=(9050,)" in ts, "prestium-timesync: TCP only to Tor's SOCKS port 9050")
    lis.close(); other.close()
    subprocess.run(["rm", "-rf", T])
print("test_landlock: " + ("OK" if not fail else "FAILED")); sys.exit(fail)
