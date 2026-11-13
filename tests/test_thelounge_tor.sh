#!/bin/bash
# 2.1: IRC (Tor), The Lounge's second instance. It mirrors the I2P instance (own user, state
# directory, root-owned read-only config.js, unit sandbox, AppArmor profile, one-use sign-in token,
# local-only Firefox, random nicks, networks start disconnected) and reaches IRC only through Tor's
# SOCKS port 127.0.0.1:9050: the firewall lets uid thelounge-tor reach nothing else, and hook 0200
# makes The Lounge send every network through that port with the host name (resolved by Tor).
# Static checks, plus the hook's network.js patch on a 4.5.2 fixture. With a The Lounge tree
# (PRESTIUM_TL_TREE=<dir with node_modules>, or the staged thelounge.tar) it also applies the hook's
# patches to the real files, runs prestium-thelounge-setup tor in a temp dir, and checks that the
# pinned irc-framework/socks hand the host name to the SOCKS5 proxy (no local DNS).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
U=$I/etc/systemd/system; P=$I/usr/share/prestium/build/perms.txt; F=$I/etc/ferm/ferm.conf
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

## users
grep -qx 'sysuser thelounge-tor /var/lib/thelounge-tor ""   # 2.1: IRC (Tor); the firewall lets it reach only 127.0.0.1:9050' \
  "$R/config/hooks/live/0100-prestium-users.hook.chroot" && ok "hook 0100: system user thelounge-tor" || bad "no thelounge-tor user"

## firewall
rules=$(grep -vE '^\s*#' "$F")
grep -qx 'def $lounge_tor_uid = thelounge-tor;' <<<"$rules" && ok "ferm: \$lounge_tor_uid is thelounge-tor" || bad "ferm def"
blk=$(sed -n '/mod owner uid-owner \$lounge_tor_uid {/,/^\t\t\t}/p' "$F" | grep -vE '^\s*#')
[ "$(grep -c ACCEPT <<<"$blk")" = 2 ] \
  && grep -qx $'\t\t\t\touterface lo daddr 127.0.0.1 proto tcp syn dport 9050 ACCEPT;' <<<"$blk" \
  && grep -qx $'\t\t\t\touterface lo mod state state (RELATED) proto icmp ACCEPT;' <<<"$blk" \
  && grep -q 'REJECT reject-with icmp-port-unreachable;' <<<"$blk" \
  && ok "ferm: thelounge-tor may open only 127.0.0.1:9050 (TCP), everything else rejected" || bad "ferm thelounge-tor block: $blk"
[ "$(grep -c 'lounge_tor_uid' <<<"$rules")" = 2 ] && ok "ferm: no other rule names thelounge-tor" || bad "ferm: other rules for thelounge-tor"
# its block comes before the generic loopback rules, so nothing later can accept its packets
a=$(grep -n 'uid-owner \$lounge_tor_uid {' "$F" | cut -d: -f1); b=$(grep -n 'daddr 127.0.0.1 proto tcp syn dport \$user_ports' "$F" | cut -d: -f1)
[ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ] && ok "ferm: thelounge-tor block before the shared loopback rules" || bad "ferm order"
grep -q 'dport (7070 7685 9000 9010) ACCEPT;' <<<"$rules" && ok "ferm: local-only Firefox may reach 9010" || bad "ferm localweb 9010"
grep -qx 'def $user_ports = (4444 4447 4450 7659 7660 9050 17600:17650);' <<<"$rules" && ok "ferm: desktop user's ports unchanged (no 9010)" || bad "user_ports changed"
if command -v ferm >/dev/null; then
  out=$(ferm --noexec --lines "$F" 2>&1) || true
  if grep -q 'thelounge-tor\|uid-owner' <<<"$out"; then
    grep -E 'Dropped thelounge-tor' <<<"$out" >/dev/null && ok "ferm renders the thelounge-tor rules" || bad "ferm render"
  else echo "SKIP ferm could not resolve the users here"; fi
else echo "SKIP ferm missing"; fi

