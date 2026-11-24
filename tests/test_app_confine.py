#!/usr/bin/python3
"""Security review F-01 and F-05: app-confine (usr/local/lib/prestium/app-confine).

Static checks: every desktop application with an AppArmor profile is in app-confine's table (or
listed below with the reason it is not), every way the image starts one goes through app-confine
(menu, panel, desktop files, D-Bus activation: hook 0625), and the table is consistent.

Functional check (needs user namespaces, dbus-daemon, xdg-dbus-proxy and python3-dbus): a patched
copy, whose fixed paths point into a temporary directory, starts a probe program in the namespace
next to a private session bus, a fake system bus, a fake Wayland broker and the restricted Wayland
socket, and the probe reports what it can reach. Nothing on this machine changes (all mounts are in
the probe's own namespace).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config", "includes.chroot")
AC = os.path.join(I, "usr/local/lib/prestium/app-confine")
fails = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fails
    fails += 1
    print("FAIL " + m)


def chk(cond, good, fail):
    if cond:
        ok(good)
    else:
        bad(fail)


def load_table():
    ns = {"re": re}
    src = open(AC).read()
    start = src.index("# name: (program, group, policy, gnupg)")
    end = src.index("RUN_USER = ")
    exec(src[start:end], ns)
    return ns["APPS"], ns["TALK_OK"]


APPS, TALK_OK = load_table()
POL = os.path.join(I, "usr/share/prestium/app-confine")

# --- static -----------------------------------------------------------------------------------
# applications with a profile including prestium-app-common (directly or through the viewer and
# app-base abstractions) that do not go through app-confine, and why
EXEMPT = {
    "torbrowser_firefox": "own bubblewrap sandbox (browser-sandbox.sh: no bus, own /run, /tmp, netns)",
    "librewolf": "own bubblewrap sandbox (browser-sandbox.sh)",
    "prestium-localfox": "own bubblewrap sandbox (prestium-localfox)",
    "prestium_pinentry": "started by gpg-agent inside the confined application",
    "mat2-inner": "inner bubblewrap profile", "metadata-cleaner-inner": "inner bubblewrap profile",
    "glycin-inner": "inner bubblewrap profile",
    "prestium_translate_engine": "inner bubblewrap profile of prestium-translate",
}
aa = os.path.join(I, "etc/apparmor.d")
profiles = {}
for f in sorted(os.listdir(aa)):
    p = os.path.join(aa, f)
    if not os.path.isfile(p):
        continue
    t = open(p).read()
    m = re.search(r"^profile (\S+) (/\S+)", t, re.M)
    if m and re.search(r"include <abstractions/prestium-(app-common|app-base|viewer-core)>", t):
        profiles[m.group(1)] = m.group(2)
progs = {v[0] for v in APPS.values()}
# profiles whose program is started by a wrapper in the table
COVERED_VIA = {"libreoffice": "libreoffice",   # /usr/bin/libreoffice -> soffice -> oosplash, soffice.bin
               "audacity": "audacity"}         # /usr/bin/audacity (shim) -> prestium-audacity -> the real one


def attach_matches(pattern):
    rx = re.escape(pattern)
    rx = re.sub(r"\\\{([^}]*)\\\}", lambda m: "(" + "|".join(m.group(1).split(",")) + ")", rx)
    rx = rx.replace(r"\*", "[^/]*")
    rx = re.compile("^" + rx + "$")
    return any(rx.match(p) for p in progs)


for prof, att in sorted(profiles.items()):
    if prof in EXEMPT:
        ok("not confined by app-confine, by design: %s (%s)" % (prof, EXEMPT[prof]))
    elif COVERED_VIA.get(prof) in APPS:
        ok("profile %s (%s) is started through app-confine (%s)" % (prof, att, COVERED_VIA[prof]))
    elif attach_matches(att):
        ok("profile %s (%s) is started through app-confine" % (prof, att))
    else:
        bad("profile %s (%s) is neither in app-confine's table nor exempt" % (prof, att))

for n, (prog, group, policy, gnupg) in sorted(APPS.items()):
    if not prog.startswith("/") or not re.match(r"^[a-z0-9-]+$", group):
        bad("%s: bad program or group" % n)
    if not os.path.isfile(os.path.join(POL, policy + ".policy")):
        bad("%s: no policy file %s.policy" % (n, policy))
    if gnupg not in (None, "shared", "private"):
        bad("%s: gnupg %r" % (n, gnupg))
for v in TALK_OK:
    if v in ("org.freedesktop.systemd1", "org.freedesktop.portal.Desktop", "ca.desrt.dconf", "org.freedesktop.DBus"):
        bad("may talk to %s" % v)
ok("table: %d programs, each with a policy file; talk only %s (the policies: test_app_confine_policy.py)"
   % (len(APPS), ", ".join(sorted(TALK_OK))))
# the gpg rule of F-02: Gajim's group never binds the real gnupg/; Kleopatra's and Claws' do
for n in ("gajim", "prestium-gajim-keys"):
    chk(APPS[n][3] == "private" and APPS[n][1] == "gajim", "%s: private gnupg/ (F-02)" % n, "%s gnupg" % n)
for n in ("kleopatra", "claws-mail"):
    chk(APPS[n][3] == "shared", "%s: the user's gnupg/" % n, "%s gnupg" % n)

src = open(AC).read()
chk("no_new_privs" in src and "PR_SET_NO_NEW_PRIVS" not in src, "no no_new_privs (profile transitions keep working)", "no_new_privs")
chk(src.startswith("#!/usr/bin/python3 -I\n"), "python3 -I", "app-confine shebang")

# the menu and the desktop files
menu = open(os.path.join(I, "etc/xdg/labwc/menu.xml")).read()
for cmd in re.findall(r'command="([^"]+)"', menu):
    w = cmd.split()
    if w[0] == "prestium-run" and len(w) > 1:
        b = os.path.basename(w[1])
        if b in APPS and w[1] not in (b, "/usr/local/bin/" + b) and not APPS[b][0].startswith("/usr/local/bin/"):
            bad("menu runs %s by its real path" % w[1])
pr = open(os.path.join(I, "usr/local/bin/prestium-run")).read()
for n, v in APPS.items():
    if v[0].startswith("/usr/local/bin/"):
        if ("%s|" % v[0] in pr or "|%s)" % v[0] in pr or v[0] in pr) and n in pr:
            ok("prestium-run sends %s through app-confine" % n)
        else:
            bad("prestium-run does not send %s through app-confine" % n)
for d in ("usr/share/applications", "usr/local/share/applications"):
    dd = os.path.join(I, d)
    for f in sorted(os.listdir(dd)) if os.path.isdir(dd) else []:
        for line in open(os.path.join(dd, f)):
            if not line.startswith("Exec="):
                continue
            w = line[5:].split()
            while w and (w[0] == "env" or "=" in w[0]):
                w = w[1:]
            if not w:
                continue
            hit = [n for n, v in APPS.items() if w[0] in (v[0],)]
            if hit and not w[0].startswith("/usr/local/lib/prestium/app-confine"):
                if APPS[hit[0]][0].startswith("/usr/local/bin/"):
                    bad("%s/%s starts %s directly" % (d, f, w[0]))
hook = os.path.join(R, "config/hooks/live/0625-prestium-app-confine.hook.chroot")
if os.path.exists(hook):
    h = open(hook).read()
    for k in ("--list", "/usr/local/share/applications", "/usr/local/share/dbus-1/services", "/etc/xdg/autostart",
              "SystemdService"):
        chk(k in h, "hook 0625 handles %s" % k, "hook 0625: %s" % k)
else:
    bad("hook 0625 missing")
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
chk("0755 root root /usr/local/lib/prestium/app-confine\n" in perms, "perms", "perms.txt: app-confine")
pl = open(os.path.join(R, "config/package-lists/prestium.list.chroot")).read()
chk(re.search(r"^xdg-dbus-proxy$", pl, re.M), "xdg-dbus-proxy installed", "xdg-dbus-proxy not in the package list")

# --- functional -------------------------------------------------------------------------------
def need():
    for t in ("dbus-daemon", "xdg-dbus-proxy"):
        if not shutil.which(t):
            return t + " missing"
    import importlib.util
    if importlib.util.find_spec("dbus") is None:
        return "python3-dbus missing"
    if subprocess.run(["unshare", "-Urm", "true"], capture_output=True).returncode != 0:
        return "user namespaces unavailable"
    return None


why = need()
if why:
    print("SKIP functional check: " + why)
    sys.exit(1 if fails else 0)

T = tempfile.mkdtemp(prefix="appconf-")
uid = os.getuid()
procs = []
try:
    RU = T + "/run/user"
    run = "%s/%d" % (RU, uid)
    os.makedirs(run, 0o700)
    os.chmod(RU, 0o755)
    for d in ("pulse", "dconf", "gnupg"):
        os.makedirs(os.path.join(run, d), 0o700)
    open(os.path.join(run, "dconf/user"), "w").write("dconf")
    socks = []

    def listen(p):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(p)
        s.listen(16)
        socks.append(s)

    listen(run + "/pulse/native")
    listen(run + "/pipewire-0")
    listen(run + "/gnupg/S.gpg-agent")
    os.makedirs(T + "/run/dbus")
    listen(T + "/run/dbus/system_bus_socket")
    os.makedirs("%s/run/prestium-wl/%d" % (T, uid))
    listen(T + "/run/prestium-wl/broker")
    listen("%s/run/prestium-wl/%d/apps" % (T, uid))
    os.makedirs(T + "/tmp/.X11-unix")
    os.chmod(T + "/tmp", 0o1777)
    listen(T + "/tmp/.X11-unix/X0")
    open(T + "/tmp/host-secret", "w").write("x")
    # a private session bus with a service that owns a notification daemon's and systemd's names
    conf = T + "/session.conf"
    open(conf, "w").write("""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>unix:path=%s/bus</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/><allow own="*"/></policy></busconfig>
