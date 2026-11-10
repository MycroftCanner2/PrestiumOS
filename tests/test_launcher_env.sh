#!/bin/bash
# 2.1 (security audit): Claws Mail, Gajim and Pidgin start tor-browser and librewolf-i2p with
# AppArmor "Ux", which keeps their environment. The launchers (and the sandbox library they source)
# must run only fixed files: no PRESTIUM_* overrides, no BASH_ENV/ENV, no exported functions, no
# PATH lookups in a directory the caller chose. No root, network or bwrap needed.
set -u
H=$(cd "$(dirname "$0")/.." && pwd)
I=$H/config/includes.chroot
fail=0; ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
LIB=$I/usr/local/lib/prestium/browser-sandbox.sh
for f in tor-browser librewolf-i2p; do
  F=$I/usr/local/bin/$f
  [ "$(head -1 "$F")" = '#!/bin/bash -p' ] && ok "$f: bash -p" || bad "$f: shebang is not bash -p"
  grep -qx 'PATH=/usr/bin:/bin; export PATH' "$F" && ok "$f: fixed PATH" || bad "$f: PATH not fixed"
  grep -v '^ *#' "$F" | grep -q 'PRESTIUM_' && bad "$f: reads a PRESTIUM_* variable" || ok "$f: no PRESTIUM_* override"
  grep -qx 'SBX_LIB=/usr/local/lib/prestium/browser-sandbox.sh' "$F" && ok "$f: fixed sandbox library" || bad "$f: sandbox library path"
done
grep -v '^ *#' "$LIB" | grep -q 'PRESTIUM_' && bad "sandbox library reads a PRESTIUM_* variable" || ok "sandbox library: no PRESTIUM_* override"
grep -qx 'SBX_BWRAP=/usr/bin/bwrap' "$LIB" && ok "sandbox library: fixed bwrap" || bad "bwrap path"

# dynamic: a hostile caller environment must not run anything of the caller's
mkdir -p "$T/evil" "$T/home" "$T/xdg"
M=$T/marker
printf '#!/bin/sh\n/usr/bin/touch %s\n' "$M" > "$T/evil/hook"; chmod 755 "$T/evil/hook"
for c in id mkdir cp chmod sed socat bwrap notify-send seq sleep rm kill; do ln -s hook "$T/evil/$c"; done
printf '/usr/bin/touch %s\n' "$M" > "$T/evil.sh"
for f in tor-browser librewolf-i2p; do
  rm -f "$M"
  env -i HOME="$T/home" XDG_RUNTIME_DIR="$T/xdg" PATH="$T/evil" BASH_ENV="$T/evil.sh" ENV="$T/evil.sh" \
    'BASH_FUNC_id%%=() { /usr/bin/touch '"$M"'; }' 'BASH_FUNC_command%%=() { /usr/bin/touch '"$M"'; }' \
    PRESTIUM_SANDBOX_LIB="$T/evil.sh" PRESTIUM_BWRAP="$T/evil/hook" PRESTIUM_WL_BASE="$T" \
    PRESTIUM_LIBREWOLF="$T/evil/hook" PRESTIUM_I2P_HTTP_PORT=1 \
    "$I/usr/local/bin/$f" >/dev/null 2>&1 </dev/null
  [ -e "$M" ] && bad "$f ran code chosen by the caller's environment" || ok "$f ignores a hostile environment"
done
# the sandbox library itself: sourced with hostile overrides, it keeps its fixed paths
out=$(env -i PATH=/usr/bin:/bin PRESTIUM_BWRAP="$T/evil/hook" PRESTIUM_WL_BASE="$T" bash -c '. "$1"; echo "$SBX_BWRAP $SBX_WL_BASE"' _ "$LIB")
[ "$out" = "/usr/bin/bwrap /run/prestium-wl" ] && ok "sandbox library keeps fixed paths" || bad "sandbox library paths: $out"
exit $fail
