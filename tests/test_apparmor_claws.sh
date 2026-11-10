#!/bin/bash
# Prestium 2.0 r12: the Claws Mail profile compiles with the shipped abstractions, is enforced by
# the build hook, and keeps Claws out of sudo, Prestium helpers, other apps' data and ~/.gnupg.
set -u; T=$(cd "$(dirname "$0")/.." && pwd); A=$T/config/includes.chroot/etc/apparmor.d
P=$A/usr.bin.claws-mail; H=$T/config/hooks/live/0600-prestium-apparmor.hook.chroot; fail=0
ok(){ echo "OK $1"; }; no(){ echo "FAIL $1"; fail=1; }
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$A"/. "$W"/
if command -v apparmor_parser >/dev/null; then
  apparmor_parser -QK -b "$W" "$W/usr.bin.claws-mail" 2>/dev/null && ok "profile compiles" || no "profile compiles"
  E=$(apparmor_parser -p -b "$W" "$W/usr.bin.claws-mail" 2>/dev/null)
else echo "SKIP apparmor_parser missing"; E=$(cat "$P"); fi
grep -q '^profile claws-mail /usr/bin/claws-mail {' "$P" && ok "attaches to /usr/bin/claws-mail" || no attach
grep -q 'flags=' "$P" && no "has flags (complain?)" || ok "no complain flag"
grep -q 'include <abstractions/prestium-app-base>' "$P" && ok "shared app rules" || no "shared app rules"
grep -q 'usr.bin.claws-mail' <(sed -n '/^for p in/,/do$/p' "$H" | head -4) && ok "hook enforces it" || no "hook enforces it"
[ "$(grep -c 'usr.bin.claws-mail' "$H")" -ge 2 ] && ok "hook checks no-admin" || no "hook checks no-admin"
grep -q 'apparmor.d/usr.bin.claws-mail' "$T/config/includes.chroot/usr/share/prestium/build/perms.txt" && ok perms || no perms
for d in 'deny /{,usr/}{,s}bin/sudo' 'deny /usr/local/sbin/\*\*' 'deny /run/tor/\*\*' 'deny @{run}/user/\[0-9\]\*/wayland' 'deny @{HOME}/.librewolf' 'deny @{HOME}/\*\*.kdbx'; do
  grep -q -- "$d" <<<"$E" && ok "expanded: $d" || no "expanded: $d"; done
# outside the child profile, nothing grants ~/.gnupg, all of $HOME or Ux/ix to a general path
parent=$(sed '/^  profile gpg {/,/^  }/d' "$P")
grep -q '\.gnupg' <<<"$(grep -v '^\s*#' <<<"$parent")" && no "parent touches ~/.gnupg" || ok "parent has no ~/.gnupg rule"
grep -Eq '@\{HOME\}/\*\*|@\{HOME\}/ +[rw]*w' <<<"$parent" && no "broad home access" || ok "no broad home access"
grep -Eq '^\s*/\*\*|/usr/bin/\*\* +[A-Za-z]*x|/usr/local/bin/\*\*' <<<"$parent" && no "broad exec" || ok "no broad exec"
# 2.1 (review): no Ux at all; the browser launchers and pinentry run in their own profiles
grep -Eq '\bUx,' "$P" && no "Ux in the profile" || ok "no Ux"
grep -q '^  /usr/local/bin/tor-browser Px -> prestium_tor_browser_launcher,' "$P" && grep -q '^  /usr/local/bin/librewolf-i2p Px -> prestium_librewolf_launcher,' "$P" && ok "browsers: Px into the launcher profiles" || no "browser launchers not Px"
grep -q '^    /usr/bin/pinentry\* Px -> prestium_pinentry,' "$P" && ok "pinentry: Px into prestium_pinentry" || no "pinentry not Px"
exit $fail
