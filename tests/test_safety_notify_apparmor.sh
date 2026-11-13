#!/bin/bash
# Prestium 2.1: prestium-safety-notify alerts when AppArmor is not active. Runs the real notifier one
# pass with stubs on PATH (systemctl, notify-send, zenity, sleep) and fake sysfs files.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
N=$R/config/includes.chroot/usr/local/bin/prestium-safety-notify
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
grep -q '/sys/module/apparmor/parameters/enabled' "$N" && grep -q 'is-active apparmor.service' "$N" \
  && grep -q 'alert unit:apparmor' "$N" && ok "notifier checks the AppArmor module and apparmor.service" || bad "AppArmor checks missing"
grep -q '^sleep 15$' "$N" && grep -q '  sleep 20$' "$N" && ok "15 s start delay and 20 s loop kept" || bad "timing changed"
mkdir -p "$T/bin"
# systemctl stub: every unit active, except apparmor.service which takes its state from $AASTATE
cat > "$T/bin/systemctl" <<'S'
#!/bin/sh
u=; for a in "$@"; do case "$a" in *.service) u=$a;; esac; done
case "$1 $2" in
  "-q is-active") [ "$u" = apparmor.service ] && { [ "$AASTATE" = active ]; exit; }; exit 0;;
  "-q is-failed") exit 1;;
  "show -p") [ "$u" = apparmor.service ] && echo "$AASTATE" || echo active;;
esac
S
printf '#!/bin/sh\necho "$@" >> "$ALERTS"\n' > "$T/bin/notify-send"
printf '#!/bin/sh\nexit 0\n' > "$T/bin/zenity"
# sleep stub: the 15 s start delay returns at once; the 20 s loop sleep ends the run after one pass
printf '#!/bin/sh\n[ "$1" = 20 ] && kill -TERM $PPID\nexit 0\n' > "$T/bin/sleep"
chmod +x "$T/bin/"*
run(){ # enabled-flag aastate [profiles-file]
  printf '%s\n' "$1" > "$T/enabled"; rm -f "$T/alerts"
  env -i PATH="$T/bin:/usr/bin:/bin" HOME="$T" ALERTS="$T/alerts" AASTATE="$2" PRESTIUM_AA_ENABLED="$T/enabled" PRESTIUM_CMDLINE_CHECK=true \
    PRESTIUM_AA_PROFILES="${3:-$T/no-profiles}" timeout 10 bash "$N" >/dev/null 2>&1
  cat "$T/alerts" 2>/dev/null; }
o=$(run Y active); [ -z "$o" ] && ok "module enabled, service active: no alert" || bad "false alert: $o"
o=$(run Y inactive); case "$o" in *"AppArmor is not active (apparmor.service: inactive)"*) ok "service stopped: alert";; *) bad "no alert when stopped: $o";; esac
o=$(run Y failed); case "$o" in *"AppArmor is not active"*) ok "service failed: alert";; *) bad "no alert when failed: $o";; esac
o=$(run Y activating); [ -z "$o" ] && ok "service activating: no alert yet" || bad "boot-time false alert: $o"
o=$(run N active); case "$o" in *"AppArmor is not active (kernel module N)"*) ok "module disabled: alert";; *) bad "no alert when module off: $o";; esac
rm -f "$T/enabled"; o=$(env -i PATH="$T/bin:/usr/bin:/bin" HOME="$T" ALERTS="$T/alerts" AASTATE=active PRESTIUM_AA_ENABLED="$T/missing" PRESTIUM_CMDLINE_CHECK=true \
  timeout 10 bash "$N" >/dev/null 2>&1; cat "$T/alerts" 2>/dev/null)
case "$o" in *"kernel module not loaded"*) ok "no apparmor module: alert";; *) bad "no alert without module: $o";; esac
P=$T/profiles
for p in torbrowser_firefox librewolf prestium-localfox claws-mail gajim pidgin onionshare feather libreoffice thelounge thelounge-tor loupe ristretto vlc file-roller xarchiver featherpad mat2 metadata-cleaner gimp audacity keepassxc kleopatra; do echo "$p (enforce)"; done > "$P"
o=$(run Y active "$P"); [ -z "$o" ] && ok "all Prestium profiles enforced: no alert" || bad "false profile alert: $o"
sed -i 's/^gajim (enforce)$/gajim (complain)/; /^feather /d' "$P"
o=$(run Y active "$P"); case "$o" in *'"gajim" is not loaded in enforce mode'*'"feather"'*|*'"feather"'*'"gajim" is not loaded'*) ok "complain/missing profile: alert";; *) bad "no profile alert: $o";; esac
# securityfs shows the list as 0444 but only root may open it: [ -r ] passes, the read fails.
# A file that tests readable but cannot be read must give no profile alerts.
grep -q '\[ -r "\$AA_PROFILES" \]' "$N" && bad "notifier still trusts [ -r ] on the profiles list" || ok "notifier does not rely on [ -r ]"
U=$T/unreadable; mkdir -p "$U"   # a directory: [ -r ] is true, cat fails like an EACCES open
[ -r "$U" ] && ! cat "$U" >/dev/null 2>&1 && ok "fixture: readable by [ -r ], read fails" || bad "fixture"
o=$(run Y active "$U"); [ -z "$o" ] && ok "unreadable profiles list: no alerts" || bad "false alerts from unreadable list: $o"
if [ "$(id -u)" != 0 ]; then
  cp "$P" "$T/noperm"; chmod 000 "$T/noperm"
  o=$(run Y active "$T/noperm"); [ -z "$o" ] && ok "permission-denied profiles list: no alerts" || bad "false alerts on EACCES: $o"
fi
: > "$T/empty"; o=$(run Y active "$T/empty"); [ -z "$o" ] && ok "empty profiles list: no alerts" || bad "false alerts from empty list: $o"
[ $fail = 0 ] && echo "safety notify apparmor: OK"; exit $fail
