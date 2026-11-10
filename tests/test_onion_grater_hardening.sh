#!/bin/bash
# 2.1 (security audit): onion-grater holds CAP_SYS_PTRACE to read /proc of the connecting app. It
# must not be able to trace or write other processes: seccomp drops @debug, and an enforced AppArmor
# profile allows ptrace read only and denies /proc/<pid>/mem. Static checks; compiles the profile
# when apparmor_parser is installed.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
U=$I/etc/systemd/system/prestium-onion-grater.service
P=$I/etc/apparmor.d/usr.local.sbin.prestium-onion-grater
H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot
grep -qx 'SystemCallFilter=~@debug' "$U" && ok "unit: no @debug syscalls (ptrace, process_vm_*)" || bad "unit: @debug not filtered"
grep -qx 'SystemCallFilter=@system-service' "$U" && ok "unit: @system-service allow-list" || bad "unit: no allow-list"
grep -qx 'CapabilityBoundingSet=CAP_SYS_PTRACE' "$U" && ok "unit: only CAP_SYS_PTRACE" || bad "unit: capability set"
grep -qx 'NoNewPrivileges=yes' "$U" && ok "unit: no_new_privs" || bad "unit: NoNewPrivileges"
grep -q '^profile prestium_onion_grater /usr/local/sbin/prestium-onion-grater ' "$P" && ok "profile attaches to the filter" || bad "profile attach"
grep -q 'flags=(.*complain' "$P" && bad "profile in complain mode" || ok "profile enforced"
grep -qx '  ptrace (read),' "$P" && ok "profile: ptrace read" || bad "profile: no ptrace (read)"
grep -qx '  deny ptrace (trace),' "$P" && ok "profile: trace denied" || bad "profile: trace not denied"
grep -qx '  deny @{PROC}/\*/mem rwx,' "$P" && ok "profile: /proc/*/mem denied" || bad "profile: mem not denied"
grep -E '^\s*ptrace' "$P" | grep -v '(read)' | grep -vq 'deny' && bad "profile: wider ptrace rule" || ok "profile: no wider ptrace rule"
grep -qE '^\s*(/\*\*|@\{PROC\}/\*\*) *[a-z]*w' "$P" && bad "profile: broad write rule" || ok "profile: no broad write rule"
# every path the filter opens is allowed
for x in /run/onion-grater/control /run/tor/control /run/tor/control.authcookie /opt/tor-browser/Browser/firefox.real; do
  grep -q "$x" "$I/usr/local/sbin/prestium-onion-grater" || continue
  grep -q "^  $x " "$P" && ok "profile allows $x" || bad "profile lacks $x"
done
# AppArmor checks ptrace on both sides when the tracee's profile has ptrace rules: Tor Browser's has
grep -qx '  ptrace (readby) peer=prestium_onion_grater,' "$I/etc/apparmor.d/torbrowser.Browser.firefox" \
  && ok "Tor Browser's profile lets onion-grater read its identity" || bad "torbrowser_firefox lacks ptrace readby"
for f in "$I"/etc/apparmor.d/*; do
  [ -f "$f" ] || continue; n=$(basename "$f")
  case $n in usr.local.sbin.prestium-onion-grater|torbrowser.Browser.firefox) continue;; esac
  # a profile that may connect to the filter (an allow rule for /run/onion-grater) and has ptrace rules
  if grep -E '/run/onion-grater' "$f" | grep -vqE '^\s*(deny|#)' && grep -qE '^\s*ptrace' "$f"; then
    grep -q 'readby) peer=prestium_onion_grater' "$f" && ok "$n allows readby" || bad "$n uses the control filter and has ptrace rules but no readby"
  fi
done
grep -q 'usr.local.sbin.prestium-onion-grater' "$H" && ok "hook 0600 enforces and parses it" || bad "hook 0600 misses it"
grep -q '/etc/apparmor.d/usr.local.sbin.prestium-onion-grater$' "$I/usr/share/prestium/build/perms.txt" && ok "perms.txt" || bad "perms.txt"
if command -v apparmor_parser >/dev/null; then
  W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cp -r /etc/apparmor.d/. "$W"/ 2>/dev/null; cp -r "$I/etc/apparmor.d"/. "$W"/
  apparmor_parser -QK -b "$W" "$W/usr.local.sbin.prestium-onion-grater" 2>/dev/null && ok "profile compiles" || bad "profile compiles"
else echo "SKIP apparmor_parser missing (the build hook compiles it)"; fi
exit $fail
