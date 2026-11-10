#!/bin/bash
# Prestium 2.0: download and verify the third-party software that is not in Debian, then stage it
# for the chroot hooks in config/includes.chroot/usr/src/prestium-thirdparty/ (not committed).
#   scripts/fetch-thirdparty.sh            verify signature + pinned SHA-256 (fails on any mismatch)
#   scripts/fetch-thirdparty.sh --repin    verify signature only, print the SHA-256 values to pin
#   2.1: Tor Browser is the newest signed release unless pinned (thirdparty/versions.sh, scripts/tb-latest.sh)
#   It also stages a signature-checked I2P reseed file (StormyCloud su3; a verified download under 24 h old is reused) into config/includes.chroot/var/lib/i2pd/.
# Needs: curl gpg gpgv git sha256sum unzip npm python3 openssl (the host's npm only runs "npm ci --ignore-scripts": pure JS,
# architecture-independent). Every registry tarball is checked against the lockfile's sha512 integrity; the one git
# dependency (irc-framework, pinned to a commit, no integrity in the lockfile) is installed from a "git archive" tarball
# of IRC_FRAMEWORK_COMMIT with a pinned SHA-256, and checked file by file against a git checkout of that commit.
set -euo pipefail
TOP=$(cd "$(dirname "$0")/.." && pwd)
. "$TOP/thirdparty/versions.sh"
REPIN=0; [ "${1:-}" = "--repin" ] && REPIN=1
C=${PRESTIUM_CACHE:-$TOP/cache/thirdparty}; mkdir -p "$C"
# 2.0 r7: the cache can be shared between trees; only one fetch may write it at a time
exec 8>"$C/.fetch.lock"
flock -w 3600 8 || { echo "ERROR: another fetch-thirdparty.sh holds $C/.fetch.lock"; exit 1; }
S=$TOP/config/includes.chroot/usr/src/prestium-thirdparty
export GNUPGHOME=$(mktemp -d); trap 'rm -rf "$GNUPGHOME"' EXIT
# 2.1 (security audit): no shared keyring; each signature is checked against its own publisher's key
# only (sigok imports it into a throw-away home), and an import failure stops the build
K=$TOP/thirdparty/keys
get(){ [ -s "$C/$2" ] || { curl -sfL --proto =https --proto-redir =https --retry 3 -m 1800 -o "$C/$2.part" "$1" && mv "$C/$2.part" "$C/$2"; }; }
sha(){ sha256sum "$1" | cut -c1-64; }
pin(){ # name file expected
  pinhash "$1" "$(sha "$2")" "$3"; }
pinhash(){ # name sha256 expected
  local got=$2
  if [ "$REPIN" = 1 ]; then echo "PIN $1 $got"; return 0; fi
  [ -n "$3" ] || { echo "ERROR: no SHA-256 pinned for $1 (run --repin)"; exit 1; }
  [ "$got" = "$3" ] || { echo "ERROR: $1 SHA-256 $got != pinned $3"; exit 1; }
  echo "OK $1 $got"; }
treehash(){ # sha256 over package.json, package-lock.json, .npmrc and every file under node_modules
  (cd "$1" && { find node_modules -type f -print0; printf '%s\0' package.json package-lock.json .npmrc; } \
    | LC_ALL=C sort -z | xargs -0 sha256sum) | sha256sum | cut -c1-64; }
. "$TOP/scripts/sigcheck.sh"
sigok(){ # sigfile datafile fpr keyfile (detached signatures only; a keyring with only that key)
  local h st; h=$(mktemp -d "$GNUPGHOME/key.XXXXXX")
  gpg --homedir "$h" --batch -q --import "$4" || { echo "ERROR: cannot import the key $4"; exit 1; }
  st=$(gpg --homedir "$h" --batch --status-fd 1 --verify "$1" "$2" 2>/dev/null) || true
  gpgconf --homedir "$h" --kill all >/dev/null 2>&1; rm -rf "$h"
  sigstatus_detached_ok "$2" "$st" "$3" || exit 1; }

# Tor Browser (2.1: the newest release unless versions.sh or PRESTIUM_TB_VERSION pins one)
. "$TOP/scripts/tb-latest.sh"
if [ "$TB_VERSION" = latest ]; then
  TB_VERSION=$(tb_latest) || exit 1
  TB_LATEST=1; echo "Tor Browser: newest release is $TB_VERSION"
