#!/bin/bash
# 2.1: hook 0200 sets The Lounge's irc-framework ping_timeout to 320s (IRC over I2P).
# Applies the hook's patch to a copy of 4.5.2 network.js: the option appears once, the
# file parses, a second run is a no-op, and changed upstream text fails the patch.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
H=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
fail=0
ok(){ echo "OK   $1"; }
bad(){ echo "FAIL $1"; fail=1; }

grep -q 'models/network.js' "$H" && grep -q 'ping_timeout: 320' "$H" \
  && grep -q 'ping_interval stays the default 30' "$H" \
  && ok "hook 0200: 320s ping_timeout patch on network.js" || bad "hook 0200 patch missing"

# The patch runs after the verified thelounge.tar is unpacked; it must not edit irc-framework
# (those files are checked against the pinned commit).
! grep -q 'node_modules/irc-framework' "$H" \
  && ok "hook 0200: does not patch irc-framework" || bad "hook 0200 patches irc-framework"

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
sed -n '/^python3 - "\$N"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/patch.py"
grep -q 'ping_timeout: 320' "$T/patch.py" && ok "hook patch extracted" || { bad "could not extract hook patch"; exit 1; }

# Minimal 4.5.2 Client options (the exact text hook 0200 searches for)
cat > "$T/network.orig.js" <<'JS'
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
class Network {
    createIrcFramework(client) {
        this.irc = new irc_framework_1.default.Client({
            version: false, // We handle it ourselves
            outgoing_addr: config_1.default.values.bind,
            enable_chghost: true,
            enable_echomessage: true,
            enable_setname: true,
            auto_reconnect: true,
            // Exponential backoff maxes out at 300 seconds after 9 reconnects,
            // it will keep trying for well over an hour (plus the timeouts)
            auto_reconnect_max_retries: 30,
            // TODO: this type should be set after setIrcFrameworkOptions
        });
        this.setIrcFrameworkOptions(client);
    }
}
exports.default = Network;
JS

NODE=
if command -v node >/dev/null; then
  NODE=node
elif [ -x /opt/nodejs/bin/node ]; then
  NODE=/opt/nodejs/bin/node
fi
[ -n "$NODE" ] && ok "node for --check: $($NODE --version)" || bad "node missing (needed for --check)"

apply(){ python3 "$T/patch.py" "$1"; }

cp "$T/network.orig.js" "$T/network.js"
if out=$(apply "$T/network.js" 2>&1); then
  echo "$out" | grep -q 'ping_timeout is 320' && ok "first apply: patch accepted" || ok "first apply: exit 0"
else
  bad "first apply failed: $out"
fi

n=$(grep -c 'ping_timeout: 320' "$T/network.js" || true)
[ "$n" = 1 ] && ok "ping_timeout: 320 present once" || bad "ping_timeout: 320 count is $n"
! grep -q 'ping_interval' "$T/network.js" && ok "ping_interval not set (stays 30)" || bad "ping_interval was set"
grep -q 'auto_reconnect: true' "$T/network.js" && ok "surrounding Client options still present" || bad "Client options missing"

if [ -n "$NODE" ]; then
  $NODE --check "$T/network.js" && ok "patched file parses (node --check)" || bad "node --check failed"
fi

sum1=$(sha256sum "$T/network.js" | cut -c1-64)
if out=$(apply "$T/network.js" 2>&1); then
  sum2=$(sha256sum "$T/network.js" | cut -c1-64)
  [ "$sum1" = "$sum2" ] && ok "second apply: no-op (file unchanged)" || bad "second apply rewrote the file"
else
  bad "second apply failed: $out"
fi

# Changed upstream text must fail closed (unpatched copy with the searched block altered)
cp "$T/network.orig.js" "$T/changed.js"
sed -i 's/enable_chghost: true/enable_chghost: false/' "$T/changed.js"
if out=$(apply "$T/changed.js" 2>&1); then
  bad "changed upstream text was accepted"
else
  echo "$out" | grep -q 'Client options changed' && ok "changed upstream text fails the patch" || ok "changed upstream text failed (exit non-zero)"
fi
# The failed run must not have written ping_timeout into the mutated file
! grep -q 'ping_timeout' "$T/changed.js" && ok "failed apply left the mutated file unpatched" || bad "failed apply wrote ping_timeout"

# If a real The Lounge 4.5.2 tree is present, apply to a copy of that network.js too
REAL=
cands="/tmp/lounge/node_modules/thelounge/dist/server/models/network.js"
if [ -f "$R/thirdparty/versions.sh" ]; then
  # shellcheck source=/dev/null
  . "$R/thirdparty/versions.sh"
  cands="$cands $R/cache/thirdparty/thelounge-$THELOUNGE_VERSION-r22/node_modules/thelounge/dist/server/models/network.js"
fi
for cand in $cands; do
  [ -f "$cand" ] && REAL=$cand && break
done
if [ -n "$REAL" ]; then
  cp "$REAL" "$T/real.js"
  if out=$(apply "$T/real.js" 2>&1); then
    [ "$(grep -c 'ping_timeout: 320' "$T/real.js")" = 1 ] && ok "real 4.5.2 network.js: patched once" || bad "real network.js: ping_timeout count"
    [ -n "$NODE" ] && $NODE --check "$T/real.js" && ok "real 4.5.2 network.js parses" || { [ -z "$NODE" ] || bad "real network.js: node --check"; }
    sumr=$(sha256sum "$T/real.js" | cut -c1-64)
    apply "$T/real.js" >/dev/null && [ "$(sha256sum "$T/real.js" | cut -c1-64)" = "$sumr" ] \
      && ok "real 4.5.2 network.js: second apply is a no-op" || bad "real network.js: second apply changed it"
  else
    bad "real 4.5.2 network.js: patch failed: $out"
  fi
else
  ok "no local 4.5.2 tree; fixture only (optional)"
fi

[ $fail = 0 ] && echo "thelounge ping timeout: OK"
exit $fail
