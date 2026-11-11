#!/bin/sh
# Prestium 2.1 (audit of 96468c5, L-1): hook 0460 turns the per-user site-packages off
# on frozen Python (3.11+) via sitecustomize, and the session sets PYTHONNOUSERSITE.
# This test injects the shipped sitecustomize through PYTHONPATH (so it runs in place
# of the host's) and does not modify the host Python install.
set -eu
R=$(cd "$(dirname "$0")/.." && pwd)
SRC=$R/config/includes.chroot/usr/local/lib/prestium/sitecustomize.py
HK=$R/config/hooks/live/0460-prestium-python-usersite.hook.chroot
ENV=$R/config/includes.chroot/etc/environment
fail=0
ok() { printf 'OK   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

[ -f "$SRC" ] && ok "sitecustomize.py is in includes" || bad "missing $SRC"
[ -f "$HK" ] && ok "hook 0460 is present" || bad "missing hook 0460"
grep -q 'PYTHONNOUSERSITE=1' "$ENV" && ok "/etc/environment sets PYTHONNOUSERSITE=1" \
	|| bad "/etc/environment does not set PYTHONNOUSERSITE=1"
grep -q 'sitecustomize' "$HK" && grep -q 'ENABLE_USER_SITE is False' "$HK" && grep -q 'exit 1' "$HK" \
	&& ok "hook 0460 installs sitecustomize and fails the build if it does not take effect" \
	|| bad "hook 0460 does not check that the user site is off"
# Must not rely on a site.py disk patch as the disable (frozen site ignores it)
if grep -q "sed -i .*ENABLE_USER_SITE" "$HK"; then
	bad "hook 0460 still patches site.py (ignored by frozen site)"
else
	ok "hook 0460 does not patch site.py"
fi
grep -q 'ENABLE_USER_SITE = False' "$SRC" && ok "sitecustomize sets ENABLE_USER_SITE = False" \
	|| bad "sitecustomize does not set ENABLE_USER_SITE = False"

# Functional: our sitecustomize, a fake HOME, no PYTHONNOUSERSITE
v=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/sc" "$T/home/.local/lib/python$v/site-packages"
cp "$SRC" "$T/sc/sitecustomize.py"
printf '%s\n' 'import os; open(os.environ["PRESTIUM_MARKER"], "w").write("pth")' \
	> "$T/home/.local/lib/python$v/site-packages/prestium-probe.pth"
printf '%s\n' 'import os; open(os.environ["PRESTIUM_MARKER"] + ".uc", "w").write("uc")' \
	> "$T/home/.local/lib/python$v/site-packages/usercustomize.py"

rm -f "$T/pth-ran" "$T/pth-ran.uc"
if env -u PYTHONNOUSERSITE HOME="$T/home" PRESTIUM_MARKER="$T/pth-ran" PYTHONPATH="$T/sc" \
	python3 -c 'import os, site, sys
assert site.ENABLE_USER_SITE is False, site.ENABLE_USER_SITE
assert site.USER_SITE not in sys.path, sys.path
assert not os.path.exists(os.environ["PRESTIUM_MARKER"] + ".uc")
'; then
	ok "sitecustomize: ENABLE_USER_SITE is False, path dropped, usercustomize does not run"
else
	bad "sitecustomize did not disable the user site without PYTHONNOUSERSITE"
fi

rm -f "$T/pth-ran" "$T/pth-ran.uc"
if HOME="$T/home" PRESTIUM_MARKER="$T/pth-ran" PYTHONPATH="$T/sc" PYTHONNOUSERSITE=1 \
	python3 -c 'import os, site, sys
assert site.ENABLE_USER_SITE is False, site.ENABLE_USER_SITE
assert site.USER_SITE not in sys.path, sys.path
assert not os.path.exists(os.environ["PRESTIUM_MARKER"])
assert not os.path.exists(os.environ["PRESTIUM_MARKER"] + ".uc")
'; then
	ok "PYTHONNOUSERSITE: a user-site .pth does not run"
else
	bad "PYTHONNOUSERSITE did not stop a user-site .pth"
fi

# Control: without our sitecustomize and without PYTHONNOUSERSITE, the user site is on
# (proves the probe is valid). Skip if this host already disables it some other way.
rm -f "$T/pth-ran" "$T/pth-ran.uc"
if env -u PYTHONNOUSERSITE -u PYTHONPATH HOME="$T/home" PRESTIUM_MARKER="$T/pth-ran" \
	python3 -c 'import site, sys; sys.exit(0 if site.ENABLE_USER_SITE else 1)'; then
	ok "control: host Python enables the user site without the hook (probe is valid)"
	[ -f "$T/pth-ran" ] && ok "control: a user-site .pth runs on the host without the hook" \
		|| bad "control: host .pth did not run; the probe may be wrong"
else
	ok "control: this host already disables the user site (skipped the .pth-runs check)"
fi

[ "$fail" -eq 0 ] || exit 1
