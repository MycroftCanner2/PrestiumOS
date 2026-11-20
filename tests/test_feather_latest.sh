#!/bin/bash
# Prestium 2.1: Feather is the newest signed GitHub release at build time (scripts/feather-latest.sh),
# like Tor Browser. Only a clean version number is taken from GitHub (a published, non-prerelease
# release), never older than FEATHER_MIN_VERSION; the zip must pass the signature check with FEATHER_KEY
# and hold feather-<that version>; a pinned FEATHER_VERSION keeps the SHA-256 check. No network: the
# release list is a file and fetch-thirdparty.sh's own Feather code runs against a pre-filled cache,
# signed with a throw-away key.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'gpgconf --homedir "$T/g" --kill all >/dev/null 2>&1; rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
F=$R/scripts/fetch-thirdparty.sh; V=$R/thirdparty/versions.sh; L=$R/scripts/feather-latest.sh
# shellcheck disable=SC2034  # read by feather_latest
FEATHER_MIN_VERSION=2.9.1
# shellcheck source=../scripts/feather-latest.sh
. "$L"

## discovery
J(){ printf '{"tag_name": %s, "draft": %s, "prerelease": %s, "assets": [{"browser_download_url": "https://evil.example/x.zip"}]}' "$1" "${2:-false}" "${3:-false}"; }
lat(){ printf '%s' "$1" > "$T/j"; PRESTIUM_FEATHER_JSON_FILE="$T/j" feather_latest 2>/dev/null; }
[ "$(lat "$(J '"2.9.1"')")" = 2.9.1 ] && ok "same as minimum: accepted" || bad "2.9.1 refused"
[ "$(lat "$(J '"2.9.10"')")" = 2.9.10 ] && ok "2.9.10 > 2.9.9 (version order, not text order)" || bad "2.9.10"
[ "$(lat "$(J '"3.0"')")" = 3.0 ] && ok "newer two-part version accepted" || bad "3.0"
lat "$(J '"2.9.0"')" >/dev/null && bad "older than minimum accepted" || ok "2.9.0 < minimum: refused (no downgrade)"
lat "$(J '"2.8.1"')" >/dev/null && bad "2.8.1 accepted" || ok "2.8.1 refused"
lat "$(J '"3.0"' true)" >/dev/null && bad "draft accepted" || ok "draft refused"
lat "$(J '"3.0"' false true)" >/dev/null && bad "prerelease accepted" || ok "prerelease refused"
lat "$(J '"3.0"' null)" >/dev/null && bad "missing draft flag accepted" || ok "missing draft flag refused"
for v in '"v2.9.1"' '"2.9.1-beta"' '"2.9.1; rm -rf /"' '"../2.9.1"' '"2.9.1/../x"' '"2.9.1\n"' '"02.9.1"' '"2.9.1a"' '""' '2.91' 'null' '["3.0"]'; do
  lat "$(J "$v")" >/dev/null && bad "bad tag accepted: $v" || ok "bad tag refused: $v"; done
lat 'not json' >/dev/null && bad "junk accepted" || ok "unparsable release refused"
lat '{}' >/dev/null && bad "no tag accepted" || ok "missing tag refused"
for v in $'2.9.1\n../../x' $'2.9.1\n' $'x\n2.9.1' '2.9.1 ' ' 2.9.1'; do
  feather_version_ok "$v" && bad "multi-line or padded version accepted: $(printf %q "$v")" || ok "refused: $(printf %q "$v")"; done
# fallback: the /releases/latest redirect (only a github.com tag URL with a clean version counts)
[ "$(feather_redirect_version https://github.com/feather-wallet/feather/releases/tag/2.9.2)" = 2.9.2 ] && ok "redirect: tag read" || bad "redirect tag"
for u in https://github.com/feather-wallet/feather/releases/tag/v2.9.2 https://evil.example/feather-wallet/feather/releases/tag/2.9.2 \
         https://github.com/feather-wallet/feather/releases/tag/2.9.2/x http://github.com/feather-wallet/feather/releases/tag/2.9.2 ''; do
  [ -z "$(feather_redirect_version "$u")" ] && ok "redirect refused: ${u:-empty}" || bad "redirect accepted: $u"; done
mkdir -p "$T/bin"
# stub curl: the API fails (rate limit), the redirect points at a tag
cat > "$T/bin/curl" <<'SH'
#!/bin/sh
case "$*" in *api.github.com*) exit 22;; *releases/latest*) printf '%s' "$STUB_LOC";; *) exit 22;; esac
SH
chmod +x "$T/bin/curl"
[ "$(PATH="$T/bin:$PATH" STUB_LOC=https://github.com/feather-wallet/feather/releases/tag/2.9.3 feather_latest 2>/dev/null)" = 2.9.3 ] \
  && ok "API unreachable: the /releases/latest redirect is used" || bad "redirect fallback"
