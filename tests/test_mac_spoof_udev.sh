#!/bin/sh
# Prestium 2.0 r18: the MAC spoofing udev rule and script.
# 1. nomacspoof is imported on its own line (udev tests ENV{} before IMPORT{} within one line).
# 2. The script gets the interface index (stable across rename), not the pre-rename %k name.
# 3. The script finds the renamed device from its index, and leaves an already-spoofed one alone.
set -e
R=$(cd "$(dirname "$0")/.." && pwd)/config/includes.chroot
U=$R/etc/udev/rules.d/70-prestium-mac-spoof.rules
S=$R/usr/local/lib/prestium-spoof-mac
rules=$(grep -v '^#' "$U" | grep -v '^$')
imp=$(printf '%s\n' "$rules" | grep -c 'IMPORT{cmdline}="nomacspoof"')
[ "$imp" -eq 1 ]
printf '%s\n' "$rules" | grep 'IMPORT{cmdline}' | grep -vq 'RUN+=' || { echo "FAIL: import shares a line with RUN"; exit 1; }
printf '%s\n' "$rules" | grep 'RUN+=' | grep -q 'ENV{nomacspoof}!="?\*"'
printf '%s\n' "$rules" | grep 'RUN+=' | grep -q '\$env{IFINDEX}'
! printf '%s\n' "$rules" | grep 'RUN+=' | grep -q '%k' || { echo "FAIL: RUN still uses %k"; exit 1; }
# fake sysfs + stub tools
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/sys/class/net/enp1s0" "$T/bin"
echo 2 > "$T/sys/class/net/enp1s0/ifindex"
echo 52:54:00:12:34:56 > "$T/sys/class/net/enp1s0/address"
cat > "$T/bin/logger" <<'S'
#!/bin/sh
shift 2; echo "$*" >> "$LOG"
S
cat > "$T/bin/ip" <<'S'
#!/bin/sh
case "$*" in "-o link show dev enp1s0") [ -n "$PERM" ] && echo "2: enp1s0: <BROADCAST> mtu 1500 link/ether $(cat $PRESTIUM_SYSFS/class/net/enp1s0/address) brd ff:ff:ff:ff:ff:ff permaddr $PERM" || echo "2: enp1s0: <BROADCAST> mtu 1500 link/ether x";; esac
exit 0
S
chmod +x "$T/bin/logger" "$T/bin/ip"
sed 's#/usr/bin/macchanger#macchanger#' "$S" > "$T/spoof"; chmod +x "$T/spoof"
cat > "$T/bin/macchanger" <<'S'
#!/bin/sh
echo 52:54:00:ab:cd:ef > "$PRESTIUM_SYSFS/class/net/$2/address"
S
chmod +x "$T/bin/macchanger"
export PRESTIUM_SYSFS=$T/sys LOG=$T/log PATH=$T/bin:$PATH
PERM= "$T/spoof" 2
grep -q 'enp1s0: MAC address spoofed' "$T/log" || { echo "FAIL: index lookup"; cat "$T/log"; exit 1; }
[ "$(cat "$T/sys/class/net/enp1s0/address")" = 52:54:00:ab:cd:ef ]
: > "$T/log"
PERM=52:54:00:12:34:56 "$T/spoof" 2
grep -q 'already spoofed' "$T/log" || { echo "FAIL: re-spoof"; cat "$T/log"; exit 1; }
: > "$T/log"
"$T/spoof" 9
grep -q 'gone' "$T/log" || { echo "FAIL: missing device"; exit 1; }
# boot menu: a "spoofing off" entry in both menus
B=$R/../bootloaders
grep -q '@APPEND_LIVE@ nomacspoof' "$B/grub-pc/grub.cfg"
grep -q '@APPEND_LIVE@ nomacspoof' "$B/syslinux_common/live.cfg.in"
echo "mac spoof udev: OK"
