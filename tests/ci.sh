#!/bin/bash
# Prestium 2.1 (security audit): the checks CI runs on every push (.github/workflows/checks.yml), and
# that can be run by hand on Debian 13 with the same packages installed:
#   1. shellcheck (errors) on every shell script in the tree
#   2. every Prestium AppArmor profile compiles (apparmor_parser -Q -K)
#   3. no private keys or tokens committed
#   4. systemd-analyze security scores for the hardened services (printed, not gated)
#   5. the test suite, except the tests that need a real Wayland session, bwrap and sudo
#      (test_wayland_broker.sh, test_wayland_session.sh, test_browser_sandbox.sh,
#      test_onion_grater_identity.py): those run on a Prestium build machine or the live system.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); cd "$R" || exit 1
fail=0; step(){ echo; echo "== $*"; }
LIVE_ONLY="test_wayland_broker.sh test_wayland_session.sh test_browser_sandbox.sh test_onion_grater_identity.py"

step "shellcheck (errors)"
mapfile -t SH < <(git ls-files | while read -r f; do
  [ -f "$f" ] || continue
  case $f in *.torrent|*.xpi|*.deb|*.su3|*.kbx|*.png|*.jpg|*.svg|*.webp|*.ico) continue;; esac
  head -n1 "$f" 2>/dev/null | grep -qE '^#!(/usr)?/bin/(env )?(ba|da)?sh( |$)' && echo "$f"
done)
echo "${#SH[@]} shell scripts"
shellcheck -S error "${SH[@]}" || fail=1

step "AppArmor profiles compile"
if command -v apparmor_parser >/dev/null; then
  W=$(mktemp -d); cp -r /etc/apparmor.d/. "$W"/ 2>/dev/null; cp -r config/includes.chroot/etc/apparmor.d/. "$W"/
  for p in config/includes.chroot/etc/apparmor.d/*; do
    [ -f "$p" ] || continue; n=$(basename "$p")
    if apparmor_parser -Q -K -b "$W" "$W/$n" >/dev/null 2>"$W/.err"; then echo "OK   $n"
    else echo "FAIL $n"; sed 's/^/     /' "$W/.err"; fail=1; fi
  done; rm -rf "$W"
else echo "FAIL apparmor_parser missing"; fail=1; fi

step "no secrets committed"
if git grep -nIE -e '-----BEGIN ((RSA|DSA|EC|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----' -e '-----BEGIN PGP PRIVATE KEY BLOCK-----' \
     -e 'gh[pousr]_[A-Za-z0-9]{36}' -e 'AKIA[0-9A-Z]{16}' -e 'xox[baprs]-[0-9A-Za-z-]{10,}' -- . ':!tests/ci.sh'; then
  echo "FAIL a private key or token is committed"; fail=1
else echo "OK   none found"; fi

step "systemd-analyze security (informational)"
if command -v systemd-analyze >/dev/null; then
  for u in prestium-onion-grater prestium-vm-netcheck prestium-mac-guard prestium-wl-broker thelounge; do
    s=$(systemd-analyze security --offline=true "config/includes.chroot/etc/systemd/system/$u.service" 2>/dev/null | tail -n 1)
    echo "INFO $u: ${s:-n/a}"
  done
fi

step "tests"
for t in tests/test_*.sh tests/test_*.py; do
  n=$(basename "$t")
  case " $LIVE_ONLY " in *" $n "*) echo "SKIP $n (needs a live session)"; continue;; esac
  case $t in *.py) cmd=(python3 "$t");; *) cmd=(bash "$t");; esac
  if out=$(timeout 900 "${cmd[@]}" 2>&1); then echo "OK   $n"
  else echo "FAIL $n"; printf '%s\n' "$out" | grep -E '^(FAIL|ERROR|E:|not ok)|Error' | head -20 | sed 's/^/     /'; fail=1; fi
done
echo; [ $fail = 0 ] && echo "ci: OK" || echo "ci: FAILED"
exit $fail
