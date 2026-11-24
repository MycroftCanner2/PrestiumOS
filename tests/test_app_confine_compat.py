#!/usr/bin/python3
"""Compatibility audit of app-confine (after F-01): things that worked before the applications got their
own namespaces and must keep working in them.

  - GnuPG's passphrase prompt. gpg hands the application's DBUS_SESSION_BUS_ADDRESS to gpg-agent for the
    pinentry it starts. For Claws Mail and Kleopatra that agent is the session's (outside every
    namespace): the address must reach the session bus there too (app-confine links
    $XDG_RUNTIME_DIR/prestium-bus to bus outside). For Gajim and its keys tool the agent is their own,
    inside: their filtered bus must reach GCR's system prompter (and nothing else of the keyring).
  - Qt 5 tray icons (VLC, KeePassXC): org.kde.StatusNotifierItem-<own pid>-<n> may be owned, another
    process id's may not.
  - A volume mounted on the host after an application started (USB stick, VeraCrypt) appears in it
    (the namespace's mounts are slaves of the host's, not private).
  - Links in Gajim: GIO (not the portal) opens them; "env links-tor" makes Tor Browser GIO's default, and
    Gajim's AppArmor profile lets GIO read that entry and run its gio-launch-desktop wrapper.

Static checks always run; the functional ones skip without user namespaces, dbus-daemon, xdg-dbus-proxy,
python3-dbus, gpg or unshare --keep-caps. Nothing outside a temporary directory changes.
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
AA = os.path.join(I, "etc/apparmor.d")
fails = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fails
    fails += 1
    print("FAIL " + m)


def chk(cond, good, fail):
    (ok if cond else bad)(good if cond else fail)


# --- static -----------------------------------------------------------------------------------------
src = open(AC).read()
setup_src = src[src.index("def setup("):src.index("def environment(")]
proxy_src = src[src.index("def proxy_root("):src.index("def start_proxy(")]
chk("MS_REC | MS_SLAVE" in setup_src and "MS_PRIVATE" not in setup_src,
    "the application's mounts are slaves of the host's (later USB sticks and volumes appear)",
    "setup() makes the mounts private: a volume mounted after the start stays invisible")
chk("MS_REC | MS_PRIVATE" in proxy_src, "the D-Bus filter's own root stays private", "proxy_root propagation")
chk("link_host_bus(run)" in src, "app-confine links prestium-bus to the session bus outside", "no host link")
inc = {f: open(os.path.join(POL, f)).read() for f in os.listdir(POL)}
users = sorted(f for f, t in inc.items() if re.search(r"^include pinentry\s*$", t, re.M))
chk(users == ["gajim.policy", "prestium-gajim-keys.policy"],
    "only Gajim and its keys tool (their own gpg-agent) may talk to GCR's prompter",
    "pinentry.inc is included by %r" % users)
chk(re.search(r"^talk org\.gnome\.keyring\.SystemPrompter\s*$", inc["pinentry.inc"], re.M)
    and len([l for l in inc["pinentry.inc"].splitlines() if l.strip() and not l.startswith("#")]) == 1,
    "pinentry.inc: one talk rule, the system prompter", "pinentry.inc: %r" % inc["pinentry.inc"])
chk(re.search(r"^tray-items\s*$", inc["tray.inc"], re.M), "tray.inc: Qt 5 tray item names", "tray.inc lacks tray-items")
pl = open(os.path.join(R, "config/package-lists/prestium.list.chroot")).read()
chk(re.search(r"^gcr$", pl, re.M) and re.search(r"^pinentry-gnome3$", pl, re.M),
    "gcr (gcr-prompter) and pinentry-gnome3 are installed", "package list: gcr / pinentry-gnome3")
pp = open(os.path.join(AA, "prestium.pinentry")).read()
chk("owner @{run}/user/[0-9]*/prestium-bus rw," in pp, "pinentry's profile allows the bus name the apps pass on",
    "prestium.pinentry: prestium-bus")

gp = open(os.path.join(AA, "usr.bin.gajim")).read()
for r in ("/usr/lib/@{multiarch}/glib-[0-9]*/gio-launch-desktop ix,", "/usr/local/share/applications/ r,",
          "/usr/local/share/applications/torbrowser.desktop r,",
          "/usr/local/bin/tor-browser Px -> prestium_tor_browser_launcher,"):
    chk(r in gp, "gajim profile: %s" % r, "gajim profile lacks %s" % r)
chk(not re.search(r"librewolf|/usr/local/share/applications/\*", gp), "gajim profile: no I2P Browser, no other entries",
    "gajim profile reaches the I2P Browser or every .desktop entry")
chk(re.search(r"^env links-tor\s*$", inc["gajim.policy"], re.M), "gajim.policy: env links-tor", "gajim.policy: no links-tor")
LT = os.path.join(I, "usr/share/prestium/links-tor")
lt = open(os.path.join(LT, "mimeapps.list")).read()
chk(re.search(r"^x-scheme-handler/https=torbrowser\.desktop$", lt, re.M)
    and re.search(r"^x-scheme-handler/http=torbrowser\.desktop$", lt, re.M),
    "links-tor/mimeapps.list: http(s) -> Tor Browser", "links-tor/mimeapps.list: %r" % lt)
perms_txt = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
chk("0644 root root /usr/share/prestium/links-tor/mimeapps.list\n" in perms_txt, "perms.txt: links-tor", "perms.txt lacks links-tor")


def gio_default(env_dirs):
    """GIO's handler for an https link, with the image's two web entries and stand-in launchers."""
    with tempfile.TemporaryDirectory(prefix="acgio-") as d:
        os.makedirs(d + "/data/applications")
        os.makedirs(d + "/bin")
        for f in ("torbrowser.desktop", "librewolf.desktop"):
            shutil.copy(os.path.join(I, "usr/local/share/applications", f), d + "/data/applications/")
        for b in ("tor-browser", "librewolf-i2p"):
            open("%s/bin/%s" % (d, b), "w").write('#!/bin/sh\necho "$0 $1" > %s/ran\n' % d)
            os.chmod("%s/bin/%s" % (d, b), 0o755)
        env = dict(os.environ, PATH=d + "/bin:/usr/bin:/bin", HOME=d, XDG_CONFIG_HOME=d + "/c",
                   XDG_DATA_HOME=d + "/d", XDG_DATA_DIRS=d + "/data",
                   XDG_CONFIG_DIRS=env_dirs.replace("/usr/share/prestium/links-tor", LT))
        subprocess.run([sys.executable, "-c", "from gi.repository import Gio\ntry:\n"
                        "    Gio.AppInfo.launch_default_for_uri('https://example.org/', None)\n"
                        "except Exception as e:\n    print(e)"], env=env, capture_output=True, timeout=30)
        for _ in range(50):
            if os.path.exists(d + "/ran"):
                return os.path.basename(open(d + "/ran").read().split()[0])
            time.sleep(0.1)
        return None

def load(policy_dir):
    s = src.replace('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = %r' % policy_dir)
    s = s.replace("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")
    ns = {"__name__": "app_confine"}
    exec(compile(s, AC, "exec"), ns)
    return ns



import importlib.util as _iu
if _iu.find_spec("gi") is None:
    print("SKIP GIO link check: python3-gi missing")
else:
    envs = load(POL)["ENV_SETS"]
    got = gio_default(envs["links-tor"]["XDG_CONFIG_DIRS"])
    chk(got == "tor-browser", "Gajim's environment: GIO opens https links in Tor Browser",
        "Gajim's environment: GIO opens links with %r" % got)
    got = gio_default("/etc/xdg")
    chk(got != "tor-browser", "(control) without links-tor GIO does not pick Tor Browser (%r)" % got,
        "the GIO check proves nothing: Tor Browser is the default without links-tor")

T = tempfile.mkdtemp(prefix="acompat-")
procs = []
try:
    pd = T + "/policies"
    shutil.copytree(POL, pd)
    for n, body in {"x-own-prompter": "own org.gnome.keyring.SystemPrompter\n",
                    "x-talk-keyring": "talk org.gnome.keyring\n",
                    "x-talk-secrets": "talk org.freedesktop.secrets\n",
                    "x-own-tray": "own org.kde.StatusNotifierItem-1-1\n",
                    "x-tray-none": "bus none\ntray-items\n"}.items():
        open("%s/%s.policy" % (pd, n), "w").write(body)
    ac = load(pd)
    for n in ("x-own-prompter", "x-talk-keyring", "x-talk-secrets", "x-own-tray", "x-tray-none"):
        try:
            ac["parse_policy"](n)
            bad("policy %s is accepted" % n)
        except ac["Fail"]:
            ok("policy refused: %s" % n)
    for n in ("gajim", "prestium-gajim-keys"):
        a = ac["parse_policy"](n)["args"]
        chk("--talk=org.gnome.keyring.SystemPrompter" in a, "%s: GCR's prompter" % n, "%s: %r" % (n, a))
    for n in ("vlc", "keepassxc", "gajim", "kleopatra", "claws-mail", "onionshare", "feather"):
        chk(ac["parse_policy"](n)["tray_items"], "%s: tray item names" % n, "%s: no tray-items" % n)
    for n in ("claws-mail", "kleopatra", "vlc", "keepassxc"):
        chk("--talk=org.gnome.keyring.SystemPrompter" not in ac["parse_policy"](n)["args"],
            "%s: no prompter (the session's agent prompts outside)" % n, "%s talks to the prompter" % n)

    # --- functional -----------------------------------------------------------------------------------
    def need():
        for t in ("dbus-daemon", "xdg-dbus-proxy", "gpg", "gpg-connect-agent", "gpgconf", "unshare"):
            if not shutil.which(t):
                return t + " missing"
        import importlib.util
        if importlib.util.find_spec("dbus") is None or importlib.util.find_spec("gi") is None:
            return "python3-dbus or python3-gi missing"
        if subprocess.run(["unshare", "-Urm", "true"], capture_output=True).returncode != 0:
            return "user namespaces unavailable"
        return None

    why = need()
    if why:
        print("SKIP functional checks: " + why)
        sys.exit(1 if fails else 0)
    uid = os.getuid()
    RU = T + "/run/user"
    run = "%s/%d" % (RU, uid)
    os.makedirs(run, 0o700)
    os.chmod(RU, 0o755)
    os.makedirs(run + "/gnupg", 0o700)
    os.makedirs(T + "/run/dbus")
    os.makedirs("%s/run/prestium-wl/%d" % (T, uid))
    os.makedirs(T + "/tmp/.X11-unix")
    os.chmod(T + "/tmp", 0o1777)
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
    open(svc, "w").write('''import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
b = dbus.bus.BusConnection("unix:path=%s/bus")
class O(dbus.service.Object):
    @dbus.service.method("org.prestium.Test", out_signature="s")
    def Ping(self): return "pong"
names = [dbus.service.BusName(n, b) for n in ("org.gnome.keyring.SystemPrompter", "org.gnome.keyring",
         "org.freedesktop.secrets", "org.freedesktop.Notifications", "org.kde.StatusNotifierWatcher")]
O(b, "/x"); print("ready", flush=True); GLib.MainLoop().run()
''' % run)
    sp = subprocess.Popen([sys.executable, svc], stdout=subprocess.PIPE, text=True)
    procs.append(sp)
    sp.stdout.readline()

    probe = T + "/probe.py"
    open(probe, "w").write(r'''#!/usr/bin/python3
import json, os, subprocess, sys
r = {"env_bus": os.environ.get("DBUS_SESSION_BUS_ADDRESS")}
mode = os.environ.get("PROBE_MODE", "bus")
if mode == "gpg":
    p = subprocess.run(["gpg-connect-agent", "GET_PASSPHRASE --data --check probe X Prompt Desc", "/bye"],
                       capture_output=True, text=True, timeout=30, env=dict(os.environ, GNUPGHOME="%(T)s/gh"))
    r["agent"] = p.stdout.strip().splitlines()[:2]
elif mode == "mount":
    import time; time.sleep(2)
    r["mounted"] = os.path.ismount("%(T)s/shr/in")
else:
    import dbus
    b = dbus.bus.BusConnection(os.environ["DBUS_SESSION_BUS_ADDRESS"])
    def call(n):
        try: return str(b.get_object(n, "/x").Ping(dbus_interface="org.prestium.Test"))
        except dbus.DBusException as e: return e.get_dbus_name()
    for k, n in (("prompter", "org.gnome.keyring.SystemPrompter"), ("keyring", "org.gnome.keyring"),
                 ("secrets", "org.freedesktop.secrets")):
        r[k] = call(n)
    def own(n):
        try: return int(b.request_name(n))
        except dbus.DBusException as e: return e.get_dbus_name()
    r["tray_mine"] = own("org.kde.StatusNotifierItem-%%d-1" %% os.getpid())
    r["tray_other"] = own("org.kde.StatusNotifierItem-%%d-1" %% (os.getpid() + 1))
    r["own_prompter"] = own("org.gnome.keyring.SystemPrompter")
print("PROBE " + json.dumps(r), flush=True)
''' % {"T": T})
    os.chmod(probe, 0o755)
    s = src.replace('RUN_USER = "/run/user"', 'RUN_USER = "%s"' % RU)
    s = s.replace('SYSBUS_DIR = "/run/dbus"', 'SYSBUS_DIR = "%s/run/dbus"' % T)
    s = s.replace('WL_BASE = "/run/prestium-wl"', 'WL_BASE = "%s/run/prestium-wl"' % T)
    s = s.replace('TMP = "/tmp"', 'TMP = "%s/tmp"' % T)
    s = s.replace("APPS = {\n", "APPS = {\n"
                  '    "p-gajim": (%(p)r, "gajim", "gajim", "private"),\n'
                  '    "p-keys": (%(p)r, "gajim", "prestium-gajim-keys", "private"),\n'
                  '    "p-claws": (%(p)r, "claws-mail", "claws-mail", "shared"),\n'
                  '    "p-vlc": (%(p)r, "vlc", "vlc", None),\n'
                  '    "p-nobus": (%(p)r, "mat2", "mat2", None),\n' % {"p": probe}, 1)
    s = s.replace('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = "%s"' % pd)
    s = s.replace("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")
    pc = T + "/app-confine"
    open(pc, "w").write(s)
    os.chmod(pc, 0o755)

    def run_probe(name, mode="bus", wrap=None, extra=None):
        env = {"PATH": "/usr/bin:/bin", "HOME": T, "PROBE_MODE": mode}
        env.update(extra or {})
        p = subprocess.run((wrap or []) + [sys.executable, "-I", pc, name], capture_output=True, text=True,
                           timeout=90, cwd=T, env=env)
        for line in p.stdout.splitlines():
            if line.startswith("PROBE "):
                return json.loads(line[6:])
        bad("%s (%s): no probe output (rc %d): %s" % (name, mode, p.returncode, p.stderr.strip()[-400:]))
        return None

    for n in ("p-gajim", "p-keys"):
        r = run_probe(n)
        if r:
            chk(r["prompter"] == "pong", "%s: GCR's prompter answers (pinentry-gnome3 can ask)" % n, "%s: %r" % (n, r))
            chk(r["keyring"] != "pong" and r["secrets"] != "pong", "%s: not the keyring or Secret Service" % n,
                "%s reached the keyring: %r" % (n, r))
            chk(r["own_prompter"] not in (1, 2, 3, 4), "%s: may not own the prompter's name" % n, "%s owns it" % n)
    r = run_probe("p-vlc")
    if r:
        chk(r["tray_mine"] == 1, "VLC's policy: its own org.kde.StatusNotifierItem-<pid>-1 (Qt 5 tray)", "tray: %r" % r)
        chk(r["tray_other"] not in (1, 2, 3, 4), "VLC's policy: not another process's tray name", "tray other: %r" % r)
        chk(r["prompter"] != "pong", "VLC's policy: no prompter", "vlc reached the prompter")

    # the session's gpg-agent (outside) starts pinentry with the address the application passed on
    gh = T + "/gh"
    os.makedirs(gh, 0o700)
    pe = T + "/pinentry.py"
    open(pe, "w").write(r'''#!/usr/bin/python3
import os, socket, sys
a = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
res = "none"
if a.startswith("unix:path="):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(a[10:].split(",")[0]); res = "connected"
    except OSError as e:
        res = "refused:" + e.__class__.__name__
open("%s/pinentry.result", "w").write(a + " " + res + "\n")
print("OK ready", flush=True)
for line in sys.stdin:
    c = line.split(" ", 1)[0].strip()
    if c == "GETPIN":
        print("D pw" if res == "connected" else "ERR 83886179 no bus", flush=True)
        if res == "connected": print("OK", flush=True)
    elif c == "BYE":
        print("OK", flush=True); break
    else:
        print("OK", flush=True)
''' % T)
    os.chmod(pe, 0o755)
    open(gh + "/gpg-agent.conf", "w").write("pinentry-program %s\n" % pe)
    henv = {"PATH": "/usr/bin:/bin", "HOME": T, "GNUPGHOME": gh}
    subprocess.run(["gpg-connect-agent", "/bye"], env=henv, capture_output=True, timeout=30)
    r = run_probe("p-claws", "gpg")
    res = open(T + "/pinentry.result").read().split() if os.path.exists(T + "/pinentry.result") else ["?", "?"]
    chk(res[-1] == "connected" and r and any(l.startswith("D ") for l in r["agent"]),
        "Claws Mail / Kleopatra: the session agent's pinentry reaches the session bus (passphrase prompt)",
        "pinentry got %r, agent said %r" % (res, r and r["agent"]))
    subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=henv, capture_output=True, timeout=30)

    # a volume mounted on the host after the start (in a user namespace standing in for the host)
    os.makedirs(T + "/shr")
    script = ("mount -t tmpfs s %(T)s/shr && mount --make-shared %(T)s/shr && mkdir %(T)s/shr/in && "
              "( sleep 0.8; mount -t tmpfs v %(T)s/shr/in ) & exec \"$@\"" % {"T": T})
    w = ["unshare", "--map-current-user", "--keep-caps", "-m", "--propagation", "unchanged", "sh", "-c", script, "sh"]
    if subprocess.run(w[:-4] + ["true"], capture_output=True).returncode != 0:
        print("SKIP the mount check: unshare --keep-caps is unavailable")
    else:
        r = run_probe("p-nobus", "mount", wrap=w)
        chk(r is not None and r.get("mounted") is True, "a volume mounted after the start appears in the application",
            "not visible: %r" % r)
finally:
    for p in procs:
        p.kill()
    subprocess.run(["rm", "-rf", T])
sys.exit(1 if fails else 0)
