#!/usr/bin/python3
"""Security review F-07: setting the clock by hand and reseeding I2P happen only after the person at
the screen confirms them in a Wayland broker dialog (on the compositor's full socket, accessibility
off), as Tor's and I2P's settings do; neither has a sudo rule any more. Runs the broker's code with
stubs (no compositor, no root), and the prestium-wl client against a fake broker socket."""
import os, runpy, socket, subprocess, sys, tempfile, threading

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(H, "config/includes.chroot")
BROKER = os.path.join(I, "usr/local/sbin/prestium-wl-broker")
CLIENT = os.path.join(I, "usr/local/bin/prestium-wl")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)
T = tempfile.mkdtemp(prefix="prestium-f07-")

# ---------------------------------------------------------------- no sudo rules
for f in ("prestium-set-clock", "prestium-i2p-reseed"):
    check(not os.path.exists(os.path.join(I, "etc/sudoers.d", f)), "no sudoers file %s" % f)
sud = "".join(open(os.path.join(I, "etc/sudoers.d", f)).read() for f in os.listdir(os.path.join(I, "etc/sudoers.d")))
check("prestium-set-clock" not in sud and "prestium-i2p-reseed" not in sud, "no sudoers rule names either helper")

# ---------------------------------------------------------------- broker
g = runpy.run_path(BROKER, run_name="prestium_wl_broker_f07_test")["Session"].set_clock.__globals__
g["log"] = lambda *a, **k: None
REC = os.path.join(T, "calls")
FAKE = os.path.join(T, "fake-helper")
open(FAKE, "w").write("""#!/bin/sh
printf '%%s|%%s\\n' "$*" "${SUDO_USER:-}" >> %s
echo "STEP: working"
echo "${FAKE_LAST:-done}"
exit ${FAKE_RC:-0}
""" % REC)
os.chmod(FAKE, 0o755)
g["SET_CLOCK"] = FAKE; g["I2P_RESEED"] = FAKE; g["TOR_RUNNER"] = ""
check('SET_CLOCK = _test_env("PRESTIUM_WL_SET_CLOCK", "/usr/local/sbin/prestium-set-clock")' in open(BROKER).read(), "installed broker runs /usr/local/sbin/prestium-set-clock")
check('TOR_RUNNER = _test_env("PRESTIUM_WL_TOR_RUNNER", "/usr/bin/systemd-run")' in open(BROKER).read(), "helpers run as transient services (ProtectClock, no AF_INET in the broker)")
S = g["Session"]
def fake():
    s = object.__new__(S)
    s.uid, s.gid, s.groups, s.user = os.getuid(), os.getgid(), [], "user"
    s.home = s.rt = s.empty = s.apps = "/tmp"
    s.kids = {}; s.lock = threading.Lock()
    for k in ("pw_busy", "i2p_busy", "tor_busy", "clock_busy", "reseed_busy"):
        setattr(s, k, threading.Lock())
    return s
src = open(BROKER).read()
check("self.clock_busy = threading.Lock(); self.reseed_busy = threading.Lock()" in src, "Session has clock and reseed dialog locks")
dialogs = []; answer = [1]
def rec_spawn(self, argv, wait=False, capture=False, timeout=None, key=None, extra_env=None):
    dialogs.append((argv, dict(extra_env or {})))
    return (answer[0], "") if wait or capture else None
S.spawn = rec_spawn
def calls():
    try:
        out = open(REC).read().splitlines(); os.unlink(REC); return out
    except FileNotFoundError:
        return []
def text_of(a): return a[a.index("--text") + 1]
s = fake()

# set-clock
for bad_req in ("", "2026-11-10", "2026-11-10 14:30 x", "-f /etc/shadow x", "2026-11-10 14:30\n", "+1 day", "2026-11-10  14:30"):
    n = len(dialogs)
    r = s.set_clock(bad_req, 0)
    check(r.startswith("error invalid") and len(dialogs) == n and calls() == [], "set-clock %r refused without a dialog" % bad_req)
answer[0] = 1
r = s.set_clock("2026-11-10 14:30", os.getpid())
check(r == "error cancelled" and calls() == [], "set-clock declined at the dialog: the helper never runs (%r)" % r)
a, env = dialogs[-1]
check(a[0] == "zenity" and "--question" in a and "--no-markup" in a and env.get("NO_AT_BRIDGE") == "1",
      "clock dialog: zenity question on the full socket, no markup, accessibility off")