## unit: the I2P unit's sandbox, for its own paths
S=$U/thelounge-tor.service; S0=$U/thelounge.service
for k in Type=simple User=thelounge-tor Group=thelounge-tor 'Environment=THELOUNGE_HOME=/var/lib/thelounge-tor NODE_ENV=production' \
  'Environment=PRESTIUM_LOUNGE_TOR=1 PRESTIUM_LOUNGE_LAUNCH=/run/prestium-thelounge-tor-launch' \
  'ExecStartPre=+/usr/local/sbin/prestium-thelounge-setup tor' \
  'ReadWritePaths=/var/lib/thelounge-tor -/run/prestium-thelounge-tor-launch' \
  'ReadOnlyPaths=/var/lib/thelounge-tor/config.js /var/lib/thelounge-tor/packages' \
  'InaccessiblePaths=-/run/tor -/run/onion-grater -/run/prestium-tbb' \
  'InaccessiblePaths=-/var/lib/thelounge -/run/prestium-thelounge -/run/prestium-thelounge-launch' \
  AppArmorProfile=thelounge-tor; do
  grep -qxF -- "$k" "$S" && ok "unit: $k" || bad "unit: no $k"; done
# every hardening line of the I2P unit is in the Tor unit too
n=0; while IFS= read -r l; do n=$((n+1)); grep -qxF -- "$l" "$S" || bad "unit: missing '$l' (thelounge.service has it)"; done < <(
  grep -E '^(UMask|NoNewPrivileges|CapabilityBoundingSet|Private|Protect|Restrict|LockPersonality|SystemCallArchitectures|IPAddress|ExecStart=|Environment=UV_USE_IO_URING|Restart)' "$S0")
[ "$n" -ge 20 ] && ok "unit: all $n sandbox lines of thelounge.service" || bad "unit: only $n lines compared"
grep -qxF 'AppArmorProfile=thelounge' "$U/thelounge.service.d/zz-apparmor.conf" && ok "I2P unit keeps its own profile" || bad "I2P profile"
grep -qxF 'InaccessiblePaths=-/var/lib/thelounge-tor -/run/prestium-thelounge-tor -/run/prestium-thelounge-tor-launch' "$U/thelounge.service.d/prestium-191.conf" \
  && ok "I2P unit: Tor instance's paths inaccessible" || bad "I2P unit: Tor paths"
grep -qxF '/etc/systemd/system/multi-user.target.wants/thelounge-tor.service /etc/systemd/system/thelounge-tor.service' "$I/usr/share/prestium/build/systemd-wants.txt" \
  && ok "systemd-wants: thelounge-tor enabled" || bad "systemd-wants"
grep -q '"$D"/thelounge-tor.service' "$R/tests/ci.sh" && ok "ci.sh scores thelounge-tor.service" || bad "ci.sh systemd-analyze"

## AppArmor
A=$I/etc/apparmor.d/prestium.thelounge-tor; A0=$I/etc/apparmor.d/prestium.thelounge
grep -qx 'profile thelounge-tor flags=(attach_disconnected) {' "$A" && ok "AppArmor: profile thelounge-tor, attach_disconnected" || bad "AppArmor header"
for l in '  /var/lib/thelounge-tor/** rwk,' '  /run/prestium-thelounge-tor-launch/{token,.token-*} rw,' '  deny /var/lib/thelounge-tor/config.js wl,' \
  '  deny /var/lib/thelounge-tor/packages{,/**} wl,' '  deny /var/lib/thelounge/** rwl,' '  deny /run/tor/** rw,' '  deny /run/prestium-tbb/** rw,' \
  '  include <abstractions/prestium-no-admin>' '  deny /home/** rw,'; do
  grep -qxF -- "$l" "$A" && ok "AppArmor: $l" || bad "AppArmor: no $l"; done
grep -q '/var/lib/thelounge/\*\* rwk\|prestium-thelounge-launch/{token' "$A" && bad "AppArmor: Tor profile may use the I2P instance's files" || ok "AppArmor: no I2P instance paths allowed"
grep -qxF '  deny /var/lib/thelounge-tor/** rwl,' "$A0" && ok "AppArmor: I2P profile denies the Tor instance" || bad "I2P profile deny"
# the same rules apart from paths and comments
norm(){ grep -vE '^\s*(#|$)' "$1" | grep -v 'deny ' | sed 's#thelounge-tor#thelounge#g; s#prestium-thelounge-tor-launch#prestium-thelounge-launch#g'; }
diff <(norm "$A0") <(norm "$A") >/dev/null && ok "AppArmor: same allow rules as the I2P profile" || { bad "AppArmor: allow rules differ"; diff <(norm "$A0") <(norm "$A"); }
grep -q 'prestium.thelounge prestium.thelounge-tor opt.firefox.firefox' "$R/config/hooks/live/0600-prestium-apparmor.hook.chroot" \
  && grep -q 'usr.lib.libreoffice.program prestium.thelounge prestium.thelounge-tor \\' "$R/config/hooks/live/0600-prestium-apparmor.hook.chroot" \
  && ok "hook 0600: enforced and checked for sudo denial" || bad "hook 0600"
