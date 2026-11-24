#!/usr/bin/python3
"""Security review F-01 (per-application buses): app-confine's filtered session bus, the desktop portal
and the document portal, end to end, with the image's own policy (gajim.policy), portals.conf, portal
drop-in and link-handler configuration.

A private session bus runs the real xdg-desktop-portal, xdg-document-portal and xdg-permission-store
(with the drop-in's environment, pointed at copies of Prestium's files) and a fake back end (file
chooser and application chooser) that also owns systemd's and dconf's names. A probe started through a
patched copy of app-confine (its fixed paths in a temporary directory) checks that:
  - the portal sees it as org.prestium.Confined.gajim (the proxy's own /.flatpak-info), not as a host
    program, and the picked file comes back through the document portal, readable in the probe's view
    (/run/user/<uid>/doc: its own documents only, not another one exported on the host);
  - an https link reaches the link handler; file: and other schemes run nothing;
  - systemd, dconf, the back end, the bus driver's privileged parts and every portal call outside the
    policy (OpenFile, OpenDirectory, Background, Trash, Inhibit, ScreenCast, Camera, Properties.Set,
    Documents.Add) are refused;
  - the portal offers no interface without a back end in portals.conf (Inhibit, Email: default=none);
  - nothing is left behind (bwrapinfo.json, the proxy's socket).
Skips (exit 0) without user namespaces, dbus-daemon, xdg-dbus-proxy, the portals, fusermount3 or
python3-dbus/python3-gi. Nothing on this machine changes; the document portal's FUSE mount is under
the temporary directory and is unmounted at the end.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config", "includes.chroot")
AC = os.path.join(I, "usr/local/lib/prestium/app-confine")
POL = os.path.join(I, "usr/share/prestium/app-confine")
PORTAL = os.path.join(I, "usr/share/prestium/portal")
DROPIN = os.path.join(I, "etc/systemd/user/xdg-desktop-portal.service.d/prestium.conf")
LIBEXEC = "/usr/libexec"
fails = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fails
    fails += 1
    print("FAIL " + m)


def chk(cond, good, fail):
    (ok if cond else bad)(good if cond else fail)


def need():
    for t in ("dbus-daemon", "xdg-dbus-proxy", "fusermount3"):
        if not shutil.which(t):
            return t + " missing"
    for t in ("xdg-desktop-portal", "xdg-document-portal", "xdg-permission-store"):
        if not os.access(os.path.join(LIBEXEC, t), os.X_OK):
            return t + " missing"
    import importlib.util
    for m in ("dbus", "gi"):
        if importlib.util.find_spec(m) is None:
            return "python3-%s missing" % m
    if subprocess.run(["unshare", "-Urm", "true"], capture_output=True).returncode != 0:
        return "user namespaces unavailable"
    if not os.path.exists("/dev/fuse"):
        return "no /dev/fuse"
    return None


why = need()
if why:
    print("SKIP portal check: " + why)
    sys.exit(0)

T = tempfile.mkdtemp(prefix="appconf-portal-")
uid = os.getuid()
procs = []
run = "%s/run/user/%d" % (T, uid)
try:
    os.makedirs(run, 0o700)
    os.chmod(T + "/run/user", 0o755)
    os.makedirs(T + "/tmp")
    os.chmod(T + "/tmp", 0o1777)
    os.makedirs(T + "/run/prestium-wl")
    os.makedirs(T + "/run/dbus")
    os.makedirs(T + "/home")
    bus = "unix:path=%s/bus" % run
    conf = T + "/session.conf"
    open(conf, "w").write("""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>%s</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/><allow own="*"/></policy></busconfig>
