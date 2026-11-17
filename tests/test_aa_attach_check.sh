#!/bin/bash
# Prestium 2.1 (review: a second AppArmor profile with the same name passed the attach check):
# aa-attach-check.py on small fixture sets (tests/fixtures/aa-attach-check). It skips only the Prestium
# profile itself (same name, same file): another file that reuses the name, with any attachment or
# none, fails, and so does another name on the same program; a normal set passes. Needs apparmor_parser
# (PATH may need /usr/sbin); no root.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); F=$R/tests/fixtures/aa-attach-check
CHK=$R/config/includes.chroot/usr/share/prestium/build/aa-attach-check.py
H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin
if ! command -v apparmor_parser >/dev/null; then echo "SKIP apparmor_parser missing"; exit 0; fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
run() { # run CASE...: the Prestium profile, the unrelated one and the given fixtures; prints the output
  rm -rf "$T/aa"; mkdir -p "$T/aa"; cp "$F/usr.bin.prestium-demo" "$F/other-app" "$T/aa/"
  for c in "$@"; do cp "$F/$c" "$T/aa/"; done
  out=$(python3 -I "$CHK" "$T/aa" usr.bin.prestium-demo 2>&1); rc=$?
}
run
[ $rc -eq 0 ] && grep -q '^P: 2 profiles' <<<"$out" && ok "normal set passes ($out)" || bad "normal set: rc=$rc $out"
run dup-name-same-attach
[ $rc -ne 0 ] && grep -q '^E: profile name prestium-demo: defined by the Prestium file usr.bin.prestium-demo and by dup-name-same-attach' <<<"$out" \
  && grep -q '^E: /usr/bin/prestium-demo: Prestium profile prestium-demo (usr.bin.prestium-demo) and prestium-demo (dup-name-same-attach) both attach' <<<"$out" \
  && ok "second file, same name, same program: fails (name and attachment)" || bad "dup name same attach: rc=$rc $out"
run dup-name-other-attach
[ $rc -ne 0 ] && grep -q '^E: profile name prestium-demo: .* and by dup-name-other-attach' <<<"$out" \
  && ok "second file, same name, other program: fails" || bad "dup name other attach: rc=$rc $out"
run dup-name-no-attach
[ $rc -ne 0 ] && grep -q '^E: profile name prestium-demo: .* and by dup-name-no-attach' <<<"$out" \
  && ok "second file, same name, no attachment: fails" || bad "dup name no attach: rc=$rc $out"
run other-name-same-attach
[ $rc -ne 0 ] && grep -q '^E: /usr/bin/prestium-demo: Prestium profile prestium-demo (usr.bin.prestium-demo) and not-prestium (other-name-same-attach) both attach' <<<"$out" \
  && ok "other name, same program: fails" || bad "other name same attach: rc=$rc $out"
run other-name-glob-attach
[ $rc -ne 0 ] && grep -q 'and bin-glob (other-name-glob-attach) both attach' <<<"$out" \
  && ok "other name, glob covering the program: fails" || bad "glob attach: rc=$rc $out"
# a leftover dpkg copy of the Prestium file is not loaded at boot, so it is not a second definition
run; cp "$F/usr.bin.prestium-demo" "$T/aa/usr.bin.prestium-demo.dpkg-old"
out=$(python3 -I "$CHK" "$T/aa" usr.bin.prestium-demo 2>&1) && ok "skipped files (.dpkg-old) are not counted" || bad "dpkg-old counted: $out"
# hook 0600 relies on the check failing the build (no list of filenames to delete for this case)
grep -q 'aa-attach-check.py /etc/apparmor.d' "$H" && grep -q 'would not load cleanly at boot"; exit 1; }' "$H" \
  && ok "hook 0600 stops the build when the check fails" || bad "hook 0600 does not stop on a failed check"
exit $fail
