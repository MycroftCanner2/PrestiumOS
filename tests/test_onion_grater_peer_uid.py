#!/usr/bin/python3
"""2.1 (ISO test after ba6ff54): on the live system onion-grater runs as its own uid and the desktop
apps as "user", so identify() reads /proc of ANOTHER uid. /proc/<pid>/environ is mode 0400 (owner
only): CAP_SYS_PTRACE passes the ptrace check but not the file's permission check, so every Python
client (Nyx, the Tor Connection Assistant, OnionShare) was refused with "cannot inspect environment:
Permission denied" while Tor Browser (no environ check) worked. The same-uid tests
(test_onion_grater_identity.py, test_onion_grater_tamper.py) could not see that.

Runs the real identify() as uid "nobody" with exactly the capabilities of prestium-onion-grater.service
(setpriv, ambient capabilities) against a real Python client of this user that uses a ctypes callback
(libffi trampoline, as PyGObject in the assistant). Needs sudo -n and setpriv; creates a stand-in
/usr/bin/onionshare when neither it nor /usr/bin/nyx exists, and removes it afterwards. Also checks
that with CAP_SYS_PTRACE alone the client is refused for that reason (the bug this guards).
"""
import json, os, re, shutil, subprocess, sys, tempfile, time
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
SRC = os.path.join(I, "usr/local/sbin/prestium-onion-grater")
UNIT = os.path.join(I, "etc/systemd/system/prestium-onion-grater.service")
PY = "/usr/bin/python3"
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1

if not shutil.which("setpriv") or subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode:
    print("SKIP needs setpriv and sudo -n"); sys.exit(0)

unit = open(UNIT).read()
amb = re.search(r"^AmbientCapabilities=(.*)$", unit, re.M).group(1).split()
bnd = re.search(r"^CapabilityBoundingSet=(.*)$", unit, re.M).group(1).split()
(ok if sorted(amb) == sorted(bnd) else bad)("unit: ambient = bounding capabilities (%s)" % " ".join(amb))
(ok if "CAP_DAC_READ_SEARCH" in amb and "CAP_DAC_OVERRIDE" not in bnd else bad)(
    "unit: CAP_DAC_READ_SEARCH (read /proc/<pid>/environ of another uid), never CAP_DAC_OVERRIDE")
aa = open(os.path.join(I, "etc/apparmor.d/usr.local.sbin.prestium-onion-grater")).read()
(ok if re.search(r"^  capability dac_read_search,$", aa, re.M) and not re.search(r"^\s*capability dac_override", aa, re.M)
 else bad)("profile: capability dac_read_search, no dac_override")
inacc = re.search(r"^InaccessiblePaths=(.*)$", unit, re.M)
(ok if inacc and all(p in inacc.group(1).split() for p in ("-/etc/shadow", "-/etc/gshadow", "-/var/lib")) else bad)(
    "unit: shadow files and /var/lib hidden from the filter")

T = tempfile.mkdtemp(); os.chmod(T, 0o755)
S = os.path.join(T, "s"); os.mkdir(S); os.chmod(S, 0o1777)   # where "nobody" can create its socket
created = []
CLIENT = ("import ctypes, socket, sys, time\n"
          "cb = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 1); cb()  # a libffi closure, as PyGObject makes\n"
          "s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[-1]); time.sleep(3)\n")
if os.path.exists("/usr/bin/nyx"):
    # Nyx itself: its cmdline as on the live system; the ctypes case runs as a second client below
    script = "/usr/bin/nyx"
elif os.path.exists("/usr/bin/onionshare"):
    print("SKIP /usr/bin/onionshare is the real OnionShare and nyx is missing: no stand-in possible"); sys.exit(0)
else:
    script = "/usr/bin/onionshare"
    open(T + "/c.py", "w").write(CLIENT)
    subprocess.run(["sudo", "-n", "install", "-m", "0644", T + "/c.py", script], check=True); created.append(script)

