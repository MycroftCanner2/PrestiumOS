#!/bin/bash
# Security review F-06: the build-time keys of the third-party apt repositories (Tor Project,
# LibreWolf) are trusted for their own source only. live-build copies config/archives/*.key* into
# /etc/apt/trusted.gpg.d, where apt trusts a key for every source (Debian's too), so there are none
# there: the keys are in config/apt-keyrings/, build.sh installs them in chroot/etc/apt/keyrings/
# after "lb bootstrap", and every build-time list names its keyring with signed-by.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
ls "$R"/config/archives/*.key* >/dev/null 2>&1 && bad "config/archives has a .key file (live-build puts it in trusted.gpg.d)" \
  || ok "no key in config/archives"
for f in "$R"/config/archives/*.list.chroot "$R"/config/archives/*.sources.chroot; do
  [ -e "$f" ] || continue; n=$(basename "$f")
  grep -vE '^\s*(#|$)' "$f" | while read -r l; do
    k=$(printf '%s\n' "$l" | sed -n 's/.*signed-by=\([^] ]*\).*/\1/p')
    case $k in
      /etc/apt/keyrings/*.gpg) [ -f "$R/config/apt-keyrings/$(basename "$k")" ] && echo "OK   $n: $k" || echo "FAIL $n: $k not in config/apt-keyrings";;
      *) echo "FAIL $n: signed-by '$k' is not a keyring in /etc/apt/keyrings";;
    esac
  done
done | tee "$R/.apt-keyrings.out"; grep -q '^FAIL' "$R/.apt-keyrings.out" && fail=1; rm -f "$R/.apt-keyrings.out"
B=$R/build.sh
# PRE-5: every keyring a build-time list names must exist in every chroot live-build runs
# "chroot_archives chroot install" (copy config/archives/*.list.chroot, apt-get update) in: the image
# chroot ("lb chroot") and the tool chroots of "lb installer" (installer_chroot) and "lb binary"
# (binary_chroot), which are fresh copies of cache/bootstrap. Run build.sh's own keyring block on a
# stand-in tree, make the tool chroots the way live-build does, and look for each signed-by file.
b=$(grep -n '^run_lb bootstrap$' "$B" | cut -d: -f1); c=$(grep -n '^run_lb chroot$' "$B" | cut -d: -f1)
in=$(grep -n '^run_lb installer$' "$B" | cut -d: -f1); bi=$(grep -n '^run_lb binary$' "$B" | cut -d: -f1)
k=$(grep -n '^for root in chroot cache/bootstrap; do$' "$B" | cut -d: -f1)
[ -n "$b" ] && [ -n "$c" ] && [ -n "$k" ] && [ -n "$in" ] && [ -n "$bi" ] && [ "$b" -lt "$k" ] && [ "$k" -lt "$c" ] && [ "$c" -lt "$in" ] && [ "$in" -lt "$bi" ] \
  && ok "build.sh installs the keyrings (image chroot and bootstrap cache) between lb bootstrap and lb chroot" \
  || bad "build.sh: no keyring block for chroot and cache/bootstrap between lb bootstrap and lb chroot"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/config" "$T/chroot/etc/apt/trusted.gpg.d" "$T/cache/bootstrap/etc/apt/trusted.gpg.d"
cp -r "$R/config/apt-keyrings" "$T/config/"
touch "$T/cache/bootstrap/etc/apt/trusted.gpg.d/prestium-tor.key.chroot.gpg"   # a stale pre-F-06 copy
if [ -n "$k" ]; then
  awk -v s="$k" 'NR>=s{print} NR>s && /^done$/{exit}' "$B" > "$T/block.sh"
  (cd "$T" && bash -eu block.sh) || bad "build.sh's keyring block failed on a stand-in tree"
fi
cp -a "$T/cache/bootstrap" "$T/installer-tool"     # installer_chroot: cp -a cache/bootstrap chroot
cp -a "$T/cache/bootstrap" "$T/binary-tool"        # binary_chroot (bootstrap cached): the same
for f in "$R"/config/archives/*.list.chroot "$R"/config/archives/*.sources.chroot; do
  [ -e "$f" ] || continue; n=$(basename "$f")
  for key in $(grep -vE '^\s*(#|$)' "$f" | sed -n 's/.*signed-by=\([^] ]*\).*/\1/p'); do
    for st in chroot:"lb chroot" installer-tool:"lb installer" binary-tool:"lb binary"; do
      d=${st%%:*}; [ -s "$T/$d$key" ] && cmp -s "$T/$d$key" "$R/config/apt-keyrings/$(basename "$key")" \
        && ok "$n: $key there for ${st#*:}" || bad "$n: $key missing when ${st#*:} runs apt-get update"
    done
  done
done
for d in chroot installer-tool binary-tool; do
  ls "$T/$d"/etc/apt/trusted.gpg.d/prestium-* >/dev/null 2>&1 && bad "$d: a Prestium key in trusted.gpg.d" || ok "$d: no Prestium key in trusted.gpg.d"
done
grep -q 'cache/bootstrap lacks the apt keyrings' "$B" && ok "build.sh checks the bootstrap cache before lb installer" || bad "no bootstrap-cache check before lb installer"
grep -q 'a Prestium key is in trusted.gpg.d' "$B" && ok "build.sh fails on a Prestium key in trusted.gpg.d" || bad "no trusted.gpg.d check"
# the keys themselves: binary OpenPGP certificates, the same fingerprints as before (moved, not changed)
if command -v gpg >/dev/null; then
  fp(){ gpg --batch --quiet --with-colons --show-keys "$1" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}'; }
  [ "$(fp "$R/config/apt-keyrings/prestium-tor.gpg")" = A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 ] && ok "Tor Project archive key A3C4F0F9..." || bad "Tor Project key fingerprint"
  [ "$(fp "$R/config/apt-keyrings/prestium-librewolf.gpg")" = 662E3CDD6FE329002D0CA5BB40339DD82B12EF16 ] && ok "LibreWolf key 662E3CDD..." || bad "LibreWolf key fingerprint"
else echo "SKIP gpg missing (fingerprints)"; fi
exit $fail
