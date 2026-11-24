#!/usr/bin/python3
"""Security review F-01 (per-application buses): app-confine's bus policies, statically.

Every application in app-confine's table has a policy file; each parses with app-confine's own parser
and gives xdg-dbus-proxy only allowed rules: no systemd, logind, dconf, bus driver, Flatpak, portal back
end, keyring or other application's name; talk only to notifications and the tray; portal calls only
from the fixed list (file chooser, OpenURI.OpenURI, settings, requests; never OpenFile, OpenDirectory,
Background, Camera, ScreenCast, RemoteDesktop, Trash, Inhibit, Print, Email, Properties.Set, ...). The
parser refuses crafted policies. Also the portal side: portals.conf (no back end by default), the
portal's drop-in (back ends and handlers only from Prestium's read-only directories), the link handler
and portal-open's rules, the AppArmor side (prestium-app-documents only for the applications with
"documents", the proxy's own profile) and the build checks in hook 0625.
"""
import os
import re
import sys
import tempfile
import types

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config", "includes.chroot")
AC = os.path.join(I, "usr/local/lib/prestium/app-confine")
POL = os.path.join(I, "usr/share/prestium/app-confine")
fails = 0


def ok(m):
    print("OK   " + m)


def bad(m):
    global fails
    fails += 1
    print("FAIL " + m)


def chk(cond, good, fail):
    (ok if cond else bad)(good if cond else fail)


def load(policy_dir):
    src = open(AC).read()
    src = src.replace('POLICY_DIR = "/usr/share/prestium/app-confine"', 'POLICY_DIR = %r' % policy_dir)
    src = src.replace("st.st_uid != 0 or", "st.st_uid not in (0, os.getuid()) or")
    m = types.ModuleType("app_confine")
    m.__dict__["__name__"] = "app_confine"
    exec(compile(src, AC, "exec"), m.__dict__)
    return m


ac = load(POL)
FORBIDDEN_NAMES = ("org.freedesktop.systemd1", "org.freedesktop.login1", "org.freedesktop.DBus", "ca.desrt.dconf",
                   "org.freedesktop.Flatpak", "org.freedesktop.portal.Flatpak", "org.freedesktop.impl.portal",
                   "org.gnome.keyring", "org.freedesktop.secrets", "org.gtk.vfs", "org.a11y", "org.prestium",
                   "org.freedesktop.PolicyKit1", "org.freedesktop.FileManager1")
FORBIDDEN_RULES = ("OpenURI.OpenFile", "OpenURI.OpenDirectory", "portal.Background", "portal.Camera", "portal.ScreenCast",
                   "portal.RemoteDesktop", "portal.Screenshot", "portal.Trash", "portal.Inhibit", "portal.Print",
                   "portal.Email", "portal.DynamicLauncher", "portal.Secret", "portal.Location", "portal.Account",
                   "portal.GlobalShortcuts", "portal.InputCapture", "portal.Usb", "portal.Wallpaper", "portal.Notification",
                   "portal.FileTransfer", "Properties.Set", "Documents.Add", "portal.Device", "portal.Realtime")
# compatibility audit: the Gajim keys tool has a bus with GCR's prompter only (its gpg-agent's pinentry)
EXPECT_NO_BUS = {"onionshare-cli", "mat2", "prestium-translate", "audacity"}
PROMPTER_OK = {"gajim", "prestium-gajim-keys"}
EXPECT_DOCS = {"gajim", "onionshare", "featherpad", "fpad", "vlc"}
EXPECT_LINKS = {"gajim"}
EXPECT_QT = {"onionshare", "featherpad", "fpad", "vlc"}

