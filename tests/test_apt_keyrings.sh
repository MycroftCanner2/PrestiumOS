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
b=$(grep -n '^run_lb bootstrap$' "$B" | cut -d: -f1); c=$(grep -n '^run_lb chroot$' "$B" | cut -d: -f1)
i=$(grep -n 'install -m 644 config/apt-keyrings/prestium-tor.gpg config/apt-keyrings/prestium-librewolf.gpg chroot/etc/apt/keyrings/' "$B" | cut -d: -f1)
[ -n "$b" ] && [ -n "$c" ] && [ -n "$i" ] && [ "$b" -lt "$i" ] && [ "$i" -lt "$c" ] && ok "build.sh installs the keyrings between bootstrap and chroot" \
  || bad "build.sh: keyrings not installed between lb bootstrap and lb chroot"
grep -q 'a Prestium key is in trusted.gpg.d' "$B" && ok "build.sh fails on a Prestium key in trusted.gpg.d" || bad "no trusted.gpg.d check"
# the keys themselves: binary OpenPGP certificates, the same fingerprints as before (moved, not changed)
if command -v gpg >/dev/null; then
  fp(){ gpg --batch --quiet --with-colons --show-keys "$1" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}'; }
  [ "$(fp "$R/config/apt-keyrings/prestium-tor.gpg")" = A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 ] && ok "Tor Project archive key A3C4F0F9..." || bad "Tor Project key fingerprint"
  [ "$(fp "$R/config/apt-keyrings/prestium-librewolf.gpg")" = 662E3CDD6FE329002D0CA5BB40339DD82B12EF16 ] && ok "LibreWolf key 662E3CDD..." || bad "LibreWolf key fingerprint"
else echo "SKIP gpg missing (fingerprints)"; fi
exit $fail
