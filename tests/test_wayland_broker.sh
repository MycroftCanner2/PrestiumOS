#!/bin/bash
# 2.0 r11: runs the real Wayland broker (as root, via sudo) against a headless labwc started as this
# user, and checks that no process of the user can reach the compositor's full socket any more,
# while the restricted socket, the panel, the screen lock, screenshots and scaling still work.
# Needs sudo, labwc, waybar, mako, swaybg, swayidle, swaylock, slurp, grim, wlr-randr, wayland-utils.
set -u
H=$(cd "$(dirname "$0")/.." && pwd)
I=$H/config/includes.chroot
fail=0; ok() { echo "OK   $1"; }; bad() { echo "FAIL $1"; fail=1; }
U=$(id -u)
T=$(mktemp -d); chmod 755 "$T"
export PRESTIUM_WL_BASE=$T/base XDG_RUNTIME_DIR=$T/rt$U HOME=$T/home
mkdir -p "$HOME/.config/prestium" && mkdir -m 700 "$XDG_RUNTIME_DIR"
cleanup() {
  for f in "$T/broker.pid" "$T/broker2.pid"; do [ -s "$f" ] && sudo -n kill "$(cat "$f")" 2>/dev/null; done; kill "$(cat "$T/dbus.pid" 2>/dev/null)" 2>/dev/null
  pkill -u "$U" -x waybar; pkill -u "$U" -x mako; pkill -u "$U" -x swaybg; pkill -u "$U" -x swayidle
  pkill -u "$U" -x swaylock 2>/dev/null; pkill -u "$U" -x labwc 2>/dev/null; sleep 0.5
  sudo -n rm -rf "$T"
}
trap cleanup EXIT
WL="$I/usr/local/bin/prestium-wl"
globals() { timeout 10 wayland-info 2>/dev/null | grep -oE "interface: '[a-z_0-9]+'" | cut -d"'" -f2 | sort -u; }

WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 labwc -c /dev/null >/dev/null 2>&1 &
for i in $(seq 50); do [ -S "$XDG_RUNTIME_DIR/wayland-0" ] && break; sleep 0.1; done
dbus-daemon --session --address="unix:path=$XDG_RUNTIME_DIR/bus" --fork --print-pid > "$T/dbus.pid"
sudo -n env PRESTIUM_WL_BASE="$PRESTIUM_WL_BASE" PRESTIUM_WL_RUNTIME="$T/rt%d" PRESTIUM_WL_HOME="$HOME" PRESTIUM_WL_ETC="$I/etc/xdg" \
  PRESTIUM_SCALE="$I/usr/local/bin/prestium-scale" sh -c 'echo $$ > "$1"; exec python3 -I "$2"' _ \
  "$T/broker.pid" "$I/usr/local/sbin/prestium-wl-broker" > "$T/broker.log" 2>&1 < /dev/null &
for i in $(seq 50); do [ -S "$PRESTIUM_WL_BASE/broker" ] && break; sleep 0.1; done

[ -n "$(WAYLAND_DISPLAY=wayland-0 globals)" ] && ok "before start: the user can use the full socket (setup)" || bad "setup: labwc"
full_before=$(WAYLAND_DISPLAY=wayland-0 globals)
r=$(python3 "$WL" start); [ "${r%% *}" = ok ] && ok "start: $r" || { bad "start: $r"; cat "$T/broker.log"; }
st=$(stat -c '%u %a' "$XDG_RUNTIME_DIR/wayland-0")
[ "$st" = "0 600" ] && ok "full socket is now root-owned, mode 600" || bad "full socket is '$st'"
[ -z "$(WAYLAND_DISPLAY=wayland-0 globals)" ] && ok "the user can no longer connect to the full socket (by name)" || bad "full socket still reachable"
[ -z "$(WAYLAND_DISPLAY=$XDG_RUNTIME_DIR/wayland-0 globals)" ] && ok "... nor by absolute path" || bad "full socket reachable by path"
chmod 666 "$XDG_RUNTIME_DIR/wayland-0" 2>/dev/null && bad "the user could chmod the full socket" || ok "the user can't chmod it back"
chown "$U" "$XDG_RUNTIME_DIR/wayland-0" 2>/dev/null && bad "the user could chown it" || ok "... nor chown it"
mv "$XDG_RUNTIME_DIR/wayland-0" "$XDG_RUNTIME_DIR/stolen" && {
  [ -z "$(WAYLAND_DISPLAY=$XDG_RUNTIME_DIR/stolen globals)" ] && ok "renaming it gains nothing (still root's)" || bad "renamed socket reachable"
  mv "$XDG_RUNTIME_DIR/stolen" "$XDG_RUNTIME_DIR/wayland-0"; }
L=$(pgrep -x labwc | head -1)
ps=$(cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo none)
if [ "$ps" != 2 ] && [ "$ps" != 3 ]; then
  echo "SKIP pidfd_getfd check: this host has kernel.yama.ptrace_scope=$ps (Prestium sets 2, which blocks it)"
else
python3 - "$L" <<'PY' && bad "the user could take labwc's socket with pidfd_getfd" || ok "the user can't take the socket from labwc's file descriptors (pidfd_getfd)"
import ctypes, os, sys
libc = ctypes.CDLL(None, use_errno=True)
pid = int(sys.argv[1]); pfd = libc.syscall(434, pid, 0)            # pidfd_open
if pfd < 0: sys.exit(1)
for fd in range(3, 64):
    if libc.syscall(438, pfd, fd, 0) >= 0: sys.exit(0)              # pidfd_getfd