pols = {}
owners = {}
for n, (prog, group, policy, gnupg) in sorted(ac.APPS.items()):
    try:
        pol = ac.parse_policy(policy)
    except ac.Fail as e:
        bad("%s: policy %s does not parse: %s" % (n, policy, e))
        continue
    pols[n] = pol
    args = pol["args"]
    for a in args:
        m = re.match(r"^--(talk|own|call|broadcast)=([^=]+)(=(.*))?$", a)
        if not m:
            bad("%s: odd proxy argument %s" % (n, a))
            continue
        kind, name, rule = m.group(1), m.group(2), m.group(4) or ""
        # compatibility audit: GCR's passphrase prompter (not the keyring) for the two applications with
        # a gpg-agent of their own (test_app_confine_compat.py)
        prompter = kind == "talk" and name == "org.gnome.keyring.SystemPrompter" and policy in PROMPTER_OK
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN_NAMES) and not prompter:
            bad("%s: %s" % (n, a))
        if kind == "talk" and name not in ("org.freedesktop.Notifications", "org.kde.StatusNotifierWatcher") and not prompter:
            bad("%s: talks to %s" % (n, name))
        if kind in ("talk", "own") and name.startswith("org.freedesktop.portal"):
            bad("%s: %s a portal name (only --call/--broadcast rules)" % (n, kind))
        if kind in ("call", "broadcast") and name not in ("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Documents"):
            bad("%s: call rule for %s" % (n, name))
        if any(f in rule for f in FORBIDDEN_RULES):
            bad("%s: forbidden portal rule %s" % (n, a))
        if kind == "own":
            if name in ("*", ) or re.match(r"^[^.]+\.\*$", name):
                bad("%s: owns a wildcard %s" % (n, name))
            owners.setdefault(name, set()).add(policy)
    for cond, name in pol["own_if"]:
        owners.setdefault(name, set()).add(policy)
    if pol["bus"]:
        ok("%s (%s): %s" % (n, policy, ", ".join(sorted({a.split("=", 1)[0][2:] + " " + a.split("=")[1] for a in args}))))
for name, ps in sorted(owners.items()):
    chk(len(ps) == 1, "own %s: only %s" % (name, ", ".join(ps)), "own %s: several policies %s" % (name, sorted(ps)))
# no policy can own a name another policy talks to (other applications' names)
talks = {a.split("=", 1)[1] for p in pols.values() for a in p["args"] if a.startswith("--talk=")}
chk(not (set(owners) & talks), "no policy owns a name another one talks to", "owned and talked: %s" % (set(owners) & talks))

nobus = {n for n, p in pols.items() if not p["bus"]}
chk(nobus == EXPECT_NO_BUS, "no session bus at all: %s" % ", ".join(sorted(nobus)), "no bus: %s (expected %s)" % (sorted(nobus), sorted(EXPECT_NO_BUS)))
docs = {n for n, p in pols.items() if p["documents"]}
chk(docs == EXPECT_DOCS, "document portal (file chooser): %s" % ", ".join(sorted(docs)), "documents: %s" % sorted(docs))
links = {n for n, p in pols.items() if any("OpenURI.OpenURI" in a for a in p["args"])}
chk(links == EXPECT_LINKS, "OpenURI (links): %s" % ", ".join(sorted(links)), "OpenURI: %s" % sorted(links))
qt = {n for n, p in pols.items() if p["env"].get("QT_QPA_PLATFORMTHEME") == "xdgdesktopportal"}
chk(qt == EXPECT_QT, "Qt portal plugin: %s" % ", ".join(sorted(qt)), "qt-portal: %s" % sorted(qt))
chk(all(set(p["env"]) <= {"QT_QPA_PLATFORMTHEME"} for n, p in pols.items() if n not in ("gajim", "metadata-cleaner")),
    "env: only the Qt platform theme", "env")
chk(pols["metadata-cleaner"]["env"] == {"GVFS_REMOTE_VOLUME_MONITOR_IGNORE": "1"},
    "env: Metadata Cleaner's gio-local (no GVfs volume monitors)", "metadata-cleaner env: %r" % pols["metadata-cleaner"]["env"])
# compatibility audit: Gajim's GIO link handler (Tor Browser), nothing else
chk(pols["gajim"]["env"] == {"XDG_CONFIG_DIRS": "/usr/share/prestium/links-tor:/etc/xdg"},
    "env: Gajim's links-tor (GIO's default for links: Tor Browser)", "gajim env: %r" % pols["gajim"]["env"])
chk(not any("GTK_USE_PORTAL" in str(p["env"]) for p in pols.values()), "no GTK_USE_PORTAL (GIO file launches stay off the portal)", "GTK_USE_PORTAL")
kp = pols.get("keepassxc")
chk(kp and kp["own_if"] == [("keepassxc-secret-service", "org.freedesktop.secrets")] and "--own=org.freedesktop.secrets" not in kp["args"],
    "KeePassXC: org.freedesktop.secrets only while its FdoSecrets setting is on", "keepassxc own-if %r" % (kp and kp["own_if"]))
