#!/bin/bash
# Prestium 2.1 (UI review of 96db20b): the dark desktop look is wired so it can actually load.
R=$(cd "$(dirname "$0")/.." && pwd); I="$R/config/includes.chroot"; L="$R/config/package-lists/prestium.list.chroot"
f=0; ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; f=1; }
# B1: GTK 3 builds in only Adwaita and HighContrast; any other name needs its theme directory from a package
t=$(sed -n "s/^gtk-theme='\(.*\)'$/\1/p" "$I/etc/dconf/db/local.d/10-prestium-desktop")
case "$t" in Adwaita|HighContrast) ok "dconf gtk-theme '$t' is built into GTK 3" ;;
  *) grep -qx gnome-themes-extra "$L" && ok "dconf gtk-theme '$t' from gnome-themes-extra" || bad "dconf gtk-theme '$t' is not installed" ;; esac
grep -q "^color-scheme='prefer-dark'" "$I/etc/dconf/db/local.d/10-prestium-desktop" && ok "dconf prefers dark" || bad "dconf: no prefer-dark"
grep -qx 'gtk-application-prefer-dark-theme=1' "$I/etc/gtk-3.0/settings.ini" && ok "GTK 3 fallback prefers dark" || bad "GTK 3 fallback not dark"
# B2: dconf update needs dconf-cli, and the hook fails without the compiled db
grep -qx dconf-cli "$L" && ok "dconf-cli listed" || bad "dconf-cli missing"
grep -q 'dconf db not compiled' "$R/config/hooks/live/0400-prestium-system.hook.chroot" && ok "hook checks the dconf db" || bad "hook hides a dconf failure"
# B3: labwc's icon theme is a real icon theme
grep -q '<icon>Prestium</icon>' "$I/etc/xdg/labwc/rc.xml" && ok "labwc icon theme Prestium" || bad "labwc icon theme unset"
grep -qx adwaita-icon-theme-legacy "$L" && ok "AdwaitaLegacy installed" || bad "AdwaitaLegacy missing"
# B4: grouping never merges different alerts
grep -qx 'group-by=app-name,summary' "$I/etc/xdg/mako/config" && ok "mako groups identical repeats only" || bad "mako groups by app only"
# B5: every autostart line before the last one returns at once
python3 - "$I/etc/xdg/labwc/autostart" <<'PY' && ok "autostart: only the last program runs in the foreground" || bad "autostart: a program blocks the ones after it"
import sys
cmds = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.lstrip().startswith("#")]
runs = [c for c in cmds if c.startswith("prestium-run ")]
sys.exit(0 if runs and all(c.endswith("&") for c in runs[:-1]) else 1)
PY
# B7: no themerc keys that labwc 0.8.3 rejects or ignores
T="$I/usr/share/themes/Prestium-Dark/openbox-3/themerc"
grep -Eq '^(padding\.(width|height)|titlebar\.height|window\.(active|inactive)\.title\.separator\.color):' "$T" && bad "themerc: unsupported keys" || ok "themerc: labwc 0.8.3 keys"
# B6, B8
grep -q '<keybind key="A-Left"><action name="None" /></keybind>' "$I/etc/xdg/labwc/rc.xml" && ok "Alt+Left left to the browsers" || bad "labwc takes Alt+Left"
grep -q 'identifier="\*zenity\*"' "$I/etc/xdg/labwc/rc.xml" && ok "zenity window rule matches org.gnome.Zenity" || bad "zenity rule matches nothing"
python3 -c "import xml.dom.minidom as m,sys;[m.parse(p) for p in sys.argv[1:]]" "$I/etc/xdg/labwc/rc.xml" "$I/etc/xdg/labwc/menu.xml" && ok "labwc XML parses" || bad "labwc XML broken"
# Design batch (Tech Innovation): one palette everywhere, wired so it loads
H="$R/config/hooks/live"; ACC='#0066ff'
for pk in papirus-icon-theme qt-style-kvantum qt6-style-kvantum qt-style-kvantum-themes fonts-font-awesome; do
  grep -qx "$pk" "$L" && ok "package $pk" || bad "package $pk missing"; done
