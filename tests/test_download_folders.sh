#!/bin/bash
# 2.1 (L-5, revised): the apps share two folders and three stay app-specific.
#   shared:   ~/Downloads (local Firefox, Claws Mail, Gajim, Pidgin),
#             ~/Documents (LibreOffice, GIMP, FeatherPad, File Roller, Xarchiver, Audacity,
#             Kleopatra, Metadata Cleaner, Feather)
#   specific: ~/I2P Browser (I2P Browser), ~/Torrents (I2P Torrents),
#             ~/Tor Browser (Tor Browser)
#   mat2:     only "<name>.cleaned.<ext>" in ~/Documents/.remove-metadata.XXXXXX
#             (the prestium-remove-metadata helper moves the cleaned copy back
#             next to the original; tested with a fake mat2)
#   /media:   read-only for all of them (2.1, review of 6bf1234)
# The apps' settings point at the shared folders (where the app has a setting), /etc/skel matches the
# live user's home, and every file there is in perms.txt. The file manager's pinned list is exactly
# the five folders, labelled i2P Browser, i2P Torrents, Tor Browser, Documents, Downloads.
# Mail and chat read and write files directly in ~/Downloads (attachments), never in the three
# app-specific folders; the editors read every file folder (to open downloads) but write only
# ~/Documents. The local Firefox may also read *.torrent in ~/I2P Browser and files in ~/Torrents, for I2P Torrents.
# Checked on the compiled profiles (apparmor_parser -p, tests/aa_eval.py), plus the launchers, app
# settings and hook 0500 that create and point at the folders.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); A=$R/config/includes.chroot/etc/apparmor.d; I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=/home/user
grep -q 'DL="$HOME/I2P Browser"' "$I/usr/local/bin/librewolf-i2p" && grep -q -- '--bind "$DL" "$DL"' "$I/usr/local/bin/librewolf-i2p" \
  && ok "librewolf-i2p binds only ~/I2P Browser" || bad "librewolf-i2p download folder"
grep -q 'pref("browser.download.dir", "/home/user/I2P Browser");' "$I/home/user/.librewolf/librewolf.overrides.cfg" && ok "LibreWolf download.dir" || bad "LibreWolf download.dir"
grep -q 'user_pref("browser.download.dir", "/home/user/Downloads");' "$I/usr/local/share/prestium-localfox/user.js" && ok "local Firefox download.dir" || bad "local Firefox download.dir"
grep -qx 'attach_save_dir=/home/user/Downloads' "$I/home/user/.claws-mail/clawsrc" && grep -qx 'attach_load_dir=/home/user/Downloads' "$I/home/user/.claws-mail/clawsrc" && ok "Claws Mail saves attachments in ~/Downloads" || bad "clawsrc attach_save_dir"
grep -q "last_save_folder' type='path' value='/home/user/Downloads'" "$I/home/user/.purple/prefs.xml" && ok "Pidgin saves received files in ~/Downloads" || bad "Pidgin prefs"
# Pidgin 2 registers only these (pidgin/gtkprefs.c); a received file's dialog uses last_save_folder
python3 -I - "$I/home/user/.purple/prefs.xml" <<'PY' && ok "Pidgin: only real filelocations prefs" || bad "Pidgin: unknown filelocations pref"
import sys, xml.etree.ElementTree as E
r = E.parse(sys.argv[1]).getroot()
fl = [n for n in r.iter('pref') if n.get('name') == 'filelocations']
names = {c.get('name') for f in fl for c in f}
sys.exit(not (len(fl) == 1 and names and names <= {'last_save_folder', 'last_open_folder', 'last_icon_folder'}))
PY
for f in "$I/home/user/.librewolf/librewolf.overrides.cfg" "$I/home/user/.config/librewolf/librewolf/librewolf.overrides.cfg"; do
  for k in browser.download.dir browser.download.lastDir; do
    grep -qF "pref(\"$k\", \"/home/user/I2P Browser\");" "$f" && ok "$k in ${f#"$I/"}" || bad "$k missing in ${f#"$I/"}"; done; done