grep -q ' thelounge thelounge-tor ' "$I/usr/local/bin/prestium-safety-notify" && ok "safety notify watches thelounge-tor" || bad "safety notify"
if command -v apparmor_parser >/dev/null; then
  W=$(mktemp -d); cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; cp -r "$I/etc/apparmor.d"/. "$W"/
  apparmor_parser -Q -K -b "$W" "$W/prestium.thelounge-tor" >/dev/null 2>"$T/aa.err" && ok "AppArmor profile compiles" || { bad "AppArmor compile"; cat "$T/aa.err"; }
  rm -rf "$W"
else echo "SKIP apparmor_parser missing"; fi

## perms
for l in '0644 root root /etc/systemd/system/thelounge-tor.service' '0644 root root /etc/apparmor.d/prestium.thelounge-tor' \
  '0644 root root /usr/local/share/prestium-thelounge-tor/prestium.json' '0644 root root /usr/share/applications/prestium-irc-tor.desktop' \
  '0640 root thelounge-tor /var/lib/thelounge-tor/config.js' '0700 thelounge-tor thelounge-tor /var/lib/thelounge-tor/'; do
  grep -qxF "$l" "$P" && ok "perms: $l" || bad "perms: no $l"; done
( cd "$I" && find var/lib/thelounge-tor usr/local/share/prestium-thelounge-tor -type f ) | while read -r f; do
  grep -q " /$f$" "$P" || echo "FAIL perms.txt misses /$f"; done | grep . && fail=1 || ok "every Tor instance file listed in perms.txt"
B=$R/config/hooks/live/0500-prestium-permissions.hook.chroot
grep -q 'cp -R /var/lib/thelounge/packages "$TP"' "$B" && grep -q 'chown -R root:thelounge-tor "$TP"' "$B" \
  && grep -q 'find "$TP" -type d -exec chmod 0750' "$B" && grep -q 'find "$TP" -type f -exec chmod 0640' "$B" \
  && ok "hook 0500: root-owned read-only copy of the packages for thelounge-tor" || bad "hook 0500 packages copy"
# the copy step works (as the build runs it, without chown)
mkdir -p "$T/root/var/lib/thelounge-tor"; cp -R "$I/var/lib/thelounge" "$T/root/var/lib/"
sed -n '/^TP=\/var\/lib\/thelounge-tor\/packages$/,/|| { echo "E: \$TP incomplete"; exit 1; }/p' "$B" \
  | sed "s#/var/lib/#$T/root/var/lib/#g; s#^chown .*#:#" > "$T/copy.sh"
sh -e "$T/copy.sh" && [ -f "$T/root/var/lib/thelounge-tor/packages/node_modules/thelounge-theme-tech-innovation/theme.css" ] \
  && [ "$(find "$T/root/var/lib/thelounge-tor/packages" -type f ! -perm 0640 | wc -l)" = 0 ] \
  && [ "$(find "$T/root/var/lib/thelounge-tor/packages" -type d ! -perm 0750 | wc -l)" = 0 ] \
  && ok "hook 0500 copy: themes and sign-in page, 0750/0640" || bad "hook 0500 copy step"

## config.js and presets
C=$I/var/lib/thelounge-tor/config.js; C0=$I/var/lib/thelounge/config.js; J=$I/usr/local/share/prestium-thelounge-tor/prestium.json
if command -v node >/dev/null; then
  node - "$C" "$C0" "$J" "$I/etc/tor/torrc" "$I/usr/local/share/prestium-thelounge/prestium.json" <<'JS' && ok "config.js: 127.0.0.1:9010, OFTC default through 127.0.0.1:9050; 7 presets (no account first, no Pirate IRC), all through Tor" || bad "config.js / presets"
