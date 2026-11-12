#!/usr/bin/python3
"""2.1: the I2P Connection Assistant's root helper (prestium-i2p-mode). Runs it from the repo on
copies of i2pd's files, with a fake safefile and systemctl: request checks, the edits (hops, share,
bandwidth, outproxy; SOCKS outproxy tunnels keep 1 hop and port 4500), rollback when the browser
proxy doesn't come back, and the menu, sudoers and desktop wiring."""
import json, os, re, shutil, socket, subprocess, sys, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
HELPER = os.path.join(I, "usr/local/sbin/prestium-i2p-mode")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
def check(c, m): (ok if c else bad)(m)

T = tempfile.mkdtemp()
D = os.path.join(T, "i2pd"); os.makedirs(D)
for f in ("tunnels.conf", "i2pd.conf"):
    shutil.copy(os.path.join(I, "var/lib/i2pd", f), D)
SAFE = os.path.join(T, "safefile")
open(SAFE, "w").write('#!/bin/sh\ncase "$1" in read) cat "$2/$3";; write) cat > "$2/$3";; *) exit 1;; esac\n')
SYSTEMCTL = os.path.join(T, "systemctl")
open(SYSTEMCTL, "w").write('#!/bin/sh\necho "$@" >> "%s/calls"\nexit 0\n' % T)
os.chmod(SAFE, 0o755); os.chmod(SYSTEMCTL, 0o755)
open(os.path.join(T, "port"), "w").write("21437\n")

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def run(cmd, req=None, listen=True, uid=None):
    uid = os.getuid() if uid is None else uid
    port = free_port(); srv = None
    if listen:
        srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port)); srv.listen(8)
    env = dict(os.environ, PRESTIUM_I2P_DIR=D, PRESTIUM_SAFEFILE=SAFE, PRESTIUM_SYSTEMCTL=SYSTEMCTL,
               PRESTIUM_I2PD_PORTFILE=os.path.join(T, "port"), PRESTIUM_I2P_LOCK=os.path.join(T, "lock"),
               PRESTIUM_I2P_PROXY_PORT=str(port), PRESTIUM_I2P_WAIT="3", PRESTIUM_I2PD_UID=str(uid))
    r = subprocess.run([sys.executable, "-I", HELPER, cmd], input=req if isinstance(req, str) else json.dumps(req or {}),
                       capture_output=True, text=True, env=env, timeout=60)
    if srv: srv.close()
    try: out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError): out = {"raw": r.stdout + r.stderr}
    return r.returncode, out

def sect(path, name):
    s = open(path).read()
    m = re.search(r"^\[%s\]\n(.*?)(?=^\[|\Z)" % re.escape(name), s, re.M | re.S)
    return m.group(1) if m else ""

orig = {f: open(os.path.join(D, f)).read() for f in ("tunnels.conf", "i2pd.conf")}
orig_len = {s: re.findall(r"^\w+\.length = \d+$", sect(os.path.join(D, "tunnels.conf"), s), re.M)
            for s in ("socks-outproxy-tcp", "socks-outproxy-udp")}
rc, st = run("status")
check(rc == 0 and st.get("ok") and st["hops"] == 3 and st["share"] == "low" and st["outproxy"] == "acetone"
      and st["port"] == 21437, "status of the shipped files: 3 hops, low, Acetone, port (%s)" % st)

for req, why in ((dict(hops=0, share="low", outproxy="acetone"), "0 hops"),
                 (dict(hops=8, share="low", outproxy="acetone"), "8 hops"),
                 (dict(hops="3", share="low", outproxy="acetone"), "hops as text"),
                 (dict(hops=3, share="max", outproxy="acetone"), "unknown share"),
                 (dict(hops=3, share="low", outproxy="tor"), "unknown outproxy"),
                 (dict(hops=3, share="low", outproxy="acetone", extra=1), "extra field"),
                 (dict(hops=3, share="low", outproxy="custom", custom="http://example.com:3128"), "clearnet custom"),
                 (dict(hops=3, share="low", outproxy="custom", custom="http://10.0.0.1:3128"), "IP custom"),
                 (dict(hops=3, share="low", outproxy="custom", custom="http://a.i2p:3128\nshare = 100"), "newline injection"),
                 (dict(hops=3, share="low", outproxy="custom", custom="http://a.i2p:3128 = x"), "= injection"),
                 (dict(hops=3, share="low", outproxy="custom", custom="http://a.i2p:70000"), "port > 65535"),
                 (dict(hops=3, share="low", outproxy="custom", custom="socks://a.i2p:1080"), "non-HTTP custom")):
    rc, out = run("apply", req)
    check(rc != 0 and not out.get("ok"), "refused: %s (%s)" % (why, out.get("error")))
rc, out = run("apply", "not json"); check(rc != 0, "refused: not JSON")
check(all(open(os.path.join(D, f)).read() == orig[f] for f in orig), "refused requests changed nothing")
check(not os.path.exists(os.path.join(T, "calls")) or "restart" not in open(os.path.join(T, "calls")).read(),
      "refused requests didn't restart i2pd")

rc, st = run("apply", dict(hops=5, share="high", outproxy="stormycloud"))
tun, main = os.path.join(D, "tunnels.conf"), os.path.join(D, "i2pd.conf")
check(rc == 0 and st.get("ok") and st["hops"] == 5 and st["share"] == "high" and st["outproxy"] == "stormycloud",
      "apply 5 hops, high, StormyCloud (%s)" % st)
