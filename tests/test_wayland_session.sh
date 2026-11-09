#!/bin/bash
# 2.0 r10/r11: generates the compositor's configuration with the real prestium-wl-config (root, via
# sudo) and starts labwc headless with it; checks the configuration loads, is root-owned, takes the
# touchpad settings, and that ~/.config/labwc (which apps can write) is never used.
# Needs sudo, labwc, wayland-utils. (The broker itself: tests/test_wayland_broker.sh.)
set -u
H=$(cd "$(dirname "$0")/.." && pwd)
I=$H/config/includes.chroot
fail=0; ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; fail=1; }
U=$(id -u)
T=$(mktemp -d); chmod 755 "$T"
export HOME=$T/home XDG_RUNTIME_DIR=$T/xdg PRESTIUM_WL_BASE=$T/base
mkdir -p "$HOME/.config/prestium" "$HOME/.config/labwc" && mkdir -m 700 "$XDG_RUNTIME_DIR"
cleanup() { [ -n "${LP:-}" ] && kill $LP 2>/dev/null; sleep 0.3; sudo -n rm -rf "$T"; }
trap cleanup EXIT
# the config helper reads /etc/xdg/labwc: point it at the repository's copy for the test
sed "s#^SRC = \"/etc/xdg/labwc\"#SRC = \"$I/etc/xdg/labwc\"#" "$I/usr/local/sbin/prestium-wl-config" > "$T/wlconf"
gen() { sudo -n env SUDO_UID="$U" PRESTIUM_WL_BASE="$PRESTIUM_WL_BASE" HOME="$HOME" python3 -I "$T/wlconf"; }
# pwd.getpwuid gives the real home; the touchpad file is put there via a link-free copy below
RH=$(getent passwd "$U" | cut -d: -f6)

echo '{"tapping": false, "natural_scrolling": false, "disable_while_typing": true, "speed": 0.4}' > "$T/tp.json"
mkdir -p "$RH/.config/prestium"; had=0; [ -e "$RH/.config/prestium/touchpad.json" ] && { had=1; cp "$RH/.config/prestium/touchpad.json" "$T/tp.saved"; }
cp "$T/tp.json" "$RH/.config/prestium/touchpad.json"
C=$(gen 2>/dev/null); [ "$C" = "$PRESTIUM_WL_BASE/$U/labwc" ] && ok "prestium-wl-config wrote $C" || bad "prestium-wl-config: $C"
st=$(stat -c '%U %a' "$C" 2>/dev/null)
[ "$st" = "root 755" ] && [ "$(stat -c %U "$C/rc.xml")" = root ] && ok "configuration directory and files are root-owned" || bad "config owner '$st'"
grep -q "<tap>no</tap>" "$C/rc.xml" && grep -q "<pointerSpeed>0.40</pointerSpeed>" "$C/rc.xml" && grep -q "<naturalScroll>no</naturalScroll>" "$C/rc.xml" \
  && ok "touchpad settings taken (checked values only)" || bad "touchpad values"
echo '{"tapping": "</tap><keybind key=\"a\"><action name=\"Execute\" command=\"evil\"/></keybind>", "speed": "1; evil"}' > "$RH/.config/prestium/touchpad.json"
C=$(gen 2>/dev/null); grep -q evil "$C/rc.xml" && bad "a crafted touchpad file injected XML" || ok "a crafted touchpad file injects nothing"
rm -f "$RH/.config/prestium/touchpad.json"; ln -s /etc/shadow "$RH/.config/prestium/touchpad.json"
C=$(gen 2>/dev/null); [ -f "$C/rc.xml" ] && grep -q "<tap>yes</tap>" "$C/rc.xml" && ok "a symlinked touchpad file is ignored (defaults)" || bad "symlink: $C"
rm -f "$RH/.config/prestium/touchpad.json"; [ $had = 1 ] && cp "$T/tp.saved" "$RH/.config/prestium/touchpad.json"

# what an app could drop in ~/.config/labwc
cat > "$HOME/.config/labwc/rc.xml" <<'EOF'
<labwc_config><windowRules><windowRule identifier="*"><action name="Execute" command="touch /tmp/prestium-pwned"/></windowRule></windowRules></labwc_config>
EOF
echo 'touch /tmp/prestium-pwned' > "$HOME/.config/labwc/autostart"
rm -f /tmp/prestium-pwned
# control: a plain labwc does run ~/.config/labwc/autostart (so the check below means something)
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 XDG_RUNTIME_DIR=$T/xdgc timeout 4 labwc >/dev/null 2>&1 &
mkdir -m 700 "$T/xdgc"; sleep 3
[ -e /tmp/prestium-pwned ] && ok "control: a plain labwc runs ~/.config/labwc/autostart" || bad "control did not trigger"
rm -f /tmp/prestium-pwned; wait
# run labwc exactly as prestium-session does (labwc -C <dir>), with the autostart's commands absent
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 labwc -C "$C" > "$T/labwc.log" 2>&1 & LP=$!
for i in $(seq 50); do [ -S "$XDG_RUNTIME_DIR/wayland-0" ] && break; sleep 0.1; done
sleep 1.5
grep -E '\[ERROR\]' "$T/labwc.log" | grep -v "Blocking unknown protocol" > "$T/err"
[ -s "$T/err" ] && { bad "labwc reports config errors"; cat "$T/err"; } || ok "labwc loads rc.xml and menu.xml without errors"
WAYLAND_DISPLAY=wayland-0 timeout 5 wayland-info >/dev/null 2>&1 && ok "compositor running with that configuration" || bad "labwc not running"
[ -e /tmp/prestium-pwned ] && bad "labwc ran a command from ~/.config/labwc" || ok "~/.config/labwc (rc.xml window rule, autostart) is never read"
rm -f /tmp/prestium-pwned
grep -q 'prestium-run' "$C/menu.xml" && ! grep -q 'command="[^p/]' "$C/menu.xml" \
  && ok "every menu entry starts through prestium-run or a Prestium tool" || bad "menu entries"
exit $fail
