#!/bin/sh
# Safe local syntax checks (no privileges, no service changes).
set -e
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
fail=0
for f in \
  "$root/config/includes.chroot/usr/local/sbin/prestium-i2pd-port" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-i2pd-torrents" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-i2p-reseed" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-clockfix" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-timesync" \
  "$root/config/includes.chroot/usr/local/bin/claws-mail-i2p" \
  "$root/config/includes.chroot/usr/local/bin/prestium-irc" \
  "$root/config/includes.chroot/usr/local/bin/prestium-i2p-console" \
  "$root/config/includes.chroot/usr/local/bin/prestium-localfox" \
  "$root/config/includes.chroot/usr/local/bin/prestium-tunnel-hops" \
  "$root/config/includes.chroot/usr/lib/systemd/system-sleep/prestium-usb-watchdog"
do
  if ! bash -n "$f"; then
    echo "FAIL sh -n $f"; fail=1
  else
    echo "OK   bash -n $f"
  fi
done
for f in \
  "$root/config/includes.chroot/usr/local/sbin/prestium-tor-mode" \
  "$root/config/includes.chroot/usr/local/bin/prestium-tor-assistant" \
  "$root/config/includes.chroot/usr/local/bin/prestium-torrents" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-onion-grater" \
  "$root/config/includes.chroot/usr/local/lib/prestium/safefile" \
  "$root/config/includes.chroot/usr/local/lib/prestium/browser_update.py" \
  "$root/config/includes.chroot/usr/local/sbin/prestium-browser-install" \
  "$root/config/includes.chroot/usr/local/bin/prestium-browser-updater"
do
  # bytecode goes to a throw-away prefix, never into config/includes.chroot (live-build would ship it)
  if ! PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/prestium-pycache.$$" python3 -m py_compile "$f"; then
    echo "FAIL py_compile $f"; fail=1
  else
    echo "OK   py_compile $f"
  fi
done
rm -rf "${TMPDIR:-/tmp}/prestium-pycache.$$"
# awk dry-run for port+auth rewrite
python3 - <<'PY'
import subprocess, tempfile, textwrap, os
conf = textwrap.dedent("""\
  # top
  port = 12345
  [http]
  address = 127.0.0.1
  port = 7070
  # auth = true
  # user = i2pd
  # pass = changeme
  [ntcp2]
  enabled = true
""")
awk = r'''
  BEGIN { inhttp=0; done_port=0; saw_auth=0; saw_user=0; saw_pass=0 }
  !done_port && /^\[/ {
    print "port = " p; print ""; done_port=1
  }
  !done_port && /^port[ \t]*=/ { next }
  /^\[http\]/ { inhttp=1; print; next }
  /^\[/ {
    if (inhttp) {
      if (!saw_auth) print "auth = true"
      if (!saw_user) print "user = i2pd"
      if (!saw_pass) print "pass = " pass
      inhttp=0
    }
    print; next
  }
  inhttp && /^auth[ \t]*=/ { print "auth = true"; saw_auth=1; next }
  inhttp && /^user[ \t]*=/ { print "user = i2pd"; saw_user=1; next }
  inhttp && /^pass[ \t]*=/ { print "pass = " pass; saw_pass=1; next }
  inhttp && /^#[[:space:]]*auth([ \t]*=|$)/ { next }
  inhttp && /^#[[:space:]]*user([ \t]*=|$)/ { next }
  inhttp && /^#[[:space:]]*pass([ \t]*=|$)/ { next }
  { print }
  END {
    if (inhttp) {
      if (!saw_auth) print "auth = true"
      if (!saw_user) print "user = i2pd"
      if (!saw_pass) print "pass = " pass
    }
  }
'''
import subprocess
out = subprocess.check_output(["awk", "-v", "p=20000", "-v", "pass=SecretPass1", awk], input=conf, text=True)
assert "port = 20000" in out
assert "auth = true" in out
assert "user = i2pd" in out
assert "pass = SecretPass1" in out
assert "port = 12345" not in out
print("OK   awk port+auth rewrite")
PY
exit $fail
