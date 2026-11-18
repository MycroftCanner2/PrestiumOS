#!/usr/bin/python3
"""Prestium 2.1: "zenity --file-selection" opens Prestium's file picker (one header bar: Cancel, title,
search, OK, minimise/maximise/close) instead of zenity's GTK 4 dialog under labwc's title bar (two bars).
Verified under labwc with grim; this checks option parsing, the zenity fallback and the wiring."""
import importlib.machinery, importlib.util, os, re, subprocess, sys, tempfile
sys.dont_write_bytecode = True
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
P = os.path.join(I, "usr/local/lib/prestium/file-picker")
fail = 0
def check(cond, msg):
    global fail
    print(("OK   " if cond else "FAIL ") + msg)
    fail |= not cond

src = open(P).read()
check(os.access(P, os.X_OK) and src.startswith("#!/usr/bin/python3"), "picker is an executable python3 script")
loader = importlib.machinery.SourceFileLoader("file_picker", P)
spec = importlib.util.spec_from_loader("file_picker", loader)
m = importlib.util.module_from_spec(spec); loader.exec_module(m)
pz = m.parse
o = pz(["--title", "Unlock Volume", "--file-selection", "--filename", "/home/user/"])
check(o and o["title"] == "Unlock Volume" and o["filename"] == "/home/user/" and not o["multiple"], "Unlock Volume's container chooser")
o = pz(["--title", "Unlock Volume", "--file-selection", "--title", "Keyfile(s)", "--multiple", "--separator", "\x1f"])
check(o and o["title"] == "Keyfile(s)" and o["multiple"] and o["separator"] == "\x1f", "keyfile chooser: last --title wins (like zenity), --multiple, --separator")
o = pz(["--file-selection", "--title=T", "--separator=;", "--directory"])
check(o and o["title"] == "T" and o["separator"] == ";" and o["directory"], "--opt=value forms, --directory")
check(pz(["--file-selection"])["separator"] == "|", "default separator is zenity's |")
for a in (["--file-selection", "--save"], ["--file-selection", "--file-filter", "*.su3"], ["--question"], ["--file-selection", "--title"]):
    check(pz(a) is None, "falls back to zenity for %s" % " ".join(a))
# fallback really execs zenity (stubbed) with the same arguments
with tempfile.TemporaryDirectory() as d:
    z = os.path.join(d, "zenity"); open(z, "w").write('#!/bin/sh\necho "zenity $*"\n'); os.chmod(z, 0o755)
    c = os.path.join(d, "picker"); open(c, "w").write(src.replace('ZENITY = "/usr/bin/zenity"', 'ZENITY = %r' % z)); os.chmod(c, 0o755)
    r = subprocess.run([sys.executable, c, "--file-selection", "--save", "--title", "x"], capture_output=True, text=True)
    check(r.stdout.strip() == "zenity --file-selection --save --title x", "fallback runs zenity: %r" % r.stdout.strip())
check('APP_ID = "org.prestium.FilePicker"' in src and "set_decoration_layout(\":minimize,maximize,close\")" in src, "own window (not *zenity*) with min/max/close in its header")
check("suggested-action" in src and "search-mode" in src and "set_default_widget(ok)" in src, "OK button, search toggle, double-click accepts")
check("GLib.idle_add(start_at)" in src, "start folder set after the window is up (no 'could not be displayed')")
w = open(os.path.join(I, "usr/local/bin/zenity")).read()
check("--file-selection) exec /usr/local/lib/prestium/file-picker \"$@\"" in w, "zenity wrapper routes --file-selection to the picker")
rc = open(os.path.join(I, "etc/xdg/labwc/rc.xml")).read()
check(re.search(r'<windowRule identifier="org.prestium.FilePicker">\s*<action name="AutoPlace" policy="center" />', rc) is not None and
      not re.search(r'identifier="org.prestium.FilePicker"[^>]*serverDecoration="yes"', rc), "labwc: picker centred, no second title bar")
check("0755 root root /usr/local/lib/prestium/file-picker" in open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read().splitlines(), "perms: picker")
check("gir1.2-gtk-4.0" in open(os.path.join(R, "config/package-lists/prestium-2.0.list.chroot")).read().split(), "GTK 4 bindings installed")
sys.exit(fail)
