#!/usr/bin/python3
"""2.1 (review: a local program could retarget Tor without asking): prestium-tor-mode apply, cancel,
revert and reconnect run only after the person at the screen confirms them in a broker dialog on the
compositor's full socket, as I2P's settings do. sudo allows only status and features. Runs the broker's
code with stubs (no compositor, no root, no Tor), the prestium-wl client against a fake broker socket,
the assistant's broker() against a fake prestium-wl, and the helper's new "check" command."""
import ast, importlib.machinery, importlib.util, io, json, os, runpy, shutil, socket, stat, subprocess
import sys, tempfile, threading
from contextlib import redirect_stdout

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(H, "config/includes.chroot")
BROKER = os.path.join(I, "usr/local/sbin/prestium-wl-broker")
CLIENT = os.path.join(I, "usr/local/bin/prestium-wl")
ASSIST = os.path.join(I, "usr/local/bin/prestium-tor-assistant")
HELPER = os.path.join(I, "usr/local/sbin/prestium-tor-mode")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)
T = tempfile.mkdtemp(prefix="prestium-tor-confirm-")

# ---------------------------------------------------------------- sudoers
sud = open(os.path.join(I, "etc/sudoers.d/prestium-tor-mode")).read()
rules = [l for l in sud.splitlines() if l and not l.startswith("#")]
check(rules == ["user ALL=(root) NOPASSWD: /usr/local/sbin/prestium-tor-mode status, /usr/local/sbin/prestium-tor-mode features"],
      "sudoers: status and features only (%r)" % rules)
check(not any(c in " ".join(rules) for c in ("mode apply", "mode cancel", "mode revert", "mode reconnect")),
      "sudoers: apply, cancel, revert, reconnect removed")
visudo = shutil.which("visudo") or ("/usr/sbin/visudo" if os.path.exists("/usr/sbin/visudo") else None)
if visudo:
    r = subprocess.run([visudo, "-cf", os.path.join(I, "etc/sudoers.d/prestium-tor-mode")], capture_output=True, text=True)
    check(r.returncode == 0, "visudo accepts it (%s)" % (r.stdout + r.stderr).strip())
else:
    print("SKIP visudo missing")
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
check("0440 root root /etc/sudoers.d/prestium-tor-mode" in perms, "perms.txt: sudoers file 0440")

# ---------------------------------------------------------------- the helper's "check"
loader = importlib.machinery.SourceFileLoader("tormode_check", HELPER)
spec = importlib.util.spec_from_loader(loader.name, loader); hm = importlib.util.module_from_spec(spec)
loader.exec_module(hm)
hm.BUILTIN = os.path.join(I, "usr/share/prestium/tor-bridges-builtin.json")
def helper(cmd, req):
    sys.argv = ["prestium-tor-mode", cmd]
    old_in, old_euid = sys.stdin, os.geteuid
    sys.stdin = io.StringIO(req if isinstance(req, str) else json.dumps(req))
    os.geteuid = lambda: 0
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            try:
                rc = hm.main()
            except SystemExit as e:
                rc = e.code
    finally:
        sys.stdin, os.geteuid = old_in, old_euid
    lines = buf.getvalue().strip().splitlines()
    return rc, json.loads(lines[-1]) if lines else {}
FP = "A" * 40
line = "obfs4 192.0.2.7:443 %s cert=abc iat-mode=0" % FP
rc, out = helper("check", {"mode": "obfs4", "bridges": "Bridge " + line + "\n# comment\n", "builtin": False})
check(rc == 0 and out == {"ok": True, "mode": "obfs4", "builtin": False, "bridges": [line], "user_bridges": 1},
      "helper check: normalised request, nothing applied (%r)" % out)
rc, out = helper("check", {"mode": "obfs4", "bridges": "obfs4 192.0.2.7:443 nofp", "builtin": False})
check(rc != 0 and not out.get("ok") and "invalid obfs4 bridge line" in out.get("error", ""), "helper check: bad bridge line refused")
rc, out = helper("check", "[1, 2]")
check(rc != 0 and out.get("error") == "bad request", "helper check: a non-object request is refused, no traceback")
rc, out = helper("check", {"mode": "snowflake", "builtin": True})
check(rc == 0 and out["user_bridges"] == 0 and len(out["bridges"]) >= 1, "helper check: Snowflake with the built-in bridges")
src = open(HELPER).read()
check("sudoers.d/prestium-tor-mode" in src and "Wayland" in src, "helper header: run by the broker, not sudo")

