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
grep -q 'sigok "$TBW/$TBF.asc" "$TBW/$TBF" "$TB_KEY"$' "$T/tb" && ok "signature always checked with TB_KEY" || bad "signature check missing"
[ "$(grep -n 'sigok' "$T/tb" | head -1 | cut -d: -f1)" -lt "$(grep -n 'TB_SHA256=$(sha "$TBW' "$T/tb" | cut -d: -f1)" ] && ok "SHA recorded only after the signature passed" || bad "order"
grep -q 'pin TB "$TBW/$TBF" "$TB_SHA256"' "$T/tb" && ok "pinned mode still checks the SHA-256" || bad "pinned SHA check gone"
grep -q 'tb_version_ge "$TB_VERSION" "$TB_MIN_VERSION"' "$T/tb" && ok "pinned version also held to the minimum" || bad "pinned minimum"
grep -q '"tor-browser.tar.xz $TB_SHA256"' "$F" && ok "staged copy re-checked against the recorded SHA-256" || bad "stage re-check"
# 2.1 audit: one line only (grep -x matched any line of a multi-line value)
for v in $'16.0.1\n../../x' $'16.0.1\n' $'x\n16.0.1' '16.0.1 ' ' 16.0.1'; do
  tb_version_ok "$v" && bad "multi-line or padded version accepted: $(printf %q "$v")" || ok "refused: $(printf %q "$v")"; done
# 2.1 audit: the tarball's own tbb_version.json must be the version asked for (signatures do not bind names)
mk(){ python3 -I - "$T/$1.tar.xz" "$2" <<'PY'
import io, sys, tarfile
with tarfile.open(sys.argv[1], "w:xz") as t:
    if sys.argv[2] != "none":
        b = sys.argv[2].encode(); i = tarfile.TarInfo("tor-browser/Browser/tbb_version.json"); i.size = len(b)
        t.addfile(i, io.BytesIO(b))
PY
}
mk rel '{"version":"16.0.1","architecture":"linux-x86_64","channel":"release"}'
mk old '{"version":"16.0","architecture":"linux-x86_64","channel":"release"}'
mk alpha '{"version":"16.5a1","architecture":"linux-x86_64","channel":"alpha"}'
mk arch '{"version":"16.0.1","architecture":"linux-i686","channel":"release"}'
mk junk '{"version":"16.0.1\n","architecture":"linux-x86_64","channel":"release"}'
mk none none
[ "$(tb_tarball_version "$T/rel.tar.xz")" = 16.0.1 ] && ok "tarball version read from tbb_version.json" || bad "tarball version"
[ "$(tb_tarball_version "$T/old.tar.xz")" = 16.0 ] && ok "older tarball reports its own version (fetch compares it)" || bad "old tarball"
for x in alpha arch junk none; do tb_tarball_version "$T/$x.tar.xz" >/dev/null && bad "tarball accepted: $x" || ok "tarball refused: $x"; done
grep -q 'TB_GOT=$(tb_tarball_version "$TBW/$TBF")' "$T/tb" && grep -q '\[ "$TB_GOT" = "$TB_VERSION" \]' "$T/tb" \
  && ok "fetch: tarball version must equal the requested version" || bad "fetch: no tarball version check"
grep -q 'cp "$TBW/$TBF" "$S/tor-browser.tar.xz"' "$F" && ok "fetch: stages the verified private copy" || bad "fetch: stages from the shared cache"
grep -q 'sigstatus_detached_ok' "$F" && ok "fetch: detached-signature policy" || bad "fetch: detached policy"
HK=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
grep -q 'tor-browser.version' "$HK" && grep -q 'exit 1' "$HK" && ok "hook 0200: installed version checked again" || bad "hook 0200 check"
[ $fail = 0 ] && echo "tb latest: OK"; exit $fail
