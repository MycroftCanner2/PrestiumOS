#!/bin/bash
# 2.1 (security audit): The Lounge require()s config.js and every package (autologin, theme) at start,
# so the thelounge uid must not be able to rewrite them: root-owned (group thelounge, read-only),
# ReadOnlyPaths= in the unit, and denied in its AppArmor profile. i2pd and Tor (remote input) get
# ProtectProc=invisible, so they can't read other processes' command lines.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
P=$I/usr/share/prestium/build/perms.txt
grep -E ' /var/lib/thelounge/(config\.js|packages/)' "$P" > /tmp/tl.perms.$$
n=0; while read -r mode own grp path; do n=$((n+1))
  case $path in */) want=0750;; *) want=0640;; esac
  [ "$mode $own $grp" = "$want root thelounge" ] || bad "perms: $mode $own $grp $path"
done < /tmp/tl.perms.$$; rm -f /tmp/tl.perms.$$
[ "$n" -ge 54 ] && ok "perms: config.js and $((n-1)) package entries root:thelounge, read-only" || bad "perms: only $n entries"
# every shipped file under packages/ has an entry
( cd "$I" && find var/lib/thelounge/packages -type f ) | while read -r f; do
  grep -q " /$f$" "$P" || echo "FAIL perms.txt misses /$f"; done | grep . && fail=1 || ok "every package file listed in perms.txt"
grep -qx 'ReadOnlyPaths=/var/lib/thelounge/config.js /var/lib/thelounge/packages' "$I/etc/systemd/system/thelounge.service" \
  && ok "unit: config.js and packages read-only" || bad "unit: ReadOnlyPaths"
A=$I/etc/apparmor.d/prestium.thelounge
grep -qx '  deny /var/lib/thelounge/config.js wl,' "$A" && grep -qx '  deny /var/lib/thelounge/packages{,/\*\*} wl,' "$A" \
  && ok "AppArmor: writes to config.js and packages denied" || bad "AppArmor deny rules"
grep -qx 'ProtectProc=invisible' "$I/etc/systemd/system/i2pd.service.d/10-hardening.conf" && ok "i2pd: ProtectProc=invisible" || bad "i2pd ProtectProc"
grep -qx 'ProtectProc=invisible' "$I/etc/systemd/system/tor@default.service.d/prestium-protectproc.conf" && ok "Tor: ProtectProc=invisible" || bad "Tor ProtectProc"
grep -q '/etc/systemd/system/tor@default.service.d/prestium-protectproc.conf$' "$P" && ok "perms: Tor drop-in" || bad "perms: Tor drop-in"
exit $fail