for n in ("libreoffice", "kleopatra", "evince", "loupe", "vlc", "gajim", "file-roller", "metadata-cleaner", "featherpad", "onionshare", "keepassxc"):
    chk(any(a.startswith("--own=") for a in pols[n]["args"]), "%s: owns its own names (single instance)" % n, "%s owns nothing" % n)

# own-if: KeePassXC's setting
with tempfile.TemporaryDirectory() as h:
    import pwd
    real = pwd.getpwuid

    class PW:
        pw_dir = h
    ac.pwd.getpwuid = lambda u: PW
    try:
        chk(not ac.own_if_holds("keepassxc-secret-service", os.getuid()), "own-if: no keepassxc.ini, no Secret Service", "own-if without ini")
        os.makedirs(h + "/.config/keepassxc")
        open(h + "/.config/keepassxc/keepassxc.ini", "w").write("[General]\nEnabled=true\n[FdoSecrets]\nEnabled=false\n")
        chk(not ac.own_if_holds("keepassxc-secret-service", os.getuid()), "own-if: FdoSecrets off", "own-if with FdoSecrets off")
        open(h + "/.config/keepassxc/keepassxc.ini", "w").write("[Browser]\nEnabled=true\n\n[FdoSecrets]\nEnabled=true\n")
        chk(ac.own_if_holds("keepassxc-secret-service", os.getuid()), "own-if: FdoSecrets on", "own-if with FdoSecrets on")
        chk(not ac.own_if_holds("other", os.getuid()), "own-if: unknown condition is false", "own-if unknown")
    finally:
        ac.pwd.getpwuid = real

# the parser refuses crafted policies
BADS = {
    "talk systemd": "talk org.freedesktop.systemd1",
    "talk another app": "talk org.gajim.Gajim",
    "talk the portal": "talk org.freedesktop.portal.Desktop",
    "own the secret service": "own org.freedesktop.secrets",
    "own a portal": "own org.freedesktop.portal.Desktop",
    "own dconf": "own ca.desrt.dconf",
    "own a wildcard": "own org.*",
    "own everything": "own *",
    "Background": "call org.freedesktop.portal.Desktop org.freedesktop.portal.Background.RequestBackground@/org/freedesktop/portal/desktop",
    "OpenFile": "call org.freedesktop.portal.Desktop org.freedesktop.portal.OpenURI.OpenFile@/org/freedesktop/portal/desktop",
    "a whole portal": "call org.freedesktop.portal.Desktop *",
    "any path": "call org.freedesktop.portal.Desktop org.freedesktop.portal.FileChooser.OpenFile",
    "systemd call": "call org.freedesktop.systemd1 org.freedesktop.systemd1.Manager.StartTransientUnit@/org/freedesktop/systemd1",
    "broadcast all": "broadcast org.freedesktop.portal.Desktop *",
    "bus none and more": "bus none\ntalk org.freedesktop.Notifications",
    "documents alone": "documents",
    "include a path": "include ../../etc/passwd",
    "unknown env": "env GTK_USE_PORTAL=1",
    "own-if other name": "own-if keepassxc-secret-service org.freedesktop.systemd1",
    "unknown directive": "see org.freedesktop.systemd1",
    "bus driver": "talk org.freedesktop.DBus",
    "impl portal": "own org.freedesktop.impl.portal.desktop.gtk",
}
with tempfile.TemporaryDirectory() as d:
    for f in os.listdir(POL):
        if f.endswith(".inc"):
            open(os.path.join(d, f), "w").write(open(os.path.join(POL, f)).read())
    t = load(d)
    for what, text in BADS.items():
        open(os.path.join(d, "x.policy"), "w").write(text + "\n")
        try:
            t.parse_policy("x")
            bad("parser accepted: %s" % what)
        except t.Fail:
            ok("parser refuses: %s" % what)
    os.chmod(os.path.join(d, "x.policy"), 0o666)
    open(os.path.join(d, "x.policy"), "w").write("include notify\n")
    try:
        t.parse_policy("x")
        bad("parser accepted a world-writable policy file")
    except t.Fail:
        ok("parser refuses a policy file others can write")
    os.chmod(os.path.join(d, "x.policy"), 0o644)
    os.symlink(os.path.join(d, "x.policy"), os.path.join(d, "y.policy"))
    try:
        t.parse_policy("y")
        bad("parser followed a symlinked policy file")
    except t.Fail:
        ok("parser refuses a symlinked policy file")
    try:
        t.parse_policy("Gajim/../x")
        bad("parser accepted a path as policy name")
    except t.Fail:
        ok("parser refuses a path as policy name")

