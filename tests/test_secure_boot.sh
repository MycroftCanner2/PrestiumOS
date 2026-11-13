#!/bin/bash
# 2.1 (Secure Boot): the UEFI path is Debian's signed boot chain (shim -> signed GRUB -> signed kernel),
# as in Tails, and the build proves it (hook 9040).
#   - auto/config / config/binary: --uefi-secure-boot enable, grub-efi + syslinux, the trixie
#     linux-image-amd64 (Debian's signed kernel); no package list or pin brings another kernel, an
#     -unsigned one, headers or DKMS modules; no hook builds a kernel module
#   - the CA certificates in thirdparty/keys/secure-boot/ are the ones hook 9040 pins; build.sh and
#     BUILDING.md ask for sbsigntool
#   - hook 9040 on a fake build tree refuses LB_UEFI_SECURE_BOOT=auto, a swapped CA certificate, an
#     extra EFI program, efi.img differing from the ISO tree or holding more, and unsigned files.
#     With Debian's real packages (PRESTIUM_SB_DEBS=<dir with shim-signed, grub-efi-amd64-signed,
#     linux-image-*-amd64 (signed) and optionally shim-helpers-amd64-signed, grub-efi-amd64-unsigned .debs>,
#     or live-build's cache/packages.{binary,chroot}) it accepts the real chain and refuses: shim with
#     its signature removed or self-signed, Debian's GRUB or MokManager as bootx64.efi, the unsigned
#     monolithic GRUB, MokManager as grubx64.efi, a kernel with its signature removed, a kernel from an
#     -unsigned or non-linux-signed package, a kernel not from the chroot (skipped without the .debs)
#   - efi-inspect.py reads a GRUB image's prefix, modules and the disable-shim-lock object
#   - prestium-safety-notify: information (not an alert) for Secure Boot off; a "Protection NOT
#     active" alert when kernel lockdown is [none] or the lockdown file is missing
#   (needs sbsigntool, mtools, dosfstools, openssl; skipped without them)
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }; skip(){ echo "SKIP $1"; }
H=$R/config/hooks/live/9040-prestium-secure-boot.hook.binary; INS=$R/scripts/efi-inspect.py
K=$R/thirdparty/keys/secure-boot; N=$R/config/includes.chroot/usr/local/bin/prestium-safety-notify
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

## configuration
sh -n "$H" && ok "sh -n hook 9040" || bad "sh -n hook 9040"
[ -x "$H" ] && [ -x "$INS" ] && ok "hook and efi-inspect.py executable" || bad "not executable"
grep -qE '^[[:space:]]*--uefi-secure-boot enable \\$' "$R/auto/config" && ok "auto/config: --uefi-secure-boot enable" || bad "auto/config: Secure Boot not enabled"
grep -qE '^[[:space:]]*--bootloaders "grub-efi,syslinux" \\$' "$R/auto/config" && grep -qx 'LB_BOOTLOADER_BIOS="syslinux"' "$R/config/binary" \
  && grep -qx 'LB_BOOTLOADER_EFI="grub-efi"' "$R/config/binary" && ok "boot loaders: grub-efi (UEFI) and syslinux (BIOS, unchanged)" || bad "boot loaders changed"
grep -qx 'LB_UEFI_SECURE_BOOT="enable"' "$R/config/binary" && ok "config/binary: LB_UEFI_SECURE_BOOT=enable" || bad "config/binary: Secure Boot not enable"
grep -qE '^[[:space:]]*--linux-flavours amd64 \\$' "$R/auto/config" && grep -qx 'LB_LINUX_PACKAGES="linux-image"' "$R/config/chroot" \
  && grep -qx 'LB_LINUX_FLAVOURS_WITH_ARCH="amd64"' "$R/config/chroot" && ok "kernel: linux-image-amd64 (Debian's signed kernel in trixie)" || bad "kernel selection changed"
