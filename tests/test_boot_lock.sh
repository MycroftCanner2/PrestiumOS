#!/bin/bash
# 2.1: locked boot menus (hook 9020). On a fake binary/ tree made from Prestium's GRUB template and
# live-build-style entries: every boot entry is --unrestricted, editing needs the superuser whose
# PBKDF2 hash came from the build setting (or a random one), isolinux takes no added options, and an
# entry with apparmor=0 / security=... stops the build. grub-script-check runs when available
# (PRESTIUM_GRUB_SCRIPT_CHECK=<path> or PATH).
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
APPEND="boot=live dm-verity-root-hash=filesystem.squashfs:$(printf '%064d' 0) quiet apparmor=1 security=apparmor"
mk(){ rm -rf "$T/b"; mkdir -p "$T/b/binary/boot/grub" "$T/b/binary/isolinux" "$T/b/scripts"; cp "$PBK" "$T/b/scripts/"
  live=$(printf 'menuentry "Prestium 2.1" --hotkey=l {\n\tlinux\t/live/vmlinuz %s findiso=${iso_path}\n\tinitrd\t/live/initrd.img\n}\nmenuentry "Prestium 2.1 (nomodeset)" {\n\tlinux\t/live/vmlinuz %s nomodeset\n\tinitrd\t/live/initrd.img\n}' "$APPEND" "$APPEND")
  awk -v live="$live" '/^@LINUX_LIVE@$/{print live; next} {print}' "$R/config/bootloaders/grub-pc/grub.cfg" \
    | sed -e "s|@KERNEL_LIVE@|/live/vmlinuz|g; s|@INITRD_LIVE@|/live/initrd.img|g; s|@APPEND_LIVE@|$APPEND|g; s|@APPEND_VERIFY_CHECKSUMS@|$APPEND verify-checksums|g" \
          -e 's|@PRESTIUM_VERSION@|2.1|g; s|@ENABLE_INSTALL_MENU@|false|; s|@ENABLE_MEMTEST@|false|; s|@ENABLE_VERIFY_CHECKSUMS@|true|' > "$T/b/binary/boot/grub/grub.cfg"
  printf 'set default=0\nset timeout=3\n' > "$T/b/binary/boot/grub/config.cfg"
  printf 'include menu.cfg\ndefault vesamenu.c32\nprompt 0\ntimeout 30\n' > "$T/b/binary/isolinux/isolinux.cfg"
  printf 'menu tabmsg Press ENTER to boot or TAB to edit a menu entry\n' > "$T/b/binary/isolinux/stdmenu.cfg"
  sed -e "s|@LINUX@|/live/vmlinuz|; s|@INITRD@|/live/initrd.img|; s|@APPEND_LIVE@|$APPEND|; s|@APPEND_LIVE_FAILSAFE@|$APPEND nomodeset|; s|@FLAVOUR@|amd64|; s|@PRESTIUM_VERSION@|2.1|" \
    "$R/config/bootloaders/syslinux_common/live.cfg.in" > "$T/b/binary/isolinux/live.cfg"; }
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
if [ -n "$SCK" ] && "$SCK" "$G" >/dev/null 2>&1; then ok "grub-script-check: grub.cfg parses"; elif [ -n "$SCK" ]; then bad "grub-script-check: $("$SCK" "$G" 2>&1 | head -3)"; else skip "grub-script-check not available"; fi
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "9020 ran twice on one grub.cfg" || ok "9020 refuses a second run (superusers already set)"
mk; if env -u PRESTIUM_GRUB_PASSWORD_HASH sh -c 'cd "$1" && sh "$2"' _ "$T/b/binary" "$H" > "$T/out" 2>&1; then ok "unset hash: builds"; else bad "unset: $(cat "$T/out")"; fi
grep -q '^W: PRESTIUM_GRUB_PASSWORD_HASH is not set' "$T/out" && ok "unset hash: warns" || bad "no warning"
h2=$(awk '/^password_pbkdf2 /{print $3}' "$G"); python3 -I "$PBK" --check "$h2" && [ "$h2" != "$HASH" ] && ok "unset hash: a random superuser hash locks the menu" || bad "random hash"
[ "$(cat "$T/b/prestium-bootlock.tmp")" = random ] && ok "manifest mode: random" || bad "bootlock mode random"
for badh in "" "grub.pbkdf2.sha512.100.$(printf '%0128d' 0).$(printf '%0128d' 0)" "grub.pbkdf2.sha512.10000.abc.def" 'x" ; insmod shell'; do
  [ -z "$badh" ] && continue; mk
  PRESTIUM_GRUB_PASSWORD_HASH=$badh run && bad "accepted a bad hash: $badh" || ok "refuses a malformed hash (${badh:0:30}...)"; done
for o in apparmor=0 "security=selinux" "security= " "init=/bin/sh" "lsm=landlock" "apparmor=1x"; do
  mk; sed -i "0,/boot=live /s|boot=live |boot=live $o |" "$G"
  PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted an entry with '$o'" || ok "stops on an entry with '$o'"; done
mk; sed -i "s|quiet apparmor=1|quiet apparmor=0|" "$T/b/binary/isolinux/live.cfg"
PRESTIUM_GRUB_PASSWORD_HASH=$HASH run && bad "accepted isolinux apparmor=0" || ok "stops on isolinux apparmor=0"
exit $fail
