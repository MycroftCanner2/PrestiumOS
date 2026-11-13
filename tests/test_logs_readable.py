#!/usr/bin/env python3
"""2.1: logs the desktop user can read (Tor, i2pd, onion-grater), without sudo or the journal group.
prestium-logs (run with a fake journalctl) writes only those three units, keeps only entries the journal
attributes to the unit (or to PID 1 about it), and replaces control, bidi and other invisible characters;
the unit is sandboxed and not root; the user gets no sudo rule and no systemd-journal/adm group; the
directory is group user, setgid; the confined apps can't read it; the hints point to the viewer."""
import json, os, re, stat, subprocess, sys, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; fail = 1; print("FAIL " + m)
def check(c, m): (ok if c else bad)(m)
rd = lambda p: open(os.path.join(R, p), encoding="utf-8").read()

EXP = os.path.join(I, "usr/local/sbin/prestium-logs")
VIEW = os.path.join(I, "usr/local/bin/prestium-logs-view")
check(subprocess.run([sys.executable, "-m", "py_compile", EXP], env=dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.gettempdir() + "/prestium-pyc")).returncode == 0, "prestium-logs compiles")
check(subprocess.run(["sh", "-n", VIEW]).returncode == 0, "prestium-logs-view parses")
for p in (EXP, VIEW):
    check(os.stat(p).st_mode & 0o111, os.path.basename(p) + " executable")

T = tempfile.mkdtemp()
out = os.path.join(T, "logs"); os.mkdir(out)
calls = os.path.join(T, "calls")
def ent(unit=None, msg="m", pid="123", ident="tor", ts="1762940000000000", **kw):
    e = {"__REALTIME_TIMESTAMP": ts, "_PID": pid, "SYSLOG_IDENTIFIER": ident, "MESSAGE": msg}
    if unit: e["_SYSTEMD_UNIT"] = unit
    e.update(kw); return e
