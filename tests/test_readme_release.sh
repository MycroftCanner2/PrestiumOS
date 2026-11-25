#!/bin/bash
# Security review F-11: the README points at the torrent that is in the repository (and the torrent
# names that ISO), and the release-key fingerprint is either published in full or plainly marked as not
# published, never a short ID.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
M=$R/README.md
refs=$(grep -oE 'Prestium-[0-9.]*(-quick_qubes)?-amd64\.iso\.torrent' "$M" | sort -u)
[ -n "$refs" ] && ok "README names a torrent" || bad "README names no torrent"
for t in $refs; do [ -f "$R/$t" ] && ok "README's $t is in the repository" || bad "README names $t, which is not in the repository"; done
for f in "$R"/*.torrent; do [ -f "$f" ] || continue; b=${f##*/}
  grep -qF "$b" "$M" && ok "$b is described in the README" || bad "$b is not mentioned in the README"
  n=${b%.torrent}
  python3 - "$f" "$n" <<'PY' && ok "$b: its info name is $n" || bad "$b: info name is not $n"
import sys
d = open(sys.argv[1], "rb").read(); n = sys.argv[2].encode()
sys.exit(0 if (b"4:name%d:%s" % (len(n), n)) in d else 1)
PY
done
l=$(grep -E '^ *Release key fingerprint:' "$M")
case $l in
  *"*not yet published*") ok "release key: marked as not yet published" ;;
  *) f=$(sed -E 's/.*fingerprint: *`?([0-9A-F ]+)`?.*/\1/' <<<"$l" | tr -d ' ')
     [[ $f =~ ^[0-9A-F]{40}$ ]] && ok "release key: full fingerprint $f" || bad "release key line is neither a full fingerprint nor 'not yet published': $l" ;;
esac
grep -q 'gpg --verify SHA256SUMS.asc SHA256SUMS' "$M" && ok "README: how to verify SHA256SUMS.asc" || bad "README: no verify step"
grep -q 'FINGERPRINT (40 hex digits)' "$R/scripts/sign-release.sh" && ok "sign-release.sh takes a full fingerprint" || bad "sign-release.sh fingerprint check"
exit $fail
