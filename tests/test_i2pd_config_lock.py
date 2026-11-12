#!/usr/bin/python3
"""2.1: i2pd's config lock. prestium-i2pd-port (i2pd's ExecStartPre) and the I2P Connection
Assistant's root helper (prestium-i2p-mode apply) edit i2pd.conf under the same lock
(/run/prestium-hops.lock). Apply releases it before it restarts i2pd, so the port script that the
restart runs doesn't deadlock. Runs both real scripts on copies of the shipped files, with stubbed
safefile, systemctl (restart i2pd runs the port script, like ExecStartPre) and ferm reload: Apply and
port scripts at the same time (no hang, no lost edit), the port script waiting for the lock and failing
loudly after its timeout, Apply refusing when the lock stays held, and a rollback that keeps the port
script's port and console password."""
import fcntl, json, os, re, shutil, socket, subprocess, sys, tempfile, time
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
MODE = os.path.join(I, "usr/local/sbin/prestium-i2p-mode")
PORT = os.path.join(I, "usr/local/sbin/prestium-i2pd-port")
fail = 0
def check(c, m):
    global fail
    print(("OK   " if c else "FAIL ") + m)
    if not c: fail = 1

def setup(port_wait="10"):
    T = tempfile.mkdtemp()
    D = os.path.join(T, "i2pd"); os.makedirs(D); os.makedirs(os.path.join(T, "run/prestium"))
    for f in ("tunnels.conf", "i2pd.conf"):
        shutil.copy(os.path.join(I, "var/lib/i2pd", f), D)
    def sh(name, body):
        p = os.path.join(T, name); open(p, "w").write("#!/bin/sh\n" + body); os.chmod(p, 0o755); return p
    # atomic like the real safefile (temp file, then rename); a little slow so the two sides overlap
    sh("safefile", 'case "$1" in read) cat "%s/$3";; write) t="%s/.$3.$$"; cat > "$t"; sleep 0.2; mv -f "$t" "%s/$3";; *) exit 1;; esac\n' % (D, D, D))
    sh("ferm", 'sleep 0.3; exit 0\n')                      # systemctl reload-or-restart ferm.service
    sh("getter", 'cat "%s/run/prestium/i2pd.port"\n' % T)
    src = open(PORT).read()
    assert src.count("flock -w 10 9") == 1
    src = (src.replace("/usr/local/lib/prestium/safefile", T + "/safefile")
              .replace("/usr/local/lib/prestium/i2pd-port-get", T + "/getter")
              .replace("/usr/bin/systemctl", T + "/ferm")
              .replace("/run/prestium", T + "/run/prestium")
              .replace("install -d -o root -g root -m 0755", "mkdir -p")
              .replace('chown root:user "$CF" 2>/dev/null || chown root:root "$CF"', "true")
              .replace("flock -w 10 9", "flock -w %s 9" % port_wait))
    open(os.path.join(T, "port.sh"), "w").write(src)
    # Apply's systemctl: "restart i2pd" runs the port script synchronously, as i2pd's ExecStartPre does
    sh("systemctl", 'echo "$@" >> "%s/calls"\ncase "$1" in restart) sh "%s/port.sh" 2>>"%s/port.err";; *) exit 0;; esac\n' % (T, T, T))
    return T, D

def env(T, D, port, **kw):
    e = dict(os.environ, PRESTIUM_I2P_DIR=D, PRESTIUM_SAFEFILE=T + "/safefile", PRESTIUM_SYSTEMCTL=T + "/systemctl",
             PRESTIUM_I2PD_PORTFILE=T + "/run/prestium/i2pd.port", PRESTIUM_I2P_LOCK=T + "/run/prestium-hops.lock",
             PRESTIUM_I2P_APPLY_LOCK=T + "/apply.lock", PRESTIUM_I2P_PROXY_PORT=str(port), PRESTIUM_I2P_WAIT="3",
             PRESTIUM_I2PD_UID=str(os.getuid()))
    e.update(kw); return e