# every policy file is used, every fragment too
used = {v[2] for v in ac.APPS.values()}
files = {f[:-7] for f in os.listdir(POL) if f.endswith(".policy")}
chk(files == used, "every policy file belongs to an application", "unused policy files %s / missing %s" % (files - used, used - files))
src = open(AC).read()
chk("TALK = {" not in src and "--talk=%s\" % TALK" not in src, "no hard-coded talk table left", "old talk table")

# the portal side
pc = open(os.path.join(I, "usr/share/prestium/portal/portals/portals.conf")).read()
pc_lines = [l for l in pc.splitlines() if l and not l.startswith("#")]
chk(pc_lines == ["[preferred]", "default=none", "org.freedesktop.impl.portal.FileChooser=gtk",
                 "org.freedesktop.impl.portal.AppChooser=gtk", "org.freedesktop.impl.portal.Settings=gtk"],
    "portals.conf: no back end by default; GTK's for the file chooser, app chooser and settings only", "portals.conf %r" % pc_lines)
di = open(os.path.join(I, "etc/systemd/user/xdg-desktop-portal.service.d/prestium.conf")).read()
env = dict(re.findall(r"^Environment=([A-Z_]+)=(\S+)$", di, re.M))
chk(env.get("XDG_DESKTOP_PORTAL_DIR") == "/usr/share/prestium/portal/portals"
    and all(env.get(k, "").startswith("/usr/share/prestium/portal/open") for k in ("XDG_DATA_DIRS", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CONFIG_DIRS"))
    and ":" not in env.get("XDG_DATA_DIRS", ":"),
    "portal drop-in: back ends and link handlers only from Prestium's read-only directories", "drop-in %r" % env)
od = os.path.join(I, "usr/share/prestium/portal/open/applications")
chk(sorted(os.listdir(od)) == ["mimeapps.list", "prestium-portal-open.desktop"], "the portal knows one handler only", "handlers %r" % os.listdir(od))
d = open(os.path.join(od, "prestium-portal-open.desktop")).read()
chk("MimeType=x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/mailto;\n" in d
    and "Exec=/usr/local/lib/prestium/portal-open %u\n" in d, "handler: http, https, mailto -> portal-open", "handler desktop file")
for f in (os.path.join(od, "mimeapps.list"), os.path.join(I, "usr/share/prestium/portal/open/config/mimeapps.list")):
    m = open(f).read()
    chk(set(re.findall(r"^(x-scheme-handler/\w+)=prestium-portal-open.desktop$", m, re.M)) == {"x-scheme-handler/http", "x-scheme-handler/https", "x-scheme-handler/mailto"}
        and len([l for l in m.splitlines() if "=" in l]) == 3, "%s: defaults only for the three schemes" % os.path.relpath(f, I), "mimeapps %s" % f)

po_src = os.path.join(I, "usr/local/lib/prestium/portal-open")
po = types.ModuleType("portal_open")
po.__dict__["__name__"] = "portal_open"
exec(compile(open(po_src).read(), po_src, "exec"), po.__dict__)
for u, want in (("https://example.org/a?b=c", True), ("http://x.onion/", True), ("file:///etc/passwd", False),
                ("https://", False), ("javascript:alert(1)", False), ("HTTPS://Example.org", True), ("ftp://x/", False)):
    chk(bool(po.web(u)) == want, "portal-open web(%s) -> %s" % (u, want), "portal-open web(%s)" % u)
for u, want in (("mailto:a@b.c?subject=Hi&attach=/etc/passwd&body=x", "mailto:a@b.c?subject=Hi&body=x"),
                ("mailto:a%3F@b", None), ("mailto:?attach=/x", None), ("mailto://host/x", None),
                ("mailto:a@b?Attachment=x&cc=c@d", "mailto:a@b?cc=c%40d")):
    chk(po.mail(u) == want, "portal-open mail(%s) -> %s" % (u, want), "portal-open mail(%s) = %r" % (u, po.mail(u)))
pos = open(po_src).read()
chk("os.execve(PRESTIUM_RUN, [PRESTIUM_RUN, TOR_BROWSER, w], clean_env())" in pos and "os.execve(CLAWS, [CLAWS, m], clean_env())" in pos,
    "portal-open: Tor Browser through prestium-run, Claws Mail, a clean environment", "portal-open exec lines")
chk("XDG_DATA_DIRS" not in pos.split("KEEP = (")[1].split(")")[0], "portal-open: the portal's XDG directories are not passed on", "KEEP")

# AppArmor
aa = os.path.join(I, "etc/apparmor.d")
prof_of = {"gajim": "usr.bin.gajim", "onionshare": "usr.bin.onionshare", "featherpad": "usr.bin.featherpad",
           "fpad": "usr.bin.featherpad", "vlc": "usr.bin.vlc"}
inc = {f for f in os.listdir(aa) if os.path.isfile(os.path.join(aa, f)) and "abstractions/prestium-app-documents" in open(os.path.join(aa, f)).read()}
chk(inc == set(prof_of.values()), "prestium-app-documents only in the profiles of the applications with \"documents\"",
    "included by %s" % sorted(inc))
ad = open(os.path.join(aa, "abstractions/prestium-app-documents")).read()
rules = [l.strip() for l in ad.splitlines() if l.strip() and not l.strip().startswith("#")]
chk(rules == ["owner @{run}/user/[0-9]*/doc/ r,", "owner @{run}/user/[0-9]*/doc/** rwk,"], "prestium-app-documents: the doc view only", "rules %r" % rules)
xp = open(os.path.join(aa, "prestium.xdg-dbus-proxy")).read()
chk(re.search(r"^profile prestium_xdg_dbus_proxy /usr/bin/xdg-dbus-proxy ", xp, re.M) is not None and "deny network inet," in xp
    and not re.search(r"\b[PpCcUui]?x,", xp.replace("rwx,", "")),
    "xdg-dbus-proxy has its own profile (no network, runs nothing)", "prestium.xdg-dbus-proxy")
h6 = open(os.path.join(R, "config/hooks/live/0600-prestium-apparmor.hook.chroot")).read()
chk(h6.count("prestium.xdg-dbus-proxy") >= 2, "hook 0600 enforces and attach-checks the proxy's profile", "hook 0600")
h = open(os.path.join(R, "config/hooks/live/0625-prestium-app-confine.hook.chroot")).read()
for k in ('"$AC" --check', "/usr/libexec/xdg-document-portal", "/usr/libexec/xdg-desktop-portal-gtk", "-u /usr/bin/fusermount3",
          "/.flatpak-info", "qt6-xdgdesktopportal-platformtheme", "ln -sfn /usr/share/xdg-desktop-portal/portals/gtk.portal"):
    chk(k in h, "hook 0625: %s" % k, "hook 0625 lacks %s" % k)
pl = open(os.path.join(R, "config/package-lists/prestium.list.chroot")).read()
for pk in ("xdg-dbus-proxy", "xdg-desktop-portal", "xdg-desktop-portal-gtk", "qt5-xdgdesktopportal-platformtheme",
           "qt6-xdgdesktopportal-platformtheme", "fuse3"):
    chk(re.search(r"^%s$" % re.escape(pk), pl, re.M), "package %s" % pk, "package list lacks %s" % pk)
chk(not re.search(r"^xdg-desktop-portal-wlr$", pl, re.M), "no xdg-desktop-portal-wlr (no screen sharing)", "-wlr listed")
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
for f in sorted(os.listdir(POL)):
    if "0644 root root /usr/share/prestium/app-confine/%s\n" % f not in perms:
        bad("perms.txt: %s" % f)
chk("0755 root root /usr/local/lib/prestium/portal-open\n" in perms, "perms: portal-open, the policies", "perms.txt: portal-open")
sys.exit(1 if fails else 0)