t = text_of(a)
check("2026-11-10 14:30 UTC" in t and "Asked for by:" in t and "choose Cancel" in t, "clock dialog shows the time and the requester")
check(a[a.index("--ok-label") + 1] == "Set clock", "clock dialog: Set clock button")
answer[0] = 0
r = s.set_clock("2026-11-10 14:30:05", 0)
c = calls()
check(r == "ok done" and c == ["2026-11-10 14:30:05|"], "confirmed: the helper gets exactly the date and the time (%r, %r)" % (r, c))
os.environ["FAKE_RC"] = "1"; os.environ["FAKE_LAST"] = "prestium-set-clock: 2020-01-01 00:00 UTC is before this image was built; refusing"
r = s.set_clock("2026-11-10 14:30", 0); calls()
check(r.startswith("error ") and "before this image was built" in r, "the helper's refusal is passed back (%r)" % r)
del os.environ["FAKE_RC"], os.environ["FAKE_LAST"]
s.clock_busy.acquire()
check(s.set_clock("2026-11-10 14:30", 0) == "error a clock dialog is already open" and calls() == [], "one clock dialog at a time")
s.clock_busy.release()

# i2p-reseed
answer[0] = 1
r = s.i2p_reseed("", 0)
check(r == "error cancelled" and calls() == [], "reseed declined: the helper never runs")
check("over Tor" in text_of(dialogs[-1][0]) and dialogs[-1][0][dialogs[-1][0].index("--ok-label") + 1] == "Reseed", "reseed dialog (over Tor)")
for bad_req in ("--file relative.su3", "--file /a/../etc/shadow", "--file /x\ny", "--other", "--file "):
    n = len(dialogs)
    r = s.i2p_reseed(bad_req, 0)
    check(r.startswith("error invalid") and len(dialogs) == n, "reseed %r refused without a dialog" % bad_req)
answer[0] = 0
prog = []
r = s.i2p_reseed("--file /home/user/Downloads/i2pseeds.su3", 0, emit=prog.append)
c = calls()
check(r == "ok rc 0" and c == ["--file /home/user/Downloads/i2pseeds.su3|user"], "confirmed: --file PATH, read as the desktop user (SUDO_USER) (%r, %r)" % (r, c))
check("/home/user/Downloads/i2pseeds.su3" in text_of(dialogs[-1][0]), "file dialog names the file")
check("progress STEP: working" in prog, "the helper's STEP lines reach the caller (%r)" % prog)
os.environ["FAKE_RC"] = "2"
r = s.i2p_reseed("", 0); calls(); del os.environ["FAKE_RC"]
check(r == "error rc 2", "the helper's exit code is passed back (%r)" % r)

# dispatch
check('if cmd.startswith("set-clock "):' in src and 'cmd == "i2p-reseed" or cmd.startswith("i2p-reseed ")' in src, "dispatch routes set-clock and i2p-reseed")

# ---------------------------------------------------------------- prestium-wl client
base = os.path.join(T, "wl"); os.makedirs(base)
srv = socket.socket(socket.AF_UNIX); srv.bind(os.path.join(base, "broker")); srv.listen(4)
got = []
def serve():
    while True:
        try:
            cn, _ = srv.accept()
        except OSError:
            return
        d = b""
        while not d.endswith(b"\n"):
            x = cn.recv(4096)
            if not x:
                break
            d += x
        got.append(d.decode().strip())
        cn.sendall(b"progress STEP: x\nok rc 0\n"); cn.close()
threading.Thread(target=serve, daemon=True).start()
def client(*a):
    return subprocess.run([sys.executable, CLIENT] + list(a), capture_output=True, text=True,
                          env=dict(os.environ, PRESTIUM_WL_BASE=base), timeout=30)
p = client("set-clock", "2026-11-10", "14:30")
check(p.returncode == 0 and got[-1] == "set-clock 2026-11-10 14:30", "client: set-clock request (%r)" % got[-1:])
p = client("i2p-reseed")
check(p.returncode == 0 and got[-1] == "i2p-reseed" and "progress STEP: x" in p.stdout, "client: i2p-reseed, progress printed")
p = client("i2p-reseed", "--file", "/home/user/a.su3")
check(got[-1] == "i2p-reseed --file /home/user/a.su3", "client: i2p-reseed --file")
n = len(got)
for a in (["i2p-reseed", "--file", "rel"], ["set-clock", "2026-11-10"], ["i2p-reseed", "x"]):
    p = client(*a)
    check(p.returncode == 2 and len(got) == n, "client refuses %r" % a)
srv.close()
subprocess.run(["rm", "-rf", T])
sys.exit(fail)
