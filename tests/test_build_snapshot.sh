#!/bin/bash
# 2.1 (security audit): PRESTIUM_SNAPSHOT pins the Debian archive to snapshot.debian.org; build.sh
# sets SOURCE_DATE_EPOCH from the source commit. Runs auto/config with a stub "lb".
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
printf '#!/bin/sh\nprintf "%%s\\n" "$@" > %s/args\n' "$T" > "$T/lb"; chmod 755 "$T/lb"
PATH=$T:$PATH sh "$R/auto/config" >/dev/null 2>&1
grep -qx 'https://deb.debian.org/debian/' "$T/args" && ! grep -q snapshot "$T/args" && ok "default: deb.debian.org" || bad "default mirrors"
rm -f "$T/args"; PATH=$T:$PATH PRESTIUM_SNAPSHOT=20261110T000000Z sh "$R/auto/config" >/dev/null 2>&1
grep -qx 'https://snapshot.debian.org/archive/debian/20261110T000000Z/' "$T/args" \
  && grep -qx 'https://snapshot.debian.org/archive/debian-security/20261110T000000Z/' "$T/args" \
  && grep -qx -- '--yes -o Acquire::Check-Valid-Until=false' "$T/args" && ok "snapshot: main, security, Valid-Until off" || bad "snapshot mirrors"
rm -f "$T/args"; PATH=$T:$PATH PRESTIUM_SNAPSHOT='2026; rm -rf /' sh "$R/auto/config" >/dev/null 2>&1 && bad "bad snapshot accepted" || { [ -e "$T/args" ] && bad "lb ran" || ok "malformed snapshot refused"; }
grep -q 'SOURCE_DATE_EPOCH=$(git log -1 --format=%ct' "$R/build.sh" && grep -q '^export SOURCE_DATE_EPOCH' "$R/build.sh" && ok "build.sh: SOURCE_DATE_EPOCH from the commit" || bad "SOURCE_DATE_EPOCH"
exit $fail
