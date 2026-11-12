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
run(){ rm -f "$T/flag" "$T/state"; run2; }
run2(){ rm -f "$T/flag"; PRESTIUM_PROC=$T/proc PRESTIUM_FLAG=$T/flag.sh PRESTIUM_PASSWD=$T/passwd PRESTIUM_STATE=$T/state \
  PATH="$T/bin:$PATH" sh "$S" >/dev/null; }
# logger stub: count journal lines
mkdir -p "$T/bin"; printf '#!/bin/sh\necho "$@" >> %s/log\n' "$T" > "$T/bin/logger"; chmod 755 "$T/bin/logger"
conf(){ printf '%s\n' "$1" > "$T/home/.gnupg/gpg-agent.conf"; rm -f "$T/home/.gnupg/scdaemon.conf"; }
flagged(){ grep -q "^set gnupg-helper" "$T/flag"; }
echo "pinentry-program /usr/bin/pinentry-gnome3" > "$T/home/.gnupg/gpg-agent.conf"
proc gpg-agent 1000 unconfined; run; grep -q "^clear gnupg-helper" "$T/flag" && ok "helper under /usr: no flag" || bad "false flag"
echo "  pinentry-program /home/user/.x/evil" > "$T/home/.gnupg/gpg-agent.conf"
run; grep -q "^set gnupg-helper .*evil" "$T/flag" && ok "unconfined agent, helper outside /usr: flagged" || bad "not flagged"
echo "scdaemon-program /tmp/sc" > "$T/home/.gnupg/scdaemon.conf"; proc scdaemon 1000 unconfined; run
grep -q "^set gnupg-helper .*/tmp/sc" "$T/flag" && ok "scdaemon-program: flagged" || bad "scdaemon not flagged"
proc gpg-agent 1000 "claws-mail//gpg-agent (enforce)"; run; grep -q "^clear" "$T/flag" && ok "confined agent: no flag" || bad "confined flagged"
proc gpg-agent 0 unconfined; run; grep -q "^clear" "$T/flag" && ok "root daemon ignored" || bad "root"
proc bash 1000 unconfined; run; grep -q "^clear" "$T/flag" && ok "other programs ignored" || bad "other"
# Review of 7242e00: canonical paths, relative/empty values, quiet when nothing changes
proc gpg-agent 1000 unconfined
conf "pinentry-program /usr/../home/user/.x/evil"; run; flagged && ok "/usr/../home/... flagged" || bad "/usr/.. not flagged"
conf "pinentry-program /usr/bin/../../tmp/evil"; run; flagged && ok "/usr/bin/../../tmp flagged" || bad "/usr/bin/../.. not flagged"
conf "pinentry-program /usr//bin/./pinentry-gnome3"; run; grep -q "^clear" "$T/flag" && ok "/usr//bin/./x not flagged" || bad "odd /usr spelling flagged"
conf "pinentry-program pinentry-gnome3"; run; flagged && ok "relative path flagged" || bad "relative not flagged"
conf "pinentry-program"; run; flagged && ok "empty value flagged" || bad "empty not flagged"
conf 'pinentry-program "/home/user/my evil"'; run; grep -q "^set gnupg-helper .*my evil" "$T/flag" && ok "quoted path with space flagged" || bad "quoted not flagged"
ln -s /usr/bin/env "$T/home/link"; conf "pinentry-program $T/home/link"; run
flagged && ok "home symlink into /usr flagged (owner could repoint it)" || bad "home symlink accepted"
if [ -L /bin ] && [ "$(realpath /bin)" = /usr/bin ]; then
  conf "pinentry-program /bin/sh"; run; grep -q "^clear" "$T/flag" && ok "/bin/sh (merged /usr symlink) not flagged" || bad "/bin/sh flagged"
else echo "SKIP /bin is not a symlink into /usr here"; fi
if [ -L /etc/alternatives/pinentry ] && case "$(realpath /etc/alternatives/pinentry)" in /usr/*) true;; *) false;; esac; then
  conf "pinentry-program /etc/alternatives/pinentry"; run; grep -q "^clear" "$T/flag" && ok "alternatives link into /usr not flagged" || bad "alternatives flagged"
else echo "SKIP no /etc/alternatives/pinentry here"; fi
conf "pinentry-program /home/user/.x/evil"; rm -f "$T/log"; run; run2; run2
[ "$(grep -c . "$T/log")" = 1 ] && ok "one journal line for three identical runs" || bad "journal noise: $(grep -c . "$T/log") lines"
grep -qs "^set" "$T/flag" && bad "flag re-set on unchanged finding" || ok "flag not re-set when unchanged"
conf "pinentry-program /usr/bin/pinentry-gnome3"; run2; grep -q "^clear" "$T/flag" && [ "$(grep -c . "$T/log")" = 2 ] \
  && ok "clear logged once on change" || bad "clear transition"
conf "pinentry-program /home/user/.x/evil"; run2; flagged && ok "re-flagged after a change" || bad "not re-flagged"
grep -q '/usr/local/\*) P=/proc; FLAG=/usr/local/lib/prestium/safety-flag' "$S" && ok "installed copy ignores PRESTIUM_* overrides" || bad "overrides"
grep -q '^profile prestium_pinentry /usr/bin/pinentry{,-gnome3,-gtk2,-gtk-2,-curses,-x11} {' "$I/etc/apparmor.d/prestium.pinentry" && ok "pinentry profile attached" || bad "pinentry attachment"
grep -q 'timers.target.wants/prestium-gnupg-check.timer' "$I/usr/share/prestium/build/systemd-wants.txt" && ok "timer enabled" || bad "timer not enabled"
grep -q '^  @{run}/prestium-wl/\[0-9\]\*/apps rw,' "$I/etc/apparmor.d/prestium.pinentry" && grep -q 'deny @{run}/prestium-wl/broker rw,' "$I/etc/apparmor.d/prestium.pinentry" \
  && ok "pinentry: apps' Wayland socket, not the broker's" || bad "pinentry Wayland socket"
grep -qx 'pinentry-timeout 120' "$I/etc/gnupg/gpg-agent.conf" && ok "gpg-agent: prompt times out" || bad "pinentry-timeout"
exit $f
