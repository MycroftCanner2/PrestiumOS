#!/bin/bash
# Prestium 2.1 (security audit): sign a release. Run as the person who holds the release key (not
# root), in the directory with the build's SHA256SUMS:
#   scripts/sign-release.sh KEYID      writes SHA256SUMS.asc (detached, armored) and checks it
# KEYID: the release key's full 40-hex fingerprint (no short IDs). Publish SHA256SUMS,
# SHA256SUMS.asc and the public key; users verify as README.md "Verify a download" says.
set -euo pipefail
K=${1:-}
[[ $K =~ ^[0-9A-Fa-f]{40}$ ]] || { echo "usage: $0 FINGERPRINT (40 hex digits)"; exit 2; }
[ "$(id -u)" != 0 ] || { echo "run as the key holder, not as root"; exit 1; }
[ -s SHA256SUMS ] || { echo "no SHA256SUMS here (run build.sh first)"; exit 1; }
sha256sum -c SHA256SUMS || { echo "SHA256SUMS does not match the files here"; exit 1; }
rm -f SHA256SUMS.asc
gpg --local-user "$K" --armor --detach-sign --output SHA256SUMS.asc SHA256SUMS
st=$(gpg --status-fd 1 --verify SHA256SUMS.asc SHA256SUMS 2>/dev/null) || true
grep -qE "^\[GNUPG:\] VALIDSIG .* ${K^^}$" <<<"$st" || { echo "the new signature does not verify with $K"; rm -f SHA256SUMS.asc; exit 1; }
grep -qE '^\[GNUPG:\] (EXPKEYSIG|REVKEYSIG|EXPSIG)' <<<"$st" && { echo "the key $K is expired or revoked"; rm -f SHA256SUMS.asc; exit 1; }
echo "SHA256SUMS.asc written and verified with $K"
