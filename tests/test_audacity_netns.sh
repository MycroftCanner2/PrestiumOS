#!/bin/bash
# Prestium 2.1 (review of 6d14434): Audacity runs only in its own, empty network namespace, so its
# AppArmor TCP rule (the single-instance listener on 127.0.0.1) can't reach the host's loopback (Tor's
# SOCKS port, I2P's proxies) or anything else, while the microphone (PipeWire/PulseAudio sockets,
# /dev/snd), the display and the files keep working. Checks the wrapper, helper, hook 0620 (divert +
# shim), the profile's attachment, the menu and perms; runs the wrapper with stand-ins (no fallback
# without bubblewrap); and, where bubblewrap works, proves the isolation live: a process the wrapper
# starts can listen on its own 127.0.0.1 but not connect to a listener on the host's 127.0.0.1, a
# second start joins the first one's namespace through the session socket (no ptrace / nsenter
# --target), filesystem Unix sockets (PipeWire's) and Xwayland's /tmp/.X11-unix socket (with Xvfb)
# still connect, and a socket that hands over the host network is refused.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }; skip(){ echo "SKIP $1"; }
WR=$I/usr/local/bin/prestium-audacity
NSF=$I/usr/local/lib/prestium/audacity-ns
HK=$R/config/hooks/live/0620-prestium-audacity-netns.hook.chroot
PF=$I/etc/apparmor.d/usr.bin.audacity
PM=$I/usr/share/prestium/build/perms.txt
REAL=/usr/libexec/prestium-audacity
T=$(mktemp -d); PIDS=()
cleanup(){ for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; rm -rf "$T"; }
trap cleanup EXIT

echo "== the wrapper and helper"
[ -f "$WR" ] || { bad "no $WR"; exit 1; }
[ -f "$NSF" ] || { bad "no $NSF"; exit 1; }
[ "$(head -1 "$WR")" = '#!/bin/sh' ] && ok "wrapper: /bin/sh" || bad "wrapper shebang"
[ "$(head -1 "$NSF")" = '#!/usr/bin/python3' ] && ok "helper: /usr/bin/python3" || bad "helper shebang"
grep -qx '0755 root root /usr/local/bin/prestium-audacity' "$PM" && ok "perms: wrapper 0755 root root" || bad "perms: wrapper"
grep -qx '0755 root root /usr/local/lib/prestium/audacity-ns' "$PM" && ok "perms: helper 0755 root root" || bad "perms: helper"
grep -qx "REAL=$REAL" "$WR" && ok "wrapper: fixed path to the real Audacity" || bad "wrapper: real binary path"
grep -qx 'BWRAP=/usr/bin/bwrap' "$WR" && ok "wrapper: fixed bwrap path" || bad "wrapper: bwrap path"
grep -qx 'NS=/usr/local/lib/prestium/audacity-ns' "$WR" && ok "wrapper: fixed helper path" || bad "wrapper: helper path"
grep -qx 'PY=/usr/bin/python3' "$WR" && ok "wrapper: fixed python path" || bad "wrapper: python path"
code=$(grep -v '^\s*#' "$WR")
hcode=$(grep -v '^\s*#' "$NSF")
grep -qE '\beval\b|sh -c|command -v|\bwhich\b|\$PATH|\$\{PATH' <<<"$code" && bad "wrapper: eval, sh -c or a PATH lookup" || ok "wrapper: no eval, sh -c or PATH lookup"
grep -qE 'nsenter|--target|/proc/\[0-9\]\*|ptrace' <<<"$code" && bad "wrapper still joins through another process (ptrace)" || ok "wrapper: no nsenter --target or /proc/pid scan"
grep -qE 'nsenter|--target' <<<"$hcode" && bad "helper uses nsenter --target" || ok "helper: no nsenter --target"
grep -q 'SCM_RIGHTS' "$NSF" && grep -q 'only_loopback' "$NSF" && ok "helper: passes namespace fds and requires only loopback" || bad "helper: missing SCM_RIGHTS or loopback check"
grep -qE '(^|[^-])--unshare-all|--bind / /|--clearenv|--unsetenv|--tmpfs' <<<"$code" && bad "wrapper: browser-style sandbox or plain --bind (breaks files, devices or audio)" || ok "wrapper: not the browser sandbox"
# every start of the real program is either a join through the helper, or bwrap --unshare-net running the helper's serve
grep -qF 'exec "$NS" join "$SOCK" -- "$REAL" "$@"' <<<"$code" \
  && grep -qF '"$NS" check "$SOCK"' <<<"$code" \
  && grep -qF 'exec "$BWRAP" --dev-bind / / --unshare-net --die-with-parent -- "$NS" serve "$SOCK" -- "$REAL" "$@"' <<<"$code" \
  && [ "$(grep -F '"$REAL"' <<<"$code" | grep -cE '(^|\s)exec\s')" = 2 ] \
  && ok "wrapper: the real Audacity only through bwrap --unshare-net --die-with-parent or a checked socket join into its namespace" \
  || bad "wrapper starts the real program another way"