L=$(grep -hvE '^[[:space:]]*#' "$R"/config/package-lists/*.list.chroot | tr ' \t' '\n\n' | grep .)
k=$(printf '%s\n' "$L" | grep -E '^(linux-(image|headers|kbuild|source)|.*-dkms$|dkms$|module-assistant$|.*-modules-.*)' | grep -vx 'libpam-modules-bin')
[ -z "$k" ] && ok "package lists: no extra kernel, headers or DKMS modules" || bad "package lists bring kernels or modules: $k"
printf '%s\n' "$L" | grep -qE '^(shim-signed|grub-efi-amd64-signed|grub-efi-amd64)$' && bad "shim/GRUB in the live system's package lists (live-build installs them for the binary stage only)" || ok "shim and signed GRUB not in the live system (binary stage only)"
grep -hE '^Package:' "$R"/config/archives/*.pref* | grep -qE '[[:space:]]linux-' && bad "an apt pin names a linux-* package" || ok "no apt pin moves the kernel (e.g. to backports)"
grep -lE '\bdkms\b|make[^|;]*\bmodules\b|\.ko\b|/lib/modules/[^ ]*/(updates|extra)' "$R"/config/hooks/live/*.chroot >/dev/null 2>&1 && bad "a hook builds or installs a kernel module" || ok "no hook builds or installs a kernel module (lurch is userspace)"
grep -qx 'module.sig_enforce=1' <(tr ' ' '\n' <<<"$(sed -n 's/^APPEND="\(.*\)"$/\1/p' "$R/auto/config")") && ok "module.sig_enforce=1 kept" || bad "module.sig_enforce=1 gone"
grep -qx 'lockdown=integrity' <(tr ' ' '\n' <<<"$(sed -n 's/^APPEND="\(.*\)"$/\1/p' "$R/auto/config")") && ok "lockdown=integrity on the command line" || bad "lockdown=integrity gone"
grep -q 'command -v sbverify' "$R/build.sh" && ok "build.sh checks for sbverify" || bad "build.sh does not check sbverify"
grep -q 'cryptsetup-bin sbsigntool' "$R/BUILDING.md" && ok "BUILDING.md requirements: sbsigntool" || bad "BUILDING.md lacks sbsigntool"
if command -v openssl >/dev/null; then
  for c in microsoft-uefi-ca-2011 microsoft-uefi-ca-2023 debian-secure-boot-ca; do
    f=$(openssl x509 -in "$K/$c.pem" -noout -fingerprint -sha256 | sed 's/^.*=//; s/://g' | tr 'A-F' 'a-f')
    grep -qx "pin $c.pem $f" "$H" && ok "hook pins $c.pem ($f)" || bad "$c.pem is not the one hook 9040 pins"
  done
  openssl x509 -in "$K/debian-secure-boot-ca.pem" -noout -subject | grep -q 'CN *= *Debian Secure Boot CA' && ok "Debian Secure Boot CA subject" || bad "Debian CA subject"
else skip "openssl missing: certificate pins"; fi
# the GRUB commands Prestium's configs use (hooks 9020, 9030, live-build's config.cfg) must be built in
for m in password_pbkdf2 regexp search search_fs_file sleep reboot echo test configfile normal linux efifwsetup; do
  grep -qE "^for m in .*\b$m\b" "$H" || bad "hook 9040 does not require the built-in module $m"; done
grep -q 'regexp --set' "$R/config/hooks/live/9030-prestium-boot-cmdline.hook.binary" && grep -q 'password_pbkdf2' "$R/config/hooks/live/9020-prestium-boot-lock.hook.binary" \
  && ok "hook 9040 requires every module the menu lock and the marker search use" || bad "menu lock / marker search changed"

## efi-inspect.py on a synthetic GRUB image (prefix, module, disable-shim-lock object)
python3 - "$T/fake-grub.efi" <<'PY'
import struct, sys
def obj(t, data):
    data += b"\0" * (-len(data) % 8)
    return struct.pack("<II", t, 8 + len(data)) + data
# a minimal ELF64 with a .modname section saying "normal"
names = b"\0.shstrtab\0.modname\0"; modname = b"normal\0"
eh = 64; shoff = eh + len(names) + len(modname); shoff += -shoff % 8
elf = bytearray(b"\x7fELF\x02\x01\x01" + b"\0" * 9)
elf += struct.pack("<HHIQQQIHHHHHH", 1, 62, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 3, 1)
elf += names + modname; elf += b"\0" * (shoff - len(elf))
sh = lambda n, t, off, size: struct.pack("<IIQQQQIIQQ", n, t, 0, 0, off, size, 0, 0, 1, 0)
elf += sh(0, 0, 0, 0) + sh(1, 3, eh, len(names)) + sh(11, 1, eh + len(names), len(modname))
body = obj(0, bytes(elf)) + obj(3, b"/boot/grub\0") + obj(6, b"")
mods = struct.pack("<IIQQ", 0x676D696D, 0, 24, 24 + len(body)) + body
mods += b"\0" * (-len(mods) % 512)
pe = bytearray(512)
pe[0:2] = b"MZ"; struct.pack_into("<I", pe, 0x3C, 64)
pe[64:68] = b"PE\0\0"; struct.pack_into("<HHIIIHH", pe, 68, 0x8664, 1, 0, 0, 0, 240, 0x22)
struct.pack_into("<H", pe, 88, 0x20B)
s = 88 + 240
pe[s:s + 8] = b"mods\0\0\0\0"; struct.pack_into("<IIII", pe, s + 8, len(mods), 0x1000, len(mods), 512)
open(sys.argv[1], "wb").write(bytes(pe) + mods)
PY
o=$(python3 -I "$INS" grub "$T/fake-grub.efi" 2>&1)
case $o in *"module normal"*"prefix /boot/grub"*"disable-shim-lock"*) ok "efi-inspect.py: modules, prefix and the disable-shim-lock object";; *) bad "efi-inspect.py grub: $o";; esac
printf 'MZ not really a PE' > "$T/junk.efi"; python3 -I "$INS" grub "$T/junk.efi" >/dev/null 2>&1; [ $? = 2 ] && ok "efi-inspect.py: refuses a non-PE file" || bad "efi-inspect.py accepted junk"

