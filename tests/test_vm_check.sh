#!/bin/bash
# Prestium 2.1: virtual machine detection and network diagnosis. Runs the real prestium-vm-netcheck
# and prestium-vm-notify with stubs on PATH (systemd-detect-virt, journalctl, ss, ip, sleep, notify-send).
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
C=$R/config/includes.chroot
CHK=$C/usr/local/sbin/prestium-vm-netcheck
NOT=$C/usr/local/bin/prestium-vm-notify
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
mkdir -p "$T/bin"
cat > "$T/bin/systemd-detect-virt" <<'S'
#!/bin/sh
echo "${VIRT:-none}"; [ "${VIRT:-none}" != none ]
S
cat > "$T/bin/journalctl" <<'S'
#!/bin/sh
case "$*" in
  *tor@default*) [ -n "$TORLOG" ] && printf '%s\n' "$TORLOG";;
  *prestium-timesync*) [ -n "$SYNCLOG" ] && printf '%s\n' "$SYNCLOG";;
esac; exit 0
S
cat > "$T/bin/ss" <<'S'
#!/bin/sh
[ -n "$SSOUT" ] && printf '%b\n' "$SSOUT"; exit 0
S
cat > "$T/bin/ip" <<'S'
#!/bin/sh
[ -n "$GW" ] && echo "default via $GW dev enp1s0 proto dhcp src 10.0.2.15 metric 100"; exit 0
S
printf '#!/bin/sh\nexit 0\n' > "$T/bin/sleep"
cat > "$T/bin/notify-send" <<'S'
#!/bin/bash
# records "title|body": the last two arguments (after -u/-t options)
printf '%s|%s\n' "${@: -2:1}" "${@: -1}" >> "$ALERTS"
S
chmod +x "$T/bin/"*
P2000='0 0 10.0.2.15:41000 198.51.100.7:23456 uid:2000 ino:1 sk:1'
LOOP='0 0 127.0.0.1:41001 127.0.0.1:4500 uid:2000 ino:2 sk:2'
OTHER='0 0 10.0.2.15:41002 198.51.100.8:443 uid:111 ino:3 sk:3'
check(){ # runs one check round; env: VIRT GW TORLOG SYNCLOG SSOUT
  rm -rf "$T/out"; mkdir -p "$T/out"
  env -i PATH="$T/bin:/usr/bin:/bin" VIRT="${VIRT:-none}" GW="${GW:-}" TORLOG="${TORLOG:-}" SYNCLOG="${SYNCLOG:-}" \
    SSOUT="${SSOUT:-}" PRESTIUM_VM_OUT="$T/out" PRESTIUM_VM_FIRST=0 PRESTIUM_VM_EVERY=0 PRESTIUM_VM_ROUNDS=1 \
    timeout 10 bash "$CHK" >/dev/null 2>&1
  echo $? > "$T/rc"; cat "$T/out/network" 2>/dev/null; }

U=$C/etc/systemd/system/prestium-vm-netcheck.service
grep -qx 'User=prestium-vmcheck' "$U" && grep -qx 'SupplementaryGroups=systemd-journal' "$U" && ok "service: own user, journal group (not root)" || bad "service runs as root"
for k in ProtectProc=invisible IPAddressDeny=any SystemCallFilter=@system-service RestrictNamespaces=yes ProtectKernelLogs=yes; do
  grep -qx "$k" "$U" && ok "service: $k" || bad "service: no $k"; done
grep -q '^sysuser prestium-vmcheck ' "$R/config/hooks/live/0100-prestium-users.hook.chroot" && ok "user prestium-vmcheck created" || bad "no prestium-vmcheck user"
grep -q '^ConditionVirtualization=vm$' $C/etc/systemd/system/prestium-vm-netcheck.service && ok "service runs only in a VM" || bad "no ConditionVirtualization=vm"
grep -qx '/etc/systemd/system/multi-user.target.wants/prestium-vm-netcheck.service /etc/systemd/system/prestium-vm-netcheck.service' \
  $C/usr/share/prestium/build/systemd-wants.txt && ok "service enabled (systemd-wants.txt)" || bad "service not enabled"
for p in "0755 root root /usr/local/sbin/prestium-vm-netcheck" "0755 root root /usr/local/bin/prestium-vm-notify" \
         "0644 root root /etc/systemd/system/prestium-vm-netcheck.service"; do
  grep -qxF "$p" $C/usr/share/prestium/build/perms.txt && ok "perms: $p" || bad "perms missing: $p"; done
