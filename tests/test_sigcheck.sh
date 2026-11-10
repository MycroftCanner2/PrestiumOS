#!/bin/bash
# Prestium 2.1: the OpenPGP signature policy used by scripts/fetch-thirdparty.sh (scripts/sigcheck.sh)
# against throw-away keys in a temporary GNUPGHOME (no network). gpg and gpgv exit 0 for a good
# signature by an expired key, so these cases check the status lines, through gpg and through gpgv.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
. "$R/scripts/sigcheck.sh"
command -v gpg >/dev/null || { echo "SKIP gpg missing"; exit 0; }
V=checkv; command -v gpgv >/dev/null || { echo "SKIP gpgv missing (gpgv cases)"; V=; }
export GNUPGHOME=$(mktemp -d); W=$(mktemp -d); trap 'gpgconf --kill all >/dev/null 2>&1; rm -rf "$GNUPGHOME" "$W"' EXIT
fail=0
ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
G="gpg -q --batch --pinentry-mode loopback --passphrase ''"
gen(){ # uid [faked-time expire]
  if [ -n "${2:-}" ]; then $G --faked-system-time "$2" --quick-gen-key "$1" ed25519 sign "$3" 2>/dev/null
  else $G --quick-gen-key "$1" ed25519 sign never 2>/dev/null; fi
  gpg --batch --with-colons --list-keys "$1" | awk -F: '/^fpr/{print $10; exit}'; }
printf 'payload\n' > "$W/data"
sig(){ # fpr out [faked-time]
  $G ${3:+--faked-system-time "$3"} -u "$1" --detach-sign -o "$2" "$W/data" 2>/dev/null; }
check(){ # name sig fpr -> output, return code (gpg path)
  local st; st=$(gpg --status-fd 1 --verify "$2" "$W/data" 2>/dev/null) || true
  sigstatus_ok "$1" "$st" "$3"; }
checkv(){ # gpgv path, keyring = exported keys
  local st; st=$(gpgv --status-fd 1 --keyring "$W/ring.gpg" "$2" "$W/data" 2>/dev/null) || true
  sigstatus_ok "$1" "$st" "${3:-}"; }

GOOD=$(gen good@example.invalid)
OTHER=$(gen other@example.invalid)
# expired: created 2020-01-01, expires after 1 year; signed on 2020-06-01 while valid
EXP=$(gen expired@example.invalid 20200101T000000 1y)
REV=$(gen revoked@example.invalid)
sig "$GOOD" "$W/good.sig"; sig "$OTHER" "$W/other.sig"; sig "$EXP" "$W/exp.sig" 20200601T000000; sig "$REV" "$W/rev.sig"
# revoke after signing: import the revocation certificate made at key generation (strip the comment
# and the ":" guard gpg puts before the armour so it imports)
RC=$GNUPGHOME/openpgp-revocs.d/$REV.rev
sed -n '/-----BEGIN PGP PUBLIC KEY BLOCK-----/,$p' "$RC" | sed 's/^:-----/-----/' > "$W/rev.asc"
gpg -q --batch --import "$W/rev.asc" 2>/dev/null
gpg --batch --with-colons --list-keys "$REV" | grep -q '^pub:r:' || bad "test setup: key not revoked"
gpg -q --batch --export > "$W/ring.gpg"

# exit status alone would accept the expired key (the bug this guards against)
gpg --batch --verify "$W/exp.sig" "$W/data" 2>/dev/null && ok "gpg exits 0 for the expired key (status lines needed)"

o=$(check good "$W/good.sig" "$GOOD") && ok "good signature, pinned key: accepted" || bad "good signature rejected: $o"
[ -z "$V" ] || o=$(checkv good "$W/good.sig" "") && ok "good signature via gpgv: accepted" || bad "gpgv good signature rejected: $o"
o=$(check other "$W/other.sig" "$GOOD") && bad "other key accepted" || { case "$o" in *"not made by the pinned key"*) ok "other key: rejected ($o)";; *) bad "other key: wrong message: $o";; esac; }
for f in check $V; do
  o=$($f expired "$W/exp.sig" "$EXP") && bad "$f: expired key accepted" || { case "$o" in *EXPIRED*) ok "$f expired key: rejected ($o)";; *) bad "$f expired: wrong message: $o";; esac; }
  o=$($f revoked "$W/rev.sig" "$REV") && bad "$f: revoked key accepted" || { case "$o" in *REVOKED*) ok "$f revoked key: rejected ($o)";; *) bad "$f revoked: wrong message: $o";; esac; }