# ---------------------------------------------------------------- broker
g = runpy.run_path(BROKER, run_name="prestium_wl_broker_tor_test")["Session"].tor_mode.__globals__
g["log"] = lambda *a, **k: None
REC = os.path.join(T, "helper-calls")
FAKE = os.path.join(T, "fake-tor-mode")
open(FAKE, "w").write("""#!/usr/bin/python3
import json, os, sys
cmd = sys.argv[1]; data = sys.stdin.read()
with open(REC_PATH, "a") as f:
    f.write(json.dumps([cmd, data, os.environ.get("RUNNER_SAW", "")]) + "\\n")
res = json.loads(os.environ.get("FAKE_RESULT") or "null")
if cmd == "check":
    req = json.loads(data)
    if req.get("bridges", "").startswith("bad"):
        print(json.dumps({"ok": False, "error": "invalid obfs4 bridge line: bad"})); sys.exit(1)
    lines = [l for l in req.get("bridges", "").splitlines() if l]
    print(json.dumps({"ok": True, "mode": req["mode"], "builtin": req.get("builtin", True),
                      "bridges": lines + (["obfs4 198.51.100.1:80 " + "B" * 40 + " cert=x"] if req.get("builtin") else []),
                      "user_bridges": len(lines)}))
    sys.exit(0)
print(json.dumps({"event": "phase", "phase": "stopping", "message": "Stopping Tor…"}), flush=True)
print("not json", flush=True)
print(json.dumps(res or {"ok": True, "mode": "obfs4"}), flush=True)
""".replace("REC_PATH", repr(REC)))
os.chmod(FAKE, 0o755)
g["TOR_MODE"] = FAKE; g["TOR_RUNNER"] = ""
g["TOR_STATE_DIR"] = os.path.join(T, "run-prestium")
os.makedirs(os.path.join(T, "run-prestium", "tor-mode.prev"))
json.dump({"mode": "snowflake"}, open(os.path.join(T, "run-prestium", "tor-mode.json"), "w"))
json.dump({"mode": "direct"}, open(os.path.join(T, "run-prestium", "tor-mode.prev", "state"), "w"))
S = g["Session"]
def fake():
    s = object.__new__(S)
    s.uid, s.gid, s.groups, s.user = os.getuid(), os.getgid(), [], "user"
    s.home = s.rt = s.empty = s.apps = "/tmp"
    s.kids = {}; s.lock = threading.Lock(); s.pw_busy = threading.Lock(); s.i2p_busy = threading.Lock()
    s.tor_busy = threading.Lock()
    return s
check("self.tor_busy = threading.Lock()" in open(BROKER).read(), "Session has a Tor dialog lock")
dialogs, notes = [], []
answer = [1]
def rec_spawn(self, argv, wait=False, capture=False, timeout=None, key=None, extra_env=None):
    dialogs.append((argv, dict(extra_env or {})))
    return (answer[0], "") if wait or capture else None
S.spawn = rec_spawn
S.as_user = lambda self, argv, input=None, timeout=10: notes.append(argv) or (0, "")
def calls():
    try:
        with open(REC) as f:
            out = [json.loads(l) for l in f]
        os.unlink(REC)
        return out
    except FileNotFoundError:
        return []
def text_of(argv): return argv[argv.index("--text") + 1]

s = fake()
req = {"mode": "obfs4", "bridges": line, "builtin": True}
answer[0] = 1; dialogs.clear()
r = s.tor_mode("apply", json.dumps(req), os.getpid())
c = calls()
check(r == "error cancelled" and [x[0] for x in c] == ["check"], "apply declined at the dialog: helper never applies (%r, %r)" % (r, c))
z = dialogs[-1] if dialogs else ([], {})
check(z[0][:2] == ["zenity", "--question"] and "--no-markup" in z[0] and z[1].get("GTK_A11Y") == "none"
      and z[1].get("NO_AT_BRIDGE") == "1", "apply dialog: zenity on the full socket, accessibility off, no markup")
