#!/bin/bash
# Prestium 2.1 (late): Gajim OpenPGP Keys (prestium-gajim-keys) and its AppArmor profile
# usr.local.bin.prestium-gajim-keys, checked statically and against the compiled profile (tests/aa_eval.py).
# The allowed paths come from an strace of the library's flows as the live user (list accounts, list
# Kleopatra's keys, import one and add the xmpp: user ID, check, generate, back up, restore, delete),
# split by program: the Python app itself, and gpg, gpg-agent and keyboxd in the child profile "gpg".
# gpg never opened anything in ~/.gnupg (it reads a copy in /tmp/prestium-keys-*); the app only read
# pubring.kbx and private-keys-v1.d/<keygrip>.key there. Also: the menu entry, the .desktop file,
# perms.txt and hook 0600. Needs apparmor_parser for the compiled part (PATH may need /usr/sbin).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; A=$I/etc/apparmor.d
P=$A/usr.local.bin.prestium-gajim-keys; fail=0
ok(){ echo "OK   $*"; }; no(){ echo "FAIL $*"; fail=1; }
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin:/sbin

# ------------------------------------------------------------------------------------------- static
[ -f "$P" ] && ok "profile file" || { no "no profile file"; exit 1; }
grep -qx 'profile prestium_gajim_keys /usr/local/bin/prestium-gajim-keys {' "$P" && ok "attaches to /usr/local/bin/prestium-gajim-keys" || no "attachment"
grep -q 'flags=' "$P" && no "has flags (complain?)" || ok "no complain flag"
grep -Eq '\b[uU]x\b|\bPUx\b|\bpux\b|\bCUx\b|\bcux\b' "$P" && no "unconfined exec in the profile" || ok "no unconfined exec"
parent=$(sed '/^  profile gpg {/,/^  }/d' "$P" | grep -v '^\s*#')
child=$(sed -n '/^  profile gpg {/,/^  }/p' "$P" | grep -v '^\s*#')
[ -n "$child" ] && ok "child profile gpg" || no "no child profile gpg"
for b in gpg gpgconf gpg-agent gpg-connect-agent; do
  grep -qx "  /usr/bin/$b Cx -> gpg," <<<"$parent" && ok "parent: $b Cx -> gpg" || no "parent: $b not Cx -> gpg"
done
grep -Eq '^\s*network (inet|inet6)' <<<"$(grep -v '^\s*deny' <<<"$parent$child")" && no "TCP/UDP allowed" || ok "no inet/inet6 allow"
grep -qx '  deny network inet,' <<<"$parent" && grep -qx '  deny network inet6,' <<<"$parent" && ok "parent: inet and inet6 denied" || no "parent: no inet deny"
grep -Eq '^\s*network\s*,|^\s*network (raw|packet|dgram|netlink [a-z]+)' <<<"$parent$child" && no "other networking allowed" || ok "unix stream only"
grep -q 'dbus' <<<"$parent$child" && no "D-Bus rules" || ok "no D-Bus rules (the session bus stays denied by prestium-app-common)"
grep -q 'dirmngr' <<<"$parent$child" && no "dirmngr allowed" || ok "no dirmngr"
grep -q 'include <abstractions/prestium-app-common>' <<<"$parent" && grep -q 'include <abstractions/prestium-app-secrets>' <<<"$parent" \
  && ok "parent: Prestium's app base (no sudo, no secrets, restricted Wayland)" || no "parent: app base"
grep -q 'include <abstractions/prestium-no-admin>' <<<"$child" && ok "child: no sudo or Prestium helpers" || no "child: prestium-no-admin"
grep -qx '    /usr/bin/pinentry\* Px -> prestium_pinentry,' <<<"$child" && ok "pinentry: Px into prestium_pinentry" || no "pinentry not Px"
# ~/.gnupg: read-only for the app, nothing at all for gpg
grep -Eq '\.gnupg[^ ]* +[a-z]*[wlk]' <<<"$(grep -v '^\s*deny' <<<"$parent$child")" && no "a write, link or lock in ~/.gnupg is allowed" || ok "no write, link or lock in ~/.gnupg"
grep -qF '  deny @{HOME}/.gnupg/** wl,' <<<"$parent" && ok "parent: deny write and link in ~/.gnupg" || no "parent: ~/.gnupg deny"
grep -qF '    deny @{HOME}/.gnupg/** rwlk,' <<<"$child" && ! grep -v '^\s*deny' <<<"$child" | grep -q '\.gnupg' && ok "child: never ~/.gnupg" || no "child and ~/.gnupg"
for x in parent child; do
  t=${!x}; sp=$([ $x = child ] && echo "    " || echo "  ")
  grep -qF "${sp}deny @{HOME}/.local/share/gajim/openpgp/*/*.conf{,.*} wl," <<<"$t" && grep -qF "${sp}deny @{HOME}/.local/share/gajim/openpgp/*/common.conf wl," <<<"$t" \
    && ok "$x: no write or link on the keyrings' *.conf" || no "$x may write the keyrings' *.conf"
