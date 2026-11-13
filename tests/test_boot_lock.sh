#!/bin/bash
# 2.1: locked boot menus (hook 9020). On a fake binary/ tree made from Prestium's GRUB template and
# live-build-style entries: every boot entry is --unrestricted, editing needs the superuser whose
# PBKDF2 hash came from the build setting (or a random one), isolinux takes no added options, and an
# entry with apparmor=0 / security=... stops the build. grub-script-check runs when available
# (PRESTIUM_GRUB_SCRIPT_CHECK=<path> or PATH).
# 2.1 (review of 6bf1234): superusers is exported (submenus), the early GRUB configs (per-platform
# grub.cfg, and the EFI image's grub.cfg when mtools and mkfs.msdos are installed) are locked and
# checked, every kernel line is checked token by token against the banned list (shells, init, security
# modules, debug, persistence, findiso=, lockdown= other than integrity) and must have exactly one
# lockdown=integrity, findiso= and loopback.cfg are gone, and shellcheck (when
# installed) finds nothing in the boot hooks.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }; skip(){ echo "SKIP $1"; }
H=$R/config/hooks/live/9020-prestium-boot-lock.hook.binary; PBK=$R/scripts/grub-pbkdf2.py
sh -n "$H" && ok "sh -n 9020" || bad "sh -n 9020"
python3 -m py_compile "$PBK" 2>/dev/null && ok "grub-pbkdf2.py compiles" || bad "grub-pbkdf2.py"
find "$R/scripts" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
grep -q 'grub-password.pbkdf2' "$R/build.sh" && grep -qx '/grub-password.pbkdf2' "$R/.gitignore" && ok "build.sh reads the gitignored hash file" || bad "hash file wiring"
grep -q 'export PRESTIUM_GRUB_PASSWORD_HASH' "$R/build.sh" && ok "build.sh hands the hash to the hooks" || bad "hash not exported"
# no committed boot entry turns AppArmor off or passes security=/init= overrides
if grep -rnE '(apparmor=0|security=[^a]|security=a[^p]|init=/|lsm=|selinux=)' "$R/config/bootloaders" "$R/auto/config"; then bad "a committed boot entry overrides security"; else ok "no apparmor=0/security= overrides in the templates"; fi
SCK=${PRESTIUM_GRUB_SCRIPT_CHECK:-$(command -v grub-script-check || true)}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
APPEND="boot=live dm-verity-root-hash=filesystem.squashfs:$(printf '%064d' 0) dm-verity-oncorruption=panic panic=10 quiet lockdown=integrity apparmor=1 security=apparmor"
EFIOK=; command -v mkfs.msdos >/dev/null && command -v mcopy >/dev/null && command -v mtype >/dev/null && command -v mmd >/dev/null && EFIOK=1
mk(){ rm -rf "$T/b"; mkdir -p "$T/b/binary/boot/grub" "$T/b/binary/isolinux" "$T/b/scripts"; cp "$PBK" "$T/b/scripts/"
  live=$(printf 'menuentry "Prestium 2.1" --hotkey=l {\n\tlinux\t/live/vmlinuz %s findiso=${iso_path}\n\tinitrd\t/live/initrd.img\n}\nmenuentry "Prestium 2.1 (nomodeset)" {\n\tlinux\t/live/vmlinuz %s nomodeset\n\tinitrd\t/live/initrd.img\n}' "$APPEND" "$APPEND")
  awk -v live="$live" '/^@LINUX_LIVE@$/{print live; next} {print}' "$R/config/bootloaders/grub-pc/grub.cfg" \
    | sed -e "s|@KERNEL_LIVE@|/live/vmlinuz|g; s|@INITRD_LIVE@|/live/initrd.img|g; s|@APPEND_LIVE@|$APPEND|g; s|@APPEND_VERIFY_CHECKSUMS@|$APPEND verify-checksums|g" \
          -e 's|@PRESTIUM_VERSION@|2.1|g; s|@ENABLE_INSTALL_MENU@|false|; s|@ENABLE_MEMTEST@|false|; s|@ENABLE_VERIFY_CHECKSUMS@|true|' > "$T/b/binary/boot/grub/grub.cfg"
  printf 'set default=0\nset timeout=3\n' > "$T/b/binary/boot/grub/config.cfg"
  printf 'include menu.cfg\ndefault vesamenu.c32\nprompt 0\ntimeout 30\n' > "$T/b/binary/isolinux/isolinux.cfg"
  printf 'menu tabmsg Press ENTER to boot or TAB to edit a menu entry\n' > "$T/b/binary/isolinux/stdmenu.cfg"
  sed -e "s|@LINUX@|/live/vmlinuz|; s|@INITRD@|/live/initrd.img|; s|@APPEND_LIVE@|$APPEND|; s|@APPEND_LIVE_FAILSAFE@|$APPEND nomodeset|; s|@FLAVOUR@|amd64|; s|@PRESTIUM_VERSION@|2.1|" \
    "$R/config/bootloaders/syslinux_common/live.cfg.in" > "$T/b/binary/isolinux/live.cfg"
  echo "source /boot/grub/grub.cfg" > "$T/b/binary/boot/grub/loopback.cfg"
  mkdir -p "$T/b/binary/boot/grub/x86_64-efi"
  printf 'insmod part_acorn\ninsmod part_amiga\nsource /boot/grub/grub.cfg\n' > "$T/b/binary/boot/grub/x86_64-efi/grub.cfg"
  if [ -n "$EFIOK" ]; then
    printf 'search --set=root --file /.disk/info\nset prefix=($root)/boot/grub\nconfigfile ($root)/boot/grub/grub.cfg\n' > "$T/efi.cfg"
    mkfs.msdos -C "$T/b/binary/boot/grub/efi.img" 256 >/dev/null && mmd -i "$T/b/binary/boot/grub/efi.img" ::boot ::boot/grub \
      && mcopy -i "$T/b/binary/boot/grub/efi.img" "$T/efi.cfg" ::boot/grub/grub.cfg
  fi; }
