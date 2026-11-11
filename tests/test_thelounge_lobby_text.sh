#!/bin/bash
# 2.1: hook 0200 only shows The Lounge's "Network created, connecting to host:port..."
# lobby line when a connection will actually start, and adds "Connecting to host:port..."
# in connect.js for /connect and the Connect menu. Applies the hook's patch to copies of
# 4.5.2 connection.js and connect.js: substitution once, files parse, second run is a
# no-op, changed upstream text fails; a stubbed load of the plugin checks the behaviour.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
H=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
fail=0
ok(){ echo "OK   $1"; }
bad(){ echo "FAIL $1"; fail=1; }

grep -q 'plugins/irc-events/connection.js' "$H" && grep -q 'userDisconnected' "$H" \
  && grep -q 'plugins/inputs/connect.js' "$H" && grep -q 'Connecting to ' "$H" \
  && ok "hook 0200: connecting lobby text patches" || bad "hook 0200 lobby text patches missing"

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
sed -n '/^python3 - "\$C" "\$I"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/patch.py"
grep -q 'userDisconnected' "$T/patch.py" && grep -q 'Connecting to ' "$T/patch.py" \
  && ok "hook patch extracted" || { bad "could not extract hook patch"; exit 1; }

# Minimal fixtures with the exact 4.5.2 text the hook searches for
cat > "$T/connection.orig.js" <<'JS'
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const msg_1 = { default: function (attr) { this.text = attr.text; } };
exports.default = (function (irc, network) {
    const client = this;
    network.getLobby().pushMessage(client, new msg_1.default({
        text: "Network created, connecting to " + network.host + ":" + network.port + "...",
    }), true);
    irc.on("registered", function () { });
    irc.on("socket connected", function () {
        network.getLobby().pushMessage(client, new msg_1.default({
            text: "Connected to the network.",
        }), true);
    });
    irc.on("reconnecting", function (data) {
        network.getLobby().pushMessage(client, new msg_1.default({
            text: "Disconnected from the network. Reconnecting in " + data.wait + " seconds…",
        }), true);
    });
});
JS

cat > "$T/connect.orig.js" <<'JS'
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const msg_1 = { default: function (attr) { this.text = attr && attr.text; this.type = attr && attr.type; } };
const msg_2 = { MessageType: { ERROR: "error" } };
const commands = ["connect", "server"];
const allowDisconnected = true;
const input = function (network, chan, cmd, args) {
    if (args.length === 0) {
        network.userDisconnected = false;
        this.save();
        const irc = network.irc;
        if (!irc) {
            return;
        }
        if (irc.connected) {
            chan.pushMessage(this, new msg_1.default({
                type: msg_2.MessageType.ERROR,
                text: "You are already connected.",
            }));
            return;
        }
        irc.connect();
        return;
    }
    this.connectToNetwork({ host: args[0], port: args[1] || "", tls: false });
    return true;
};
exports.default = {
    commands,
    input,
    allowDisconnected,
};
JS

NODE=
if command -v node >/dev/null; then
  NODE=node
elif [ -x /opt/nodejs/bin/node ]; then
  NODE=/opt/nodejs/bin/node
fi
[ -n "$NODE" ] && ok "node for --check: $($NODE --version)" || bad "node missing (needed for --check)"

apply(){ python3 "$T/patch.py" "$1" "$2"; }

cp "$T/connection.orig.js" "$T/connection.js"
cp "$T/connect.orig.js" "$T/connect.js"
if out=$(apply "$T/connection.js" "$T/connect.js" 2>&1); then
  echo "$out" | grep -q 'gated on userDisconnected' && echo "$out" | grep -q 'Connecting to host:port' \
    && ok "first apply: patch accepted" || ok "first apply: exit 0"
else
  bad "first apply failed: $out"
fi

[ "$(grep -c 'if (!network.userDisconnected)' "$T/connection.js")" = 1 ] \
  && [ "$(grep -c 'Network created, connecting to ' "$T/connection.js")" = 1 ] \
  && ok "connection.js: message gated once" || bad "connection.js: gate or message count"