## hook 9040 on a fake build tree
need=; for t in sbverify mcopy mdir openssl; do command -v "$t" >/dev/null || need="$need $t"; done
MKFS=$(command -v mkfs.msdos || command -v /usr/sbin/mkfs.msdos || command -v /sbin/mkfs.msdos || true); [ -n "$MKFS" ] || need="$need mkfs.msdos"
if [ -n "$need" ]; then skip "hook 9040 cases: missing$need (apt install sbsigntool mtools dosfstools openssl)"; else
W=$T/build
# $1 bootx64 $2 grubx64 (files); the kernel comes from $KSRC (optional); builds binary/ + chroot/ + config
mktree() {
  rm -rf "$W"; mkdir -p "$W/binary/EFI/boot" "$W/binary/boot/grub" "$W/binary/live" "$W/config" "$W/scripts" "$W/thirdparty/keys" "$W/chroot/boot" "$W/chroot/var/lib/dpkg/info"
  cp "$R/config/binary" "$W/config/"; cp "$INS" "$W/scripts/"; cp -r "$K" "$W/thirdparty/keys/"
  cp "$1" "$W/binary/EFI/boot/bootx64.efi"; cp "$2" "$W/binary/EFI/boot/grubx64.efi"
  printf 'search --set=root --file /.disk/prestium-0\nconfigfile ($root)/boot/grub/grub.cfg\n' > "$T/efi-grub.cfg"
  "$MKFS" -C "$W/binary/boot/grub/efi.img" 8192 >/dev/null
  mmd -i "$W/binary/boot/grub/efi.img" ::EFI ::EFI/boot ::boot ::boot/grub
  mcopy -i "$W/binary/boot/grub/efi.img" "$1" ::EFI/boot/bootx64.efi; mcopy -i "$W/binary/boot/grub/efi.img" "$2" ::EFI/boot/grubx64.efi
  mcopy -i "$W/binary/boot/grub/efi.img" "$T/efi-grub.cfg" ::boot/grub/grub.cfg
  if [ -n "${KSRC:-}" ]; then
    cp "$KSRC" "$W/chroot/boot/vmlinuz-$KVER"; cp "$KSRC" "$W/binary/live/vmlinuz-$KVER"
    printf '/.\n/boot\n/boot/vmlinuz-%s\n' "$KVER" > "$W/chroot/var/lib/dpkg/info/$KPKG.list"
    printf '%s  boot/vmlinuz-%s\n' "$(md5sum < "$KSRC" | cut -d' ' -f1)" "$KVER" > "$W/chroot/var/lib/dpkg/info/$KPKG.md5sums"
    printf 'Package: %s\nStatus: install ok installed\nSource: %s\nVersion: 1\n\n' "$KPKG" "$KSOURCE" > "$W/chroot/var/lib/dpkg/status"
  else : > "$W/chroot/var/lib/dpkg/status"; fi
}
run9040() { (cd "$W/binary" && PATH="$PATH:/usr/sbin:/sbin" sh "$H") 2>&1; }
refuse() { # $1 label, $2 expected message part
  if o=$(run9040); then bad "hook accepted: $1"; else case $o in *"$2"*) ok "hook refuses: $1";; *) bad "hook refused $1 for another reason: $o";; esac; fi; }