t = text_of(z[0])
check("Connection: obfs4 bridges" in t and "192.0.2.7:443" in t and "1 entered, 1 built-in" in t
      and "A bridge sees this computer's IP address" in t, "apply dialog shows the mode and the entered bridge (%r)" % t)
check("Asked for by: " + os.path.realpath(sys.executable) in t and "If you didn't just press Apply and connect" in t,
      "apply dialog names the requester")
check(z[0][z[0].index("--ok-label") + 1] == "Apply" and z[0][z[0].index("--title") + 1] == "Tor Connection Assistant",
      "apply dialog: title and Apply button")

answer[0] = 0; events = []
r = s.tor_mode("apply", json.dumps(req), os.getpid(), events.append)
c = calls()
check(r.startswith("ok ") and json.loads(r[3:]) == {"ok": True, "mode": "obfs4"}, "apply confirmed: ok + the helper's result (%r)" % r)
check([x[0] for x in c] == ["check", "apply"] and json.loads(c[1][1]) == req, "the helper applies exactly the confirmed request")
check(events == ['progress {"event": "phase", "phase": "stopping", "message": "Stopping Tor\\u2026"}'],
      "progress lines passed back to the caller (%r)" % events)
check(notes and notes[-1][:5] == ["notify-send", "-a", "Prestium", "-i", "tor"], "a confirmed change is announced")

answer[0] = 0
t_snow = None
r = s.tor_mode("apply", json.dumps({"mode": "snowflake", "bridges": "", "builtin": True}), os.getpid())
calls(); t_snow = text_of(dialogs[-1][0])
check("UDP" in t_snow, "Snowflake dialog says it opens UDP for Tor")
r = s.tor_mode("apply", json.dumps({"mode": "direct", "bridges": "", "builtin": True}), os.getpid())
calls(); check("Connection: Direct connection" in text_of(dialogs[-1][0]) and "Bridge lines" not in text_of(dialogs[-1][0]), "Direct dialog")

os.environ["FAKE_RESULT"] = json.dumps({"ok": False, "error": "x", "firewall_error": "y", "tor_stopped": True})
r = s.tor_mode("apply", json.dumps(req), os.getpid(), lambda l: None)
calls(); del os.environ["FAKE_RESULT"]
check(r.startswith("fail ") and json.loads(r[5:]).get("firewall_error") == "y", "a failed apply: fail + the helper's JSON, flags kept (%r)" % r)

n = len(dialogs)
for raw, why in (("not json", "not JSON"), (json.dumps([1]), "a list"), (json.dumps(dict(req, extra=1)), "an extra key"),
                 (json.dumps(dict(req, mode="vpn")), "an unknown mode"), (json.dumps(dict(req, bridges=["x"])), "bridges not text"),
                 (json.dumps(dict(req, builtin="yes")), "builtin not a boolean"), (json.dumps(dict(req, bridges="bad line")), "a line the helper refuses")):
    r = s.tor_mode("apply", raw, os.getpid())
    check(r.startswith("error ") and len(dialogs) == n, "apply refused without a dialog: %s (%r)" % (why, r))
c = calls(); check(all(x[0] == "check" for x in c), "refused requests never reach apply")

for cmd, label, word in (("cancel", "Stop Tor", "Stop Tor?"), ("revert", "Revert", "Previous: Direct connection"),
                         ("reconnect", "Reconnect", "Connection: Snowflake")):
    answer[0] = 1
    r = s.tor_mode(cmd, "", os.getpid())
    check(r == "error cancelled" and calls() == [], "%s declined: helper not run" % cmd)
    a = dialogs[-1][0]
    check(a[a.index("--ok-label") + 1] == label and word in text_of(a) and "Asked for by: " in text_of(a),
          "%s dialog: %r button, says what happens (%r)" % (cmd, label, text_of(a)))
    answer[0] = 0
    r = s.tor_mode(cmd, "", os.getpid())
    c = calls()
    check(r.startswith("ok ") and [x[0] for x in c] == [cmd], "%s confirmed: the helper runs %s (%r)" % (cmd, cmd, c))
    check(s.tor_mode(cmd, "{}", os.getpid()).startswith("error ") and calls() == [], "%s takes no request" % cmd)
