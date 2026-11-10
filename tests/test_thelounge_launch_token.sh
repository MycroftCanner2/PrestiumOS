#!/bin/bash
# 2.1 (review of the security audit): The Lounge's launcher sign-in token works once. Applies hook
# 0200's patch to the real, pinned The Lounge (the staged tarball), runs it on a free port and signs
# in over socket.io: the launch token is accepted once, the browser gets its own token, the next
# launch token is written (group-readable file, only its hash in the user file) and works once too.
# Also checks prestium-irc keeps the token out of the command line. Needs node and the staged
# thelounge.tar (scripts/fetch-thirdparty.sh); SKIPs the live part otherwise.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=$R/config/hooks/live/0200-prestium-thirdparty.hook.chroot
IRC=$I/usr/local/bin/prestium-irc; LF=$I/usr/local/bin/prestium-localfox; S=$I/usr/local/sbin/prestium-thelounge-setup
grep -q 'prestium-thelounge-launch/token' "$IRC" && ok "prestium-irc: reads the one-use token" || bad "prestium-irc token path"
grep -v '^ *#' "$IRC" | grep -q 'prestium-localfox "http[^"]*#\$T' && bad "prestium-irc: token in the command line" || ok "prestium-irc: token not in the command line"
grep -q 'exec /usr/local/bin/prestium-localfox "file://$F"' "$IRC" && ok "prestium-irc: opens a one-off page" || bad "prestium-irc handoff"
grep -q 'irc-launch/"\*.html) ;;' "$LF" && ok "prestium-localfox: allows only that page's directory" || bad "localfox file URL"
grep -q 'file:///home/user/.local/share/prestium-localfox/irc-launch/\*' "$I/usr/share/prestium/opt-overlay/firefox/distribution/policies.json" && ok "policy: file exception for that directory only" || bad "policy"
grep -q 'prestiumLaunch: true' "$S" && grep -q 'LAUNCH, luid, ugid, 0o2750' "$S" && ok "setup: marked launch session, setgid launch directory" || bad "setup"
grep -q -- '-/run/prestium-thelounge-launch' "$I/etc/systemd/system/thelounge.service" && ok "unit: launch directory writable" || bad "unit"
grep -q '/run/prestium-thelounge-launch/{token,.token-\*} rw' "$I/etc/apparmor.d/prestium.thelounge" && ok "AppArmor: launch token file" || bad "AppArmor"
# handoff page: dynamic, with a stub localfox
T=$(mktemp -d); trap 'kill $TLPID 2>/dev/null; rm -rf "$T"' EXIT; TLPID=
mkdir -p "$T/home" "$T/run"; tok=$(head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n')
printf '#!/bin/sh\nprintf "%%s\\n" "$@" > %s/argv; cat "${1#file://}" > %s/page\n' "$T" "$T" > "$T/localfox"; chmod 755 "$T/localfox"
printf '#!/bin/sh\nexit 0\n' > "$T/systemctl"; chmod 755 "$T/systemctl"
echo "$tok" > "$T/run/token"
sed "s#/run/prestium-thelounge-launch/token#$T/run/token#; s#/usr/local/bin/prestium-localfox#$T/localfox#; s#( sleep 120;#( sleep 1;#" "$IRC" > "$T/irc"
HOME=$T/home PATH=$T:/usr/bin:/bin sh "$T/irc" >/dev/null 2>&1
grep -q "$tok" "$T/argv" 2>/dev/null && bad "token in localfox's argv" || ok "token not in localfox's argv"
grep -q "autologin.html#$tok" "$T/page" 2>/dev/null && ok "one-off page forwards with the token" || bad "page content"
f=$(sed -n 's#^file://##p' "$T/argv"); [ "$(stat -c %a "$(dirname "$f")")" = 700 ] && ok "page directory 0700" || bad "page dir mode"
sleep 2; [ -e "$f" ] && bad "page not deleted" || ok "page deleted afterwards"
# live: the patched The Lounge
TAR=$I/usr/src/prestium-thirdparty/thelounge.tar
command -v node >/dev/null && [ -s "$TAR" ] || { echo "SKIP node or staged thelounge.tar missing (live sign-in)"; exit $fail; }
mkdir -p "$T/opt" "$T/tlhome/users" "$T/launch"; tar -xf "$TAR" -C "$T/opt"
P=$T/opt/node_modules/thelounge/dist/server/plugins
sed -n '/^python3 - "$P\/changelog.js"/,/^PY$/p' "$H" | sed '1d;$d' > "$T/patch.py"
python3 "$T/patch.py" "$P/changelog.js" "$P/packages/index.js" "$P/../client.js" "$P/../server.js" >/dev/null && ok "hook patch applies to The Lounge $(node -p "require('$T/opt/node_modules/thelounge/package.json').version")" || { bad "hook patch"; exit 1; }
sed -i "s#\"/run/prestium-thelounge-launch\"#\"$T/launch\"#" "$P/../server.js"
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
printf 'module.exports = {public: false, host: "127.0.0.1", port: %s, prefetch: false, fileUpload: {enable: false}, transports: ["websocket"]};\n' "$PORT" > "$T/tlhome/config.js"
H0=$(printf %s "$tok" | sha512sum | cut -c1-128)
cat > "$T/tlhome/users/prestium.json" <<J
{"log": false, "password": "\$2a\$10\$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu", "sessions": {"$H0": {"lastUse": 1, "ip": "127.0.0.1", "agent": "Prestium launcher", "prestiumLaunch": true}}, "clientSettings": {}, "browser": {}, "networks": []}
J
THELOUNGE_HOME=$T/tlhome node "$T/opt/node_modules/thelounge/index.js" start >"$T/tl.log" 2>&1 & TLPID=$!
for i in $(seq 100); do (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break; sleep 0.1; done
C(){ node "$R/tests/thelounge_launch_client.js" "$T/opt/node_modules/ws" "$PORT" prestium "$1"; }
r1=$(C "$tok"); echo "$r1" | grep -q '"ok":true' && ok "launch token signs in" || bad "launch token: $r1 $(tail -3 "$T/tl.log")"
bt=$(echo "$r1" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("initToken") or "")')
[ ${#bt} -eq 128 ] && [ "$bt" != "$tok" ] && ok "browser gets its own session token" || bad "no new browser token"
r2=$(C "$tok"); echo "$r2" | grep -q '"ok":false' && ok "launch token refused the second time" || bad "launch token reusable: $r2"
r3=$(C "$bt"); echo "$r3" | grep -q '"ok":true' && echo "$r3" | grep -q '"initToken":null' && ok "browser token keeps working (reconnect)" || bad "browser token: $r3"
sleep 0.5; nt=$(tr -d '\n' < "$T/launch/token" 2>/dev/null)
[ ${#nt} -eq 128 ] && [ "$nt" != "$tok" ] && ok "next launch token written" || bad "no next launch token"
[ "$(stat -c %a "$T/launch/token" 2>/dev/null)" = 640 ] && ok "next launch token file 0640" || bad "launch token mode"
# The Lounge saves the user file 5 s after the last change (debounced)
sleep 6; U=$T/tlhome/users/prestium.json
python3 - "$U" "$tok" "$nt" <<'PY' && ok "user file: old launch session gone, only the new one's hash, marked" || bad "user file sessions"
import json,sys,hashlib
s=json.load(open(sys.argv[1]))["sessions"]; h=lambda t: hashlib.sha512(t.encode()).hexdigest()
assert h(sys.argv[2]) not in s; assert s[h(sys.argv[3])]["prestiumLaunch"] is True
assert sys.argv[3] not in json.dumps(s)
assert sum(1 for v in s.values() if v.get("prestiumLaunch")) == 1
PY
r4=$(C "$nt"); echo "$r4" | grep -q '"ok":true' && ok "next launch token signs in" || bad "next token: $r4"
r5=$(C "$nt"); echo "$r5" | grep -q '"ok":false' && ok "and works only once" || bad "next token reusable"
exit $fail