def listener():
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0)); s.listen(8); return s, s.getsockname()[1]

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def apply(T, D, req, port, **kw):
    return subprocess.Popen([sys.executable, "-I", MODE, "apply"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env(T, D, port, **kw))

def port_script(T):
    return subprocess.Popen(["sh", T + "/port.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

def top(path, key):
    s = open(path).read().split("\n[", 1)[0]
    return re.findall(r"^%s\s*=\s*(.*)$" % key, s, re.M)

def sect(path, name, key):
    m = re.search(r"^\[%s\]\n(.*?)(?=^\[|\Z)" % re.escape(name), open(path).read(), re.M | re.S)
    return re.findall(r"^%s\s*=\s*(.*)$" % re.escape(key), m.group(1), re.M) if m else []

def consistent(T, D):
    c = os.path.join(D, "i2pd.conf")
    p = open(T + "/run/prestium/i2pd.port").read().strip()
    pw = open(T + "/run/prestium/i2pd-console.pass").read().strip()
    return top(c, "port") == [p] and sect(c, "http", "auth") == ["true"] and sect(c, "http", "pass") == [pw]

REQ = {"hops": 5, "share": "high", "outproxy": "stormycloud"}

# 1. Apply and the port script at the same time
T, D = setup()
srv, lp = listener()
subprocess.run(["sh", T + "/port.sh"], check=True, stderr=subprocess.DEVNULL)   # "boot": first port
t0 = time.monotonic()
a = apply(T, D, REQ, lp)
ps = []
for i in range(4):
    ps.append(port_script(T)); time.sleep(0.15)
a.stdin.write(json.dumps(REQ)); a.stdin.close()
try:
    out = a.stdout.read(); a.wait(timeout=60); hung = False
except subprocess.TimeoutExpired:
    a.kill(); hung = True; out = ""
prc = []
for p in ps:
    try: p.wait(timeout=60); prc.append(p.returncode)
    except subprocess.TimeoutExpired: p.kill(); prc.append("hung")
el = time.monotonic() - t0
srv.close()
check(not hung and a.returncode == 0 and '"ok": true' in out, "Apply finished and succeeded while port scripts ran (%.1f s, %s)" % (el, out.strip()[-80:]))
check(prc == [0, 0, 0, 0], "all concurrent port scripts finished and succeeded (%s)" % prc)
check(el < 30, "no hang: everything done in %.1f s (port script waits at most 10 s)" % el)
calls = open(T + "/calls").read()
check("restart i2pd" in calls and "stayed locked" not in open(T + "/port.err").read(),
      "Apply's restart ran the port script without waiting for Apply's lock (no deadlock)")
c = os.path.join(D, "i2pd.conf")
check(top(c, "share") == ["80"] and top(c, "bandwidth") == ["128"] and sect(c, "exploratory", "inbound.length") == ["5"]
      and sect(c, "socksproxy", "outbound.length") == ["5"], "Apply's i2pd.conf edits kept (share 80, bandwidth 128, 5 hops)")
check(sect(os.path.join(D, "tunnels.conf"), "Web Browser HTTP Proxy", "outbound.length") == ["5"], "Apply's tunnels.conf edit kept")
check(consistent(T, D), "port script's edits kept: one global port = /run port file, [http] auth and console password match")
check(not [f for f in os.listdir(D) if f.startswith(".")], "no temporary files left in i2pd's directory")
shutil.rmtree(T)

# 2. the port script waits for the lock, and fails loudly after its timeout
T, D = setup(port_wait="1")
subprocess.run(["sh", T + "/port.sh"], check=True, stderr=subprocess.DEVNULL)
before = (open(D + "/i2pd.conf").read(), open(T + "/run/prestium/i2pd.port").read())
lk = open(T + "/run/prestium-hops.lock", "a"); fcntl.flock(lk, fcntl.LOCK_EX)
p = port_script(T); time.sleep(0.5)
check(p.poll() is None and open(D + "/i2pd.conf").read() == before[0], "port script waits while the config is locked")
fcntl.flock(lk, fcntl.LOCK_UN)
p.wait(timeout=30)
check(p.returncode == 0 and open(T + "/run/prestium/i2pd.port").read() != before[1] and consistent(T, D),
      "port script proceeds once the lock is free")
before = (open(D + "/i2pd.conf").read(), open(T + "/run/prestium/i2pd.port").read())
fcntl.flock(lk, fcntl.LOCK_EX)
t0 = time.monotonic(); p = port_script(T)
try: err = p.communicate(timeout=30)[1]
except subprocess.TimeoutExpired: p.kill(); err = "hung"
check(p.returncode not in (0, None) and "stayed locked" in err and time.monotonic() - t0 < 10,
      "lock held past the timeout: port script fails loudly (rc %s: %s)" % (p.returncode, err.strip()[:90]))
check(open(D + "/i2pd.conf").read() == before[0] and open(T + "/run/prestium/i2pd.port").read() == before[1],
      "... and changes nothing")
fcntl.flock(lk, fcntl.LOCK_UN); lk.close()
shutil.rmtree(T)

# 3. Apply refuses, unchanged, when the config lock stays held
T, D = setup()
before = {f: open(os.path.join(D, f)).read() for f in ("tunnels.conf", "i2pd.conf")}
lk = open(T + "/run/prestium-hops.lock", "a"); fcntl.flock(lk, fcntl.LOCK_EX)
a = apply(T, D, REQ, free_port(), PRESTIUM_I2P_LOCK_WAIT="1")
o, e = a.communicate(json.dumps(REQ), timeout=30)
check(a.returncode != 0 and "busy" in o and "locked" in e, "Apply with the config locked: refused, loudly (%s)" % o.strip())
check(all(open(os.path.join(D, f)).read() == before[f] for f in before) and not os.path.exists(T + "/calls"),
      "... nothing written, i2pd not restarted")
fcntl.flock(lk, fcntl.LOCK_UN); lk.close()
# a second Apply while one runs is refused at once (Apply lock, held across the restart)
op = open(T + "/apply.lock", "a"); fcntl.flock(op, fcntl.LOCK_EX)
a = apply(T, D, REQ, free_port())
o, _ = a.communicate(json.dumps(REQ), timeout=30)
check(a.returncode != 0 and "already running" in o, "a second Apply at the same time is refused")
fcntl.flock(op, fcntl.LOCK_UN); op.close()
shutil.rmtree(T)

# 4. rollback keeps the port script's port and console password
T, D = setup()
subprocess.run(["sh", T + "/port.sh"], check=True, stderr=subprocess.DEVNULL)
orig_tun = open(D + "/tunnels.conf").read(); c = D + "/i2pd.conf"
orig = (top(c, "share"), top(c, "bandwidth"), sect(c, "exploratory", "inbound.length"))
a = apply(T, D, REQ, free_port())   # nothing listens: i2pd "doesn't come back"
o, _ = a.communicate(json.dumps(REQ), timeout=60)
check(a.returncode != 0 and "previous settings were restored" in o, "proxy didn't come back: rolled back (%s)" % o.strip())
check(open(T + "/calls").read().count("restart i2pd") == 2, "i2pd restarted with the new, then the previous settings")
check((top(c, "share"), top(c, "bandwidth"), sect(c, "exploratory", "inbound.length")) == orig and open(D + "/tunnels.conf").read() == orig_tun,
      "previous settings back")
check(consistent(T, D), "rollback kept the port and console password the port script wrote")
shutil.rmtree(T)

# 5. static: lock before the first read, released before the restart
s = open(PORT).read()
check(s.index("flock -w 10 9") < s.index("$SAFE read") and s.index('exec 9>>"$LOCK"') < s.index("flock -w 10 9")
      and "LOCK=/run/prestium-hops.lock" in s, "port script: same lock file, taken (10 s max) before reading i2pd.conf")
check("logger -p daemon.err" in s, "port script: timeout logged to the journal")
m = open(MODE).read()
check('"/run/prestium-hops.lock"' in m and m.index("unlock(lk)   # before the restart") < m.index('[SYSTEMCTL, "restart", "i2pd"]'),
      "Apply: same lock file, released before restarting i2pd")
sys.exit(fail)
