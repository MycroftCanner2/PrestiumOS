#!/usr/bin/python3
"""Launch check (every menu application started in a booted image chroot, strace compared with its
AppArmor profile): the fixes it needed stay in place.

  - Gajim: GStreamer's plugin scanner is where Debian installs it
    (/usr/lib/<multiarch>/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner); the profile's old rule
    never matched, so GStreamer loaded every plugin inside Gajim itself.
  - Local Firefox: no Wayland proxy (its socket in $XDG_RUNTIME_DIR is not in the profile; it printed
    "StartProxyServer(): bind() error" at every start).
  - Metadata Cleaner: no GVfs volume monitors (D-Bus services app-confine keeps off its bus; GTK's
    file chooser printed five D-Bus errors at every start).
Nothing outside a temporary directory changes.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config", "includes.chroot")
AC = os.path.join(I, "usr/local/lib/prestium/app-confine")
POL = os.path.join(I, "usr/share/prestium/app-confine")
fails = 0


def chk(cond, good, fail):
    global fails
    print(("OK   " + good) if cond else ("FAIL " + fail))
    fails += 0 if cond else 1


def aa_glob(p):
    """AppArmor glob (with @{multiarch} = *-linux-gnu*) -> regex, enough for the rules used here."""
    p = p.replace("@{multiarch}", "*-linux-gnu*")
    out = ""
    i = 0
    while i < len(p):
        if p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "{":
            j = p.index("}", i)
            out += "(?:" + "|".join(re.escape(a) for a in p[i + 1:j].split(",")) + ")"
            i = j + 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(out + r"\Z")


# --- Gajim: the plugin scanner -----------------------------------------------------------------------
prof = open(os.path.join(I, "etc/apparmor.d/usr.bin.gajim")).read()
rules = re.findall(r"^\s*(/\S+)\s+([a-zA-Z]+),", prof, re.M)
SCANNER = "/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner"


def perms(path):
    return "".join(m for g, m in rules if aa_glob(g).match(path))


chk("ix" in perms(SCANNER), "gajim: Debian's gst-plugin-scanner runs in Gajim's profile (ix)",
    "gajim: no x rule for %s (%r)" % (SCANNER, perms(SCANNER)))
chk("x" not in perms("/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/other-helper"),
    "gajim: nothing else in that directory may run", "gajim: other helpers there are executable")
for real in ("/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner",):
    if os.path.exists(real):  # a build host or a Prestium image with GStreamer
        chk("ix" in perms(os.path.realpath(real)), "gajim: installed scanner %s covered" % real,
            "gajim: installed scanner %s not covered" % real)

# --- local Firefox: no Wayland proxy ------------------------------------------------------------------
LF = os.path.join(I, "usr/local/bin/prestium-localfox")
lf = open(LF).read()
chk(re.search(r"^MOZ_DISABLE_WAYLAND_PROXY=1; export MOZ_DISABLE_WAYLAND_PROXY$", lf, re.M) and
    lf.index("MOZ_DISABLE_WAYLAND_PROXY=1") < lf.index("exec "),
    "prestium-localfox: Wayland proxy off before Firefox starts", "prestium-localfox: Wayland proxy on")
prof = open(os.path.join(I, "etc/apparmor.d/opt.firefox.firefox")).read()
chk("wayland-proxy" not in prof, "local Firefox profile: still no Wayland proxy socket",
    "local Firefox profile: a wayland-proxy rule appeared (the variable is the fix)")
t = tempfile.mkdtemp(prefix="launchcheck-")
try:  # run the real script with Firefox, sg and the shared files replaced by stand-ins
    stub = os.path.join(t, "firefox")
    with open(stub, "w") as f:
        f.write('#!/bin/sh\necho "proxy=${MOZ_DISABLE_WAYLAND_PROXY:-unset}"\n')
    os.chmod(stub, 0o755)
    share = os.path.join(t, "share")
    os.makedirs(os.path.join(share, "prestium-localfox"))
    os.makedirs(os.path.join(share, "prestium-nssdb"))
    for f in ("prestium-localfox/user.js", "prestium-nssdb/cert9.db", "prestium-nssdb/key4.db"):
        open(os.path.join(share, f), "w").close()
    s = lf.replace("/opt/firefox/firefox", stub).replace("/usr/local/share", share)
    s = s.replace("exec sg prestium-localweb -c", "exec sh -c")
    with open(os.path.join(t, "lf"), "w") as f:
        f.write(s)
    env = {"PATH": "/usr/bin:/bin", "HOME": os.path.join(t, "home")}
    os.makedirs(env["HOME"])
    r = subprocess.run(["sh", os.path.join(t, "lf"), "http://127.0.0.1:7070/"], env=env,
                       capture_output=True, text=True, timeout=20)
    chk(r.stdout.strip() == "proxy=1", "prestium-localfox: Firefox gets MOZ_DISABLE_WAYLAND_PROXY=1",
        "prestium-localfox: Firefox got %r (rc %d, %r)" % (r.stdout, r.returncode, r.stderr))
finally:
    shutil.rmtree(t)

# --- Metadata Cleaner: no GVfs volume monitors ----------------------------------------------------------
src = open(AC).read().replace('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = %r' % POL)
src = src.replace("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")
ac = types.ModuleType("app_confine")
exec(compile(src, AC, "exec"), ac.__dict__)
want = {"GVFS_REMOTE_VOLUME_MONITOR_IGNORE": "1"}
pol = ac.parse_policy("metadata-cleaner")
chk(pol["env"] == want, "metadata-cleaner: env gio-local", "metadata-cleaner env: %r" % pol["env"])
env = ac.environment(os.getuid(), True, pol["env"])
chk(env.get("GVFS_REMOTE_VOLUME_MONITOR_IGNORE") == "1", "metadata-cleaner: the variable reaches it",
    "metadata-cleaner: variable not in its environment")
chk(all(not k.startswith("GIO_") for k in ac.ENV_SETS.get("gio-local", {"GIO_": 1})), "gio-local changes no GIO module choice",
    "gio-local: %r" % ac.ENV_SETS.get("gio-local", {"GIO_": 1}))
chk("org.gtk.vfs." in ac.FORBIDDEN, "org.gtk.vfs.* stays forbidden", "org.gtk.vfs. allowed")
for n in os.listdir(POL):
    if n.endswith(".policy") and n != "metadata-cleaner.policy":
        e = ac.parse_policy(n[:-7])["env"]
        chk("GVFS_REMOTE_VOLUME_MONITOR_IGNORE" not in e, "%s: unchanged" % n[:-7], "%s: gio-local too" % n)
MOD = "/usr/lib/x86_64-linux-gnu/gio/modules/libgioremote-volume-monitor.so"
if os.path.exists(MOD):  # gvfs installed: its module still knows the variable
    chk(b"GVFS_REMOTE_VOLUME_MONITOR_IGNORE" in open(MOD, "rb").read(), "gvfs honours the variable",
        "gvfs module no longer reads GVFS_REMOTE_VOLUME_MONITOR_IGNORE")
else:
    print("SKIP gvfs not installed here (the image's gvfs 1.5x module reads the variable)")

print("%d failure(s)" % fails)
sys.exit(1 if fails else 0)