cmp -s "$I/home/user/.librewolf/librewolf.overrides.cfg" "$I/home/user/.config/librewolf/librewolf/librewolf.overrides.cfg" \
  && ok "both LibreWolf overrides files identical" || bad "LibreWolf overrides files differ"
echo "== pinned file list: exactly five, labelled i2P Browser, i2P Torrents, Tor Browser, Documents, Downloads"
exp="file:///home/user/I2P%20Browser i2P Browser
file:///home/user/Torrents i2P Torrents
file:///home/user/Tor%20Browser Tor Browser
file:///home/user/Documents Documents
file:///home/user/Downloads Downloads"
for h in home/user etc/skel; do
  for b in .config/gtk-3.0/bookmarks .gtk-bookmarks; do
    [ "$(tr -d '\r' < "$I/$h/$b")" = "$exp" ] && ok "$h/$b: the five pinned folders, in order" || bad "$h/$b: pinned list is not the five folders"; done; done
echo "== editors' settings"
X=$I/usr/lib/libreoffice/share/registry/prestium.xcd
python3 -I - "$X" <<'PY' && ok "LibreOffice: Work path ~/Documents, UseLocking=false" || bad "LibreOffice prestium.xcd"
import sys, xml.etree.ElementTree as E
O = '{http://openoffice.org/2001/registry}'
r = E.parse(sys.argv[1]).getroot()
assert r.find('dependency').get('file') == 'main'
c = {d.get(O + 'name'): d for d in r.findall(O + 'component-data')}
assert c['Common'].get(O + 'package') == 'org.openoffice.Office' and c['Paths'].get(O + 'package') == 'org.openoffice.Office'
m = c['Common'].find("node[@%sname='Misc']/prop[@%sname='UseLocking']/value" % (O, O))
w = c['Paths'].find("node[@%sname='Paths']/node[@%sname='Work']/prop[@%sname='WritePath']/value" % (O, O, O))
sys.exit(not (m.text == 'false' and w.text == 'file:///home/user/Documents'))
PY
grep -qF '/usr/lib/libreoffice/** mr,' "$A/usr.lib.libreoffice.program" && ok "LibreOffice profile reads prestium.xcd" || bad "LibreOffice can't read its registry"
grep -q "UseLocking=false" "$A/usr.lib.libreoffice.program" && ! grep -q "opens read-only" "$A/usr.lib.libreoffice.program" \
  && ok "LibreOffice profile comment: lock files off, Save As" || bad "LibreOffice profile comment"
for h in home/user etc/skel; do
  python3 -I - "$I/$h/.config/xarchiver/xarchiverrc" <<'PY' && ok "Xarchiver ($h): extracts to ~/Documents, complete file" || bad "Xarchiver xarchiverrc ($h)"
import sys, configparser
c = configparser.ConfigParser(interpolation=None); c.read(sys.argv[1]); x = c['xarchiver']
need = {'preferred_extract_dir': '/home/user/Documents', 'preferred_temp_dir': '/tmp', 'prefer_unzip': 'true',
        'confirm_deletion': 'true', 'advanced_isearch': 'true', 'auto_expand': 'true', 'show_toolbar': 'true',
        'show_location_bar': 'true', 'show_sidebar': 'true', 'ensure_directory': 'true', 'full_path': '2',
        'updadd': 'true', 'recurse': 'true', 'icon_size': '2'}
sys.exit(any(x.get(k) != v for k, v in need.items()))
PY
  for o in Save Export; do
    python3 -I - "$I/$h/.config/audacity/audacity.cfg" "$o" <<'PY' && ok "Audacity ($h): $o folder ~/Documents" || bad "Audacity $o folder ($h)"
import sys
cur = None; v = None
for l in open(sys.argv[1]):
    l = l.strip()
    if l.startswith('['): cur = l[1:-1]
    elif cur == 'Directories/' + sys.argv[2] and l.startswith('Default='): v = l[8:]
