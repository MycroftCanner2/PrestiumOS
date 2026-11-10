#!/bin/bash
# Prestium 2.1: Tor Browser is the newest release at build time (scripts/tb-latest.sh). Only a clean
# version number is taken from the release list, never older than TB_MIN_VERSION; the tarball is still
# signature-checked with TB_KEY, and a pinned TB_VERSION keeps the SHA-256 check. No network.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
TB_MIN_VERSION=16.0.1
. "$R/scripts/tb-latest.sh"
lat(){ printf '%s' "$1" > "$T/j"; PRESTIUM_TB_JSON_FILE="$T/j" tb_latest 2>/dev/null; }
J(){ printf '{"version": %s, "downloads": {"linux-x86_64": {"ALL": {"binary": "https://evil.example/x.tar.xz"}}}}' "$1"; }
[ "$(lat "$(J '"16.0.1"')")" = 16.0.1 ] && ok "same as minimum: accepted" || bad "16.0.1 refused"
[ "$(lat "$(J '"16.0.10"')")" = 16.0.10 ] && ok "16.0.10 > 16.0.9 (version order, not text order)" || bad "16.0.10"
[ "$(lat "$(J '"17.0"')")" = 17.0 ] && ok "two-part version accepted" || bad "17.0"
lat "$(J '"16.0"')" >/dev/null && bad "older than minimum accepted" || ok "16.0 < minimum: refused (no downgrade)"
lat "$(J '"15.0.26"')" >/dev/null && bad "15.0.26 accepted" || ok "15.0.26 refused"
for v in '"16.0.1; rm -rf /"' '"../16.0.1"' '"16.0.1/../x"' '"16.0.1\n"' '"016.0.1"' '"16.0.1a1"' '""' '16.1' 'null' '["16.1"]'; do
  lat "$(J "$v")" >/dev/null && bad "bad version accepted: $v" || ok "bad version refused: $v"; done
lat 'not json' >/dev/null && bad "junk accepted" || ok "unparsable list refused"
lat '{}' >/dev/null && bad "no version accepted" || ok "missing version refused"
F=$R/scripts/fetch-thirdparty.sh; V=$R/thirdparty/versions.sh
grep -q '^TB_VERSION=${PRESTIUM_TB_VERSION:-latest}$' "$V" && ok "versions.sh: latest by default" || bad "TB_VERSION default"
grep -qE '^TB_MIN_VERSION=[0-9.]+ ' "$V" && ok "versions.sh: minimum version set" || bad "no TB_MIN_VERSION"
grep -q 'binary' "$R/scripts/tb-latest.sh" && bad "tb-latest.sh reads a URL from the list" || ok "only the version is read from the list (URL built on dist.torproject.org)"
grep -q -- '--max-redirs 0' "$R/scripts/tb-latest.sh" && grep -q -- '--proto =https' "$R/scripts/tb-latest.sh" && ok "list fetched over HTTPS, no redirects" || bad "list fetch options"
grep -q 'get https://dist.torproject.org/torbrowser/$TB_VERSION/$TBF $TBF' "$F" && ok "tarball from dist.torproject.org" || bad "download URL"
awk '/^# Tor Browser/,/^# Firefox/' "$F" > "$T/tb"
grep -q 'sigok "$C/$TBF.asc" "$C/$TBF" "$TB_KEY"$' "$T/tb" && ok "signature always checked with TB_KEY" || bad "signature check missing"
[ "$(grep -n 'sigok' "$T/tb" | head -1 | cut -d: -f1)" -lt "$(grep -n 'TB_SHA256=$(sha' "$T/tb" | cut -d: -f1)" ] && ok "SHA recorded only after the signature passed" || bad "order"
grep -q 'pin TB "$C/$TBF" "$TB_SHA256"' "$T/tb" && ok "pinned mode still checks the SHA-256" || bad "pinned SHA check gone"
grep -q 'tb_version_ge "$TB_VERSION" "$TB_MIN_VERSION"' "$T/tb" && ok "pinned version also held to the minimum" || bad "pinned minimum"
grep -q '"tor-browser.tar.xz $TB_SHA256"' "$F" && ok "staged copy re-checked against the recorded SHA-256" || bad "stage re-check"
[ $fail = 0 ] && echo "tb latest: OK"; exit $fail
