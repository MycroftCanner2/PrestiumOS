#!/bin/sh
# Prestium 2.1: the kernel command line must be this image's own (cmdline.policy next to this file).
# Sourced, never run:
#  - in the initramfs, by /init right after /scripts/functions (initramfs-tools hook prestium-cmdline
#    puts it there, before /init reads break=, init=, debug or panic= and before any boot script
#    runs): prestium_cmdline_guard refuses to go on and restarts the computer after 10 s;
#  - by /usr/local/sbin/prestium-cmdline-check (prestium-cmdline-check.service, before AppArmor
#    loads; prestium-safety-notify);
#  - by hook 9030 at build time, against every boot entry.
# Plain POSIX sh for busybox ash and klibc dash: no grep, sed or awk (the initramfs may lack them),
# nothing taken from the environment (the kernel turns unknown name=value options into environment
# variables of /init).
# Every token must match a "require" or "allow" line of the policy, each line at most once, and every
# "require" line must be matched. Only letters, digits, spaces and "=.,:_/+()-" may appear, so quotes,
# "$", globs, tabs and the like are refused before the line is split into words.

prestium_cmdline_match ()
{
	# $1: policy token, $2: command-line token
	case "${1}" in
		*'<hex64>')
			_pcm_p=${1%'<hex64>'}
			case "${2}" in
				"${_pcm_p}"*) ;;
				*) return 1 ;;
			esac
			_pcm_r=${2#"${_pcm_p}"}
			[ "${#_pcm_r}" -eq 64 ] || return 1
			case "${_pcm_r}" in
				*[!0-9a-f]*) return 1 ;;
			esac
			return 0
			;;
		*'<live-kernel>'|*'<live-initrd>')
			case "${1}" in
				*'<live-kernel>') _pcm_p=${1%'<live-kernel>'}; _pcm_f=vmlinuz ;;
				*) _pcm_p=${1%'<live-initrd>'}; _pcm_f=initrd.img ;;
			esac
			case "${2}" in
				"${_pcm_p}"*) ;;
				*) return 1 ;;
			esac
			_pcm_r=${2#"${_pcm_p}"}
			# GRUB may name the device first: (hd0,gpt1)/live/vmlinuz-...
			case "${_pcm_r}" in
				'('*')'*) _pcm_r=${_pcm_r#*')'} ;;
			esac
			case "${_pcm_r}" in
				"/live/${_pcm_f}"|"/live/${_pcm_f}-"*) ;;
				*) return 1 ;;
			esac
			case "${_pcm_r#/live/}" in
				*[!A-Za-z0-9._+-]*) return 1 ;;
			esac
			return 0
			;;
	esac
	[ "${1}" = "${2}" ]
}

prestium_cmdline_problems ()
{
	# $1: the kernel command line, $2: the policy file. Prints one problem per line; returns 0 when
	# there are none.
	_pc_line=${1}
	_pc_pol=${2}
	if [ ! -f "${_pc_pol}" ] || [ ! -r "${_pc_pol}" ]
	then
		echo "the boot policy ${_pc_pol} is missing"
		return 1
	fi
	_pc_rules=
	_pc_nreq=0
	_pc_out=
	while read -r _pc_k _pc_p _pc_x
	do
		case "${_pc_k}" in
			''|'#'*) continue ;;
			require|allow) ;;
			*) echo "the boot policy has an unknown line: ${_pc_k}"; return 1 ;;
		esac
		if [ -z "${_pc_p}" ] || [ -n "${_pc_x}" ]
		then
			echo "the boot policy has a malformed line: ${_pc_k} ${_pc_p}"
			return 1
		fi
		[ "${_pc_k}" = require ] && _pc_nreq=$((_pc_nreq + 1))
		_pc_rules="${_pc_rules}${_pc_k} ${_pc_p}