run(){ (cd "$T/b/binary" && sh "$H") > "$T/out" 2>&1; }
PW='a long test passphrase'
HASH=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import importlib; m = importlib.import_module("grub-pbkdf2"); print(m.make(sys.argv[2].encode()))' "$R/scripts" "$PW" 2>/dev/null)
[ -n "$HASH" ] || HASH=$(python3 -I - "$PW" <<'PY'
import hashlib, secrets, sys
s = secrets.token_bytes(64); print("grub.pbkdf2.sha512.10000.%s.%s" % (s.hex().upper(), hashlib.pbkdf2_hmac("sha512", sys.argv[1].encode(), s, 10000, 64).hex().upper()))
PY
)
find "$R/scripts" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
mk; if PRESTIUM_GRUB_PASSWORD_HASH=$HASH run; then ok "9020 with a build-time hash"; else bad "9020 failed: $(cat "$T/out")"; fi
G=$T/b/binary/boot/grub/grub.cfg
[ "$(sed -n 1p "$G")" = "source /boot/grub/config.cfg" ] && grep -qx 'set superusers="prestium"' "$G" && ok "superuser set right after config.cfg" || bad "superusers"
grep -qx "password_pbkdf2 prestium $HASH" "$G" && ok "the build-time hash is used" || bad "hash not in grub.cfg"
python3 -I - "$PW" "$(awk '/^password_pbkdf2 /{print $3}' "$G")" <<'PY' && ok "the hash checks the password (PBKDF2-HMAC-SHA512)" || bad "PBKDF2 mismatch"
import hashlib, sys
p = sys.argv[2].split("."); it, salt, key = int(p[3]), bytes.fromhex(p[4]), p[5]
sys.exit(0 if hashlib.pbkdf2_hmac("sha512", sys.argv[1].encode(), salt, it, 64).hex().upper() == key else 1)
PY
n_all=$(grep -cE '^[[:space:]]*(menuentry|submenu)[[:space:]]' "$G"); n_unr=$(grep -cE '^[[:space:]]*(menuentry|submenu)[[:space:]].*--unrestricted' "$G")
[ "$n_unr" = $((n_all - 1)) ] && ok "$n_unr of $n_all entries unrestricted (all but firmware settings)" || bad "unrestricted: $n_unr of $n_all"
grep -E 'menuentry "UEFI Firmware Settings"' "$G" | grep -qv -- '--unrestricted' && ok "firmware settings need the superuser" || bad "fwsetup unrestricted"
grep -E 'menuentry "Prestium 2.1" --hotkey=l --unrestricted \{' "$G" >/dev/null && ok "default entry boots without a password" || bad "default entry"
grep -qx 'allowoptions 0' "$T/b/binary/isolinux/isolinux.cfg" && grep -qx 'noescape 1' "$T/b/binary/isolinux/isolinux.cfg" && ok "isolinux: allowoptions 0, noescape 1" || bad "isolinux not locked"
grep -q 'TAB to edit' "$T/b/binary/isolinux/stdmenu.cfg" && bad "isolinux still offers TAB editing" || ok "isolinux: no TAB-to-edit hint"
[ "$(cat "$T/b/prestium-bootlock.tmp")" = build-setting ] && ok "manifest mode: build-setting" || bad "bootlock mode"
# superusers exported before the first submenu (GRUB submenus only see exported variables)
awk '/^export superusers$/{e=NR} /^[[:space:]]*submenu[[:space:]]/{if(!s)s=NR} END{exit !(e && s && e<s)}' "$G" && ok "superusers exported before the first submenu" || bad "superusers not exported before submenus"
awk '/^[[:space:]]*submenu .Utilities/{u=1} u && /menuentry "Verify integrity/{print; exit}' "$G" | grep -q -- '--unrestricted' && ok "entries inside a submenu are --unrestricted (boot only)" || bad "submenu entry"
grep -q 'findiso=' "$G" && bad "findiso= still on a boot entry" || ok "findiso= removed (no ISO-file boot)"
[ ! -e "$T/b/binary/boot/grub/loopback.cfg" ] && ok "loopback.cfg removed" || bad "loopback.cfg still there"
E2=$T/b/binary/boot/grub/x86_64-efi/grub.cfg
head -4 "$E2" | grep -qx 'export superusers' && grep -qx "password_pbkdf2 prestium $HASH" "$E2" && tail -1 "$E2" | grep -qx 'source /boot/grub/grub.cfg' && ok "per-platform grub.cfg locked before it loads grub.cfg" || bad "x86_64-efi/grub.cfg not locked"
if [ -n "$SCK" ]; then "$SCK" "$E2" >/dev/null 2>&1 && ok "grub-script-check: per-platform grub.cfg parses" || bad "per-platform grub.cfg does not parse"; fi
if [ -n "$EFIOK" ]; then
  mtype -i "$T/b/binary/boot/grub/efi.img" ::boot/grub/grub.cfg > "$T/efi.out"
  head -4 "$T/efi.out" | grep -qx 'export superusers' && grep -qx "password_pbkdf2 prestium $HASH" "$T/efi.out" && grep -q '^configfile (\$root)/boot/grub/grub.cfg' "$T/efi.out" && ok "EFI image grub.cfg locked (superuser, exported) before it loads grub.cfg" || bad "efi.img grub.cfg: $(cat "$T/efi.out")"
  if [ -n "$SCK" ]; then "$SCK" "$T/efi.out" >/dev/null 2>&1 && ok "grub-script-check: EFI image grub.cfg parses" || bad "EFI grub.cfg does not parse"; fi