grep -qE '^\s*(exec\s+)?/usr/bin/audacity' <<<"$code" && bad "wrapper runs itself or the shim" || ok "wrapper: does not loop through the shim"
grep -qF -- '-- /usr/bin/true 2>/dev/null' <<<"$code" && grep -qF '|| fail "The network sandbox (bubblewrap) could not be started' <<<"$code" \
  && ok "wrapper: checks bubblewrap before starting Audacity" || bad "wrapper: no bubblewrap preflight"
grep -q 'No session runtime directory' <<<"$code" && ok "wrapper: fails closed without XDG_RUNTIME_DIR" || bad "wrapper: missing XDG_RUNTIME_DIR check"
grep -qE 'notify-send' <<<"$code" && ok "wrapper: tells the user when it refuses" || bad "wrapper: silent failure"
shellcheck -S warning "$WR" "$HK" >/dev/null 2>&1 && ok "shellcheck (warning): wrapper and hook" || { command -v shellcheck >/dev/null && bad "shellcheck: $(shellcheck -S warning "$WR" "$HK" | head -5)" || skip "shellcheck missing"; }
python3 -m py_compile "$NSF" 2>/dev/null && ok "helper: python compiles" || bad "helper does not compile"
rm -rf "$(dirname "$NSF")/__pycache__"

echo "== hook 0620 (divert, shim)"
[ -x "$HK" ] && ok "hook 0620 present" || bad "no executable $HK"
grep -qF 'dpkg-divert --quiet --local --rename --divert "$REAL" --add "$B"' "$HK" && grep -qx 'B=/usr/bin/audacity' "$HK" && grep -qx "REAL=$REAL" "$HK" \
  && ok "hook: diverts /usr/bin/audacity to $REAL" || bad "hook: no divert"
grep -qF 'if ! dpkg-divert --list "$B" | grep -q "$REAL"; then' "$HK" && ok "hook: diverts once (safe to run again)" || bad "hook: divert not guarded"
grep -qx 'exec /usr/local/bin/prestium-audacity "$@"' "$HK" && ok "hook: shim runs the wrapper with \"\$@\"" || bad "hook: shim"
grep -q 'chmod 0755 "$B"' "$HK" && grep -q 'chown root:root "$B"' "$HK" && ok "hook: shim root:root 0755" || bad "hook: shim mode"
grep -q 'ldd "$REAL"' "$HK" && ok "hook: checks the real program's libraries resolve from /usr/libexec" || bad "hook: no ldd check"
grep -q 'NS=/usr/local/lib/prestium/audacity-ns' "$HK" && grep -q '\[ -x "$NS" \]' "$HK" && ok "hook: requires the helper" || bad "hook: no helper check"
# run the hook against a stand-in tree (paths rewritten, a fake dpkg-divert), twice
F=$T/hook; mkdir -p "$F/bin" "$F/usr/bin" "$F/usr/libexec" "$F/usr/local/bin" "$F/usr/local/lib/prestium" "$F/apps" "$F/xdg"
cp /usr/bin/true "$F/usr/bin/audacity"; printf '#!/bin/sh\necho wrapper "$@"\n' > "$F/usr/local/bin/prestium-audacity"; chmod 0755 "$F/usr/local/bin/prestium-audacity"
printf '#!/bin/sh\nexit 0\n' > "$F/usr/local/lib/prestium/audacity-ns"; chmod 0755 "$F/usr/local/lib/prestium/audacity-ns"
printf '[Desktop Entry]\nName=Audacity\nExec=env GDK_BACKEND=x11 audacity %%F\n' > "$F/apps/audacity.desktop"
cat > "$F/bin/dpkg-divert" <<'FAKE'
#!/bin/bash
S=$(dirname "$0")/../divert.state
case $1 in
  --list) [ -f "$S" ] && grep -F "$2" "$S" | sed 's/^/local diversion of /'; exit 0;;
  --truename) d=$(grep -F "$2 to " "$S" 2>/dev/null | sed 's/.* to //'); echo "${d:-$2}";;
  --quiet) shift 2; [ "$1" = --rename ] && [ "$2" = --divert ] && [ "$4" = --add ] || exit 2
    echo "$5 to $3" >> "$S"; mv "$5" "$3";;
  *) exit 2;;