done
grep -Eq '@\{HOME\}/\*\* +[a-z]*w|^\s*/\*\* ' <<<"$parent$child" && no "broad write" || ok "no broad home or root write"
# Gajim's own profile is not loosened by this tool: still no ~/.gnupg for Gajim or its gpg
G=$A/usr.bin.gajim
grep -q 'prestium-gajim-keys\|prestium_gajim_keys' "$G" && no "Gajim's profile names this tool" || ok "Gajim's profile does not name this tool"
grep -qF '    deny @{HOME}/.gnupg/** rw,' "$G" && ok "Gajim's gpg still denied ~/.gnupg" || no "Gajim's gpg and ~/.gnupg"

H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot
[ "$(grep -c 'usr.local.bin.prestium-gajim-keys' "$H")" -ge 3 ] && ok "hook 0600: enforced, no-admin check, attach check" || no "hook 0600 lists"
PM=$I/usr/share/prestium/build/perms.txt
for l in "0755 root root /usr/local/bin/prestium-gajim-keys" "0644 root root /usr/local/lib/prestium-keys/gajim_keys.py" \
         "0644 root root /usr/share/applications/prestium-gajim-keys.desktop" "0644 root root /etc/apparmor.d/usr.local.bin.prestium-gajim-keys"; do
  grep -qxF "$l" "$PM" && ok "perms.txt: ${l##* }" || no "perms.txt lacks $l"
done
D=$I/usr/share/applications/prestium-gajim-keys.desktop
for l in "Name=Gajim OpenPGP Keys" "Exec=/usr/local/bin/prestium-gajim-keys" "Icon=dialog-password" "Terminal=false" "StartupWMClass=org.prestium.GajimKeys"; do
  grep -qxF "$l" "$D" && ok "desktop: $l" || no "desktop lacks $l"
done
grep -q 'APP_ID = "org.prestium.GajimKeys"' "$I/usr/local/bin/prestium-gajim-keys" && ok "window app_id matches StartupWMClass" || no "app_id"
M=$I/etc/xdg/labwc/menu.xml
grep -A1 '<item label="Gajim OpenPGP Keys" icon="dialog-password">' "$M" | grep -qF 'command="prestium-run /usr/local/bin/prestium-gajim-keys"' \
  && ok "menu: Communication > Gajim OpenPGP Keys through prestium-run" || no "menu entry"
grep -q '^#!/usr/bin/python3 -I$' "$I/usr/local/bin/prestium-gajim-keys" && ok "isolated Python" || no "shebang"
grep -q 'XDG_CONFIG_HOME"\] = "/usr/share/prestium/broker-style"' "$I/usr/local/bin/prestium-gajim-keys" && ok "Prestium's GTK style, root-owned" || no "style"
grep -Eq 'socket|urllib|http\.client|requests' "$I/usr/local/lib/prestium-keys/gajim_keys.py" "$I/usr/local/bin/prestium-gajim-keys" \
  && no "network code in the tool" || ok "no network code"
grep -Eq '"--(keyserver|recv-keys|send-keys|search-keys|refresh-keys|locate-keys)"' "$I/usr/local/lib/prestium-keys/gajim_keys.py" \
  && no "keyserver use" || ok "no keyserver use"
grep -Eq 'set_visibility\(False\)|getpass|"--passphrase"' "$I/usr/local/bin/prestium-gajim-keys" && no "the window asks for a passphrase" || ok "no passphrase entry in the window (pinentry only)"
grep -n '"--passphrase"' "$I/usr/local/lib/prestium-keys/gajim_keys.py" | grep -vq '"--passphrase", ""\]' && no "the library passes a passphrase other than the empty one" || ok "the library passes only an empty passphrase (a key without one, as Gajim's)"

