#!/bin/sh
# Prestium 2.1 (Tails-style): client-side decorations by default (no double titlebars
# on GTK/Firefox), with a Prestium-Adwaita server-side titlebar only for terminal,
# XWayland and Qt apps; the Applications menu button opens prestium-apps-menu.
set -e
R=$(cd "$(dirname "$0")/.." && pwd)/config/includes.chroot
RC=$R/etc/xdg/labwc/rc.xml
grep -q '<core>' "$RC" && grep -q '<decoration>client</decoration>' "$RC" \
  || { echo "FAIL: rc.xml does not default to client-side decorations"; exit 1; }
grep -q '<windowRule identifier="\*" serverDecoration="no" />' "$RC" \
  || { echo "FAIL: rc.xml has no default serverDecoration=no rule"; exit 1; }
for id in foot Audacity org.keepassxc.KeePassXC org.kde.kleopatra featherpad onionshare vlc; do
  grep -q "<windowRule identifier=\"$id\" serverDecoration=\"yes\" />" "$RC" \
    || { echo "FAIL: rc.xml gives no server-side titlebar to $id"; exit 1; }
done
# no app gets the compositor's forced frame any more (that rule drew a second titlebar)
! grep -q 'sandboxEngine=' "$RC" || { echo "FAIL: rc.xml still forces a frame by security context"; exit 1; }
# Super+Space opens the root menu, and the panel button opens the Applications dropdown
python3 - "$RC" <<'PY'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
kb = [k for k in root.iter() if k.tag.endswith("keybind") and k.get("key") == "W-space"]
assert len(kb) == 1, "one W-space keybind"
a = [x for x in kb[0] if x.tag.endswith("action")][0]
assert a.get("name") == "ShowMenu" and a.get("menu") == "root-menu"
txt = {c.tag.split("}")[-1]: c for c in a.iter()}
assert txt["atCursor"].text == "no"
assert txt["x"].text == "0" and txt["y"].text == "-1", "menu bottom edge on the bar (the usable area already ends at the bar)"
PY
W=$R/etc/xdg/waybar/config.jsonc
sed 's#//.*##' "$W" | python3 -c '
import json, sys
c = json.load(sys.stdin)
assert isinstance(c, list) and [b["name"] for b in c] == ["tails-top", "tails-bottom"], c
top = c[0]
assert top["modules-left"][0] == "custom/applications", top["modules-left"]
m = top["custom/applications"]
assert m["on-click"] == "/usr/local/bin/prestium-apps-menu", m
'
grep -qx wtype "$R/../package-lists/prestium-2.0.list.chroot"
# Firefox-based browsers: no tabs in the title bar
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-tor-browser/user.js"
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-localfox/user.js"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["policies"]["Preferences"]["browser.tabs.inTitlebar"]["Value"] == 0' "$R/usr/share/librewolf/distribution/policies.json"
echo "wayland decorations + Applications menu: OK"
