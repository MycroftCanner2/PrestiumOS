#!/bin/bash
# 2.1: the live image is mounted only through dm-verity.
#   - hooks 0405 / 9010, the initramfs hook and 9989-prestium-verity.sh parse (sh -n)
#   - hook 0405 patches live-boot's 9990-overlay.sh exactly once (needs live-boot's file: from
#     /usr/lib/live/boot, or PRESTIUM_LIVE_BOOT_DIR=<dir with 9990-overlay.sh>; skipped otherwise)
#   - prestium_verity_check refuses a missing hash tree, a missing/malformed root hash, other images
#   - hook 9010 on a fake binary/ tree: the root hash lands on every boot entry, the .roothash file
#     leaves the medium, a tampered image stops it (veritysetup round-trip, PRESTIUM_VERITYSETUP or
#     PATH; skipped without it)
#   - build.sh/auto/config wiring (release files carry the root hash)
#   - 2.1 (review of 6bf1234): panic=10 on every entry (no initramfs root shell), .fec/.fec.roots/
#     .roothash/.roothash.p7s/*.module next to the image and odd characters in its path stop the boot,
#     hook 0405 removes the medium's boot.conf from live-boot's initramfs hook
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }; skip(){ echo "SKIP $1"; }
H0405=$R/config/hooks/live/0405-prestium-verity.hook.chroot
H9010=$R/config/hooks/live/9010-prestium-verity-boot.hook.binary
LB=$R/config/includes.chroot/usr/lib/live/boot/9989-prestium-verity.sh
IH=$R/config/includes.chroot/etc/initramfs-tools/hooks/prestium-verity
for f in "$H0405" "$H9010" "$LB" "$IH"; do sh -n "$f" && ok "sh -n $(basename "$f")" || bad "sh -n $f"; done
[ -x "$H0405" ] && [ -x "$H9010" ] && [ -x "$IH" ] && ok "hooks executable" || bad "a hook is not executable"
grep -q -- '--dm-verity \\' "$R/auto/config" && ok "auto/config: --dm-verity" || bad "auto/config lacks --dm-verity"
grep -qx 'LB_DM_VERITY="true"' "$R/config/binary" && ok "config/binary: LB_DM_VERITY=true" || bad "config/binary"
grep -q 'echo "dm_verity_root_hash: ' "$R/build.sh" && ok "manifest: dm_verity_root_hash" || bad "manifest lacks the root hash"
grep -q 'sha256sum "$OUT" "$MAN" "$ROOTHASH"' "$R/build.sh" && ok "SHA256SUMS covers the root hash" || bad "SHA256SUMS lacks the root hash"
grep -q 'command -v veritysetup' "$R/build.sh" && ok "build.sh needs veritysetup" || bad "build.sh: no veritysetup check"
for p in /usr/lib/live/boot/9989-prestium-verity.sh /etc/initramfs-tools/hooks/prestium-verity; do
  grep -q " $p\$" "$R/config/includes.chroot/usr/share/prestium/build/perms.txt" && ok "perms.txt: $p" || bad "perms.txt lacks $p"; done
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