# ------------------------------------------------------------------------------------ compiled
if ! command -v apparmor_parser >/dev/null; then echo "SKIP apparmor_parser missing (compiled checks)"; exit $fail; fi
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$A"/. "$W"/
apparmor_parser -QK -b "$W" "$W/usr.local.bin.prestium-gajim-keys" >/dev/null 2>&1 && ok "profile compiles" || no "profile compiles"
apparmor_parser -p -b "$W" "$W/usr.local.bin.prestium-gajim-keys" > "$W/.exp" 2>/dev/null || { no "profile does not expand"; exit 1; }
H=/home/user; G=$H/.gnupg; O=$H/.local/share/gajim/openpgp; K=$O/alice@example.org; T=/tmp/prestium-keys-k3j_8x2a
D=/run/user/1000/gnupg/d.64c8yunxnuqikwbosfpqkxcb; GR=0123456789ABCDEF0123456789ABCDEF01234567
M=prestium_gajim_keys; C=prestium_gajim_keys//gpg
python3 -B "$R/tests/aa_eval.py" "$W/.exp" <<EOT || fail=1
# the app: Python, its library, GnuPG in the child
allow $M /usr/bin/python3.13 x:i
allow $M /usr/local/lib/prestium-keys/gajim_keys.py r
allow $M /usr/bin/gpg x:C
allow $M /usr/bin/gpgconf x:C
deny $M /usr/bin/dirmngr x
deny $M /usr/bin/sudo x
deny $M /usr/local/sbin/prestium-tor-mode x
deny $M /usr/local/lib/prestium/file-picker x
# accounts and "is Gajim running?"
allow $M $H/.config/gajim/settings.sqlite r
deny $M $H/.config/gajim/settings.sqlite w
deny $M $H/.config/gajim/settings.sqlite-journal w
allow $M /proc/4242/cmdline r
# Gajim's keyrings (strace)
allow $M $H/.local/ w
allow $M $H/.local/share/gajim/ w
allow $M $O/ w
allow $M $K/ w
allow $M $K/private-keys-v1.d/ w
allow $M $K/private-keys-v1.d/$GR.key rw
deny $M $K/gpg.conf w
deny $M $K/gpg-agent.conf l
deny $M $K/common.conf w
deny $M $K/contacts.db r
deny $M $H/.local/share/gajim/logs.db r
deny $M $H/.local/share/gajim/cache.db r
# Kleopatra's keyring: read the public keyring and secret key files, nothing else, never write
allow $M $G/ r
allow $M $G/pubring.kbx r
allow $M $G/common.conf r
allow $M $G/public-keys.d/pubring.db r
allow $M $G/private-keys-v1.d/ r
allow $M $G/private-keys-v1.d/$GR.key r
deny $M $G/pubring.kbx w
deny $M $G/pubring.kbx.lock w
deny $M $G/private-keys-v1.d/$GR.key w
deny $M $G/gpg.conf w
deny $M $G/trustdb.gpg w
deny $M $G/sshcontrol r
deny $M $G/openpgp-revocs.d/$GR.rev r
# the temporary copy, backups and restores
allow $M $T/ w
allow $M $T/pubring.kbx w
allow $M $T/common.conf w
allow $M $T/public-keys.d/pubring.db w
allow $M $H/Documents/alice@example.org.gajim-key.asc w
allow $M $H/Documents/keys/alice@example.org.gajim-key.asc w
allow $M "/media/user/USB STICK/alice@example.org.gajim-key.asc" w
deny $M $H/Documents/notes.txt w
deny $M $H/Downloads/alice@example.org.gajim-key.asc w
deny $M $H/.bashrc w
deny $M $H/alice@example.org.gajim-key.asc w
allow $M $H/Downloads/backup.gajim-key.asc r
allow $M "/media/user/USB STICK/alice@example.org.gajim-key.asc" r
deny $M $H/.ssh/id_ed25519 r
deny $M $H/.local/share/keyrings/login.keyring r
deny $M /run/user/1000/bus rw
deny $M /run/user/1000/wayland-0 rw
allow $M /run/prestium-wl/1000/apps rw
# gpg, gpg-agent and keyboxd (strace)
allow $C /usr/bin/gpg-agent x:i
allow $C /usr/lib/gnupg/keyboxd x:i
allow $C /usr/bin/pinentry-gnome3 x:P
deny $C /usr/bin/dirmngr x
deny $C /usr/bin/sudo x
deny $C /usr/bin/python3.13 x
allow $C $K/ rw
allow $C $K/pubring.kbx rw
allow $C $K/pubring.kbx~ w
allow $C $K/pubring.kbx.tmp w
allow $C $K/pubring.kbx.lock rwl
allow $C $K/.#lk0x00005581e2c4f6b0.prestium.4242 wl
allow $C $K/.#lk0x00005581e2c4f6b0.prestium.4242x wl
allow $C $K/gnupg_spawn_agent_sentinel.lock wl
allow $C $K/trustdb.gpg rw
allow $C $K/trustdb.gpg.lock rwl
allow $C $K/tofu.db rw
allow $C $K/tofu.db-journal rw
allow $C $K/random_seed w
allow $C $K/private-keys-v1.d/$GR.key rw
allow $C $K/openpgp-revocs.d/ w
allow $C $K/openpgp-revocs.d/$GR.rev w
allow $C $K/gpg.conf r
deny $C $K/gpg.conf w
deny $C $K/gpg-agent.conf w
deny $C $K/gpg-agent.conf l
deny $C $K/common.conf w
deny $C $K/contacts.db r
allow $C $T/pubring.kbx r
allow $C $T/pubring.kbx.lock rwl
allow $C $T/.#lk0x00005581e2c4f6b0.prestium.4242 wl
allow $C $T/public-keys.d/pubring.db rwk
allow $C $D/ w
allow $C $D/S.gpg-agent rw
allow $C $D/S.keyboxd rw
deny $C $G/ r
deny $C $G/pubring.kbx r
deny $C $G/pubring.kbx.lock w
deny $C $G/private-keys-v1.d/$GR.key r
deny $C $G/gnupg_spawn_agent_sentinel.lock w
deny $C $H/.config/gajim/settings.sqlite r
deny $C $H/.local/share/gajim/logs.db r
deny $C $H/Documents/alice@example.org.gajim-key.asc w
deny $C $H/Downloads/x r
deny $C /media/user/USB/x r
EOT
exit $fail
