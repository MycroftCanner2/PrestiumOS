#!/bin/bash
# 2.1: IRC (Tor) sign-in (SASL). Hook 0200 makes the Tor instance refuse a connection whose SASL sign-in
# can't work (Libera.Chat without a client certificate, AlphaChat without SASL, SASL PLAIN with an empty
# account or password), explain it in the lobby, show the certificate fingerprint with SASL EXTERNAL and
# report a failed SASL sign-in. hackint, OFTC and the others connect as before; the I2P instance is
# unchanged. The patch runs on a fixture with the exact 4.5.2 text; with a The Lounge tree
# (PRESTIUM_TL_TREE=<dir with node_modules>, or the staged thelounge.tar) also on the real files,
# with the real irc-framework (its socket connect is stubbed: nothing leaves the machine).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

sed -n '/^python3 - "\$NA" "\$IA"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/sasl.py"
grep -q 'prestiumTorRefuse' "$T/sasl.py" && ok "hook patch (SASL) extracted" || { bad "could not extract the SASL patch"; exit 1; }
grep -q '/opt/nodejs/bin/node --check "\$NA"' "$H" && grep -q '/opt/nodejs/bin/node --check "\$IA"' "$H" && ok "hook 0200: patched files syntax-checked" || bad "no node --check"
# runs after the Tor SOCKS patch and the connect.js "Connecting to" patch
a=$(grep -n '^python3 - "\$NS"' "$H" | cut -d: -f1); b=$(grep -n '^python3 - "\$C" "\$I"' "$H" | cut -d: -f1); c=$(grep -n '^python3 - "\$NA" "\$IA"' "$H" | cut -d: -f1)
[ -n "$a" ] && [ -n "$b" ] && [ -n "$c" ] && [ "$b" -lt "$c" ] && [ "$a" -lt "$c" ] && ok "hook 0200: SASL patch after the connect.js and SOCKS patches" || bad "patch order"
grep -q 'PRESTIUM_LOUNGE_TOR !== "1"' "$T/sasl.py" && grep -q 'if (process.env.PRESTIUM_LOUNGE_TOR === \\"1\\") {' "$T/sasl.py" && ok "patch: Tor instance only" || bad "patch not limited to the Tor instance"

# fixture: the 4.5.2 text the patch looks for, with stand-ins for The Lounge's modules
cat > "$T/network.js" <<'JS'
"use strict";
const crypto_1 = {default: require("crypto")};
const msg_1 = {default: class Msg { constructor(a) { Object.assign(this, {type: "message"}, a); } }};
const msg_2 = {MessageType: {ERROR: "error"}};
const clientCertificate_1 = {default: {get: () => global.PRESTIUM_TEST_CERT || null}};
class Network {
    constructor(attr) {
        Object.assign(this, {sasl: "", saslAccount: "", saslPassword: "", name: "net", uuid: "u1"}, attr);
        this.lobby = {messages: [], pushMessage(client, m) { this.messages.push(m); }};
    }
    getLobby() { return this.lobby; }
    createIrcFramework(client) {
        const E = require("events");
        this.irc = Object.assign(new E(), {started: 0, requestCap() {}, connect() { this.started++; }});
        this.setIrcFrameworkOptions(client);
        this.irc.requestCap([
            "znc.in/self-message", // Legacy echo-message for ZNC
        ]);
    }
    setIrcFrameworkOptions(client) {
    }
}
module.exports = Network;
JS
cat > "$T/connect.js" <<'JS'
"use strict";
const input = function (network, chan, cmd, args) {
    if (args.length === 0) {
        network.userDisconnected = false;
        this.save();
        const irc = network.irc;
        if (irc.connected) {
            return;
        }
        // Prestium: tell the user when a connection actually starts (/connect or the Connect menu)
        network.getLobby().pushMessage(this, {text: "Connecting to " + network.host + ":" + network.port + "..."}, true);
        irc.connect();
        return;
    }
};
module.exports = input;
JS
python3 "$T/sasl.py" "$T/network.js" "$T/connect.js" >/dev/null && ok "patch applies" || bad "patch failed"
cp "$T/network.js" "$T/n1.js"; cp "$T/connect.js" "$T/c1.js"
python3 "$T/sasl.py" "$T/network.js" "$T/connect.js" >/dev/null && cmp -s "$T/network.js" "$T/n1.js" && cmp -s "$T/connect.js" "$T/c1.js" \
  && ok "second run is a no-op" || bad "patch not idempotent"
