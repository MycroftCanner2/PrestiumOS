#!/bin/bash
# Prestium 2.0: build Prestium-2.0-amd64.iso with live-build.
#   sudo ./build.sh            fetch+verify third-party software, lb config, lb build, checksum
#   sudo ./build.sh --resume   continue an interrupted build (keeps chroot and stage files)
#   sudo ./build.sh --clean    lb clean --purge first
# Host: Debian 13 (trixie) with live-build, debootstrap, squashfs-tools, xorriso, curl, gpg, gpgv,
# git, unzip, npm. On a non-amd64 host also qemu-user-static with a binfmt_misc entry for x86-64
# (flag F), so the amd64 chroot runs emulated. Output: ./Prestium-2.0-amd64.iso and .sha256.
set -euo pipefail
cd "$(dirname "$0")"
TOP=$(pwd)
OUT=Prestium-2.0-amd64.iso
LOG=${PRESTIUM_BUILD_LOG:-$TOP/build.log}
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)"; exit 1; }
MODE=${1:-}
# 2.0 r7: one build per tree. --resume removes live-build's own .lock, which is only safe while
# nothing else builds here, so hold an exclusive lock for the whole run (released on exit).
exec 9>"$TOP/.prestium-build.lock"
flock -n 9 || { echo "another build.sh is running in $TOP (lock $TOP/.prestium-build.lock)"; exit 1; }

if [ "$(dpkg --print-architecture)" != amd64 ]; then
	[ -e /proc/sys/fs/binfmt_misc/qemu-x86_64 ] || { echo "non-amd64 host: register qemu-x86_64 in binfmt_misc (qemu-user-static)"; exit 1; }
fi

if [ "$MODE" = --clean ]; then lb clean --purge; fi

# 1. third-party software (signature + pinned SHA-256), staged for the chroot hooks
CACHE=${PRESTIUM_CACHE:-$TOP/cache/thirdparty}
PRESTIUM_CACHE=$CACHE scripts/fetch-thirdparty.sh

# 2. the hooks need a resolver while the chroot is built; Prestium's own resolv.conf
#    (nameserver 127.0.0.1) is put back by live-build at the end of the chroot stage
install -D -m 644 /etc/resolv.conf config/includes.chroot/usr/share/prestium/build/host-resolv.conf

# 3. configure + build
lb config >/dev/null
if [ "$MODE" = --resume ]; then
	rm -f .lock
	# The installer and binary stages swap the real chroot into chroot/chroot (outer = bootstrap copy,
	# marked chroot_for_installer.cache or chroot.cache). live-build re-runs installer_chroot on every
	# "lb build" (it removes that stage file itself), and on a swapped tree that deletes the real chroot.
	# So undo an interrupted swap first and let binary_chroot redo it.
	if [ -d chroot/chroot ] && { [ -e chroot/chroot_for_installer.cache ] || [ -e chroot/chroot.cache ]; }; then
		for m in chroot/chroot/dev/pts chroot/chroot/proc chroot/chroot/sys chroot/dev/pts chroot/proc chroot/sys; do
			mountpoint -q "$m" && { umount -R "$m" || umount -R -l "$m"; } || true
		done
		mv chroot/chroot chroot.real && rm -rf chroot && mv chroot.real chroot
		rm -f .build/installer_chroot .build/binary_chroot .build/binary_rootfs
		# the configuration stage files then describe the discarded outer chroot, not the real one
		for s in apt archives debianchroot dpkg hostname hosts resolv sysv-rc tmpfs; do rm -f ".build/chroot_$s"; done
	fi
	# an interrupted bootstrap stage cannot be continued: start the chroot again (debs are cached)
	if [ ! -e .build/bootstrap ] && [ -d chroot ]; then rm -rf chroot; fi
	# live-build appends the package lists to chroot/root/packages.chroot: rebuild it from the
	# current lists when the install pass has not finished (a changed list would otherwise keep old names)
	if [ ! -e .build/chroot_install-packages.install ]; then
		rm -f .build/chroot_package-lists.install chroot/root/packages.chroot
	fi
	# mounts do not survive a reboot: let live-build mount them again
	for s in chroot_devpts chroot_proc chroot_selinuxfs chroot_sysfs chroot_tmpfs; do rm -f ".build/$s"; done
	if [ -d chroot/var/lib/dpkg ] && [ -n "$(ls -A chroot/var/lib/dpkg/updates 2>/dev/null)" ]; then
		mount -t proc proc chroot/proc; mount --bind /dev chroot/dev; mount -t sysfs sysfs chroot/sys
		chroot chroot dpkg --configure -a || true
		umount chroot/sys chroot/dev chroot/proc
	fi
fi
# 2.0 r15/r16: "lb build" split into its stages so the final apt sources go in after the chroot stage.
# They use the packages' own keyrings (signed-by /usr/share/keyrings/...); live-build's build-time lists for the
# same repositories use its trusted.gpg.d keys, and with both present apt refuses to run ("Conflicting values set
# for option Signed-By"). r16: the final files carry the build-time lists' names (prestium-tor.list,
# prestium-i2pd.list, prestium-librewolf.list), so whenever live-build re-adds its lists (a --resume, or
# "lb binary" configuring its tool chroot, which may be a full copy of the image chroot) it overwrites them
# instead of adding a second entry. Final copies left from an earlier run are removed first, and the older
# names (r14 and earlier) too; they are installed again once the chroot stage is complete.
run_lb(){ lb "$@" 2>&1 | tee -a "$LOG"; [ "${PIPESTATUS[0]}" = 0 ] || { echo "lb $* failed, see $LOG"; exit 1; }; }
APTF=config/includes.chroot/usr/share/prestium/build/apt
SLD=chroot/etc/apt/sources.list.d
if [ -d "$SLD" ]; then
	rm -f "$SLD/tor.list" "$SLD/purplei2p.list" "$SLD/librewolf.sources"
	for f in "$APTF"/*; do
		t="$SLD/$(basename "$f")"
		if [ -e "$t" ] && grep -q 'signed-by=/usr/share/keyrings/' "$t"; then rm -f "$t"; fi
	done
fi
run_lb bootstrap
run_lb chroot
for f in config/archives/*.list.chroot; do
	[ ! -e "chroot/etc/apt/sources.list.d/$(basename "$f" .chroot)" ] || { echo "build-time apt list $(basename "$f" .chroot) still in the chroot"; exit 1; }
done
install -m 644 "$APTF"/* chroot/etc/apt/sources.list.d/
run_lb installer
run_lb binary
run_lb source   # no-op unless sources are enabled (same stages as "lb build")

# 4. name + checksum
ISO=$(ls -t Prestium-2.0-amd64.hybrid.iso live-image-amd64.hybrid.iso Prestium-2.0*.iso 2>/dev/null | head -1 || true)
[ -n "$ISO" ] || { echo "no ISO produced"; exit 1; }
[ "$ISO" = "$OUT" ] || mv -f "$ISO" "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
cat "$OUT.sha256"
