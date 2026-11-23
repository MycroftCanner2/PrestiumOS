#!/bin/bash
# 2.1 (security audit): "sudo date -s" is gone; the user may set the clock only through
# prestium-set-clock: strict UTC date and time, not before the image's build date (one day of
# slack) or more than 10 years after it, and a safety flag afterwards. Runs a patched copy (fake
# build date, flag and clock) under unshare -r, so nothing on this machine changes.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
S=$I/usr/local/sbin/prestium-set-clock
SU=$I/etc/sudoers.d/prestium-set-clock
[ -e "$I/etc/sudoers.d/date" ] && bad "old sudo date rule still shipped" || ok "no sudo date rule"
# security review F-07: no sudo rule at all; the Wayland broker runs the helper after the person at the
# screen confirms the time (tests/test_broker_confirm_f07.py)
[ -e "$SU" ] && bad "sudoers rule for prestium-set-clock still shipped" || ok "F-07: no sudoers rule (the broker runs it after a confirmation)"
grep -q '/etc/sudoers.d/prestium-set-clock' "$I/usr/share/prestium/build/perms.txt" && bad "perms.txt still lists the sudoers file" || ok "perms: no sudoers entry"
grep -rqs 'prestium-set-clock' "$I/etc/sudoers.d" && bad "another sudoers file names prestium-set-clock" || ok "no sudoers file names prestium-set-clock"
grep -qx '0755 root root /usr/local/sbin/prestium-set-clock' "$I/usr/share/prestium/build/perms.txt" && ok "perms: helper" || bad "perms helper"
grep -q '/usr/share/prestium/build-date' "$R/config/hooks/live/0400-prestium-system.hook.chroot" && ok "hook 0400 records the build date" || bad "no build date"
unshare -r true 2>/dev/null || { echo "SKIP unshare -r unavailable"; exit $fail; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
date -u -d '2026-11-10 12:00' +%s > "$T/build"
printf '#!/bin/sh\necho "$@" >> %s/flag\n' "$T" > "$T/flag.sh"; chmod 755 "$T/flag.sh"
sed -e "s#^BUILD_FILE=.*#BUILD_FILE=$T/build#" -e "s#^FLAG=.*#FLAG=$T/flag.sh#" \
    -e "s#date -u -s \"@\$new\" >/dev/null#echo \"\$new\" > $T/set#" "$S" > "$T/sc"; chmod 755 "$T/sc"
run(){ rm -f "$T/set" "$T/flag"; unshare -r "$T/sc" "$@" 2>&1; }
o=$(run 2026-11-10 14:30) && [ "$(cat "$T/set")" = "$(date -u -d '2026-11-10 14:30' +%s)" ] && grep -q 'clock-manual' "$T/flag" \
  && ok "valid UTC time set, safety flag raised" || bad "valid time: $o"
o=$(run 2026-11-09 13:00) && ok "one day of slack before the build date" || bad "slack: $o"
for a in "2026-11-08 12:00" "2020-01-01 00:00" "2037-01-01 00:00" "2026-02-30 10:00" "2026-11-10 24:61" \
         "2026-11-10 14:30 x" "2026-11-10" "-f /etc/shadow" "2026-11-10 14:30:99" "+1 day" "@0 x"; do
  # shellcheck disable=SC2086
  o=$(run $a) && bad "accepted: $a" || { [ -e "$T/set" ] && bad "clock changed for: $a" || ok "refused: $a"; }
done
rm -f "$T/build"; o=$(run 2026-11-10 14:30) && bad "accepted without a build date" || ok "no build date: refused"
o=$("$T/sc" 2026-11-10 14:30 2>&1) && bad "runs without root" || ok "refuses to run without root"
exit $fail