PATH="$T/bin:$PATH" STUB_LOC=https://github.com/feather-wallet/feather/releases/tag/2.9.0 feather_latest >/dev/null 2>&1 \
  && bad "redirect to an older release accepted" || ok "redirect to an older release refused"
grep -q -- '--max-redirs 0' "$L" && grep -q -- '--proto =https' "$L" && ok "GitHub asked over HTTPS, no redirects followed" || bad "discovery fetch options"
grep -q 'browser_download_url' "$L" && bad "a URL is read from GitHub's answer" || ok "only the version is read (URLs built from it)"

## static: versions.sh and fetch-thirdparty.sh
grep -q '^FEATHER_VERSION=${PRESTIUM_FEATHER_VERSION:-latest}$' "$V" && grep -q '^FEATHER_SHA256=${PRESTIUM_FEATHER_SHA256:-}$' "$V" \
  && ok "versions.sh: latest by default, pin by env or edit" || bad "FEATHER_VERSION default"
grep -qE '^FEATHER_MIN_VERSION=2\.9\.1 ' "$V" && ok "versions.sh: minimum 2.9.1" || bad "FEATHER_MIN_VERSION"
awk '/^# Feather \(Monero wallet/,/^# i2pd:/' "$F" > "$T/fb"
grep -q 'get https://github.com/feather-wallet/feather/releases/download/$FEATHER_VERSION/$FEF $FEF' "$T/fb" \
  && grep -q 'get https://github.com/feather-wallet/feather/releases/download/$FEATHER_VERSION/$FEF.asc $FEF.asc' "$T/fb" \
  && ok "zip and .asc from GitHub releases" || bad "download URLs"
grep -q '^sigok "$FEW/$FEF.asc" "$FEW/$FEF" "$FEATHER_KEY" "$K/feather.asc"$' "$T/fb" && ok "signature always checked with FEATHER_KEY" || bad "signature check"
grep -q '"feather.zip $FEATHER_SHA256"' "$F" && grep -q 'cp "$FEW/$FEF" "$S/feather.zip"' "$F" \
  && ok "the verified private copy is staged and re-checked" || bad "staging"
HK=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
grep -q 'unzip -p "$S/feather.zip" "feather-$FV"' "$HK" && grep -q 'E: bad Feather version' "$HK" \
  && ok "hook 0200: installs feather-<version> for any version, checks the version's form" || bad "hook 0200 Feather"
grep -q 'echo "feather: $(cat "$TP/feather.version"' "$R/build.sh" && ok "manifest: the Feather version and SHA-256 actually staged" || bad "manifest"

## fetch-thirdparty.sh's own Feather code, offline
command -v gpg >/dev/null && command -v unzip >/dev/null || { echo "SKIP fetch run (gpg/unzip missing)"; [ $fail = 0 ] && echo "feather latest: OK"; exit $fail; }
mkdir -m 700 "$T/g"; gk(){ gpg --homedir "$T/g" --batch -q "$@"; }
gk --pinentry-mode loopback --passphrase '' --quick-gen-key feather@example.invalid ed25519 sign 1y 2>/dev/null
gk --pinentry-mode loopback --passphrase '' --quick-gen-key other@example.invalid ed25519 sign 1y 2>/dev/null
FPR=$(gk --with-colons --list-keys feather@example.invalid | awk -F: '/^fpr/{print $10; exit}')
mkdir -p "$T/k"; gk --armor --export "$FPR" > "$T/k/feather.asc"
{ awk '/^get\(\)\{/,/^  sigstatus_detached_ok "\$2" "\$st" "\$3" \|\| exit 1; \}$/' "$F"; cat "$T/fb"
  echo 'echo "RESULT $FEATHER_VERSION $FEATHER_SHA256"'; } > "$T/run.sh"
