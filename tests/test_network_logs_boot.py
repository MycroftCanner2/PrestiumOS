#!/usr/bin/env python3
"""2.1: the "Network Logs" boot entry is the only boot with network logging.

Default boot: no Network Logs menu entry (prestium-wl-config drops it from the labwc copy it
writes), Tor logs nowhere (prestium-network-logs writes "Log err file /dev/null" before Tor
starts), i2pd logs nothing (prestium-i2pd-start execs it with --loglevel=none), and
prestium-logs.service does not run (ConditionKernelCommandLine).
Network Logs boot (prestium.network-logs on the kernel command line, GRUB and isolinux): Tor
logs notice to syslog, i2pd logs info to syslog, prestium-logs runs, and the menu keeps the
Network Logs entry. The token is allowed by cmdline.policy (its guard tests are in
test_boot_cmdline_guard.sh)."""
import os, re, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; fail = 1; print("FAIL " + m)
def check(c, m): (ok if c else bad)(m)
rd = lambda p: open(os.path.join(R, p), encoding="utf-8").read()
TOKEN = "prestium.network-logs"

## boot entries and policy
grub = rd("config/bootloaders/grub-pc/grub.cfg")
m = re.search(r'menuentry "Prestium @PRESTIUM_VERSION@ \(Network Logs\)" \{\n\tlinux @KERNEL_LIVE@ @APPEND_LIVE@ prestium\.network-logs\n\tinitrd @INITRD_LIVE@\n\}', grub)
check(m is not None, "GRUB: a 'Prestium (Network Logs)' entry with prestium.network-logs")
entries = re.findall(r'menuentry "[^"]*" \{\n\tlinux [^\n]*', grub)
check(sum(TOKEN in e for e in entries) == 1, "GRUB: exactly one entry carries the token (not the default): %d" % sum(TOKEN in e for e in entries))
sysl = rd("config/bootloaders/syslinux_common/live.cfg.in")
check(re.search(r"label live-@FLAVOUR@-network-logs\n\tmenu label Prestium @PRESTIUM_VERSION@ \(Network Logs\)\n\tlinux @LINUX@\n\tinitrd @INITRD@\n\tappend @APPEND_LIVE@ prestium\.network-logs$", sysl, re.M) is not None,
      "isolinux: a 'Prestium (Network Logs)' label with prestium.network-logs")
labels = re.findall(r"^label \S+\n(?:\t[^\n]*\n)*?\tappend [^\n]*", sysl, re.M)
check(sum(TOKEN in l for l in labels) == 1, "isolinux: exactly one label carries the token (not the default)")
check(re.search(r"^label live-@FLAVOUR@\n\tmenu label \^Prestium @PRESTIUM_VERSION@\n\tmenu default", sysl, re.M) is not None,
      "isolinux: the default label is unchanged (menu default, no token)")
pol = rd("config/includes.chroot/usr/share/prestium/boot/cmdline.policy")
check(re.search(r"^allow prestium\.network-logs$", pol, re.M) is not None, "cmdline.policy allows prestium.network-logs (at most once)")

## i2pd launcher: level per boot, same i2pd command line as before otherwise
START = os.path.join(I, "usr/local/sbin/prestium-i2pd-start")
check(subprocess.run([sys.executable, "-m", "py_compile", START], env=dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.gettempdir() + "/prestium-pyc")).returncode == 0, "prestium-i2pd-start compiles")
check(os.stat(START).st_mode & 0o111, "prestium-i2pd-start executable")
sys.dont_write_bytecode = True
import importlib.machinery, importlib.util
ld = importlib.machinery.SourceFileLoader("i2pdstart", START); sp = importlib.util.spec_from_loader("i2pdstart", ld)
mod = importlib.util.module_from_spec(sp); ld.exec_module(mod)
check(mod.loglevel("boot=live quiet prestium.network-logs") == "info", "i2pd: Network Logs boot -> info")
check(mod.loglevel("boot=live quiet") == "none", "i2pd: default boot -> none (logging disabled)")
check(mod.loglevel("boot=live xprestium.network-logs prestium.network-logsx") == "none", "i2pd: only the exact token counts")
check(mod.main(["prestium-i2pd-start", "x"]) == 2, "i2pd launcher takes no arguments")
T = tempfile.mkdtemp()
cmd = os.path.join(T, "cmdline")
for text, want in (("boot=live prestium.network-logs", "--loglevel=info"), ("boot=live", "--loglevel=none")):
    open(cmd, "w").write(text)
    r = subprocess.run([sys.executable, "-I", START], env=dict(os.environ, PRESTIUM_CMDLINE=cmd, PRESTIUM_I2PD_BIN="/bin/echo"),
                       capture_output=True, text=True)
    args = r.stdout.strip()
    check(r.returncode == 0 and want in args and "--log=syslog" in args and "--logfile" not in args
          and "--conf=/var/lib/i2pd/i2pd.conf" in args and "--daemon" in args and "--service" in args,
          "i2pd launcher execs i2pd (%s): %s" % (want, args))

