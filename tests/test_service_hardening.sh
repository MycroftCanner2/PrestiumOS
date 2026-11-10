#!/bin/bash
# 2.1 (security audit): root daemons keep only the capabilities they use. Static checks on the unit
# files; "systemd-analyze security" scores them when systemd-analyze is installed (needs the units
# loaded, so it is informational here).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); U=$R/config/includes.chroot/etc/systemd/system; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
caps(){ sed -n 's/^CapabilityBoundingSet=//p' "$U/$1"; }
[ "$(caps prestium-mac-guard.service)" = CAP_NET_ADMIN ] && ok "mac-guard: CAP_NET_ADMIN only" || bad "mac-guard caps: $(caps prestium-mac-guard.service)"
for k in SystemCallFilter=@system-service RestrictAddressFamilies='AF_UNIX AF_NETLINK' NoNewPrivileges=yes ProtectSystem=strict; do
  grep -qx "$k" "$U/prestium-mac-guard.service" && ok "mac-guard: $k" || bad "mac-guard: no $k"; done
b=$(caps prestium-wl-broker.service)
[ -n "$b" ] && ok "wl-broker: bounded capabilities" || bad "wl-broker: no CapabilityBoundingSet"
for c in CAP_SYS_ADMIN CAP_NET_ADMIN CAP_SYS_MODULE CAP_SYS_RAWIO CAP_MKNOD CAP_SYS_TIME CAP_NET_RAW CAP_BPF CAP_SYS_BOOT CAP_MAC_ADMIN CAP_SETFCAP CAP_SETPCAP CAP_LINUX_IMMUTABLE; do
  case " $b " in *" $c "*) bad "wl-broker keeps $c";; esac; done
ok "wl-broker: no admin, network, module, raw-io, mknod, clock or MAC capability"
# what the broker itself needs (and sudo in the tools it starts)
for c in CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE CAP_SETUID CAP_SETGID CAP_KILL CAP_SYS_PTRACE CAP_AUDIT_WRITE CAP_SYS_RESOURCE; do
  case " $b " in *" $c "*) ;; *) bad "wl-broker lacks $c (needed)";; esac; done
grep -qx 'NoNewPrivileges=yes' "$U/prestium-wl-broker.service" && bad "wl-broker: NoNewPrivileges would break swaylock's PAM helper" || ok "wl-broker: no NoNewPrivileges (its tools use setuid helpers)"
grep -q '^SystemCallFilter' "$U/prestium-wl-broker.service" && bad "wl-broker: a syscall filter would bind the session tools too" || ok "wl-broker: no syscall filter"
# 2.1 (audit L-4): the rest of the sandbox the broker's tools can live with, and no system uids
for k in ProtectSystem=yes 'RestrictAddressFamilies=AF_UNIX AF_NETLINK' RestrictNamespaces=yes ProtectKernelLogs=yes ProtectControlGroups=yes SystemCallArchitectures=native RestrictSUIDSGID=yes; do
  grep -qx "$k" "$U/prestium-wl-broker.service" && ok "wl-broker: $k" || bad "wl-broker: no $k"; done
grep -qx 'ProtectSystem=strict' "$U/prestium-wl-broker.service" && bad "wl-broker: strict would block chpasswd and screenshots" || ok "wl-broker: /etc and home stay writable"
B=$R/config/includes.chroot/usr/local/sbin/prestium-wl-broker
grep -q 'not UID_MIN <= uid <= UID_MAX' "$B" && grep -q '^UID_MIN, UID_MAX = 1000, 60000' "$B" && ok "wl-broker: refuses system uids" || bad "wl-broker uid range"
if command -v systemd-analyze >/dev/null; then
  for u in prestium-wl-broker prestium-mac-guard prestium-onion-grater prestium-vm-netcheck thelounge prestium-timesync prestium-clockfix prestium-usb-watchdog; do
    systemd-analyze security --offline=yes "$U/$u.service" 2>/dev/null | tail -n 1 | sed "s/^/INFO $u: /"; done
else echo "SKIP systemd-analyze missing"; fi
exit $fail
