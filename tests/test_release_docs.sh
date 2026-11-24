#!/bin/bash
# Security review F-12, F-13, F-14: the release checklist (raise the version floors, pin for release
# builds, re-pin i2pd with a second check and a look at its maintainer scripts) and the documented
# limits are in the docs, and the floors are well-formed versions.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
B=$R/BUILDING.md; V=$R/thirdparty/versions.sh; C=$R/CHANGELOG.md
grep -q '^### Release checklist (security review F-12, F-13)' "$B" && ok "BUILDING.md: release checklist" || bad "no release checklist"
grep -q 'Raise `TB_MIN_VERSION` and `FEATHER_MIN_VERSION`' "$B" && ok "checklist: raise the floors" || bad "checklist: floors"
grep -q 'dpkg-deb -e i2pd_' "$B" && grep -q 'asset digest' "$B" && ok "checklist: i2pd digest and maintainer scripts" || bad "checklist: i2pd"
for k in TB_MIN_VERSION FEATHER_MIN_VERSION; do
  grep -Eq "^$k=[0-9]+(\.[0-9]+)+ " "$V" && ok "$k is a plain version" || bad "$k malformed"; done
grep -q 'rdinit=' "$C" && grep -q 'F-14' "$C" && ok "CHANGELOG: kernel-consumed options before the guard (F-14)" || bad "F-14 limit not documented"
grep -q '^### Kernel: why Debian 13' "$B" && ok "BUILDING.md: kernel decision recorded" || bad "kernel decision"
exit $fail
