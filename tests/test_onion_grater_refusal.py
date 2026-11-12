#!/usr/bin/python3
"""2.1 (ISO test after ba6ff54): what a refused client shows.
- onion-grater answers "510 Prestium onion-grater: client not allowed", logs the reason, and reads the
  client's first command before closing, so a client that writes AUTHENTICATE after the 510 is sent
  reads the 510 instead of failing with "Broken pipe" (the Tor Connection Assistant showed that).
- The assistant turns a 510 from the filter into a clear message (also when its write failed first).
- Nyx's menu entry runs prestium-nyx, which keeps the terminal open when Nyx fails.
Runs the real filter code (handle/identify) on a socket in a temporary directory; no root needed."""
import asyncio, importlib.machinery, importlib.util, os, re, socket, subprocess, sys, tempfile, threading, time
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
T = tempfile.mkdtemp()

loader = importlib.machinery.SourceFileLoader("og", os.path.join(I, "usr/local/sbin/prestium-onion-grater"))
spec = importlib.util.spec_from_loader("og", loader); og = importlib.util.module_from_spec(spec); loader.exec_module(og)
logs = []
og.log = logs.append
og.USER_UID = os.getuid(); og.LOCALWEB_GID = None
SOCK = os.path.join(T, "control")

def serve(stop):
    async def main():
        srv = await asyncio.start_unix_server(og.handle, path=SOCK)
        async with srv:
            while not stop.is_set():
                await asyncio.sleep(0.05)
    asyncio.run(main())
stop = threading.Event(); th = threading.Thread(target=serve, args=(stop,), daemon=True); th.start()
for _ in range(100):
    if os.path.exists(SOCK): break
    time.sleep(0.05)

# a client this filter does not know (python3 -c ...), writing only after the filter has answered
CL = ("import socket,sys,time\ns=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3)\n"
      "try:\n    s.sendall(b'AUTHENTICATE\\r\\n'); print(s.recv(200).decode().strip())\n"
      "except OSError as e: print('error', e)\n")
out = subprocess.run([sys.executable, "-c", CL, SOCK], capture_output=True, text=True, timeout=10).stdout.strip()
(ok if out == "510 Prestium onion-grater: client not allowed" else bad)("a refused client reads the 510, no Broken pipe (%r)" % out)
(ok if any(l.startswith("refused pid ") and "unknown client" in l for l in logs) else bad)(
    "the reason is logged for the journal (%s)" % (logs[-1] if logs else "nothing"))

# the assistant's ControlMonitor.session(), from its source, with a stand-in GLib
src = open(os.path.join(I, "usr/local/bin/prestium-tor-assistant")).read()
a = src.index("class FilterRefused("); b = src.index("class Assistant(")
class GLib:
    @staticmethod
    def idle_add(*a): pass
g = {"socket": socket, "re": re, "time": time, "threading": threading, "subprocess": subprocess, "GLib": GLib,
     "CONTROL": SOCK, "__name__": "tca"}
exec(src[a:b], g)
mon = g["ControlMonitor"](lambda *a: None, lambda *a: None)
try:
    mon.session(); r = "no error"
except g["FilterRefused"] as e: r = "FilterRefused: %s" % e
except Exception as e: r = "%s: %s" % (e.__class__.__name__, e)
(ok if r.startswith("FilterRefused") else bad)("assistant: the filter's refusal is recognised (%s)" % r)

# a filter that closes at once (as before 2.1): the write may fail, the 510 must still be shown
# 2.1 (review V-8): this case races the stub's close against the client's write, and about one run in
# sixty the kernel reports only the Broken pipe. Three tries; a real regression fails all three.
OLD = os.path.join(T, "old")
ls = socket.socket(socket.AF_UNIX); ls.bind(OLD); ls.listen(3)
def old_filter():
    for _ in range(3):
        c, _ = ls.accept(); c.sendall(b"510 Prestium onion-grater: client not allowed\r\n"); c.close()
threading.Thread(target=old_filter, daemon=True).start()
g["CONTROL"] = OLD
for _try in range(3):
    try:
        mon.session(); r = "no error"
    except g["FilterRefused"] as e: r = "FilterRefused: %s" % e
    except Exception as e: r = "%s: %s" % (e.__class__.__name__, e)
    if r.startswith("FilterRefused"):
        break
(ok if r.startswith("FilterRefused") else bad)("assistant: 510 recognised when the filter closes at once (%s)" % r)
(ok if "Network Logs" in g["REFUSED_TEXT"] and "journalctl" not in g["REFUSED_TEXT"] else bad)("assistant: the message points to Network Logs (readable by the user)")
(ok if "except FilterRefused:" in src and "REFUSED_TEXT" in src[src.index("def run(self)"):] else bad)(
    "assistant: run() shows the refusal text")
stop.set()

# Nyx: the menu runs the launcher; the launcher waits for Enter only when Nyx fails
menu = open(os.path.join(I, "etc/xdg/labwc/menu.xml")).read()
(ok if re.search(r'command="prestium-run foot [^"]*prestium-nyx -s /run/onion-grater/control"', menu) else bad)(
    "menu: Tor Monitor (Nyx) runs prestium-nyx in foot")
L = os.path.join(I, "usr/local/bin/prestium-nyx")
(ok if os.access(L, os.X_OK) else bad)("prestium-nyx is executable")
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
(ok if "\n0755 root root /usr/local/bin/prestium-nyx\n" in perms else bad)("perms.txt lists prestium-nyx 0755")
ltxt = open(L).read()
(ok if re.search(r"^/usr/bin/nyx \"\$@\"$", ltxt, re.M) and "exec " not in ltxt.split("\n/usr/bin/nyx", 1)[0].split("\n", 1)[1] else bad)(
    "prestium-nyx runs /usr/bin/nyx unchanged as a child (onion-grater still sees python3 /usr/bin/nyx)")
for rc, want_prompt in ((1, True), (0, False)):
    stub = os.path.join(T, "nyx-%d" % rc); open(stub, "w").write("#!/bin/sh\necho \"nyx $*\"\nexit %d\n" % rc); os.chmod(stub, 0o755)
    lw = os.path.join(T, "launcher-%d" % rc); open(lw, "w").write(ltxt.replace("/usr/bin/nyx", stub)); os.chmod(lw, 0o755)
    p = subprocess.run([lw, "-s", "/run/onion-grater/control"], input="\n", capture_output=True, text=True, timeout=10)
    got = "Press Enter" in p.stdout
    (ok if p.returncode == rc and got == want_prompt and "nyx -s /run/onion-grater/control" in p.stdout else bad)(
        "prestium-nyx, Nyx exit %d: status %d, %s" % (rc, p.returncode, "waits for Enter" if got else "closes"))
sys.exit(fail)