# --- hook 0405 against live-boot's real 9990-overlay.sh
D=${PRESTIUM_LIVE_BOOT_DIR:-/usr/lib/live/boot}
if [ -f "$D/9990-overlay.sh" ]; then
  mkdir -p "$T/r/usr/lib/live/boot" "$T/r/etc/initramfs-tools/hooks"
  cp "$D/9990-overlay.sh" "$T/r/usr/lib/live/boot/"; cp "$LB" "$T/r/usr/lib/live/boot/"; cp "$IH" "$T/r/etc/initramfs-tools/hooks/"
  mkdir -p "$T/r/usr/share/initramfs-tools/hooks"
  IHL=${PRESTIUM_LIVE_BOOT_HOOK:-$D/../../../share/initramfs-tools/hooks/live}
  if [ -f "$IHL" ]; then cp "$IHL" "$T/r/usr/share/initramfs-tools/hooks/live"; ok "live-boot's initramfs hook found"
  else printf '#!/bin/sh\nfor _FILE in /etc/live/boot.conf /etc/live/boot/* \\\n\t     /run/live/medium/live/boot.conf /run/live/medium/live/boot/*\ndo\n\t[ -e "${_FILE}" ] && . "${_FILE}"\ndone\n' > "$T/r/usr/share/initramfs-tools/hooks/live"
    skip "live-boot's initramfs hook not found: a copy of its boot.conf loop is used (PRESTIUM_LIVE_BOOT_HOOK)"; fi
  if PRESTIUM_HOOK_ROOT=$T/r sh "$H0405" >/dev/null; then ok "0405 patches 9990-overlay.sh"; else bad "0405 failed"; fi
  O=$T/r/usr/lib/live/boot/9990-overlay.sh
  [ "$(grep -c '# prestium-verity' "$O")" = 3 ] && ok "three changes" || bad "changes: $(grep -c '# prestium-verity' "$O")"
  cp "$O" "$T/once"; PRESTIUM_HOOK_ROOT=$T/r sh "$H0405" >/dev/null && cmp -s "$O" "$T/once" && ok "0405 idempotent" || bad "0405 not idempotent"
  grep -B1 'prestium_verity_check "${image}"' "$O" | grep -q 'imagename=$(basename' && ok "check runs before each image is mounted" || bad "check misplaced"
  L=$T/r/usr/share/initramfs-tools/hooks/live
  ! grep -q '/run/live/medium' "$L" && grep -q '^for _FILE in /etc/live/boot.conf /etc/live/boot/\* # prestium-verity' "$L" && sh -n "$L" \
    && ok "initramfs hook no longer sources boot.conf from the medium" || bad "initramfs hook still reads the medium: $(grep -n medium "$L")"
  cp "$D/9990-overlay.sh" "$T/r/usr/lib/live/boot/9990-overlay.sh"; sed -i 's/# we have a plain root system/# plain/' "$T/r/usr/lib/live/boot/9990-overlay.sh"
  PRESTIUM_HOOK_ROOT=$T/r sh "$H0405" >/dev/null 2>&1 && bad "0405 accepted a changed live-boot" || ok "0405 stops on a changed live-boot"
else skip "live-boot's 9990-overlay.sh not found (set PRESTIUM_LIVE_BOOT_DIR)"; fi

# --- prestium_verity_check (busybox-compatible sh, panic stubbed)
H=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
mkdir -p "$T/m"; : > "$T/m/filesystem.squashfs"
chk(){ # $1 image, $2 the dm-verity-root-hash= value (live-boot's DM_VERITY_ROOT_HASH); PV_MOUNT: mount --version
  DM_VERITY_ROOT_HASH=$2 sh -c '
    panic(){ echo "PANIC $*"; exit 3; }
    mount(){ echo "$PV_MOUNT"; }
    modprobe(){ return 0; }
    get_dm_verity_hash(){ echo "$2" | tr "," "\n" | awk -v image="$1" -F ":" "\$1==image {print \$2}"; }
    . "$0"; prestium_verity_check "$1" && echo PASS' "$LB" "$1" "$2" 2>&1 | tail -n 1; }
export PV_MOUNT="mount from util-linux 2.41 (libmount 2.41: verity)"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H")
[[ $r == PANIC*hash\ tree* ]] && ok "no hash tree: refused" || bad "no hash tree: $r"
: > "$T/m/filesystem.squashfs.verity"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H"); [ "$r" = PASS ] && ok "hash tree + root hash: mounts" || bad "good case: $r"
r=$(chk "$T/m/filesystem.squashfs" ""); [[ $r == PANIC*no\ dm-verity\ root\ hash* ]] && ok "no root hash on the command line: refused" || bad "no hash: $r"
r=$(chk "$T/m/filesystem.squashfs" "other.squashfs:$H"); [[ $r == PANIC* ]] && ok "root hash for another image only: refused" || bad "other: $r"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:${H:0:63}"); [[ $r == PANIC*malformed* ]] && ok "short root hash: refused" || bad "short: $r"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:${H:0:63}G"); [[ $r == PANIC*malformed* ]] && ok "non-hex root hash: refused" || bad "nonhex: $r"
: > "$T/m/extra.squashfs"; r=$(chk "$T/m/extra.squashfs" "filesystem.squashfs:$H"); [[ $r == PANIC* ]] && ok "an added image without hash: refused" || bad "extra: $r"
mkdir "$T/m/x.dir"; r=$(chk "$T/m/x.dir" "x.dir:$H"); [[ $r == PANIC*unexpected* ]] && ok "a directory image: refused" || bad "dir: $r"
: > "$T/m/r.ext4"; r=$(chk "$T/m/r.ext4" "r.ext4:$H"); [[ $r == PANIC*unexpected* ]] && ok "an ext4 image: refused" || bad "ext4: $r"
PV_MOUNT="mount from util-linux 2.41 (libmount 2.41: selinux)" r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H")
[[ $r == PANIC*mount* ]] && ok "mount without dm-verity support: refused" || bad "mount: $r"
export PV_MOUNT="mount from util-linux 2.41 (libmount 2.41: verity)"
# files live-boot would read from the medium into mount options or paths
for x in filesystem.squashfs.fec filesystem.squashfs.fec.roots filesystem.squashfs.roothash filesystem.squashfs.roothash.p7s filesystem.module; do
  echo '2 -o verity.oncorruption=ignore' > "$T/m/$x"
  r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H"); [[ $r == PANIC*unexpected\ file*$x* ]] && ok "$x next to the image: refused" || bad "$x: $r"
  rm -f "$T/m/$x"; done
