#!/bin/bash
# 2.0 r9/r10/r11: runs the real browser launchers (tor-browser, librewolf-i2p) with bwrap, and the
# real Wayland broker (root, via sudo) against a headless labwc, with a probe (tests/sandbox_probe.py) in
# place of the browser, and checks what a browser would see inside its sandbox.
# Needs bwrap, labwc, wayland-utils, socat, python3, tor and sudo (creates /opt/tor-browser,
# /run/prestium-tbb, /usr/local/share/prestium-{tor-browser,nssdb} when absent and removes them).
set -u
H=$(cd "$(dirname "$0")/.." && pwd)
I=$H/config/includes.chroot
PROBE=$H/tests/sandbox_probe.py
fail=0; ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; fail=1; }
created=()
mk() {   # create $1 and remember the topmost directory that did not exist, to remove it afterwards
  [ -e "$1" ] && return 0
  local top=$1; while [ ! -e "$(dirname "$top")" ]; do top=$(dirname "$top"); done
  sudo -n mkdir -p "$1"; created+=("$top")
}
mk /opt/tor-browser/Browser/TorBrowser/Data/Browser/profile.default/extensions
mk /run/prestium-tbb; mk /usr/local/share/prestium-tor-browser; mk /usr/local/share/prestium-nssdb
sudo -n chown "$(id -u)" /run/prestium-tbb /opt/tor-browser/Browser
sudo -n sh -c 'echo "user_pref(\"browser.download.dir\", \"@DOWNLOADS@\");" > /usr/local/share/prestium-tor-browser/user.js; : > /usr/local/share/prestium-nssdb/cert9.db; : > /usr/local/share/prestium-nssdb/key4.db'
T=$(mktemp -d); chmod 755 "$T"; export HOME=$T/home; mkdir -p "$HOME"; echo secret > "$HOME/keepass.kdbx"; mkdir -p "$HOME/.ssh"
export XDG_RUNTIME_DIR=$T/xdg$(id -u); mkdir -m 700 "$XDG_RUNTIME_DIR"
export PRESTIUM_WL_BASE=$T/wlbase
# 2.1: the shipped launchers take nothing from the environment, so the test runs patched copies
L=$T/launch; mkdir -p "$L"
sed "s#^SBX_WL_BASE=.*#SBX_WL_BASE=$PRESTIUM_WL_BASE#; s#^SBX_BWRAP=.*#SBX_BWRAP=$(command -v bwrap)#" \
  "$I/usr/local/lib/prestium/browser-sandbox.sh" > "$L/browser-sandbox.sh"
# 2.1 (review): the launchers take HOME and XDG_RUNTIME_DIR from the system; use the test's here
UNHOME="s#^HOME=\$(getent passwd.*#:#; s#^case \$HOME in /home.*#:#; s#^XDG_RUNTIME_DIR=/run/user.*#:#"
sed "s#^SBX_LIB=.*#SBX_LIB=$L/browser-sandbox.sh#; $UNHOME" "$I/usr/local/bin/tor-browser" > "$L/tor-browser"
sed "s#^SBX_LIB=.*#SBX_LIB=$L/browser-sandbox.sh#; $UNHOME; s#^I2P_HTTP_PORT=.*#I2P_HTTP_PORT=14444#; s#^LIBREWOLF=.*#LIBREWOLF=\"\$HOME/.librewolf/probe\"#" \
  "$I/usr/local/bin/librewolf-i2p" > "$L/librewolf-i2p"
