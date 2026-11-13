#!/bin/bash
# Prestium 2.1: AppArmor is loaded at boot. apparmor.service is enabled and not skipped on the live
# overlay; the whole profile set compiles as the service loads it; no Debian profile attaches to a
# program a Prestium profile confines (an equal match makes the kernel attach neither, so the program ran
# unconfined: Debian's LibreOffice profiles did that). Needs apparmor_parser for the profile part
# (PATH may need /usr/sbin); AA_SYSTEM_DIR: Debian's /etc/apparmor.d (default); AA_UNIT: Debian's
# apparmor.service (default /usr/lib/systemd/system/apparmor.service, skipped when missing).
set -u
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }; skip(){ echo "SKIP $*"; }
D=$I/etc/systemd/system/apparmor.service.d/prestium-live.conf
W=$I/usr/share/prestium/build/systemd-wants.txt

echo "== apparmor.service runs at boot"
grep -qx '/etc/systemd/system/sysinit.target.wants/apparmor.service /usr/lib/systemd/system/apparmor.service' "$W" \
  && ok "enabled (sysinit.target.wants)" || bad "apparmor.service not in systemd-wants.txt"
python3 - "$D" <<'PY' && ok "drop-in resets Debian's live-overlay conditions" || bad "drop-in does not reset ConditionPathExists"
import sys
sec, reset = None, False
for l in open(sys.argv[1]):
    l = l.strip()
    if l.startswith('['): sec = l
    elif sec == '[Unit]' and l == 'ConditionPathExists=': reset = True
    elif sec == '[Unit]' and l.startswith('Condition') and reset: sys.exit(1)   # a condition added back
sys.exit(0 if reset else 1)
PY
if grep -rnE 'apparmor\.service.*(/dev/null|mask)|systemctl (mask|disable).*apparmor' "$R/config/hooks" "$I/etc/systemd" 2>/dev/null \
   || find "$I/etc/systemd" -name apparmor.service -lname /dev/null 2>/dev/null | grep -q .; then bad "apparmor.service masked or disabled somewhere"
else ok "not masked or disabled by a hook"; fi
U=${AA_UNIT:-/usr/lib/systemd/system/apparmor.service}
if [ -f "$U" ]; then
  python3 - "$U" "$D" <<'PY' && ok "Debian unit + drop-in: no condition left that is false on the live system" || bad "a condition still skips apparmor.service on the live system"
import sys
conds = []
for f in sys.argv[1:]:
    sec = None
    for l in open(f):
        l = l.strip()
        if l.startswith('['): sec = l; continue
        if sec != '[Unit]' or not l.startswith('Condition') or '=' not in l: continue
        k, v = l.split('=', 1)
        if v == '': conds = []          # systemd: an empty Condition*= resets all conditions
        else: conds.append((k, v))
live = [c for c in conds if c[0] == 'ConditionPathExists' and c[1].startswith('!/run/live')]
print("   conditions left:", conds or "none")
sys.exit(1 if live else 0)
PY
else skip "no $U (apparmor not installed): unit merge not checked"; fi

echo "== the profile set as apparmor.service loads it"
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin
if ! command -v apparmor_parser >/dev/null; then skip "apparmor_parser missing"; exit $fail; fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mk() { # a tree as the image has it before hook 0600: Debian's profiles, the fixture (libreoffice-common), Prestium's
  rm -rf "$T/aa"; mkdir -p "$T/aa"; cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$T/aa"/ 2>/dev/null
  rm -f "$T/aa/loupe" "$T/aa/firefox"
  cp "$R"/tests/fixtures/apparmor-debian/* "$T/aa"/; cp -r "$I/etc/apparmor.d"/. "$T/aa"/
  # the empty local/ files dh_apparmor's postinst creates
  grep -ho 'include <local/[^>]*>' "$T"/aa/* 2>/dev/null | sed 's/include <\(.*\)>/\1/' | sort -u | while read -r l; do
    mkdir -p "$T/aa/$(dirname "$l")"; [ -e "$T/aa/$l" ] || : > "$T/aa/$l"; done
}
OURS=$(sed -n '/aa-attach-check.py \/etc\/apparmor.d/,/|| {/p' "$H" | tr -d '\\' | tr ' \t' '\n\n' \
  | grep -E '^(usr|opt|prestium|torbrowser)\.' | sort -u | tr '\n' ' ')
[ "$(echo "$OURS" | wc -w)" -ge 25 ] && ok "hook 0600 runs the check on $(echo "$OURS" | wc -w) Prestium profiles" || bad "hook 0600 does not run aa-attach-check.py"
CHK=$I/usr/share/prestium/build/aa-attach-check.py
mk
# shellcheck disable=SC2086
out=$(python3 -I "$CHK" "$T/aa" $OURS 2>&1); rc=$?
[ $rc -ne 0 ] && echo "$out" | grep -q 'soffice.bin: Prestium profile libreoffice' && echo "$out" | grep -q 'oosplash: Prestium profile libreoffice' \
  && ok "check finds the LibreOffice conflict (without hook 0600's removals)" || { bad "check misses the LibreOffice conflict"; echo "$out"; }
# hook 0600's removals, applied to the tree
grep -E '^rm -f /etc/apparmor.d/' "$H" | sed 's#^rm -f ##' | tr ' ' '\n' | sed -n 's#^/etc/apparmor.d/##p' | while read -r f; do rm -f "$T/aa/$f"; done
[ ! -e "$T/aa/usr.lib.libreoffice.program.soffice.bin" ] && [ ! -e "$T/aa/usr.lib.libreoffice.program.oosplash" ] \
  && [ -e "$T/aa/usr.lib.libreoffice.program.xpdfimport" ] && ok "hook 0600 removes Debian's oosplash and soffice.bin profiles only" || bad "hook 0600 removals"
# shellcheck disable=SC2086
out=$(python3 -I "$CHK" "$T/aa" $OURS 2>&1) && ok "after hook 0600: ${out#P: }" || { bad "profile set after hook 0600"; echo "$out"; }
# a profile that doesn't compile is reported (apparmor.service would fail)
printf 'profile broken /usr/bin/prestium-broken {\n  /etc/** rw\n}\n' > "$T/aa/zz-broken"
# shellcheck disable=SC2086
python3 -I "$CHK" "$T/aa" $OURS 2>&1 | grep -q '^E: zz-broken does not compile' && ok "a profile that does not compile fails the check" || bad "broken profile not reported"
exit $fail
