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
exit $f
