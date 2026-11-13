#!/bin/bash
# 2.1 (boot command line): Prestium boots only with its own kernel command line.
#   - the policy (usr/share/prestium/boot/cmdline.policy) is auto/config's APPEND (and config/binary's
#     LB_BOOTAPPEND_LIVE/_FAILSAFE) plus hook 9010's options; every extra option a boot entry template
#     adds is allowed by it
#   - cmdline-guard.sh (dash, bash and busybox sh when available) accepts every real entry and refuses
#     missing, extra, repeated, malformed and banned options, odd characters and a missing policy
#   - the initramfs entry point refuses and restarts (never returns, never a shell), checked in a
#     user-namespace chroot with a fake /proc/cmdline and a static busybox (skipped without them)
#   - initramfs-tools hook prestium-cmdline puts the guard into a copy of initramfs-tools' /init
#     (PRESTIUM_INITRAMFS_INIT=<file> or /usr/share/initramfs-tools/init; skipped without one) before
#     the command line is parsed and before init-top, once, and refuses a changed init
#   - hook 9030 on a fake binary/ tree (after 9020): GRUB's EFI config searches for the per-build marker
#     on the boot disk first and reboots when it is missing; a foreign option, a missing option, another
#     root hash, chainloader, a foreign kernel, policy drift or a built-in kernel command line stop it
#     (needs mtools and mkfs.msdos; grub-script-check when available)
#   - prestium-cmdline-check.service: before AppArmor and sysinit, reboots on failure, enabled
#   - prestium-safety-notify alerts on a mismatch and when the check did not run
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }; skip(){ echo "SKIP $1"; }
I=$R/config/includes.chroot
B=$I/usr/share/prestium/boot; LIB=$B/cmdline-guard.sh; POL=$B/cmdline.policy
IH=$I/etc/initramfs-tools/hooks/prestium-cmdline; CHK=$I/usr/local/sbin/prestium-cmdline-check
H30=$R/config/hooks/live/9030-prestium-boot-cmdline.hook.binary; H20=$R/config/hooks/live/9020-prestium-boot-lock.hook.binary
U=$I/etc/systemd/system/prestium-cmdline-check.service; N=$I/usr/local/bin/prestium-safety-notify
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

## files, wiring
for f in "$LIB" "$IH" "$CHK" "$H30"; do sh -n "$f" && ok "sh -n ${f#"$R"/}" || bad "sh -n $f"; done
[ -x "$IH" ] && [ -x "$CHK" ] && [ -x "$H30" ] && ok "hooks and check executable" || bad "not executable"
P=$I/usr/share/prestium/build/perms.txt
for p in "0644 root root /usr/share/prestium/boot/cmdline-guard.sh" "0644 root root /usr/share/prestium/boot/cmdline.policy" \
  "0755 root root /etc/initramfs-tools/hooks/prestium-cmdline" "0755 root root /usr/local/sbin/prestium-cmdline-check" \
  "0644 root root /etc/systemd/system/prestium-cmdline-check.service"; do grep -qxF "$p" "$P" && ok "perms.txt: ${p##* }" || bad "perms.txt lacks $p"; done
grep -qxF '/etc/systemd/system/sysinit.target.wants/prestium-cmdline-check.service /etc/systemd/system/prestium-cmdline-check.service' \
  "$I/usr/share/prestium/build/systemd-wants.txt" && ok "service enabled (sysinit.target.wants)" || bad "service not enabled"
grep -qx 'DefaultDependencies=no' "$U" && grep -qE '^Before=.*\bapparmor\.service\b' "$U" && grep -qE '^Before=.*\bsysinit\.target\b' "$U" \
  && ok "check runs before AppArmor loads and before sysinit" || bad "unit ordering"
grep -qx 'FailureAction=reboot-force' "$U" && grep -qx 'ExecStart=/usr/local/sbin/prestium-cmdline-check --enforce' "$U" \
  && ok "a mismatch restarts the computer (FailureAction=reboot-force)" || bad "unit does not enforce"