SERVER = r'''
import importlib.machinery, importlib.util, json, os, socket, sys
src, path, uid = sys.argv[1], sys.argv[2], int(sys.argv[3])
loader = importlib.machinery.SourceFileLoader("og", src)
spec = importlib.util.spec_from_loader("og", loader); og = importlib.util.module_from_spec(spec); loader.exec_module(og)
og.USER_UID = uid; og.LOCALWEB_GID = None
s = socket.socket(socket.AF_UNIX); s.bind(path); os.chmod(path, 0o666); s.listen(1); s.settimeout(20)
print("ready", flush=True)
c, _ = s.accept(); who, why, pid = og.identify(c)
print(json.dumps({"who": who, "why": why, "uid": os.getuid()}), flush=True)
'''
open(T + "/server.py", "w").write(SERVER)

def run(caps, argv_of):
    path = os.path.join(S, "ctl")
    subprocess.run(["sudo", "-n", "rm", "-f", path])
    c = ",".join("+" + x[4:].lower() for x in caps)
    srv = subprocess.Popen(["sudo", "-n", "setpriv", "--reuid=nobody", "--regid=nogroup", "--clear-groups",
                            "--inh-caps=-all," + c, "--ambient-caps=-all," + c, "--bounding-set=-all," + c,
                            PY, T + "/server.py", SRC, path, str(os.getuid())],
                           stdout=subprocess.PIPE, text=True)
    try:
        if srv.stdout.readline().strip() != "ready":
            return {"who": None, "why": "server did not start"}
        env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp"), "TERM": "dumb", "PYTHONNOUSERSITE": "1"}
        cl = subprocess.Popen(argv_of(path), env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        line = srv.stdout.readline()
        cl.kill(); cl.wait()
        return json.loads(line) if line else {"who": None, "why": "no result"}
    finally:
        srv.wait(timeout=20)

try:
    if script == "/usr/bin/nyx":
        argv = lambda p: [PY, script, "-s", p]; want = "nyx"
    else:
        argv = lambda p: [PY, script, p]; want = "onionshare"
    r = run(amb, argv)
    (ok if r["who"] == want and r["uid"] != os.getuid() else bad)(
        "%s identified as %s by uid %s with %s (%s)" % (script, want, r.get("uid"), "+".join(amb), r["why"]))
    r = run(["CAP_SYS_PTRACE"], argv)
    (ok if r["who"] is None and "environ" in r["why"] else bad)(
        "with CAP_SYS_PTRACE alone it is refused: %s" % r["why"])
    if script == "/usr/bin/nyx":
        # the libffi trampoline of a GTK/ctypes client, through the real identify() as another uid:
        # (a stand-in script can't pose as /usr/bin/nyx), so tampered() on it as nobody
        open(T + "/c.py", "w").write(CLIENT.split("\ns = ")[0] + "\nprint(1, flush=True); time.sleep(10)\n")
        cl = subprocess.Popen([PY, T + "/c.py"], env={"PATH": "/usr/bin"}, stdout=subprocess.PIPE)
        cl.stdout.readline()
        c = ",".join("+" + x[4:].lower() for x in amb)
        out = subprocess.run(["sudo", "-n", "setpriv", "--reuid=nobody", "--regid=nogroup", "--clear-groups",
                              "--inh-caps=-all," + c, "--ambient-caps=-all," + c, "--bounding-set=-all," + c, PY, "-c",
                              "import importlib.machinery as m, importlib.util as u, sys\n"
                              "l = m.SourceFileLoader('og', sys.argv[1]); s = u.spec_from_loader('og', l); og = u.module_from_spec(s); l.exec_module(og)\n"
                              "print(og.tampered(int(sys.argv[2])))", SRC, str(cl.pid)], capture_output=True, text=True)
        cl.kill(); cl.wait()
        (ok if out.stdout.strip() == "None" else bad)(
            "a ctypes (libffi) client of another uid passes tampered(): %s" % (out.stdout.strip() or out.stderr.strip()[-200:]))
finally:
    for f in created:
        subprocess.run(["sudo", "-n", "rm", "-f", f])
    subprocess.run(["sudo", "-n", "rm", "-rf", T])
sys.exit(fail)
