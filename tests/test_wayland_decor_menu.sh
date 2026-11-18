#!/bin/sh
# Prestium 2.1: one compositor title bar (minimise, maximise, close) for every
# window, outside the client surface. Apps that used to draw their own bar
# (Galculator, LibreWolf) are told not to, so labwc does not paint a second bar
# over the top. Header-bar apps (Evince, File Roller, Loupe) keep their own single bar with the same
# three buttons. The Applications button opens the root menu under itself.
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
# the file picker draws its own single header (no serverDecoration), it is only centred
assert rules == [("*zenity*", "yes"), ("org.prestium.FilePicker", None)], rules
kb = [k for k in root.iter() if k.tag.endswith("keybind") and k.get("key") == "W-space"]
assert len(kb) == 1, "one W-space keybind"
a = [x for x in kb[0] if x.tag.endswith("action")][0]
assert a.get("name") == "ShowMenu" and a.get("menu") == "root-menu"
txt = {c.tag.split("}")[-1]: c for c in a.iter()}
assert txt["atCursor"].text == "no"
assert txt["x"].text == "0" and txt["y"].text == "0", "menu top-left under Applications (usable area starts under the top bar)"
mouse = [m for m in root.iter() if m.tag.endswith("mouse")][0]
assert any(c.tag.endswith("default") for c in list(mouse))
ctx = [c for c in list(mouse) if c.tag.endswith("context") and c.get("name") == "Root"]
assert len(ctx) == 1
# 2.1: no mouse button on the desktop opens the root menu (labwc's defaults do on Left, Right and
# Middle press), and no mousebind anywhere shows it: only Applications and Super+Space open it
for btn in ("Left", "Right", "Middle"):
    mb = [b for b in list(ctx[0]) if b.tag.endswith("mousebind") and b.get("button") == btn and b.get("action") == "Press"]
    assert len(mb) == 1, btn
    acts = [a for a in list(mb[0]) if a.tag.endswith("action")]
    assert [a.get("name") for a in acts] == ["None"], "%s-click on the desktop must not open the root menu" % btn
for b in mouse.iter():
    if b.tag.endswith("mousebind"):
        for a in b.iter():
            assert not (a.tag.endswith("action") and a.get("name") == "ShowMenu"), "a mouse binding shows a menu"
shows = [k.get("key") for k in root.iter() if k.tag.endswith("keybind")
         for a in k if a.tag.endswith("action") and a.get("menu") == "root-menu"]
assert shows == ["W-space"], shows
PY
# Evince (Document Viewer) is a GTK 3 header-bar app: it draws its one bar itself (title and the window
# buttons from dconf's button-layout, minimise, maximise, close, as File Roller and Loupe do), and
# labwc adds none, since no window rule forces a frame on it. Its launcher sets no decoration override.
grep -q 'command="prestium-run evince"' "$R/etc/xdg/labwc/menu.xml" \
  || { echo "FAIL: Document Viewer is not started through prestium-run"; exit 1; }
! grep -qi 'evince' "$RC" || { echo "FAIL: rc.xml has a window rule for Evince (would paint a second bar)"; exit 1; }
grep -qx "button-layout='appmenu:minimize,maximize,close'" "$R/etc/dconf/db/local.d/10-prestium-desktop" \
  || { echo "FAIL: header bars (Evince) have no minimise/maximise/close"; exit 1; }
! grep -rqs 'GTK_CSD=1' "$R/usr/local/bin" "$R/etc/environment" \
  || { echo "FAIL: something turns GTK client-side decorations on for every window"; exit 1; }
W=$R/etc/xdg/waybar/config.jsonc
sed 's#//.*##' "$W" | python3 -c '
import json, sys
c = json.load(sys.stdin)
assert isinstance(c, list) and [b["name"] for b in c] == ["prestium-top", "prestium-bottom"], c
top = c[0]
assert top["modules-left"][0] == "custom/applications", top["modules-left"]
m = top["custom/applications"]
# 2.1: on release: a menu opened on the press took the pointer before the release reached waybar, and
# GTK then sent the next click in either bar (a pill, a taskbar icon) to Applications again
assert m["on-click-release"] == "/usr/local/bin/prestium-wl menu" and "on-click" not in m, m
# nothing else in either bar opens the menu
for bar in c:
    for k, v in bar.items():
        if isinstance(v, dict) and k != "custom/applications":
            for e, cmd in v.items():
                if e.startswith("on-") and isinstance(cmd, str):
                    assert "prestium-wl menu" not in cmd and "wtype" not in cmd, (k, e, cmd)
'
grep -qx wtype "$R/../package-lists/prestium-2.0.list.chroot"
# Firefox-based browsers: no tabs in the title bar (the compositor draws the frame)
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-tor-browser/user.js"
grep -q 'browser.tabs.inTitlebar", 0' "$R/usr/local/share/prestium-localfox/user.js"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["policies"]["Preferences"]["browser.tabs.inTitlebar"]["Value"] == 0' "$R/usr/share/librewolf/distribution/policies.json"
echo "wayland decorations + Applications menu: OK"
