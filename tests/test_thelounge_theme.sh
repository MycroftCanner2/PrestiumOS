#!/bin/bash
# Prestium 2.1: The Lounge's theme packages (the 10 Theme Factory themes) are installed,
# enabled and well-formed, Tech Innovation is the server default, every theme loads nothing from outside,
# the generated themes match scripts/thelounge-themes.py (which also checks WCAG contrast >= 4.5:1),
# and every file has a perms.txt entry. No network, no Node needed.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot
P=$I/var/lib/thelounge/packages; PERMS=$I/usr/share/prestium/build/perms.txt
DEFAULT=thelounge-theme-tech-innovation
THEMES="ocean-depths sunset-boulevard forest-canopy modern-minimalist golden-hour arctic-frost desert-rose tech-innovation botanical-garden midnight-galaxy"
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
n=0
for s in $THEMES; do
  pkg=thelounge-theme-$s; D=$P/node_modules/$pkg; n=$((n+1))
  python3 - "$P/package.json" "$D/package.json" "$pkg" <<'PY' && ok "$pkg: enabled, type theme, css theme.css, main index.js" || bad "$pkg: package.json"
import json,sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
assert sys.argv[3] in a["dependencies"] and b["name"]==sys.argv[3]
t=b["thelounge"]; assert t["type"]=="theme" and t["css"]=="theme.css" and b["main"]=="index.js"
assert t["name"] and "thelounge-theme" in b["keywords"] and t["supports"]==">=4.5.0"
assert t["themeColor"].startswith("#") and len(t["themeColor"])==7
PY
  [ -f "$D/index.js" ] && node -e "require('$D')" 2>/dev/null && ok "$pkg: index.js loads" || { [ -f "$D/index.js" ] && ! command -v node >/dev/null && ok "$pkg: index.js present (no node here)" || bad "$pkg: index.js"; }
  [ "$(head -c1 "$D/theme.css" 2>/dev/null)" ] && grep -qx '@import "default.css";' "$D/theme.css" || bad "$pkg: theme.css missing or no default.css import"
  grep -qiE 'url\(|https?:|@font-face|@import' <(grep -v '^@import "default.css";$' "$D/theme.css") && bad "$pkg: theme loads something remote" || ok "$pkg: loads nothing but The Lounge's default.css"
  [ "$(grep -o '{' "$D/theme.css" | wc -l)" = "$(grep -o '}' "$D/theme.css" | wc -l)" ] && ok "$pkg: braces balanced" || bad "$pkg: braces"
  for f in index.js package.json theme.css; do
    grep -qx "0640 root thelounge /var/lib/thelounge/packages/node_modules/$pkg/$f" "$PERMS" && ok "$pkg: perms $f" || bad "$pkg: perms $f"; done
  grep -qx "0750 root thelounge /var/lib/thelounge/packages/node_modules/$pkg/" "$PERMS" && ok "$pkg: perms directory" || bad "$pkg: perms directory"
done
[ "$n" = 10 ] && ok "10 theme packages" || bad "theme count $n"
# Theme Factory display names, exactly as in the skill
python3 - "$P/node_modules" <<'PY' && ok "Theme Factory display names" || bad "display names"
import json,sys
want={"ocean-depths":"Ocean Depths","sunset-boulevard":"Sunset Boulevard","forest-canopy":"Forest Canopy",
 "modern-minimalist":"Modern Minimalist","golden-hour":"Golden Hour","arctic-frost":"Arctic Frost",
 "desert-rose":"Desert Rose","tech-innovation":"Tech Innovation","botanical-garden":"Botanical Garden",
 "midnight-galaxy":"Midnight Galaxy"}
for s,n in want.items():
    assert json.load(open("%s/thelounge-theme-%s/package.json"%(sys.argv[1],s)))["thelounge"]["name"]==n, s
PY
grep -q "^	theme: \"$DEFAULT\",\$" "$I/var/lib/thelounge/config.js" && ok "server default theme: $DEFAULT" || bad "config.js theme"
D=$P/node_modules/$DEFAULT
grep -q 'color-scheme: dark;' "$D/theme.css" && grep -q -- '--t-fg: #ffffff;' "$D/theme.css" && grep -q -- '--t-in-fg: #ffffff;' "$D/theme.css" \
  && ok "default: dark, chat and field text #ffffff" || bad "default theme text colours"
# text fields get an explicit colour and background in every generated theme
for s in $THEMES; do
  grep -q '^textarea,$' "$P/node_modules/thelounge-theme-$s/theme.css" && grep -q '^#chat .self .content,$' "$P/node_modules/thelounge-theme-$s/theme.css" \
    && ok "thelounge-theme-$s: explicit field and chat text colours" || bad "thelounge-theme-$s: no explicit field / chat text colours"; done
python3 "$R/scripts/thelounge-themes.py" --check && ok "generated themes match scripts/thelounge-themes.py, contrast >= 4.5:1" || bad "generator check"
grep -q 'background:#1e1e1e;color:#ffffff' "$P/node_modules/thelounge-prestium-autologin/autologin.html" \
  && ! grep -qiE 'https?:|url\(|<link|src="[^a]' "$P/node_modules/thelounge-prestium-autologin/autologin.html" \
  && ok "sign-in splash uses the default's colours, nothing remote" || bad "autologin.html"
[ -f "$P/THEME-FACTORY-NOTICE.txt" ] && grep -q 'Apache License' "$P/THEME-FACTORY-NOTICE.txt" && grep -q 8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4 "$P/THEME-FACTORY-NOTICE.txt" \
  && grep -qx '0640 root thelounge /var/lib/thelounge/packages/THEME-FACTORY-NOTICE.txt' "$PERMS" && ok "Theme Factory notice shipped" || bad "Theme Factory notice"
[ $fail = 0 ] && echo "thelounge theme: OK"; exit $fail