const [c, c0, j, torrc, j0] = process.argv.slice(2).map((f, i) => i < 2 ? require(f) : require("fs").readFileSync(f, "utf8"));
const assert = require("assert");
assert.strictEqual(c.port, 9010); assert.strictEqual(c.host, "127.0.0.1"); assert.strictEqual(c.public, false);
for (const k of ["prefetch", "prefetchStorage", "disableMediaPreview", "theme", "lockNetwork", "webirc", "identd", "oidentd", "ldap", "fileUpload", "messageStorage", "storagePolicy", "useHexIp", "reverseProxy", "https", "debug", "transports", "leaveMessage"])
	assert.deepStrictEqual(c[k], c0[k], k);
assert.deepStrictEqual(Object.keys(c).sort(), Object.keys(c0).sort());
assert.strictEqual(c.theme, "thelounge-theme-tech-innovation");
const d = c.defaults;
assert.strictEqual(d.name, "OFTC"); assert.strictEqual(d.host, "oftcnet6xg6roj6d7id4y4cu6dchysacqj2ldgea73qzdagufflqxrid.onion");
assert.strictEqual(d.port, 6697); assert.strictEqual(d.tls, true); assert.strictEqual(d.nick, c0.defaults.nick);
assert.strictEqual(d.proxyEnabled, true); assert.strictEqual(d.proxyHost, "127.0.0.1"); assert.strictEqual(d.proxyPort, 9050);
const p = JSON.parse(j);
// 2.1: networks that need no account first, then the SASL ones; Pirate IRC removed.
// [host, port, tls, rejectUnauthorized, sasl]
const want = {
	"OFTC": ["oftcnet6xg6roj6d7id4y4cu6dchysacqj2ldgea73qzdagufflqxrid.onion", 6697, true, false, ""],
	"Ergo": ["vrw7zcuarwx4oeju3iikiz3jffrvuijsysyznqf53mxizxrebomfnrid.onion", 6667, false, true, ""],
	"DarkScience": ["darkirc6tqgpnwd3blln3yfv5ckl47eg7llfxkmtovrv7c7iwohhb6ad.onion", 6667, false, true, ""],
	"IRCNow": ["4ufrikyorlatp5ekgz6tlre22v6b5jxqbiid6cp7nuhemklukiohidqd.onion", 6667, false, true, ""],
	"Libera.Chat (SASL certificate)": ["palladium.libera.chat", 6697, true, true, "external"],
	"hackint (SASL optional)": ["guybrush.hackint.org", 6697, true, true, ""],
	"AlphaChat (SASL)": ["irc.alphachat.net", 6697, true, true, "plain"],
};
assert.ok(!/pirate/i.test(j), "Pirate IRC still in the presets");
assert.deepStrictEqual(p.networks.map(n => n.name), Object.keys(want));
const maps = {};
for (const l of torrc.split("\n")) { const m = l.match(/^MapAddress (\S+) ([a-z2-7]{56}\.onion)$/); if (m) maps[m[1]] = m[2]; }
for (const n of p.networks) {
	const [host, port, tls, rej, sasl] = want[n.name];
	assert.deepStrictEqual([n.host, n.port, n.tls, n.rejectUnauthorized, n.sasl], [host, port, tls, rej, sasl], n.name);
	// no account or password ships in the image: each user brings their own
	assert.deepStrictEqual([n.saslAccount, n.saslPassword, n.password], ["", "", ""], n.name);
	assert.strictEqual(n.proxyEnabled, true, n.name); assert.strictEqual(n.proxyHost, "127.0.0.1"); assert.strictEqual(n.proxyPort, 9050);
	assert.strictEqual(n.userDisconnected, true, n.name); assert.deepStrictEqual(n.channels, []);
	// every server is an onion service: an .onion name, or a name torrc maps to one
	assert.ok(/^[a-z2-7]{56}\.onion$/.test(n.host) || maps[n.host], n.name + ": not an onion service");
	// certificate checking is off only where the certificate can't match (OFTC's onion)
	if (n.tls && !n.rejectUnauthorized) assert.strictEqual(n.name, "OFTC");
}
assert.strictEqual(p.networks.find(n => n.name.startsWith("Libera")).sasl, "external");
assert.deepStrictEqual(Object.keys(p).sort(), Object.keys(JSON.parse(j0)).sort());
assert.deepStrictEqual(Object.keys(p.networks[0]).sort(), Object.keys(JSON.parse(j0).networks[0]).sort());
JS
else echo "SKIP node missing (config.js)"; fi

