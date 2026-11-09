#!/bin/sh
# Checks that stopping ferm falls back to drop-all instead of Debian's flush-to-ACCEPT.
set -e
R=$(dirname "$0")/../config/includes.chroot
F=$R/etc/systemd/system/ferm.service.d/prestium-failclosed.conf
S=$R/usr/local/sbin/prestium-firewall-early
grep -qx 'ExecStop=' "$F"
grep -qx 'ExecStop=/usr/local/sbin/prestium-firewall-early' "$F"
[ "$(grep -c '^ExecStop' "$F")" -eq 2 ]
for c in INPUT OUTPUT FORWARD; do grep -q -- "-P $c DROP" "$S"; done
grep -q ip6tables-legacy "$S"
grep -q 'ferm.service.d/prestium-failclosed.conf' $R/usr/share/prestium/build/perms.txt
echo "ferm stop fail-closed: OK"