sys.exit(v != '/home/user/Documents')
PY
  done
  grep -qx 'shortcuts=file:, file:///home/user, file:///home/user/Documents, file:///home/user/Downloads' "$I/$h/.config/QtProject.conf" \
    && grep -qx 'sidebarWidth=150' "$I/$h/.config/QtProject.conf" && ok "Qt file dialog sidebar: the shared folders ($h)" || bad "QtProject.conf ($h)"
done
echo "== /etc/skel matches the live user's home, and perms.txt lists them"
d=$(diff -r "$I/etc/skel" "$I/home/user" 2>&1 | grep -v 'gtk.css: No such file'); [ -z "$d" ] && ok "/etc/skel == home/user" || bad "skel differs: $d"
PM=$I/usr/share/prestium/build/perms.txt
for h in etc/skel home/user; do
  m=$(cd "$I" && find "$h" -type f | while read -r f; do grep -qF " /$f" "$PM" || echo "$f"; done)
  [ -z "$m" ] && ok "perms.txt lists every file in /$h" || bad "perms.txt misses: $m"; done
python3 -I -c 'import sqlite3,json,sys; v=json.loads(sqlite3.connect(sys.argv[1]).execute("select settings from settings where name=\"app\"").fetchone()[0]); sys.exit(not (v.get("last_save_dir")=="/home/user/Downloads" and v.get("last_send_dir")=="/home/user/Downloads"))' \
  "$I/home/user/.config/gajim/settings.sqlite" && ok "Gajim saves in ~/Downloads" || bad "Gajim last_save_dir"
H0500=$R/config/hooks/live/0500-prestium-permissions.hook.chroot
grep -qF 'install -d -m 0700 "/home/user/I2P Browser"' "$H0500" && ok "hook 0500 creates the I2P Browser folder" || bad "hook 0500 I2P Browser folder"
! grep -qE 'Downloads/\$d|Documents/\$d|Local Firefox|Mail Gajim|Metadata Cleaner|Documents/Feather' "$H0500" && ok "hook 0500 creates no per-app folders" || bad "hook 0500 still creates per-app folders"
echo "== prestium-remove-metadata: mat2 works in ~/Documents/.remove-metadata.XXXXXX (fake mat2)"
T=$(mktemp -d); FH=$T/home; mkdir -p "$FH/Downloads" "$T/bin"
printf 'pdf\n' > "$FH/Downloads/a.pdf"; printf 'pdf\n' > "$FH/Downloads/b.pdf"; printf 'old\n' > "$FH/Downloads/b.cleaned.pdf"
printf 'x\n' > "$FH/Downloads/c.pdf"; ln -s "$FH/Downloads/a.pdf" "$FH/Downloads/l.pdf"
cat > "$T/bin/mat2" <<'SH'
#!/bin/sh
# fake mat2: logs its argument; for c.pdf it writes a symlink instead of a file
[ "$1" = -- ] && shift; echo "$1" >> "$HOME/../mat2.log"
o="${1%.*}.cleaned.${1##*.}"
case $1 in */c.pdf) ln -s /etc/passwd "$o" ;; *) cp "$1" "$o" ;; esac
SH
printf '#!/bin/sh\nexit 0\n' > "$T/bin/zenity"; cp "$T/bin/zenity" "$T/bin/notify-send"; chmod +x "$T/bin/"*
HOME=$FH PATH=$T/bin:$PATH bash "$I/usr/local/bin/prestium-remove-metadata" "$FH/Downloads/a.pdf" "$FH/Downloads/b.pdf" \
  "$FH/Downloads/c.pdf" "$FH/Downloads/l.pdf" >/dev/null 2>&1; rc=$?
