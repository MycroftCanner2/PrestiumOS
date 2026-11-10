#!/bin/bash
# 2.1 (review of the security audit): Claws Mail, Gajim and Pidgin start the browser launchers with
# "Px" into named profiles (not "Ux"), and Claws Mail's pinentry runs in its own profile. The launcher
# profiles may write only their own browser's directories, so a crafted HOME or a symlink planted in
# a browser profile cannot make the launcher overwrite another file before the sandbox starts.
# Compiles the profiles when apparmor_parser is present (AA_SYSTEM_DIR: Debian's /etc/apparmor.d).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); A=$R/config/includes.chroot/etc/apparmor.d; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
L=$A/prestium.browser-launcher; LA=$A/abstractions/prestium-browser-launcher; PE=$A/prestium.pinentry
H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot; PM=$R/config/includes.chroot/usr/share/prestium/build/perms.txt
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$A"/. "$W"/
if command -v apparmor_parser >/dev/null; then
  for p in prestium.browser-launcher prestium.pinentry usr.bin.claws-mail usr.bin.gajim usr.bin.pidgin; do
    apparmor_parser -QK -b "$W" "$W/$p" >/dev/null 2>"$W/.err" && ok "$p compiles" || { bad "$p: $(head -2 "$W/.err")"; }
  done
else echo "SKIP apparmor_parser missing (compile)"; fi
for n in prestium_tor_browser_launcher prestium_librewolf_launcher; do
  grep -qx "profile $n {" "$L" && ok "$n: named, no attachment (the menu's launch is unchanged)" || bad "$n header"; done
grep -qx 'profile prestium_pinentry {' "$PE" && ok "prestium_pinentry: named" || bad "pinentry header"
for a in usr.bin.claws-mail usr.bin.gajim usr.bin.pidgin; do
  grep -Eq '\bUx,' "$A/$a" && bad "$a still has Ux" || ok "$a: no Ux"
  grep -q '/usr/local/bin/tor-browser Px -> prestium_tor_browser_launcher,' "$A/$a" && ok "$a: tor-browser Px" || bad "$a: tor-browser not Px"
done
grep -q '/usr/local/bin/librewolf-i2p Px -> prestium_librewolf_launcher,' "$A/usr.bin.claws-mail" && ok "claws: librewolf-i2p Px" || bad "claws librewolf-i2p"
# every write rule of the two launcher profiles (top level, child excluded) is a browser directory
wr=$( { sed '/^  profile bwrap/,/^  }/d' "$LA"; sed -n '/^profile prestium_/,/^}/p' "$L"; } \
  | grep -v '^\s*#' | grep -v '^\s*deny' | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -v -- '->' )
odd=$(grep -vE '@\{HOME\}/\.tor-browser/|"@\{HOME\}/Tor Browser/|@\{HOME\}/\.librewolf/|@\{HOME\}/Downloads/|@\{run\}/user/\[0-9\]\*/prestium-sandbox/' <<<"$wr")
[ -n "$wr" ] && [ -z "$odd" ] && ok "launchers write only browser directories ($(grep -c . <<<"$wr") rules)" || bad "launcher write rules: $odd"
t=$(sed -n '/^profile prestium_tor_browser_launcher/,/^}/p' "$L" | grep -v '^\s*#\|deny'); l=$(sed -n '/^profile prestium_librewolf_launcher/,/^}/p' "$L" | grep -v '^\s*#\|deny')
grep -q 'librewolf' <<<"$t" && bad "Tor Browser launcher may touch LibreWolf" || ok "Tor Browser launcher: no LibreWolf paths"
grep -q 'tor-browser/\|Tor Browser' <<<"$(grep ' rw,' <<<"$l")" && bad "LibreWolf launcher may write Tor Browser" || ok "LibreWolf launcher: no Tor Browser writes"
grep -Eq '^\s*(owner\s+)?(/\*\*|@\{HOME\}/\*\*)\s+[a-z]*w' "$LA" "$L" && bad "broad write rule" || ok "no broad write rule"
grep -q 'deny /usr/local/sbin/\*\* mrwx' "$LA" && grep -q 'deny /run/tor/\*\* rw' "$LA" && ok "launchers: no sudo, helpers, Tor control" || bad "launcher denies"
grep -q '/usr/bin/bwrap mrCx -> bwrap,' "$LA" && ok "bubblewrap in a child profile" || bad "bwrap transition"
grep -q 'firefox.real Px -> torbrowser_firefox' "$LA" && grep -q 'librewolf{,-bin} Px -> librewolf' "$LA" && ok "browsers keep their own profiles inside" || bad "browser transitions"
# pinentry: no writes except the terminal, no exec, no network but unix
pw=$(grep -v '^\s*#\|deny' "$PE" | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -vE '^\s*/dev/(tty|pts/\*) rw,')
[ -z "$pw" ] && ok "pinentry: writes only its terminal" || bad "pinentry writes: $pw"
grep -Eq '\s[a-zA-Z]*[iPpCcUu]x[a-zA-Z]*(\s*->\s*\S+)?,\s*$' <<<"$(grep -v '^\s*#' "$PE")" && bad "pinentry may run programs" || ok "pinentry: runs nothing"
grep -q 'network inet' "$PE" && bad "pinentry has network" || ok "pinentry: no network"
for p in prestium.browser-launcher prestium.pinentry; do
  grep -q "$p" "$H" && ok "hook enforces $p" || bad "hook: $p"
  grep -q "/etc/apparmor.d/$p" "$PM" && ok "perms: $p" || bad "perms: $p"
done
exit $fail
