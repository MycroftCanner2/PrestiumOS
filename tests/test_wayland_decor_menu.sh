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
python3 - "$RC" <<'PY'
import sys, xml.etree.ElementTree as ET
ns = {"l": "http://openbox.org/3.4/rc"}
root = ET.parse(sys.argv[1]).getroot()
kb = [k for k in root.iter() if k.tag.endswith("keybind") and k.get("key") == "W-space"]
assert len(kb) == 1, "one W-space keybind"
a = [x for x in kb[0] if x.tag.endswith("action")][0]
assert a.get("name") == "ShowMenu" and a.get("menu") == "root-menu"
txt = {c.tag.split("}")[-1]: c for c in a.iter()}
assert txt["atCursor"].text == "no"
assert txt["x"].text == "0" and txt["y"].text == "-34", "menu fixed above the bar"
PY
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