printf 'not an EFI program\n' > "$T/text.efi"
mktree "$T/text.efi" "$T/text.efi"
sed -i 's/^LB_UEFI_SECURE_BOOT=.*/LB_UEFI_SECURE_BOOT="auto"/' "$W/config/binary"; refuse 'LB_UEFI_SECURE_BOOT="auto"' 'LB_UEFI_SECURE_BOOT="enable"'
mktree "$T/text.efi" "$T/text.efi"; cp "$K/microsoft-uefi-ca-2011.pem" "$W/thirdparty/keys/secure-boot/debian-secure-boot-ca.pem"; refuse "a swapped CA certificate" "not the pinned certificate"
mktree "$T/text.efi" "$T/text.efi"; cp "$T/text.efi" "$W/binary/EFI/boot/mmx64.efi"; refuse "an extra EFI program in the ISO tree" "not exactly EFI/boot/bootx64.efi"
mktree "$T/text.efi" "$T/text.efi"; mkdir -p "$W/binary/EFI/BOOT2"; cp "$T/text.efi" "$W/binary/EFI/BOOT2/BOOTIA32.EFI"; refuse "an extra (upper-case) EFI program" "not exactly EFI/boot/bootx64.efi"
mktree "$T/text.efi" "$T/text.efi"; mcopy -i "$W/binary/boot/grub/efi.img" "$T/text.efi" ::EFI/boot/fbx64.efi; refuse "an extra file in efi.img" "does not hold exactly"
mktree "$T/text.efi" "$T/text.efi"; echo x >> "$W/binary/EFI/boot/grubx64.efi"; refuse "efi.img's GRUB differs from the ISO tree's" "differs from EFI/boot/grubx64.efi"
mktree "$T/text.efi" "$T/text.efi"; refuse "an unsigned (non-PE) bootx64.efi" "not signed for the Microsoft UEFI CA"
mktree "$T/text.efi" "$T/text.efi"; cp "$W/binary/boot/grub/efi.img" "$W/binary/efi.img"; o=$(run9040)
[ ! -e "$W/binary/efi.img" ] && case $o in *"removed live-build's unused efi.img"*) true;; *) false;; esac && ok "hook removes live-build's unused efi.img from the ISO root" || bad "root efi.img kept: $o"
rm -f "$W/binary/boot/grub/efi.img"; refuse "no efi.img" "efi.img missing"

## with Debian's real packages
DEBS=${PRESTIUM_SB_DEBS:-}
findeb() { local d f; for d in $DEBS "$R/cache/packages.binary" "$R/cache/packages.chroot"; do [ -d "$d" ] || continue
  for f in "$d"/$1; do [ -f "$f" ] && { echo "$f"; return 0; }; done; done; return 1; }
SHIMD=$(findeb 'shim-signed_*_amd64.deb'); GRUBD=$(findeb 'grub-efi-amd64-signed_*_amd64.deb'); KD=
for d in $DEBS "$R/cache/packages.chroot"; do for f in "$d"/linux-image-[0-9]*-amd64_*_amd64.deb; do [ -f "$f" ] && KD=$f; done; done
if [ -z "$SHIMD" ] || [ -z "$GRUBD" ] || [ -z "$KD" ]; then
  skip "real Debian chain cases: set PRESTIUM_SB_DEBS to a directory with shim-signed, grub-efi-amd64-signed and linux-image-*-amd64 .debs"