[ "$(grep -c 'Connecting to " + network.host' "$T/connect.js")" = 1 ] \
  && [ "$(grep -c 'irc.connect();' "$T/connect.js")" = 1 ] \
  && ok "connect.js: Connecting to message once, irc.connect once" || bad "connect.js: message or irc.connect count"
grep -q 'irc.on("reconnecting"' "$T/connection.js" && grep -q 'Connected to the network.' "$T/connection.js" \
  && ok "connection.js: reconnect and socket-connected handlers kept" || bad "connection.js: handlers missing"

if [ -n "$NODE" ]; then
  $NODE --check "$T/connection.js" && $NODE --check "$T/connect.js" \
    && ok "patched files parse (node --check)" || bad "node --check failed"
fi

sum1=$(sha256sum "$T/connection.js" "$T/connect.js")
if out=$(apply "$T/connection.js" "$T/connect.js" 2>&1); then
  sum2=$(sha256sum "$T/connection.js" "$T/connect.js")
  [ "$sum1" = "$sum2" ] && ok "second apply: no-op (files unchanged)" || bad "second apply rewrote a file"
else
  bad "second apply failed: $out"
fi

# Changed upstream text must fail closed
cp "$T/connection.orig.js" "$T/changed-conn.js"
cp "$T/connect.orig.js" "$T/changed-conn-ok.js"
sed -i 's/Network created, connecting to /Network created, dialing /' "$T/changed-conn.js"
if out=$(apply "$T/changed-conn.js" "$T/changed-conn-ok.js" 2>&1); then
  bad "changed connection.js text was accepted"
else
  echo "$out" | grep -q 'Network created message changed' && ok "changed connection.js text fails the patch" \
    || ok "changed connection.js text failed (exit non-zero)"
fi
! grep -q 'userDisconnected' "$T/changed-conn.js" && ok "failed connection.js apply left the file unpatched" \
  || bad "failed connection.js apply wrote the guard"

cp "$T/connection.orig.js" "$T/changed-conn-ok2.js"
cp "$T/connect.orig.js" "$T/changed-in.js"
# Already-patched connection.js would skip; use unpatched connection + mutated connect
sed -i 's/irc.connect();/irc.open();/' "$T/changed-in.js"
if out=$(apply "$T/changed-conn-ok2.js" "$T/changed-in.js" 2>&1); then
  bad "changed connect.js text was accepted"
else
  echo "$out" | grep -q 'irc.connect() after already-connected check changed' && ok "changed connect.js text fails the patch" \
    || ok "changed connect.js text failed (exit non-zero)"
fi
! grep -q 'Connecting to ' "$T/changed-in.js" && ok "failed connect.js apply left the file unpatched" \
  || bad "failed connect.js apply wrote Connecting to"

# Behaviour: load the patched plugin with stubs
if [ -n "$NODE" ]; then
  if $NODE "$R/tests/thelounge_lobby_text_behaviour.js" "$T/connection.js" "$T/connect.js" \
       /tmp/lounge/node_modules/thelounge/dist/server/plugins/irc-events/connection.js \
       /tmp/lounge/node_modules/thelounge/dist/server/plugins/inputs/connect.js
  then
    ok "stubbed plugin: userDisconnected true hides the line, false shows it; /connect announces"
  else
    bad "stubbed plugin behaviour"
  fi
fi

# Real 4.5.2 tree, if present
REAL_C=/tmp/lounge/node_modules/thelounge/dist/server/plugins/irc-events/connection.js
REAL_I=/tmp/lounge/node_modules/thelounge/dist/server/plugins/inputs/connect.js
if [ -f "$REAL_C" ] && [ -f "$REAL_I" ]; then
  cp "$REAL_C" "$T/real-connection.js"
  cp "$REAL_I" "$T/real-connect.js"
  if out=$(apply "$T/real-connection.js" "$T/real-connect.js" 2>&1); then
    [ "$(grep -c 'if (!network.userDisconnected)' "$T/real-connection.js")" = 1 ] \
      && [ "$(grep -c 'Network created, connecting to ' "$T/real-connection.js")" = 1 ] \
      && ok "real 4.5.2 connection.js: gated once" || bad "real connection.js: counts"
    [ "$(grep -c 'Connecting to " + network.host' "$T/real-connect.js")" = 1 ] \
      && ok "real 4.5.2 connect.js: Connecting to once" || bad "real connect.js: count"
    if [ -n "$NODE" ]; then
      $NODE --check "$T/real-connection.js" && $NODE --check "$T/real-connect.js" \
        && ok "real 4.5.2 files parse" || bad "real files: node --check"
      if $NODE "$R/tests/thelounge_lobby_text_behaviour.js" "$T/real-connection.js" "$T/real-connect.js" "$REAL_C" "$REAL_I"
      then
        ok "real 4.5.2 stubbed behaviour"
      else
        bad "real 4.5.2 stubbed behaviour"
      fi
    fi
    sumr=$(sha256sum "$T/real-connection.js" "$T/real-connect.js")
    apply "$T/real-connection.js" "$T/real-connect.js" >/dev/null \
      && [ "$(sha256sum "$T/real-connection.js" "$T/real-connect.js")" = "$sumr" ] \
      && ok "real 4.5.2: second apply is a no-op" || bad "real 4.5.2: second apply changed a file"
  else
    bad "real 4.5.2 files: patch failed: $out"
  fi
else
  ok "no local 4.5.2 tree; fixture only (optional)"
fi

[ $fail = 0 ] && echo "thelounge lobby text: OK"
exit $fail
