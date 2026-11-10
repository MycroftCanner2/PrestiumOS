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
L=$I/usr/local/bin/prestium-lock-screen; B=$I/usr/local/sbin/prestium-wl-broker; S=$I/etc/sudoers.d/prestium-session-password
grep -q 'at least 8 characters' "$B" && grep -q 'len(p1) < 8' "$B" && ok "lock dialog (broker) says and checks the minimum" || bad "lock dialog"
# 2.1 (audit L-2): the first password is set by the broker from its own dialog, never through sudo
printf '%s\n' 'correct horse' | SUDO_USER=user SUDO_UID=1000 sh "$T/sp" set >/dev/null 2>&1 && bad "set through sudo accepted" || ok "set through sudo refused"
grep -v '^#' "$S" | grep -q 'session-password set' && bad "sudoers still allows set" || ok "sudoers: status only"
grep -q 'prestium-session-password status$' "$S" && ok "sudoers: status allowed" || bad "sudoers status"
grep -v '^\s*#' "$L" | grep -q 'session-password set' && bad "lock screen still uses sudo set" || ok "lock screen: no sudo set"
grep -q 'prestium-wl set-password' "$L" && grep -q '"set-password"' "$I/usr/local/bin/prestium-wl" && ok "lock screen asks the broker" || bad "lock screen -> broker"
grep -q 'if cmd == "set-password":' "$B" && grep -q '\[SESSION_PASSWORD, "set"\]' "$B" && ok "broker sets it as root" || bad "broker set-password"
python3 - "$B" <<'PY' && ok "broker: password dialog on the full socket (spawn), not prestium-run" || bad "broker dialog"
import re,sys
s=open(sys.argv[1]).read(); f=s[s.index("def set_password"):s.index("def lock_screen")]
sys.exit(0 if 'self.spawn(["zenity", "--forms"' in f and "prestium-run" not in f else 1)
PY
# 2.1 (review of db6601c): plain passwd isn't setuid (an empty password asks for no old one), and no
# confined app may run passwd or its relatives
grep -q 'dpkg-statoverride --update --add root root 0755 /usr/bin/passwd' "$R/config/hooks/live/0500-prestium-permissions.hook.chroot" \
  && grep -q 'still setuid' "$R/config/hooks/live/0500-prestium-permissions.hook.chroot" && ok "hook 0500: passwd not setuid, checked" || bad "passwd setuid"
grep -q 'deny /{,usr/}{,s}bin/{passwd,gpasswd,chsh,chfn,chage,expiry} mrwx,' "$I/etc/apparmor.d/abstractions/prestium-no-admin" && ok "no-admin: denies passwd" || bad "no-admin passwd"
P=$I/etc/pam.d/swaylock
grep -qE '^auth\s+optional\s+pam_faildelay\.so delay=4000000$' "$P" && ok "pam: 4 s per wrong password" || bad "pam faildelay"
grep -qE '^auth\s+include\s+login$' "$P" && ok "pam: then the login stack" || bad "pam include login"
grep -q 'faillock\|pam_tally' "$P" && bad "pam: lockout module (would shut out the only user)" || ok "pam: no lockout"
grep -qx '0644 root root /etc/pam.d/swaylock' "$I/usr/share/prestium/build/perms.txt" && ok "perms: pam file" || bad "perms pam"
exit $fail