grep -qx 'panic=10' <(awk '$1=="require"{print $2}' "$POL") && ok "policy requires panic=10" || bad "policy lacks panic=10"

## policy == auto/config
A=$(sed -n 's/^APPEND="\(.*\)"$/\1/p' "$R/auto/config")
want=$(printf '%s\n' $A | grep -vx -e quiet -e splash)
have=$(awk '$1=="require"{print $2}' "$POL" | grep -v -e '^dm-verity-' -e '^panic=10$')
[ -n "$A" ] && [ "$want" = "$have" ] && ok "policy requires exactly auto/config's APPEND (without quiet splash), same order" || bad "policy and auto/config differ: $(diff <(echo "$want") <(echo "$have") | tr '\n' ' ')"
LBA=$(sed -n 's/^LB_BOOTAPPEND_LIVE="\(.*\)"$/\1/p' "$R/config/binary"); LBF=$(sed -n 's/^LB_BOOTAPPEND_LIVE_FAILSAFE="\(.*\)"$/\1/p' "$R/config/binary")
[ "$LBA" = "$A" ] && [ "$LBF" = "$A nomodeset" ] && ok "config/binary matches auto/config (live and nomodeset)" || bad "config/binary differs from auto/config"
for t in quiet splash nomodeset prestium.nocammic nomacspoof verify-checksums; do grep -qx "allow $t" "$POL" || bad "policy does not allow $t"; done
extra=$(grep -hvE '^[[:space:]]*#' "$R/config/bootloaders/grub-pc/grub.cfg" "$R/config/bootloaders/syslinux_common/live.cfg.in" | grep -oE '@APPEND_LIVE(_FAILSAFE)?@[^}]*$' | sed 's/@APPEND_LIVE[A-Z_]*@//' | tr ' ' '\n' | sort -u | grep .)
miss=; for t in $extra; do grep -qx "allow $t" "$POL" || miss="$miss $t"; done
[ -z "$miss" ] && ok "every template entry's extra option is allowed ($(echo $extra))" || bad "template options not in the policy:$miss"
HASH=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
V="dm-verity-root-hash=filesystem.squashfs:$HASH dm-verity-oncorruption=panic panic=10"
LIVE="${A/boot=live /boot=live $V }"

## guard: accept / refuse
SHELLS="dash bash"; BB=${PRESTIUM_BUSYBOX:-$(command -v busybox || true)}; [ -n "$BB" ] && SHELLS="$SHELLS busybox"
chk(){ # shell cmdline -> prints problems, rc
  case $1 in busybox) "$BB" sh -c '. "$1"; prestium_cmdline_problems "$2" "$3"' x "$LIB" "$2" "${3:-$POL}";;
    *) "$1" -c '. "$1"; prestium_cmdline_problems "$2" "$3"' x "$LIB" "$2" "${3:-$POL}";; esac; }
