#!/bin/bash
# 2.1 (security audit): the unused /etc/i2pd/i2pd.conf is the live config (it used to differ, SAM on),
# copied at build time by hook 0700; the desktop user is not in group i2pd.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
cmp -s "$I/etc/i2pd/i2pd.conf" "$I/var/lib/i2pd/i2pd.conf" && ok "repo: /etc/i2pd/i2pd.conf = live config" || bad "repo copies differ"
grep -qx 'install -m 0644 -o root -g root /var/lib/i2pd/i2pd.conf /etc/i2pd/i2pd.conf' "$R/config/hooks/live/0700-prestium-i2pd.hook.chroot" \
  && ok "hook 0700 copies the live config" || bad "hook 0700 copy"
awk '/^\[sam\]/{s=1;next} /^\[/{s=0} s && /^enabled *= *true/' "$I/etc/i2pd/i2pd.conf" | grep -q . && bad "SAM enabled in /etc copy" || ok "SAM off"
H=$R/config/hooks/live/0100-prestium-users.hook.chroot
grep -E '^usermod -aG [^ ]+ user( |$)' "$H" | grep -qw i2pd && bad "user added to group i2pd" || ok "user not added to group i2pd"
grep -q 'gpasswd -d user i2pd' "$H" && ok "and removed if the package added it" || bad "no removal"
exit $fail