esac
FAKE
chmod 0755 "$F/bin/dpkg-divert"
sed -e "s|/usr/bin/audacity|$F/usr/bin/audacity|g; s|/usr/libexec/prestium-audacity|$F/usr/libexec/prestium-audacity|g" \
    -e "s|/usr/local/bin/prestium-audacity|$F/usr/local/bin/prestium-audacity|g; s|/usr/local/lib/prestium/audacity-ns|$F/usr/local/lib/prestium/audacity-ns|g" \
    -e "s|/usr/share/applications/audacity.desktop|$F/apps/audacity.desktop|" \
    -e "s|/usr/share/applications /etc/xdg|$F/apps $F/xdg|; s|chown root:root|: |" "$HK" > "$F/hook.sh"
h1=$(PATH=$F/bin:$PATH sh "$F/hook.sh" 2>&1); r1=$?; h2=$(PATH=$F/bin:$PATH sh "$F/hook.sh" 2>&1); r2=$?
[ $r1 = 0 ] && [ $r2 = 0 ] && ok "hook runs (twice) on a stand-in tree" || bad "hook failed: $h1 / $h2"
[ "$(grep -c . "$F/divert.state" 2>/dev/null)" = 1 ] && ok "hook: one diversion after two runs" || bad "hook: diversions: $(cat "$F/divert.state" 2>/dev/null)"
cmp -s /usr/bin/true "$F/usr/libexec/prestium-audacity" && ok "hook: the real program moved to /usr/libexec" || bad "hook: real program not moved"
[ "$("$F/usr/bin/audacity" "a b" '$(id)')" = 'wrapper a b $(id)' ] && ok "hook: /usr/bin/audacity (shim) runs the wrapper, arguments unchanged" || bad "hook: shim output: $("$F/usr/bin/audacity" "a b")"
# Debian's desktop file: Exec=env GDK_BACKEND=x11 audacity %F -> PATH -> the shim
d=$(grep '^Exec=' "$F/apps/audacity.desktop")
[ "$d" = "Exec=env GDK_BACKEND=x11 audacity %F" ] && ok "desktop Exec still starts audacity from PATH (the shim)" || bad "desktop Exec: $d"
# a desktop file that would start the real program must fail the hook
printf '[Desktop Entry]\nExec=%s\n' "$F/usr/libexec/prestium-audacity" > "$F/apps/evil.desktop"
h3=$(PATH=$F/bin:$PATH sh "$F/hook.sh" 2>&1); r3=$?
[ $r3 != 0 ] && echo "$h3" | grep -q . && ok "hook refuses a desktop file that starts the real program" || bad "hook accepted a bypassing desktop file: rc=$r3 $h3"

echo "== profile, menu"
grep -qE "^\s*profile audacity $REAL \{" "$PF" && ok "profile attaches the real program ($REAL)" || bad "profile attachment: $(grep -E '^\s*profile ' "$PF")"
grep -qE '^\s*profile \S+ /usr/bin/audacity' "$PF" && bad "profile still attaches /usr/bin/audacity (now the shim)" || ok "profile does not attach the shim"
grep -qx '  network inet stream,' "$PF" && ok "profile: TCP for the listener (inside the namespace)" || bad "profile: no inet stream (Audacity would not start)"
grep -qx '  owner @{run}/user/\[0-9\]\*/pipewire-\[0-9\]\* rw,' "$PF" && ok "profile: PipeWire socket (microphone)" || bad "profile: no PipeWire socket"
grep -qx '  deny /dev/video\* rw,' "$PF" && ok "profile: no camera" || bad "profile: camera"
grep -vE '^\s*#' "$PF" | grep -E '(bwrap|nsenter|prestium-audacity|/usr/bin/audacity|audacity-ns)\b.*\b[a-zA-Z]*x[a-zA-Z]*,' | grep -v "$REAL mr," && bad "profile may exec the sandbox tools" || ok "profile: no exec of bwrap, nsenter, wrapper, helper or shim"
grep -vE '^\s*#' "$PF" | grep -qE '\s(Ux|ux|Ix|Pux|pux|Cux|cux)\b|\s[a-z]*U[a-z]*x,' && bad "profile: unconfined exec" || ok "profile: no unconfined exec"
grep -q '<action name="Execute" command="prestium-run audacity" />' "$I/etc/xdg/labwc/menu.xml" && ok "menu: prestium-run audacity (restricted Wayland socket, then the shim)" || bad "menu entry"
o=$(grep -rlF "$REAL" "$I" "$R/config/hooks" | grep -vE "usr/local/bin/prestium-audacity$|usr/local/lib/prestium/audacity-ns$|etc/apparmor.d/usr.bin.audacity$|0620-prestium-audacity-netns.hook.chroot$")
[ -z "$o" ] && ok "nothing else starts $REAL directly" || bad "other references to $REAL: $o"