grep -q '^Inherits=Papirus-Dark,' "$H/0450-prestium-tray-icons.hook.chroot" && ok "Prestium icon theme inherits Papirus-Dark first" || bad "icon theme not on Papirus-Dark"
grep -q 'prestium-logo.svg' "$H/0450-prestium-tray-icons.hook.chroot" && [ -f "$I/usr/share/prestium/branding/prestium-logo.svg" ] && ok "logo in the icon theme" || bad "logo missing"
grep -q "^export QT_STYLE_OVERRIDE=kvantum$" "$I/usr/local/bin/prestium-session" && ok "Qt style kvantum" || bad "Qt style not kvantum"
for kd in etc/skel/.config etc/xdg home/user/.config; do grep -qx 'theme=Prestium' "$I/$kd/Kvantum/kvantum.kvconfig" && ok "Kvantum theme Prestium ($kd)" || bad "Kvantum theme ($kd)"; done
grep -q "set_color highlight.color '$ACC'" "$H/0455-prestium-qt-theme.hook.chroot" && ok "Kvantum accent $ACC" || bad "Kvantum accent"
grep -q 'owner @{HOME}/.config/Kvantum/\*\* r,' "$I/etc/apparmor.d/abstractions/prestium-app-common" && grep -q 'owner @{HOME}/.config/gtk-4.0/\*\* r,' "$I/etc/apparmor.d/abstractions/prestium-app-common" && ok "AppArmor: confined apps read Kvantum and GTK 4 colours" || bad "AppArmor misses Kvantum or gtk-4.0"
grep -q "^accent-color='blue'" "$I/etc/dconf/db/local.d/10-prestium-desktop" && ok "dconf accent blue" || bad "dconf accent"
for v in 3 4; do for b in etc/skel/.config home/user/.config usr/share/prestium/broker-style; do
  [ "$(readlink "$I/$b/gtk-$v.0/gtk.css")" = "/usr/share/prestium/theme/gtk$v.css" ] && ok "gtk-$v.0 css ($b)" || bad "gtk-$v.0 css ($b)"; done
  grep -qi "$ACC" "$I/usr/share/prestium/theme/gtk$v.css" && ok "GTK $v accent $ACC" || bad "GTK $v accent"; done
# broker dialogs: the style directory only, and accessibility still applied last
B="$I/usr/local/sbin/prestium-wl-broker"
grep -q 'extra_env=dict(DIALOG_STYLE, \*\*DIALOG_ENV)' "$B" && grep -q '        e.update(DIALOG_ENV)   # last' "$B" && ok "broker dialogs styled, accessibility off last" || bad "broker dialog env order"
grep -q '^os.environ\["XDG_CONFIG_HOME"\] = "/nonexistent/prestium-stock-gtk"' "$I/usr/local/bin/prestium-browser-updater" && ok "Browser Updater stays stock GTK 3" || bad "Browser Updater picks up gtk.css"
# Kleopatra: Prestium colour scheme by default (not Breeze Dark)
grep -qx 'ColorScheme=Prestium' "$I/etc/xdg/kleopatrarc" && grep -qx 'Name=Prestium' "$I/usr/share/color-schemes/Prestium.colors" && ok "Kleopatra defaults to the Prestium colour scheme" || bad "Kleopatra colour scheme"
grep -q '^BackgroundNormal=0,102,255$' "$I/usr/share/color-schemes/Prestium.colors" && ok "KDE selection $ACC" || bad "KDE selection colour"
# labwc, swaylock, mako, waybar
grep -q "^window.active.border.color: $ACC" "$T" && grep -q '<dropShadows>yes</dropShadows>' "$I/etc/xdg/labwc/rc.xml" && grep -q '<cornerRadius>' "$I/etc/xdg/labwc/rc.xml" && ok "labwc accent, shadows, corners" || bad "labwc theme"
grep -q '^ring-color=0066ffff' "$I/usr/share/prestium/swaylock.conf" && ok "swaylock accent" || bad "swaylock accent"
M="$I/etc/xdg/mako/config"
grep -q '^\[category=prestium.osd\]' "$M" && grep -q -- '-c prestium.osd' "$I/usr/local/bin/prestium-media-key" && ok "OSD category styled" || bad "OSD category"
grep -q '^icon-path=/usr/share/icons/Prestium:/usr/share/icons/Papirus-Dark:' "$M" && ok "mako icons from Papirus-Dark" || bad "mako icon-path"
grep -q '\[ -f "\$FLAG" \] || exit 0' "$I/usr/local/bin/prestium-notify-sound" && ok "notification sounds off unless turned on" || bad "sounds not opt-in"
W="$I/etc/xdg/waybar"
python3 - "$W/config.jsonc" <<'PY' && ok "waybar: floating, Tor and I2P pills from prestium-netstatus" || bad "waybar config"
import json, re, sys
c = json.loads(re.sub(r'^\s*//.*$', '', open(sys.argv[1]).read(), flags=re.M))
assert c["margin-bottom"] > 0 and {"custom/tor", "custom/i2p", "network"} <= set(c["modules-right"])
for k in ("tor", "i2p"):
    assert c["custom/" + k]["exec"] == "cat /run/prestium/netstatus/%s.json" % k and c["custom/" + k]["return-type"] == "json"