ln -s /nonexistent "$T/m/filesystem.squashfs.fec.roots"; r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H")
[[ $r == PANIC*unexpected\ file* ]] && ok "a dangling .fec.roots symlink: refused" || bad "symlink: $r"; rm -f "$T/m/filesystem.squashfs.fec.roots"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H"); [ "$r" = PASS ] && ok "clean directory again: mounts" || bad "clean: $r"
mkdir -p "$T/m b"; : > "$T/m b/filesystem.squashfs"; : > "$T/m b/filesystem.squashfs.verity"
r=$(chk "$T/m b/filesystem.squashfs" "filesystem.squashfs:$H"); [[ $r == PANIC*characters* ]] && ok "a space in the image path: refused" || bad "space: $r"
r=$(chk '/x/filesystem.squashfs;-o' "filesystem.squashfs:$H"); [[ $r == PANIC*characters* ]] && ok "shell/option characters in the image path: refused" || bad "chars: $r"
r=$(chk "$T/m/filesystem.squashfs" "filesystem.squashfs:$H,filesystem.squashfs:$H"); [[ $r == PANIC*malformed* ]] && ok "two root hashes for one image: refused" || bad "two hashes: $r"
grep -q 'panic=10' "$LB" && ok "9989 documents that panic reboots (panic=10)" || bad "9989 panic comment"

