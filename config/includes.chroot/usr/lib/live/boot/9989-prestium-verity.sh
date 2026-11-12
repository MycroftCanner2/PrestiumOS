#!/bin/sh
# Prestium 2.1: dm-verity is required for every live image (sourced by live-boot in the initramfs;
# hook 0405 calls prestium_verity_check from setup_unionfs in 9990-overlay.sh before each image is
# mounted). live-boot on its own falls back to a plain mount when "<image>.verity" is missing, and
# would take the root hash from "<image>.roothash" on the same USB stick; both are refused here.
# The expected root hash comes from the kernel command line (dm-verity-root-hash=<image>:<hash>,
# written into the boot menus by hook 9010 at build time).

prestium_verity_fail ()
{
	# panic is live-boot's/initramfs-tools' "drop to a shell"; with panic=0 on the command line it
	# reboots. Either way the image is not mounted.
	panic "Prestium: $*. The USB stick may have been changed; refusing to boot."
}

prestium_verity_check ()
{
	_pv_image="${1}"
	_pv_name=$(basename "${_pv_image}")
	case "${_pv_name}" in
		*.squashfs) ;;
		*) prestium_verity_fail "unexpected live image '${_pv_name}' (only squashfs images with dm-verity are allowed)" ;;
	esac
	[ -f "${_pv_image}" ] || prestium_verity_fail "live image '${_pv_name}' is not a file"
	[ -f "${_pv_image}.verity" ] || prestium_verity_fail "'${_pv_name}' has no dm-verity hash tree"
	_pv_hash=$(get_dm_verity_hash "${_pv_name}" "${DM_VERITY_ROOT_HASH}")
	[ -n "${_pv_hash}" ] || prestium_verity_fail "no dm-verity root hash for '${_pv_name}' on the kernel command line"
	case "${_pv_hash}" in
		*[!0-9a-f]*) prestium_verity_fail "malformed dm-verity root hash for '${_pv_name}'" ;;
	esac
	[ "${#_pv_hash}" -eq 64 ] || prestium_verity_fail "malformed dm-verity root hash for '${_pv_name}'"
	case "$(mount --version 2>/dev/null)" in
		*verity*) ;;
		*) prestium_verity_fail "the initramfs mount has no dm-verity support" ;;
	esac
	[ -e /sys/module/dm_verity ] || modprobe -q dm-verity || prestium_verity_fail "the dm-verity module is missing"
	return 0
}