printf '#!/bin/sh\necho "network used: $*" >&2; exit 99\n' > "$T/bin/curl"   # the harness must never download
grep -q '^sigok()' "$T/run.sh" && grep -q 'feather_latest' "$T/run.sh" && ok "harness built from fetch-thirdparty.sh" || bad "harness extraction"
zipv(){ # cache-dir version entry-name signer
  mkdir -p "$1" "$T/z"; printf 'ELF %s' "$2" > "$T/z/$3"; (cd "$T/z" && rm -f x.zip && python3 -c 'import sys,zipfile; z=zipfile.ZipFile("x.zip","w"); z.write(sys.argv[1]); z.close()' "$3")
  mv "$T/z/x.zip" "$1/feather-$2-linux.zip"; rm -rf "$T/z"
  gk --pinentry-mode loopback --passphrase '' -u "$4" --armor --detach-sign -o "$1/feather-$2-linux.zip.asc" "$1/feather-$2-linux.zip"; }
fe(){ # cache json [pinned-version pinned-sha] -> output
  local gh; gh=$(mktemp -d "$T/h.XXXXXX")
  printf '%s' "$2" > "$T/rel.json"
  env -i PATH="$T/bin:$PATH" HOME="$T" TOP="$R" C="$1" K="$T/k" GNUPGHOME="$gh" REPIN=0 PRESTIUM_FEATHER_JSON_FILE="$T/rel.json" \
    FEATHER_VERSION="${3:-latest}" FEATHER_SHA256="${4:-}" FEATHER_MIN_VERSION=2.9.1 FEATHER_KEY="$FPR" \
    bash -c 'set -e; . "$0"' "$T/run.sh" > "$T/out" 2>&1; local rc=$?
  [ -n "${VERBOSE:-}" ] && tail -3 "$T/out" | sed 's/^/     | /' >&2
  cat "$T/out"; return $rc; }
zipv "$T/c1" 2.9.4 feather-2.9.4 feather@example.invalid; zipv "$T/c1" 2.9.1 feather-2.9.1 feather@example.invalid
SHA=$(sha256sum "$T/c1/feather-2.9.4-linux.zip" | cut -c1-64)
o=$(fe "$T/c1" "$(J '"2.9.4"')"); grep -qx "RESULT 2.9.4 $SHA" <<<"$o" && grep -q "OK FEATHER $SHA (Feather 2.9.4, signature verified, not pinned)" <<<"$o" \
  && ok "newest release picked, signature checked, SHA-256 recorded" || bad "newest: $o"
o=$(fe "$T/c1" "$(J '"2.9.0"')") && bad "release older than the minimum accepted" || ok "older than the minimum: build stops ($(tail -1 <<<"$o"))"
o=$(fe "$T/c1" "$(J '"v2.9.4"')") && bad "malformed tag accepted" || ok "malformed tag: build stops"
zipv "$T/c2" 2.9.4 feather-2.9.4 other@example.invalid
o=$(fe "$T/c2" "$(J '"2.9.4"')") && bad "zip signed by another key accepted" || ok "signature by another key: build stops"
zipv "$T/c3" 2.9.4 feather-2.9.4 feather@example.invalid; printf x >> "$T/c3/feather-2.9.4-linux.zip"
o=$(fe "$T/c3" "$(J '"2.9.4"')") && bad "tampered zip accepted" || ok "bad signature (tampered zip): build stops"
zipv "$T/c4" 2.9.4 feather-2.9.4 feather@example.invalid; echo 'not a signature' > "$T/c4/feather-2.9.4-linux.zip.asc"
o=$(fe "$T/c4" "$(J '"2.9.4"')") && bad "junk signature accepted" || ok "no valid signature: build stops"
zipv "$T/c5" 2.9.4 feather-2.9.1 feather@example.invalid
o=$(fe "$T/c5" "$(J '"2.9.4"')") && bad "zip holding another version accepted" || ok "signed zip holding another version: build stops"
o=$(fe "$T/c1" "$(J '"2.9.4"')" 2.9.4 "$SHA"); grep -qx "RESULT 2.9.4 $SHA" <<<"$o" && grep -q "^OK FEATHER $SHA$" <<<"$o" && ok "pinned mode: SHA-256 checked" || bad "pinned: $o"
o=$(fe "$T/c1" "$(J '"2.9.4"')" 2.9.4 0000000000000000000000000000000000000000000000000000000000000000) && bad "pinned mode accepted a wrong SHA-256" || ok "pinned mode: wrong SHA-256 stops"
o=$(fe "$T/c1" "$(J '"2.9.4"')" 2.9.0 "$SHA") && bad "pinned version below the minimum accepted" || ok "pinned mode: below the minimum stops"
o=$(fe "$T/c1" "$(J '"2.9.4"')" 2.9.4 "") && bad "pinned mode without a SHA-256 accepted" || ok "pinned mode: no SHA-256 stops"

[ $fail = 0 ] && echo "feather latest: OK"; exit $fail
