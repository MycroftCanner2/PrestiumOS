#!/bin/bash
# 2.1 (security audit): the session password (screen lock, admin prompts) has at least 8 characters,
# and each wrong password at the lock screen costs at least 4 seconds (pam_faildelay), no lockout.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
sed -e 's#^cur=.*#cur=""#' -e "s#chpasswd#cat > $T/set#" "$I/usr/local/sbin/prestium-session-password" > "$T/sp"
for p in 'short' '1234567' ''; do
  printf '%s\n' "$p" | sh "$T/sp" set >/dev/null 2>&1 && bad "accepted: '$p'" || ok "refused: '${p}' (${#p} chars)"; done
printf '%s\n' 'correct horse' | sh "$T/sp" set >/dev/null 2>&1 && grep -qx 'user:correct horse' "$T/set" && ok "8+ characters accepted" || bad "long password refused"
printf '%s\n' 'abc:defgh' | sh "$T/sp" set >/dev/null 2>&1 && bad "':' accepted" || ok "':' refused"
L=$I/usr/local/bin/prestium-lock-screen
grep -q 'at least 8 characters' "$L" && grep -q '"${#p1}" -lt 8' "$L" && ok "lock dialog says and checks the minimum" || bad "lock dialog"
P=$I/etc/pam.d/swaylock
grep -qE '^auth\s+optional\s+pam_faildelay\.so delay=4000000$' "$P" && ok "pam: 4 s per wrong password" || bad "pam faildelay"
grep -qE '^auth\s+include\s+login$' "$P" && ok "pam: then the login stack" || bad "pam include login"
grep -q 'faillock\|pam_tally' "$P" && bad "pam: lockout module (would shut out the only user)" || ok "pam: no lockout"
grep -qx '0644 root root /etc/pam.d/swaylock' "$I/usr/share/prestium/build/perms.txt" && ok "perms: pam file" || bad "perms pam"
exit $fail
