#!/bin/bash
# Prestium 2.1: prestium-firewall-early (early drop-all and ferm's ExecStop) fails loudly. Stub backends
# check a missing binary and a failed command (non-zero, everything else still applied); with root,
# a real run in a private network namespace must leave DROP policies that -S reads back.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
S=$R/config/includes.chroot/usr/local/sbin/prestium-firewall-early
H=$R/config/hooks/live/0400-prestium-system.hook.chroot
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
mkdir -p "$T/none" "$T/good" "$T/badp"
for x in grep; do ln -s "$(command -v $x)" "$T/none/$x"; ln -s "$(command -v $x)" "$T/good/$x"; ln -s "$(command -v $x)" "$T/badp/$x"; done
# stub backend: records calls, answers -S like a drop-all table; FAILP=chain makes "-P chain DROP" fail
stub(){ cat > "$1/$2" <<E
#!/bin/sh
echo "$2 \$*" >> "$T/calls"
[ "\$2" = -P ] && [ "\$3" = "\${FAILP:-}" ] && exit 4
[ "\$2" = -S ] && printf '%s\n' "-P INPUT DROP" "-P FORWARD DROP" "-P OUTPUT DROP" "-A INPUT -i lo -j ACCEPT" "-A OUTPUT -o lo -j ACCEPT"
exit 0
E
chmod +x "$1/$2"; }
for t in iptables-legacy ip6tables-legacy; do stub "$T/good" $t; stub "$T/badp" $t; done
stub "$T/none" ip6tables-legacy   # IPv4 backend missing, IPv6 present
run(){ rm -f "$T/calls"; env -i PATH="$1" FAILP="${2:-}" /bin/sh "$S" 2>"$T/err"; }
run "$T/good"; [ $? = 0 ] && ok "both backends set and read back: exit 0" || bad "good run failed: $(cat "$T/err")"
[ "$(grep -c -- '-P .* DROP' "$T/calls")" = 6 ] && ok "six DROP policies applied" || bad "policies: $(cat "$T/calls")"
run "$T/none"; rc=$?
[ $rc != 0 ] && grep -q 'iptables-legacy is missing' "$T/err" && ok "missing iptables-legacy: exit $rc" || bad "missing binary not reported (rc $rc)"
grep -q '^ip6tables-legacy -w -P INPUT DROP' "$T/calls" && ok "IPv6 still set to drop-all when IPv4 is missing" || bad "IPv6 skipped"
run "$T/badp" OUTPUT; rc=$?
[ $rc != 0 ] && grep -q -- '-P OUTPUT DROP failed' "$T/err" && ok "failed -P: exit $rc" || bad "failed policy not reported (rc $rc)"
grep -q -- '-A OUTPUT -o lo -j ACCEPT' "$T/calls" && grep -q '^ip6tables-legacy -w -P FORWARD DROP' "$T/calls" \
  && ok "the remaining rules were still applied" || bad "stopped after the first failure"
grep -qx 'exit \$rc' "$S" && ! grep -qx 'exit 0' "$S" && ok "no unconditional exit 0" || bad "unconditional exit 0"
# ferm and this script on the same backend
grep -q 'update-alternatives --set \$a /usr/sbin/\$a-legacy' "$H" && grep -q 'for a in iptables ip6tables; do' "$H" \
  && ok "hook 0400 pins iptables/ip6tables to legacy (ferm's backend)" || bad "backend not pinned in hook 0400"
# real run (root, private netns)
SUDO=; [ "$(id -u)" = 0 ] || { sudo -n true 2>/dev/null && SUDO="sudo -n"; }
if { [ "$(id -u)" = 0 ] || [ -n "$SUDO" ]; } && command -v iptables-legacy >/dev/null && command -v unshare >/dev/null; then
  out=$($SUDO unshare -n sh -c "sh '$S' >/dev/null 2>&1; echo rc=\$?; iptables-legacy -S 2>/dev/null; echo ---; ip6tables-legacy -S 2>/dev/null" 2>/dev/null)
  rc=$(printf '%s\n' "$out" | sed -n 's/^rc=//p'); v4=$(printf '%s\n' "$out" | sed -n '/^rc=/,/^---$/p'); v6=$(printf '%s\n' "$out" | sed -n '/^---$/,$p')
  if [ "$(printf '%s\n' "$v4" | grep -cxE -- '-P (INPUT|OUTPUT|FORWARD) DROP')" = 3 ]; then
    ok "real run: iptables-legacy -S shows DROP on INPUT, OUTPUT and FORWARD"
    if [ "$(printf '%s\n' "$v6" | grep -cxE -- '-P (INPUT|OUTPUT|FORWARD) DROP')" = 3 ]; then
      [ "$rc" = 0 ] && ok "real run: ip6tables-legacy too, exit 0" || bad "real run: exit $rc with both backends set"
    else
      [ "$rc" != 0 ] && ok "real run: no IPv6 xtables here, and the script exits $rc (reported, not hidden)" || bad "real run: IPv6 not set but exit 0"
    fi
  else
    echo "SKIP real run (no legacy xtables in this kernel/namespace)"
  fi
else echo "SKIP real run (needs root, iptables-legacy and unshare)"; fi
[ $fail = 0 ] && echo "firewall early: OK"; exit $fail
