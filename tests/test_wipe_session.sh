#!/bin/bash
# Prestium 2.1 (review: the session wipe reported success when deletion failed): prestium-wipe-session
# and the USB watchdog's emergency wipe on a fake root. Everything in the required trees (/tmp,
# /var/tmp, /dev/shm, the overlay's work directory and read-write branch) and in the runtime secret
# directories under /run is deleted; what shutdown still needs (/run/systemd, the overlay's own work
# directories, FUSE mount points in /run/user) stays; a missing tree, a failing find or a file left
# behind gives "FAILED" and exit 1, never "session files deleted". Unprivileged.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot
S=$I/usr/local/sbin/prestium-wipe-session; W=$I/usr/local/sbin/prestium-usb-watchdog
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
T=$(mktemp -d); trap 'chmod -R u+w "$T" 2>/dev/null; rm -rf "$T"' EXIT
F=$T/root

mkroot() {
  chmod -R u+w "$F" 2>/dev/null; rm -rf "$F"; mkdir -p "$F"
  for d in tmp/.X11-unix var/tmp dev/shm run/live/overlay/rw/home/user/.ssh run/live/overlay/work/work/#1 \
           run/live/overlay/work/index run/prestium/tor-mode.prev run/prestium-thelounge-tor-launch run/tor \
           run/user/1000/gnupg run/user/1000/gvfs run/systemd run/initramfs; do mkdir -p "$F/$d"; done
  echo secret > "$F/tmp/a"; echo s > "$F/tmp/.hidden"; ln -s /etc/passwd "$F/tmp/link"
  echo s > "$F/var/tmp/b"; echo s > "$F/dev/shm/c"; echo key > "$F/run/live/overlay/rw/home/user/.ssh/id"
  echo s > "$F/run/live/overlay/work/work/#1/tmpfile"; echo s > "$F/run/live/overlay/work/index/x"
  echo s > "$F/run/live/overlay/work/stray"
  echo "Bridge obfs4 1.2.3.4:443" > "$F/run/prestium/tor-mode.prev/dropin"; echo t > "$F/run/prestium-thelounge-tor-launch/token"
  echo c > "$F/run/tor/control.authcookie"; : > "$F/run/user/1000/bus"; : > "$F/run/user/1000/.dotfile"
  : > "$F/run/user/1000/gnupg/S.gpg-agent"; : > "$F/run/user/1000/gvfs/inside-fuse"
  : > "$F/run/systemd/keep"; : > "$F/run/initramfs/keep"
}
gone() { [ -z "$(find "$F$1" -mindepth 1 -print -quit)" ]; }

echo "== prestium-wipe-session"
run() { : > "$T/kmsg"; out=$(env "$@" PRESTIUM_WIPE_ROOT="$F" PRESTIUM_KMSG="$T/kmsg" PRESTIUM_MOUNTS="$T/mounts" sh "$S" 2>&1); rc=$?; }
printf '%s\n' "tmpfs /run tmpfs rw 0 0" "gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse rw 0 0" > "$T/mounts"
mkroot; run
[ $rc -eq 0 ] && grep -qx 'prestium: session files deleted' "$T/kmsg" && ok "full set: exit 0, success logged" || bad "full set: rc=$rc $out $(cat "$T/kmsg")"
for d in /tmp /var/tmp /dev/shm /run/live/overlay/rw /run/prestium /run/prestium-thelounge-tor-launch /run/tor; do
  gone "$d" && [ -d "$F$d" ] && ok "emptied $d (directory kept)" || bad "not emptied: $d"; done
[ -d "$F/run/live/overlay/work/work" ] && [ -d "$F/run/live/overlay/work/index" ] && gone /run/live/overlay/work/work \
  && gone /run/live/overlay/work/index && [ ! -e "$F/run/live/overlay/work/stray" ] \
  && ok "overlay work dir: contents deleted, overlayfs's work/ and index/ kept" || bad "overlay work dir: $(cd "$F" && find run/live/overlay/work)"
[ ! -e "$F/run/user/1000/bus" ] && [ ! -e "$F/run/user/1000/.dotfile" ] && [ ! -e "$F/run/user/1000/gnupg" ] \
  && [ -e "$F/run/user/1000/gvfs/inside-fuse" ] && ok "/run/user/1000: deleted, FUSE mount point (gvfs) left alone" || bad "/run/user/1000: $(ls -A "$F/run/user/1000")"
[ -e "$F/run/systemd/keep" ] && [ -e "$F/run/initramfs/keep" ] && ok "/run/systemd and /run/initramfs kept (shutdown needs them)" || bad "removed what shutdown needs"

mkroot; rm -rf "$F/run/prestium" "$F/run/prestium-thelounge-tor-launch" "$F/run/tor" "$F/run/user"; run
[ $rc -eq 0 ] && ok "runtime directories that don't exist are not a failure" || bad "absent runtime dirs: rc=$rc $out"

mkroot; rm -rf "$F/dev/shm"; run
[ $rc -eq 1 ] && grep -q '^<3>prestium: session wipe FAILED, .*/dev/shm(missing)' "$T/kmsg" && ! grep -q 'deleted' "$T/kmsg" \
  && gone /tmp && ok "a missing required tree: exit 1, FAILED logged, no success, the rest still deleted" || bad "missing tree: rc=$rc $(cat "$T/kmsg")"