for s in $SHELLS; do command -v "$s" >/dev/null || [ "$s" = busybox ] || { skip "$s missing"; continue; }
  g=0
  for c in "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 $LIVE" "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 $LIVE nomodeset" \
           "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 $LIVE prestium.nocammic" "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 $LIVE nomacspoof" \
           "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 $(echo "$LIVE" | sed 's/ quiet//; s/ splash//') verify-checksums" \
           "BOOT_IMAGE=/live/vmlinuz-6.12.57+deb13-amd64 initrd=/live/initrd.img-6.12.57+deb13-amd64 $LIVE" \
           "BOOT_IMAGE=(hd0,gpt1)/live/vmlinuz $LIVE toram" "$LIVE"; do
    o=$(chk "$s" "$c") || { bad "$s: refused a real entry: $o"; g=1; }; done
  [ $g = 0 ] && ok "$s: every real boot entry passes"
  r=0
  for c in "${LIVE/apparmor=1 /}" "${LIVE/security=apparmor /}" "${LIVE/panic=10 /}" "${LIVE/ module.sig_enforce=1/}" "${LIVE/boot=live /}" \
           "${LIVE/dm-verity-oncorruption=panic /}" "${LIVE/$V /}" "$LIVE apparmor=0" "$LIVE security=selinux" "$LIVE lsm=landlock" \
           "$LIVE init=/bin/sh" "$LIVE rdinit=/bin/sh" "$LIVE break=top" "$LIVE break" "$LIVE debug" "$LIVE single" "$LIVE emergency" \
           "$LIVE systemd.unit=rescue.target" "$LIVE persistence" "$LIVE findiso=/x.iso" "$LIVE fetch=http://x/y" "$LIVE live-media=/dev/sdb" \
           "$LIVE toram=filesystem.squashfs" "$LIVE root=/dev/sda1" "$LIVE module.sig_enforce=0" "$LIVE panic=0" "$LIVE panic=10" \
           "$LIVE nomodeset nomodeset" "$LIVE apparmor=1" "${LIVE/$HASH/${HASH}0}" "${LIVE/$HASH/${HASH^^}}" "${LIVE/$HASH/${HASH:1}}" \
           "$LIVE dm-verity-root-hash=filesystem.squashfs:$HASH" "$LIVE dm-verity-root-hash=other.squashfs:$HASH" \
           "BOOT_IMAGE=/boot/vmlinuz $LIVE" "BOOT_IMAGE=/live/vmlinuz BOOT_IMAGE=/live/vmlinuz $LIVE" "BOOT_IMAGE=/live/vmlinuz/../../x $LIVE" \
           "$LIVE -- single" "$LIVE \"init=/bin/sh x\"" "$LIVE a\$b" "$LIVE *" "$(printf '%s\tinit=/bin/sh' "$LIVE")" "$LIVE bootconfig" ""; do
    if o=$(chk "$s" "$c"); then bad "$s: accepted '${c: -60}'"; r=1; fi; done
  [ $r = 0 ] && ok "$s: refuses 45 wrong command lines (missing, extra, repeated, malformed, odd characters, empty)"
  o=$(chk "$s" "$LIVE" "$T/no-policy") && bad "$s: accepted without a policy" || { case $o in *"policy"*"missing"*) ok "$s: no policy: refused";; *) bad "$s: no policy: $o";; esac; }
  printf 'allow quiet\n' > "$T/p0"; o=$(chk "$s" "quiet" "$T/p0") && bad "$s: a policy without require lines passed" || ok "$s: a policy that requires nothing is refused"
  printf 'require boot=live\nmaybe x\n' > "$T/p1"; o=$(chk "$s" "boot=live" "$T/p1") && bad "$s: unknown policy line passed" || ok "$s: a malformed policy is refused"
done
o=$(chk dash "$LIVE init=/bin/sh"); case $o in *"unexpected boot option: init=/bin/sh"*) ok "reports the unexpected option";; *) bad "report: $o";; esac
o=$(chk dash "${LIVE/apparmor=1 /}"); case $o in *"missing boot option: apparmor=1"*) ok "reports the missing option";; *) bad "report: $o";; esac
grep -qE '(^|[^_])(grep|sed|awk) ' <(grep -v '^[[:space:]]*#' "$LIB") && bad "the guard uses grep/sed/awk (may be missing in the initramfs)" || ok "the guard is plain sh (no grep, sed, awk)"
grep -q '\${PRESTIUM_\|\$PRESTIUM_' "$LIB" && bad "the guard reads PRESTIUM_* variables (the kernel can set /init's environment)" || ok "the guard takes nothing from the environment"
grep -qw panic <(grep -v '^[[:space:]]*#' "$LIB" | grep -v 'panic=\|oncorruption') && bad "the guard calls panic (shell without panic=)" || ok "the guard never calls panic()"