# --- hook 9010 on a fake binary/ tree, with a real veritysetup round-trip
VS=${PRESTIUM_VERITYSETUP:-$(command -v veritysetup || true)}
if [ -n "$VS" ] && "$VS" --version >/dev/null 2>&1; then
  mkdir -p "$T/b/binary/live" "$T/b/binary/boot/grub" "$T/b/binary/isolinux" "$T/bin"
  ln -s "$VS" "$T/bin/veritysetup"
  dd if=/dev/urandom of="$T/b/binary/live/filesystem.squashfs" bs=4096 count=256 2>/dev/null
  RH=$("$VS" format "$T/b/binary/live/filesystem.squashfs" "$T/b/binary/live/filesystem.squashfs.verity" | awk -F: '$1=="Root hash"{print $2}' | tr -d '[:space:]')
  printf %s "$RH" > "$T/b/binary/live/filesystem.squashfs.roothash"
  cp -a "$T/b/binary/live" "$T/live.orig"
  printf 'menuentry "Prestium 2.1" {\n\tlinux\t/live/vmlinuz boot=live quiet apparmor=1\n\tinitrd\t/live/initrd.img\n}\nmenuentry "x" {\n\tlinux\t/live/vmlinuz boot=live nomacspoof\n}\n' > "$T/b/binary/boot/grub/grub.cfg"
  printf 'label live\n\tlinux /live/vmlinuz\n\tappend boot=live quiet\n' > "$T/b/binary/isolinux/live.cfg"
  printf 'set default=0\n' > "$T/b/binary/boot/grub/config.cfg"
  if (cd "$T/b/binary" && PATH=$T/bin:$PATH sh "$H9010") >/dev/null; then ok "9010 on an intact image"; else bad "9010 failed on an intact image"; fi
  n=$(grep -c "boot=live dm-verity-root-hash=filesystem.squashfs:$RH dm-verity-oncorruption=panic panic=10 " "$T/b/binary/boot/grub/grub.cfg" "$T/b/binary/isolinux/live.cfg" | awk -F: '{s+=$2} END{print s}')
  [ "$n" = 3 ] && ok "root hash and panic=10 on all 3 boot entries (GRUB, isolinux)" || bad "root hash/panic=10 on $n of 3 entries"
  m=$(grep -ohE '(^|[[:space:]])panic=[^[:space:]]*' "$T/b/binary/boot/grub/grub.cfg" "$T/b/binary/isolinux/live.cfg" | sort | uniq -c | awk '{print $1" "$2}')
  [ "$m" = "3 panic=10" ] && ok "exactly one panic=10 per entry" || bad "panic= tokens: $m"
  [ ! -e "$T/b/binary/live/filesystem.squashfs.roothash" ] && ok ".roothash file not left on the medium" || bad ".roothash still on the medium"
  [ "$(cat "$T/b/prestium-roothash.tmp")" = "$RH" ] && ok "root hash handed to build.sh" || bad "prestium-roothash.tmp"
  "$VS" verify "$T/b/binary/live/filesystem.squashfs" "$T/b/binary/live/filesystem.squashfs.verity" "$RH" && ok "veritysetup verify: intact image" || bad "verify failed on the intact image"
  printf 'X' | dd of="$T/b/binary/live/filesystem.squashfs" bs=1 seek=300000 conv=notrunc 2>/dev/null
  "$VS" verify "$T/b/binary/live/filesystem.squashfs" "$T/b/binary/live/filesystem.squashfs.verity" "$RH" >/dev/null 2>&1 && bad "a changed byte verified" || ok "veritysetup verify: one changed byte refused"
  rm -rf "$T/b/binary/live"; cp -a "$T/live.orig" "$T/b/binary/live"
  printf 'X' | dd of="$T/b/binary/live/filesystem.squashfs" bs=1 seek=300000 conv=notrunc 2>/dev/null
  printf 'menuentry "P" {\n\tlinux\t/live/vmlinuz boot=live quiet\n}\n' > "$T/b/binary/boot/grub/grub.cfg"
  (cd "$T/b/binary" && PATH=$T/bin:$PATH sh "$H9010") >/dev/null 2>&1 && bad "9010 accepted a tampered image" || ok "9010 stops the build on a tampered image"
  rm -rf "$T/b/binary/live"; cp -a "$T/live.orig" "$T/b/binary/live"
  printf 'menuentry "P" {\n\tlinux\t/live/vmlinuz boot=live panic=0\n}\n' > "$T/b/binary/boot/grub/grub.cfg"
  (cd "$T/b/binary" && PATH=$T/bin:$PATH sh "$H9010") >/dev/null 2>&1 && bad "9010 accepted an entry with its own panic=" || ok "9010 stops on an entry that already sets panic="
  rm -rf "$T/b/binary/live"; cp -a "$T/live.orig" "$T/b/binary/live"; rm "$T/b/binary/live/filesystem.squashfs.roothash"
  (cd "$T/b/binary" && PATH=$T/bin:$PATH sh "$H9010") >/dev/null 2>&1 && bad "9010 without a root hash" || ok "9010 stops without a root hash"
else skip "veritysetup not available (cryptsetup-bin; or PRESTIUM_VERITYSETUP=<path>)"; fi
exit $fail