printf 'x\n' > "$T/x.js"; python3 "$T/sasl.py" "$T/x.js" "$T/connect.js" >/dev/null 2>&1 && bad "changed network.js passes" || ok "changed network.js stops the build"
cp "$T/n1.js" "$T/n2.js"; printf 'x\n' > "$T/cx.js"; python3 "$T/sasl.py" "$T/n2.js" "$T/cx.js" >/dev/null 2>&1 && bad "changed connect.js passes" || ok "changed connect.js stops the build"
command -v node >/dev/null || { echo "SKIP node missing"; exit $fail; }
node --check "$T/network.js" && node --check "$T/connect.js" && ok "patched files parse" || bad "patched files do not parse"
if command -v openssl >/dev/null; then
  openssl req -x509 -newkey rsa:2048 -nodes -subj /CN=t -days 1 -keyout "$T/k.pem" -out "$T/c.pem" >/dev/null 2>&1
  fp=$(openssl x509 -in "$T/c.pem" -noout -fingerprint -sha512 | awk -F= '{gsub(":",""); print tolower ($2)}')
else fp=; fi
cat > "$T/rules.js" <<'JS'
// shared by the fixture and the real tree: mk(attr) -> Network, client
const assert = require("assert");
module.exports = function (mk, client, started, connectInput, fp) {
	const lobby = (n) => n.getLobby().messages.map(m => (m.type === "error" ? "E " : "I ") + m.text);
	const go = (attr) => { const n = mk(attr); n.createIrcFramework(client); n.irc.connect(); return {n, s: started(n), l: lobby(n)}; };
	process.env.PRESTIUM_LOUNGE_TOR = "1";
	let r = go({host: "palladium.libera.chat", sasl: ""});
	assert.strictEqual(r.s, 0); assert.strictEqual(r.n.userDisconnected, true);
	assert.ok(r.l.some(t => t.startsWith("E Not connecting. Libera.Chat over Tor only accepts an account registered without Tor")), r.l);
	assert.ok(r.l.some(t => t.includes("Client certificate (SASL EXTERNAL)") && t.includes("/msg NickServ CERT ADD")), r.l);
	assert.strictEqual(go({host: "palladium.libera.chat", sasl: "plain", saslAccount: "a", saslPassword: "b"}).s, 0, "Libera: PLAIN refused over Tor");
	assert.strictEqual(go({host: "libera75jm6of4wxpxt4aynol3xjmbtxgfyjpu34ss4d7r7q2v5zrpyd.onion", sasl: ""}).s, 0);
	assert.strictEqual(go({host: "IRC.Libera.Chat", sasl: ""}).s, 0);
	r = go({host: "palladium.libera.chat", sasl: "external"});
	assert.strictEqual(r.s, 1, r.l);
	if (fp) assert.ok(r.l.some(t => t.includes("fingerprint (SHA-512) is " + fp + ".") && t.endsWith("CERT ADD " + fp)), r.l);
	r = go({host: "irc.alphachat.net", sasl: "plain"});
	assert.strictEqual(r.s, 0); assert.ok(r.l.some(t => t.startsWith("E Not connecting. AlphaChat needs your account name and password")), r.l);
	assert.ok(r.l.some(t => t.startsWith("I AlphaChat needs your account name and password")), "hint before Connect");
	assert.strictEqual(go({host: "irc.alphachat.net", sasl: "plain", saslAccount: "me", saslPassword: ""}).s, 0);
	assert.strictEqual(go({host: "irc.alphachat.net", sasl: ""}).s, 0);
	assert.strictEqual(go({host: "rjmhwz5coqxunj3taoceh6etng4tvvaqg6nh3brhn2mfudpikptblpad.onion", sasl: ""}).s, 0);
	assert.strictEqual(go({host: "irc.alphachat.net", sasl: "plain", saslAccount: "me", saslPassword: "pw"}).s, 1);
	assert.strictEqual(go({host: "irc.alphachat.net", sasl: "external"}).s, 1);
	r = go({host: "guybrush.hackint.org", sasl: ""});
	assert.strictEqual(r.s, 1); assert.ok(r.l.some(t => t.startsWith("I hackint lets you in over Tor without an account")), r.l);
	assert.strictEqual(go({host: "guybrush.hackint.org", sasl: "plain", saslAccount: "me", saslPassword: ""}).s, 0);
	assert.strictEqual(go({host: "guybrush.hackint.org", sasl: "plain", saslAccount: "me", saslPassword: "pw"}).s, 1);
	for (const h of ["oftcnet6xg6roj6d7id4y4cu6dchysacqj2ldgea73qzdagufflqxrid.onion", "vrw7zcuarwx4oeju3iikiz3jffrvuijsysyznqf53mxizxrebomfnrid.onion",
		"darkirc6tqgpnwd3blln3yfv5ckl47eg7llfxkmtovrv7c7iwohhb6ad.onion", "4ufrikyorlatp5ekgz6tlre22v6b5jxqbiid6cp7nuhemklukiohidqd.onion", "notlibera.chat.example"]) {
		r = go({host: h, sasl: ""}); assert.strictEqual(r.s, 1, h); assert.deepStrictEqual(r.l, [], h);
	}
	assert.strictEqual(go({host: "oftcnet6xg6roj6d7id4y4cu6dchysacqj2ldgea73qzdagufflqxrid.onion", sasl: "plain", saslAccount: "", saslPassword: ""}).s, 0);
	// a failed sign-in is reported
	r = go({host: "irc.alphachat.net", sasl: "plain", saslAccount: "me", saslPassword: "pw"});
	r.n.irc.emit("sasl failed", {reason: "fail"});
	assert.ok(lobby(r.n).some(t => t.startsWith("E Sign-in (SASL) failed (fail).")), lobby(r.n));
	// /connect: refused before the "Connecting to" line, network stays disconnected
	const n = mk({host: "irc.alphachat.net", sasl: "plain"}); n.createIrcFramework(client); n.getLobby().messages.length = 0;
	connectInput.call(client, n, n.getLobby(), "connect", []);
	assert.strictEqual(started(n), 0); assert.strictEqual(n.userDisconnected, true);
	assert.ok(!lobby(n).some(t => t.includes("Connecting to")), lobby(n));
	assert.ok(lobby(n)[0].startsWith("E Not connecting."), lobby(n));
	const m = mk({host: "irc.alphachat.net", sasl: "plain", saslAccount: "me", saslPassword: "pw"}); m.createIrcFramework(client);
	connectInput.call(client, m, m.getLobby(), "connect", []);
	assert.strictEqual(started(m), 1); assert.ok(lobby(m).some(t => t.includes("Connecting to irc.alphachat.net")));
	// I2P instance: nothing changes
	delete process.env.PRESTIUM_LOUNGE_TOR;
	for (const a of [{host: "palladium.libera.chat", sasl: ""}, {host: "irc.alphachat.net", sasl: "plain"}]) {
		r = go(a); assert.strictEqual(r.s, 1); assert.deepStrictEqual(r.l, []);
	}
};
JS
node - "$T" "$fp" <<'JS' && ok "fixture: Libera.Chat needs a certificate, AlphaChat SASL, PLAIN needs both fields; hints, fingerprint, failed SASL; hackint/OFTC/others connect; I2P unchanged" || bad "fixture behaviour"
const [T, fp] = process.argv.slice(2), fs = require("fs");
if (fp) global.PRESTIUM_TEST_CERT = {certificate: fs.readFileSync(T + "/c.pem", "utf8")};
const N = require(T + "/network.js");
const client = {save() {}};
require(T + "/rules.js")((a) => new N(a), client, (n) => n.irc.started, require(T + "/connect.js"), fp);
JS

