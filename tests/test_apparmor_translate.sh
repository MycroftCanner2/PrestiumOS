#!/bin/bash
# Prestium 2.1: Prestium Translate's AppArmor profiles, checked statically and against the compiled
# profiles (tests/aa_eval.py): usr.local.bin.prestium-translate (the window and command line, child
# profile "engine" for bubblewrap) and prestium.translate-engine (the engine program, entered stacked from
# the child under no_new_privs). No network at all (no TCP/UDP, no D-Bus), nothing of the home but its
# settings file, no temporary files; the engine reads its models and the C/C++ runtime only. The allowed
# paths come from an strace of the app (Python, GTK, the settings file) and of the engine inside bubblewrap
# (libraries, /proc/cpuinfo, the gconv cache, the six model files). Also: the menu entry, the .desktop
# file, perms.txt, hook 0600 and the window's app_id. Needs apparmor_parser for the compiled part.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; A=$I/etc/apparmor.d
P=$A/usr.local.bin.prestium-translate; E=$A/prestium.translate-engine; fail=0
ok(){ echo "OK   $*"; }; no(){ echo "FAIL $*"; fail=1; }
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin:/sbin

# ------------------------------------------------------------------------------------------- static
[ -f "$P" ] && [ -f "$E" ] && ok "profile files" || { no "profile files missing"; exit 1; }
grep -qx 'profile prestium_translate /usr/local/bin/prestium-translate {' "$P" && ok "attaches to /usr/local/bin/prestium-translate" || no "attachment"
grep -qx 'profile prestium_translate_engine {' "$E" && ok "engine profile: no attachment (explicit transition only)" || no "engine profile header"
grep -v '^\s*#' "$P" "$E" | grep -E 'flags=' | grep -v 'profile engine flags=(attach_disconnected,mediate_deleted)' | grep -q . \
  && no "complain or other flags" || ok "enforced (no complain flag; the bwrap child only has attach_disconnected,mediate_deleted)"
grep -Eq '\b[uU]x\b|\bPUx\b|\bpux\b|\bCUx\b|\bcux\b' "$P" "$E" && no "unconfined exec" || ok "no unconfined exec"
parent=$(sed '/^  profile engine /,/^  }/d' "$P" | grep -v '^\s*#')
child=$(sed -n '/^  profile engine /,/^  }/p' "$P" | grep -v '^\s*#')
eng=$(grep -v '^\s*#' "$E")
[ -n "$child" ] && ok "child profile engine" || no "no child profile engine"
allow=$(grep -v '^\s*deny' <<<"$parent$child$eng")
grep -Eq '^\s*network (inet|inet6)|^\s*network\s*,|^\s*network (tcp|udp|stream|dgram)' <<<"$allow" && no "TCP/UDP allowed" || ok "no inet, inet6, tcp or udp allowed anywhere"
grep -Eq '^\s*network ' <<<"$(grep -v '^\s*deny' <<<"$parent")" && [ "$(grep -E '^\s*network ' <<<"$(grep -v '^\s*deny' <<<"$parent")")" = "  network unix stream," ] \
  && ok "parent: unix stream only (Wayland)" || no "parent: other networking"
for d in inet inet6 netlink "unix dgram" packet; do grep -qx "  deny network $d," <<<"$parent" || no "parent: no deny network $d"; done; ok "parent: inet, inet6, netlink, unix dgram, packet denied"
[ "$(grep -E '^\s*network ' <<<"$(grep -v '^\s*deny' <<<"$child")")" = "    network netlink raw," ] && ok "bwrap child: netlink raw only (lo in its empty namespace)" || no "bwrap child networking"
grep -qx '  deny network,' <<<"$eng" && ! grep -Eq '^\s*network' <<<"$eng" && ok "engine: deny network (all of it)" || no "engine networking"
for r in userns mount umount pivot_root capability ptrace; do grep -qx "  deny $r," <<<"$eng" || no "engine: no deny $r"; done; ok "engine: no userns, mount, pivot_root, capabilities or ptrace"
grep -q 'dbus' <<<"$parent$child$eng" && no "D-Bus rules" || ok "no D-Bus rules (the session bus stays denied by prestium-app-common)"
grep -q 'include <abstractions/prestium-app-common>' <<<"$parent" && grep -q 'include <abstractions/prestium-app-secrets>' <<<"$parent" \
  && ok "parent: Prestium's app base (no sudo, no secrets, restricted Wayland)" || no "parent: app base"