else
  TB_LATEST=0
  tb_version_ok "$TB_VERSION" || { echo "ERROR: bad TB_VERSION '$TB_VERSION'"; exit 1; }
  tb_version_ge "$TB_VERSION" "$TB_MIN_VERSION" || { echo "ERROR: TB_VERSION $TB_VERSION is older than TB_MIN_VERSION $TB_MIN_VERSION"; exit 1; }
fi
TBF=tor-browser-linux-x86_64-$TB_VERSION.tar.xz
get https://dist.torproject.org/torbrowser/$TB_VERSION/$TBF $TBF
get https://dist.torproject.org/torbrowser/$TB_VERSION/$TBF.asc $TBF.asc
# 2.1 audit: verify, hash and stage one private copy (the shared cache can change between reads)
TBW=$GNUPGHOME/tb; mkdir -m 700 "$TBW"; cp "$C/$TBF" "$TBW/$TBF"; cp "$C/$TBF.asc" "$TBW/$TBF.asc"
sigok "$TBW/$TBF.asc" "$TBW/$TBF" "$TB_KEY" "$K/torbrowser.asc"
if [ "$TB_LATEST" = 1 ]; then
  # no pin to compare with: the signature by TB_KEY (checked above) is the trust anchor; record what was used
  TB_SHA256=$(sha "$TBW/$TBF"); echo "OK TB $TB_SHA256 (Tor Browser $TB_VERSION, signature verified, not pinned)"
else
  pin TB "$TBW/$TBF" "$TB_SHA256"
fi
# the signature does not cover the file name: the tarball's own version must be the one asked for
TB_GOT=$(tb_tarball_version "$TBW/$TBF") \
  || { echo "ERROR: $TBF has no release-channel linux-x86_64 tbb_version.json"; exit 1; }
[ "$TB_GOT" = "$TB_VERSION" ] || { echo "ERROR: $TBF contains Tor Browser $TB_GOT, not $TB_VERSION"; exit 1; }

# Firefox (local-only browser for Prestium's own pages)
FFF=firefox-$FF_VERSION.tar.xz
get https://archive.mozilla.org/pub/firefox/releases/$FF_VERSION/SHA256SUMS ff-$FF_VERSION.SHA256SUMS
get https://archive.mozilla.org/pub/firefox/releases/$FF_VERSION/SHA256SUMS.asc ff-$FF_VERSION.SHA256SUMS.asc
get https://archive.mozilla.org/pub/firefox/releases/$FF_VERSION/linux-x86_64/en-US/$FFF $FFF
sigok "$C/ff-$FF_VERSION.SHA256SUMS.asc" "$C/ff-$FF_VERSION.SHA256SUMS" "$FF_KEY" "$K/mozilla.asc"
grep -q "^$(sha "$C/$FFF")  linux-x86_64/en-US/$FFF\$" "$C/ff-$FF_VERSION.SHA256SUMS" || { echo "ERROR: Firefox not in signed SHA256SUMS"; exit 1; }
pin FF "$C/$FFF" "$FF_SHA256"

# Node.js (runtime for The Lounge)
NF=node-$NODE_VERSION-linux-x64.tar.xz
get https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt.asc node-$NODE_VERSION.SHASUMS256.txt.asc
get https://nodejs.org/dist/$NODE_VERSION/$NF $NF
# gpgv exits 0 for a good signature by an expired key too: apply the same status-line policy. 2.1
# (security audit): the keybox holds every past releaser's key; only the current releasers'
# primary keys (NODE_KEYS in versions.sh, from the Node.js README) may have signed
rm -f "$C/node-$NODE_VERSION.SHASUMS256.txt.tmp"
NST=$(gpgv --status-fd 1 --keyring "$TOP/thirdparty/keys/node-release-keys.kbx" --output "$C/node-$NODE_VERSION.SHASUMS256.txt.tmp" \
  "$C/node-$NODE_VERSION.SHASUMS256.txt.asc" 2>/dev/null) || true
sigstatus_oneof_ok "Node SHASUMS256.txt" "$NST" "$NODE_KEYS" || { rm -f "$C/node-$NODE_VERSION.SHASUMS256.txt.tmp"; exit 1; }
mv -f "$C/node-$NODE_VERSION.SHASUMS256.txt.tmp" "$C/node-$NODE_VERSION.SHASUMS256.txt"
grep -q "^$(sha "$C/$NF")  $NF\$" "$C/node-$NODE_VERSION.SHASUMS256.txt" || { echo "ERROR: Node not in signed SHASUMS"; exit 1; }
pin NODE "$C/$NF" "$NODE_SHA256"