## refusal: never returns (stubbed sleep/reboot)
o=$(dash -c '. "$1"; sleep(){ echo "SLEEP $1"; [ "$1" = 60 ] && exit 7; :; }; prestium_cmdline_reboot(){ echo REBOOT; }
  prestium_cmdline_refuse "unexpected boot option: init=/bin/sh"; echo RETURNED' x "$LIB"); rc=$?
[ $rc = 7 ] && case $o in *"not started with Prestium's own boot settings"*"init=/bin/sh"*"SLEEP 10"*REBOOT*"SLEEP 60"*) true;; *) false;; esac && ! grep -q RETURNED <<<"$o" \
  && ok "refusal: explains, waits 10 s, restarts, keeps restarting, never returns" || bad "refusal: rc=$rc $o"
CHR=$(command -v chroot || { [ -x /usr/sbin/chroot ] && echo /usr/sbin/chroot; } || true)
if [ -n "$BB" ] && [ -n "$CHR" ] && ! ldd "$BB" >/dev/null 2>&1 && unshare -rm true 2>/dev/null; then
  C=$T/root; mkdir -p "$C/bin" "$C/conf" "$C/scripts" "$C/proc" "$C/dev"; : > "$C/dev/null"   # /init mounts devtmpfs before the guard
  cp "$BB" "$C/bin/busybox"; for a in sh cat sleep reboot; do ln -s busybox "$C/bin/$a"; done
  cp "$LIB" "$C/scripts/prestium-cmdline-guard"; cp "$POL" "$C/conf/prestium-cmdline.policy"
  run_init(){ printf '%s\n' "$1" > "$T/cmdline"
    unshare -rm sh -c 'mount --rbind /proc "$1/proc" && mount --bind /dev/null "$1/dev/null" && mount --bind "$2" "$1/proc/cmdline" && exec "$3" "$1" /bin/sh -c ". /scripts/prestium-cmdline-guard
      sleep(){ [ \"\$1\" = 60 ] && exit 7; :; }; prestium_cmdline_reboot(){ echo REBOOT; }; prestium_cmdline_guard; echo PASSED"' x "$C" "$T/cmdline" "$CHR" 2>&1; }
  o=$(run_init "BOOT_IMAGE=/live/vmlinuz-6.12 $LIVE"); [ "$o" = PASSED ] && ok "initramfs (busybox, chroot): the image's own command line goes on" || bad "initramfs good: $o"
  o=$(run_init "BOOT_IMAGE=/live/vmlinuz-6.12 $LIVE break=top"); case $o in *"break=top"*REBOOT*) ! grep -q PASSED <<<"$o" && ok "initramfs (busybox, chroot): break=top refused before it is read, restart";; *) bad "initramfs bad: $o";; esac
  rm "$C/conf/prestium-cmdline.policy"; o=$(run_init "BOOT_IMAGE=/live/vmlinuz-6.12 $LIVE"); case $o in *missing*REBOOT*) ok "initramfs: no policy in the initramfs: refused";; *) bad "no policy: $o";; esac
else skip "static busybox, chroot or user namespaces missing: initramfs chroot run not tested"; fi

## prestium-cmdline-check (a copy pointed at the repo's library)
sed "s|/usr/share/prestium/boot/|$B/|g" "$CHK" > "$T/check"
printf '%s\n' "BOOT_IMAGE=/live/vmlinuz $LIVE" > "$T/good"; printf '%s\n' "$LIVE apparmor=0" > "$T/bad"
sh "$T/check" "$T/good" >/dev/null && ok "check: own command line, exit 0" || bad "check refused the good line"
o=$(sh "$T/check" "$T/bad") && bad "check accepted apparmor=0" || { case $o in *apparmor=0*) ok "check: names the problem, exit 1";; *) bad "check output: $o";; esac; }
sh "$T/check" --enforce "$T/good" >/dev/null 2>&1; [ $? = 2 ] && ok "check --enforce reads only /proc/cmdline" || bad "--enforce took a file"

