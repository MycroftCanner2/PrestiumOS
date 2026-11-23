#!/bin/bash
# Security review F-01: hook 0625 makes every start of a confined desktop application go through
# app-confine. Runs the hook on a stand-in tree (paths rewritten): shims, desktop-file and D-Bus
# activation overrides, autostart files, and the build failing on what it can't redirect.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
HK=$R/config/hooks/live/0625-prestium-app-confine.hook.chroot
AC=$R/config/includes.chroot/usr/local/lib/prestium/app-confine
[ -x /usr/bin/xdg-dbus-proxy ] || { echo "SKIP xdg-dbus-proxy missing (the hook requires it)"; exit 0; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; F=$T/root
mkdir -p "$F/usr/bin" "$F/usr/local/bin" "$F/usr/local/lib/prestium" "$F/usr/share/applications" "$F/usr/local/share/applications" \
  "$F/etc/xdg/autostart" "$F/usr/share/dbus-1/services" "$F/usr/lib/systemd/user"
sed -e "s#\"/usr/bin/#\"$F/usr/bin/#g; s#\"/usr/local/bin/#\"$F/usr/local/bin/#g; s#\"/usr/libexec/#\"$F/usr/libexec/#g" "$AC" > "$F/usr/local/lib/prestium/app-confine"
chmod 755 "$F/usr/local/lib/prestium/app-confine"
for p in gajim vlc loupe keepassxc evince; do printf '#!/bin/sh\n' > "$F/usr/bin/$p"; chmod 755 "$F/usr/bin/$p"; done
for p in feather prestium-gajim-keys prestium-translate prestium-audacity; do printf '#!/bin/sh\n' > "$F/usr/local/bin/$p"; chmod 755 "$F/usr/local/bin/$p"; done
printf '[Desktop Entry]\nExec=%s --started-from-file %%U\n[Desktop Action play]\nExec=%s --play\n' "$F/usr/bin/vlc" "$F/usr/bin/vlc" > "$F/usr/share/applications/vlc.desktop"
printf '[Desktop Entry]\nExec=gajim\nDBusActivatable=true\n' > "$F/usr/share/applications/org.gajim.Gajim.desktop"
printf '[Desktop Entry]\nExec=env GDK_BACKEND=x11 audacity %%F\n' > "$F/usr/share/applications/audacity.desktop"
printf '[Desktop Entry]\nExec=pcmanfm %%U\n' > "$F/usr/share/applications/pcmanfm.desktop"
printf '[D-BUS Service]\nName=org.gnome.Loupe\nExec=%s --gapplication-service\n' "$F/usr/bin/loupe" > "$F/usr/share/dbus-1/services/org.gnome.Loupe.service"
printf '[Desktop Entry]\nExec=keepassxc --minimized\n' > "$F/etc/xdg/autostart/keepassxc.desktop"
mk(){ sed -e "s#/usr/local/lib/prestium/app-confine#$F/usr/local/lib/prestium/app-confine#g" \
  -e "s#\"/usr/local/bin/\"#\"$F/usr/local/bin/\"#g; s#\"/usr/local/bin/\" + n#\"$F/usr/local/bin/\" + n#g" \
  -e "s#/usr/local/share/#$F/usr/local/share/#g; s#\"/usr/share/#\"$F/usr/share/#g; s#/etc/xdg/autostart#$F/etc/xdg/autostart#g" \
  -e "s#/usr/lib/systemd/user#$F/usr/lib/systemd/user#g; s#/etc/systemd/user#$F/etc/systemd/user#g" \
  -e "s#p.startswith(\"/usr/bin/\")#p.startswith(\"$F/usr/bin/\")#g" "$HK" > "$T/hook.sh"; }
mk
o=$(sh "$T/hook.sh" 2>&1); r=$?
[ $r = 0 ] && ok "hook runs: $(printf '%s\n' "$o" | grep '^P:')" || bad "hook failed: $o"
for p in gajim vlc loupe keepassxc evince; do
  grep -qx "exec $F/usr/local/lib/prestium/app-confine $p \"\$@\"" "$F/usr/local/bin/$p" 2>/dev/null && ok "shim /usr/local/bin/$p" || bad "no shim for $p"
done
[ ! -e "$F/usr/local/bin/kleopatra" ] && ok "no shim for a program that is not installed" || bad "shim for a missing program"
L=$F/usr/local/share/applications
[ "$(grep -c "^Exec=$F/usr/local/bin/vlc " "$L/vlc.desktop" 2>/dev/null)" = 2 ] && ok "vlc.desktop override: both Exec lines (main and action) run the shim" || bad "vlc.desktop: $(grep Exec "$L/vlc.desktop" 2>&1)"
grep -qx "Exec=$F/usr/local/bin/gajim" "$L/org.gajim.Gajim.desktop" && ok "Exec=gajim gets the shim's absolute path" || bad "gajim desktop"
grep -qx "Exec=env GDK_BACKEND=x11 $F/usr/local/lib/prestium/app-confine audacity %F" "$L/audacity.desktop" && ok "Audacity's desktop file: app-confine audacity" || bad "audacity desktop: $(grep Exec "$L/audacity.desktop" 2>&1)"
[ ! -e "$L/pcmanfm.desktop" ] && ok "other desktop files are left alone" || bad "pcmanfm overridden"
grep -qx "Exec=$F/usr/local/bin/loupe --gapplication-service" "$F/usr/local/share/dbus-1/services/org.gnome.Loupe.service" && ok "D-Bus activation of Loupe: override runs the shim" || bad "Loupe service override"
grep -q "^Exec=$F/usr/bin/loupe" "$F/usr/share/dbus-1/services/org.gnome.Loupe.service" && ok "Debian's service file itself unchanged (the override is searched first)" || bad "service file"
grep -qx "Exec=$F/usr/local/bin/keepassxc --minimized" "$F/etc/xdg/autostart/keepassxc.desktop" && ok "autostart rewritten in place" || bad "autostart"
o=$(sh "$T/hook.sh" 2>&1) && ok "hook runs again (idempotent)" || bad "second run: $o"
[ "$(grep -c "^exec " "$F/usr/local/bin/gajim")" = 1 ] && ok "second run: shim unchanged" || bad "second run shim"
# what it must refuse
printf '[D-BUS Service]\nName=org.gnome.Evince\nExec=%s\nSystemdService=evince.service\n' "$F/usr/bin/evince" > "$F/usr/share/dbus-1/services/org.gnome.Evince.service"
o=$(sh "$T/hook.sh" 2>&1) && bad "accepted a SystemdService activation" || { printf '%s' "$o" | grep -q SystemdService && ok "refuses SystemdService= activation of a confined program" || bad "wrong error: $o"; }
rm -f "$F/usr/share/dbus-1/services/org.gnome.Evince.service" "$F/usr/local/share/dbus-1/services/org.gnome.Evince.service"
printf '[Service]\nExecStart=%s\n' "$F/usr/bin/evince" > "$F/usr/lib/systemd/user/evince.service"
o=$(sh "$T/hook.sh" 2>&1) && bad "accepted a user unit running a confined program" || ok "refuses a systemd user unit that runs a confined program"
rm -f "$F/usr/lib/systemd/user/evince.service"
printf '#!/bin/sh\necho other\n' > "$F/usr/local/bin/evince"
o=$(sh "$T/hook.sh" 2>&1) && bad "overwrote a foreign /usr/local/bin/evince" || ok "refuses to replace a /usr/local/bin program that is not its shim"
exit $fail