pids=()
cleanup() {
  kill "${pids[@]}" 2>/dev/null; [ -s "$T/broker.pid" ] && sudo -n kill "$(cat "$T/broker.pid")" 2>/dev/null; wait 2>/dev/null
  rm -f /opt/tor-browser/Browser/start-tor-browser
  for ((i=${#created[@]}-1; i>=0; i--)); do sudo -n rm -rf "${created[$i]}"; done
  sudo -n rm -rf "$T"
}
trap cleanup EXIT

# headless compositor
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 labwc -c /dev/null >/dev/null 2>&1 & pids+=($!)
for i in $(seq 50); do [ -S "$XDG_RUNTIME_DIR/wayland-0" ] && break; sleep 0.1; done
export WAYLAND_DISPLAY=wayland-0
# the Wayland broker (root) locks the full socket and makes the restricted one the browsers get
sudo -n env PRESTIUM_WL_BASE="$PRESTIUM_WL_BASE" PRESTIUM_WL_RUNTIME="$T/xdg%d" sh -c 'echo $$ > "$1"; exec python3 -I "$2"' _ \
  "$T/broker.pid" "$I/usr/local/sbin/prestium-wl-broker" >/dev/null 2>&1 < /dev/null &
for i in $(seq 50); do [ -S "$PRESTIUM_WL_BASE/broker" ] && break; sleep 0.1; done
r=$(python3 "$I/usr/local/bin/prestium-wl" start); [ "${r%% *}" = ok ] && ok "broker: $r" || bad "broker start: $r"
# a real Tor SOCKS listener on the Unix socket (no network needed for the greeting)
printf 'DataDirectory %s/tor\nSocksPort unix:/run/prestium-tbb/socks WorldWritable\nUseBridges 1\nBridge 127.0.0.1:9\nControlPort 0\nLog err stderr\n' "$T" > "$T/torrc"
mkdir -m 700 "$T/tor"; chmod 2750 /run/prestium-tbb
tor -f "$T/torrc" >/dev/null 2>&1 & pids+=($!)
for i in $(seq 40); do [ -S /run/prestium-tbb/socks ] && break; sleep 0.25; done
# host listeners that must NOT be reachable from inside: 127.0.0.1:9050 and Xwayland's abstract socket
python3 -c 'import socket,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1",9050)); s.listen(5); time.sleep(120)' & pids+=($!)
# (labwc's Xwayland may already listen there; then that is the socket we test against)
python3 -c 'import socket,time; s=socket.socket(socket.AF_UNIX); s.bind("\0/tmp/.X11-unix/X0"); s.listen(5); time.sleep(120)' 2>/dev/null & pids+=($!)
# a fake "i2pd HTTP proxy" on the host's 127.0.0.1:14444 (LibreWolf's only way out)
python3 -c '
import socket,time,threading
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1",14444)); s.listen(5)
while True:
    c,_=s.accept(); c.recv(500); c.sendall(b"HTTP/1.0 200 OK\r\n\r\nPRESTIUM-FAKE-I2P-PROXY"); c.close()' & pids+=($!)
sleep 1
python3 -c 'import socket; socket.socket(socket.AF_UNIX).connect("\0/tmp/.X11-unix/X0")' \
  && ok "host: an X11 abstract socket is listening outside (so the check inside means something)" \
  || bad "host: no X11 abstract socket to test against"

check() {   # $1 name, $2 json, $3 python expression on r
  python3 -c "import json,sys; r=json.loads(sys.argv[1]); sys.exit(0 if ($3) else 1)" "$2" && ok "$1" \
    || { bad "$1"; echo "     $2" | cut -c1-600; }
}
PRIV='["zwlr_screencopy_manager_v1","zwlr_export_dmabuf_manager_v1","zwp_virtual_keyboard_manager_v1","zwlr_virtual_pointer_manager_v1","zwlr_data_control_manager_v1","zwlr_foreign_toplevel_manager_v1","ext_foreign_toplevel_list_v1","zwp_input_method_manager_v2","wp_security_context_manager_v1","zwlr_layer_shell_v1","ext_session_lock_manager_v1","zwlr_output_manager_v1","zwlr_gamma_control_manager_v1"]'
common() {   # $1 browser, $2 json
  local b=$1 j=$2
  check "$b: only loopback in its network namespace" "$j" 'r["netdev"] == ["lo"]'
  check "$b: host 127.0.0.1:9050 not reachable" "$j" 'r["tcp_9050"] != "connected"'
  check "$b: no route to the Internet (TCP)" "$j" 'r["tcp_ext"].split(":")[0] != "connected"'
  check "$b: no UDP (DNS) out" "$j" 'r["udp"] != "sent"'
  check "$b: no X11 (no socket dir, Xwayland abstract socket unreachable)" "$j" 'not r["x11_dir"] and r["x11_abstract"] != "connected" and "DISPLAY" not in r["env"]'
  check "$b: Wayland works (compositor, windows)" "$j" 'isinstance(r["wl"], list) and "wl_compositor" in r["wl"] and "xdg_wm_base" in r["wl"]'
  check "$b: privileged Wayland protocols hidden (capture, input injection, clipboard, other windows)" "$j" "isinstance(r['wl'], list) and not set($PRIV) & set(r['wl'])"
  check "$b: only the restricted Wayland socket in XDG_RUNTIME_DIR" "$j" 'set(r["rundir"]) <= {"wayland-0", "pulse", "pipewire-0"} and "wayland-0" in r["rundir"]'
  check "$b: no_new_privs set, sudo useless" "$j" 'r["nnp"] == "1" and r["sudo"] != 0'
  check "$b: hostname localhost, own PID namespace" "$j" 'r["hostname"] == "localhost" and r["pid1"] in ("bwrap", "python3", "sh", "bash")'
  check "$b: no D-Bus, no ssh agent" "$j" '"DBUS_SESSION_BUS_ADDRESS" not in r["env"] and "SSH_AUTH_SOCK" not in r["env"]'
}

echo "== Tor Browser"
cat > /opt/tor-browser/Browser/start-tor-browser <<EOF
#!/bin/sh
exec python3 - "\$@" <<'PY'
$(cat "$PROBE")
PY
EOF
chmod +x /opt/tor-browser/Browser/start-tor-browser
out=$(bash -p "$L/tor-browser" "https://example.org/" 2>&1)
j=$(printf '%s\n' "$out" | sed -n 's/^PROBE//p')
if [ -z "$j" ]; then bad "Tor Browser probe did not run: $out"; else
  common "Tor Browser" "$j"
  check "Tor Browser: Tor SOCKS Unix socket works (05 00)" "$j" 'r["socks"] == "0500"'
  check "Tor Browser: HOME holds only .tor-browser and Tor Browser" "$j" 'r["home"] == [".tor-browser", "Tor Browser"]'
  check "Tor Browser: no proxy port inside" "$j" 'r["tcp_4444"].split(":")[0] != "connected"'
  check "Tor Browser: arguments passed through" "$j" 'r["args"][:1] == ["https://example.org/"] and "-profile" in r["args"]'
fi

echo "== LibreWolf (I2P Browser)"
mkdir -p "$HOME/.librewolf"
cp "$PROBE" "$HOME/.librewolf/probe"; chmod +x "$HOME/.librewolf/probe"
out=$(bash -p "$L/librewolf-i2p" "http://example.i2p/" 2>&1)
j=$(printf '%s\n' "$out" | sed -n 's/^PROBE//p')
if [ -z "$j" ]; then bad "LibreWolf probe did not run: $out"; else
  common "LibreWolf" "$j"
  check "LibreWolf: its 127.0.0.1:4444 reaches the I2P HTTP proxy (through the relay)" "$j" '"PRESTIUM-FAKE-I2P-PROXY" in r["tcp_4444"]'
  check "LibreWolf: HOME holds only .librewolf and I2P Browser" "$j" 'r["home"] == [".librewolf", "I2P Browser"]'
  check "LibreWolf: no Tor SOCKS socket" "$j" '"TOR_SOCKS_IPC_PATH" not in r["env"]'
  check "LibreWolf: profile and arguments passed through" "$j" 'r["args"][:3] == ["--profile", "'"$HOME"'/.librewolf/prestium", "http://example.i2p/"]'
fi
ls "$XDG_RUNTIME_DIR/prestium-sandbox" 2>/dev/null | grep -q . && bad "sandbox sockets left behind" || ok "sandbox sockets removed after exit"
sudo -n mv "$PRESTIUM_WL_BASE/$(id -u)/apps" "$T/apps.moved"
bash -p "$L/tor-browser" >/dev/null 2>&1 && bad "starts without the restricted socket" || ok "refuses to start without the restricted Wayland socket"
sudo -n mv "$T/apps.moved" "$PRESTIUM_WL_BASE/$(id -u)/apps"

echo "== refusals"
sudo -n rm -f /run/prestium-tbb/socks
bash -p "$L/tor-browser" >/dev/null 2>&1 && bad "Tor Browser starts without Tor's socket" || ok "Tor Browser refuses to start without Tor's socket"
exit $fail
