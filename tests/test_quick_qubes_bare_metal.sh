#!/bin/bash
# Security review F-08 (quick_qubes): the build without CPU microcode or firmware says so when it is
# started on real hardware: prestium-bare-metal.service (never in a VM) raises a safety flag that the
# desktop shows as "Protection NOT active", and the boot menu says "VM only".
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
U=$I/etc/systemd/system/prestium-bare-metal.service
[ -f "$U" ] && ok "unit present" || { bad "no prestium-bare-metal.service"; exit 1; }
grep -qx 'ConditionVirtualization=!vm' "$U" && ok "runs only outside a virtual machine" || bad "ConditionVirtualization"
grep -q '^ExecStart=/usr/local/lib/prestium/safety-flag set bare-metal "' "$U" && ok "raises the bare-metal safety flag" || bad "ExecStart"
for k in 'ProtectSystem=strict' 'ReadWritePaths=/run/prestium/safety' 'CapabilityBoundingSet=' 'NoNewPrivileges=yes' 'PrivateNetwork=yes'; do
  grep -qx "$k" "$U" && ok "sandbox: $k" || bad "sandbox: $k missing"; done
grep -qx '/etc/systemd/system/multi-user.target.wants/prestium-bare-metal.service /etc/systemd/system/prestium-bare-metal.service' \
  "$I/usr/share/prestium/build/systemd-wants.txt" && ok "enabled (systemd-wants.txt)" || bad "not enabled"
grep -qx '0644 root root /etc/systemd/system/prestium-bare-metal.service' "$I/usr/share/prestium/build/perms.txt" && ok "perms.txt" || bad "perms.txt"
msg=$(sed -n 's/^ExecStart=[^"]*"\(.*\)"$/\1/p' "$U")
[ "${#msg}" -le 600 ] && ok "message fits the notifier (${#msg} <= 600 characters)" || bad "message is ${#msg} characters (notifier shows 600)"
case $msg in *microcode*"standard Prestium ISO"*) ok "message says what is missing and what to use" ;; *) bad "message: $msg" ;; esac
# the flag helper writes it where the notifier reads it
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
sed "s#^D=/run/prestium/safety#D=$T/safety#" "$I/usr/local/lib/prestium/safety-flag" > "$T/sf"
mkdir -p "$T/safety"; PATH=/usr/bin:/bin sh "$T/sf" set bare-metal "$msg" 2>/dev/null; [ "$(cat "$T/safety/bare-metal" 2>/dev/null)" = "$msg" ] && ok "safety-flag writes the message" || bad "safety-flag"
grep -q 'alert "flag:${f##\*/}"' "$I/usr/local/bin/prestium-safety-notify" && ok "the notifier alerts on every flag" || bad "notifier flags"
H=$R/config/hooks/live/9000-prestium-boot-menu.hook.binary
grep -qF '[ "$VAR" != quick_qubes ] || V="$V, VM only"' "$H" && ok "boot menu: VM only" || bad "boot menu label"
if command -v systemd-analyze >/dev/null; then
  o=$(systemd-analyze verify "$U" 2>&1 | grep -v 'safety-flag\|Command .* is not executable\|not found\|Failed to\|Unit is bound' || true)
  [ -z "$o" ] && ok "systemd-analyze verify: no complaints" || echo "NOTE systemd-analyze: $o"
fi
exit $fail