grep -qx "d /run/prestium/vm 0755 prestium-vmcheck prestium-vmcheck -" $C/usr/lib/tmpfiles.d/prestium-safety.conf && ok "tmpfiles: /run/prestium/vm" || bad "tmpfiles"
grep -qx 'prestium-run /usr/local/bin/prestium-vm-notify >/dev/null 2>&1 &' $C/etc/xdg/labwc/autostart \
  && [ "$(grep -n vm-notify $C/etc/xdg/labwc/autostart | cut -d: -f1)" -lt "$(grep -n 'safety-notify' $C/etc/xdg/labwc/autostart | tail -1 | cut -d: -f1)" ] \
  && ok "autostart: notifier backgrounded, before the never-returning safety notifier" || bad "autostart line"
! grep -qE 'date -u -s|systemctl (restart|stop|start)|ip (link|addr|route) (add|del|set)' "$CHK" && ok "netcheck changes nothing (no clock, unit or network changes)" || bad "netcheck changes state"

o=$(VIRT=none GW=192.168.122.1 check); [ -z "$o" ] && [ ! -e "$T/out/virt" ] && [ "$(cat $T/rc)" = 0 ] && ok "real hardware: nothing written" || bad "bare metal wrote: $o"

o=$(VIRT=kvm GW=192.168.122.1 TORLOG='Bootstrapped 100% (done): Done' SSOUT="$P2000\n$OTHER" check)
[ -z "$o" ] && [ "$(cat $T/out/virt)" = kvm ] && ok "VM, Tor and I2P connected: virt recorded, no network problem" || bad "false problem: $o"

o=$(VIRT=kvm GW=10.0.2.2 TORLOG='Bootstrapped 10% (conn_done)' SSOUT="$LOOP\n$OTHER" check)
case "$o" in *"Tor NOT connected, I2P has NO peer connections"*) ok "status line";; *) bad "status: $o";; esac
case "$o" in *"user-mode networking"*"User session"*) ok "10.0.2.2: user-mode networking explained";; *) bad "no user-mode hint: $o";; esac
case "$o" in *"Check the clock: the VM thinks it is "*"<clock offset='utc'>"*) ok "no skew evidence, Tor down: clock check with the virt-manager fix";; *) bad "no clock hint: $o";; esac
case "$o" in *"loopback"*|*"(1 peers)"*) bad "loopback counted as a peer";; *) ok "i2pd's own 127.0.0.1 tunnel is not a peer";; esac

o=$(VIRT=kvm GW=192.168.122.1 TORLOG='Bootstrapped 100% (done): Done' SSOUT="0 0 10.0.2.15:41003 198.51.100.9:23456 uid:20000 ino:4 sk:4" check)
case "$o" in *"I2P has NO peer connections"*) ok "uid:20000 is not i2pd (uid 2000): not counted";; *) bad "uid:20000 counted as i2pd: $o";; esac

o=$(VIRT=kvm GW=192.168.122.1 TORLOG=$'Bootstrapped 5%\nReceived NETINFO cell with skewed time: Our clock is 7 hours behind' check)
case "$o" in *"clock is or was wrong (Tor: "*"7 hours behind"*"<clock offset='utc'>"*) ok "Tor skew warning shown with the fix";; *) bad "skew: $o";; esac
# 2.1 (security audit): Tor's text is never copied (its skew lines can name a relay's address)
o=$(VIRT=kvm GW=192.168.122.1 TORLOG=$'Bootstrapped 5%\nReceived NETINFO cell with skewed time (OR:198.51.100.7:9001): It seems that our clock is behind by 7 hours, 3 minutes, or that theirs is ahead. Tor requires an accurate clock' check)
case "$o" in *"198.51.100"*|*"OR:"*|*NETINFO*) bad "Tor's own text (relay address) copied: $o";;
  *"(Tor: clock is 7 hours, 3 minutes behind)"*) ok "connection skew: only the amount and direction, no relay address";; *) bad "connection skew: $o";; esac