## initramfs hook on initramfs-tools' init
INIT=${PRESTIUM_INITRAMFS_INIT:-/usr/share/initramfs-tools/init}
if [ -f "$INIT" ]; then
  mkdir -p "$T/d"; cp "$INIT" "$T/d/init"
  DESTDIR=$T/d PRESTIUM_HOOK_ROOT=$I sh "$IH" && ok "initramfs hook runs" || bad "initramfs hook failed"
  [ "$(grep -c '# prestium-cmdline$' "$T/d/init")" = 2 ] && ok "guard sourced and called in /init" || bad "guard not in /init"
  awk '/^prestium_cmdline_guard # prestium-cmdline$/{g=NR} /^for x in \$\(cat \/proc\/cmdline\); do$/{c=NR} /^maybe_break top$/{b=NR} /run_scripts \/scripts\/init-top/{t=NR} /mountroot$/{if(!m)m=NR}
    END{exit !(g && g<c && g<b && g<t && g<m)}' "$T/d/init" && ok "guard runs before break=/init=/panic= are read, before init-top and mountroot" || bad "guard order in /init"
  cmp -s "$T/d/scripts/prestium-cmdline-guard" "$LIB" && cmp -s "$T/d/conf/prestium-cmdline.policy" "$POL" && ok "guard and policy copied into the initramfs" || bad "initramfs copies"
  sh -n "$T/d/init" && ok "patched /init parses" || bad "patched /init syntax"
  DESTDIR=$T/d PRESTIUM_HOOK_ROOT=$I sh "$IH" && [ "$(grep -c '# prestium-cmdline$' "$T/d/init")" = 2 ] && ok "hook is idempotent" || bad "hook ran twice"
  cp "$INIT" "$T/d/init"; sed -i 's|^\. /scripts/functions$|. /scripts/functionz|' "$T/d/init"
  DESTDIR=$T/d PRESTIUM_HOOK_ROOT=$I sh "$IH" 2>/dev/null && bad "hook accepted a changed init" || ok "a changed initramfs-tools init stops the build"
else skip "no initramfs-tools init (PRESTIUM_INITRAMFS_INIT): hook not run"; fi

