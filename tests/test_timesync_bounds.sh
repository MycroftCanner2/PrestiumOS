#!/bin/bash
# 2.1 (audit L-3): prestium-clockfix (from Tor's consensus) keeps the same bounds as prestium-set-clock: never before the image's build date (one day of slack)
# or more than 10 years after it. A big jump raises a safety flag. Runs patched copies with fake
# sites, build date, flag and clock, so nothing on this machine changes. Also checks the units.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
date -u -d '2026-11-10 12:00' +%s > "$T/build"
printf '#!/bin/sh\necho "$@" >> %s/flag\n' "$T" > "$T/flag.sh"; chmod 755 "$T/flag.sh"
mkdir "$T/bin"
# prestium-timesync is Python since 2.1 (sdwdate design); its bounds are in tests/test_timesync.py
C=$I/usr/local/sbin/prestium-clockfix
# clockfix, run: a fake consensus far in the past, Tor never bootstrapped, a fake clock
mkdir -p "$T/tor"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/journalctl"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/sleep"; chmod 755 "$T/bin/"*
cf(){ rm -f "$T/set" "$T/flag"
  printf 'valid-after %s\nvalid-until %s\n' "$1" "$2" > "$T/tor/cached-microdesc-consensus"
  sed -e "s#^PATH=.*#PATH=$T/bin:/usr/bin:/bin; export PATH#" -e "s#^D=/var/lib/tor#D=$T/tor#" \
      -e "s#/usr/share/prestium/build-date#$T/build#" -e "s#/usr/local/lib/prestium/safety-flag#$T/flag.sh#" \
      -e "s#date -u -s \"@\$new\" >/dev/null#echo \"\$new\" > $T/set#" "$C" > "$T/cf"; sh "$T/cf" 2>&1; }
o=$(cf "2020-01-01 00:00:00" "2020-01-01 03:00:00"); { [ ! -e "$T/set" ] && grep -q clock-sync "$T/flag"; } && ok "clockfix: consensus before the build refused, flagged" || bad "clockfix old consensus: $o"
in=$(( $(cat "$T/build") + 30*86400 )); va=$(date -u -d "@$in" '+%F %T'); vu=$(date -u -d "@$((in+10800))" '+%F %T')
if [ "$(date -u +%s)" -lt $((in - 600)) ]; then
  o=$(cf "$va" "$vu"); [ "$(cat "$T/set" 2>/dev/null)" = "$((in + 5400))" ] && ok "clockfix: consensus in bounds sets valid-after + 90 min" || bad "clockfix in bounds: $o"; fi
U=$I/etc/systemd/system
for u in prestium-timesync prestium-clockfix prestium-usb-watchdog; do
  grep -q '^CapabilityBoundingSet=' "$U/$u.service" && ok "$u: bounded capabilities" || bad "$u: no CapabilityBoundingSet"
  grep -qx 'NoNewPrivileges=yes' "$U/$u.service" && ok "$u: NoNewPrivileges" || bad "$u: NoNewPrivileges"
  grep -qx 'ProtectClock=yes' "$U/$u.service" && [ "$u" != prestium-usb-watchdog ] && bad "$u: ProtectClock forbids its job"
done
for u in prestium-timesync prestium-clockfix; do
  grep -qx 'ProtectSystem=strict' "$U/$u.service" && grep -q '^SystemCallFilter=@system-service @clock$' "$U/$u.service" \
    && ok "$u: read-only system, syscall filter" || bad "$u: sandbox"; done
grep -qx 'PrivateNetwork=yes' "$U/prestium-clockfix.service" && ok "clockfix: no network" || bad "clockfix network"
W=$U/prestium-usb-watchdog.service
grep -Eq '^(ProtectSystem|PrivateTmp|ProtectKernelTunables|SystemCallFilter)=' "$W" && bad "watchdog: a setting that hides what it must wipe or write" || ok "watchdog: overlay, /tmp and sysrq stay reachable"
for c in CAP_KILL CAP_SYS_BOOT CAP_FOWNER CAP_DAC_OVERRIDE; do grep -q "^CapabilityBoundingSet=.*$c" "$W" || bad "watchdog lacks $c"; done
ok "watchdog: keeps kill, sys_boot, fowner, dac_override"
exit $fail
