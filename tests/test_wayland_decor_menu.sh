#!/bin/sh
# Prestium 2.1: one compositor title bar (minimise, maximise, close) for every
# window, outside the client surface. Apps that used to draw their own bar
# (Galculator, LibreWolf) are told not to, so labwc does not paint a second bar
# over the top. The Applications button opens the root menu under itself.
set -e
R=$(cd "$(dirname "$0")/.." && pwd)/config/includes.chroot
RC=$R/etc/xdg/labwc/rc.xml
grep -q '<core>' "$RC" && grep -q '<decoration>server</decoration>' "$RC" \
  || { echo "FAIL: rc.xml does not default to server-side decorations"; exit 1; }
! grep -q 'serverDecoration="no"' "$RC" \
  || { echo "FAIL: rc.xml still disables server decorations"; exit 1; }
# forcing a frame on an app that also draws its own painted the bar over the window
! grep -q 'identifier="Galculator"' "$RC" && ! grep -q 'identifier="librewolf"' "$RC" \
  && ! grep -q 'identifier="PrestiumLocalFirefox"' "$RC" \
  || { echo "FAIL: rc.xml still forces a frame onto an app that draws its own bar"; exit 1; }
grep -q 'identifier="\*zenity\*"' "$RC" \
  || { echo "FAIL: zenity has no frame"; exit 1; }
! grep -q 'prestium-apps-menu' "$RC" \
  || { echo "FAIL: rc.xml still mentions prestium-apps-menu"; exit 1; }
! grep -q 'sandboxEngine=' "$RC" || { echo "FAIL: rc.xml still forces a frame by security context"; exit 1; }
grep -q '<titleLayout>icon,label:minimize,maximize,close</titleLayout>' "$RC" \
  || { echo "FAIL: rc.xml titlebar has no minimise/maximise/close"; exit 1; }
grep -q 'GTK_CSD=0' "$R/usr/local/bin/prestium-session" \
  && grep -q 'MOZ_GTK_TITLEBAR_DECORATION=system' "$R/usr/local/bin/prestium-session" \
  || { echo "FAIL: session still lets GTK or Firefox draw their own title bar"; exit 1; }
# Super+Space opens the root menu under Applications (the panel button presses it through the broker)
python3 - "$RC" <<'PY'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
rules = [(k.get("identifier"), k.get("serverDecoration")) for k in root.iter() if k.tag.endswith("windowRule")]
assert rules == [("*zenity*", "yes")], rules
kb = [k for k in root.iter() if k.tag.endswith("keybind") and k.get("key") == "W-space"]
assert len(kb) == 1, "one W-space keybind"
a = [x for x in kb[0] if x.tag.endswith("action")][0]
assert a.get("name") == "ShowMenu" and a.get("menu") == "root-menu"
txt = {c.tag.split("}")[-1]: c for c in a.iter()}
assert txt["atCursor"].text == "no"
assert txt["x"].text == "0" and txt["y"].text == "0", "menu top-left under Applications (usable area starts under the top bar)"
PY
W=$R/etc/xdg/waybar/config.jsonc
sed 's#//.*##' "$W" | python3 -c '
import json, sys
c = json.load(sys.stdin)
assert isinstance(c, list) and [b["name"] for b in c] == ["prestium-top", "prestium-bottom"], c
top = c[0]
assert top["modules-left"][0] == "custom/applications", top["modules-left"]
m = top["custom/applications"]
assert m["on-click"] == "/usr/local/bin/prestium-wl menu", m
'
grep -qx wtype "$R/../package-lists/prestium-2.0.list.chroot"
# Firefox-based browsers: no tabs in the title bar (the compositor draws the frame)
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-tor-browser/user.js"
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-localfox/user.js"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["policies"]["Preferences"]["browser.tabs.inTitlebar"]["Value"] == 0' "$R/usr/share/librewolf/distribution/policies.json"
echo "wayland decorations + Applications menu: OK"