## hook 9030 on a fake binary tree
SCK=${PRESTIUM_GRUB_SCRIPT_CHECK:-$(command -v grub-script-check || true)}
if command -v mkfs.msdos >/dev/null && command -v mcopy >/dev/null && command -v mtype >/dev/null && command -v mmd >/dev/null; then
  mk(){ rm -rf "$T/b"; mkdir -p "$T/b/binary/boot/grub/x86_64-efi" "$T/b/binary/isolinux" "$T/b/binary/.disk" "$T/b/scripts" "$T/b/config" \
      "$T/b/chroot/usr/share/prestium/boot" "$T/b/chroot/boot" "$T/b/binary/live"
    cp "$R/scripts/grub-pbkdf2.py" "$T/b/scripts/"; cp "$R/config/binary" "$T/b/config/binary"; cp "$LIB" "$POL" "$T/b/chroot/usr/share/prestium/boot/"
    printf '# CONFIG_CMDLINE_BOOL is not set\nCONFIG_BOOT_CONFIG=y\n# CONFIG_BOOT_CONFIG_FORCE is not set\n' > "$T/b/chroot/boot/config-6.12.0-amd64"
    echo "$HASH" > "$T/b/prestium-roothash.tmp"; echo "Prestium 2.1" > "$T/b/binary/.disk/info"
    VC=$(echo "$LIVE" | sed 's/ quiet//; s/ splash//')
    live=$(printf 'menuentry "Prestium 2.1" --hotkey=l {\n\tlinux\t/live/vmlinuz-6.12.0-amd64 %s findiso=${iso_path}\n\tinitrd\t/live/initrd.img-6.12.0-amd64\n}\nmenuentry "Prestium 2.1 (nomodeset)" {\n\tlinux\t/live/vmlinuz-6.12.0-amd64 %s nomodeset\n\tinitrd\t/live/initrd.img-6.12.0-amd64\n}' "$LIVE" "$LIVE")
    awk -v live="$live" '/^@LINUX_LIVE@$/{print live; next} {print}' "$R/config/bootloaders/grub-pc/grub.cfg" \
      | sed -e "s|@KERNEL_LIVE@|/live/vmlinuz-6.12.0-amd64|g; s|@INITRD_LIVE@|/live/initrd.img-6.12.0-amd64|g; s|@APPEND_LIVE@|$LIVE|g; s|@APPEND_VERIFY_CHECKSUMS@|$VC verify-checksums|g" \
            -e 's|@PRESTIUM_VERSION@|2.1|g; s|@ENABLE_INSTALL_MENU@|false|; s|@ENABLE_MEMTEST@|false|; s|@ENABLE_VERIFY_CHECKSUMS@|true|' > "$T/b/binary/boot/grub/grub.cfg"
    printf 'set default=0\nset timeout=3\n' > "$T/b/binary/boot/grub/config.cfg"
    printf 'if [ x$grub_platform == xefi -a x$lockdown != xy ] ; then\n    insmod part_gpt\nfi\nsource /boot/grub/grub.cfg\n' > "$T/b/binary/boot/grub/x86_64-efi/grub.cfg"
    printf 'include menu.cfg\ndefault vesamenu.c32\nprompt 0\ntimeout 30\n' > "$T/b/binary/isolinux/isolinux.cfg"
    printf 'menu begin utilities\n\tlabel hdt\n\tmenu label ^Hardware Detection Tool (HDT)\n\tcom32 hdt.c32\nmenu end\n' > "$T/b/binary/isolinux/utilities.cfg"
    sed -e "s|@LINUX@|/live/vmlinuz-6.12.0-amd64|; s|@INITRD@|/live/initrd.img-6.12.0-amd64|; s|@APPEND_LIVE@|$LIVE|; s|@APPEND_LIVE_FAILSAFE@|$LIVE nomodeset|; s|@FLAVOUR@|amd64|; s|@PRESTIUM_VERSION@|2.1|" \
      "$R/config/bootloaders/syslinux_common/live.cfg.in" > "$T/b/binary/isolinux/live.cfg"
    printf 'search --set=root --file /.disk/info\nset prefix=($root)/boot/grub\nconfigfile ($root)/boot/grub/grub.cfg\n' > "$T/efi.cfg"
    mkfs.msdos -C "$T/b/binary/boot/grub/efi.img" 256 >/dev/null && mmd -i "$T/b/binary/boot/grub/efi.img" ::boot ::boot/grub \
      && mcopy -i "$T/b/binary/boot/grub/efi.img" "$T/efi.cfg" ::boot/grub/grub.cfg
    (cd "$T/b/binary" && sh "$H20") > "$T/out20" 2>&1 || echo "9020 failed: $(cat "$T/out20")"; }
  r30(){ (cd "$T/b/binary" && PRESTIUM_SKIP_INITRD_CHECK=1 sh "$H30") > "$T/out" 2>&1; }
  mk; if r30; then ok "9030 on a live-build-like tree: $(grep '^P:' "$T/out")"; else bad "9030 failed: $(cat "$T/out")"; fi
  ID=${HASH:0:32}
  [ -f "$T/b/binary/.disk/prestium-$ID" ] && ok "marker .disk/prestium-<first 32 hex of the root hash> written" || bad "marker missing"
  mtype -i "$T/b/binary/boot/grub/efi.img" ::boot/grub/grub.cfg | tr -d '\r' > "$T/efi.out"
  grep -q '/.disk/info' "$T/efi.out" && bad "EFI config still searches /.disk/info" || ok "EFI config no longer takes the first disk with /.disk/info"
  grep -qF -- "--hint=\"\$prestium_dev\" --hint=\"\$prestium_disk\" --hint=\"\$prestium_disk,\" --file /.disk/prestium-$ID" "$T/efi.out" \
    && grep -q "regexp --set=1:prestium_dev '^\\\\((\[^)\]+)\\\\)' \"\$cmdpath\"" "$T/efi.out" && ok "EFI config searches the marker on the disk GRUB started from first" || bad "marker search: $(cat "$T/efi.out")"
  awk '/if \[ ! -e "\(\$root\)\/.disk\/prestium-/{f=1} f && /^\treboot$/{r=1} /^configfile \(\$root\)\/boot\/grub\/grub.cfg$/{c=NR; if(!r) exit 1} END{exit !(r && c)}' "$T/efi.out" \
    && ok "marker missing: restart before configfile, nothing else is loaded" || bad "no reboot on a missing marker"
  head -4 "$T/efi.out" | grep -qx 'export superusers' && ok "EFI config keeps the superuser lock first (9020)" || bad "lock lost"
  if [ -n "$SCK" ]; then "$SCK" "$T/efi.out" && ok "grub-script-check: EFI config parses" || bad "EFI config does not parse"
    "$SCK" "$T/b/binary/boot/grub/grub.cfg" && ok "grub-script-check: grub.cfg parses" || bad "grub.cfg does not parse"
  else skip "grub-script-check not available"; fi
  (cd "$T/b/binary" && PRESTIUM_SKIP_INITRD_CHECK=1 sh "$H30") >/dev/null 2>&1 && bad "9030 ran twice" || ok "9030 refuses a second run"
  G=$T/b/binary/boot/grub/grub.cfg
  t30(){ if r30; then bad "9030 accepted: $1"; else ok "9030 stops on: $1 ($(grep -m1 '^E:' "$T/out" | cut -c1-110))"; fi; }
  mk; sed -i '0,/ nomacspoof$/s// nomacspoof systemd.log_level=debug/' "$G"; t30 "an option the image does not use (GRUB)"
  mk; sed -i '0,/ iommu.strict=1 /s// /' "$G"; t30 "an entry missing iommu.strict=1"
  mk; sed -i "0,/$HASH/s//$(printf '%064d' 1)/" "$G"; t30 "an entry with another root hash"
  mk; printf 'menuentry "Other" --unrestricted {\n\tchainloader /EFI/other.efi\n}\n' >> "$G"; t30 "a chainloader entry"
  mk; printf 'menuentry "Other" --unrestricted {\n\tlinux /boot/vmlinuz %s\n}\n' "$LIVE" >> "$G"; t30 "a kernel outside /live"
  mk; printf 'load_env\n' >> "$G"; t30 "load_env (grubenv)"
  mk; printf 'configfile (hd1,1)/boot/grub/grub.cfg\n' >> "$G"; t30 "configfile from another disk"
  mk; printf 'search --set=root --file /.disk/info\n' >> "$T/b/binary/boot/grub/x86_64-efi/grub.cfg"; t30 "a search in a per-platform config"
  mk; sed -i 's/ nomacspoof$/ nomacspoof foo=1/' "$T/b/binary/isolinux/live.cfg"; t30 "an option the image does not use (isolinux)"
  mk; printf 'label x\n\tlinux /live/vmlinuz\n\tconfig /other.cfg\n' >> "$T/b/binary/isolinux/live.cfg"; t30 "isolinux config directive"
  mk; printf 'label x\n\tcom32 chain.c32\n' >> "$T/b/binary/isolinux/utilities.cfg"; t30 "isolinux chain.c32"
  mk; sed -i 's/ iommu.strict=1 / /' "$T/b/config/binary"; t30 "policy drift from LB_BOOTAPPEND_LIVE"
  mk; echo 'CONFIG_CMDLINE_BOOL=y' >> "$T/b/chroot/boot/config-6.12.0-amd64"; t30 "a built-in kernel command line"
  mk; rm "$T/b/chroot/boot/config-6.12.0-amd64"; t30 "no kernel config"
  mk; mcopy -o -i "$T/b/binary/boot/grub/efi.img" <(printf 'set prefix=(hd0)/boot/grub\nconfigfile (hd0)/boot/grub/grub.cfg\n') ::boot/grub/grub.cfg; t30 "an EFI config without live-build's search"
  mk; sed -i 's/^set default=0$/set default=2/' "$T/b/binary/boot/grub/config.cfg"; t30 "a default other than the first entry"
  mk; (cd "$T/b/binary" && sh "$H30") > "$T/out" 2>&1 && bad "9030 passed without checking the initramfs" || { grep -q 'initrd\|initramfs' "$T/out" && ok "9030 stops when the initramfs can't be checked"; } || bad "initramfs check: $(cat "$T/out")"
