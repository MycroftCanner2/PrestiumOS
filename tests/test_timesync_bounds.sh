#!/bin/bash
# 2.1 (audit L-3): prestium-timesync (the clock over Tor) and prestium-clockfix (from Tor's consensus)
# keep the same bounds as prestium-set-clock: never before the image's build date (one day of slack)
# or more than 10 years after it. A big jump raises a safety flag. Runs patched copies with fake
# sites, build date, flag and clock, so nothing on this machine changes. Also checks the units.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
date -u -d '2026-11-10 12:00' +%s > "$T/build"
printf '#!/bin/sh\necho "$@" >> %s/flag\n' "$T" > "$T/flag.sh"; chmod 755 "$T/flag.sh"
mkdir "$T/bin"
# fake runuser: "curl -sI" answers with the Date header in $T/answer, anything else succeeds
cat > "$T/bin/runuser" <<STUB
#!/bin/sh
case " \$* " in *" -sI "*) printf 'HTTP/2 200\r\ndate: %s\r\n\r\n' "\$(cat $T/answer)";; esac
exit 0
STUB
printf '#!/bin/sh\nexit 0\n' > "$T/bin/systemctl"; chmod 755 "$T/bin/"*
sed -e "s#^PATH=.*#PATH=$T/bin:/usr/bin:/bin; export PATH#" -e "s#^BUILD_FILE=.*#BUILD_FILE=$T/build#" \
    -e "s#^FLAG=.*#FLAG=$T/flag.sh#" -e "s#date -u -s \"@\$med\" >/dev/null#echo \"\$med\" > $T/set#" \
    "$I/usr/local/sbin/prestium-timesync" > "$T/ts"
grep -q "> $T/set" "$T/ts" && ok "timesync copy patched" || bad "timesync patch"
run(){ rm -f "$T/set" "$T/flag"; printf '%s' "$1" > "$T/answer"; sh "$T/ts" 2>&1; }
o=$(run "$(date -u '+%a, %d %b %Y %H:%M:%S GMT')"); [ ! -e "$T/set" ] && [ ! -e "$T/flag" ] && ok "correct clock: left alone" || bad "correct clock: $o"
for d in "Sat, 01 Jan 2000 00:00:00 GMT" "Mon, 08 Nov 2026 00:00:00 GMT" "Fri, 01 Jan 2049 00:00:00 GMT"; do
  o=$(run "$d"); { [ ! -e "$T/set" ] && grep -q clock-sync "$T/flag"; } && ok "refused, flagged: $d" || bad "accepted: $d ($o)"; done
# a time inside the bounds but days away from now: set, and flagged as a big jump
far=$(( $(date -u +%s) + 5*86400 )); b=$(cat "$T/build")
if [ "$far" -le $((b + 315576000)) ]; then
  o=$(run "$(date -u -d "@$far" '+%a, %d %b %Y %H:%M:%S GMT')")
  [ "$(cat "$T/set" 2>/dev/null)" = "$far" ] && grep -q 'clock-sync.*moved the clock' "$T/flag" && ok "5-day jump: set and flagged" || bad "5-day jump: $o"
fi
C=$I/usr/local/sbin/prestium-clockfix
grep -q 'build - 86400' "$C" && grep -q 'build + 315576000' "$C" && ok "clockfix: same bounds" || bad "clockfix bounds"
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
