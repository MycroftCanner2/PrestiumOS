#!/usr/bin/python3
"""2.1 (audit I-1): the root daemons' PRESTIUM_* overrides are for the test suite only. Run from the
source tree they work; the installed copy (its real path) ignores them, so it never depends on sudo's
env_reset or a unit's environment."""
import os, re, sys, types
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(R, "config/includes.chroot/usr/local/sbin")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
for name in ("prestium-wl-broker", "prestium-wl-config", "prestium-mac-guard"):
    src = open(os.path.join(S, name)).read()
    if re.search(r'os\.environ(\.get\(|\[)\s*"PRESTIUM_', src):
        bad("%s: reads a PRESTIUM_* variable directly" % name)
    else:
        ok("%s: every PRESTIUM_* override goes through _test_env" % name)
    m = re.search(r"\ndef _test_env\(.*?\n(?=\S)", src, re.S)
    if not m:
        bad("%s: no _test_env" % name); continue
    if '_installed="/usr/local/sbin/%s"' % name not in m.group(0):
        bad("%s: _test_env names the wrong installed path" % name); continue
    os.environ["PRESTIUM_PROBE"] = "/tmp/evil"
    for path, want in (("/usr/local/sbin/" + name, "/safe"), (os.path.join(S, name), "/tmp/evil")):
        g = {"os": types.SimpleNamespace(environ=os.environ, path=types.SimpleNamespace(realpath=lambda p: p)),
             "__file__": path}
        exec(m.group(0), g)
        got = g["_test_env"]("PRESTIUM_PROBE", "/safe")
        (ok if got == want else bad)("%s run as %s: %s" % (name, "installed" if want == "/safe" else "source tree", got))
sys.exit(fail)