else
  X=$T/x; mkdir -p "$X"; for d in "$SHIMD" "$GRUBD" "$KD"; do dpkg-deb -x "$d" "$X"; done
  SHIM=$X/usr/lib/shim/shimx64.efi.signed; GRUB=$X/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed
  KSRC=$(ls "$X"/boot/vmlinuz-* | head -n1); KVER=${KSRC##*/vmlinuz-}; KPKG=$(dpkg-deb -f "$KD" Package); KSOURCE=$(dpkg-deb -f "$KD" Source)
  echo "     using $(basename "$SHIMD"), $(basename "$GRUBD"), $(basename "$KD") (Source: $KSOURCE)"
  mktree "$SHIM" "$GRUB"
  if o=$(run9040); then case $o in *"P: Secure Boot chain: Debian's shim"*"1 Debian-signed kernel"*) ok "hook accepts Debian's real chain: ${o##*P: }";; *) bad "hook output: $o";; esac
  else bad "hook refused Debian's real chain: $o"; fi
  if command -v sbattach >/dev/null && command -v sbsign >/dev/null; then
    # shim is signed twice (Microsoft UEFI CA 2011 and 2023): remove every signature
    nosig() { cp "$1" "$2"; local _; for _ in 1 2 3 4; do sbverify --list "$2" 2>/dev/null | grep -q '^signature 1' || return 0; sbattach --remove "$2" >/dev/null 2>&1 || return 1; done; return 1; }
    nosig "$SHIM" "$T/shim-nosig.efi" && ok "fixture: shim without signatures" || bad "fixture: signatures not removed"
    mktree "$T/shim-nosig.efi" "$GRUB"; refuse "shim with its signature removed" "not signed for the Microsoft UEFI CA"
    openssl req -x509 -newkey rsa:2048 -nodes -subj "/CN=Not Microsoft" -days 2 -keyout "$T/k.pem" -out "$T/c.pem" >/dev/null 2>&1
    sbsign --key "$T/k.pem" --cert "$T/c.pem" --output "$T/shim-self.efi" "$T/shim-nosig.efi" >/dev/null 2>&1
    mktree "$T/shim-self.efi" "$GRUB"; refuse "a self-signed shim (Debian CA still built in)" "not signed for the Microsoft UEFI CA"
    nosig "$KSRC" "$T/k-nosig"; KS0=$KSRC; KSRC=$T/k-nosig
    mktree "$SHIM" "$GRUB"; refuse "a kernel with its signature removed" "not signed under the Debian Secure Boot CA"; KSRC=$KS0
  else skip "sbattach/sbsign missing: stripped and self-signed cases"; fi
  mktree "$GRUB" "$GRUB"; refuse "Debian's GRUB as bootx64.efi (not Microsoft-signed)" "not signed for the Microsoft UEFI CA"
  mktree "$SHIM" "$SHIM"; refuse "shim as grubx64.efi (not Debian-signed)" "not signed under the Debian Secure Boot CA"
  MMD=$(findeb 'shim-helpers-amd64-signed_*_amd64.deb') && { dpkg-deb -x "$MMD" "$X"; MM=$X/usr/lib/shim/mmx64.efi.signed
    mktree "$MM" "$GRUB"; refuse "MokManager as bootx64.efi" "not signed for the Microsoft UEFI CA"
    mktree "$SHIM" "$MM"; refuse "MokManager (Debian-signed, not GRUB) as grubx64.efi" "not signed by Debian's GRUB signing key"; } \
    || skip "shim-helpers-amd64-signed .deb missing: MokManager cases"
  BIND=$(findeb 'grub-efi-amd64-unsigned_*_amd64.deb') && { dpkg-deb -x "$BIND" "$X"
    mktree "$SHIM" "$X/usr/lib/grub/x86_64-efi/monolithic/gcdx64.efi"; refuse "the unsigned monolithic GRUB (live-build's shim-only fallback)" "not signed under the Debian Secure Boot CA"; } \
    || skip "grub-efi-amd64-unsigned .deb missing: unsigned GRUB case"
  KP0=$KPKG; KPKG=$KPKG-unsigned; mktree "$SHIM" "$GRUB"; refuse "a kernel from an -unsigned package" "Debian's unsigned kernel"; KPKG=$KP0
  KS0=$KSOURCE; KSOURCE=linux; mktree "$SHIM" "$GRUB"; refuse "a kernel package not built from linux-signed-*" "linux-signed-* source"; KSOURCE=$KS0
  mktree "$SHIM" "$GRUB"; echo x >> "$W/chroot/boot/vmlinuz-$KVER"; refuse "a kernel that is not the chroot's" "not one of the chroot's"
  mktree "$SHIM" "$GRUB"; sed -i 's/^[0-9a-f]*/00000000000000000000000000000000/' "$W/chroot/var/lib/dpkg/info/$KPKG.md5sums"; refuse "a kernel that doesn't match dpkg's MD5" "does not match"
  mktree "$SHIM" "$GRUB"; rm -f "$W"/binary/live/vmlinuz*; refuse "no kernel" "no kernel in binary/live"
  o=$(python3 -I "$INS" grub "$GRUB"); n=$(grep -c '^module ' <<<"$o")
  grep -qx 'prefix /boot/grub' <<<"$o" && ! grep -qx disable-shim-lock <<<"$o" && ok "Debian's signed GRUB: prefix /boot/grub, $n built-in modules, shim lock kept" || bad "signed GRUB layout: $(grep -v '^module' <<<"$o")"
fi
fi