echo "== the wrapper with stand-ins (fail closed)"
S=$T/run; mkdir -p "$S/xdg"
export XDG_RUNTIME_DIR=$S/xdg
printf '#!/bin/sh\necho REAL "$@" > %s/real.ran\n' "$S" > "$S/real"; chmod 0755 "$S/real"
# The helper must be reachable at the rewritten path; use the real helper from the tree
mk(){ sed -e "s|^REAL=.*|REAL=$S/real|; s|^BWRAP=.*|BWRAP=$1|; s|^NS=.*|NS=$NSF|" "$WR" > "$S/w"; chmod 0755 "$S/w"; }
# no XDG_RUNTIME_DIR: refuse
mk /usr/bin/true
rm -f "$S/real.ran"
( unset XDG_RUNTIME_DIR; sh "$S/w" x >/dev/null 2>&1 ); r=$?
[ $r != 0 ] && [ ! -e "$S/real.ran" ] && ok "no XDG_RUNTIME_DIR: refuses, Audacity not started" || bad "no XDG_RUNTIME_DIR: rc=$r, started=$([ -e "$S/real.ran" ] && echo yes)"
mk "$S/no-bwrap"; rm -f "$S/real.ran"; sh "$S/w" x >/dev/null 2>&1; r=$?
[ $r != 0 ] && [ ! -e "$S/real.ran" ] && ok "no bubblewrap: refuses, Audacity not started" || bad "no bubblewrap: rc=$r, started=$([ -e "$S/real.ran" ] && echo yes)"
printf '#!/bin/sh\nexit 1\n' > "$S/bad-bwrap"; chmod 0755 "$S/bad-bwrap"; mk "$S/bad-bwrap"; rm -f "$S/real.ran"; sh "$S/w" x >/dev/null 2>&1; r=$?
[ $r != 0 ] && [ ! -e "$S/real.ran" ] && ok "bubblewrap fails: refuses, Audacity not started" || bad "bubblewrap fails: rc=$r"
# log argv, then run the real bwrap so serve (which requires an empty netns) can exec Audacity
cat > "$S/log-bwrap" <<FAKE
#!/bin/sh
printf '%s\n' "\$*" >> $S/bwrap.log
exec /usr/bin/bwrap "\$@"
FAKE
chmod 0755 "$S/log-bwrap"
if [ -x /usr/bin/bwrap ] && /usr/bin/bwrap --dev-bind / / --unshare-net --die-with-parent -- /usr/bin/true 2>/dev/null; then
  mk "$S/log-bwrap"; rm -f "$S/real.ran" "$S/bwrap.log"
  # serve execs the real program and would wait if it were a daemon; the stand-in real exits at once
  sh "$S/w" "a b" '$(id)' '*' >/dev/null 2>&1
  [ "$(cat "$S/real.ran" 2>/dev/null)" = 'REAL a b $(id) *' ] && ok "arguments reach Audacity unchanged" || bad "arguments: $(cat "$S/real.ran" 2>/dev/null)"
  [ "$(tail -1 "$S/bwrap.log" 2>/dev/null)" = "--dev-bind / / --unshare-net --die-with-parent -- $NSF serve $S/xdg/prestium-audacity/ns.sock -- $S/real a b \$(id) *" ] \
    && ok "bwrap gets --unshare-net --die-with-parent and the helper serve" || bad "bwrap argv: $(tail -1 "$S/bwrap.log" 2>/dev/null)"
else
  skip "bubblewrap can't make a network namespace here: argument and bwrap-argv checks not run with a real sandbox"
fi

echo "== live: network namespace isolation"
BW=/usr/bin/bwrap
if [ ! -x $BW ] || ! $BW --dev-bind / / --unshare-net --die-with-parent -- /usr/bin/true 2>/dev/null; then
  skip "bubblewrap can't make a network namespace here (needs unprivileged user namespaces): live isolation not checked"