MC="$FH/Documents"
[ $rc -ne 0 ] && ok "wrapper reports the files it couldn't clean" || bad "wrapper rc 0 despite failures"
[ -f "$FH/Downloads/a.cleaned.pdf" ] && [ ! -L "$FH/Downloads/a.cleaned.pdf" ] && ok "cleaned copy moved next to the original" || bad "a.cleaned.pdf missing"
[ "$(cat "$FH/Downloads/b.cleaned.pdf")" = old ] && [ -f "$MC/b.cleaned.pdf" ] && ok "existing file not overwritten; copy kept in ~/Documents" || bad "b.cleaned.pdf clobbered or lost"
[ ! -e "$FH/Downloads/c.cleaned.pdf" ] && [ ! -L "$FH/Downloads/c.cleaned.pdf" ] && ok "a symlink from mat2 is not moved" || bad "symlink moved"
! grep -q '/l.pdf$' "$T/mat2.log" && ok "a selected symlink is skipped" || bad "symlink cleaned"
[ "$(grep -c "^$MC/.remove-metadata\.[A-Za-z0-9]*/[0-9]*/[abc]\\.pdf$" "$T/mat2.log")" = 3 ] && ! grep -q "Downloads" "$T/mat2.log" \
  && ok "mat2 ran only on copies in ~/Documents/.remove-metadata.XXXXXX" || bad "mat2 args: $(cat "$T/mat2.log")"
[ -z "$(find "$MC" -name '.remove-metadata.*')" ] && ok "work folder removed" || bad "work folder left"
[ "$(cat "$FH/Downloads/a.pdf")" = pdf ] && ok "original unchanged" || bad "original changed"
rm -rf "$T"
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin
command -v apparmor_parser >/dev/null || { echo "SKIP apparmor_parser missing"; exit $fail; }
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; rm -f "$W/loupe"; cp -r "$A"/. "$W"/
run() { apparmor_parser -p -b "$W" "$W/$1" > "$W/.exp" 2>"$W/.err" || { bad "$1 does not compile"; cat > /dev/null; return; }
  python3 -B "$R/tests/aa_eval.py" "$W/.exp" || fail=1; }
# the three app-specific folders, which no shared app may write
spec() { for d in "I2P Browser" Torrents "Tor Browser"; do echo "deny $1 \"$H/$d/f.pdf\" w"; done; }
# Editors write the shared ~/Documents and nothing in ~/Downloads or a specific folder.
# Others read the file folders but write nowhere in them.
for pair in "usr.lib.libreoffice.program libreoffice" "usr.bin.gimp gimp" "usr.bin.featherpad featherpad" \
    "usr.bin.file-roller file-roller" "usr.bin.xarchiver xarchiver" "usr.bin.audacity audacity" \
    "usr.bin.kleopatra kleopatra" "usr.bin.metadata-cleaner metadata-cleaner"; do
  set -- $pair; echo "== $2: writes only the shared ~/Documents"
  run "$1" <<EOT
allow $2 "$H/Documents/f.pdf" rw
allow $2 "$H/Documents/sub/f.pdf" rw
allow $2 $H/Downloads/f.pdf r
allow $2 "$H/I2P Browser/f.pdf" r
allow $2 /media/user/STICK/f.pdf r
deny $2 /media/user/STICK/f.pdf w
deny $2 "/media/user/STICK/.~lock.f.odt#" w
deny $2 $H/Downloads/f.pdf w
$(spec "$2")
deny $2 $H/Desktop/f.pdf w
deny $2 $H/Pictures/f.pdf w
deny $2 $H/Music/f.pdf w
deny $2 $H/Videos/f.pdf w
EOT
done
echo "== feather: writes only the shared ~/Documents"
run usr.local.bin.feather <<EOT
allow feather "$H/Documents/f.pdf" rw
allow feather "$H/Documents/sub/f.pdf" rw
deny feather $H/Downloads/f.pdf w
$(spec feather)
EOT
# Network apps write files directly in the shared ~/Downloads, never in a specific folder.
for pair in "usr.bin.claws-mail claws-mail" "usr.bin.gajim gajim" "usr.bin.pidgin pidgin" "opt.firefox.firefox prestium-localfox"; do
  set -- $pair; echo "== $2: writes files directly in ~/Downloads, never in a specific folder"
  run "$1" <<EOT
