#!/bin/bash
# 2.1 (security audit): rarely used filesystem drivers can't be loaded (udisks loop-setup lets user
# programs hand the kernel filesystem images), and the ones Prestium or its users need stay loadable.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); B=$R/config/includes.chroot/etc/modprobe.d/prestium-blacklist.conf; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
for m in adfs affs befs bfs efs erofs gfs2 hfs hpfs jfs minix nilfs2 ocfs2 omfs qnx4 qnx6 reiserfs romfs sysv ufs zonefs cramfs freevxfs jffs2; do
  grep -qx "install $m /bin/false" "$B" && ok "blocked: $m" || bad "not blocked: $m"; done
for m in squashfs overlay vfat fat exfat ntfs3 ext4 btrfs xfs f2fs isofs udf hfsplus fuse loop dm_crypt dm-crypt nls_utf8 nls_cp437; do
  grep -qE "^(install|blacklist) $m( |$)" "$B" && bad "needed module blocked: $m" || ok "loadable: $m"; done
grep -q 'loop-setup' "$R/config/includes.chroot/etc/polkit-1/rules.d/49-prestium-veracrypt.rules" && ok "polkit rule still allows VeraCrypt file containers" || bad "loop-setup gone (file containers break)"
exit $fail
