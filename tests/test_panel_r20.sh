#!/bin/sh
# 2.0 r20: panel Menu button delay, localfox icon, icon-only taskbar.
set -eu
R=$(dirname "$0")/../config/includes.chroot
W=$R/etc/xdg/waybar/config.jsonc
grep -q '"on-click": "sleep 0.3; exec /usr/local/bin/prestium-wl menu"' "$W"
B=$R/usr/local/sbin/prestium-wl-broker
grep -q '\["wtype", "-M", "logo", "-k", "space", "-m", "logo"\]' "$B"
grep -q 'if cmd == "menu":' "$B"
grep -q '"menu",' "$R/usr/local/bin/prestium-wl"
grep -q '"format": "{icon}",' "$W"
D=$R/usr/share/applications/prestium-localfox.desktop
grep -q '^StartupWMClass=PrestiumLocalFirefox$' "$D"; grep -q '^Icon=prestium-localfox$' "$D"
grep -q -- "--name prestium-localfox --class PrestiumLocalFirefox" "$R/usr/local/bin/prestium-localfox"
grep -q 'apps/prestium-localfox.png' "$(dirname "$0")/../config/hooks/live/0200-prestium-thirdparty.hook.chroot"
echo "panel r20: OK"