grep -q 'include <abstractions/prestium-no-admin>' <<<"$child" && grep -q 'include <abstractions/prestium-no-admin>' <<<"$eng" && ok "child and engine: no sudo or Prestium helpers" || no "prestium-no-admin"
grep -qx '  /usr/bin/bwrap mrCx -> engine,' <<<"$parent" && ok "parent: bwrap Cx -> engine" || no "bwrap transition"
grep -qx '    /usr/share/prestium-translate/bin/prestium-translate-engine mrix -> &prestium_translate_engine,' <<<"$child" \
  && ok "child: the engine stacked onto prestium_translate_engine" || no "engine transition"
grep -Eq '^\s*/usr/share/prestium-translate/[^ ]* +[a-z]*[wlk]' <<<"$allow" && no "write to /usr/share/prestium-translate" || ok "engine and models read-only"
grep -Eq '@\{HOME\}/\*\* +[a-z]*w|^\s*/\*\* ' <<<"$allow" && no "broad write" || ok "no broad home or root write"
grep -E '@\{HOME\}' <<<"$(grep -v '^\s*deny' <<<"$parent")" | grep -v 'prestium-translate\|@{HOME}/.config/ r,' | grep -q . && no "parent: home access beyond its settings" || ok "parent: home only for its settings folder"
grep -qF 'deny /tmp/** w,' <<<"$parent" && grep -qF 'deny /tmp/** wl,' <<<"$eng" && ok "no temporary files (parent and engine)" || no "/tmp deny"
grep -q '/usr/share/prestium-translate/models/\*\* r,' <<<"$eng" && ok "engine: models read" || no "engine: models"

H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot
[ "$(grep -c 'usr.local.bin.prestium-translate prestium.translate-engine' "$H")" -ge 3 ] && ok "hook 0600: both enforced, no-admin check, attach check" || no "hook 0600 lists"
PM=$I/usr/share/prestium/build/perms.txt
for l in "0755 root root /usr/local/bin/prestium-translate" "0644 root root /usr/local/lib/prestium-translate/core.py" \
         "0644 root root /usr/share/applications/prestium-translate.desktop" "0644 root root /etc/apparmor.d/usr.local.bin.prestium-translate" \
         "0644 root root /etc/apparmor.d/prestium.translate-engine"; do
  grep -qxF "$l" "$PM" && ok "perms.txt: ${l##* }" || no "perms.txt lacks $l"
done
D=$I/usr/share/applications/prestium-translate.desktop
for l in "Name=Prestium Translate" "Exec=/usr/local/lib/prestium/app-confine prestium-translate" "Icon=accessories-dictionary" "Terminal=false" "StartupWMClass=org.prestium.Translate"; do
  grep -qxF "$l" "$D" && ok "desktop: $l" || no "desktop lacks $l"
done
# security review F-01/F-05: started in its own mount namespace (no session bus, no broker socket, private /tmp)
grep -q "^    \"prestium-translate\":" "$I/usr/local/lib/prestium/app-confine" && ok "app-confine table lists prestium-translate" || no "app-confine table lacks prestium-translate"
grep -q '^Categories=.*Utility;Office;' "$D" && ok "desktop: Accessories and Office" || no "desktop categories"
B=$I/usr/local/bin/prestium-translate
grep -q 'APP_ID = "org.prestium.Translate"' "$B" && ok "window app_id matches StartupWMClass" || no "app_id"
M=$I/etc/xdg/labwc/menu.xml
grep -A1 '<item label="Prestium Translate" icon="accessories-dictionary">' "$M" | grep -qF 'command="prestium-run /usr/local/bin/prestium-translate"' \
  && ok "menu: Accessories > Prestium Translate through prestium-run" || no "menu entry"
grep -q '^#!/usr/bin/python3 -I$' "$B" && ok "isolated Python" || no "shebang"
grep -q 'XDG_CONFIG_HOME"\] = "/usr/share/prestium/broker-style"' "$B" && ok "Prestium's GTK style, root-owned" || no "style"
grep -Eq 'import (socket|urllib|http)|from (socket|urllib|http)|requests|RecentManager|tempfile' "$I/usr/local/lib/prestium-translate/core.py" "$B" \
  && no "network, history or temp-file code" || ok "no network, history or temp-file code"
grep -q -- '--unshare-all' "$I/usr/local/lib/prestium-translate/core.py" && ! grep -q -- '--share-net' "$I/usr/local/lib/prestium-translate/core.py" \
  && ok "engine: bubblewrap with every namespace unshared (no network)" || no "bwrap flags"