""" % run)
    procs.append(subprocess.Popen(["dbus-daemon", "--config-file=" + conf, "--nofork", "--nopidfile"]))
    for _ in range(100):
        if os.path.exists(run + "/bus"):
            break
        time.sleep(0.05)
    svc = T + "/svc.py"
    open(svc, "w").write('''import dbus, dbus.service, dbus.mainloop.glib, sys
from gi.repository import GLib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
b = dbus.bus.BusConnection("unix:path=%s/bus")
class O(dbus.service.Object):
    @dbus.service.method("org.prestium.Test", out_signature="s")
    def Ping(self): return "pong"
names = [dbus.service.BusName(n, b) for n in ("org.freedesktop.Notifications", "org.freedesktop.systemd1")]
O(b, "/x"); print("ready", flush=True); GLib.MainLoop().run()
''' % run)
    sp = subprocess.Popen([sys.executable, svc], stdout=subprocess.PIPE, text=True)
    procs.append(sp)
    sp.stdout.readline()

    probe = T + "/probe.py"
    open(probe, "w").write(r'''#!/usr/bin/python3
import json, os, socket, sys
run = "%(run)s"; T = "%(T)s"; uid = os.getuid()
def can(p):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try: s.connect(p); return True
    except OSError: return False
    finally: s.close()
r = {"uid": uid, "env_bus": os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "runtime": os.environ.get("XDG_RUNTIME_DIR"),
     "wayland": os.environ.get("WAYLAND_DISPLAY"), "cwd": os.getcwd()}
for k, p in {"real_bus": run + "/bus", "proxy_bus": run + "/prestium-bus", "system_bus": T + "/run/dbus/system_bus_socket",
             "broker": T + "/run/prestium-wl/broker", "apps": "%%s/run/prestium-wl/%%d/apps" %% (T, uid),
             "pulse": run + "/pulse/native", "pipewire": run + "/pipewire-0", "x11": T + "/tmp/.X11-unix/X0",
             "gpg_agent": run + "/gnupg/S.gpg-agent"}.items():
    r[k] = can(p)
r["host_tmp"] = os.path.exists(T + "/tmp/host-secret")
r["dconf"] = os.path.exists(run + "/dconf/user")
r["shm"] = os.listdir("/dev/shm")
r["base_visible"] = os.path.exists(run + "/prestium-confine")
import shutil, subprocess
if shutil.which("bwrap"):  # the browsers' and viewers' own sandboxes must still start inside
    a = ["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/usr", "/usr"]
    for d in ("bin", "lib", "lib64", "sbin"):
        if os.path.islink("/" + d): a += ["--symlink", os.readlink("/" + d), "/" + d]
    a += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--", "/usr/bin/true"]
    r["nested_bwrap"] = subprocess.run(a, capture_output=True).returncode == 0
r["caps"] = [l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff")][0]
open(T + "/tmp/mine", "w").write("1")
if r["proxy_bus"]:
    import dbus
    b = dbus.bus.BusConnection(os.environ["DBUS_SESSION_BUS_ADDRESS"])
    def call(n):
        try: return str(b.get_object(n, "/x").Ping(dbus_interface="org.prestium.Test"))
        except dbus.DBusException as e: return e.get_dbus_name()
    r["notify"] = call("org.freedesktop.Notifications"); r["systemd"] = call("org.freedesktop.systemd1")
    def own(n):
        try: return int(b.request_name(n))
        except dbus.DBusException as e: return e.get_dbus_name()
    r["own_mine"] = own("org.example.Probe"); r["own_other"] = own("org.example.Other")
print("PROBE " + json.dumps(r))
''' % {"run": run, "T": T})
    os.chmod(probe, 0o755)
    s = open(AC).read()
    s = s.replace('RUN_USER = "/run/user"', 'RUN_USER = "%s"' % RU)
    s = s.replace('SYSBUS_DIR = "/run/dbus"', 'SYSBUS_DIR = "%s/run/dbus"' % T)
    s = s.replace('WL_BASE = "/run/prestium-wl"', 'WL_BASE = "%s/run/prestium-wl"' % T)
    s = s.replace('TMP = "/tmp"', 'TMP = "%s/tmp"' % T)
    s = s.replace("APPS = {\n", 'APPS = {\n    "probe": ("%s", "probe", "probe", None),\n'
                  '    "probe-gpg": ("%s", "probe2", "probe-gpg", "shared"),\n' % (probe, probe), 1)
    # the probes' policies next to copies of the image's fragments (owned by this user, not root)
    pd = T + "/policies"
    shutil.copytree(POL, pd)
    open(pd + "/probe.policy", "w").write("include notify\nown org.example.Probe\n")
    open(pd + "/probe-gpg.policy", "w").write("bus none\n")
    s = s.replace('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = "%s"' % pd)
    s = s.replace("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")
    pc = T + "/app-confine"
    open(pc, "w").write(s)
    os.chmod(pc, 0o755)

    def run_probe(name):
        p = subprocess.run([sys.executable, "-I", pc, name], capture_output=True, text=True, timeout=60,
                           cwd=T + "/tmp", env={"PATH": "/usr/bin:/bin", "HOME": T})
        for line in p.stdout.splitlines():
            if line.startswith("PROBE "):
                if os.environ.get("APP_CONFINE_DEBUG"):
                    print(line, p.stderr)
                return json.loads(line[6:])
        bad("%s: no probe output (rc %d): %s" % (name, p.returncode, p.stderr.strip()[-400:]))
        return None

    r = run_probe("probe")
    if r:
        def expect(k, v, what):
            chk((r.get(k) == v), "probe: " + what, "probe: %s (%s=%r)" % (what, k, r.get(k)))
        expect("uid", uid, "same user id")
        expect("real_bus", False, "no session bus socket")
        expect("proxy_bus", True, "the filtered bus is there")
        expect("system_bus", False, "no system bus (F-01)")
        expect("broker", False, "no Wayland broker (F-01)")
        expect("apps", True, "the restricted Wayland socket")
        expect("pulse", True, "PulseAudio")
        expect("pipewire", True, "PipeWire")
        expect("x11", True, "Xwayland's socket")
        expect("dconf", True, "dconf's cache")
        expect("gpg_agent", False, "no ~/.gnupg agent for a private group (F-02)")
        expect("host_tmp", False, "the host's /tmp is not visible (F-05)")
        expect("shm", [], "an empty /dev/shm (F-05)")
        expect("base_visible", False, "the other groups' runtime directories are not visible")
        expect("runtime", run, "XDG_RUNTIME_DIR")
        expect("env_bus", "unix:path=%s/prestium-bus" % run, "DBUS_SESSION_BUS_ADDRESS is the filter")
        expect("notify", "pong", "D-Bus: notifications reachable")
        expect("systemd", "org.freedesktop.DBus.Error.ServiceUnknown", "D-Bus: systemd not reachable (F-01)")
        expect("own_mine", 1, "D-Bus: may own its own name")
        chk((r.get("own_other") not in (1, 2, 3, 4)), "D-Bus: may not own another name", "owned org.example.Other")
        if "nested_bwrap" in r:
            expect("nested_bwrap", True, "a bubblewrap sandbox still starts inside (browsers, viewers)")
        expect("caps", "0000000000000000", "no capabilities")
        expect("cwd", T + "/tmp", "working directory looked up again (private /tmp)")
    chk(not os.path.exists(T + "/tmp/mine"), "the probe's /tmp file is not in the host's /tmp", "the probe wrote to the host's /tmp")
    chk(os.path.exists("%s/tmp/.prestium-confine-%d/probe/mine" % (T, uid)), "the group's /tmp keeps it for the next start", "private tmp")
    r = run_probe("probe-gpg")
    if r:
        chk(r["gpg_agent"] is True and r["proxy_bus"] is False and r["env_bus"].endswith("/no-bus"), "probe-gpg: the user's gnupg/, no session bus at all", "probe-gpg: %r" % r)
    # fails closed: a planted symlink as the group's directory
    os.rename("%s/prestium-confine/probe" % run, T + "/moved")
    os.symlink(T, "%s/prestium-confine/probe" % run)
    p = subprocess.run([sys.executable, "-I", pc, "probe"], capture_output=True, text=True, timeout=60)
    chk("PROBE" not in p.stdout and p.returncode != 0, "refuses a symlinked runtime directory", "ran with a symlinked runtime directory")
finally:
    for p in procs:
        p.kill()
    subprocess.run(["rm", "-rf", T])
sys.exit(1 if fails else 0)
