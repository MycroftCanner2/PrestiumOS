#!/bin/bash
# 2.1: Feather's network is I2P everywhere: the menu label, both settings.json copies (proxy 2 =
# Feather's Config::Proxy::i2p, SOCKS host 127.0.0.1, port = i2pd's [socksproxy] port), ferm (that port
# is open to "user"; the 9050 comment no longer names Feather) and the AppArmor profile (no exec, so no
# bundled Tor, no Documents beyond its own folder).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
port=""
for c in etc/i2pd/i2pd.conf var/lib/i2pd/i2pd.conf; do
  p=$(awk '/^\[/{s=$0} s=="[socksproxy]" && /^port *=/{gsub(/[^0-9]/,"");print}' "$I/$c")
  e=$(awk '/^\[/{s=$0} s=="[socksproxy]" && /^enabled *=/{print $3}' "$I/$c")
  [ -n "$p" ] && [ "$e" = true ] && ok "$c: I2P SOCKS on, port $p" || bad "$c: socksproxy port/enabled ($p/$e)"
  [ -z "$port" ] && port=$p; [ "$p" = "$port" ] || bad "i2pd.conf copies disagree ($p vs $port)"
done
for s in etc/skel/.config/feather/settings.json home/user/.config/feather/settings.json; do
  python3 - "$I/$s" "$port" <<'PY' && ok "$s: I2P (proxy 2) via 127.0.0.1:$port, no local Tor" || bad "$s not I2P on $port"
import json, sys
j = json.load(open(sys.argv[1]))
assert j["proxy"] == 2 and j["socks5Host"] == "127.0.0.1" and str(j["socks5Port"]) == sys.argv[2], j
assert j.get("useLocalTor") is False and j.get("firstRun") is False
PY
done
cmp -s "$I/etc/skel/.config/feather/settings.json" "$I/home/user/.config/feather/settings.json" && ok "skel and live user settings identical" || bad "settings.json copies differ"
m=$(grep -A1 -F 'command="prestium-run feather"' "$I/etc/xdg/labwc/menu.xml"; grep -B1 -F 'command="prestium-run feather"' "$I/etc/xdg/labwc/menu.xml")
grep -q 'label="Feather (Monero Wallet, I2P)"' <<<"$m" && ok "menu: Feather (… I2P)" || bad "menu label"
grep -q -i 'feather.*tor\b' "$I/etc/xdg/labwc/menu.xml" && bad "menu mentions Tor for Feather" || ok "menu doesn't say Tor"
F=$I/etc/ferm/ferm.conf
up=$(grep -E '^def \$user_ports' "$F")
grep -qE "[( ]${port}[ )]" <<<"$up" && ok "ferm: user may reach I2P SOCKS $port" || bad "ferm: $port not in user_ports"
grep -E '^#.*9050' "$F" | grep -q -i 'feather' && grep -E '^#.*9050' "$F" | grep -i feather | grep -qv -i 'uses I2P' \
  && bad "ferm comment still puts Feather on Tor 9050" || ok "ferm: Feather not listed on Tor 9050"
grep -E "^#.*$port I2P SOCKS" "$F" | grep -q Feather && ok "ferm: Feather listed on $port" || bad "ferm: Feather not on $port"
A=$I/etc/apparmor.d/usr.local.bin.feather
r=$(grep -vE '^\s*#' "$A")
grep -qE '^\s*(owner\s+|audit\s+)?/\S*\s+[a-zA-Z]*x[a-zA-Z]*\s*(->.*)?,\s*$|\s(ix|px|Px|ux|Ux|cx|Cx|pix|Pix|cix|Cix)\s+/' <<<"$r" && bad "feather profile allows exec" || ok "feather: no exec rules (no bundled Tor)"
grep -qE 'ptrace|capability|/run/tor|9050|control' <<<"$r" && bad "feather: ptrace/capability/Tor control" || ok "feather: no ptrace, capabilities or Tor control"
grep -q 'include <abstractions/prestium-app-base>' <<<"$r" && ok "feather: prestium-app-base" || bad "feather: base abstraction missing"
grep -qE 'Documents/(\*\*|) *rw|Downloads' <<<"$r" && bad "feather writes shared folders" || ok "feather writes only its own folders"
grep -q 'usr.local.bin.feather' "$R/config/hooks/live/0600-prestium-apparmor.hook.chroot" && ok "profile installed and enforced by hook 0600" || bad "hook 0600 lost feather"
grep -q '\bfeather\b' "$I/usr/local/bin/prestium-safety-notify" && ok "safety notice watches the feather profile" || bad "safety notify misses feather"
exit $fail