allow $2 $H/Downloads/f.pdf rw
deny $2 "$H/I2P Browser/f.pdf" rw
deny $2 $H/Torrents/f.pdf w
deny $2 "$H/Tor Browser/f.pdf" rw
deny $2 $H/Documents/f.pdf w
deny $2 $H/Desktop/f.pdf w
EOT
done
echo "== prestium-localfox: I2P Torrents' file picker reads .torrent files in ~/I2P Browser, nothing else there"
run opt.firefox.firefox <<EOT
allow prestium-localfox "$H/I2P Browser/" r
allow prestium-localfox "$H/I2P Browser/sub/" r
allow prestium-localfox "$H/I2P Browser/f.torrent" r
allow prestium-localfox "$H/I2P Browser/sub/F.TORRENT" r
deny prestium-localfox "$H/I2P Browser/f.torrent" w
deny prestium-localfox "$H/I2P Browser/new.torrent" w
deny prestium-localfox "$H/I2P Browser/f.pdf" r
deny prestium-localfox "$H/I2P Browser/f.torrent.part" r
deny prestium-localfox "$H/I2P Browser/f.torrent" m
allow prestium-localfox $H/Torrents/f.torrent r
allow prestium-localfox $H/Torrents/sub/f.torrent r
deny prestium-localfox $H/Torrents/f.torrent w
allow prestium-localfox $H/Downloads/f.torrent r
deny prestium-localfox "$H/Tor Browser/f.torrent" r
deny prestium-localfox $H/.librewolf/f.torrent r
EOT
echo "== the LibreWolf launcher's sandbox"
run prestium.browser-launcher <<EOT
allow prestium_librewolf_launcher//bwrap "$H/I2P Browser/f.pdf" rw
deny prestium_librewolf_launcher//bwrap $H/Downloads/f.pdf w
deny prestium_librewolf_launcher//bwrap $H/Torrents/f.pdf w
deny prestium_tor_browser_launcher//bwrap "$H/I2P Browser/f.pdf" w
EOT
echo "== mat2: only the cleaned copy, only in ~/Documents/.remove-metadata.XXXXXX"
M="$H/Documents/.remove-metadata.Ab12Cd/1"
run usr.bin.mat2 <<EOT
allow mat2 $H/Downloads/f.pdf r
allow mat2 "$M/f.pdf" r
allow mat2 "$M/f.cleaned.pdf" w
allow mat2//bwrap "$M/f.cleaned.pdf" w
deny mat2 "$M/f.pdf" w
deny mat2 $H/Downloads/f.cleaned.pdf w
deny mat2 "$H/I2P Browser/f.cleaned.pdf" w
deny mat2 $H/Documents/f.cleaned.pdf w
deny mat2 "$H/Tor Browser/f.cleaned.pdf" w
deny mat2 /media/user/STICK/f.cleaned.pdf w
deny mat2//bwrap $H/Downloads/f.cleaned.pdf w
deny mat2//bwrap /media/user/STICK/f.cleaned.pdf w
deny mat2 $H/Downloads/f.pdf w
EOT
echo "== FeatherPad reads Qt's dialog settings, can't change them"
run usr.bin.featherpad <<EOT
allow featherpad $H/.config/QtProject.conf r
deny featherpad $H/.config/QtProject.conf w
EOT
echo "== viewers write nothing in the file folders"
for pair in "usr.bin.loupe loupe" "usr.bin.ristretto ristretto" "usr.bin.vlc vlc"; do
  set -- $pair
  run "$1" <<EOT
allow $2 $H/Downloads/f.png r
deny $2 $H/Downloads/f.png w
deny $2 $H/Documents/f.png w
deny $2 "$H/I2P Browser/f.png" w
deny $2 $H/Torrents/f.png w
deny $2 "$H/Tor Browser/f.png" w
deny $2 $H/Pictures/f.png w
EOT
done
exit $fail