# Feather (Monero wallet)
FEF=feather-$FEATHER_VERSION-linux.zip
get https://featherwallet.org/files/releases/linux/$FEF $FEF
get https://featherwallet.org/files/releases/linux/$FEF.asc $FEF.asc
sigok "$C/$FEF.asc" "$C/$FEF" "$FEATHER_KEY" "$K/feather.asc"; pin FEATHER "$C/$FEF" "$FEATHER_SHA256"

# irc-framework (a git dependency of The Lounge, commit-pinned, no integrity in the lockfile). 2.1: npm
# never sees the git URL: packing a git dependency runs its "prepare" script (babel + webpack, caret-ranged
# devDependencies resolved from the registry that day) on the build host, even with --ignore-scripts.
# Instead the pinned commit is exported with "git archive" (no lifecycle scripts, the files npm would
# ship: IRC_FRAMEWORK_FILES), its SHA-256 is pinned, and npm ci installs that tarball.
grep -q "irc-framework.git#$IRC_FRAMEWORK_COMMIT\"" "$TOP/thirdparty/thelounge/package-lock.json" \
  || { echo "ERROR: package-lock.json does not resolve irc-framework to $IRC_FRAMEWORK_COMMIT"; exit 1; }
IG=$C/irc-framework-src
if [ ! -d "$IG/.git" ]; then rm -rf "$IG"; git clone -q https://github.com/kiwiirc/irc-framework.git "$IG"; fi
git -C "$IG" cat-file -e "$IRC_FRAMEWORK_COMMIT^{commit}" 2>/dev/null || git -C "$IG" fetch -q origin
git -C "$IG" -c advice.detachedHead=false checkout -q -f "$IRC_FRAMEWORK_COMMIT" && git -C "$IG" clean -qfdx
[ "$(git -C "$IG" rev-parse HEAD)" = "$IRC_FRAMEWORK_COMMIT" ] || { echo "ERROR: irc-framework checkout is not $IRC_FRAMEWORK_COMMIT"; exit 1; }
IT=$C/irc-framework-$IRC_FRAMEWORK_COMMIT.tar
# shellcheck disable=SC2086 # IRC_FRAMEWORK_FILES is a list of paths
git -C "$IG" archive --format=tar --prefix=package/ "$IRC_FRAMEWORK_COMMIT" $IRC_FRAMEWORK_FILES > "$IT.tmp" && mv -f "$IT.tmp" "$IT"
pin IRC_FRAMEWORK_TAR "$IT" "$IRC_FRAMEWORK_TAR_SHA256"

# The Lounge: npm ci from the committed lockfile (registry tarballs checked against their sha512 integrity;
# .npmrc: ignore-scripts, save-exact, min-release-age=7 for lockfile regeneration, see BUILDING.md)
L=$C/thelounge-$THELOUNGE_VERSION-r21   # r21: new cache name (older trees were built with irc-framework's prepare)
if [ ! -s "$L/.done" ]; then   # 2.0 r7: empty .done (older builds) = no recorded tree hash, install again
  rm -rf "$L"; mkdir -p "$L"
  cp "$TOP/thirdparty/thelounge/package.json" "$TOP/thirdparty/thelounge/package-lock.json" "$TOP/thirdparty/thelounge/.npmrc" "$L/"
  cp "$IT" "$L/irc-framework.tar"
  [ "$(sha "$L/irc-framework.tar")" = "$IRC_FRAMEWORK_TAR_SHA256" ] || [ "$REPIN" = 1 ] \
    || { echo "ERROR: staged irc-framework tarball does not match its pinned SHA-256"; exit 1; }
  # working copies only: lockfile entry -> file:irc-framework.tar + its sha512, package.json override
  python3 "$TOP/scripts/npm-local-tarball.py" "$L" irc-framework irc-framework.tar >/dev/null
  # --git=false: if npm still wanted the git URL, the install fails instead of cloning and packing it
  ( cd "$L" && npm ci --omit=dev --omit=optional --ignore-scripts --git=false --no-audit --no-fund >/dev/null )
  grep -q "\"version\": \"$THELOUNGE_VERSION\"" "$L/node_modules/thelounge/package.json" || { echo "ERROR: thelounge version"; exit 1; }
  # ship the committed manifest and lockfile, not the working copies
  cp "$TOP/thirdparty/thelounge/package.json" "$TOP/thirdparty/thelounge/package-lock.json" "$L/"
  rm -f "$L/irc-framework.tar"
  treehash "$L" > "$L/.done"