PY
python3 - "$W/config.jsonc" <<'PY' && ok "waybar: icon-only status, two-line clock without tooltip" || bad "waybar status area"
import json, re, sys
c = json.loads(re.sub(r'^\s*//.*$', '', open(sys.argv[1]).read(), flags=re.M))
assert c["clock"]["tooltip"] is False and "\n" in c["clock"]["format"]
assert c["pulseaudio"]["format"] == "{icon}" and c["battery"]["format"] == "{icon}"
PY
for cl in connecting ready failed; do grep -q "#custom-tor.$cl, #custom-i2p.$cl" "$W/style.css" && ok "pill colour: $cl" || bad "pill colour $cl"; done
grep -q 'border-radius: 14px' "$W/style.css" && ok "rounded bar" || bad "bar not rounded"
# panel status service: not root, read-only, sandboxed
U="$I/etc/systemd/system/prestium-netstatus.service"
for k in User=prestium-netstatus NoNewPrivileges=yes ProtectSystem=strict ReadWritePaths=/run/prestium/netstatus IPAddressDeny=any CapabilityBoundingSet=; do
  grep -qx "$k" "$U" && ok "netstatus: $k" || bad "netstatus: no $k"; done
grep -q 'prestium-netstatus.service' "$I/usr/share/prestium/build/systemd-wants.txt" && grep -q '^sysuser prestium-netstatus' "$H/0100-prestium-users.hook.chroot" && grep -q '/run/prestium/netstatus 0755 prestium-netstatus' "$I/usr/lib/tmpfiles.d/prestium-safety.conf" && ok "netstatus enabled, user and directory" || bad "netstatus wiring"
D=$(mktemp -d); PATH="$R/tests/fixtures/netstatus:$PATH" PRESTIUM_NETSTATUS_OUT=$D PRESTIUM_NETSTATUS_ONCE=1 bash "$I/usr/local/sbin/prestium-netstatus"
python3 -c "import json,sys;[json.load(open(sys.argv[1]+'/'+f)) for f in ('tor.json','i2p.json')]" "$D" && ok "netstatus writes valid JSON" || bad "netstatus JSON"
grep -q '"class": "ready"' "$D/tor.json" && grep -q '"class": "connecting"' "$D/i2p.json" && ok "netstatus states (fixture: Tor 100 %, I2P 1 router)" || bad "netstatus states: $(cat "$D"/*.json)"
PRESTIUM_FIXTURE_NOROUTE=1 PATH="$R/tests/fixtures/netstatus:$PATH" PRESTIUM_NETSTATUS_OUT=$D PRESTIUM_NETSTATUS_ONCE=1 bash "$I/usr/local/sbin/prestium-netstatus"
grep -q '"class": "connecting"' "$D/tor.json" && grep -q 'no network' "$D/tor.json" && ok "netstatus: Tor 100 % but no default route shows connecting" || bad "netstatus no-route: $(cat "$D/tor.json")"
rm -rf "$D"
# wallpapers: names only, never a path from the user's file
for w in horizon circuit mark; do [ -f "$I/usr/share/backgrounds/prestium/$w.png" ] && ok "wallpaper $w" || bad "wallpaper $w missing"; done
grep -q 'return val if val in WALLPAPERS else WALLPAPERS\[0\]' "$B" && ok "broker takes only a known wallpaper name" || bad "broker wallpaper check"
exit $f
