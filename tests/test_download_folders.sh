#!/bin/bash
# 2.1 (L-5): every confined app writes files in the home only in its own download or output folder.
#   network apps:  ~/Downloads/{I2P Browser,Local Firefox,Mail,Gajim,Pidgin}, Tor Browser ~/Tor Browser
#   editors:       ~/Documents/{LibreOffice,GIMP,FeatherPad,File Roller,Xarchiver,Audacity,Kleopatra,Metadata Cleaner}
#   mat2:          only "<name>.cleaned.<ext>" next to the original
# Mail and chat may read what you put directly in ~/Downloads (attachments); the browsers see only their
# own folder; viewers and editors read every file folder (to open downloads) but write none of them.
# Checked on the compiled profiles (apparmor_parser -p, tests/aa_eval.py), plus the launchers, app
# settings and hook 0500 that create and point at the folders.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); A=$R/config/includes.chroot/etc/apparmor.d; I=$R/config/includes.chroot; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=/home/user
grep -q 'DL="$HOME/Downloads/I2P Browser"' "$I/usr/local/bin/librewolf-i2p" && grep -q -- '--bind "$DL" "$DL"' "$I/usr/local/bin/librewolf-i2p" \
  && ok "librewolf-i2p binds only ~/Downloads/I2P Browser" || bad "librewolf-i2p download folder"
grep -q 'pref("browser.download.dir", "/home/user/Downloads/I2P Browser");' "$I/home/user/.librewolf/librewolf.overrides.cfg" && ok "LibreWolf download.dir" || bad "LibreWolf download.dir"
grep -q 'user_pref("browser.download.dir", "/home/user/Downloads/Local Firefox");' "$I/usr/local/share/prestium-localfox/user.js" && ok "local Firefox download.dir" || bad "local Firefox download.dir"
grep -qx 'attach_save_dir=/home/user/Downloads/Mail' "$I/home/user/.claws-mail/clawsrc" && ok "Claws Mail saves attachments in ~/Downloads/Mail" || bad "clawsrc attach_save_dir"
grep -q "last_receive_folder' type='path' value='/home/user/Downloads/Pidgin'" "$I/home/user/.purple/prefs.xml" && ok "Pidgin receives in ~/Downloads/Pidgin" || bad "Pidgin prefs"
python3 -I -c 'import sqlite3,json,sys; v=json.loads(sqlite3.connect(sys.argv[1]).execute("select settings from settings where name=\"app\"").fetchone()[0]); sys.exit(v.get("last_save_dir")!="/home/user/Downloads/Gajim")' \
  "$I/home/user/.config/gajim/settings.sqlite" && ok "Gajim saves in ~/Downloads/Gajim" || bad "Gajim last_save_dir"
H0500=$R/config/hooks/live/0500-prestium-permissions.hook.chroot
for d in '"I2P Browser" "Local Firefox" Mail Gajim Pidgin' 'LibreOffice GIMP FeatherPad "File Roller" Xarchiver Audacity Kleopatra "Metadata Cleaner"'; do
  grep -qF "for d in $d; do install -d -m 0700" "$H0500" && ok "hook 0500 creates: $d" || bad "hook 0500 lacks: $d"; done
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin
command -v apparmor_parser >/dev/null || { echo "SKIP apparmor_parser missing"; exit $fail; }
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; rm -f "$W/loupe"; cp -r "$A"/. "$W"/
run() { apparmor_parser -p -b "$W" "$W/$1" > "$W/.exp" 2>"$W/.err" || { bad "$1 does not compile"; cat > /dev/null; return; }
  python3 -B "$R/tests/aa_eval.py" "$W/.exp" || fail=1; }
# others(PROFILE, OWN): no write in any other app's folder or a shared folder
others() { for d in "Downloads/I2P Browser" "Downloads/Local Firefox" Downloads/Mail Downloads/Gajim Downloads/Pidgin Downloads/Torrents \
    Documents/LibreOffice Documents/GIMP Documents/FeatherPad "Documents/File Roller" Documents/Xarchiver Documents/Audacity Documents/Kleopatra \
    "Documents/Metadata Cleaner" Downloads Documents Desktop Pictures Music Videos Public Templates OnionShare "Tor Browser"; do
    [ "$d" = "$2" ] && continue; echo "deny $1 \"$H/$d/f.pdf\" w"; done; }