w = sect(tun, "Web Browser HTTP Proxy")
check("outproxy = http://5d4s7pcvfdpftfk7npc7hllyujhufsdprtrf4o53i44rgsa2xbwa.b32.i2p\n" in w
      and "inbound.length = 5" in w and "outbound.length = 5" in w, "browser proxy: StormyCloud, 5 hops")
for s in ("socks-outproxy-tcp", "socks-outproxy-udp"):
    b = sect(tun, s)
    check("port = 4500" in b and "destination = 5d4s7pcvfdpftfk7npc7hllyujhufsdprtrf4o53i44rgsa2xbwa.b32.i2p" in b
          and ".length = 5" not in b and orig_len[s] == re.findall(r"^\w+\.length = \d+$", b, re.M),
          "%s: StormyCloud, still port 4500, hop setting unchanged" % s)
check("outbound.length = 5" in sect(tun, "IRC2P"), "other tunnels get 5 hops")
m = open(main).read()
check(re.search(r"^share = 80$", m, re.M) and re.search(r"^bandwidth = 128$", m, re.M)
      and len(re.findall(r"^share\s*=", m, re.M)) == 1 and len(re.findall(r"^bandwidth\s*=", m, re.M)) == 1,
      "i2pd.conf: share 80, bandwidth 128, once each")
check("inbound.length = 5" in sect(main, "exploratory") and "inbound.length = 5" in sect(main, "socksproxy"),
      "i2pd.conf: exploratory and SOCKS proxy 5 hops")
check("restart i2pd" in open(os.path.join(T, "calls")).read(), "i2pd restarted")

rc, st = run("apply", dict(hops=3, share="medium", outproxy="custom", custom="http://outproxy.example.i2p:3128"))
check(rc == 0 and st["outproxy"] == "custom" and st["custom"] == "http://outproxy.example.i2p:3128" and st["share"] == "medium",
      "apply custom outproxy, medium (%s)" % st)
check("destination = proxy4uwdijqxac2bvdx4fuhem6njmiwukuk2gelejv2nzxka2xq.b32.i2p" in sect(tun, "socks-outproxy-tcp"),
      "custom outproxy: SOCKS outproxy back on Acetone")
check(re.search(r"^bandwidth = 64$", open(main).read(), re.M), "medium: bandwidth 64")

before = {f: open(os.path.join(D, f)).read() for f in ("tunnels.conf", "i2pd.conf")}
rc, out = run("apply", dict(hops=2, share="low", outproxy="acetone"), listen=False)
check(rc != 0 and "restored" in (out.get("error") or ""), "proxy not back: refused and restored (%s)" % out.get("error"))
check(all(open(os.path.join(D, f)).read() == before[f] for f in before), "rollback restored both files exactly")

before = {f: open(os.path.join(D, f)).read() for f in ("tunnels.conf", "i2pd.conf")}
rc, out = run("apply", dict(hops=4, share="low", outproxy="acetone"), uid=os.getuid() + 1)
check(rc != 0 and all(open(os.path.join(D, f)).read() == before[f] for f in before),
      "a listener of another uid on 4444 doesn't count: rolled back (review N-3)")
rc, st = run("apply", dict(hops=3, share="low", outproxy="acetone"))
check(rc == 0 and st["share"] == "low" and st["outproxy"] == "acetone" and re.search(r"^bandwidth = L$", open(main).read(), re.M),
      "back to defaults: low (L), Acetone")

h = open(HELPER).read()
check('INSTALLED = os.path.abspath(sys.argv[0]).startswith("/usr/local/")' in h, "test overrides ignored when installed")
check("create_connection" not in h and "/proc/net/tcp" in h,
      "readiness from /proc/net/tcp, never a connection (the firewall refuses root on 4444)")
sud = open(os.path.join(I, "etc/sudoers.d/prestium-i2p-mode")).read()
check("NOPASSWD: /usr/local/sbin/prestium-i2p-mode status\n" in sud and "mode apply" not in sud,
      "sudoers: status only; apply goes through the broker's confirmation (review N-2)")
check("tunnel-hops" not in open(os.path.join(I, "etc/sudoers.d/prestium-power")).read().split("\n", 1)[1],
      "sudoers: old tunnel-hops grant removed")
if shutil.which("visudo"):
    r = subprocess.run(["visudo", "-cf", os.path.join(I, "etc/sudoers.d/prestium-i2p-mode")], capture_output=True)
    check(r.returncode == 0, "visudo accepts it")
else:
    print("SKIP visudo missing")
app = open(os.path.join(I, "usr/local/bin/prestium-i2p-assistant")).read()
check('APP_ID = "org.prestium.I2PConnectionAssistant"' in app and
      os.path.exists(os.path.join(I, "usr/share/applications/org.prestium.I2PConnectionAssistant.desktop")),
      "desktop file named after the app ID (panel icon)")
menu = open(os.path.join(I, "etc/xdg/labwc/menu.xml")).read()
check("prestium-i2p-assistant" in menu and "prestium-tunnel-hops" not in menu and "restart i2pd" not in menu
      and "prestium-i2p-reseed-gui" not in menu, "menu: one I2P Connection Assistant entry")
check("deny /usr/local/bin/prestium-i2p-assistant mrwx," in open(os.path.join(I, "etc/apparmor.d/abstractions/prestium-no-admin")).read(),
      "confined apps can't start the assistant")
perms = open(os.path.join(I, "usr/share/prestium/build/perms.txt")).read()
check(all(x in perms for x in ("0755 root root /usr/local/sbin/prestium-i2p-mode", "0440 root root /etc/sudoers.d/prestium-i2p-mode",
                               "0755 root root /usr/local/bin/prestium-i2p-assistant")), "perms.txt entries")
shutil.rmtree(T)
sys.exit(fail)
