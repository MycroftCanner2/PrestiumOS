#!/bin/bash
# Prestium 2.1: Claws Mail key generation. Claws reads an empty "name=" in accountrc as an empty full
# name and its "Generate a new key pair" passes that to gpg as an empty Name-Real, which gpg rejects
# ("Couldn't generate a new key pair: General error"). The shipped account has no name line, the
# launcher drops an empty one (Claws writes it back on save) before each start, and every way into
# Claws goes through the launcher. Unprivileged; needs gpg for the key-generation part.
set -u; T=$(cd "$(dirname "$0")/.." && pwd); C=$T/config/includes.chroot; fail=0
ok(){ echo "OK $1"; }; no(){ echo "FAIL $1"; fail=1; }
L=$C/usr/local/bin/claws-mail-i2p
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

# shipped account files
# no preset account: Claws' first-run wizard asks for name, address and password (an empty name is refused there)
for d in "$C/etc/skel/.claws-mail" "$C/home/user/.claws-mail"; do
  [ ! -e "$d/accountrc" ] && ok "no preset account in ${d#$C}" || no "preset accountrc still in ${d#$C}"
  m=$d/accountrc.tmpl
  grep -qx 'smtpserver=127.0.0.1:7659' "$m" && grep -qx 'recvserver=127.0.0.1:7660' "$m" && grep -qx 'recvtype=0' "$m" \
    && ok "wizard defaults: POP3 127.0.0.1:7660, SMTP 127.0.0.1:7659 in ${d#$C}" || no "wizard servers in ${d#$C}"
  grep -qx 'smtpauth=1' "$m" && grep -qx 'smtpssl=0' "$m" && grep -qx 'recvssl=0' "$m" && ok "SMTP auth on, no TLS in ${d#$C}" || no "auth/ssl in ${d#$C}"
  grep -Eq '^(smtpport|popport)=' "$m" && no "port keys Claws ignores in ${d#$C}" || ok "ports given as server:port in ${d#$C}"
  grep -Eqx 'name=|recvuser=|recvpass=|smtppass=' "$m" && ! grep -Eq '^(recvpass|smtppass|name)=.' "$m" && ok "name and password left for the user in ${d#$C}" || no "prefilled name/password in ${d#$C}"
done
cmp -s "$C/etc/skel/.claws-mail/accountrc.tmpl" "$C/home/user/.claws-mail/accountrc.tmpl" && ok "skel and live user template match" || no "templates differ"
! grep -q '/.claws-mail/accountrc$' "$C/usr/share/prestium/build/perms.txt" && ok "perms.txt has no preset accountrc" || no "perms.txt still lists accountrc"
# every way in uses the launcher
grep -q 'command="prestium-run claws-mail-i2p"' "$C/etc/xdg/labwc/menu.xml" && ok "menu uses launcher" || no "menu uses launcher"
D=$C/usr/local/share/applications/claws-mail.desktop
[ -f "$D" ] && ! grep -E '^Exec=' "$D" | grep -vq '^Exec=claws-mail-i2p' && ok "desktop file: every Exec uses launcher" || no "desktop file Exec"
grep -q 'MimeType=.*x-scheme-handler/mailto' "$D" && ok "desktop file keeps mailto" || no "desktop file mailto"
grep -qx '0755 root root /usr/local/bin/claws-mail-i2p' "$C/usr/share/prestium/build/perms.txt" && ok "perms launcher" || no "perms launcher"
grep -qx '0644 root root /usr/local/share/applications/claws-mail.desktop' "$C/usr/share/prestium/build/perms.txt" && ok "perms desktop" || no "perms desktop"
grep -qx 'exec /usr/bin/claws-mail "\$@"' "$L" && ok "launcher execs the confined binary" || no "launcher exec"

# launcher behaviour, with /usr/bin/claws-mail replaced by a stub that records its argv
mkdir -p "$W/bin"; printf '#!/bin/sh\nfor a; do printf "%%s\\n" "$a"; done > "$HOME/argv"\n' > "$W/bin/claws"; chmod 755 "$W/bin/claws"
sed "s#^exec /usr/bin/claws-mail #exec $W/bin/claws #" "$L" > "$W/launcher"; chmod 755 "$W/launcher"
mk(){ rm -rf "$W/h"; mkdir -p "$W/h/.claws-mail"; printf '%s\n' "$@" > "$W/h/.claws-mail/accountrc"; chmod 600 "$W/h/.claws-mail/accountrc"; }
mk '[Account: 1]' 'account_name=mail.i2p' 'is_default=1' 'name=' 'address=username@mail.i2p' '[Account: 2]' 'account_name=' 'name=' 'name=Alice' 'nickname=' 'address=b@mail.i2p'
HOME=$W/h "$W/launcher" --compose 'mailto:a b@mail.i2p' >/dev/null 2>&1
R=$W/h/.claws-mail/accountrc
grep -qx 'name=' "$R" && no "empty name lines dropped" || ok "empty name lines dropped"
[ "$(grep -c . "$R")" = 9 ] && grep -qx 'name=Alice' "$R" && grep -qx 'account_name=' "$R" && grep -qx 'nickname=' "$R" \
  && ok "other lines untouched (a real name, account_name=, nickname=)" || no "other lines untouched"
[ "$(stat -c %a "$R")" = 600 ] && ok "accountrc stays 600" || no "accountrc mode $(stat -c %a "$R")"
[ "$(printf '%s|' $(cat "$W/h/argv" | tr ' ' '_'))" = "--compose|mailto:a_b@mail.i2p|" ] && ok "arguments passed through" || no "arguments passed through"
ls "$W/h/.claws-mail" | grep -q 'accountrc\.' && no "temp file left" || ok "no temp file left"
# a symlinked accountrc is left alone; no accountrc still starts Claws
mk 'name=' 'address=x@mail.i2p'; mv "$W/h/.claws-mail/accountrc" "$W/real"; ln -s "$W/real" "$W/h/.claws-mail/accountrc"
HOME=$W/h "$W/launcher" >/dev/null 2>&1; grep -qx 'name=' "$W/real" && [ -f "$W/h/argv" ] && ok "symlink not followed, Claws still starts" || no "symlink case"
rm -rf "$W/h"; mkdir -p "$W/h"; HOME=$W/h "$W/launcher" >/dev/null 2>&1; [ -f "$W/h/argv" ] && ok "first start without accountrc" || no "first start without accountrc"

# the gpg side: the parameters Claws builds (sgpgme.c), empty name vs. the address it falls back to
if command -v gpg >/dev/null; then
  kg(){ G=$(mktemp -d "$W/g.XXXX"); printf 'Key-Type: RSA\nKey-Length: 2048\nSubkey-Type: RSA\nSubkey-Length: 2048\nName-Real: %s\nName-Email: username@mail.i2p\nExpire-Date: 0\n%%no-protection\n' "$1" \
      | gpg --homedir "$G" --batch --gen-key 2>/dev/null; r=$?; gpgconf --homedir "$G" --kill all 2>/dev/null; return $r; }
  kg '' && no "gpg accepts an empty Name-Real (premise changed)" || ok "gpg rejects an empty Name-Real (the bug)"
  kg 'username@mail.i2p' && ok "gpg accepts the address as Name-Real (the fix)" || no "address as Name-Real"
else echo "SKIP gpg missing"; fi
exit $fail
