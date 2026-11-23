#!/bin/bash
# Security review F-03: DHCP never sends the hostname, and the client identifiers follow the random
# MAC address. Static checks of the shipped NetworkManager configuration; when NetworkManager is
# installed, its own parser reads the shipped conf.d (offline, nothing on this machine changes).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
D=$I/etc/NetworkManager/conf.d; C=$D/45-prestium-dhcp.conf
[ -f "$C" ] || { bad "45-prestium-dhcp.conf missing"; exit 1; }
sect(){ awk -v s="[$2]" '/^\[/{f=($0==s)} f && /^[a-z]/' "$1"; }
for kv in ipv4.dhcp-send-hostname=false ipv6.dhcp-send-hostname=false \
          ipv4.dhcp-client-id=mac ipv4.dhcp-iaid=mac ipv6.dhcp-duid=ll ipv6.dhcp-iaid=mac; do
  sect "$C" connection | grep -qx "$kv" && ok "[connection] $kv" || bad "[connection] $kv missing"
done
sect "$C" main | grep -qx 'dhcp=internal' && ok "[main] dhcp=internal" || bad "dhcp client not pinned to internal"
# no other shipped file (read after 45 in name order) turns it back on or picks another client
if grep -hE '^(ipv[46]\.dhcp-send-hostname=(true|1|yes)|ipv[46]\.dhcp-hostname=|dhcp=(dhclient|dhcpcd))' "$D"/*.conf; then
  bad "a conf.d file sends a hostname or uses another DHCP client"; else ok "no conf.d file sends a hostname"; fi
grep -q 'hostname-mode=none' "$D/40-prestium-privacy.conf" && ok "DHCP can't set the hostname either" || bad "hostname-mode"
[ -z "$(ls -A "$I/etc/NetworkManager/system-connections" 2>/dev/null)" ] && ok "no shipped connection profile overrides the defaults" \
  || bad "a shipped connection profile could override the DHCP defaults"
grep -qx '0644 root root /etc/NetworkManager/conf.d/45-prestium-dhcp.conf' "$I/usr/share/prestium/build/perms.txt" && ok "perms" || bad "perms.txt entry"
H=$R/config/hooks/live/0400-prestium-system.hook.chroot
grep -q 'dhclient.conf still sends the hostname' "$H" && ok "hook 0400 removes dhclient's send host-name" || bad "hook 0400 dhclient"
# the hook's sed on a stock dhclient.conf
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
printf 'option rfc3442-classless-static-routes code 121 = array of unsigned integer 8;\n\nsend host-name = gethostname();\nrequest subnet-mask;\n' > "$T/dhclient.conf"
sed -i 's/^\([[:space:]]*send[[:space:]]\+host-name\)/#prestium F-03: \1/' "$T/dhclient.conf"
grep -qE '^[[:space:]]*send[[:space:]]+host-name' "$T/dhclient.conf" && bad "sed left send host-name" || ok "sed comments out send host-name"
NM=$(command -v NetworkManager || ls /usr/sbin/NetworkManager 2>/dev/null)
if [ -n "$NM" ]; then
  : > "$T/empty.conf"
  o=$("$NM" --print-config --config-dir="$D" --config="$T/empty.conf" --system-config-dir="$T/none" 2>&1)
  if printf '%s\n' "$o" | grep -q '^\[connection\]'; then
    for kv in ipv4.dhcp-send-hostname=false ipv6.dhcp-send-hostname=false ipv4.dhcp-client-id=mac dhcp=internal; do
      printf '%s\n' "$o" | grep -qx "$kv" && ok "NetworkManager's merged config: $kv" || bad "NetworkManager's merged config lacks $kv"
    done
    printf '%s\n' "$o" | grep -q "unknown key.*45-prestium-dhcp.conf" && bad "NetworkManager does not know a key in 45-prestium-dhcp.conf" \
      || ok "NetworkManager knows every key in 45-prestium-dhcp.conf"
  else echo "SKIP NetworkManager --print-config gave nothing"; fi
else echo "SKIP NetworkManager not installed (merged-config check)"; fi
exit $fail