else skip "mtools/mkfs.msdos missing: EFI image grub.cfg not tested"; fi
grep -q 'command -v mcopy' "$R/build.sh" && ok "build.sh needs mtools" || bad "build.sh: no mtools check"
if [ -n "$SCK" ] && "$SCK" "$G" >/dev/null 2>&1; then ok "grub-script-check: grub.cfg parses"; elif [ -n "$SCK" ]; then bad "grub-script-check: $("$SCK" "$G" 2>&1 | head -3)"; else skip "grub-script-check not available"; fi
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "9020 ran twice on one grub.cfg" || ok "9020 refuses a second run (superusers already set)"
mk; if env -u PRESTIUM_GRUB_PASSWORD_HASH sh -c 'cd "$1" && sh "$2"' _ "$T/b/binary" "$H" > "$T/out" 2>&1; then ok "unset hash: builds"; else bad "unset: $(cat "$T/out")"; fi
grep -q '^W: PRESTIUM_GRUB_PASSWORD_HASH is not set' "$T/out" && ok "unset hash: warns" || bad "no warning"
h2=$(awk '/^password_pbkdf2 /{print $3}' "$G"); python3 -I "$PBK" --check "$h2" && [ "$h2" != "$HASH" ] && ok "unset hash: a random superuser hash locks the menu" || bad "random hash"
[ "$(cat "$T/b/prestium-bootlock.tmp")" = random ] && ok "manifest mode: random" || bad "bootlock mode random"
for badh in "" "grub.pbkdf2.sha512.100.$(printf '%0128d' 0).$(printf '%0128d' 0)" "grub.pbkdf2.sha512.10000.abc.def" 'x" ; insmod shell'; do
  [ -z "$badh" ] && continue; mk
  PRESTIUM_GRUB_PASSWORD_HASH=$badh run && bad "accepted a bad hash: $badh" || ok "refuses a malformed hash (${badh:0:30}...)"; done
