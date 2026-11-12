#!/bin/bash
# 2.1: Tor Browser reconnects after Tor restarts (Tor Connection Assistant switching methods).
# The sandbox must bind the socket directories, not the socket files: Tor makes a new SOCKS socket
# at every start, and a bound socket file stays the old one inside the sandbox. Static checks, plus
# (where unshare works) a live check that a read-only directory bind sees a re-created socket.
root=$(cd "$(dirname "$0")/.." && pwd); I="$root/config/includes.chroot"; fail=0
ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; fail=1; }
L="$I/usr/local/bin/tor-browser"
grep -q -- '--ro-bind "${SOCKS%/\*}" "${SOCKS%/\*}" --ro-bind-try "${CTL%/\*}" "${CTL%/\*}"' "$L" \
  && ok "tor-browser binds /run/prestium-tbb and /run/onion-grater" || bad "tor-browser: directory binds missing"
grep -qE -- '--bind(-try)? "\$(SOCKS|CTL)"' "$L" && bad "tor-browser still binds a socket file" || ok "no socket-file binds"
grep -q '^SOCKS=/run/prestium-tbb/socks$' "$L" && grep -q '^CTL=/run/onion-grater/control$' "$L" \
  && ok "socket paths unchanged" || bad "socket paths changed"
grep -q '^RuntimeDirectoryPreserve=yes$' "$I/etc/systemd/system/prestium-onion-grater.service" \
  && ok "onion-grater keeps /run/onion-grater across restarts" || bad "onion-grater: RuntimeDirectoryPreserve missing"
grep -q 'SocksPort unix:/run/prestium-tbb/socks' "$I/etc/tor/torrc" && ok "Tor's socket is in /run/prestium-tbb" || bad "torrc socket path"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; mkdir "$T/d" "$T/m"
if unshare -rm true 2>/dev/null; then
  if unshare -rm sh -c "mount --bind '$T/d' '$T/m' && mount -o remount,bind,ro '$T/m' && python3 -I -c '
import os, socket, sys
d, m = sys.argv[1], sys.argv[2]
a = socket.socket(socket.AF_UNIX); a.bind(d + \"/s\"); a.listen()
socket.socket(socket.AF_UNIX).connect(m + \"/s\"); a.close(); os.unlink(d + \"/s\")
b = socket.socket(socket.AF_UNIX); b.bind(d + \"/s\"); b.listen()
socket.socket(socket.AF_UNIX).connect(m + \"/s\")' '$T/d' '$T/m'"; then
    ok "read-only directory bind reaches a re-created socket"
  else bad "read-only directory bind: re-created socket not reachable"; fi
else echo "SKIP unshare not available"; fi
exit $fail
