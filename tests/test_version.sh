#!/bin/bash
# Prestium 2.1.1: every place that states the version agrees with hook 0400's VERSION (os-release, and
# from there the boot menu labels): image name, ISO name, docs and the newest changelog section.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
V=$(sed -n 's/^VERSION=//p' "$R/config/hooks/live/0400-prestium-system.hook.chroot" | head -1)
[[ $V =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] && ok "hook 0400: VERSION=$V" || bad "hook 0400 VERSION '$V'"
N=$(sed -n 's/^LB_IMAGE_NAME="\(.*\)"$/\1/p' "$R/config/common")
case $N in "Prestium-$V"|"Prestium-$V-"*) ok "config/common: image name $N";; *) bad "config/common image name '$N' (version $V)";; esac
grep -qF -- "--image-name $N \\" "$R/auto/config" && ok "auto/config: --image-name $N" || bad "auto/config image name"
grep -qx "OUT=$N-amd64.iso" "$R/build.sh" && ok "build.sh writes $N-amd64.iso" || bad "build.sh OUT"
grep -qF "\`$N-amd64.iso\`" "$R/BUILDING.md" && ok "BUILDING.md names $N-amd64.iso" || bad "BUILDING.md output name"
grep -qF "*Prestium $V" "$R/README.md" && grep -qF "Prestium **$V**" "$R/README.md" && ok "README: status and boot entry say $V" || bad "README version"
h=$(grep -m1 -E '^## [0-9]' "$R/CHANGELOG.md")
[[ $h == "## $V:"* ]] && ok "CHANGELOG: newest release section is $V" || bad "CHANGELOG newest section: $h"
[ "$(grep -c -E "^## ${V}[: ]" "$R/CHANGELOG.md")" = 1 ] && ok "CHANGELOG: one $V section" || bad "CHANGELOG: $V sections"
grep -q '^## Unreleased' "$R/CHANGELOG.md" && bad "CHANGELOG still has an Unreleased section" || ok "CHANGELOG: no Unreleased section left"
exit $fail