check(dialogs[-1][0][dialogs[-1][0].index("--cancel-label") + 1] == "Cancel", "reconnect: Cancel button")
s.tor_mode("cancel", "", os.getpid()); calls()
a = [d for d, _ in dialogs if "Stop Tor" in d][-1]
check(a[a.index("--cancel-label") + 1] == "Keep going", "cancel dialog: Keep going instead of a second Cancel")
check(s.tor_mode("status", "", 0) == "error unknown Tor command" and s.tor_mode("features", "", 0).startswith("error"),
      "only apply, cancel, revert and reconnect through the broker")

# one dialog at a time
s.tor_busy.acquire()
check(s.tor_mode("reconnect", "", 0) == "error a Tor settings dialog is already open" and calls() == [], "a second Tor dialog is refused")
s.tor_busy.release()

# dispatch and the request size limit
g["session_for"] = lambda uid, create=False: s
s.alive = lambda: True
answer[0] = 0; ev = []
r = g["dispatch"](os.getuid(), "tor-mode apply " + json.dumps(req), os.getpid(), ev.append)
check(r.startswith("ok ") and ev and [x[0] for x in calls()] == ["check", "apply"], "dispatch: tor-mode apply JSON")
r = g["dispatch"](os.getuid(), "tor-mode reconnect", os.getpid())
check(r.startswith("ok ") and [x[0] for x in calls()] == ["reconnect"], "dispatch: tor-mode reconnect")
check(g["REQUEST_MAX"] > g["TOR_REQUEST_MAX"] >= 100000, "the broker reads Tor requests with bridge lines (limit %d)" % g["REQUEST_MAX"])

# the helper runs as its own transient service (out of the broker's AF_UNIX-only sandbox)
RUN = os.path.join(T, "fake-runner")
open(RUN, "w").write('#!/bin/sh\nfor a; do [ "$a" = -- ] && break; printf "%s|" "$a"; done > "$RUNNER_ARGS"\nwhile [ "$1" != -- ]; do shift; done; shift\nexec "$@"\n')
os.chmod(RUN, 0o755); os.environ["RUNNER_ARGS"] = os.path.join(T, "runner-args")
g["TOR_RUNNER"] = RUN
r = s.tor_mode("reconnect", "", os.getpid()); calls()
ra = open(os.environ["RUNNER_ARGS"]).read().split("|")
check(r.startswith("ok ") and ra[:5] == ["--quiet", "--pipe", "--wait", "--collect", "--service-type=exec"]
      and "RuntimeMaxSec=600" in ra and any(x.startswith("prestium-tor-mode-reconnect-") for x in ra),
      "helper started through systemd-run --pipe --wait as its own unit (%r)" % ra)
bsrc = open(BROKER).read()
check('TOR_RUNNER = _test_env("PRESTIUM_WL_TOR_RUNNER", "/usr/bin/systemd-run")' in bsrc, "installed broker uses systemd-run")
check("RestrictAddressFamilies=AF_UNIX AF_NETLINK" in open(os.path.join(I, "etc/systemd/system/prestium-wl-broker.service")).read(),
      "broker unit stays AF_UNIX/AF_NETLINK (the helper's DoH runs outside it)")

# ---------------------------------------------------------------- prestium-wl client
base = os.path.join(T, "wl"); os.makedirs(base)
srv = socket.socket(socket.AF_UNIX); srv.bind(os.path.join(base, "broker")); srv.listen(4)
got = []
replies = []
def serve():
    while True:
        try:
            c, _ = srv.accept()
        except OSError:
            return
        f = c.makefile("rb"); got.append(f.readline().decode())
        for l in replies.pop(0):
            c.sendall((l + "\n").encode())
        c.close()