## Tor: prestium-network-logs writes the one Log line for this boot, before Tor starts
NET = os.path.join(I, "usr/local/sbin/prestium-network-logs")
check(subprocess.run([sys.executable, "-m", "py_compile", NET], env=dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.gettempdir() + "/prestium-pyc")).returncode == 0, "prestium-network-logs compiles")
check(os.stat(NET).st_mode & 0o111, "prestium-network-logs executable")
ld = importlib.machinery.SourceFileLoader("netlogs", NET); sp = importlib.util.spec_from_loader("netlogs", ld)
nl = importlib.util.module_from_spec(sp); ld.exec_module(nl)
check(nl.torrc_text(True).count("\nLog notice syslog\n") == 1, "Tor: Network Logs boot -> Log notice syslog")
check("\nLog err file /dev/null\n" in "\n" + nl.torrc_text(False), "Tor: default boot -> Log err file /dev/null (Tor has no none; the log is discarded)")
check(nl.enabled("a prestium.network-logs b") and not nl.enabled("a prestium.network-logs2"), "Tor: only the exact token counts")
for text, want in (("boot=live prestium.network-logs", "Log notice syslog"), ("boot=live", "Log err file /dev/null")):
    d = os.path.join(T, "torrc.d-" + ("on" if "network-logs" in text else "off")); os.mkdir(d)
    open(cmd, "w").write(text)
    r = subprocess.run([sys.executable, "-I", NET], env=dict(os.environ, PRESTIUM_CMDLINE=cmd, PRESTIUM_TORRC_D=d),
                       capture_output=True, text=True)
    f = os.path.join(d, "40-prestium-logging.conf")
    check(r.returncode == 0 and os.path.isfile(f) and want in open(f).read() and not [x for x in os.listdir(d) if x.startswith(".")],
          "prestium-network-logs writes %s atomically" % want)
r = subprocess.run([sys.executable, "-I", NET, "x"], env=dict(os.environ, PRESTIUM_CMDLINE=cmd, PRESTIUM_TORRC_D=T), capture_output=True, text=True)
check(r.returncode == 2, "prestium-network-logs takes no arguments")
unit = rd("config/includes.chroot/etc/systemd/system/prestium-network-logs.service")
for d in ("ExecStart=/usr/local/sbin/prestium-network-logs", "Before=tor.service tor@default.service",
          "ProtectSystem=strict", "ReadWritePaths=/etc/tor/torrc.d", "PrivateNetwork=yes", "CapabilityBoundingSet=\n"):
    check(d in unit, "prestium-network-logs.service: " + d.strip())
check("multi-user.target.wants/prestium-network-logs.service /etc/systemd/system/prestium-network-logs.service" in rd("config/includes.chroot/usr/share/prestium/build/systemd-wants.txt"), "prestium-network-logs enabled at boot")
torrc = rd("config/includes.chroot/etc/tor/torrc")
check(not re.search(r"^\s*Log\s", torrc, re.M), "torrc itself sets no Log (the per-boot drop-in does; SafeLogging stays after the include)")

## exporter only in the Network Logs boot
logs = rd("config/includes.chroot/etc/systemd/system/prestium-logs.service")
check(re.search(r"^ConditionKernelCommandLine=prestium\.network-logs$", logs, re.M) is not None,
      "prestium-logs.service: ConditionKernelCommandLine=prestium.network-logs")

## menu: source keeps the entry; prestium-wl-config drops it unless the token is present
menu = rd("config/includes.chroot/etc/xdg/labwc/menu.xml")
ET.fromstring(menu); ok("menu.xml parses")
wl = rd("config/includes.chroot/usr/local/sbin/prestium-wl-config")
check('_test_env("PRESTIUM_CMDLINE", "/proc/cmdline")' in wl and '"prestium.network-logs" not in cmdline.split()' in wl,
      "prestium-wl-config: the menu copy depends on the boot token")
pat = re.search(r"re\.subn\(r'([^']+)', \"\"", wl)
check(pat is not None, "prestium-wl-config: drops the entry with one subn")
if pat:
    stripped, n = re.subn(pat.group(1), "", menu, count=1, flags=re.S)
    check(n == 1 and "Network Logs" not in stripped and "prestium-logs-view" not in stripped, "default boot: the written menu has no Network Logs entry")
    ET.fromstring(stripped); ok("default boot: the written menu still parses")
    check("Tor Monitor (Nyx)" in stripped and "Tor Connection Assistant" in stripped, "default boot: the rest of the Network menu stays")
perms = rd("config/includes.chroot/usr/share/prestium/build/perms.txt")
for p in ("/etc/systemd/system/prestium-network-logs.service", "/usr/local/sbin/prestium-network-logs", "/usr/local/sbin/prestium-i2pd-start"):
    check(" " + p + "\n" in perms, "perms.txt: " + p)
import shutil; shutil.rmtree(T)
sys.exit(fail)
