#!/bin/bash
# Prestium 2.1: apps opened from the panel start outside prestium-wl-broker.service. waybar lives in the
# broker's unit, whose RestrictAddressFamilies/RestrictNamespaces seccomp filters every child inherits
# (no IP sockets: Refresh reseed via Tor; no namespaces: bwrap for Tor Browser, I2P Browser, Loupe, mat2).
# prestium-launch starts them as transient units of the user's systemd manager. Verified in a VM with
# waybar in the broker's sandbox (Seccomp 0 in the app, bwrap running); this checks the wiring.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; fail=0
ok() { echo "OK   $*"; }; bad() { echo "FAIL $*"; fail=1; }
L=$I/usr/local/bin/prestium-launch
[ -x "$L" ] && sh -n "$L" && ok "prestium-launch is an executable shell script" || bad "prestium-launch"
grep -qxF '0755 root root /usr/local/bin/prestium-launch' "$I/usr/share/prestium/build/perms.txt" && ok "perms" || bad "perms"
# every waybar click that opens something goes through prestium-launch (or asks the broker / pactl)
python3 - "$I/etc/xdg/waybar/config.jsonc" <<'PY' && ok "waybar: every app click uses prestium-launch" || bad "waybar click without prestium-launch"
import json, re, sys
txt = re.sub(r'^\s*//.*$', '', open(sys.argv[1]).read(), flags=re.M)
bars = json.loads(txt); bars = bars if isinstance(bars, list) else [bars]
allowed_internal = {"activate", "close", "minimize", "maximize", "minimize-raise"}
broker_ok = ("/usr/local/bin/prestium-wl ", "/usr/local/bin/prestium-media-key ")
bad = []; n = 0
for bar in bars:
    for name, mod in bar.items():
        if not isinstance(mod, dict): continue
        for k, v in mod.items():
            if k.startswith("on-") and isinstance(v, str):
                n += 1
                if v in allowed_internal or v.startswith(broker_ok): continue
                if not v.startswith("/usr/local/bin/prestium-launch "): bad.append((name, k, v))
assert n >= 6 and not bad, bad
PY
for c in "prestium-launch /usr/local/bin/prestium-tor-assistant" "prestium-launch /usr/local/bin/prestium-i2p-assistant" \
         "prestium-launch pavucontrol --tab=1" "prestium-launch /usr/local/bin/prestium-power-menu"; do
  grep -qF "\"/usr/local/bin/$c\"" "$I/etc/xdg/waybar/config.jsonc" && ok "waybar: $c" || bad "waybar: $c missing"; done
grep -q '"/usr/local/bin/prestium-launch", "tor-browser", MANUAL_URL' "$I/usr/local/bin/prestium-i2p-reseed-gui" \
  && ok "reseed failure: Open in Tor Browser uses prestium-launch" || bad "reseed GUI tor-browser launch"
# the user manager gets every variable prestium-session exports (apps from the panel see the session's settings)
A=$I/etc/xdg/labwc/autostart
imp=$(awk '/^dbus-update-activation-environment/{f=1} f{print} f&&!/\\$/{exit}' "$A" | tr -d '\\\n')
vars=$(sed -e ':a' -e '/\\$/N; s/\\\n//; ta' "$I/usr/local/bin/prestium-session" | grep -oE '^export [^#]*' | sed 's/^export //' | grep -oE '(^| )[A-Z_][A-Z0-9_]*=' | tr -d ' =')
[ "$(wc -w <<<"$vars")" -ge 15 ] || bad "could not read prestium-session's exports"
for v in $vars; do
  case $v in WLR_*) continue ;; esac
  grep -qw -- "$v" <<<"$imp" || bad "autostart does not import $v into the user manager"; done
grep -q -- '--systemd' <<<"$imp" && ok "autostart imports the session environment into the user manager" || bad "no --systemd import"
# behaviour, with stub systemd-run and prestium-run
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
mkdir -p "$W/bin" "$W/home"
printf '#!/bin/sh\nprintf "%%s\\n" "$@" > "%s/sr.args"\nexit ${SR_RC:-0}\n' "$W" > "$W/bin/systemd-run"
printf '#!/bin/sh\necho "direct $*"\n' > "$W/prun"; printf '#!/bin/sh\n:\n' > "$W/bin/logger"
chmod +x "$W/bin/systemd-run" "$W/prun" "$W/bin/logger"
sed "s#/usr/local/bin/prestium-run#$W/prun#g" "$L" > "$W/launch"
out=$(HOME=$W/home PATH=$W/bin:/usr/bin:/bin sh "$W/launch" /usr/local/bin/prestium-i2p-assistant --x 'a b'); rc=$?
[ $rc = 0 ] && [ -z "$out" ] && ok "started through the user manager" || bad "launch rc=$rc out=$out"
a=$(cat "$W/sr.args" 2>/dev/null)
for f in --user --collect --no-block --service-type=exec -p 'WorkingDirectory=~' StandardOutput=null StandardError=null; do
  grep -qxF -- "$f" <<<"$a" || bad "systemd-run without $f"; done
grep -qE '^--unit=app-prestium-i2p-assistant-[0-9a-f]{8}$' <<<"$a" && ok "unit app-prestium-<name>-<random>" || bad "unit name: $(grep unit <<<"$a")"
[ "$(sed -n '/^--$/,$p' <<<"$a" | tail -n +2)" = "$(printf '%s\n' "$W/prun" /usr/local/bin/prestium-i2p-assistant --x 'a b')" ] \
  && ok "runs prestium-run COMMAND ARGS (arguments kept)" || bad "command line: $a"
grep -q -- '--scope' <<<"$a" && bad "a scope keeps the caller's seccomp filter" || ok "a service, not a scope (a scope would keep the broker's filters)"
out=$(SR_RC=1 HOME=$W/home PATH=$W/bin:/usr/bin:/bin sh "$W/launch" pavucontrol --tab=1)
[ "$out" = "direct pavucontrol --tab=1" ] && ok "no user manager: starts it directly" || bad "fallback: $out"
out=$(HOME=$W/home PATH=$W/bin:/usr/bin:/bin sh "$W/launch" '/x/we ird$(name)'); grep -qE '^--unit=app-prestium-we_ird__name_-[0-9a-f]{8}$' "$W/sr.args" \
  && ok "unit name sanitised" || bad "unit name: $(grep unit "$W/sr.args")"
sh "$W/launch" >/dev/null 2>&1; [ $? = 2 ] && ok "usage without a command" || bad "usage"
exit $fail