else
  python3 -c '
import socket, sys
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(8)
open(sys.argv[1], "w").write(str(s.getsockname()[1])); import time
while True:
    c, _ = s.accept(); c.close()' "$T/hostport" & PIDS+=($!)
  for _ in $(seq 50); do [ -s "$T/hostport" ] && break; sleep 0.1; done
  HP=$(cat "$T/hostport"); python3 -c "import socket; socket.create_connection(('127.0.0.1', $HP), 2)" && ok "host listener on 127.0.0.1:$HP reachable from the host" || bad "host listener"
  python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(8)
while True:
    c, _ = s.accept(); c.sendall(b"pw"); c.close()' "$T/pipewire-0" & PIDS+=($!)
  for _ in $(seq 50); do [ -S "$T/pipewire-0" ] && break; sleep 0.1; done
  L=$T/live; mkdir -p "$L/xdg"
  export XDG_RUNTIME_DIR=$L/xdg
  cp /usr/bin/python3 "$L/prestium-audacity"
  # a fake nsenter --target that fails if called: the wrapper must not use it
  mkdir -p "$L/bin"
  printf '#!/bin/sh\necho nsenter-called > "%s/nsenter.ran"; exit 1\n' "$L" > "$L/bin/nsenter"
  chmod 0755 "$L/bin/nsenter"
  sed -e "s|^REAL=.*|REAL=$L/prestium-audacity|; s|^NS=.*|NS=$NSF|" "$WR" > "$L/w"
  chmod 0755 "$L/w"
  PROBE='
import os, socket, sys, json
r = {"net": os.readlink("/proc/self/ns/net")}
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(8); r["own_port"] = s.getsockname()[1]
try: socket.create_connection(("127.0.0.1", int(sys.argv[1])), 2); r["host"] = "connected"
except OSError as e: r["host"] = "refused: %s" % e.strerror
try:
    u = socket.socket(socket.AF_UNIX); u.connect(sys.argv[2]); r["unix"] = u.recv(2).decode()
except OSError as e: r["unix"] = "error: %s" % e.strerror
r["ifaces"] = sorted(l.split(":")[0].strip() for l in open("/proc/net/dev").readlines()[2:])
r["dev"] = open("/dev/null", "w").write("x") == 1 and os.path.isdir("/dev/snd") == (sys.argv[4] == "snd")
r["home"] = os.access(os.path.expanduser("~"), os.R_OK)
open(sys.argv[3], "w").write(json.dumps(r))
if len(sys.argv) > 5:
    open(sys.argv[5], "w").write(str(r["own_port"]))
    import time; c, _ = s.accept(); c.sendall(b"si"); time.sleep(3)
'
  PATH=$L/bin:$PATH sh "$L/w" -c "$PROBE" "$HP" "$T/pipewire-0" "$L/first.json" "$([ -d /dev/snd ] && echo snd || echo none)" "$L/first.port" & PIDS+=($!)
  for _ in $(seq 100); do [ -s "$L/first.port" ] && break; sleep 0.1; done
  j(){ python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2" 2>/dev/null; }
  if [ ! -s "$L/first.json" ]; then bad "the wrapper did not start the stand-in Audacity"
  else
    [ "$(j "$L/first.json" net)" != "$(readlink /proc/self/ns/net)" ] && ok "Audacity runs in a network namespace of its own" || bad "same network namespace as the host"
    [ "$(j "$L/first.json" ifaces)" = "['lo']" ] && ok "its namespace has only a loopback" || bad "interfaces: $(j "$L/first.json" ifaces)"
    [ -n "$(j "$L/first.json" own_port)" ] && ok "it can listen on its own 127.0.0.1 (single-instance check)" || bad "no listener"
    case $(j "$L/first.json" host) in refused*) ok "it can't connect to the host's 127.0.0.1:$HP ($(j "$L/first.json" host))";; *) bad "host loopback reachable: $(j "$L/first.json" host)";; esac
    [ "$(j "$L/first.json" unix)" = pw ] && ok "filesystem Unix sockets still connect (PipeWire/PulseAudio: microphone)" || bad "Unix socket: $(j "$L/first.json" unix)"
    [ "$(j "$L/first.json" dev)" = True ] && [ "$(j "$L/first.json" home)" = True ] && ok "device nodes (/dev/null, /dev/snd as on the host) and the home stay usable" || bad "devices/home"
    P2='
