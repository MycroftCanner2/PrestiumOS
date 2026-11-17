#!/bin/sh
# Prestium 2.1: dual bar — root menu on the Applications button,
# icon-only window-list taskbar on the bottom bar.
set -eu
R=$(dirname "$0")/../config/includes.chroot
W=$R/etc/xdg/waybar/config.jsonc
B=$R/usr/local/sbin/prestium-wl-broker
grep -q '\"on-click-release\": \"/usr/local/bin/prestium-wl menu\"' "$W"
! grep -q '\"on-click\": \"/usr/local/bin/prestium-wl menu\"' "$W"
grep -q '\"format\": \"{icon}\",' "$W"
grep -q '\"icon-size\": 24,' "$W"
grep -q '\[\"wtype\", \"-M\", \"logo\", \"-k\", \"space\", \"-m\", \"logo\"\]' "$B"
grep -q 'if cmd == \"menu\":' "$B"
grep -q '\"menu\",' "$R/usr/local/bin/prestium-wl"
D=$R/usr/share/applications/prestium-localfox.desktop
grep -q '^StartupWMClass=PrestiumLocalFirefox$' "$D"; grep -q '^Icon=prestium-localfox$' "$D"
grep -q -- "--name prestium-localfox --class PrestiumLocalFirefox" "$R/usr/local/bin/prestium-localfox"
grep -q 'apps/prestium-localfox.png' "$(dirname "$0")/../config/hooks/live/0200-prestium-thirdparty.hook.chroot"
echo "panel root menu + icon-only taskbar: OK"
