#!/bin/sh
# Prestium 2.0 r19: window frames for restricted-socket apps, and the panel's Menu button.
set -e
R=$(cd "$(dirname "$0")/.." && pwd)/config/includes.chroot
RC=$R/etc/xdg/labwc/rc.xml
BR=$R/usr/local/sbin/prestium-wl-broker
# the engine name labwc matches must be the one the broker registers
eng=$(sed -n 's/.*c.send(ctx, 1, wstring("\([^"]*\)")).*/\1/p' "$BR")
[ -n "$eng" ]
grep -q "<windowRule sandboxEngine=\"$eng\" serverDecoration=\"yes\" />" "$RC" || { echo "FAIL: rc.xml rule does not match broker engine $eng"; exit 1; }
# Super+Space opens the root menu, and the panel button sends exactly that
grep -q '<keybind key="W-space"><action name="ShowMenu" menu="root-menu" /></keybind>' "$RC"
W=$R/etc/xdg/waybar/config.jsonc
sed 's#//.*##' "$W" | python3 -c '
import json, sys
c = json.load(sys.stdin)
assert c["modules-left"][0] == "custom/menu", c["modules-left"]
m = c["custom/menu"]
assert m["on-click"] == "sleep 0.3; exec /usr/local/bin/prestium-wl menu", m
'
grep -qx wtype "$R/../package-lists/prestium-2.0.list.chroot"
# Firefox-based browsers: no tabs in the title bar
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-tor-browser/user.js"
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-localfox/user.js"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["policies"]["Preferences"]["browser.tabs.inTitlebar"]["Value"] == 0' "$R/usr/share/librewolf/distribution/policies.json"
echo "wayland decorations + menu button: OK"