done
printf 'tampered\n' > "$W/data"
o=$(check tampered "$W/good.sig" "$GOOD") && bad "tampered data accepted" || { case "$o" in *"bad signature"*) ok "tampered data: rejected ($o)";; *) bad "tampered: wrong message: $o";; esac; }
o=$(sigstatus_ok empty "" "$GOOD") && bad "empty status accepted" || ok "no status output: rejected"
# 2.1 audit: an inline-signed (opaque) message passed as the "detached" signature verifies its own
# text, not the data file; sigstatus_detached_ok refuses it, and a file with two signatures
printf 'payload\n' > "$W/data"
$G -u "$GOOD" --sign -o "$W/opaque.gpg" "$W/data" 2>/dev/null
printf 'other data\n' > "$W/data2"
st=$(gpg --status-fd 1 --verify "$W/opaque.gpg" "$W/data2" 2>/dev/null) || true
sigstatus_ok opaque "$st" "$GOOD" >/dev/null && ok "(general policy alone would accept the opaque message)"
o=$(sigstatus_detached_ok opaque "$st" "$GOOD") && bad "opaque message accepted as detached signature" || ok "opaque message refused ($o)"
$G -u "$GOOD" -u "$OTHER" --detach-sign -o "$W/two.sig" "$W/data" 2>/dev/null
st=$(gpg --status-fd 1 --verify "$W/two.sig" "$W/data" 2>/dev/null) || true
o=$(sigstatus_detached_ok two "$st" "$GOOD") && bad "two signatures accepted" || ok "two signatures refused ($o)"
st=$(gpg --status-fd 1 --verify "$W/good.sig" "$W/data" 2>/dev/null) || true
o=$(sigstatus_detached_ok good "$st" "$GOOD") && ok "detached good signature accepted" || bad "detached good refused: $o"
# 2.1 audit: Node.js: the signer must be one of the pinned current releasers (the keybox has old ones too)
o=$(sigstatus_oneof_ok node "$st" "$OTHER $GOOD") && ok "one of the pinned keys: accepted" || bad "pinned list refused: $o"
o=$(sigstatus_oneof_ok node "$st" "$OTHER") && bad "key outside the list accepted" || ok "key outside the list refused ($o)"
o=$(sigstatus_oneof_ok node "$st" "") && bad "empty list accepted" || ok "empty list refused"
st=$(gpg --status-fd 1 --verify "$W/exp.sig" "$W/data" 2>/dev/null) || true
o=$(sigstatus_oneof_ok node "$st" "$EXP") && bad "expired key in the list accepted" || ok "expired key refused even when listed"
# 2.1 audit: per-publisher keyrings, import errors not hidden, Node keys pinned
F=$R/scripts/fetch-thirdparty.sh
grep -q 'gpg -q --import "$TOP"/thirdparty/keys/\*.asc' "$F" && bad "shared keyring still imported" || ok "no shared keyring"
grep -q 'gpg --homedir "$h" --batch -q --import "$4" || { echo "ERROR: cannot import' "$F" && ok "each check imports only its publisher key, failure stops" || bad "sigok keyring"
for k in '"$TB_KEY" "$K/torbrowser.asc"' '"$FF_KEY" "$K/mozilla.asc"' '"$FEATHER_KEY" "$K/feather.asc"'; do
  grep -qF "$k" "$F" && ok "sigok with its own key file: $k" || bad "sigok key file: $k"; done
. "$R/thirdparty/versions.sh"
[ "$(wc -w <<<"$NODE_KEYS")" -ge 1 ] && ! tr ' ' '\n' <<<"$NODE_KEYS" | grep -qvE '^[0-9A-F]{40}$' && ok "NODE_KEYS: $(wc -w <<<"$NODE_KEYS") fingerprints" || bad "NODE_KEYS malformed"
# fetch-thirdparty.sh must use the policy for every signature, gpgv (Node.js) included
F=$R/scripts/fetch-thirdparty.sh
grep -q '^\. "\$TOP/scripts/sigcheck.sh"' "$F" && grep -q 'sigstatus_detached_ok "\$2" "\$st" "\$3"' "$F" \
  && grep -q 'NST=\$(gpgv --status-fd 1' "$F" && grep -q 'sigstatus_oneof_ok "Node SHASUMS256.txt" "\$NST" "\$NODE_KEYS"' "$F" \
  && ok "fetch-thirdparty.sh: gpg and gpgv paths use sigstatus_ok" || bad "fetch-thirdparty.sh does not use sigstatus_ok everywhere"
# 2.1: the image ships the same policy for the Browser Updater (browser_update.py and the root helper)
cmp -s "$R/scripts/sigcheck.sh" "$R/config/includes.chroot/usr/local/lib/prestium/sigcheck.sh" \
  && ok "the image's /usr/local/lib/prestium/sigcheck.sh is scripts/sigcheck.sh" \
  || bad "config/includes.chroot/usr/local/lib/prestium/sigcheck.sh differs from scripts/sigcheck.sh"
[ $fail = 0 ] && echo "signature policy: OK"; exit $fail
