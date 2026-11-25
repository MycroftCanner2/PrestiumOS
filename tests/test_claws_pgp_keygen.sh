#!/bin/bash
# Prestium 2.1: Claws Mail key generation. Claws reads an empty "name=" in accountrc as an empty full
# name and its "Generate a new key pair" passes that to gpg as an empty Name-Real, which gpg rejects
# ("Couldn't generate a new key pair: General error"). There is no shipped account: the launcher writes
# it from a first-start form, drops an empty name line (Claws writes it back on save) and keeps the
# @mail.i2p privacy settings before each start, and every way into Claws goes through the launcher.
# The key it generates is Ed25519 + Curve25519 (hook 0470). Unprivileged; needs gpg and python3-gpg for the key-generation part.
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
grep -qx 'exec /usr/local/lib/prestium/app-confine claws-mail "\$@"' "$L" && ok "launcher execs the confined binary through app-confine (review F-01)" || no "launcher exec"

# launcher behaviour, with /usr/bin/claws-mail replaced by a stub that records its argv
mkdir -p "$W/bin"; printf '#!/bin/sh\nfor a; do printf "%%s\\n" "$a"; done > "$HOME/argv"\n' > "$W/bin/claws"; chmod 755 "$W/bin/claws"
sed "s#^exec /usr/local/lib/prestium/app-confine claws-mail #exec $W/bin/claws #" "$L" > "$W/launcher"; chmod 755 "$W/launcher"
mk(){ rm -rf "$W/h"; mkdir -p "$W/h/.claws-mail"; printf '%s\n' "$@" > "$W/h/.claws-mail/accountrc"; chmod 600 "$W/h/.claws-mail/accountrc"; }
mk '[Account: 1]' 'account_name=mail.i2p' 'is_default=1' 'name=' 'address=username@mail.i2p' '[Account: 2]' 'account_name=' 'name=' 'name=Alice' 'nickname=' 'address=b@mail.i2p'
HOME=$W/h "$W/launcher" --compose 'mailto:a b@mail.i2p' >/dev/null 2>&1
R=$W/h/.claws-mail/accountrc
grep -qx 'name=' "$R" && no "empty name lines dropped" || ok "empty name lines dropped"
[ "$(grep -c . "$R")" = 15 ] && grep -qx 'name=Alice' "$R" && grep -qx 'account_name=' "$R" && grep -qx 'nickname=' "$R" \
  && ok "other lines untouched (a real name, account_name=, nickname=)" || no "other lines untouched"
[ "$(stat -c %a "$R")" = 600 ] && ok "accountrc stays 600" || no "accountrc mode $(stat -c %a "$R")"
[ "$(printf '%s|' $(cat "$W/h/argv" | tr ' ' '_'))" = "--compose|mailto:a_b@mail.i2p|" ] && ok "arguments passed through" || no "arguments passed through"
ls "$W/h/.claws-mail" | grep -q 'accountrc\.' && no "temp file left" || ok "no temp file left"
# a symlinked accountrc is left alone; no accountrc still starts Claws
mk 'name=' 'address=x@mail.i2p'; mv "$W/h/.claws-mail/accountrc" "$W/real"; ln -s "$W/real" "$W/h/.claws-mail/accountrc"
HOME=$W/h "$W/launcher" >/dev/null 2>&1; grep -qx 'name=' "$W/real" && [ -f "$W/h/argv" ] && ok "symlink not followed, Claws still starts" || no "symlink case"
rm -rf "$W/h"; mkdir -p "$W/h"; PATH=/usr/bin:/bin HOME=$W/h "$W/launcher" >/dev/null 2>&1; [ -f "$W/h/argv" ] && ok "first start without accountrc or form: Claws (wizard) starts" || no "first start without accountrc"

# privacy settings on @mail.i2p accounts: no X-Mailer, mail.i2p (not the hostname) as domain
sec(){ awk -v n="[Account: $2]" '/^\[/{on=($0==n);next} on' "$1"; }
mk '[Account: 1]' 'address=a@mail.i2p' 'generate_xmailer=1' 'set_domain=0' 'domain=prestium' \
   '[Account: 2]' 'address=b@mail.i2p' \
   '[Account: 3]' 'address=c@example.org' 'generate_xmailer=1' 'set_domain=0'
HOME=$W/h "$W/launcher" >/dev/null 2>&1
for n in 1 2; do
  s=$(sec "$R" $n)
  printf '%s\n' "$s" | grep -qx generate_xmailer=0 && printf '%s\n' "$s" | grep -qx set_domain=1 && printf '%s\n' "$s" | grep -qx domain=mail.i2p \
    && [ "$(printf '%s\n' "$s" | grep -c '^\(generate_xmailer\|set_domain\|domain\)=')" = 3 ] \
    && ok "account $n (@mail.i2p): no X-Mailer, domain mail.i2p" || no "account $n privacy: $s"
