#!/usr/bin/python3
"""2.1 (review V-1, V-2): the broker's confirmation and password dialogs run with accessibility off,
so no process of the user can press Apply or fill in the password form through AT-SPI; a dialog that
times out is closed; the I2P dialog names the program that asked. Runs the broker's code with stubs
(no compositor, no root)."""
import os, re, runpy, socket, subprocess, sys, threading

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(H, "config/includes.chroot/usr/local/sbin/prestium-wl-broker")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1

g = runpy.run_path(SRC, run_name="prestium_wl_broker_test")["Session"].i2p_apply.__globals__  # the live module dict
src = open(SRC).read()
g["log"] = lambda *a, **k: None

# every zenity window the broker opens goes through dialog()
z = [l.strip() for l in src.splitlines() if '"zenity"' in l]
(ok if z and all("self.dialog(" in l for l in z) else bad)("every zenity call uses dialog() (%d)" % len(z))
env = g["DIALOG_ENV"]
(ok if env.get("GTK_A11Y") == "none" and env.get("NO_AT_BRIDGE") == "1" else bad)("dialogs: GTK_A11Y=none, NO_AT_BRIDGE=1")

S = g["Session"]
def fake():
    s = object.__new__(S)
    s.uid, s.gid, s.groups, s.user = os.getuid(), os.getgid(), [], "user"
    s.home = s.rt = s.empty = s.apps = "/tmp"
    s.kids = {}; s.lock = threading.Lock(); s.pw_busy = threading.Lock(); s.i2p_busy = threading.Lock()
    return s

calls = []
def rec_spawn(self, argv, wait=False, capture=False, timeout=None, key=None, extra_env=None):
    calls.append((argv, dict(extra_env or {})))
    return (1, "") if wait or capture else None
S.spawn = rec_spawn
s = fake()
r = s.i2p_apply('{"hops": 3, "share": "low", "outproxy": "acetone"}', os.getpid())
c = [e for a, e in calls if a[0] == "zenity"]
(ok if r == "error cancelled" and c and c[0].get("GTK_A11Y") == "none" else bad)("I2P dialog env (%r, %r)" % (r, c))
text = calls[-1][0][calls[-1][0].index("--text") + 1] if calls else ""
(ok if "Asked for by: " + os.path.realpath(sys.executable) in text else bad)("I2P dialog names the requester")

calls.clear()
g["SESSION_PASSWORD"] = "/bin/false"   # status prints nothing: not set yet
r = s.set_password()
c = [e for a, e in calls if a[0] == "zenity"]
(ok if r == "error cancelled" and c and all(e.get("GTK_A11Y") == "none" for e in c) else bad)("password form env (%r)" % r)

# R-1: everything the broker starts (waybar, wdisplays, ...) gets accessibility off, and it can't be undone
e = fake().env({"GTK_A11Y": "atspi", "NO_AT_BRIDGE": "0"})
(ok if e["GTK_A11Y"] == "none" and e["NO_AT_BRIDGE"] == "1" else bad)("env(): a11y off for every broker child")

req = g["requester"]
pr = g["printable"]
(ok if pr("/tmp/x\nOutproxy: Acetone\u202e") == "/tmp/x?Outproxy: Acetone?" and len(pr("a" * 999)) == 200 else bad)(
    "requester: control and bidi characters replaced, length capped")
me = req(os.getpid())
(ok if "running " + sys.argv[0] + " (self-reported)" in me or sys.argv[0] in me else bad)("requester: script path for interpreters (%s)" % me)
(ok if "\n" not in me else bad)("requester: one line")
so = g["script_of"]
cases = [("/usr/bin/python3.13", [b"-I", b"-W", b"ignore", b"x.py"], "x.py"),
         ("/usr/bin/python3.13", [b"-X", b"utf8", b"-I", b"/usr/local/bin/prestium-wl", b"i2p-apply"], "/usr/local/bin/prestium-wl"),
         ("/usr/bin/python3.13", [b"-c", b"print(1)"], "-c"),
         ("/usr/bin/python3.13", [b"-m", b"http.server"], "-m http.server"),
         ("/usr/bin/bash", [b"-c", b"exec x", b"name"], "-c"),
         ("/usr/bin/perl", [b"-w", b"s.pl"], "s.pl")]
for exe, argv, want in cases:
    (ok if so(exe, argv) == want else bad)("script_of %s %r -> %r (%r)" % (exe, argv, want, so(exe, argv)))
(ok if pr("a\u3164b\u200bc\u2800d\u115f") == "a?b?c?d?" else bad)("printable: fillers and zero-width replaced")
(ok if req(0) == "unknown" and req(10 ** 9) == "unknown" else bad)("requester: unknown pid")
# a child of this test, so its parent is readable here whoever started the test
out = subprocess.run([sys.executable, "-c", "import runpy, os, sys; print(runpy.run_path(sys.argv[1], "
                      "run_name='t')['requester'](os.getpid()))", SRC], capture_output=True, text=True).stdout
(ok if ", started by " in out and "test_broker_dialogs.py (self-reported)" in out else bad)("requester: process and parent (%s)" % out.strip())

# V-2: a dialog that times out is killed, not left on screen
del S.spawn
S.spawn = runpy.run_path(SRC, run_name="prestium_wl_broker_test2")["Session"].spawn
s = fake()
a, b = socket.socketpair()
class Sock:
    def detach(self): return a.detach()
s.connect_full = lambda: (Sock(), 0)
s.groups = None   # setgroups needs root; the broker passes the user's groups
pidf = "/tmp/prestium-broker-dialog-%d" % os.getpid()
try:
    s.spawn(["sh", "-c", 'echo $$ > "$0"; exec sleep 30', pidf], wait=True, timeout=0.5)
    bad("timeout raised")
except subprocess.TimeoutExpired:
    pid = int(open(pidf).read())
    alive = os.path.exists("/proc/%d" % pid) and open("/proc/%d/stat" % pid).read().split()[2] != "Z"
    (ok if not alive else bad)("timed-out dialog is killed")
finally:
    try: os.unlink(pidf)
    except OSError: pass
    b.close()
sys.exit(fail)