# ------------------------------------------------------------------------------------ compiled
if ! command -v apparmor_parser >/dev/null; then echo "SKIP apparmor_parser missing (compiled checks)"; exit $fail; fi
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$A"/. "$W"/
for f in usr.local.bin.prestium-translate prestium.translate-engine; do
  apparmor_parser -QK -b "$W" "$W/$f" >/dev/null 2>&1 && ok "$f compiles" || no "$f compiles"
done
{ apparmor_parser -p -b "$W" "$W/usr.local.bin.prestium-translate"; apparmor_parser -p -b "$W" "$W/prestium.translate-engine"; } > "$W/.exp" 2>/dev/null || { no "profiles do not expand"; exit 1; }
H=/home/user; S=/usr/share/prestium-translate; L=/usr/lib/x86_64-linux-gnu
M=prestium_translate; C=prestium_translate//engine; G=prestium_translate_engine
python3 -B "$R/tests/aa_eval.py" "$W/.exp" <<EOT || fail=1
# the app: Python, its library, the engine's files read, bwrap in the child
allow $M /usr/bin/python3.13 x:i
allow $M /usr/local/lib/prestium-translate/core.py r
allow $M $S/bin/prestium-translate-engine r
allow $M $S/models/enru/model.enru.intgemm.alphas.bin r
deny $M $S/models/enru/model.enru.intgemm.alphas.bin w
allow $M /usr/bin/bwrap x:C
deny $M $S/bin/prestium-translate-engine x
deny $M /usr/bin/sudo x
deny $M /usr/bin/curl x
deny $M /usr/local/sbin/prestium-tor-mode x
# its settings, nothing else of the home, no temporary files
allow $M $H/.config/prestium-translate/settings.json rw
allow $M $H/.config/prestium-translate/settings.json.new rw
deny $M $H/.config/prestium-translate/history.txt w
deny $M $H/Documents/notes.txt r
deny $M $H/Documents/notes.txt w
deny $M $H/Downloads/f.txt r
deny $M "$H/Tor Browser/f.txt" r
deny $M $H/notes.txt w
deny $M $H/.gnupg/pubring.kbx r
deny $M $H/.local/share/recently-used.xbel w
deny $M $H/.bashrc w
deny $M /tmp/prestium-translate.txt w
deny $M /var/tmp/x w
deny $M /media/user/STICK/f.txt r
# bubblewrap
allow $C /usr/bin/bwrap r
allow $C $L/libc.so.6 m
allow $C $S/models/ruen/vocab.ruen.spm r
allow $C /newroot/usr/share/prestium-translate/ w
allow $C /proc/1234/uid_map w
allow $C $S/bin/prestium-translate-engine x:&prestium_translate_engine
deny $C $H/.bashrc r
deny $C $H/Documents/notes.txt r
deny $C /run/user/1000/wayland-0 r
deny $C /usr/bin/python3.13 x
deny $C /usr/bin/sh x
deny $C $S/models/ruen/vocab.ruen.spm w
# the engine (strace inside bubblewrap)
allow $G $S/bin/prestium-translate-engine m
allow $G $L/libstdc++.so.6 m
allow $G $L/libm.so.6 m
allow $G $L/libgcc_s.so.1 m
allow $G $L/libc.so.6 m
allow $G $L/gconv/gconv-modules.cache r
allow $G /proc/cpuinfo r
allow $G /proc/sys/vm/overcommit_memory r
allow $G /sys/devices/system/cpu/online r
allow $G $S/models/enru/model.enru.intgemm.alphas.bin r
allow $G $S/models/enru/lex.50.50.enru.s2t.bin r
allow $G $S/models/enru/vocab.enru.spm r
allow $G $S/models/ruen/model.ruen.intgemm.alphas.bin r
deny $G $S/models/ruen/model.ruen.intgemm.alphas.bin w
deny $G $S/bin/prestium-translate-engine w
deny $G /tmp/x w
deny $G $H/.bashrc r
deny $G $H/Documents/notes.txt r
deny $G /run/user/1000/wayland-0 r
deny $G /etc/shadow r
deny $G /usr/bin/sh x
deny $G /usr/bin/bwrap x
deny $G /usr/bin/python3.13 x
EOT
# no network rule at all survives in the compiled engine profile, and the parent's only allow is unix stream
awk '/^profile prestium_translate_engine /,/^}/' "$W/.exp" | grep -E '^\s*network' | grep -v '^\s*deny' | grep -q . && no "compiled engine profile allows networking" || ok "compiled engine profile: no network allow"
exit $fail