else skip "mtools/mkfs.msdos missing: hook 9030 not run"; fi

## safety notifier
grep -q 'alert unit:cmdline' "$N" && grep -q 'is-active prestium-cmdline-check.service' "$N" && ok "notifier checks the command line and the boot check" || bad "notifier wiring"
mkdir -p "$T/nb"
cat > "$T/nb/systemctl" <<'S'
#!/bin/sh
u=; for a in "$@"; do case "$a" in *.service) u=$a;; esac; done
case "$1 $2" in
  "-q is-active") [ "$u" = prestium-cmdline-check.service ] && { [ "$CLSTATE" = active ]; exit; }; exit 0;;
  "-q is-failed") exit 1;;
  "show -p") [ "$u" = prestium-cmdline-check.service ] && echo "$CLSTATE" || echo active;;
esac
S
printf '#!/bin/sh\necho "$@" >> "$ALERTS"\n' > "$T/nb/notify-send"; printf '#!/bin/sh\nexit 0\n' > "$T/nb/zenity"
printf '#!/bin/sh\n[ "$1" = 20 ] && kill -TERM $PPID\nexit 0\n' > "$T/nb/sleep"
printf '#!/bin/sh\necho "unexpected boot option: apparmor=0"\necho "missing boot option: apparmor=1"\nexit 1\n' > "$T/nb/cl-bad"
chmod +x "$T/nb/"*; echo Y > "$T/aa"
nrun(){ rm -f "$T/alerts"; env -i PATH="$T/nb:/usr/bin:/bin" HOME="$T" ALERTS="$T/alerts" CLSTATE="$2" PRESTIUM_AA_ENABLED="$T/aa" \
  PRESTIUM_AA_PROFILES="$T/none" PRESTIUM_EFI_DIR="$T/no-efi" PRESTIUM_CMDLINE_CHECK="$1" timeout 10 bash "$N" >/dev/null 2>&1; cat "$T/alerts" 2>/dev/null; }
o=$(nrun true active); [ -z "$o" ] && ok "notifier: own command line, check ran: no alert" || bad "notifier false alert: $o"
o=$(nrun "$T/nb/cl-bad" active); case $o in *"Protection NOT active"*"not started with Prestium's own boot settings"*"apparmor=0"*) ok "notifier: mismatch alert names the options";; *) bad "notifier mismatch: $o";; esac
o=$(nrun true inactive); case $o in *"boot settings check did not run (prestium-cmdline-check.service: inactive)"*) ok "notifier: check did not run: alert";; *) bad "notifier inactive: $o";; esac
o=$(nrun true activating); [ -z "$o" ] && ok "notifier: check still activating: no alert" || bad "notifier activating: $o"

SC=$(command -v shellcheck || true)
if [ -n "$SC" ]; then
  "$SC" -s sh -S style "$LIB" "$IH" "$CHK" "$H30" && "$SC" -S warning "$N" && ok "shellcheck (all levels): guard, hooks, check" || bad "shellcheck findings"
else skip "shellcheck not installed"; fi
[ $fail = 0 ] && echo "boot cmdline guard: OK"; exit $fail