o=$(VIRT=kvm GW=192.168.122.1 TORLOG=$'Bootstrapped 5%\nclock skew detected from 203.0.113.9:443' check)
case "$o" in *"203.0.113"*) bad "address copied: $o";; *"(Tor: clock skew reported)"*) ok "unparsed skew line: fixed wording";; *) bad "unparsed skew: $o";; esac
case "$o" in *"user-mode"*) bad "NAT network flagged as user-mode";; *) ok "libvirt NAT not flagged as user-mode";; esac
case "$o" in *"Neither Tor nor I2P connects"*) ok "both down on NAT: host/bridge hint";; *) bad "no both-down hint: $o";; esac

o=$(VIRT=oracle GW=192.168.122.1 TORLOG='Bootstrapped 100% (done): Done' SYNCLOG='median of 3 sources, skew 25200s' SSOUT="$OTHER" check)
case "$o" in *"off by 25200 s at boot"*"Hardware Clock in UTC Time"*) ok "timesync's measured skew and the VirtualBox fix";; *) bad "sync skew: $o";; esac
case "$o" in *"Tor works but I2P doesn't"*"VPN"*) ok "Tor up, no I2P peers: host VPN/firewall hint";; *) bad "no VPN hint: $o";; esac

o=$(VIRT=kvm GW= check)
case "$o" in *"no network: no default route"*) ok "no default route: no network adapter hint";; *) bad "no-route: $o";; esac
case "$o" in *"VPN"*|*"Neither Tor"*) bad "route-less VM got host hints";; *) ok "no host hints without a route";; esac

# a later check that finds both connected removes the old diagnosis
mkdir -p "$T/out2"; echo old > "$T/out2/network"
env -i PATH="$T/bin:/usr/bin:/bin" VIRT=kvm GW=192.168.122.1 TORLOG='Bootstrapped 100%' SSOUT="$P2000" PRESTIUM_VM_OUT="$T/out2" \
  PRESTIUM_VM_FIRST=0 PRESTIUM_VM_EVERY=0 PRESTIUM_VM_ROUNDS=1 timeout 10 bash "$CHK" >/dev/null 2>&1
[ ! -e "$T/out2/network" ] && ok "fixed later: diagnosis removed" || bad "stale diagnosis kept"
[ "$(stat -c %a "$T/out/network" 2>/dev/null || stat -c %a "$T/out/virt")" = 644 ] && ok "files are 0644 (desktop can read)" || bad "mode"

# notifier
run_notify(){ rm -f "$T/alerts"; env -i PATH="$T/bin:/usr/bin:/bin" ALERTS="$T/alerts" PRESTIUM_VM_OUT="$T/n" \
  PRESTIUM_VM_NOTIFY_WAIT=0 PRESTIUM_VM_NOTIFY_POLL=1 PRESTIUM_VM_NOTIFY_LIFE="${1:-1}" timeout 10 bash "$NOT" >/dev/null 2>&1; cat "$T/alerts" 2>/dev/null; }
rm -rf "$T/n"; mkdir -p "$T/n"
o=$(run_notify); [ -z "$o" ] && ok "notifier: no VM file, no alert" || bad "notifier alerted on bare metal: $o"
echo kvm > "$T/n/virt"
o=$(run_notify); case "$o" in "Prestium is running in a virtual machine (kvm)|The host operating system and the virtualization software can see and record"*) ok "notifier: VM warning";; *) bad "no VM warning: $o";; esac
echo "Running in QEMU. Tor NOT connected" > "$T/n/network"
o=$(run_notify); case "$o" in *"Prestium: network problem in the virtual machine|Running in QEMU. Tor NOT connected"*) ok "notifier: shows the diagnosis";; *) bad "no diagnosis alert: $o";; esac
[ "$(printf '%s\n' "$o" | grep -c 'network problem')" = 1 ] && ok "notifier: same diagnosis shown once" || bad "repeated alerts"
echo "Set <clock offset='utc'> & retry" > "$T/n/network"
o=$(run_notify); case "$o" in *"Set &lt;clock offset='utc'&gt; &amp; retry"*) ok "notifier: markup escaped for mako";; *) bad "markup not escaped: $o";; esac
printf 'evil$(touch %s/pwned)\n' "$T" > "$T/n/virt"; run_notify >/dev/null; [ ! -e "$T/pwned" ] && ok "notifier: virt name is not executed" || bad "virt name executed"
[ $fail = 0 ] && echo "vm check: OK"; exit $fail