import os, socket, sys, json
r = {"net": os.readlink("/proc/self/ns/net")}
try: c = socket.create_connection(("127.0.0.1", int(sys.argv[1])), 2); r["si"] = c.recv(2).decode()
except OSError as e: r["si"] = "error: %s" % e.strerror
try: socket.create_connection(("127.0.0.1", int(sys.argv[2])), 2); r["host"] = "connected"
except OSError as e: r["host"] = "refused"
r["caps"] = [l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff")][0]
open(sys.argv[3], "w").write(json.dumps(r))
'
    PATH=$L/bin:$PATH sh "$L/w" -c "$P2" "$(cat "$L/first.port")" "$HP" "$L/second.json"
    [ ! -e "$L/nsenter.ran" ] && ok "second start did not call nsenter" || bad "nsenter was invoked"
    [ "$(j "$L/second.json" net)" = "$(j "$L/first.json" net)" ] && ok "a second start joins the running Audacity's namespace" || bad "second start: other namespace ($(j "$L/second.json" net))"
    [ "$(j "$L/second.json" si)" = si ] && ok "the second start reaches the first one's 127.0.0.1 listener (single instance)" || bad "single instance: $(j "$L/second.json" si)"
    [ "$(j "$L/second.json" host)" = refused ] && ok "the joined start can't reach the host's 127.0.0.1 either" || bad "joined start reaches the host"
    [ "$(j "$L/second.json" caps)" = 0000000000000000 ] && ok "the joined start has no capabilities" || bad "joined caps: $(j "$L/second.json" caps)"
  fi
  # A socket that hands over the host network must be refused (same-user replacement)
  python3 -c '
import array, os, socket, sys
sock_path, marker = sys.argv[1], sys.argv[2]
if os.path.exists(sock_path):
    os.unlink(sock_path)
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(sock_path); os.chmod(sock_path, 0o600); s.listen(1)
# write a pid so the test can wait until we are listening, then serve one client
open(marker + ".ready", "w").write("1")
conn, _ = s.accept()
user = os.open("/proc/self/ns/user", os.O_RDONLY)
net = os.open("/proc/self/ns/net", os.O_RDONLY)
conn.sendmsg([b"ns"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [user, net]).tobytes())])
conn.close()
' "$L/xdg/prestium-audacity/host.sock" "$L/evil" & PIDS+=($!)
  for _ in $(seq 50); do [ -f "$L/evil.ready" ] && break; sleep 0.05; done
  rm -f "$L/evil.ran"
  printf '#!/bin/sh\necho started > "%s"\n' "$L/evil.ran" > "$L/evil-real"; chmod 0755 "$L/evil-real"
  if "$NSF" join "$L/xdg/prestium-audacity/host.sock" -- "$L/evil-real"; then
    bad "join accepted the host network namespace"
  else
    [ ! -e "$L/evil.ran" ] && ok "join refuses a socket that hands over the host network" || bad "join refused but the program still started"
  fi
  # X11: Xwayland's abstract socket is not in the namespace; libxcb falls back to /tmp/.X11-unix
  if command -v Xvfb >/dev/null && command -v xdpyinfo >/dev/null; then
    n=$((90 + RANDOM % 9)); while [ -e "/tmp/.X11-unix/X$n" ]; do n=$((n + 1)); done
    Xvfb ":$n" -nolisten tcp >/dev/null 2>&1 & PIDS+=($!)
    for _ in $(seq 50); do [ -S "/tmp/.X11-unix/X$n" ] && break; sleep 0.1; done
    sed -e "s|^REAL=.*|REAL=/usr/bin/xdpyinfo|; s|^NS=.*|NS=$NSF|" "$WR" > "$L/wx"
    chmod 0755 "$L/wx"
    DISPLAY=":$n" XDG_RUNTIME_DIR=$L/xdg sh "$L/wx" >/dev/null 2>&1 && ok "X11 (DISPLAY=:$n) works in the namespace through /tmp/.X11-unix/X$n" || bad "X11 display lost in the namespace"
    DISPLAY=":$n" $BW --dev-bind / / --tmpfs /tmp/.X11-unix --unshare-net -- /usr/bin/xdpyinfo >/dev/null 2>&1 \
      && bad "abstract X11 socket reachable from the namespace" || ok "the host's abstract X11 socket is not reachable from the namespace"
  else skip "Xvfb/xdpyinfo missing: X11 fallback not checked live"; fi
fi
[ $fail = 0 ] && echo "audacity netns: OK"; exit $fail
