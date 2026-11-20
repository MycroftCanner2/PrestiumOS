#!/bin/bash
# 2.1: Feather and i2pd come from GitHub releases.
#   - Feather: zip and .asc from github.com/feather-wallet/feather (tag = the version), always checked
#     with sigok against FEATHER_KEY; the newest release unless pinned (tests/test_feather_latest.sh), and
#     a pinned FEATHER_VERSION is still checked against FEATHER_SHA256
#   - i2pd: PurpleI2P's trixie amd64 .deb from github.com/PurpleI2P/i2pd, pinned by SHA-256 in
#     versions.sh (no signature exists, and none is claimed), checked for package/version/arch, staged as
#     i2pd.deb + i2pd.version and re-checked with the other staged files; hook 0005 checks it again and
#     installs it with apt (dependencies from Debian), before hook 0100 moves the i2pd user to 2000
#   - the repo.i2pd.xyz apt repository is gone: no list, key, keyring, origin pin, perms entry or package
#     list entry; Debian's own i2pd gets priority -1
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
F=$R/scripts/fetch-thirdparty.sh; V=$R/thirdparty/versions.sh; I=$R/config/includes.chroot
H=$R/config/hooks/live/0005-prestium-i2pd.hook.chroot
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

## Feather
grep -qxF 'get https://github.com/feather-wallet/feather/releases/download/$FEATHER_VERSION/$FEF $FEF' "$F" \
  && grep -qxF 'get https://github.com/feather-wallet/feather/releases/download/$FEATHER_VERSION/$FEF.asc $FEF.asc' "$F" \
  && ok "Feather zip and .asc from GitHub releases" || bad "Feather URLs"
grep -qxF 'sigok "$FEW/$FEF.asc" "$FEW/$FEF" "$FEATHER_KEY" "$K/feather.asc"' "$F" \
  && grep -qxF '  pin FEATHER "$FEW/$FEF" "$FEATHER_SHA256"' "$F" \
  && ok "Feather: signature (FEATHER_KEY) always checked; a pinned release also against FEATHER_SHA256" || bad "Feather checks changed"
grep -q 'featherwallet\.org/files' "$F" "$V" "$R/BUILDING.md" && bad "featherwallet.org download still referenced" || ok "no featherwallet.org download"

## i2pd: pin and fetch
# shellcheck source=../thirdparty/versions.sh
( . "$V"; [ "$I2PD_VERSION" = 3.0.0 ] && [ "$I2PD_DEB_VERSION" = 3.0.0-1trixie1 ] && echo "$I2PD_SHA256" | grep -qxE '[0-9a-f]{64}' ) \
  && ok "versions.sh pins i2pd 3.0.0-1trixie1 by SHA-256" || bad "versions.sh i2pd pin"
grep -qxF 'I2PDF=i2pd_${I2PD_DEB_VERSION}_amd64.deb' "$F" \
  && grep -qxF 'get https://github.com/PurpleI2P/i2pd/releases/download/$I2PD_VERSION/$I2PDF $I2PDF' "$F" \
  && ok "i2pd .deb from PurpleI2P's GitHub releases" || bad "i2pd URL"
grep -qxF 'pin I2PD "$I2W/$I2PDF" "$I2PD_SHA256"' "$F" && ok "i2pd .deb checked against the pinned SHA-256 (--repin prints it)" || bad "no i2pd pin check"
grep -q 'no detached OpenPGP signature for the .deb, so there is NO signature' "$F" && ok "fetch-thirdparty.sh says the pin is the only trust anchor" || bad "trust-anchor comment"
grep -qE 'sigok[^#]*I2PD' "$F" && bad "a signature check is claimed for i2pd" || ok "no signature check claimed for i2pd"
grep -q 'Package: i2pd Version: $I2PD_DEB_VERSION Architecture: amd64 ' "$F" && ok "package, version and architecture checked" || bad "control fields not checked"
grep -qF '"i2pd.deb $I2PD_SHA256"' "$F" && grep -qxF 'cp "$I2W/$I2PDF" "$S/i2pd.deb"; echo "$I2PD_DEB_VERSION $I2PD_SHA256" > "$S/i2pd.version"' "$F" \
  && ok "staged as i2pd.deb + i2pd.version and re-checked after staging" || bad "staging"
pinline=$(grep -n '^pin I2PD ' "$F" | cut -d: -f1); exitline=$(grep -n '^\[ "\$REPIN" = 1 \] && exit 0$' "$F" | cut -d: -f1)
[ -n "$pinline" ] && [ -n "$exitline" ] && [ "$pinline" -lt "$exitline" ] && ok "--repin reaches the i2pd pin before it exits" || bad "--repin flow"
grep -q 'PurpleI2P publishes no detached signature' "$R/BUILDING.md" && ok "BUILDING.md: SHA-256 pin is the trust anchor" || bad "BUILDING.md trust anchor"

## the apt repository is gone
for f in config/archives/prestium-i2pd.list.chroot config/archives/prestium-i2pd.key.chroot \
         config/includes.chroot/usr/share/prestium/build/apt/prestium-i2pd.list config/includes.chroot/usr/share/keyrings/purplei2p.gpg; do
  [ ! -e "$R/$f" ] && ok "removed: $f" || bad "still there: $f"; done