for pair in "usr.bin.claws-mail claws-mail Downloads/Mail" "usr.bin.gajim gajim Downloads/Gajim" "usr.bin.pidgin pidgin Downloads/Pidgin"; do
  set -- $pair; echo "== $2: own folder ~/$3; reads files put directly in ~/Downloads"
  run "$1" <<EOT
allow $2 $H/$3/f.pdf rw
allow $2 $H/$3/sub/f.pdf rw
allow $2 $H/Downloads/f.pdf r
$(for d in Mail Gajim Pidgin Torrents; do [ "Downloads/$d" = "$3" ] || echo "deny $2 $H/Downloads/$d/f.pdf r"; done)
deny $2 "$H/Downloads/I2P Browser/f.pdf" r
deny $2 $H/Documents/LibreOffice/f.odt r
$(others "$2" "$3")
EOT
done
for pair in "usr.share.librewolf.librewolf librewolf Downloads/I2P_Browser" "opt.firefox.firefox prestium-localfox Downloads/Local_Firefox"; do
  set -- $pair; own=${3//_/ }; echo "== $2: own folder ~/$own only"
  run "$1" <<EOT
allow $2 "$H/$own/f.pdf" rw
deny $2 $H/Downloads/f.pdf r
deny $2 $H/Downloads/Mail/f.pdf r
deny $2 $H/Documents/f.odt r
$(others "$2" "$own")
EOT
done
echo "== the LibreWolf launcher's sandbox"
run prestium.browser-launcher <<EOT
allow prestium_librewolf_launcher//bwrap "$H/Downloads/I2P Browser/f.pdf" rw
deny prestium_librewolf_launcher//bwrap $H/Downloads/f.pdf w
deny prestium_librewolf_launcher//bwrap $H/Downloads/Mail/f.pdf w
deny prestium_tor_browser_launcher//bwrap "$H/Downloads/I2P Browser/f.pdf" w
EOT
for pair in "usr.lib.libreoffice.program libreoffice LibreOffice" "usr.bin.gimp gimp GIMP" "usr.bin.featherpad featherpad FeatherPad" \
    "usr.bin.file-roller file-roller File_Roller" "usr.bin.xarchiver xarchiver Xarchiver" "usr.bin.audacity audacity Audacity" \
    "usr.bin.kleopatra kleopatra Kleopatra" "usr.bin.metadata-cleaner metadata-cleaner Metadata_Cleaner"; do
  set -- $pair; own="Documents/${3//_/ }"; echo "== $2: reads the file folders, writes only ~/$own"
  run "$1" <<EOT
allow $2 "$H/$own/f.pdf" rw
allow $2 $H/Downloads/Mail/f.pdf r
allow $2 "$H/Downloads/I2P Browser/f.pdf" r
allow $2 $H/Downloads/f.pdf r
allow $2 $H/Documents/f.pdf r
allow $2 /media/user/STICK/f.pdf rw
$(others "$2" "$own")
EOT
done
echo "== mat2: only the cleaned copy, next to the original"
run usr.bin.mat2 <<EOT
allow mat2 $H/Downloads/Mail/f.pdf r
allow mat2 $H/Downloads/Mail/f.cleaned.pdf w
allow mat2 "$H/Downloads/I2P Browser/f.cleaned.pdf" w
allow mat2 $H/Documents/LibreOffice/f.cleaned.odt w
$(others mat2 none)
deny mat2 $H/Downloads/Mail/f.pdf w
EOT
echo "== viewers write nothing in the file folders"
for pair in "usr.bin.loupe loupe" "usr.bin.ristretto ristretto" "usr.bin.vlc vlc"; do
  set -- $pair
  run "$1" <<EOT
allow $2 $H/Downloads/Mail/f.png r
$(others "$2" none | grep -v 'Pictures/')
EOT
done
exit $fail