threading.Thread(target=serve, daemon=True).start()
env = dict(os.environ, PRESTIUM_WL_BASE=base)
replies.append(['progress {"event": "phase", "message": "a"}', 'progress {"event": "phase", "message": "b"}', 'ok {"ok": true}'])
r = subprocess.run([sys.executable, CLIENT, "tor-mode", "apply"], input=json.dumps(req) + "\n", capture_output=True, text=True, env=env, timeout=20)
check(r.returncode == 0 and r.stdout.splitlines()[-1] == 'ok {"ok": true}' and r.stdout.count("progress ") == 2
      and got[-1] == "tor-mode apply " + json.dumps(req) + "\n", "client: request from stdin, progress lines and result printed (%r)" % r.stdout)
replies.append(['fail {"ok": false}'])
r = subprocess.run([sys.executable, CLIENT, "tor-mode", "revert"], input="", capture_output=True, text=True, env=env, timeout=20)
check(r.returncode == 1 and got[-1] == "tor-mode revert\n", "client: revert, fail -> exit 1")
for argv, inp in ((["tor-mode", "status"], ""), (["tor-mode", "apply"], ""), (["tor-mode", "apply"], "{}\n{}\n"), (["tor-mode"], "")):
    r = subprocess.run([sys.executable, CLIENT] + argv, input=inp, capture_output=True, text=True, env=env, timeout=20)
    check(r.returncode == 2, "client refuses %r with stdin %r" % (argv, inp))
srv.close()

# ---------------------------------------------------------------- the assistant
asrc = open(ASSIST).read()
check("/usr/bin/sudo" not in asrc and "HELPER" not in asrc, "assistant: no sudo left")
check('BROKER = ["/usr/local/bin/prestium-wl", "tor-mode"]' in asrc, "assistant: changes go through prestium-wl tor-mode")
check(asrc.count('broker("apply"') == 1 and 'broker("cancel"' in asrc and "broker(cmd" in asrc, "assistant: apply, cancel, revert/reconnect use broker()")
tree = ast.parse(asrc)
fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "broker"][0]
ns = {"json": json, "subprocess": subprocess, "threading": threading}
FAKEWL = os.path.join(T, "fake-wl")
open(FAKEWL, "w").write('#!/bin/sh\ncat > "$WL_IN"\nprintf "%s\\n" "$@" > "$WL_ARGS"\nprintf "%b" "$WL_OUT"\n')
os.chmod(FAKEWL, 0o755)
ns["BROKER"] = [FAKEWL, "tor-mode"]; ns["BROKER_TIMEOUT"] = 30
exec(compile(ast.Module([fn], []), ASSIST, "exec"), ns)
os.environ.update(WL_IN=os.path.join(T, "wl-in"), WL_ARGS=os.path.join(T, "wl-args"))
def wl(out, *a, **k):
    os.environ["WL_OUT"] = out
    return ns["broker"](*a, **k)
ev = []
res = wl('progress {"event": "phase", "message": "x"}\\nprogress nope\\nok {"ok": true, "mode": "obfs4"}\\n', "apply", req, ev.append)
check(res == {"ok": True, "mode": "obfs4"} and ev == [{"event": "phase", "message": "x"}]
      and json.loads(open(os.environ["WL_IN"]).read()) == req and open(os.environ["WL_ARGS"]).read() == "tor-mode\napply\n",
      "assistant broker(): request on stdin, events, result (%r)" % res)
res = wl('error cancelled\\n', "revert")
check(res.get("declined") and not res.get("ok") and open(os.environ["WL_IN"]).read() == "", "assistant: No in the dialog -> declined, nothing on stdin")
res = wl('fail {"ok": false, "error": "e", "reverted": true}\\n', "apply", req)
check(res == {"ok": False, "error": "e", "reverted": True}, "assistant: a failed change keeps the helper's flags")
res = wl('error the Wayland broker is not running\\n', "reconnect")
check(res == {"ok": False, "error": "the Wayland broker is not running"}, "assistant: broker errors shown")
res = wl('', "reconnect")
check(res.get("ok") is False and res.get("error"), "assistant: no answer is an error")
check("self.apply_result = res" in asrc and 'if res.get("declined"):' in asrc,
      "assistant: Keep going in the Cancel dialog resumes the apply and shows its result")

shutil.rmtree(T)
sys.exit(fail)