## torrc
TR=$I/etc/tor/torrc
for l in 'MapAddress palladium.libera.chat libera75jm6of4wxpxt4aynol3xjmbtxgfyjpu34ss4d7r7q2v5zrpyd.onion' \
  'MapAddress guybrush.hackint.org dtlbunzs5b7s5sl775quwezleyeplxzicdoh3cnhm7feolxmkfd42nqd.onion' \
  'MapAddress irc.alphachat.net rnjlael46gqqmfiuiqsswdeev6axrf47j7bq4dtuqdsv2qgqfumcy4yd.onion'; do
  grep -qxF "$l" "$TR" && ok "torrc: $l" || bad "torrc: no $l"; done
[ "$(grep -c '^MapAddress ' "$TR")" = 3 ] && ok "torrc: exactly 3 MapAddress lines, all to .onion" || bad "torrc MapAddress count"
grep -qi 'pirate' "$TR" && bad "torrc still mentions Pirate IRC" || ok "torrc: no Pirate IRC"
git -C "$R" grep -qi 'pirateirc\|pirate irc' -- . ':!CHANGELOG.md' ':!tests/test_thelounge_tor.sh' && bad "Pirate IRC still named outside the CHANGELOG" || ok "Pirate IRC gone (CHANGELOG notes the removal)"
grep -qx 'SocksPort 127.0.0.1:9050 IsolateDestAddr IsolateDestPort IsolateSOCKSAuth' "$TR" && grep -q '^SocksPort unix:/run/prestium-tbb/socks WorldWritable ExtendedErrors KeepAliveIsolateSOCKSAuth$' "$TR" \
  && grep -qx '%include /etc/tor/torrc.d/\*.conf' "$TR" && ok "torrc: SocksPorts and drop-in include unchanged" || bad "torrc existing options"

## setup script
SU=$I/usr/local/sbin/prestium-thelounge-setup
grep -q 'tor: {name: "thelounge-tor", home: "/var/lib/thelounge-tor", template: "/usr/local/share/prestium-thelounge-tor/prestium.json",' "$SU" \
  && grep -q 'run: "/run/prestium-thelounge-tor", launch: "/run/prestium-thelounge-tor-launch", tor: true}' "$SU" \
  && grep -q 'n.proxyPort = 9050;' "$SU" && grep -q 'n.proxyUsername = "prestium-" + crypto.randomBytes(12)' "$SU" \
  && ok "setup: Tor instance paths, proxy and fresh SOCKS username per network" || bad "setup script"

