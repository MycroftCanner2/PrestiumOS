#!/bin/bash
# 2.1 (security audit): the desktop says when the image is more than 45 days old (no in-session
# updates). Patched copy with a fake build date and a stub notify-send.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
printf '#!/bin/sh\nprintf "%%s|" "$@" > %s/note\n' "$T" > "$T/notify-send"; chmod 755 "$T/notify-send"
sed "s#^B=.*#B=$T/build#" "$I/usr/local/bin/prestium-age-notify" > "$T/an"
run(){ rm -f "$T/note"; echo "$1" > "$T/build"; PATH=$T:$PATH PRESTIUM_AGE_WAIT=0 sh "$T/an"; }
run $(( $(date -u +%s) - 50*86400 )); grep -q 'This Prestium image is 50 days old' "$T/note" 2>/dev/null && ok "50 days: notice" || bad "no notice at 50 days"
run $(( $(date -u +%s) - 10*86400 )); [ -e "$T/note" ] && bad "notice at 10 days" || ok "10 days: quiet"
run 'junk'; [ -e "$T/note" ] && bad "notice without a build date" || ok "no build date: quiet"
grep -q 'prestium-age-notify' "$I/etc/xdg/labwc/autostart" && ok "started at login" || bad "not in autostart"
grep -q 'BUILD_ID=' "$R/config/hooks/live/0400-prestium-system.hook.chroot" && ok "os-release BUILD_ID" || bad "no BUILD_ID"
exit $fail
