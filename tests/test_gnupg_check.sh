#!/bin/bash
# Prestium 2.1 (review of 4ccd585): prestium-gnupg-check flags an unconfined GnuPG daemon whose user's
# config names a helper outside /usr, and nothing else; the pinentry profile attaches to the binaries.
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; S=$I/usr/local/sbin/prestium-gnupg-check
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; f=0
ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; f=1; }
printf '#!/bin/sh\necho "$@" >> %s/flag\n' "$T" > "$T/flag.sh"; chmod 755 "$T/flag.sh"
mkdir -p "$T/home/.gnupg"; echo "user:x:1000:1000::$T/home:/bin/bash" > "$T/passwd"
proc(){ rm -rf "$T/proc"; mkdir -p "$T/proc/42/attr/apparmor"; echo "$1" > "$T/proc/42/comm"
  printf 'Uid:\t%s\t%s\n' "$2" "$2" > "$T/proc/42/status"; echo "$3" > "$T/proc/42/attr/apparmor/current"; }
run(){ rm -f "$T/flag"; PRESTIUM_PROC=$T/proc PRESTIUM_FLAG=$T/flag.sh PRESTIUM_PASSWD=$T/passwd sh "$S" >/dev/null; }
echo "pinentry-program /usr/bin/pinentry-gnome3" > "$T/home/.gnupg/gpg-agent.conf"
proc gpg-agent 1000 unconfined; run; grep -q "^clear gnupg-helper" "$T/flag" && ok "helper under /usr: no flag" || bad "false flag"
echo "  pinentry-program /home/user/.x/evil" > "$T/home/.gnupg/gpg-agent.conf"
run; grep -q "^set gnupg-helper .*evil" "$T/flag" && ok "unconfined agent, helper outside /usr: flagged" || bad "not flagged"
echo "scdaemon-program /tmp/sc" > "$T/home/.gnupg/scdaemon.conf"; proc scdaemon 1000 unconfined; run
grep -q "^set gnupg-helper .*/tmp/sc" "$T/flag" && ok "scdaemon-program: flagged" || bad "scdaemon not flagged"
proc gpg-agent 1000 "claws-mail//gpg-agent (enforce)"; run; grep -q "^clear" "$T/flag" && ok "confined agent: no flag" || bad "confined flagged"
proc gpg-agent 0 unconfined; run; grep -q "^clear" "$T/flag" && ok "root daemon ignored" || bad "root"
proc bash 1000 unconfined; run; grep -q "^clear" "$T/flag" && ok "other programs ignored" || bad "other"
grep -q '/usr/local/\*) P=/proc; FLAG=/usr/local/lib/prestium/safety-flag' "$S" && ok "installed copy ignores PRESTIUM_* overrides" || bad "overrides"
grep -q '^profile prestium_pinentry /usr/bin/pinentry{,-gnome3,-gtk2,-gtk-2,-curses,-x11} {' "$I/etc/apparmor.d/prestium.pinentry" && ok "pinentry profile attached" || bad "pinentry attachment"
grep -q 'timers.target.wants/prestium-gnupg-check.timer' "$I/usr/share/prestium/build/systemd-wants.txt" && ok "timer enabled" || bad "timer not enabled"
exit $f
