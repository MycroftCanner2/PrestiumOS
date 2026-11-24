#!/bin/bash
# quick_qubes: the VM / Qubes OS variant.
#   - no bare-metal firmware or CPU microcode: no firmware list or pin, no firmware package in any package
#     list or optional-packages.txt, no non-free-firmware archive area, live-build's firmware options off,
#     and hook 9980 stops the build when one is installed anyway (run against a stub dpkg-query)
#   - no Wi-Fi, mobile broadband, tethering, tablet or real-GPU X driver packages, and no units or D-Bus
#     aliases left for them; the virtual GPU X drivers stay
#   - the ISO name, os-release VARIANT_ID and boot menu labels say quick_qubes; the kernel command line
#     (and so cmdline.policy) is the same as main's
#   - live-boot loads the optical drivers after 1 s in a VM
#   - no guest agents (host-to-guest channels) by default
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
I=$R/config/includes.chroot; L=$R/config/package-lists; H=$R/config/hooks/live
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pk=$(cat "$L"/*.list.chroot "$I/usr/share/prestium/build/optional-packages.txt" | sed 's/#.*//' | tr -s ' \t' '\n' | grep .)

## firmware
[ ! -e "$L/prestium-firmware.list.chroot" ] && ok "no firmware package list" || bad "prestium-firmware.list.chroot still there"
[ ! -e "$R/config/archives/prestium-firmware.pref.chroot" ] && [ ! -e "$I/etc/apt/preferences.d/prestium" ] && ok "no firmware pin" || bad "firmware pin still there"
grep -q 'preferences.d/prestium$' "$I/usr/share/prestium/build/perms.txt" && bad "perms.txt lists the removed pin" || ok "perms.txt: no firmware pin"
fw=$(printf '%s\n' "$pk" | grep -E '^(firmware-.*|.*-microcode|iucode-tool|atmel-firmware|wireless-regdb)$' | tr '\n' ' ')
[ -z "$fw" ] && ok "no firmware or microcode in the package lists" || bad "firmware listed: $fw"
grep -q 'firmware-' "$R/config/preseed/prestium.cfg.chroot" && bad "firmware preseeds left" || ok "no firmware preseeds"
grep -q -- '--archive-areas "main contrib" \\' "$R/auto/config" && grep -q -- '--parent-archive-areas "main contrib" \\' "$R/auto/config" \
  && ok "auto/config: archive areas main contrib" || bad "auto/config archive areas"
grep -qx 'LB_ARCHIVE_AREAS="main contrib"' "$R/config/bootstrap" && grep -qx 'LB_PARENT_ARCHIVE_AREAS="main contrib"' "$R/config/bootstrap" \
  && ok "config/bootstrap: archive areas main contrib" || bad "config/bootstrap archive areas"
grep -rh 'non-free-firmware' "$R/auto" "$R/config/bootstrap" "$R/config/archives" "$I/usr/share/prestium/build/apt" "$I/etc/apt" \
  | grep -qv '^[[:space:]]*#' && bad "non-free-firmware still referenced" || ok "no non-free-firmware archive area anywhere"
grep -q -- '--firmware-chroot false \\' "$R/auto/config" && grep -q -- '--firmware-binary false \\' "$R/auto/config" \
  && ok "live-build firmware options explicitly off" || bad "--firmware-chroot/--firmware-binary not false"
grep -qx 'LB_FIRMWARE_CHROOT="false"' "$R/config/binary" && grep -qx 'LB_FIRMWARE_BINARY="false"' "$R/config/binary" \
  && ok "config/binary: firmware off" || bad "config/binary firmware"
G=$H/9980-prestium-vm-no-firmware.hook.chroot
[ -x "$G" ] && sh -n "$G" && ok "hook 9980 present" || bad "hook 9980 missing"
mkdir -p "$T/bin"
cat > "$T/bin/dpkg-query" <<'S'
#!/bin/sh
printf 'ii  tor\nii  linux-image-amd64\n'; [ -n "$EXTRA" ] && printf '%s\n' "$EXTRA"; exit 0
S
chmod +x "$T/bin/dpkg-query"
PATH="$T/bin:$PATH" EXTRA= sh "$G" >/dev/null 2>&1 && ok "hook 9980: passes without firmware" || bad "hook 9980 failed without firmware"
for p in firmware-iwlwifi intel-microcode amd64-microcode iucode-tool; do
  PATH="$T/bin:$PATH" EXTRA="ii  $p" sh "$G" >/dev/null 2>&1 && bad "hook 9980 let $p through" || ok "hook 9980 stops the build on $p"
done
PATH="$T/bin:$PATH" EXTRA="rc  firmware-iwlwifi" sh "$G" >/dev/null 2>&1 && ok "hook 9980: removed (rc) package ignored" || bad "hook 9980: rc package"

## bare-metal hardware support
for p in wpasupplicant wireless-tools modemmanager ppp usb-modeswitch usb-modeswitch-data usbmuxd xserver-xorg-input-wacom \
         libwacom-bin xserver-xorg-video-all xserver-xorg-video-amdgpu xserver-xorg-video-ati xserver-xorg-video-intel \
         xserver-xorg-video-nouveau xserver-xorg-video-radeon xinput firmware-sof-signed; do
  printf '%s\n' "$pk" | grep -qx "$p" && bad "$p still listed" || ok "not listed: $p"
done
for p in xserver-xorg-video-qxl xserver-xorg-video-vmware xserver-xorg-video-fbdev xserver-xorg-video-vesa network-manager macchanger; do
  printf '%s\n' "$pk" | grep -qx "$p" && ok "kept: $p" || bad "$p missing"
done
grep -qE 'ModemManager|wpa_supplicant' "$I/usr/share/prestium/build/systemd-wants.txt" && bad "systemd-wants.txt enables a removed unit" || ok "no ModemManager/wpa_supplicant units enabled"
grep -E '^ln ' "$H/0400-prestium-system.hook.chroot" | grep -qE 'ModemManager|wpa_supplicant' && bad "hook 0400 aliases a removed unit" || ok "no D-Bus aliases for removed units"
grep -qE 'prestium-(brightness|touchpad)' "$I/etc/xdg/labwc/menu.xml" && bad "Brightness/Touchpad still in the menu" || ok "no Brightness/Touchpad menu entries"
## no guest agents: they are host-to-guest channels (clipboard, files, commands)
for p in qemu-guest-agent spice-vdagent virtualbox-guest-utils virtualbox-guest-x11 open-vm-tools open-vm-tools-desktop qubes-core-agent; do
  printf '%s\n' "$pk" | grep -qx "$p" && bad "guest agent listed: $p" || ok "no guest agent: $p"
done

## name and boot menu
grep -q -- '--image-name Prestium-2.1-quick_qubes \\' "$R/auto/config" && grep -qx 'LB_IMAGE_NAME="Prestium-2.1-quick_qubes"' "$R/config/common" \
  && ok "image name Prestium-2.1-quick_qubes" || bad "image name"
grep -qx 'OUT=Prestium-2.1-quick_qubes-amd64.iso' "$R/build.sh" && ok "build.sh writes Prestium-2.1-quick_qubes-amd64.iso" || bad "build.sh ISO name"
grep -qx 'VARIANT_ID=quick_qubes' "$H/0400-prestium-system.hook.chroot" && grep -qx 'VARIANT_ID=$VARIANT_ID' "$H/0400-prestium-system.hook.chroot" \
  && ok "os-release VARIANT_ID=quick_qubes" || bad "os-release variant"
# hook 9000 on a fake binary/ tree, without a chroot (falls back to hook 0400's values)
mkdir -p "$T/w/binary/boot/grub" "$T/w/binary/isolinux" "$T/w/config/hooks/live"
cp "$H/0400-prestium-system.hook.chroot" "$T/w/config/hooks/live/"
sed -e 's|@PRESTIUM_VERSION@|@PRESTIUM_VERSION@|' "$R/config/bootloaders/grub-pc/grub.cfg" > "$T/w/binary/boot/grub/grub.cfg"
sed -e 's|@APPEND_LIVE@|APPEND|' "$R/config/bootloaders/syslinux_common/live.cfg.in" > "$T/w/binary/isolinux/live.cfg"
before=$(grep -hE '^[[:space:]]*(linux|append)' "$T/w/binary/boot/grub/grub.cfg" "$T/w/binary/isolinux/live.cfg")
(cd "$T/w/binary" && sh "$H/9000-prestium-boot-menu.hook.binary") >/dev/null 2>&1 && ok "hook 9000 runs" || bad "hook 9000 failed"
grep -q 'menuentry "Prestium 2.1 quick_qubes (MAC address spoofing off)"' "$T/w/binary/boot/grub/grub.cfg" && ok "GRUB labels: Prestium 2.1 quick_qubes" || bad "GRUB labels: $(grep menuentry "$T/w/binary/boot/grub/grub.cfg" | head -2)"
grep -q 'menu label ^Prestium 2.1 quick_qubes$' "$T/w/binary/isolinux/live.cfg" && ok "isolinux labels: Prestium 2.1 quick_qubes" || bad "isolinux labels"
after=$(grep -hE '^[[:space:]]*(linux|append)' "$T/w/binary/boot/grub/grub.cfg" "$T/w/binary/isolinux/live.cfg")
[ "$before" = "$after" ] && ok "hook 9000 changes labels only, not kernel command lines" || bad "hook 9000 changed a command line"
# the command line is main's (the cmdline guard and its policy are unchanged; test_boot_cmdline_guard.sh checks the match)
A=$(sed -n 's/^APPEND="\(.*\)"$/\1/p' "$R/auto/config")
for t in modprobe.blacklist=libata module.sig_enforce=1 lockdown=confidentiality apparmor=1 security=apparmor init_on_free=1; do
  printf '%s\n' $A | grep -qx "$t" && ok "command line keeps $t" || bad "command line lost $t"; done

## live-boot: optical drivers early in a VM
M=$I/usr/lib/live/boot/9990-main.sh
grep -q 'grep -qw hypervisor /proc/cpuinfo 2>/dev/null && cd_at=1' "$M" && grep -q 'if \[ "$i" -eq "$cd_at" \]' "$M" && grep -qx '			cd_at=8' "$M" \
  && ok "live-boot: optical drivers after 1 s in a VM (8 s on hardware)" || bad "live-boot VM optical probe"
sh -n "$M" && ok "sh -n 9990-main.sh" || bad "9990-main.sh syntax"

[ $fail = 0 ] && echo "quick_qubes: OK"; exit $fail