"
	done < "${_pc_pol}"
	if [ "${_pc_nreq}" -eq 0 ]
	then
		echo "the boot policy requires nothing"
		return 1
	fi
	if [ "${#_pc_line}" -gt 4096 ]
	then
		echo "the kernel command line is too long (${#_pc_line} characters)"
		return 1
	fi
	case "${_pc_line}" in
		*[!A-Za-z0-9=.,:_/+\(\)\ -]*)
			echo "the kernel command line has characters Prestium never uses (quotes, \$, tabs or similar)"
			return 1
			;;
	esac
	_pc_used=' '
	_pc_n=0
	for _pc_t in ${_pc_line}
	do
		_pc_n=$((_pc_n + 1))
		if [ "${_pc_n}" -gt 256 ]
		then
			_pc_out="${_pc_out}too many boot options
"
			break
		fi
		_pc_hit=
		while read -r _pc_k _pc_p
		do
			[ -n "${_pc_p}" ] || continue
			if prestium_cmdline_match "${_pc_p}" "${_pc_t}"
			then
				_pc_hit=${_pc_p}
				break
			fi
		done <<PRESTIUM_RULES
${_pc_rules}
PRESTIUM_RULES
		if [ -z "${_pc_hit}" ]
		then
			_pc_out="${_pc_out}unexpected boot option: ${_pc_t}
"
			continue
		fi
		case "${_pc_used}" in
			*" ${_pc_hit} "*) _pc_out="${_pc_out}boot option given twice: ${_pc_t}
" ;;
			*) _pc_used="${_pc_used}${_pc_hit} " ;;
		esac
	done
	while read -r _pc_k _pc_p
	do
		[ "${_pc_k}" = require ] || continue
		case "${_pc_used}" in
			*" ${_pc_p} "*) ;;
			*) _pc_out="${_pc_out}missing boot option: ${_pc_p}
" ;;
		esac
	done <<PRESTIUM_RULES
${_pc_rules}
PRESTIUM_RULES
	[ -z "${_pc_out}" ] && return 0
	printf '%s' "${_pc_out}"
	return 1
}

prestium_cmdline_report ()
{
	# $1: problems, one per line. At most 12 are shown.
	echo ""
	echo "Prestium: this computer was not started with Prestium's own boot settings."
	echo "AppArmor, dm-verity or other protections could be off, so Prestium will not start this way."
	_pr_n=0
	while read -r _pr_l
	do
		[ -n "${_pr_l}" ] || continue
		_pr_n=$((_pr_n + 1))
		if [ "${_pr_n}" -gt 12 ]
		then
			echo "  ..."
			break
		fi
		echo "  - ${_pr_l}"
	done <<PRESTIUM_PROBLEMS
${1}
PRESTIUM_PROBLEMS
	echo "Start the computer from the Prestium USB stick and choose a Prestium entry in its boot menu."
}

prestium_cmdline_reboot ()
{
	# immediate restart: nothing is mounted read-write in the initramfs. /proc/sysrq-trigger works for
	# root whatever kernel.sysrq says.
	echo b > /proc/sysrq-trigger 2>/dev/null
	reboot -f 2>/dev/null
}

prestium_cmdline_refuse ()
{
	# $1: problems. Never returns and never opens a shell (no panic(): without panic= on the command
	# line, initramfs-tools' panic would offer one).
	trap '' HUP INT QUIT TERM TSTP 2>/dev/null
	prestium_cmdline_report "${1}"
	echo "Restarting in 10 seconds."
	sleep 10
	prestium_cmdline_reboot
	while :
	do
		sleep 60
		prestium_cmdline_reboot
	done
}

prestium_cmdline_guard ()
{
	# the initramfs entry point: /proc/cmdline against the policy copied into the initramfs
	_pg_cmdline=$(cat /proc/cmdline 2>/dev/null) || _pg_cmdline=
	if _pg_problems=$(prestium_cmdline_problems "${_pg_cmdline}" /conf/prestium-cmdline.policy)
	then
		return 0
	fi
	prestium_cmdline_refuse "${_pg_problems}"
}
