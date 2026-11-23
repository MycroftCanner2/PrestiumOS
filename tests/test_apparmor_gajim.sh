#!/bin/bash
# Prestium 2.1 (late): Gajim's OpenPGP plugin (gajim-openpgp, python3-gpg/GPGME) needs to run gpg.
# Without an exec rule GPGME's engine check ("gpg --version") failed and Gajim stopped at account
# connect with "GPGMEError: GPGME: Invalid crypto engine". GnuPG runs in the child profile gajim//gpg,
# as in Claws Mail's profile: only Gajim's own keyrings (~/.local/share/gajim/openpgp/<jid>/), never
# ~/.gnupg; no network but unix sockets; no write or hard link on GnuPG's *.conf; pinentry Px.
# With python3-gpg installed, also checks that GPGME's engine check passes with gpg runnable and fails
# with exactly this error when it is not (the denied exec, reproduced with bubblewrap).
set -u; T=$(cd "$(dirname "$0")/.." && pwd); A=$T/config/includes.chroot/etc/apparmor.d
P=$A/usr.bin.gajim; fail=0
ok(){ echo "OK $1"; }; no(){ echo "FAIL $1"; fail=1; }
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin:/sbin
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$A"/. "$W"/
if command -v apparmor_parser >/dev/null; then
  apparmor_parser -QK -b "$W" "$W/usr.bin.gajim" 2>/dev/null && ok "profile compiles" || no "profile compiles"
else echo "SKIP apparmor_parser missing (compile)"; fi
L=$T/config/package-lists/prestium.list.chroot
grep -qx 'gajim-openpgp' "$L" && grep -qx 'gpg' "$L" && grep -qx 'gpgconf' "$L" && grep -qx 'gpg-agent' "$L" \
  && ok "gajim-openpgp and the GnuPG engine are in the image" || no "package list: gajim-openpgp/gpg/gpgconf/gpg-agent"
grep -q 'flags=' "$P" && no "has flags (complain?)" || ok "no complain flag"
grep -Eq '\bUx,' "$P" && no "Ux in the profile" || ok "no Ux"

parent=$(sed '/^  profile gpg {/,/^  }/d' "$P" | grep -v '^\s*#')
child=$(sed -n '/^  profile gpg {/,/^  }/p' "$P" | grep -v '^\s*#')
[ -n "$child" ] && ok "child profile gpg" || no "no child profile gpg"
for b in gpg gpgsm gpgconf gpg-connect-agent gpg-agent; do
  grep -qx "  /usr/bin/$b Cx -> gpg," <<<"$parent" && ok "parent: $b Cx -> gpg" || no "parent: $b not Cx -> gpg"
done
grep -Eq '/usr/bin/gpg[^ ]* +[a-z]*[iuUpP]x' <<<"$parent" && no "parent runs GnuPG outside the child" || ok "GnuPG only in the child"
grep -q '\.gnupg' <<<"$(grep -v '^\s*deny' <<<"$parent")" && no "parent grants ~/.gnupg" || ok "parent has no ~/.gnupg rule"
grep -qF '  deny @{HOME}/.local/share/gajim/openpgp/*/*.conf{,.*} wl,' <<<"$parent" && grep -qF '  deny @{HOME}/.local/share/gajim/openpgp/*/common.conf wl,' <<<"$parent" \
  && ok "parent: no write or link on the keyrings' *.conf" || no "parent may write the keyrings' *.conf"
grep -qF '    deny @{HOME}/.local/share/gajim/openpgp/*/*.conf{,.*} wl,' <<<"$child" && grep -qF '    deny @{HOME}/.local/share/gajim/openpgp/*/common.conf wl,' <<<"$child" \
  && ok "child: no write or link on *.conf (as Claws Mail and Kleopatra)" || no "child may write *.conf"
