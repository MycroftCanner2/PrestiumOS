#!/bin/bash
# Prestium 2.1 (dialog look): zenity dialogs (Power, Unlock Volume, confirmations) show one title (labwc's
# title bar) over a flat content area: no inner rounded card, no outline, no second bold title.
# Verified under labwc with grim; this checks the pieces stay wired together.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok() { echo "OK   $*"; }; bad() { echo "FAIL $*"; fail=1; }
Z=$I/usr/local/bin/zenity D=$I/usr/share/prestium/dialog-style/gtk-4.0 B=$I/usr/share/prestium/broker-style/gtk-4.0
P=$I/usr/share/prestium/build/perms.txt
[ -x "$Z" ] && sh -n "$Z" && ok "zenity wrapper is an executable shell script" || bad "zenity wrapper"
grep -qxF '0755 root root /usr/local/bin/zenity' "$P" && ok "perms: wrapper" || bad "perms: wrapper"
for f in dialog-style/gtk-4.0/gtk.css dialog-style/gtk-4.0/settings.ini broker-style/gtk-4.0/gtk.css; do
  grep -qxF "0644 root root /usr/share/prestium/$f" "$P" && ok "perms: $f" || bad "perms: $f"; done
cmp -s "$D/gtk.css" "$B/gtk.css" && ok "broker dialogs use the same rules" || bad "dialog-style and broker-style gtk.css differ"
c=$(sed 's#/\*.*\*/##g' "$D/gtk.css" | tr -d '\n' | sed 's#/\*[^*]*\*/##g')
grep -q 'window.messagedialog { border-radius: 0; box-shadow: none; outline: none; }' <<<"$c" && ok "flat content, no outline" || bad "card corners/outline rule missing"
grep -q 'heading-bin label { color: transparent; font-size: 1px' <<<"$c" && ok "title shown once (heading hidden)" || bad "duplicate heading rule missing"
grep -q '\.child frame { border: none' <<<"$c" && ok "--forms: no inner bordered box" || bad "forms frame rule missing"
grep -Eq '(^|})\s*[a-z]' <<<"$(sed 's/window\.messagedialog[^{]*{[^}]*}//g' <<<"$c")" && bad "a rule outside window.messagedialog (would restyle other dialogs)" || ok "every rule is scoped to window.messagedialog"
grep -q 'identifier="\*zenity\*" serverDecoration="yes"' "$I/etc/xdg/labwc/rc.xml" && ok "labwc: zenity keeps its title bar (min/max/close)" || bad "labwc zenity rule lost"
# behaviour, against a stub zenity
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
printf '#!/bin/sh\necho "XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-}"\n' > "$W/zenity"; chmod +x "$W/zenity"
sed "s#/usr/bin/zenity#$W/zenity#g" "$Z" > "$W/wrap"
r=$(env -u XDG_CONFIG_HOME sh "$W/wrap" --list --title Power); [ "$r" = "XDG_CONFIG_HOME=/usr/share/prestium/dialog-style" ] && ok "dialogs load dialog-style" || bad "dialogs: $r"
r=$(XDG_CONFIG_HOME=/home/user/.config sh "$W/wrap" --question); [ "$r" = "XDG_CONFIG_HOME=/usr/share/prestium/dialog-style" ] && ok "dialogs ignore the user's config dir" || bad "user config: $r"
r=$(XDG_CONFIG_HOME=/home/user/.config sh "$W/wrap" --file-selection --title Keyfile); [ "$r" = "XDG_CONFIG_HOME=/home/user/.config" ] && ok "file chooser keeps the user's settings (bookmarks)" || bad "file chooser: $r"
r=$(XDG_CONFIG_HOME=/usr/share/prestium/broker-style sh "$W/wrap" --forms); [ "$r" = "XDG_CONFIG_HOME=/usr/share/prestium/broker-style" ] && ok "broker's style directory kept" || bad "broker: $r"
grep -q '"PATH": "/usr/local/bin:' "$I/usr/local/sbin/prestium-wl-broker" && ok "broker finds the wrapper first" || bad "broker PATH"
exit $fail