fi
# 2.0 r7: a cached install is reused only if its whole tree still matches the hash recorded right
# after the lockfile-verified npm ci (catches cache corruption or later edits; .done itself is
# not a signature: a cache writer could rewrite both, so keep the cache on storage only the builder writes)
[ "$(treehash "$L")" = "$(cat "$L/.done")" ] || { echo "ERROR: cached The Lounge tree changed since npm ci (delete $L)"; exit 1; }
# 2.0 r13: check every installed irc-framework file against the git checkout of the pinned commit: same
# paths, same bytes, package.json equal as JSON, nothing that is not in the commit, and no dist/ (the
# browser bundle "prepare" builds; 2.1: never built, so its presence means prepare ran). Every build.
IRCF=$L/node_modules/irc-framework
[ -d "$IRCF" ] && [ -z "$(find "$IRCF" ! -type f ! -type d | head -1)" ] || { echo "ERROR: irc-framework tree missing or has non-regular files"; exit 1; }
[ ! -e "$IRCF/dist" ] || { echo "ERROR: irc-framework/dist present: its prepare script ran (delete $L)"; exit 1; }
[ -f "$IRCF/src/index.js" ] || { echo "ERROR: irc-framework src/index.js missing"; exit 1; }
( cd "$IRCF" && find . -type f -print0 ) | while IFS= read -r -d '' f; do
  f=${f#./}
  if [ "$f" = package.json ]; then
    python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1])) != json.load(open(sys.argv[2])))' "$IRCF/$f" "$IG/$f" \
      || { echo "ERROR: irc-framework package.json differs from commit $IRC_FRAMEWORK_COMMIT"; exit 1; }
  elif [ ! -f "$IG/$f" ] || [ -L "$IG/$f" ]; then echo "ERROR: irc-framework file not in commit $IRC_FRAMEWORK_COMMIT: $f"; exit 1
  elif ! cmp -s "$IRCF/$f" "$IG/$f"; then echo "ERROR: irc-framework file differs from commit $IRC_FRAMEWORK_COMMIT: $f"; exit 1; fi
done
echo "OK IRC_FRAMEWORK $IRC_FRAMEWORK_COMMIT ($(find "$IRCF" -type f | wc -l) files match the commit)"
echo "OK THELOUNGE $THELOUNGE_VERSION (npm ci, lockfile integrity + pinned irc-framework tarball)"

# lurch source at pinned commits (submodules checked too)
LS=$C/lurch-src
# 2.0 r12: the marker sits beside the tree, not in it (an untracked .done made the clean-tree check below always fail)
if [ ! -e "$LS.done" ] || [ ! -d "$LS" ]; then
  rm -rf "$LS" "$LS.done"; git clone -q --recursive https://github.com/gkdr/lurch "$LS"
  git -C "$LS" checkout -q "$LURCH_COMMIT"; git -C "$LS" submodule -q update --init --recursive
  touch "$LS.done"
fi
[ "$(git -C "$LS" rev-parse HEAD)" = "$LURCH_COMMIT" ] && [ "$(git -C "$LS/lib/axc" rev-parse HEAD)" = "$AXC_COMMIT" ] && \
  [ "$(git -C "$LS/lib/libomemo" rev-parse HEAD)" = "$LIBOMEMO_COMMIT" ] || { echo "ERROR: lurch commits"; exit 1; }
# 2.0 r7: HEAD alone does not cover the checked-out files; the work trees must match their commits
for r in "$LS" "$LS/lib/axc" "$LS/lib/libomemo"; do
  [ -z "$(git -C "$r" status --porcelain --untracked-files=all --ignore-submodules=none)" ] \
    || { echo "ERROR: cached lurch work tree $r differs from its pinned commit (delete $LS)"; exit 1; }
done
echo "OK LURCH $LURCH_COMMIT"

[ "$REPIN" = 1 ] && exit 0