## with a real The Lounge tree
TL=${PRESTIUM_TL_TREE:-}
if [ -z "$TL" ] && [ -s "$I/usr/src/prestium-thirdparty/thelounge.tar" ]; then
  mkdir -p "$T/opt"; tar -xf "$I/usr/src/prestium-thirdparty/thelounge.tar" -C "$T/opt"; TL=$T/opt; fi
if [ -z "$TL" ]; then echo "SKIP no The Lounge tree (PRESTIUM_TL_TREE or staged thelounge.tar)"; exit $fail; fi
# The Lounge is patched in a copy (all of hook 0200's patches, in order); its dependencies are used in place
mkdir -p "$T/tl/node_modules" "$T/home"; cp -R "$TL/node_modules/thelounge" "$T/tl/node_modules/thelounge"
for d in "$TL"/node_modules/*; do [ "$(basename "$d")" = thelounge ] || ln -s "$d" "$T/tl/node_modules/"; done
D=$T/tl/node_modules/thelounge/dist/server
blk(){ sed -n "/^python3 - $1 <<'PY'\$/,/^PY\$/p" "$H" | sed '1d;$d'; }
blk '"\$N"' > "$T/p1.py"; blk '"\$C" "\$I"' > "$T/p2.py"; blk '"\$NS"' > "$T/p3.py"; blk '"\$NA" "\$IA"' > "$T/p4.py"
python3 "$T/p1.py" "$D/models/network.js" >/dev/null && python3 "$T/p2.py" "$D/plugins/irc-events/connection.js" "$D/plugins/inputs/connect.js" >/dev/null \
  && python3 "$T/p3.py" "$D/models/network.js" >/dev/null && python3 "$T/p4.py" "$D/models/network.js" "$D/plugins/inputs/connect.js" >/dev/null \
  && node --check "$D/models/network.js" && node --check "$D/plugins/inputs/connect.js" \
  && ok "hook 0200 patches apply to The Lounge $(node -p "require('$D/../../package.json').version")" || { bad "hook patches on the real tree"; exit 1; }
node - "$D" "$T/home" "$T" <<'JS' && ok "real tree: same rules with the real Network, irc-framework and certificate (fingerprint = SHA-512 of the generated certificate)" || bad "real tree behaviour"
const [D, home, T] = process.argv.slice(2), crypto = require("crypto"), fs = require("fs");
const config = require(D + "/config.js").default; config.setHome(home);
const Network = require(D + "/models/network.js").default;
const connect = require(D + "/plugins/inputs/connect.js").default.input;
const client = {messageStorage: [], config: {}, save() {}, emit() {}};
const count = new WeakMap();
const mk = (a) => new Network(Object.assign({uuid: crypto.randomUUID(), name: "x", nick: "anon1", port: 6697, tls: true, userDisconnected: true}, a));
const orig = Network.prototype.createIrcFramework;
Network.prototype.createIrcFramework = function (c) { orig.call(this, c); count.set(this, 0); this.irc.connection.connect = () => count.set(this, count.get(this) + 1); };
// the fingerprint the lobby must show: SHA-512 of the certificate The Lounge generates for that uuid
const uuid = crypto.randomUUID();
const cert = require(D + "/plugins/clientCertificate.js").default.get(uuid);
const fp = crypto.createHash("sha512").update(new crypto.X509Certificate(cert.certificate).raw).digest("hex");
const mkfp = (a) => mk(a.host === "palladium.libera.chat" && a.sasl === "external" ? Object.assign({uuid}, a) : a);
require(T + "/rules.js")(mkfp, client, (n) => count.get(n), connect, fp);
JS
exit $fail