sys.exit(1)
PY
fi
APPS=$PRESTIUM_WL_BASE/$U/apps
st=$(stat -c '%U %a' "$APPS" 2>/dev/null); dst=$(stat -c '%U %a' "$PRESTIUM_WL_BASE/$U")
[ "$st" = "root 660" ] && [ "$dst" = "root 755" ] && ok "restricted socket root:user 660 in a root-owned directory" || bad "apps socket '$st' dir '$dst'"
mv "$APPS" "$APPS.x" 2>/dev/null && bad "the user could rename the restricted socket (MITM)" || ok "the user can't rename or replace the restricted socket"
apps=$(WAYLAND_DISPLAY=$APPS globals)
n=0
for p in zwlr_screencopy_manager_v1 zwlr_export_dmabuf_manager_v1 zwp_virtual_keyboard_manager_v1 \
         zwlr_virtual_pointer_manager_v1 zwlr_data_control_manager_v1 zwlr_foreign_toplevel_manager_v1 \
         ext_foreign_toplevel_list_v1 zwp_input_method_manager_v2 wp_security_context_manager_v1 \
         zwlr_layer_shell_v1 ext_session_lock_manager_v1 zwlr_output_manager_v1 zwlr_gamma_control_manager_v1 \
         ext_idle_notifier_v1; do
  echo "$full_before" | grep -qx "$p" || { bad "full socket lacks $p (setup)"; continue; }
  echo "$apps" | grep -qx "$p" && { bad "restricted socket offers $p"; n=1; }
done
[ $n = 0 ] && ok "restricted socket hides capture, input injection, clipboard managers, other windows, overlays, lock, output/gamma, idle"
echo "$apps" | grep -qx xdg_wm_base && ok "restricted socket works for normal windows" || bad "restricted socket unusable"
[ "$(PRESTIUM_WL_BASE= sh -c '. /dev/null; S=$1; WAYLAND_DISPLAY=$S timeout 5 grim /dev/null 2>&1' _ "$APPS" | grep -ci "screencopy\|not support\|failed")" -gt 0 ] \
  && ok "grim run by an app fails (no screen capture on the restricted socket)" || bad "grim worked on the restricted socket"

r=$(python3 "$WL" panel); sleep 2
wb=$(pgrep -u "$U" -x waybar | head -1)
[ -n "$wb" ] && ok "panel: waybar started by the broker, as the user ($r)" || bad "panel: $r"
if [ -n "$wb" ]; then
  tr '\0' '\n' < /proc/$wb/environ | grep -qx "WAYLAND_DISPLAY=$APPS" && ok "the panel's own children get the restricted socket" || bad "waybar WAYLAND_DISPLAY"
  tr '\0' '\n' < /proc/$wb/environ | grep -qx "XDG_CONFIG_HOME=$PRESTIUM_WL_BASE/$U/empty" && ok "trusted tools ignore ~/.config (empty root-owned XDG_CONFIG_HOME)" || bad "XDG_CONFIG_HOME"
fi
for p in mako swaybg swayidle; do pgrep -u "$U" -x $p >/dev/null && ok "panel: $p running" || bad "panel: $p not running"; done

echo 150 > "$HOME/.config/prestium/scale"
r=$(python3 "$WL" scale)
sc=$(sudo -n env WAYLAND_DISPLAY="$XDG_RUNTIME_DIR/wayland-0" wlr-randr 2>/dev/null | awk '/Scale/{print $2}')
[ "$sc" = "1.500000" ] && ok "scale: applied by the broker ($r)" || bad "scale: '$sc' ($r)"

python3 "$WL" screenshot > "$T/shot" 2>&1 < /dev/null & SP=$!
sleep 1.5
pgrep -u "$U" -x slurp >/dev/null && ok "screenshot waits for the user's click (slurp overlay up)" || bad "screenshot: no slurp"
pkill -u "$U" -x slurp; wait $SP
grep -q "^ok cancelled" "$T/shot" && ok "screenshot without a click: nothing captured" || bad "screenshot: $(cat "$T/shot")"
ls "$HOME/Pictures" 2>/dev/null | grep -q . && bad "a screenshot file was written" || ok "no screenshot file written"

r=$(python3 "$WL" lock); [ "$r" = "ok locked" ] && ok "lock: swaylock locked the session" || bad "lock: $r"
pgrep -u "$U" -x swaylock >/dev/null && ok "lock: swaylock runs as the user" || bad "lock: no swaylock"
r=$(python3 "$WL" bogus 2>&1); [ $? -ne 0 ] && ok "unknown requests refused" || bad "bogus accepted"
r=$(sudo -n python3 -I "$WL" status 2>/dev/null); case "$r" in error*|"") ok "requests from root refused" ;; *) bad "root request: $r" ;; esac

# a second broker against a socket that isn't labwc's
T2=$T/fake; mkdir -p "$T2/rt$U"; chmod 700 "$T2/rt$U"
python3 -c 'import socket,sys,time; s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(5); time.sleep(20)' "$T2/rt$U/wayland-0" >/dev/null 2>&1 &
sleep 0.5
sudo -n env PRESTIUM_WL_BASE="$T2/base" PRESTIUM_WL_RUNTIME="$T2/rt%d" sh -c 'echo $$ > "$1"; exec python3 -I "$2"' _ \
  "$T/broker2.pid" "$I/usr/local/sbin/prestium-wl-broker" >/dev/null 2>&1 < /dev/null &
for i in $(seq 50); do [ -S "$T2/base/broker" ] && break; sleep 0.1; done
r=$(PRESTIUM_WL_BASE=$T2/base python3 "$WL" start 2>&1)
case "$r" in *"not the user's compositor"*) ok "start refuses a socket that isn't labwc's" ;; *) bad "fake compositor: $r" ;; esac
exit $fail
