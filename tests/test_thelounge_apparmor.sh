#!/bin/sh
# Prestium 2.0 r20: The Lounge runs under AppArmorProfile=thelounge with PrivateDevices/PrivateTmp, so
# its profile must attach disconnected paths (systemd's host-opened stdin), or Node aborts at start.
set -e
R=$(cd "$(dirname "$0")/.." && pwd)/config/includes.chroot
grep -q '^AppArmorProfile=thelounge$' "$R/etc/systemd/system/thelounge.service.d/zz-apparmor.conf"
grep -q '^profile thelounge flags=(attach_disconnected) {$' "$R/etc/apparmor.d/prestium.thelounge"
# compile against the system's AppArmor base plus the tree's own files (abi, abstractions), as CI does
if command -v apparmor_parser >/dev/null; then
  W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
  cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null || true; cp -r "$R/etc/apparmor.d"/. "$W"/
  apparmor_parser -Q -K -b "$W" "$W/prestium.thelounge" >/dev/null 2>"$W/.err" || { cat "$W/.err"; exit 1; }
fi
# 2.0 r20: Claws Mail 4.x control socket dir
grep -q "owner @{run}/user/\[0-9\]\*/claws-mail/\* rwk," "$R/etc/apparmor.d/usr.bin.claws-mail"
# 2.0 r20: Gajim multiprocessing semaphores
grep -q "owner /dev/shm/sem.\* rwkl," "$R/etc/apparmor.d/usr.bin.gajim"
echo "thelounge + claws + gajim apparmor: OK"