## launcher, local-only Firefox, menu
IRC=$I/usr/local/bin/prestium-irc
grep -qxF '  tor) N="IRC (Tor)"; SVC=thelounge-tor.service; PORT=9010; TOK=/run/prestium-thelounge-tor-launch/token ;;' "$IRC" && ok "prestium-irc tor: service, port, token" || bad "prestium-irc tor"
mkdir -p "$T/home" "$T/run"; tok=$(head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n'); echo "$tok" > "$T/run/token"
printf '#!/bin/sh\nprintf "%%s\\n" "$@" > %s/argv; cat "${1#file://}" > %s/page\n' "$T" "$T" > "$T/localfox"; chmod 755 "$T/localfox"
printf '#!/bin/sh\necho "$@" >> %s/systemctl.log; exit 0\n' "$T" > "$T/systemctl"; chmod 755 "$T/systemctl"
sed "s#/run/prestium-thelounge-tor-launch/token#$T/run/token#; s#/usr/local/bin/prestium-localfox#$T/localfox#; s#( sleep 120;#( sleep 1;#" "$IRC" > "$T/irc"
HOME=$T/home PATH=$T:/usr/bin:/bin sh "$T/irc" tor >/dev/null 2>&1
grep -q "127.0.0.1:9010/packages/thelounge-prestium-autologin/autologin.html#$tok" "$T/page" 2>/dev/null && ok "prestium-irc tor: one-off page to 127.0.0.1:9010" || bad "prestium-irc tor page"
grep -q "$tok" "$T/argv" 2>/dev/null && bad "token in localfox's argv" || ok "prestium-irc tor: token not in the command line"
grep -q 'thelounge-tor.service' "$T/systemctl.log" 2>/dev/null && ok "prestium-irc tor: checks thelounge-tor.service" || bad "prestium-irc tor service check"
HOME=$T/home PATH=$T:/usr/bin:/bin sh "$T/irc" bogus >/dev/null 2>&1; [ $? = 2 ] && ok "prestium-irc: unknown instance refused" || bad "prestium-irc bogus"
grep -q 'http://127.0.0.1:9000/\*|http://127.0.0.1:9010/\*) ;;' "$I/usr/local/bin/prestium-localfox" && ok "prestium-localfox: allows 127.0.0.1:9010" || bad "localfox 9010"
M=$I/etc/xdg/labwc/menu.xml
python3 - "$M" <<'PY' && ok "menu: Communication has IRC (I2P) and IRC (Tor), same icon" || bad "menu entries"
import sys, xml.etree.ElementTree as E
m = E.parse(sys.argv[1]).getroot()
c = [x for x in m.iter("menu") if x.get("id") == "/Communication"][0]
items = {i.get("label"): (i.get("icon"), i.find("action").get("command")) for i in c.findall("item")}
assert items["IRC (I2P)"] == ("irc-chat", "prestium-run /usr/local/bin/prestium-irc"), items
assert items["IRC (Tor)"] == ("irc-chat", "prestium-run /usr/local/bin/prestium-irc tor"), items
labels = [i.get("label") for i in c.findall("item")]
assert labels.index("IRC (Tor)") == labels.index("IRC (I2P)") + 1
assert not any("The Lounge" in (i.get("label") or "") for i in m.iter("item"))
PY
grep -qx 'Name=IRC (I2P)' "$I/usr/share/applications/prestium-irc.desktop" && grep -qx 'Name=IRC (Tor)' "$I/usr/share/applications/prestium-irc-tor.desktop" \
  && grep -qx 'Exec=/usr/local/bin/prestium-irc tor' "$I/usr/share/applications/prestium-irc-tor.desktop" && ok "desktop entries IRC (I2P), IRC (Tor)" || bad "desktop entries"
git -C "$R" grep -n 'The Lounge (IRC, I2P)' -- . ':!CHANGELOG.md' ':!tests/test_thelounge_tor.sh' >/dev/null && bad "old label 'The Lounge (IRC, I2P)' still used" || ok "old label gone"
grep -q 'IRC (Tor)' "$R/README.md" && grep -q '\*\*New: IRC (Tor)\*\*' "$R/CHANGELOG.md" && ok "README and CHANGELOG describe IRC (Tor)" || bad "docs"

## hook 0200: every network through Tor (fixture with the exact 4.5.2 text)
sed -n '/^python3 - "\$NS"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/patch.py"
grep -q 'PRESTIUM_LOUNGE_TOR' "$T/patch.py" && ok "hook patch (Tor SOCKS) extracted" || { bad "could not extract the Tor SOCKS patch"; exit 1; }
grep -q '/opt/nodejs/bin/node --check "$NS"' "$H" && ok "hook 0200: patched network.js syntax-checked" || bad "no node --check"
cat > "$T/network.js" <<'JS'
"use strict";
class Network {
    setIrcFrameworkOptions(client) {
        this.irc.options.host = this.host;
        this.irc.options.port = this.port;
        if (this.proxyEnabled) {
            this.irc.options.socks = {
                host: this.proxyHost,
                port: this.proxyPort,
                user: this.proxyUsername,
                pass: this.proxyPassword,
            };
        }
        else {
            delete this.irc.options.socks;
        }
    }
}
module.exports = Network;
JS
cp "$T/network.js" "$T/orig.js"
python3 "$T/patch.py" "$T/network.js" >/dev/null && ok "patch applies" || bad "patch failed"
cp "$T/network.js" "$T/once.js"; python3 "$T/patch.py" "$T/network.js" >/dev/null && cmp -s "$T/network.js" "$T/once.js" && ok "second run is a no-op" || bad "patch not idempotent"
printf 'x\n' > "$T/changed.js"; python3 "$T/patch.py" "$T/changed.js" >/dev/null 2>&1 && bad "changed upstream text passes" || ok "changed upstream text stops the build"
if command -v node >/dev/null; then
  node --check "$T/network.js" && ok "patched file parses" || bad "patched file does not parse"
  node - "$T/network.js" <<'JS' && ok "Tor instance: every network via 127.0.0.1:9050, own SOCKS user; I2P instance unchanged" || bad "patched behaviour"
const N = require(process.argv[2]); const assert = require("assert");
const run = (env, net) => { if (env) process.env.PRESTIUM_LOUNGE_TOR = env; else delete process.env.PRESTIUM_LOUNGE_TOR;
	const n = Object.assign(new N(), {irc: {options: {}}, host: "palladium.libera.chat", port: 6697, uuid: "u1"}, net); n.setIrcFrameworkOptions({}); return n.irc.options; };
let o = run("1", {proxyEnabled: false, proxyHost: "", proxyPort: 1080, proxyUsername: "", proxyPassword: ""});
assert.deepStrictEqual(o.socks, {host: "127.0.0.1", port: 9050, user: "prestium-u1", pass: "prestium"});
assert.strictEqual(o.host, "palladium.libera.chat");   // the name, never an address: Tor resolves it
o = run("1", {proxyEnabled: true, proxyHost: "203.0.113.5", proxyPort: 1080, proxyUsername: "prestium-a", proxyPassword: "b"});
assert.deepStrictEqual(o.socks, {host: "127.0.0.1", port: 9050, user: "prestium-a", pass: "b"});
o = run(undefined, {proxyEnabled: false}); assert.strictEqual(o.socks, undefined);
o = run(undefined, {proxyEnabled: true, proxyHost: "127.0.0.1", proxyPort: 4447, proxyUsername: "x", proxyPassword: "y"});
assert.deepStrictEqual(o.socks, {host: "127.0.0.1", port: 4447, user: "x", pass: "y"});
JS
fi
grep -q 'process.env.PRESTIUM_LOUNGE_LAUNCH === "/run/prestium-thelounge-tor-launch"' "$H" && ok "hook 0200: Tor instance's launch token directory (fixed choice of two)" || bad "launch dir patch"
grep -q '(process.env.PRESTIUM_LOUNGE_TOR === "1" ? "Tor" : "I2P")' "$H" && ok "hook 0200: lobby text names Tor in the Tor instance" || bad "lobby text"

## with a real The Lounge tree: hook patches, remote DNS, setup script
TL=${PRESTIUM_TL_TREE:-}
if [ -z "$TL" ] && [ -s "$I/usr/src/prestium-thirdparty/thelounge.tar" ] && command -v node >/dev/null; then
  mkdir -p "$T/opt"; tar -xf "$I/usr/src/prestium-thirdparty/thelounge.tar" -C "$T/opt"; TL=$T/opt; fi
if [ -z "$TL" ] || ! command -v node >/dev/null; then echo "SKIP no The Lounge tree (PRESTIUM_TL_TREE or staged thelounge.tar) or node"; exit $fail; fi
# only The Lounge itself is patched (a copy); irc-framework, socks and bcryptjs are read in place
NM=$TL/node_modules; mkdir -p "$T/tl"; cp -R "$NM/thelounge/dist" "$T/tl/dist"; D=$T/tl/dist/server
NJ=$NM/irc-framework/src/transports/net.js
grep -q '^        if (options.socks) {$' "$NJ" && sed -n '/SocksClient.createConnection({/,/}).then/p' "$NJ" | grep -q '^                    host: ircd_host,$' \
  && ok "irc-framework: SOCKS destination is the configured host name ($(grep -n '                    host: ircd_host,' "$NJ" | head -1 | cut -d: -f1): host: ircd_host)" || bad "irc-framework SOCKS destination"
SC=$NM/socks/build/client/socksclient.js
sed -n '/sendSocks5CommandRequest() {/,/^    }/p' "$SC" | grep -q 'buff.writeUInt8(constants_1.Socks5HostType.Hostname);' \
  && ! grep -q "require('dns')\|require(\"dns\")" "$SC" && ok "socks $(node -p "require('$NM/socks/package.json').version"): a name goes to the proxy as ATYP 3 (domain), no local DNS" || bad "socks remote DNS"
sed -n '/^python3 - "\$P\/changelog.js"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/p1.py"
sed -n '/^python3 - "\$N"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/p2.py"
PP=$D/plugins
python3 "$T/p1.py" "$PP/changelog.js" "$PP/packages/index.js" "$D/client.js" "$D/server.js" >/dev/null \
  && python3 "$T/p2.py" "$D/models/network.js" >/dev/null && python3 "$T/patch.py" "$D/models/network.js" >/dev/null \
  && node --check "$D/models/network.js" && node --check "$D/client.js" && node --check "$D/server.js" \
  && ok "hook 0200 patches apply to The Lounge $(node -p "require('$NM/thelounge/package.json').version")" || bad "hook patches on the real tree"
grep -q '"Not connected (Prestium never connects automatically). When " + (process.env.PRESTIUM_LOUNGE_TOR === "1" ? "Tor" : "I2P") + " is ready,' "$D/client.js" \
  && ok "client.js: lobby text per instance" || bad "client.js lobby text"
# setup script in a temp root: own uid as thelounge-tor and group user; root-only calls stubbed
mkdir -p "$T/sr/etc" "$T/sr/share" "$T/sr/run" "$T/sr/var"
echo "thelounge-tor:x:$(id -u):$(id -g)::/x:/bin/false" > "$T/sr/etc/passwd"; echo "user:x:$(id -g):" > "$T/sr/etc/group"
cp "$J" "$T/sr/share/prestium.json"
sed -e "s#\"/etc/passwd\"#\"$T/sr/etc/passwd\"#; s#\"/etc/group\"#\"$T/sr/etc/group\"#" \
    -e "s#/usr/local/share/prestium-thelounge-tor/prestium.json#$T/sr/share/prestium.json#" \
    -e "s#\"/var/lib/thelounge-tor\"#\"$T/sr/var/thelounge-tor\"#; s#\"/run/prestium-thelounge-tor\"#\"$T/sr/run/tl\"#; s#\"/run/prestium-thelounge-tor-launch\"#\"$T/sr/run/launch\"#" \
    -e "s#/opt/thelounge/node_modules/bcryptjs#$NM/bcryptjs#" \
    -e 's#process\.set\(groups\|egid\|euid\)(#((x) => x)(#g' -e 's#fs\.\(fchownSync\|chownSync\)(#((...a) => a)(#g' \
    -e "s#fs.rmSync(RUN + \"/token\"#fs.rmSync(\"$T/sr/run/tl/token\"#" "$SU" > "$T/setup.js"
node "$T/setup.js" tor >/dev/null 2>"$T/setup.err" || { bad "setup tor: $(cat "$T/setup.err")"; exit 1; }
cp "$T/sr/var/thelounge-tor/users/prestium.json" "$T/u1.json"; node "$T/setup.js" tor >/dev/null 2>&1
node - "$T/u1.json" "$T/sr/var/thelounge-tor/users/prestium.json" "$T/sr/run/launch/token" <<'JS' && ok "setup tor: random nicks, all disconnected, all via 127.0.0.1:9050, fresh SOCKS user per network and start, launch token" || bad "setup tor result"
const fs = require("fs"), assert = require("assert"), crypto = require("crypto");
const [a, b] = [0, 1].map(i => JSON.parse(fs.readFileSync(process.argv[2 + i], "utf8")));
const tok = fs.readFileSync(process.argv[4], "utf8").trim();
assert.ok(/^[0-9a-f]{128}$/.test(tok));
const h = crypto.createHash("sha512").update(tok).digest("hex");
assert.ok(b.sessions[h] && b.sessions[h].prestiumLaunch === true);
for (const u of [a, b]) {
	assert.strictEqual(u.networks.length, 7);
	assert.strictEqual(new Set(u.networks.map(n => n.nick)).size, 7);
	assert.strictEqual(new Set(u.networks.map(n => n.proxyUsername)).size, 7);
	for (const n of u.networks) {
		assert.ok(/^anon\d{4}$/.test(n.nick)); assert.strictEqual(n.userDisconnected, true);
		assert.deepStrictEqual([n.proxyEnabled, n.proxyHost, n.proxyPort], [true, "127.0.0.1", 9050]);
		assert.ok(/^prestium-[0-9a-f]{24}$/.test(n.proxyUsername) && /^[0-9a-f]{24}$/.test(n.proxyPassword));
	}
}
a.networks.forEach((n, i) => { assert.strictEqual(n.nick, b.networks[i].nick); assert.notStrictEqual(n.proxyUsername, b.networks[i].proxyUsername); });
JS
node "$T/setup.js" bogus >/dev/null 2>&1 && bad "setup accepts an unknown instance" || ok "setup refuses an unknown instance"
exit $fail
