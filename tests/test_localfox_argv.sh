#!/bin/bash
# Prestium 2.1: prestium-localfox passes the profile path and URL to Firefox as arguments, never inside a
# shell command string, so a HOME with a single quote (or other shell syntax) cannot change the command.
# Runs the launcher with stubs on PATH: id (not yet in prestium-localweb), cp, and an sg that runs its -c
# string with sh exactly as sg does, but with a recorder in place of /opt/firefox/firefox.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
LF=$R/config/includes.chroot/usr/local/bin/prestium-localfox
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
mkdir -p "$T/bin"
printf '#!/bin/sh\necho user\n' > "$T/bin/id"
printf '#!/bin/sh\nexit 0\n' > "$T/bin/cp"
cat > "$T/bin/rec" <<'R'
#!/bin/sh
for a in "$@"; do printf '%s\n' "$a"; done > "$REC"
R
# sg GROUP -c CMD ARG0 ARGS...: sg hands CMD to sh -c with the rest as $0 $1 ...
cat > "$T/bin/sg" <<'S'
#!/bin/sh
[ "$1" = prestium-localweb ] && [ "$2" = -c ] || exit 99
cmd=$3; shift 4
exec sh -c "$cmd" "$STUBFF" "$@"
S
chmod +x "$T/bin/"*
H="$T/it's a \$(touch PWNED) home"; mkdir -p "$H"
run(){ ( cd "$T" && HOME="$H" PATH="$T/bin:$PATH" REC="$T/argv" STUBFF="$T/bin/rec" sh "$LF" "$@" ); }
rm -f "$T/argv"; run http://127.0.0.1:9000/; rc=$?
[ $rc = 0 ] && [ -s "$T/argv" ] || bad "launcher did not reach Firefox (rc $rc)"
want=$(printf '%s\n' --name prestium-localfox --class PrestiumLocalFirefox --profile "$H/.local/share/prestium-localfox" http://127.0.0.1:9000/)
[ "$(cat "$T/argv" 2>/dev/null)" = "$want" ] && ok "HOME with a quote: argv passed through unchanged" || { bad "argv differs:"; cat "$T/argv"; }
[ ! -e "$T/PWNED" ] && ok "no command substitution from HOME" || bad "HOME was evaluated by a shell"
[ "$(stat -c %a "$H/.local/share/prestium-localfox")" = 700 ] && ok "profile is mode 700" || bad "profile mode"
for u in http://127.0.0.1:7070/ "http://127.0.0.1:7685/abc/web/" http://127.0.0.1:9000/ http://i2pd:pw@127.0.0.1:7070/; do
  rm -f "$T/argv"; run "$u" && [ -s "$T/argv" ] && ok "accepted $u" || bad "refused $u"
done
for u in http://127.0.0.1:8080/ https://example.com/ http://127.0.0.1:7070.evil/ "http://127.0.0.1:9000/'x" "http://127.0.0.1:9000/\$(id)" file:///etc/passwd; do
  rm -f "$T/argv"; run "$u" 2>/dev/null; rc=$?
  [ $rc = 2 ] && [ ! -e "$T/argv" ] && ok "refused $u" || bad "accepted $u (rc $rc)"
done
grep -q 'sh -c "\$CMD"\|-c "\$CMD"' "$LF" && bad "launcher still builds a command string" || ok "no command string in the launcher"
[ $fail = 0 ] && echo "localfox argv: OK"; exit $fail
