#!/usr/bin/python3
# Prestium tests: run inside a browser sandbox in place of the browser; prints one JSON line.
import json, os, socket, subprocess, sys
r = {"args": sys.argv[1:]}
r["netdev"] = [l.split(":")[0].strip() for l in open("/proc/net/dev").read().split("\n")[2:] if l.strip()]
def tcp(host, port, send=None):
    s = socket.socket(); s.settimeout(3)
    try:
        s.connect((host, port))
        if send:
            s.sendall(send); return "connected:" + s.recv(200).decode(errors="replace")
        return "connected"
    except OSError as e:
        return type(e).__name__ + ":" + str(e.errno)
r["tcp_9050"] = tcp("127.0.0.1", 9050)
r["tcp_ext"] = tcp("1.1.1.1", 443)
r["tcp_4444"] = tcp("127.0.0.1", 4444, b"GET http://example.i2p/ HTTP/1.0\r\n\r\n")
try:
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); u.sendto(b"x", ("9.9.9.9", 53)); r["udp"] = "sent"
except OSError as e:
    r["udp"] = type(e).__name__
if os.environ.get("TOR_SOCKS_IPC_PATH"):
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(os.environ["TOR_SOCKS_IPC_PATH"]); s.sendall(b"\x05\x01\x00"); r["socks"] = s.recv(2).hex()
    except OSError as e:
        r["socks"] = str(e)
a = socket.socket(socket.AF_UNIX)
try:
    a.connect("\0/tmp/.X11-unix/X0"); r["x11_abstract"] = "connected"
except OSError as e:
    r["x11_abstract"] = type(e).__name__
r["x11_dir"] = os.path.exists("/tmp/.X11-unix")
r["home"] = sorted(os.listdir(os.environ["HOME"]))
r["nnp"] = [l for l in open("/proc/self/status") if l.startswith("NoNewPrivs")][0].split()[1]
r["hostname"] = socket.gethostname()
r["env"] = {k: os.environ[k] for k in os.environ if k in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
                                                           "XDG_RUNTIME_DIR", "TOR_SOCKS_IPC_PATH", "SSH_AUTH_SOCK")}
r["pid1"] = open("/proc/1/comm").read().strip()
try:
    r["sudo"] = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True).returncode
except OSError as e:
    r["sudo"] = str(e)
r["run"] = sorted(os.listdir("/run"))
r["rundir"] = sorted(os.listdir(os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")))
try:
    out = subprocess.run(["wayland-info"], capture_output=True, text=True, timeout=10).stdout
    import re
    r["wl"] = sorted(set(re.findall(r"interface: '([A-Za-z0-9_]+)'", out)))
except Exception as e:
    r["wl"] = "error " + str(e)
print("PROBE" + json.dumps(r))
