#!/bin/bash
# Prestium 2.1: Kleopatra's self-test runs "gpgconf --list-options <component>" for scdaemon; when the
# scdaemon binary is missing that fails ("probably not installed") and the test reports Failed.
# scdaemon is only Suggested by gpg-agent and the image is built with --apt-recommends false, so it must
# be listed explicitly. Optional runtime part: with SCDAEMON=/path/to/scdaemon (e.g. from the .deb),
# check that it answers the query gpgconf makes.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
L=$R/config/package-lists
grep -hqx kleopatra "$L"/*.list.chroot && ok "kleopatra installed" || bad "kleopatra not in the package lists"
grep -hqx scdaemon "$L"/*.list.chroot && ok "scdaemon installed explicitly" || bad "scdaemon missing (Kleopatra self-test fails)"
grep -hqx pcscd "$L"/*.list.chroot && ok "pcscd installed" || bad "pcscd missing"
grep -q -- '--apt-recommends false' "$R/auto/config" && ok "recommends off (so scdaemon must be explicit)" || echo "NOTE recommends no longer off"
S=${SCDAEMON:-}
if [ -n "$S" ] && [ -x "$S" ]; then
  G=$(mktemp -d); trap 'rm -rf "$G"' EXIT
  out=$(GNUPGHOME=$G "$S" --gpgconf-list 2>&1) && printf '%s\n' "$out" | grep -q '^pcsc-driver:' \
    && ok "scdaemon --gpgconf-list answers (what Kleopatra's check needs)" || bad "scdaemon --gpgconf-list: $out"
else echo "SKIP runtime check (set SCDAEMON=)"; fi
[ $fail = 0 ] && echo "kleopatra selftest: OK"; exit $fail