left=$(git -C "$R" grep -nI -e 'repo\.i2pd\.xyz' -e 'purplei2p' -- . ':!CHANGELOG.md' ':!tests/test_i2pd_deb.sh' | head -5)
[ -z "$left" ] && ok "nothing references repo.i2pd.xyz or the purplei2p keyring" || bad "left: $left"
grep -qx i2pd "$R"/config/package-lists/*.list.chroot && bad "i2pd still in a package list (Debian's would be installed)" || ok "i2pd not in the package lists"
for p in "$R/config/archives/prestium-thirdparty.pref.chroot" "$I/etc/apt/preferences.d/prestium-thirdparty"; do
  awk 'BEGIN{RS=""} /Package: i2pd\nPin: release o=Debian\nPin-Priority: -1/{f=1} END{exit !f}' "$p" \
    && ok "${p#"$R"/}: Debian's i2pd never installed" || bad "${p#"$R"/}: no -1 pin for Debian's i2pd"; done
cmp -s "$R/config/archives/prestium-thirdparty.pref.chroot" "$I/etc/apt/preferences.d/prestium-thirdparty" && ok "build-time and image pins identical" || bad "pin files differ"

## hook 0005 on a fake staging tree (real dpkg-deb, stub apt-get/dpkg-query)
[ -x "$H" ] && sh -n "$H" && ok "hook 0005 present" || bad "hook 0005 missing"
printf '%s\n' 0001-prestium-build-dns.hook.chroot "$(basename "$H")" 0010-prestium-optional-packages.hook.chroot | LC_ALL=C sort -c 2>/dev/null && ok "hook 0005 runs after the build resolver and before 0100 (i2pd user to 2000)" || bad "hook order"
if command -v dpkg-deb >/dev/null; then
  mk(){ # dir pkg version arch
    mkdir -p "$T/p/DEBIAN"; printf 'Package: %s\nVersion: %s\nArchitecture: %s\nMaintainer: t <t@t>\nDescription: t\n' "$2" "$3" "$4" > "$T/p/DEBIAN/control"
    dpkg-deb -b --root-owner-group "$T/p" "$1/i2pd.deb" >/dev/null 2>&1; rm -rf "$T/p"; }
  mkdir -p "$T/bin"
  printf '#!/bin/sh\necho "$*" >> "$T_LOG"; mkdir -p "$PRESTIUM_HOOK_ROOT/etc/i2pd"; : > "$PRESTIUM_HOOK_ROOT/etc/i2pd/i2pd.conf.dpkg-dist"; echo "${INSTALLED:-}" > "$T_STATE"\n' > "$T/bin/apt-get"
  printf '#!/bin/sh\ncat "$T_STATE" 2>/dev/null\n' > "$T/bin/dpkg-query"
  chmod +x "$T/bin/"*
  run(){ # root -> rc
    rm -f "$T/log" "$T/state"
    PATH="$T/bin:$PATH" T_LOG="$T/log" T_STATE="$T/state" PRESTIUM_HOOK_ROOT="$1" INSTALLED="${INST:-3.0.0-1trixie1}" sh "$H" >/dev/null 2>&1; }
  stage(){ # name pkg version arch [hash]
    local r=$T/$1 s; s=$r/usr/src/prestium-thirdparty; mkdir -p "$s"; mk "$s" "$2" "$3" "$4"
    echo "3.0.0-1trixie1 ${5:-$(sha256sum "$s/i2pd.deb" | cut -c1-64)}" > "$s/i2pd.version"; echo "$r"; }
  r=$(stage good i2pd 3.0.0-1trixie1 amd64)
  if run "$r"; then ok "hook 0005: installs the staged .deb"; else bad "hook 0005 failed on a good .deb"; fi
  grep -q -- "--force-confold.* $r/usr/src/prestium-thirdparty/i2pd.deb" "$T/log" 2>/dev/null && ok "hook 0005: apt installs the local file, keeping Prestium's config" || bad "apt call: $(cat "$T/log" 2>/dev/null)"
  [ ! -e "$r/etc/i2pd/i2pd.conf.dpkg-dist" ] && ok "hook 0005: package's config copy removed" || bad ".dpkg-dist left"
  r=$(stage badhash i2pd 3.0.0-1trixie1 amd64 0000000000000000000000000000000000000000000000000000000000000000)
  run "$r" && bad "hook 0005 accepted a .deb with the wrong SHA-256" || { [ ! -e "$T/log" ] && ok "hook 0005: wrong SHA-256 stops before apt" || bad "apt ran on a bad hash"; }
  r=$(stage badver i2pd 2.56.0-1 amd64); run "$r" && bad "hook 0005 accepted another version" || ok "hook 0005: another version stops"
  r=$(stage badpkg notI2pd 3.0.0-1trixie1 amd64); run "$r" && bad "hook 0005 accepted another package" || ok "hook 0005: another package stops"
  r=$(stage badarch i2pd 3.0.0-1trixie1 i386); run "$r" && bad "hook 0005 accepted another architecture" || ok "hook 0005: another architecture stops"
  r=$(stage notinst i2pd 3.0.0-1trixie1 amd64); INST=2.56.0-1 run "$r" && bad "hook 0005 passed with the wrong version installed" || ok "hook 0005: checks the installed version"
  run "$T/empty" && bad "hook 0005 ran without a staged .deb" || ok "hook 0005: missing .deb stops"
else echo "SKIP hook 0005 run (no dpkg-deb)"; fi

[ $fail = 0 ] && echo "i2pd deb: OK"; exit $fail