# I2P reseed file, checked every time before use: SU3 format, StormyCloud signer, RSA-4096/SHA-512
# signature against i2pd's reseed certificate (thirdparty/keys/reseed/), routerInfo entries in the zip,
# and an age limit on the signed version timestamp. i2pd.conf [reseed] file= points at it; owner i2pd
# (2000) comes from perms.txt.
# 2.0 r14: the server rate-limits per IP (HTTP 429), so rebuilds and --resume runs kept failing. The last
# verified download is kept in the cache and reused, re-verified, when it was downloaded less than
# PRESTIUM_RESEED_REUSE_HOURS ago (default 24; 0 always downloads). If a download fails, a cached copy is
# used only if its signed version is at most 3 days old. Otherwise the build stops, as before.
SU3=$TOP/config/includes.chroot/var/lib/i2pd/stormycloud-i2pseeds.su3
SU3URL=https://reseed.stormycloud.org/i2pseeds.su3
SU3C=$C/reseed/stormycloud-i2pseeds.su3; mkdir -p "$C/reseed"
SU3V="$TOP/config/includes.chroot/usr/local/lib/prestium/verify-su3"
su3ok(){ python3 "$SU3V" "$1" --max-age "$2" --signers admin@stormycloud.org,idk@stormycloud.org "$TOP/thirdparty/keys/reseed"; }
REUSE_H=${PRESTIUM_RESEED_REUSE_HOURS:-24}
case "$REUSE_H" in ''|*[!0-9]*) echo "ERROR: PRESTIUM_RESEED_REUSE_HOURS must be a whole number"; exit 1;; esac
rm -f "$SU3" "$SU3.part"
if [ "$REUSE_H" -gt 0 ] && [ -s "$SU3C" ] && [ -n "$(find "$SU3C" -mmin -$((REUSE_H * 60)))" ] && su3ok "$SU3C" 14; then
  echo "OK RESEED reusing the copy verified $(date -u -r "$SU3C" +%FT%TZ) (under ${REUSE_H}h old)"
  cp "$SU3C" "$SU3.part"
else
  # reseed servers only answer I2P's reseed user agent; curl honours Retry-After, up to 25 min in all
  if curl -sfL --proto =https --proto-redir =https --retry 8 --retry-all-errors --retry-max-time 1500 -m 300 -A "Wget/1.11.4" \
      -o "$SU3.part" "$SU3URL"; then
    su3ok "$SU3.part" 14 || { rm -f "$SU3.part"; echo "ERROR: I2P reseed file $SU3URL failed verification"; exit 1; }
    cp "$SU3.part" "$SU3C.tmp" && mv -f "$SU3C.tmp" "$SU3C"
  else
    rm -f "$SU3.part"
    if [ -s "$SU3C" ] && su3ok "$SU3C" 3; then
      echo "WARN: cannot download $SU3URL; using the cached copy verified $(date -u -r "$SU3C" +%FT%TZ) (signed under 3 days ago)"
      cp "$SU3C" "$SU3.part"
    else
      echo "ERROR: cannot download the I2P reseed file $SU3URL and no verified copy under 3 days old is cached"; exit 1
    fi
  fi
fi
su3ok "$SU3.part" 14 || { rm -f "$SU3.part"; echo "ERROR: I2P reseed file failed verification"; exit 1; }
chmod 644 "$SU3.part"; mv -f "$SU3.part" "$SU3"

# stage for the hooks
rm -rf "$S"; mkdir -p "$S"
cp "$TBW/$TBF" "$S/tor-browser.tar.xz"; echo "$TB_VERSION" > "$S/tor-browser.version"; cp "$C/$FFF" "$S/firefox.tar.xz"; cp "$C/$NF" "$S/node.tar.xz"
cp "$C/$FEF" "$S/feather.zip"; echo "$FEATHER_VERSION" > "$S/feather.version"
# 2.0 r7: re-check what was actually staged (closes the verify-then-copy gap)
for x in "tor-browser.tar.xz $TB_SHA256" "firefox.tar.xz $FF_SHA256" "node.tar.xz $NODE_SHA256" "feather.zip $FEATHER_SHA256"; do
  [ "$(sha "$S/${x%% *}")" = "${x#* }" ] || { echo "ERROR: staged ${x%% *} does not match its pinned SHA-256"; exit 1; }
done
# tar once per The Lounge version (node_modules has thousands of small files; slow on network filesystems)
LT="$C/thelounge-$THELOUNGE_VERSION.tar"
if [ ! -s "$LT" ] || [ ! -s "$LT.sha256" ] || [ "$L/.done" -nt "$LT" ]; then
  tar -C "$L" -cf "$LT.tmp" package.json package-lock.json node_modules && mv -f "$LT.tmp" "$LT"
  sha "$LT" > "$LT.sha256"
fi
cp "$LT" "$S/thelounge.tar"
[ "$(sha "$S/thelounge.tar")" = "$(cat "$LT.sha256")" ] || { echo "ERROR: cached The Lounge tar is corrupt (delete $LT)"; exit 1; }
tar -C "$LS" --exclude=.git -cf "$S/lurch-src.tar" .
echo "STAGED $S"; ls -la "$S"
