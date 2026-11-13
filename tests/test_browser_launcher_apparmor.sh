#!/bin/bash
# 2.1 (review of the security audit): Claws Mail, Gajim and Pidgin start the browser launchers with
# "Px" into named profiles (not "Ux"), and Claws Mail's pinentry runs in its own profile. The launcher
# profiles may write only their own browser's directories, so a crafted HOME or a symlink planted in
# a browser profile cannot make the launcher overwrite another file before the sandbox starts.
# Compiles the profiles when apparmor_parser is present (AA_SYSTEM_DIR: Debian's /etc/apparmor.d).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); A=$R/config/includes.chroot/etc/apparmor.d; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
L=$A/prestium.browser-launcher; LA=$A/abstractions/prestium-browser-launcher; LB=$A/abstractions/prestium-browser-launcher-bwrap; PE=$A/prestium.pinentry
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
grep -qx 'profile prestium_pinentry /usr/bin/pinentry{,-gnome3,-gtk2,-gtk-2,-curses,-x11} {' "$PE" && ok "prestium_pinentry: attached to the pinentry programs" || bad "pinentry header"
for a in usr.bin.claws-mail usr.bin.gajim usr.bin.pidgin; do
  grep -Eq '\bUx,' "$A/$a" && bad "$a still has Ux" || ok "$a: no Ux"
  grep -q '/usr/local/bin/tor-browser Px -> prestium_tor_browser_launcher,' "$A/$a" && ok "$a: tor-browser Px" || bad "$a: tor-browser not Px"
done
grep -q '/usr/local/bin/librewolf-i2p Px -> prestium_librewolf_launcher,' "$A/usr.bin.claws-mail" && ok "claws: librewolf-i2p Px" || bad "claws librewolf-i2p"
# every write rule of the two launcher profiles (top level, child excluded) is a browser directory
wr=$( { cat "$LA"; sed -n '/^profile prestium_/,/^}/p' "$L" | sed '/^  profile bwrap/,/^  }/d'; } \
  | grep -v '^\s*#' | grep -v '^\s*deny' | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -v -- '->' )