""" % bus)
    procs.append(subprocess.Popen(["dbus-daemon", "--config-file=" + conf, "--nofork", "--nopidfile"]))
    for _ in range(100):
        if os.path.exists(run + "/bus"):
            break
        time.sleep(0.05)
    base_env = {"PATH": "/usr/bin:/bin", "HOME": T + "/home", "DBUS_SESSION_BUS_ADDRESS": bus, "XDG_RUNTIME_DIR": run}
    log = open(T + "/services.log", "w")

    # Prestium's portal configuration, the drop-in's paths moved into T; the back end is the fake one
    tp = T + "/portal"
    shutil.copytree(PORTAL, tp)
    pc = open(tp + "/portals/portals.conf").read()
    open(tp + "/portals/portals.conf", "w").write(re.sub(r"=gtk$", "=prestiumtest", pc, flags=re.M))
    open(tp + "/portals/prestiumtest.portal", "w").write(
        "[portal]\nDBusName=org.freedesktop.impl.portal.desktop.prestiumtest\n"
        "Interfaces=org.freedesktop.impl.portal.FileChooser;org.freedesktop.impl.portal.AppChooser;"
        "org.freedesktop.impl.portal.Inhibit;org.freedesktop.impl.portal.Email;\n")
    rec = T + "/opened"
    handler = T + "/handler.sh"
    open(handler, "w").write("#!/bin/sh\nprintf '%%s\\n' \"$*\" >> %s\n" % rec)
    os.chmod(handler, 0o755)
    df = tp + "/open/applications/prestium-portal-open.desktop"
    d = open(df).read()
    chk("Exec=/usr/local/lib/prestium/portal-open %u\n" in d, "the link handler runs portal-open", "handler Exec")
    open(df, "w").write(d.replace("/usr/local/lib/prestium/portal-open", handler))
    penv = dict(base_env)
    for line in open(DROPIN):
        m = re.match(r"^Environment=([A-Z_]+)=(.*)$", line.strip())
        if m:
            penv[m.group(1)] = m.group(2).replace("/usr/share/prestium/portal", tp)
    chk(set(penv) >= {"XDG_DESKTOP_PORTAL_DIR", "XDG_DATA_DIRS", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CONFIG_DIRS"},
        "drop-in: the portal's back ends and handlers come only from Prestium's directories", "drop-in env %r" % penv)

    pick = T + "/pick"
    os.makedirs(pick)
    open(pick + "/picked.txt", "w").write("picked content\n")
    open(pick + "/other.txt", "w").write("someone else's\n")
    backend = T + "/backend.py"
    open(backend, "w").write(r'''import dbus, dbus.service, dbus.mainloop.glib, json
from gi.repository import GLib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
b = dbus.bus.BusConnection(%(bus)r)
names = [dbus.service.BusName(n, b) for n in ("org.freedesktop.impl.portal.desktop.prestiumtest",
         "org.freedesktop.systemd1", "ca.desrt.dconf")]
LOG = %(log)r
def note(**k):
    open(LOG, "a").write(json.dumps(k) + "\n")
class Impl(dbus.service.Object):
    @dbus.service.method("org.freedesktop.impl.portal.FileChooser", in_signature="osssa{sv}", out_signature="ua{sv}")
    def OpenFile(self, handle, app_id, parent, title, options):
        note(call="OpenFile", app_id=str(app_id))
        return dbus.UInt32(0), {"uris": dbus.Array(["file://%(pick)s/picked.txt"], signature="s")}
    @dbus.service.method("org.freedesktop.impl.portal.AppChooser", in_signature="ossasa{sv}", out_signature="ua{sv}")
    def ChooseApplication(self, handle, app_id, parent, choices, options):
        note(call="ChooseApplication", app_id=str(app_id), choices=[str(c) for c in choices])
        return dbus.UInt32(1), {}
    @dbus.service.method("org.freedesktop.impl.portal.AppChooser", in_signature="oas", out_signature="")
    def UpdateChoices(self, handle, choices):
        pass
    @dbus.service.method("org.prestium.Test", out_signature="s")
    def Ping(self):
        note(call="Ping")
        return "pong"
Impl(b, "/org/freedesktop/portal/desktop")
class X(dbus.service.Object):
    @dbus.service.method("org.prestium.Test", out_signature="s")
    def Ping(self):
        note(call="Ping-x")
        return "pong"
X(b, "/x")
print("ready", flush=True)
GLib.MainLoop().run()
''' % {"bus": bus, "log": T + "/backend.log", "pick": pick})
    bp = subprocess.Popen([sys.executable, backend], stdout=subprocess.PIPE, text=True, env=base_env, stderr=log)
    procs.append(bp)
    bp.stdout.readline()
    for t in ("xdg-permission-store", "xdg-document-portal"):
        procs.append(subprocess.Popen([os.path.join(LIBEXEC, t), "-r"], env=base_env, stdout=log, stderr=log))
    procs.append(subprocess.Popen([os.path.join(LIBEXEC, "xdg-desktop-portal"), "-r"], env=penv, stdout=log, stderr=log))

    import dbus
    host = dbus.bus.BusConnection(bus)
    for _ in range(100):
        if host.name_has_owner("org.freedesktop.portal.Desktop") and os.path.ismount(run + "/doc"):
            break
        time.sleep(0.1)
    if not os.path.ismount(run + "/doc"):
        print("SKIP portal check: the document portal could not mount its FUSE file system here")
        sys.exit(0)
    xml = str(host.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop").Introspect(
        dbus_interface="org.freedesktop.DBus.Introspectable"))
    ifaces = set(re.findall(r'<interface name="([^"]+)"', xml))
    chk({"org.freedesktop.portal.FileChooser", "org.freedesktop.portal.OpenURI"} <= ifaces,
        "portal: file chooser and OpenURI offered", "portal interfaces %s" % sorted(ifaces))
    chk(not ifaces & {"org.freedesktop.portal.Inhibit", "org.freedesktop.portal.Email", "org.freedesktop.portal.Print",
                      "org.freedesktop.portal.ScreenCast", "org.freedesktop.portal.RemoteDesktop", "org.freedesktop.portal.Background"},
        "portal: no Inhibit, Email, Print, ScreenCast, RemoteDesktop or Background (portals.conf default=none)",
        "portal offers %s" % sorted(ifaces))
    # a document exported on the host (not for the probe's application)
    fd = os.open(pick + "/other.txt", os.O_RDONLY)
    other_id = str(host.get_object("org.freedesktop.portal.Documents", "/org/freedesktop/portal/documents").Add(
        dbus.types.UnixFd(fd), True, False, dbus_interface="org.freedesktop.portal.Documents"))
    os.close(fd)

    probe = T + "/probe.py"
    open(probe, "w").write(r'''#!/usr/bin/python3
import json, os, sys, dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
DBusGMainLoop(set_as_default=True)
run = %(run)r; other = %(other)r
r = {"env_bus": os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "flatpak_info": os.path.exists("/.flatpak-info")}
b = dbus.bus.BusConnection(os.environ["DBUS_SESSION_BUS_ADDRESS"])
loop = GLib.MainLoop()
resp = {}
def on_resp(code, results, path=None):
    resp[str(path)] = (int(code), {str(k): [str(x) for x in v] if isinstance(v, dbus.Array) else str(v) for k, v in results.items()})
    loop.quit()
b.add_signal_receiver(on_resp, "Response", "org.freedesktop.portal.Request", None, None, path_keyword="path")
P = b.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
def opts(tok):
    return dbus.Dictionary({"handle_token": dbus.String(tok, variant_level=1)}, signature="sv")
def err(f):
    try:
        f()
        return "allowed"
    except dbus.DBusException as e:
        return e.get_dbus_name()
def wait():
    t = GLib.timeout_add_seconds(15, loop.quit)
    loop.run()
    GLib.source_remove(t)
h = P.OpenFile("", "Pick", opts("pick1"), dbus_interface="org.freedesktop.portal.FileChooser")
wait()
r["pick"] = resp.get(str(h))
uris = (r["pick"] or (1, {}))[1].get("uris", [])
r["uris"] = uris
r["content"] = None
for u in uris:
    try:
        r["content"] = open(u[len("file://"):]).read()
    except OSError as e:
        r["content"] = "error: %%s" %% e
try:
    r["doc_list"] = sorted(os.listdir(run + "/doc"))
except OSError as e:
    r["doc_list"] = "error: %%s" %% e
try:
    r["other_doc"] = open("%%s/doc/%%s/other.txt" %% (run, other)).read()
except OSError as e:
    r["other_doc"] = "error"
for k, u in (("open_https", "https://example.org/prestium"), ("open_file", "file:///etc/passwd"), ("open_other", "x-prestium-test:run")):
    try:
        h = P.OpenURI("", u, opts(k), dbus_interface="org.freedesktop.portal.OpenURI")
        resp.clear()
        wait()
        r[k] = resp.get(str(h), "no response")
    except dbus.DBusException as e:
        r[k] = e.get_dbus_name()
U = "org.freedesktop.portal."
r["denied"] = {
    "OpenURI.OpenFile": err(lambda: P.OpenFile("", dbus.types.UnixFd(0), opts("of"), dbus_interface=U + "OpenURI")),
    "OpenURI.OpenDirectory": err(lambda: P.OpenDirectory("", dbus.types.UnixFd(0), opts("od"), dbus_interface=U + "OpenURI")),
    "Background": err(lambda: P.RequestBackground("", opts("bg"), dbus_interface=U + "Background")),
    "Trash": err(lambda: P.TrashFile(dbus.types.UnixFd(0), dbus_interface=U + "Trash")),
    "Inhibit": err(lambda: P.Inhibit("", dbus.UInt32(8), opts("in"), dbus_interface=U + "Inhibit")),
    "ScreenCast": err(lambda: P.CreateSession(opts("sc"), dbus_interface=U + "ScreenCast")),
    "Camera": err(lambda: P.AccessCamera(opts("ca"), dbus_interface=U + "Camera")),
    "DynamicLauncher": err(lambda: P.PrepareInstall("", "x", dbus.Array([], signature="v"), opts("dl"), dbus_interface=U + "DynamicLauncher")),
    "Properties.Set": err(lambda: P.Set(U + "FileChooser", "version", dbus.UInt32(9, variant_level=1), dbus_interface="org.freedesktop.DBus.Properties")),
    "Documents.Add": err(lambda: b.get_object(U + "Documents", "/org/freedesktop/portal/documents").Add(
        dbus.types.UnixFd(0), True, False, dbus_interface=U + "Documents")),
    "systemd1": err(lambda: b.get_object("org.freedesktop.systemd1", "/x").Ping(dbus_interface="org.prestium.Test")),
    "dconf": err(lambda: b.get_object("ca.desrt.dconf", "/x").Ping(dbus_interface="org.prestium.Test")),
    "backend": err(lambda: b.get_object("org.freedesktop.impl.portal.desktop.prestiumtest", "/x").Ping(dbus_interface="org.prestium.Test")),
    "own_secrets": err(lambda: b.request_name("org.freedesktop.secrets")),
    "own_portal": err(lambda: b.request_name("org.freedesktop.portal.Desktop")),
}
r["version"] = err(lambda: P.Get(U + "FileChooser", "version", dbus_interface="org.freedesktop.DBus.Properties"))
r["names"] = sorted(str(n) for n in b.list_names() if not str(n).startswith(":"))
print("PROBE " + json.dumps(r))
''' % {"run": run, "other": other_id})
    os.chmod(probe, 0o755)
    s = open(AC).read()
    for a, b_ in (('RUN_USER = "/run/user"', 'RUN_USER = "%s/run/user"' % T),
                  ('SYSBUS_DIR = "/run/dbus"', 'SYSBUS_DIR = "%s/run/dbus"' % T),
                  ('WL_BASE = "/run/prestium-wl"', 'WL_BASE = "%s/run/prestium-wl"' % T),
                  ('TMP = "/tmp"', 'TMP = "%s/tmp"' % T),
                  ('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = "%s/policies"' % T),
                  ("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")):
        assert a in s, a
        s = s.replace(a, b_)
    s = s.replace("APPS = {\n", 'APPS = {\n    "probe": ("%s", "probe", "gajim", "private"),\n' % probe, 1)
    shutil.copytree(POL, T + "/policies")
    pcf = T + "/app-confine"
    open(pcf, "w").write(s)
    os.chmod(pcf, 0o755)
    p = subprocess.run([sys.executable, "-I", pcf, "probe"], capture_output=True, text=True, timeout=180,
                       cwd=T + "/tmp", env=dict(base_env, HOME=T + "/home"))
    r = None
    for line in p.stdout.splitlines():
        if line.startswith("PROBE "):
            r = json.loads(line[6:])
    if os.environ.get("APP_CONFINE_DEBUG"):
        print(p.stdout, p.stderr, open(T + "/services.log").read())
    if r is None:
        bad("no probe output (rc %d): %s" % (p.returncode, p.stderr.strip()[-600:]))
    else:
        blog = [json.loads(x) for x in open(T + "/backend.log")] if os.path.exists(T + "/backend.log") else []
        ids = {x.get("app_id") for x in blog if x["call"] == "OpenFile"}
        chk(ids == {"org.prestium.Confined.gajim"}, "the portal sees the probe as org.prestium.Confined.gajim (the proxy's /.flatpak-info)",
            "the portal saw app ids %r" % ids)
        chk(r["flatpak_info"] is False, "no /.flatpak-info in the application's own view", "/.flatpak-info visible to the app")
        uris = r.get("uris") or []
        chk(len(uris) == 1 and re.match(r"^file://%s/doc/[^/]+/picked\.txt$" % re.escape(run), uris[0]),
            "file chooser: the picked file comes back through the document portal", "file chooser uris %r (%r)" % (uris, r.get("pick")))
        chk(r.get("content") == "picked content\n", "file chooser: the probe reads the picked file in its own view",
            "picked file content %r" % r.get("content"))
        doc_id = uris[0].split("/")[-2] if uris else None
        chk(r.get("doc_list") == [doc_id], "document portal: only its own document is in the probe's /run/user/<uid>/doc",
            "doc list %r" % r.get("doc_list"))
        chk(r.get("other_doc") == "error", "document portal: a document exported for no one/another app is not readable",
            "read another document: %r" % r.get("other_doc"))
        opened = open(rec).read().split("\n") if os.path.exists(rec) else []
        opened = [x for x in opened if x]
        chk(opened == ["https://example.org/prestium"], "OpenURI: the https link reached Prestium's handler, nothing else ran",
            "handler ran with %r (https %r, file %r, other %r)" % (opened, r.get("open_https"), r.get("open_file"), r.get("open_other")))
        for k, v in sorted(r["denied"].items()):
            chk(v in ("org.freedesktop.DBus.Error.AccessDenied", "org.freedesktop.DBus.Error.ServiceUnknown"),
                "refused: %s (%s)" % (k, v.rsplit(".", 1)[-1]), "%s was not refused: %s" % (k, v))
        chk(r["version"] == "allowed", "allowed: Properties.Get (the toolkits' version check)", "Properties.Get: %s" % r["version"])
        pings = [x for x in blog if x["call"].startswith("Ping")]
        chk(not pings, "the back end, systemd and dconf were never reached", "reached: %r" % pings)
        bad_names = [n for n in r["names"] if n.startswith(("org.freedesktop.systemd1", "ca.desrt.dconf", "org.freedesktop.impl."))]
        chk(not bad_names, "ListNames shows none of systemd, dconf or the back ends", "ListNames shows %r" % bad_names)
        chk(r["env_bus"] == "unix:path=%s/prestium-bus" % run, "DBUS_SESSION_BUS_ADDRESS is the filter", "env %r" % r["env_bus"])
    left = os.listdir(run + "/.flatpak") if os.path.isdir(run + "/.flatpak") else []
    chk(not left, "the instance's bwrapinfo.json is removed when the application exits", "left: %r" % left)
    socks = [f for f in os.listdir(run + "/prestium-confine") if f.startswith(".bus-")]
    chk(not socks, "the proxy's socket is removed", "left: %r" % socks)
finally:
    for p_ in reversed(procs):
        p_.terminate()
    time.sleep(0.3)
    subprocess.run(["fusermount3", "-uz", run + "/doc"], capture_output=True)
    for p_ in procs:
        try:
            p_.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p_.kill()
    if not os.environ.get("APP_CONFINE_KEEP"):
        subprocess.run(["rm", "-rf", T])
    else:
        print("kept", T)
sys.exit(1 if fails else 0)
