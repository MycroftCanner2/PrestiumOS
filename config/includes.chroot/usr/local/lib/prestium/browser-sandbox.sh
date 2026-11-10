# Prestium 2.0 r10: shared bubblewrap sandbox for the browsers (Tor Browser, LibreWolf).
# Sourced by /usr/local/bin/tor-browser and /usr/local/bin/librewolf-i2p (bash).
#
# The sandbox has:
#  - its own, empty network namespace: only loopback, so no TCP/UDP/DNS/ICMP to anywhere (not even
#    the host's 127.0.0.1) and no abstract Unix sockets of the host (e.g. Xwayland's). Its only ways
#    out are the Unix sockets the caller binds in (Tor's SOCKS socket, a proxy relay).
#  - its own mount namespace: read-only /usr, /etc and the browser install, private /tmp and
#    /dev/shm, and of $HOME only the directories the caller binds in. No D-Bus at all.
#  - Wayland only, through the restricted socket (/run/prestium-wl/<uid>/apps, a security context
#    made by prestium-wl-broker): no screen capture, no input injection, no clipboard snooping, no
#    access to other windows. The compositor's full socket is root-owned. No X11 socket.
#  - its own PID, IPC, UTS (hostname "localhost") and cgroup namespaces; no_new_privs (sudo and every
#    other setuid program are useless inside).
#  - the browser's AppArmor profile still applies inside (same paths).

# 2.1 (security audit): fixed paths, never from the environment (see the launchers' header).
SBX_WL_BASE=/run/prestium-wl
SBX_BWRAP=/usr/bin/bwrap

sbx_fail() {   # $1 title, $2 message
  notify-send -u critical "$1" "$2" 2>/dev/null
  echo "$1: $2" >&2
  exit 1
}

# sbx_init TITLE: checks, and starts the B array with everything both browsers share.
sbx_init() {
  SBX_TITLE=$1
  [ -x "$SBX_BWRAP" ] || sbx_fail "$SBX_TITLE" "The browser sandbox (bubblewrap) is missing. The browser was not started."
  [ -n "${XDG_RUNTIME_DIR:-}" ] || sbx_fail "$SBX_TITLE" "No session. The browser was not started."
  SBX_U=$(id -u)
  SBX_DIR="$XDG_RUNTIME_DIR/prestium-sandbox"
  mkdir -p -m 0700 "$SBX_DIR" || sbx_fail "$SBX_TITLE" "Cannot create $SBX_DIR."
  SBX_WL="$SBX_WL_BASE/$SBX_U/apps"
  [ -S "$SBX_WL" ] || sbx_fail "$SBX_TITLE" "The restricted Wayland socket is missing. The browser was not started."
  local inner="/run/user/$SBX_U"
  B=(--unshare-all --new-session --die-with-parent --hostname localhost
     --ro-bind /usr /usr --ro-bind /etc /etc)
  local d
  for d in bin lib lib64 sbin; do
    [ -L "/$d" ] && B+=(--symlink "$(readlink "/$d")" "/$d")
  done
  B+=(--proc /proc --dev /dev --tmpfs /dev/shm --dev-bind-try /dev/dri /dev/dri --ro-bind /sys /sys
      --tmpfs /tmp --dir /var/tmp --tmpfs /run --dir /run/user --dir "$inner" --chmod 0700 "$inner"
      --bind "$SBX_WL" "$inner/wayland-0"
      --bind-try "$XDG_RUNTIME_DIR/pulse" "$inner/pulse"
      --bind-try "$XDG_RUNTIME_DIR/pipewire-0" "$inner/pipewire-0"
      --dir "$HOME" --ro-bind-try "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-3.0"
      --clearenv --setenv HOME "$HOME" --setenv USER "$(id -un)" --setenv LOGNAME "$(id -un)"
      --setenv PATH /usr/bin:/bin --setenv LANG "${LANG:-C.UTF-8}"
      --setenv XDG_RUNTIME_DIR "$inner" --setenv WAYLAND_DISPLAY wayland-0
      --setenv XDG_SESSION_TYPE wayland --setenv MOZ_ENABLE_WAYLAND 1 --setenv GDK_BACKEND wayland
      --setenv MOZ_DISABLE_WAYLAND_PROXY 1
      --unsetenv DISPLAY)
  [ -n "${LC_ALL:-}" ] && B+=(--setenv LC_ALL "$LC_ALL")
  return 0
}

# sbx_run APP_ID COMMAND...: run bwrap "${B[@]}" -- COMMAND and return its exit status.
# sbx_exec: the same, replacing the shell. (APP_ID is kept for the callers; the restricted socket
# is shared by all applications.)
sbx_run() {
  shift
  "$SBX_BWRAP" "${B[@]}" -- "$@"
}
sbx_exec() {
  shift
  exec "$SBX_BWRAP" "${B[@]}" -- "$@"
}