odd=$(grep -vE '@\{HOME\}/\.tor-browser/|"@\{HOME\}/Tor Browser/|@\{HOME\}/\.librewolf/|"@\{HOME\}/I2P Browser/|@\{HOME\}/Downloads/|@\{run\}/user/\[0-9\]\*/prestium-sandbox/' <<<"$wr")
[ -n "$wr" ] && [ -z "$odd" ] && ok "launchers write only browser directories ($(grep -c . <<<"$wr") rules)" || bad "launcher write rules: $odd"
t=$(sed -n '/^profile prestium_tor_browser_launcher/,/^}/p' "$L" | grep -v '^\s*#\|deny'); l=$(sed -n '/^profile prestium_librewolf_launcher/,/^}/p' "$L" | grep -v '^\s*#\|deny')
# the bubblewrap children (one per launcher) and their shared rules: no browser directory in common
grep -v '^\s*#\|deny' "$LB" | grep -Eq 'tor-browser|Tor Browser|librewolf|I2P Browser|Downloads' && bad "shared bwrap rules name a browser directory" || ok "shared bwrap rules: no browser directory"
[ "$(grep -c '^  profile bwrap flags=(attach_disconnected,mediate_deleted) {' "$L")" = 2 ] && ok "each launcher has its own bwrap child" || bad "bwrap children"
grep -q 'librewolf' <<<"$t" && bad "Tor Browser launcher may touch LibreWolf" || ok "Tor Browser launcher: no LibreWolf paths"
grep -q 'tor-browser/\|Tor Browser' <<<"$(grep ' rw,' <<<"$l")" && bad "LibreWolf launcher may write Tor Browser" || ok "LibreWolf launcher: no Tor Browser writes"
grep -Eq '^\s*(owner\s+)?(/\*\*|@\{HOME\}/\*\*)\s+[a-z]*w' "$LA" "$L" && bad "broad write rule" || ok "no broad write rule"
grep -q 'deny /usr/local/sbin/\*\* mrwx' "$LA" && grep -q 'deny /run/tor/\*\* rw' "$LA" && ok "launchers: no sudo, helpers, Tor control" || bad "launcher denies"
grep -q '/usr/bin/bwrap mrCx -> bwrap,' "$LA" && ok "bubblewrap in a child profile" || bad "bwrap transition"
grep -q 'firefox.real Px -> torbrowser_firefox' <<<"$t" && grep -q 'librewolf{,-bin} Px -> librewolf' <<<"$l" && ok "browsers keep their own profiles inside" || bad "browser transitions"
# pinentry: no writes except the terminal, no exec, no network but unix
pw=$(grep -v '^\s*#\|deny' "$PE" | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -vE '^\s*(/dev/(tty|pts/\*)|@\{run\}/prestium-wl/\[0-9\]\*/apps) rw,')
[ -z "$pw" ] && ok "pinentry: writes only its terminal and the apps Wayland socket" || bad "pinentry writes: $pw"
grep -Eq '\s[a-zA-Z]*[iPpCcUu]x[a-zA-Z]*(\s*->\s*\S+)?,\s*$' <<<"$(grep -v '^\s*#' "$PE")" && bad "pinentry may run programs" || ok "pinentry: runs nothing"
grep -v '^\s*#' "$PE" | grep -v deny | grep -q 'network inet' && bad "pinentry has network" || ok "pinentry: no network rule of its own"
grep -q 'abstractions/nameservice>' "$PE" && bad "pinentry includes nameservice (inet rules)" || ok "pinentry: nameservice-strict"
grep -q '^  deny @{HOME}/\*\* x,' "$PE" && grep -q '^  deny /tmp/\*\* x,' "$PE" && grep -q '^  deny network inet,' "$PE" && grep -q '^  deny network inet6,' "$PE" && ok "pinentry: inet denied" || bad "pinentry inet deny"
if command -v apparmor_parser >/dev/null; then
  ex=$(apparmor_parser -p -b "$W" "$W/prestium.pinentry" 2>/dev/null | grep -v '^\s*#' | grep -Ev '^\s*deny' | grep -E '^\s*network (inet|inet6|netlink)')
  [ -z "$ex" ] && ok "pinentry, expanded: no inet/netlink allow" || bad "pinentry expanded network: $ex"
  exl=$(apparmor_parser -p -b "$W" "$W/prestium.browser-launcher" 2>/dev/null)
  tb=$(awk '/^profile prestium_tor_browser_launcher/{f=1} /^profile prestium_librewolf_launcher/{f=0} f' <<<"$exl" | grep -v '^\s*#' | grep -Ev '^\s*deny' | grep -E 'librewolf/.*w' )
  [ -z "$tb" ] && ok "Tor launcher and its child, expanded: no LibreWolf writes" || bad "Tor child LibreWolf: $tb"
  lw=$(awk '/^profile prestium_librewolf_launcher/{f=1} f' <<<"$exl" | grep -v '^\s*#' | grep -Ev '^\s*deny' | grep -E '(tor-browser|Tor Browser)/.*w' )
  [ -z "$lw" ] && ok "LibreWolf launcher and its child, expanded: no Tor Browser writes" || bad "LibreWolf child Tor Browser: $lw"
  # pinentry, expanded: every exec rule the abstractions bring in falls under one of its x denies
  pex=$(apparmor_parser -p -b "$W" "$W/prestium.pinentry" 2>/dev/null | grep -v '^\s*#' | grep -Ev '^\s*deny' \
    | grep -E '\s[a-z]*[iPpCcUu]x[a-z]*(\s*->\s*\S+)?,\s*$' | grep -vE '^\s*(owner\s+)?(@\{HOME\}|@\{HOMEDIRS\}|/tmp|/var/tmp)/')
  [ -z "$pex" ] && ok "pinentry, expanded: no exec outside its x denies" || bad "pinentry exec: $pex"
fi
for p in prestium.browser-launcher prestium.pinentry; do
  grep -q "$p" "$H" && ok "hook enforces $p" || bad "hook: $p"
  grep -q "/etc/apparmor.d/$p" "$PM" && ok "perms: $p" || bad "perms: $p"
done
exit $fail