done
s=$(sec "$R" 3); printf '%s\n' "$s" | grep -qx generate_xmailer=1 && printf '%s\n' "$s" | grep -qx set_domain=0 && ! printf '%s\n' "$s" | grep -q '^domain=' \
  && ok "other accounts untouched" || no "non-I2P account changed: $s"
cp "$R" "$W/before"; HOME=$W/h "$W/launcher" >/dev/null 2>&1; cmp -s "$R" "$W/before" && ok "second start changes nothing" || no "not idempotent"

# first start: the form writes the account before Claws starts
Z=$W/zbin; mkdir -p "$Z"
cat > "$Z/zenity" <<'S'
#!/bin/sh
n=$(cat "$ZN" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$ZN"
eval "a=\${ZA$n-}"; [ "$a" = CANCEL ] && exit 1; printf '%b\n' "$a"
S
chmod 755 "$Z/zenity"
fs(){ rm -rf "$W/h" "$W/zn"; mkdir -p "$W/h"; env PATH="$Z:/usr/bin:/bin" HOME="$W/h" ZN="$W/zn" PRESTIUM_CLAWS_ACCOUNT_IN="$C/usr/local/share/prestium-claws/accountrc.in" "$@" "$W/launcher" >/dev/null 2>&1; }
fs ZA1='Alice Q\nAlice@Mail.I2P'
[ -f "$W/h/argv" ] && grep -qx 'address=alice@mail.i2p' "$R" && grep -qx 'user_id=alice' "$R" && grep -qx 'name=Alice Q' "$R" \
  && ok "form: account written (address lowercased, user from address, name), Claws started" || no "form account: $(cat "$R" 2>/dev/null | head -5)"
grep -qx 'receive_server=127.0.0.1' "$R" && grep -qx 'pop_port=7660' "$R" && grep -qx 'smtp_port=7659' "$R" && grep -qx 'use_smtp_auth=1' "$R" \
  && grep -qx 'generate_xmailer=0' "$R" && grep -qx 'set_domain=1' "$R" && grep -qx 'domain=mail.i2p' "$R" \
  && ok "form: I2P servers, SMTP auth, no X-Mailer, domain mail.i2p from the first session" || no "form account settings"
! grep -q '^#\|^password=\|^smtp_password=\|@ADDRESS@\|@USER@' "$R" && [ "$(stat -c %a "$R")" = 600 ] \
  && ok "form: no comments, placeholders or password lines; mode 600" || no "form account file"
fs ZA1='\nbob'; grep -qx 'address=bob@mail.i2p' "$R" && ! grep -q '^name=' "$R" && ok "form: empty name gives no name line; @mail.i2p added" || no "empty name/short address"
fs ZA1='x\nbob@example.org' ZA2='x\nb\$(id)@mail.i2p' ZA3='x\nbob@mail.i2p'
[ "$(cat "$W/zn")" = 3 ] && grep -qx 'address=bob@mail.i2p' "$R" && ok "form: other domains and shell syntax refused, asked again" || no "address validation (asked $(cat "$W/zn"))"
fs ZA1='a\nb\nc@mail.i2p' ZA2='ok\nc@mail.i2p'; [ "$(cat "$W/zn")" = 2 ] && [ "$(grep -c '^name=' "$R")" = 1 ] && grep -qx 'name=ok' "$R" \
  && ok "form: an extra line (injection) is refused" || no "line injection"
fs ZA1=CANCEL; [ ! -e "$R" ] && [ ! -f "$W/h/argv" ] && ok "form cancelled: no account, Mail not started" || no "cancel"

# the key Claws generates: hook 0470 patches pgpcore.so (Debian's own, or a stand-in with the same
# parameter list) so "Generate a new key pair" makes Ed25519 + Curve25519 instead of RSA-2048
H=$T/config/hooks/live/0470-prestium-claws-keygen.hook.chroot; PL=usr/lib/x86_64-linux-gnu/claws-mail/plugins/pgpcore.so
[ -x "$H" ] && ls "$T/config/hooks/live" | grep -q '^0400-' && ok "hook 0470 present, executable" || no "hook 0470 missing"
grep -q -- "--local --rename --divert \"\$P.debian\" --add \"\$P\"" "$H" && ok "hook keeps Debian's pgpcore.so diverted (dpkg-divert)" || no "hook dpkg-divert"
RSA=$'<GnupgKeyParms format="internal">\nKey-Type: RSA\nKey-Length: 2048\nSubkey-Type: RSA\nSubkey-Length: 2048\nName-Real: %s\nName-Email: %s\nExpire-Date: 0\n%s%s%s</GnupgKeyParms>\n'
fake(){ rm -rf "$W/r"; mkdir -p "$W/r/${PL%/*}"; { printf 'ELF\0'; for n in $(seq "$1"); do printf '%s\0' "$RSA"; done; printf 'Couldn'"'"'t generate a new key pair: %%s\0'; } > "$W/r/$PL"; }
hk(){ PRESTIUM_CLAWS_ROOT=$W/r sh "$H" >/dev/null 2>&1; }
fake 0; hk && no "hook accepts a plugin without the RSA list" || ok "hook fails the build when Claws' parameter list is not found"
fake 2; hk && no "hook accepts two RSA lists" || ok "hook fails the build on more than one match"
if [ -f "/$PL" ]; then mkdir -p "$W/r2/${PL%/*}"; cp "/$PL" "$W/r2/$PL"; SRC="Debian's pgpcore.so ($(dpkg-query -W -f '${Version}' claws-mail-pgpmime 2>/dev/null))"
else fake 1; mv "$W/r" "$W/r2"; SRC="a stand-in pgpcore.so"; fi
PRESTIUM_CLAWS_ROOT=$W/r2 sh "$H" >/dev/null 2>&1 && PRESTIUM_CLAWS_ROOT=$W/r2 sh "$H" >/dev/null 2>&1 && ok "hook patches $SRC (and again on a second run)" || no "hook on $SRC"
O=$W/r2/$PL.debian; N=$W/r2/$PL
[ "$(stat -c %s "$O")" = "$(stat -c %s "$N")" ] && [ "$(cmp -l "$O" "$N" | wc -l)" -le 112 ] && ok "same size, only the parameter list changed" || no "patched plugin size/changes"
grep -aq 'Key-Type: RSA' "$N" && no "patched plugin still asks for RSA" || ok "patched plugin no longer asks for RSA"
grep -aq 'Key-Type: RSA' "$O" && ok "Debian's original kept as pgpcore.so.debian" || no "original"

# the gpg side: the exact list the patched plugin hands gpgme (sgpgme.c: name, address, and no
# passphrase lines with gpg 2, whose agent asks for the passphrase), empty name vs. the address
if command -v gpg >/dev/null && python3 -c 'import gpg' 2>/dev/null; then
  kg(){ G=$(mktemp -d "$W/g.XXXX"); KG_HOME=$G python3 -I - "$N" "$1" > "$G/out" 2>/dev/null <<'PY'
import gpg, os, re, sys
d = open(sys.argv[1], "rb").read()
fmt = re.search(rb'<GnupgKeyParms format="internal">\n.*?</GnupgKeyParms>\n', d, re.S).group(0).decode()
parms = fmt % (sys.argv[2], "username@mail.i2p", "", "", "")
c = gpg.Context(home_dir=os.environ["KG_HOME"], armor=True, pinentry_mode=gpg.constants.PINENTRY_MODE_LOOPBACK)
c.set_passphrase_cb(lambda *a: "pw")
r = c.op_genkey(parms, None, None)
k = c.get_key(c.op_genkey_result().fpr, secret=False)
for s in k.subkeys:
    print("key", s.pubkey_algo, gpg.core.pubkey_algo_name(s.pubkey_algo), s.curve, "S" if s.can_sign else "", "C" if s.can_certify else "",
          "E" if s.can_encrypt else "", "A" if s.can_authenticate else "", s.expires)
print("uid", k.uids[0].uid)
plain = b"hello over I2P\n"
ct, _, sr = c.encrypt(plain, recipients=[k], sign=True, always_trust=True)
pt, dr, vr = c.decrypt(ct, verify=True)
assert pt == plain and vr.signatures[0].status == 0 and vr.signatures[0].fpr == k.fpr
print("roundtrip ok")
PY
    r=$?; gpgconf --homedir "$G" --kill all 2>/dev/null; return $r; }
  kg '' && no "gpg accepts an empty Name-Real (premise changed)" || ok "gpg rejects an empty Name-Real (the bug)"
  if kg 'username@mail.i2p'; then
    ok "gpg accepts the address as Name-Real (the fix) with the new parameters"
    o=$(cat "$G/out")
    printf '%s\n' "$o" | grep -qx 'key 303 EdDSA ed25519 S C   0' && ok "primary key: Ed25519, sign + certify, no expiry" || no "primary key: $o"
    printf '%s\n' "$o" | grep -qx 'key 302 ECDH cv25519   E  0' && ok "subkey: Curve25519, encrypt, no expiry" || no "subkey: $o"
    [ "$(printf '%s\n' "$o" | grep -c '^key ')" = 2 ] && ! printf '%s\n' "$o" | grep -q RSA && ok "no RSA keys" || no "key list: $o"
    printf '%s\n' "$o" | grep -qx 'uid username@mail.i2p <username@mail.i2p>' && ok "user ID from the address" || no "uid: $o"
    printf '%s\n' "$o" | grep -qx 'roundtrip ok' && ok "sign + encrypt, decrypt + verify work" || no "sign/encrypt round trip"
  else no "address as Name-Real"; fi
else echo "SKIP gpg or python3-gpg missing"; fi
exit $fail
