#!/bin/bash
# 2.1 (security audit): i2pd and Tor parse remote network input, so neither may reach Prestium's
# local services on loopback (The Lounge 9000 and 9010, i2pd console 7070, I2P Torrents 7685, IRC tunnels,
# mail tunnels). i2pd: loopback only 4500 (its SOCKS outproxy tunnel). Tor: loopback only the
# kernel's ephemeral ports (its pluggable transports listen on 127.0.0.1:0). Static checks on
# ferm.conf; renders it with ferm when installed.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); F=$R/config/includes.chroot/etc/ferm/ferm.conf; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
rules=$(grep -vE '^\s*#' "$F")
for u in i2pd_uid tor_uid; do
  # every ACCEPT naming this uid must be bound to an interface (no blanket accept)
  while IFS= read -r l; do
    case $l in *outerface*) ;; *) bad "blanket accept for \$$u: $(echo $l)";; esac
  done < <(grep -E "uid-owner \\\$$u\b.*ACCEPT" <<<"$rules")
done
grep -qE '^\s*outerface ! lo mod owner uid-owner \$i2pd_uid ACCEPT;' <<<"$rules" && ok "i2pd: network (not loopback)" || bad "i2pd network rule"
grep -qE '^\s*outerface ! lo mod owner uid-owner \$tor_uid proto tcp ACCEPT;' <<<"$rules" && ok "Tor: TCP to the network (not loopback)" || bad "Tor network rule"
n=$(grep -cE 'uid-owner \$i2pd_uid outerface lo ' <<<"$rules")
grep -qE 'uid-owner \$i2pd_uid outerface lo daddr 127\.0\.0\.1 proto \(tcp udp\) dport 4500 ACCEPT;' <<<"$rules" && [ "$n" = 1 ] \
  && ok "i2pd: loopback only 4500" || bad "i2pd loopback rules ($n)"
lo_tor=$(grep -E 'outerface lo .*uid-owner \$tor_uid' <<<"$rules")
[ "$(wc -l <<<"$lo_tor")" = 2 ] && grep -qE 'daddr 127\.0\.0\.1 proto tcp syn dport 32768:60999 ' <<<"$lo_tor" \
  && grep -qE 'daddr 127\.0\.0\.1 proto tcp syn dport 17600:17650 ' <<<"$lo_tor" \
  && ok "Tor: loopback only ephemeral ports 32768-60999 and OnionShare 17600-17650" || bad "Tor loopback rules: $lo_tor"
# OnionShare's onion-grater target range and the firewall's agree
grep -q '17600-17650' config/includes.chroot/usr/local/sbin/prestium-onion-grater 2>/dev/null || grep -q '17600-17650' "$R/config/includes.chroot/usr/local/sbin/prestium-onion-grater" \
  && ok "onion-grater OnionShare targets match the firewall" || bad "OnionShare port range differs"
for p in 4444 4447 4450 4500 6665 6672 7070 7656 7659 7660 7685 9000 9010 9050 9051 17600 17650 30000; do
  [ "$p" -ge 32768 ] && bad "service port $p inside Tor's loopback range"; done
ok "fixed local service ports are below Tor's loopback range"
cat "$R"/config/includes.chroot/etc/sysctl.d/* "$R"/config/includes.chroot/usr/lib/sysctl.d/* 2>/dev/null \
  | grep -v '^\s*#' | grep -q 'ip_local_port_range' && bad "ip_local_port_range changed (update ferm.conf)" || ok "kernel ephemeral range unchanged"
# the Snowflake include stays off loopback
grep -q 'outerface ! lo mod owner uid-owner \$tor_uid proto udp ACCEPT;' "$R/config/includes.chroot/usr/local/sbin/prestium-tor-mode" \
  && ok "Snowflake UDP rule stays off loopback" || bad "Snowflake rule"
if command -v ferm >/dev/null; then
  ferm --noexec --lines "$F" >/dev/null 2>&1 && ok "ferm renders it" || bad "ferm cannot render ferm.conf"
else echo "SKIP ferm missing"; fi
exit $fail