mkroot; rm -rf "$F/run/live/overlay/work"; ln -s "$T" "$F/run/live/overlay/work"; run
[ $rc -eq 1 ] && grep -q '/run/live/overlay/work(missing)' "$T/kmsg" && ok "a symlink instead of a tree is refused (not followed)" || bad "symlinked tree: rc=$rc $(cat "$T/kmsg")"

mkdir -p "$T/bin"; printf '#!/bin/sh\nexit 1\n' > "$T/bin/find"; chmod 755 "$T/bin/find"
mkroot; : > "$T/kmsg"; out=$(env PATH="$T/bin:$PATH" PRESTIUM_WIPE_ROOT="$F" PRESTIUM_KMSG="$T/kmsg" PRESTIUM_MOUNTS="$T/mounts" sh "$S" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q 'FAILED.*/tmp(find)' "$T/kmsg" && ! grep -q 'deleted' "$T/kmsg" && ok "find fails: exit 1, no success logged" || bad "failing find: rc=$rc $(cat "$T/kmsg")"

if [ "$(id -u)" != 0 ]; then
  mkroot; mkdir -p "$F/var/tmp/locked"; : > "$F/var/tmp/locked/f"; chmod 555 "$F/var/tmp/locked"; run
  chmod u+w "$F/var/tmp/locked"
  [ $rc -eq 1 ] && grep -q '/var/tmp(find)' "$T/kmsg" && grep -q '/var/tmp(left:locked' "$T/kmsg" && ! grep -q deleted "$T/kmsg" \
    && ok "a file that can't be deleted: exit 1, named in the log" || bad "undeletable file: rc=$rc $(cat "$T/kmsg")"
else echo "SKIP undeletable file (root deletes it anyway)"; fi

echo "== prestium-usb-watchdog emergency wipe"
blk=$(sed -n '/# BEGIN emergency wipe/,/# END emergency wipe/p' "$W")
[ -n "$blk" ] && ok "emergency wipe block found" || bad "no emergency wipe block"
# the same trees as prestium-wipe-session
lists() { sed -n '/^ *REQUIRED="/p; /^ *RUNTIME="/,/"$/p' "$1" | tr -s ' \n' '  ' | sed 's/^ //; s/ $//'; }
[ "$(lists "$S")" = "$(lists <(printf '%s\n' "$blk"))" ] && ok "same REQUIRED and RUNTIME trees as prestium-wipe-session" || bad "lists differ: $(lists "$S") | $(lists <(printf '%s\n' "$blk"))"
L1=$(grep -n 'echo "<0>prestium: emergency session wipe FAILED' "$W" | cut -d: -f1); L2=$(grep -n 'echo o > /proc/sysrq-trigger' "$W" | cut -d: -f1)
[ -n "$L1" ] && [ -n "$L2" ] && [ "$L1" -lt "$L2" ] && ! grep -q 'exit' <(sed -n "${L1},${L2}p" "$W") \
  && ok "failure logged, then power-off (sysrq o) either way" || bad "emergency: log/power-off order"
grep -E '\$F .*-delete' <<<"$blk" | grep -vq '|| bad=' && bad "an emergency find whose result is ignored" || ok "every emergency find is checked"
# run the block on the fake root (paths prefixed), as the fallback runs it
eblk=$(printf '%s\n' "$blk" | sed -E "s#([\"= ])/(tmp|var/tmp|dev/shm|run/)#\1$F/\2#g; s#< /proc/self/mounts#< \"$T/mounts-e\"#")
printf '%s\n' "gvfsd-fuse $F/run/user/1000/gvfs fuse.gvfsd-fuse rw 0 0" > "$T/mounts-e"
mkroot; res=$(bash -c "$eblk"'
wipe_all; printf "%s" "$bad"' 2>&1)
[ -z "$res" ] && gone /tmp && gone /run/live/overlay/rw && gone /run/prestium && gone /run/live/overlay/work/work \
  && [ -e "$F/run/user/1000/gvfs/inside-fuse" ] && [ -e "$F/run/systemd/keep" ] && ok "emergency: full set deleted, nothing reported" || bad "emergency full set: $res"
mkroot; rm -rf "$F/var/tmp"; res=$(bash -c "$eblk"'
wipe_all; printf "%s" "$bad"' 2>&1)
grep -q "$F/var/tmp(missing)" <<<"$res" && ok "emergency: a missing tree is reported" || bad "emergency missing: $res"
if [ "$(id -u)" != 0 ]; then
  mkroot; mkdir -p "$F/dev/shm/locked"; : > "$F/dev/shm/locked/f"; chmod 555 "$F/dev/shm/locked"
  res=$(bash -c "$eblk"'
wipe_all; printf "%s" "$bad"' 2>&1); chmod u+w "$F/dev/shm/locked"
  grep -q "$F/dev/shm(find)" <<<"$res" && grep -q "$F/dev/shm(left)" <<<"$res" && ok "emergency: a file left behind is reported" || bad "emergency undeletable: $res"
fi
bash -n "$W" && ok "watchdog: bash -n" || bad "watchdog syntax"
exit $fail