ENT = {
    "tor@default.service": [
        ent("tor@default.service", "Bootstrapped 100% (done): Done"),
        ent("tor@default.service", "esc \x1b[31mred\x1b[0m bell\x07 nul\x00 cr\rlf"),
        ent("tor@default.service", "bidi \u202eevil\u202c zw\u200b\u2060 ls\u2028ps\u2029 tab\tend"),
        ent("tor@default.service", "two\nlines"),
        ent("tor@default.service", "forge\n2025-11-12 09:33:20 UTC tor: Bootstrapped 100% FAKE \\n end"),
        ent("tor@default.service", "zalgo a\u0301\u0302\u0303\u0304\u0305 b\u0301 c\u0301\u0302 d"),
        ent("tor@default.service", list(b"bytes \xff\x1b[2J ok")),
        ent("tor@default.service", "x" * 5000),
        ent(None, "Started tor@default.service.", pid="1", ident="systemd", UNIT="tor@default.service"),
        ent(None, "FORGED from another unit", pid="999", ident="evil", UNIT="tor@default.service"),
        ent("evil.service", "FORGED other unit"),
        ent(None, "FORGED object", pid="999", OBJECT_SYSTEMD_UNIT="tor@default.service"),
    ],
    "i2pd.service": [ent("i2pd.service", "i2pd: started", ident="i2pd")],
    "prestium-onion-grater.service": [ent("prestium-onion-grater.service", "refused: nyx (exe not allowed)", ident="onion-grater")],
}
fake = os.path.join(T, "journalctl")
with open(fake, "w") as f:
    f.write("#!%s\nimport json, sys\nENT = %r\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "u = sys.argv[sys.argv.index('-u') + 1]\nfor e in ENT.get(u, []): print(json.dumps(e))\n" % (sys.executable, ENT, calls))
os.chmod(fake, 0o755)
env = dict(os.environ, PRESTIUM_LOGS_OUT=out, PRESTIUM_LOGS_JOURNALCTL=fake, PRESTIUM_LOGS_ONCE="1")
r = subprocess.run([sys.executable, "-I", EXP], env=env, capture_output=True, text=True, timeout=60)
check(r.returncode == 0, "prestium-logs runs (%s)" % r.stderr.strip()[:200])
check(sorted(os.listdir(out)) == ["i2p.log", "onion-grater.log", "tor.log"], "exactly three files: %s" % sorted(os.listdir(out)))
units = sorted(re.findall(r"-u (\S+)", open(calls).read()))
check(units == sorted(ENT), "journalctl asked for exactly the three units: %s" % units)
check(all(" -b " in " " + l + " " and "-o json" in l for l in open(calls).read().splitlines()), "this boot only, JSON output")
tor = open(os.path.join(out, "tor.log"), encoding="utf-8").read()
check("Bootstrapped 100% (done): Done" in tor, "tor.log has Tor's lines")
check("systemd: Started tor@default.service." in tor, "systemd's own lines about the unit are kept")
check("FORGED" not in tor, "entries attributed to another unit or a forged UNIT= are dropped")
bad_chars = [c for c in tor if c != "\n" and (ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in "\u202e\u202c\u200b\u2060\u2028\u2029\ufeff")]
check(not bad_chars, "no control, bidi, zero-width or separator characters: %r" % bad_chars[:5])
check("esc ?[31mred?[0m bell? nul? cr?lf" in tor, "ESC, BEL, NUL and CR replaced with ?")
check("bidi ?evil? zw?? ls?ps? tab end" in tor, "bidi, zero-width, line/paragraph separators replaced; tab is a space")
check(": two\\nlines\n" in tor, "a multi-line message stays one line (\\n shown as text)")
check(not any(l.startswith("2025-11-12 09:33:20 UTC tor: Bootstrapped 100% FAKE") for l in tor.splitlines())
      and ": forge\\n2025-11-12 09:33:20 UTC tor: Bootstrapped 100% FAKE \\\\n end\n" in tor,
      "a newline can't forge a line; a backslash is doubled")
check(len([l for l in tor.splitlines() if not l.startswith("#")]) == 9, "one line per entry kept (%d)" % len(tor.splitlines()))
check("zalgo a\u0301\u0302? b\u0301 c\u0301\u0302 d" in tor, "at most 2 combining marks per character, the rest one ?")
check("bytes \ufffd?[2J ok" in tor, "byte-array messages decoded, escapes replaced")
check(max(len(l) for l in tor.splitlines()) <= 1000, "lines cut at 1000 characters")
for name in ("i2p", "onion-grater"):
    t = open(os.path.join(out, name + ".log"), encoding="utf-8").read()
    check(t.count("\n") == 2 and "Bootstrapped" not in t, "%s.log has only its own unit" % name)
check(all(stat.S_IMODE(os.stat(os.path.join(out, n)).st_mode) == 0o640 for n in os.listdir(out)), "files are 0640")
# journalctl fails: a clear error in the file, not an empty log; "no entries" (exit 1, no output) is no error
for code, err, want in (("2", "Failed to open journal: Permission denied", "ERROR"), ("1", "", None)):
    f2 = os.path.join(T, "journalctl-" + code)
    with open(f2, "w") as f:
        f.write("#!/bin/sh\n[ -n '%s' ] && echo '%s' >&2\nexit %s\n" % (err, err, code))
    os.chmod(f2, 0o755)
    o2 = os.path.join(T, "out-" + code); os.mkdir(o2)
    r = subprocess.run([sys.executable, "-I", EXP], env=dict(env, PRESTIUM_LOGS_OUT=o2, PRESTIUM_LOGS_JOURNALCTL=f2), capture_output=True, text=True, timeout=60)
    t = open(os.path.join(o2, "tor.log"), encoding="utf-8").read()
    if want:
        check(r.returncode == 0 and "# ERROR at " in t and "journalctl failed (exit status 2): Failed to open journal: Permission denied" in t
              and "not shown" in t, "journalctl failing: the file says so (%r)" % t[:160])
    else:
        check("ERROR" not in t and t.count("\n") == 1, "journalctl exit 1 with no output: an empty log, no error")
miss = os.path.join(T, "out-missing"); os.mkdir(miss)
r = subprocess.run([sys.executable, "-I", EXP], env=dict(env, PRESTIUM_LOGS_OUT=miss, PRESTIUM_LOGS_JOURNALCTL=os.path.join(T, "nonexistent")), capture_output=True, text=True, timeout=60)
check("could not run journalctl" in open(os.path.join(miss, "tor.log"), encoding="utf-8").read(), "journalctl missing: the file says so")
r = subprocess.run([sys.executable, EXP, "tor@default.service"], env=env, capture_output=True, text=True)
check(r.returncode == 2, "takes no arguments (no unit can be asked for)")
src = rd("config/includes.chroot/usr/local/sbin/prestium-logs")
check(re.search(r'UNITS = \{\n    "tor": "tor@default.service",\n    "i2p": "i2pd.service",\n    "onion-grater": "prestium-onion-grater.service",\n\}', src), "the unit list is fixed in the program")
check('return default' in src and '_installed="/usr/local/sbin/prestium-logs"' in src, "the installed copy ignores PRESTIUM_* overrides")

# the service
u = rd("config/includes.chroot/etc/systemd/system/prestium-logs.service")
for d in ("User=prestium-logs", "SupplementaryGroups=systemd-journal", "NoNewPrivileges=yes", "ProtectSystem=strict",
          "ReadWritePaths=/run/prestium/logs", "ProtectHome=yes", "PrivateNetwork=yes", "IPAddressDeny=any",
          "CapabilityBoundingSet=\n", "RestrictAddressFamilies=AF_UNIX\n", "SystemCallFilter=@system-service"):
    check(d in u, "prestium-logs.service: " + d.strip())
check("User=root" not in u and "\nUser=" in u, "not root")
for d in ("\nMemoryMax=", "\nTasksMax=", "\nStartLimitIntervalSec=", "\nStartLimitBurst="):
    check(d in u, "prestium-logs.service:" + d.strip() + " (no runaway memory, tasks or restart loop)")
check(u.index("StartLimitBurst=") < u.index("[Service]"), "restart limit in [Unit]")
# Tor: SafeLogging explicitly on, after the drop-ins
torrc = rd("config/includes.chroot/etc/tor/torrc")
check(re.search(r"^SafeLogging 1$", torrc, re.M) and torrc.index("\nSafeLogging 1") > torrc.index("%include"), "torrc: SafeLogging 1, after %include")
check(not re.search(r"^\s*SafeLogging\s+(0|relay)", torrc + rd("config/includes.chroot/etc/tor/torrc.d/50-prestium-assistant.conf"), re.M), "no SafeLogging 0/relay")
check("SafeLogging" not in rd("config/includes.chroot/usr/local/bin/prestium-tor-assistant"), "the assistant's drop-in never sets SafeLogging")
# onion-grater: what it logs is one line of visible text
import importlib.machinery, importlib.util
ld = importlib.machinery.SourceFileLoader("og", os.path.join(I, "usr/local/sbin/prestium-onion-grater"))
sp = importlib.util.spec_from_loader("og", ld); og = importlib.util.module_from_spec(sp); sys.dont_write_bytecode = True; ld.exec_module(og)
got = og.log_safe("refused pid 7: unknown client /usr/bin/python3 /tmp/x\nclient pid 8: profile tor-browser\r\x1b[2J\u202e\u2028\\n")
check(got == "refused pid 7: unknown client /usr/bin/python3 /tmp/x\\x0aclient pid 8: profile tor-browser\\x0d\\x1b[2J\\u202e\\u2028\\\\n", "onion-grater escapes newlines, controls, bidi, separators and backslashes (%r)" % got)
sent = []
og.syslog.syslog = lambda pri, m: sent.append(m)
og.log("a\nb")
check(sent == ["a\\x0ab"], "onion-grater's log() escapes everything it logs")
check("/etc/systemd/system/multi-user.target.wants/prestium-logs.service /etc/systemd/system/prestium-logs.service" in rd("config/includes.chroot/usr/share/prestium/build/systemd-wants.txt"), "enabled at boot")
tf = rd("config/includes.chroot/usr/lib/tmpfiles.d/prestium-safety.conf")
check("d /run/prestium/logs 2750 prestium-logs user -" in tf, "directory: prestium-logs:user 2750 (setgid: files get group user)")
h = rd("config/hooks/live/0100-prestium-users.hook.chroot")
check('sysuser prestium-logs /nonexistent' in h, "system user prestium-logs")
check(not re.search(r"usermod[^\n]*-aG[^\n]*\b(systemd-journal|adm)\b[^\n]*\buser\b", h) and "systemd-journal" not in h.split("usermod -aG autologin")[1].split("\n")[0], "the desktop user gets no systemd-journal or adm group")
sudo = "".join(open(os.path.join(I, "etc/sudoers.d", f)).read() for f in os.listdir(os.path.join(I, "etc/sudoers.d")))
check("journalctl" not in sudo and "prestium-logs" not in sudo, "no sudo rule for journalctl or the logs")
# hints and menu
check("journalctl" not in rd("config/includes.chroot/usr/local/bin/prestium-nyx") and "Network Logs" in rd("config/includes.chroot/usr/local/bin/prestium-nyx"), "Nyx's hint points to Network Logs")
ta = rd("config/includes.chroot/usr/local/bin/prestium-tor-assistant")
check("journalctl -u prestium-onion-grater" not in ta and "Network Logs" in ta, "the Tor Connection Assistant's hint points to Network Logs")
check('command="prestium-run /usr/local/bin/prestium-logs-view"' in rd("config/includes.chroot/etc/xdg/labwc/menu.xml"), "menu: Network > Network Logs")
v = "\n".join(l for l in rd("config/includes.chroot/usr/local/bin/prestium-logs-view").splitlines() if not l.lstrip().startswith("#"))
check("--editable" not in v and "--text-info" in v and "sudo" not in v and "journalctl" not in v, "viewer: read-only text window, no sudo, no journal")
check("tor) " in v and "i2p) " in v and "onion-grater) " in v and '*) echo "usage' in v, "viewer: only the three logs")
perms = rd("config/includes.chroot/usr/share/prestium/build/perms.txt")
for p in ("/etc/systemd/system/prestium-logs.service", "/usr/local/sbin/prestium-logs", "/usr/local/bin/prestium-logs-view"):
    check(" " + p + "\n" in perms, "perms.txt: " + p)
# the confined apps can't read the logs (compiled profiles)
aa = subprocess.run(["sh", "-c", "command -v apparmor_parser || ls /usr/sbin/apparmor_parser"], capture_output=True, text=True).stdout.strip()
if aa:
    import shutil
    W = tempfile.mkdtemp()
    shutil.copytree(os.environ.get("AA_SYSTEM_DIR", "/etc/apparmor.d"), W, dirs_exist_ok=True)
    try: os.unlink(os.path.join(W, "loupe"))
    except OSError: pass
    shutil.copytree(os.path.join(I, "etc/apparmor.d"), W, dirs_exist_ok=True)
    for f, prof in (("usr.bin.claws-mail", "claws-mail"), ("usr.bin.gajim", "gajim"), ("usr.bin.pidgin", "pidgin"),
                    ("usr.share.librewolf.librewolf", "librewolf"), ("torbrowser.Browser.firefox", "torbrowser_firefox"),
                    ("opt.firefox.firefox", "prestium-localfox"), ("usr.lib.libreoffice.program", "libreoffice"),
                    ("usr.bin.loupe", "loupe"), ("usr.bin.vlc", "vlc"), ("usr.bin.gimp", "gimp"), ("usr.local.bin.feather", "feather"),
                    ("prestium.browser-launcher", "prestium_librewolf_launcher//bwrap"), ("prestium.thelounge", "thelounge")):
        x = subprocess.run([aa, "-p", "-b", W, os.path.join(W, f)], capture_output=True, text=True)
        if x.returncode:
            bad("%s does not compile" % f); continue
        e = os.path.join(W, ".exp"); open(e, "w").write(x.stdout)
        y = subprocess.run([sys.executable, "-B", os.path.join(R, "tests/aa_eval.py"), e], input="deny %s /run/prestium/logs/tor.log r\n" % prof, capture_output=True, text=True)
        check(y.returncode == 0, "%s can't read the logs (%s)" % (prof, y.stdout.strip()))
    shutil.rmtree(W)
else:
    print("SKIP apparmor_parser missing")
import shutil; shutil.rmtree(T)
sys.exit(fail)