for o in apparmor=0 "security=selinux" "security= " "init=/bin/sh" "lsm=landlock" "apparmor=1x" rdinit=/bin/sh selinux=1 enforcing=0 \
         single s S 1 -b emergency rescue break break=premount rd.break rd.shell rd.emergency rd.debug rd.systemd.unit=emergency.target \
         systemd.unit=rescue.target systemd.debug-shell systemd.debug_shell=1 systemd.wants=debug-shell.service "systemd.run=/bin/sh" \
         systemd.mask=apparmor.service systemd.confirm_spawn=1 systemd.setenv=X=1 debug debug=1 persistence persistence-label=x \
         "findiso=/x.iso" fromiso=/x.iso live-media=/dev/sdb bootfrom=/dev/sdb module.sig_enforce=0 panic=0 dm-verity-oncorruption=ignore lockdown=none lockdown=confidentiality; do
  mk; sed -i "0,/boot=live /s|boot=live |boot=live $o |" "$G"
  PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted an entry with '$o'" || ok "stops on an entry with '$o'"; done
mk; sed -i "0,/ panic=10/s| panic=10||" "$G"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted a live entry without panic=10" || ok "stops on a live entry without panic=10"
mk; sed -i "0,/ lockdown=integrity/s| lockdown=integrity||" "$G"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted a live entry without lockdown=integrity" || ok "stops on a live entry without lockdown=integrity"
mk; sed -i "0,/lockdown=integrity/s|lockdown=integrity|lockdown=integrity lockdown=integrity|" "$G"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted a live entry with two lockdown=integrity" || ok "stops on a live entry with two lockdown=integrity"
mk; sed -i "s|insmod part_acorn|insmod part_acorn\nlinux /live/vmlinuz boot=live init=/bin/sh|" "$T/b/binary/boot/grub/x86_64-efi/grub.cfg"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted a banned option in a per-platform grub.cfg" || ok "stops on a banned option in a per-platform grub.cfg"
if [ -n "$EFIOK" ]; then
  mk; printf 'linux /live/vmlinuz boot=live apparmor=0\n' >> "$T/efi.cfg"; mcopy -o -i "$T/b/binary/boot/grub/efi.img" "$T/efi.cfg" ::boot/grub/grub.cfg
  PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted a banned option in the EFI image" || ok "stops on a banned option in the EFI image grub.cfg"
  mk; mkdir -p "$T/nomtools"
  # /usr/bin also has mtype (Debian merged /bin), so drop whole PATH dirs that contain it and keep
  # only the tools hook 9020 needs besides mtools
  for b in python3 grep awk gawk mawk sed mv rm cat tr head cut touch chmod mkdir printf echo ln; do
    c=$(command -v "$b") || continue
    [ -e "$T/nomtools/$b" ] || ln -s "$c" "$T/nomtools/$b"
  done
  (cd "$T/b/binary" && PATH=$T/nomtools PRESTIUM_GRUB_PASSWORD_HASH=$HASH /bin/sh "$H") > "$T/out" 2>&1 \
    && bad "EFI image without mtools accepted" || { grep -q 'mtools' "$T/out" && ok "EFI image but no mtools: stops"; } || bad "no-mtools: $(cat "$T/out")"
fi
mk; sed -i "s|apparmor=1|apparmor=0|" "$T/b/binary/isolinux/live.cfg"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted isolinux apparmor=0" || ok "stops on isolinux apparmor=0"
mk; sed -i "s| lockdown=integrity||" "$T/b/binary/isolinux/live.cfg"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted isolinux without lockdown=integrity" || ok "stops on isolinux without lockdown=integrity"
# templates: no banned token in a committed boot entry (also checked rendered, through 9020 above)
if grep -nE '(^|[[:space:]])(single|emergency|rescue|debug|persistence[^[:space:]]*|rdinit=[^[:space:]]*|findiso=[^[:space:]]*|systemd\.(unit|wants|run|debug[-_]shell)[^[:space:]]*|break(=[^[:space:]]*)?)([[:space:]]|$)' \
  "$R/config/bootloaders/grub-pc/grub.cfg" "$R/config/bootloaders/syslinux_common/live.cfg.in" | grep -v '^[^:]*:[0-9]*:[[:space:]]*#'; then
  bad "a template boot entry has a banned option"; else ok "templates: no banned options"; fi
SC=$(command -v shellcheck || true)
if [ -n "$SC" ]; then
  "$SC" -S style "$H" "$R/config/hooks/live/0405-prestium-verity.hook.chroot" "$R/config/hooks/live/9010-prestium-verity-boot.hook.binary" \
    "$R/config/includes.chroot/etc/initramfs-tools/hooks/prestium-verity" && "$SC" -s sh -S style "$R/config/includes.chroot/usr/lib/live/boot/9989-prestium-verity.sh" \
    && ok "shellcheck (all levels): boot lock and dm-verity hooks clean" || bad "shellcheck findings in the boot hooks"
else skip "shellcheck not installed"; fi
exit $fail