## safety notifier: Secure Boot information; lockdown failure is an alert
grep -q 'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c' "$N" && ok "notifier reads the SecureBoot EFI variable" || bad "notifier: SecureBoot variable"
mkdir -p "$T/nb"; printf '#!/bin/sh\necho "$@" >> "$ALERTS"\n' > "$T/nb/notify-send"; printf '#!/bin/sh\necho zenity >> "$ALERTS"\n' > "$T/nb/zenity"
printf '#!/bin/sh\n[ "$1" = 20 ] && kill -TERM $PPID\nexit 0\n' > "$T/nb/sleep"; printf '#!/bin/sh\n[ "$2" = is-failed ] && exit 1\nexit 0\n' > "$T/nb/systemctl"; printf '#!/bin/sh\nexit 0\n' > "$T/nb/logger"
chmod +x "$T/nb/"*; echo Y > "$T/aa"
efi() { # $1 SecureBoot value (0/1, or "" for no variable, "bios" for no EFI), $2 lockdown file content (empty: file missing)
  rm -rf "$T/efi" "$T/lockdown"
  if [ "$1" != bios ]; then
    mkdir -p "$T/efi/efivars"
    [ -n "$1" ] && printf "\\006\\000\\000\\000\\$(printf %03o "$1")" > "$T/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
  fi
  [ -n "$2" ] && printf '%s\n' "$2" > "$T/lockdown"; }
nrun(){ rm -f "$T/alerts"; env -i PATH="$T/nb:/usr/bin:/bin" HOME="$T" ALERTS="$T/alerts" PRESTIUM_AA_ENABLED="$T/aa" PRESTIUM_AA_PROFILES="$T/none" \
  PRESTIUM_CMDLINE_CHECK=true PRESTIUM_EFI_DIR="$T/efi" PRESTIUM_LOCKDOWN="$T/lockdown" timeout 10 bash "$N" >/dev/null 2>&1; cat "$T/alerts" 2>/dev/null; }
efi 1 "none [integrity] confidentiality"; o=$(nrun); [ -z "$o" ] && ok "notifier: Secure Boot on, locked down: nothing shown" || bad "notifier: SB on: $o"
efi 0 "none [integrity] confidentiality"; o=$(nrun)
case $o in *"-u normal Secure Boot is off"*) case $o in *critical*|*zenity*|*"Protection NOT active"*) bad "notifier: SB off is shown as an alert: $o";; *) ok "notifier: Secure Boot off (kernel locked down): information (normal urgency, no dialog)";; esac;; *) bad "notifier: SB off not shown: $o";; esac
efi 1 "[none] integrity confidentiality"; o=$(nrun)
case $o in *"Protection NOT active"*"kernel is not locked down"*) case $o in *"-u critical"*"zenity"*) ok "notifier: Secure Boot on, no lockdown: Protection NOT active alert";; *) bad "notifier: SB on, no lockdown, not a critical alert: $o";; esac;; *) bad "notifier: SB on, no lockdown: $o";; esac
efi 1 "none integrity [confidentiality]"; o=$(nrun); [ -z "$o" ] && ok "notifier: confidentiality is accepted (stricter than integrity)" || bad "notifier: confidentiality: $o"
efi bios "none [integrity] confidentiality"; o=$(nrun); [ -z "$o" ] && ok "notifier: BIOS boot, locked down: nothing shown" || bad "notifier: BIOS integrity: $o"
efi bios ""; o=$(nrun)
case $o in *"Protection NOT active"*"kernel is not locked down"*"unavailable"*) ok "notifier: BIOS, lockdown file missing: Protection NOT active alert";; *) bad "notifier: BIOS missing lockdown: $o";; esac
efi "" "[none] integrity confidentiality"; o=$(nrun)
case $o in *"Protection NOT active"*"kernel is not locked down"*) ok "notifier: SecureBoot variable unreadable, no lockdown: alert";; *) bad "notifier: unknown, no lockdown: $o";; esac
efi 0 "[none] integrity confidentiality"; o=$(nrun)
case $o in *"-u normal Secure Boot is off"*"Protection NOT active"*"kernel is not locked down"*) ok "notifier: Secure Boot off and no lockdown: information plus alert";; *) bad "notifier: SB off and no lockdown: $o";; esac

SC=$(command -v shellcheck || true)
if [ -n "$SC" ]; then "$SC" -s sh "$H" && "$SC" -S warning "$N" && "$SC" -S warning "$0" && ok "shellcheck: hook 9040, notifier, this test" || bad "shellcheck findings"; else skip "shellcheck missing"; fi
[ $fail = 0 ] && echo "secure boot: OK"; exit $fail