grep -qF '    owner @{HOME}/.local/share/gajim/openpgp/*/** rwkl,' <<<"$child" && ok "child: Gajim's keyrings" || no "child lost the keyrings"
grep -qF '    deny @{HOME}/.gnupg/** rw,' <<<"$child" && ! grep -v '^\s*deny' <<<"$child" | grep -q '\.gnupg' && ok "child: never ~/.gnupg" || no "child and ~/.gnupg"
grep -Eq '^\s*network (inet|inet6)' <<<"$child" && no "child allows TCP/UDP" || ok "child: no inet allow"
grep -Eq '^\s*network\s*,|^\s*network (raw|packet|netlink|dgram|stream)' <<<"$child" && no "child allows other networking" || ok "child: unix stream only"
grep -q 'dirmngr' <<<"$child$parent" && no "dirmngr allowed" || ok "no dirmngr (gajim-openpgp runs gpg offline)"
grep -q 'include <abstractions/prestium-no-admin>' <<<"$child" && ok "child: no sudo or Prestium helpers" || no "child: no prestium-no-admin"
grep -qx '    /usr/bin/pinentry\* Px -> prestium_pinentry,' <<<"$child" && ok "pinentry: Px into prestium_pinentry" || no "pinentry not Px"
grep -Eq '@\{HOME\}/\*\*|^\s*/\*\* ' <<<"$child" && no "child: broad access" || ok "child: no broad home or root access"

# security review F-02: the compiled child profile reaches its own agent (gnupg/d.<hash>/) only,
# never the ~/.gnupg agent's sockets directly in gnupg/ (Kleopatra's and Claws Mail's keys)
if command -v apparmor_parser >/dev/null; then
  AW=$(mktemp -d); cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$AW"/ 2>/dev/null; cp -r "$A"/. "$AW"/
  if apparmor_parser -p -b "$AW" "$AW/usr.bin.gajim" > "$AW/.exp" 2>/dev/null; then
    GD=/run/user/1000/gnupg
    python3 -B "$T/tests/aa_eval.py" "$AW/.exp" <<EOT && ok "F-02: gpg reaches only its own agent" || no "F-02: gpg agent sockets"
allow gajim//gpg $GD/ w
allow gajim//gpg $GD/d.64c8yunxnuqikwbosfpqkxcb/ w
allow gajim//gpg $GD/d.64c8yunxnuqikwbosfpqkxcb/S.gpg-agent rw
allow gajim//gpg $GD/d.64c8yunxnuqikwbosfpqkxcb/S.keyboxd rw
deny gajim//gpg $GD/S.gpg-agent rw
deny gajim//gpg $GD/S.gpg-agent.extra rw
deny gajim//gpg $GD/S.gpg-agent.ssh rw
deny gajim//gpg $GD/S.keyboxd rw
deny gajim//gpg $GD/S.dirmngr rw
EOT
  else no "usr.bin.gajim does not expand"; fi
  rm -rf "$AW"
else echo "SKIP apparmor_parser missing (F-02 compiled check)"; fi

# GPGME's engine check, with gpg runnable and with its exec denied (needs python3-gpg and bwrap)
if python3 -c 'import gpg' 2>/dev/null && command -v bwrap >/dev/null && command -v gpg >/dev/null \
   && bwrap --dev-bind / / true 2>/dev/null; then
  mkdir -m 700 "$W/home"; : > "$W/noexec"
  probe='import gpg,sys
try: gpg.Context(armor=False, offline=True, home_dir=sys.argv[1]); print("engine ok")
except gpg.errors.GPGMEError as e: print(e)'
  r=$(python3 -c "$probe" "$W/home" 2>&1); [ "$r" = "engine ok" ] && ok "GPGME engine check passes" || no "GPGME engine check: $r"
  r=$(bwrap --dev-bind / / --ro-bind "$W/noexec" /usr/bin/gpg python3 -c "$probe" "$W/home" 2>&1)
  [ "$r" = "GPGME: Invalid crypto engine" ] && ok "gpg not runnable: the reported error" || no "gpg not runnable gave: $r"
else echo "SKIP GPGME engine check (needs python3-gpg, gpg and bwrap)"; fi
exit $fail
