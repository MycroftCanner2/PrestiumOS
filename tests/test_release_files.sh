#!/bin/bash
# 2.1 (security audit): build.sh writes SHA256SUMS (ISO, manifest, package list) and a manifest; a
# release is signed with scripts/sign-release.sh (detached, verified, full fingerprint only).
# Signs with a throw-away key in a temporary GNUPGHOME; no network, no build.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
B=$R/build.sh; S=$R/scripts/sign-release.sh
grep -q 'sha256sum "$OUT" "$MAN"' "$B" && ok "build.sh: SHA256SUMS over the ISO and the manifest" || bad "no SHA256SUMS"
grep -q 'rm -f SHA256SUMS.asc' "$B" && ok "build.sh: drops an old signature" || bad "old signature kept"
for k in image_sha256 build_date_utc source_commit tor_browser firefox_local nodejs thelounge feather; do
  grep -q "echo \"$k: " "$B" && ok "manifest: $k" || bad "manifest lacks $k"; done
grep -qx '/SHA256SUMS.asc' "$R/.gitignore" && ok "release files not committed" || bad ".gitignore"
command -v gpg >/dev/null || { echo "SKIP gpg missing"; exit $fail; }
T=$(mktemp -d); export GNUPGHOME=$T/g; mkdir -m 700 "$GNUPGHOME"; trap 'gpgconf --kill all >/dev/null 2>&1; rm -rf "$T"' EXIT
gpg -q --batch --pinentry-mode loopback --passphrase '' --quick-gen-key rel@example.invalid ed25519 sign never 2>/dev/null
FPR=$(gpg --batch --with-colons --list-keys rel@example.invalid | awk -F: '/^fpr/{print $10; exit}')
cd "$T" && echo iso > Prestium-2.0-amd64.iso && echo man > Prestium-2.0-amd64.manifest
sha256sum Prestium-2.0-amd64.iso Prestium-2.0-amd64.manifest > SHA256SUMS
o=$(bash "$S" "${FPR:0:16}" 2>&1) && bad "short key ID accepted" || ok "short key ID refused"
o=$(bash "$S" "$FPR" 2>&1) && [ -s SHA256SUMS.asc ] && ok "signed and verified" || bad "sign: $o"
gpg --batch --verify SHA256SUMS.asc SHA256SUMS 2>/dev/null && ok "SHA256SUMS.asc verifies" || bad "does not verify"
grep -q 'BEGIN PGP SIGNATURE' SHA256SUMS.asc && ok "detached, armored" || bad "not armored"
echo changed > Prestium-2.0-amd64.iso
o=$(bash "$S" "$FPR" 2>&1) && bad "signed a SHA256SUMS that does not match the files" || ok "refuses when the files changed"
exit $fail
