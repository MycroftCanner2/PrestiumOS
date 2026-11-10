#!/bin/bash
# Prestium 2.1: The Lounge's "Prestium" theme package is installed, enabled, the server default,
# loads nothing from outside, and every file has a perms.txt entry. No network, no Node needed.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot
P=$I/var/lib/thelounge/packages; D=$P/node_modules/thelounge-theme-prestium
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
python3 - "$P/package.json" "$D/package.json" <<'PY' && ok "package enabled, type theme, css theme.css, main index.js" || bad "package.json"
import json,sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
assert "thelounge-theme-prestium" in a["dependencies"]
t=b["thelounge"]; assert t["type"]=="theme" and t["css"]=="theme.css" and b["main"]=="index.js"
assert t["themeColor"].startswith("#") and len(t["themeColor"])==7
PY
[ -f "$D/index.js" ] && node -e "require('$D')" 2>/dev/null && ok "index.js loads" || { [ -f "$D/index.js" ] && ! command -v node >/dev/null && ok "index.js present (no node here)" || bad "index.js"; }
grep -q '^	theme: "thelounge-theme-prestium",$' "$I/var/lib/thelounge/config.js" && ok "server default theme" || bad "config.js theme"
grep -qiE 'url\(|https?:|@font-face' <(grep -v '^@import "default.css";$' "$D/theme.css") && bad "theme loads something remote" || ok "theme loads nothing but The Lounge's default.css"
[ "$(grep -c '{' "$D/theme.css")" = "$(grep -c '}' "$D/theme.css")" ] && ok "braces balanced" || bad "braces"
for f in index.js package.json theme.css; do
  grep -qx "0600 thelounge thelounge /var/lib/thelounge/packages/node_modules/thelounge-theme-prestium/$f" "$I/usr/share/prestium/build/perms.txt" && ok "perms: $f" || bad "perms: $f"; done
grep -qx "0700 thelounge thelounge /var/lib/thelounge/packages/node_modules/thelounge-theme-prestium/" "$I/usr/share/prestium/build/perms.txt" && ok "perms: directory" || bad "perms: directory"
[ $fail = 0 ] && echo "thelounge theme: OK"; exit $fail
