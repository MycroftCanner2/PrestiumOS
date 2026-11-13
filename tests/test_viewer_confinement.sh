#!/bin/bash
# 2.1 (audit of 96468c5, M-1): every program that opens downloaded files by default (mimeapps.list),
# and every viewer, editor or archive tool on the image, KeePassXC and Kleopatra, has an enforced
# AppArmor profile with no network, no other app's data and no keys. Checks the sources, the build
# hook and perms, and (with apparmor_parser; AA_SYSTEM_DIR: Debian's /etc/apparmor.d) the compiled
# profiles, abstractions expanded.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); I=$R/config/includes.chroot; A=$I/etc/apparmor.d; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
H=$R/config/hooks/live/0600-prestium-apparmor.hook.chroot; PM=$I/usr/share/prestium/build/perms.txt
# desktop id or package -> binary -> profile file
TABLE="org.gnome.Loupe.desktop /usr/bin/loupe usr.bin.loupe
org.xfce.ristretto.desktop /usr/bin/ristretto usr.bin.ristretto
org.gnome.FileRoller.desktop /usr/bin/file-roller usr.bin.file-roller
vlc /usr/bin/vlc usr.bin.vlc
xarchiver /usr/bin/xarchiver usr.bin.xarchiver
featherpad /usr/bin/featherpad usr.bin.featherpad
mat2 /usr/bin/mat2 usr.bin.mat2
metadata-cleaner /usr/bin/metadata-cleaner usr.bin.metadata-cleaner
gimp /usr/bin/gimp-3.0 usr.bin.gimp
audacity /usr/libexec/prestium-audacity usr.bin.audacity
keepassxc /usr/bin/keepassxc usr.bin.keepassxc
kleopatra /usr/bin/kleopatra usr.bin.kleopatra"
# every default handler in mimeapps.list is in the table
for d in $(grep -v '^\s*[#[]' "$I/etc/xdg/mimeapps.list" | cut -d= -f2 | tr ';' '\n' | grep . | sort -u); do
  grep -q "^$d " <<<"$TABLE" && ok "default handler $d has a profile" || bad "default handler $d: no profile"; done
# every package in the table that the image installs
pk=$(cat "$R"/config/package-lists/*.list.chroot | sed 's/#.*//' | tr -s ' \t' '\n')
for p in vlc xarchiver featherpad mat2 metadata-cleaner gimp audacity keepassxc kleopatra loupe ristretto file-roller; do
  grep -qx "$p" <<<"$pk" || bad "package $p is no longer installed: update this test"; done
attach(){ # does profile file $1 attach binary $2? (expands one {a,b} group in the header)
  python3 - "$A/$1" "$2" <<'PY'
import re, sys
h = [l for l in open(sys.argv[1]) if re.match(r"\s*profile \S+ /", l)]
pats = [re.match(r"\s*profile \S+ (\S+)", l).group(1) for l in h]
def exp(p):
    m = re.search(r"\{([^}]*)\}", p)
    return [p] if not m else [x for a in m.group(1).split(",") for x in exp(p[:m.start()] + a + p[m.end():])]
sys.exit(0 if any(sys.argv[2] == e for p in pats for e in exp(p)) else 1)
PY
}
while read -r id bin f; do
  [ -f "$A/$f" ] || { bad "$id: no $f"; continue; }
  attach "$f" "$bin" && ok "$f attaches $bin" || bad "$f does not attach $bin"
  grep -q 'flags=(complain\|flags=(unconfined' "$A/$f" && bad "$f not enforced"
  grep -q "prestium.pinentry \\\\" "$H" >/dev/null; n=$(grep -c "\b$f\b" "$H"); [ "$n" -ge 2 ] && ok "hook enforces and checks $f" || bad "hook lists $f $n times (want 2)"
  grep -qx "0644 root root /etc/apparmor.d/$f" "$PM" && ok "perms: $f" || bad "perms: $f"
done <<<"$TABLE"
grep -q '^rm -f /etc/apparmor.d/loupe /etc/apparmor.d/local/loupe$' "$H" && ok "hook drops Debian's unconfined loupe profile" || bad "Debian loupe profile kept"
for a in prestium-app-common prestium-app-secrets prestium-user-files prestium-viewer prestium-viewer-core prestium-viewer-write prestium-viewer-bwrap; do
  grep -qx "0644 root root /etc/apparmor.d/abstractions/$a" "$PM" || bad "perms: abstraction $a"; done
if command -v apparmor_parser >/dev/null; then
  W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
  cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; rm -f "$W/loupe"; cp -r "$A"/. "$W"/
  while read -r id bin f; do
    x=$(apparmor_parser -p -b "$W" "$W/$f" 2>"$W/.err") || { bad "$f does not compile: $(grep -v 'Cache' "$W/.err" | head -2)"; continue; }
    ok "$f compiles"
    # allow rules only (no comments, no denies), with the profile each sits in
    al=$(awk '/^[[:space:]]*profile /{p=$2} {print p" "$0}' <<<"$x" | grep -v '^\S* \s*#' | grep -Ev '^\S* \s*(audit\s+)?deny\s')
    inet=$(grep -E '^\S* \s*network (inet|inet6)' <<<"$al" | grep -v '^dirmngr ')
    # 2.1 (review of 7242e00): Audacity alone may open IPv4 TCP sockets (its single-instance check
    # listens on 127.0.0.1); never UDP, raw or IPv6. 2.1 (review of 778baf7): only in its own, empty
    # network namespace (hook 0620 and prestium-audacity; tests/test_audacity_netns.sh), so the rule
    # reaches only that namespace's loopback, never the host's network.
    if [ "$f" = usr.bin.audacity ]; then
      [ "$inet" = "audacity   network inet stream," ] && ok "$f: IPv4 TCP only (single-instance listener, in its own network namespace)" || bad "$f: IP network: $inet"
      grep -q 'unshare-net' "$I/usr/local/bin/prestium-audacity" 2>/dev/null && [ -f "$R/config/hooks/live/0620-prestium-audacity-netns.hook.chroot" ] \
        && ok "$f: Audacity starts only in its own network namespace (wrapper and hook 0620)" || bad "$f: TCP allowed but no network namespace wrapper/hook"
      for d in 'network inet dgram' 'network inet raw' 'network inet6'; do
        grep -qF "deny $d," <<<"$x" && ok "$f: deny $d" || bad "$f: no deny $d"; done
    else
      [ -z "$inet" ] && ok "$f: no IP network (expanded)" || bad "$f: IP network: $inet"
      case $f in usr.bin.keepassxc|usr.bin.kleopatra) ;; *)
        grep -qF "deny network inet," <<<"$x" && ok "$f: deny network inet" || bad "$f: no deny network inet";; esac
    fi
    oth=$(grep -E '@\{HOME\}/(\.claws-mail|\.purple|\.local/share/gajim|\.config/gajim|\.tor-browser|\.librewolf|\.mozilla|\.ssh|\.local/share/keyrings|\.config/libreoffice)' <<<"$al")
    [ -z "$oth" ] && ok "$f: no other app's data or keys (expanded)" || bad "$f: $oth"
    if [ "$f" != usr.bin.kleopatra ]; then
      grep -q '@{HOME}/.gnupg' <<<"$al" && bad "$f may use ~/.gnupg" || ok "$f: no ~/.gnupg"; fi
    if [ "$f" != usr.bin.keepassxc ]; then
      grep -q 'kdbx' <<<"$al" && bad "$f may open KeePassXC databases" || ok "$f: no *.kdbx"; fi
    # never a write anywhere in the home outside the file folders and the app's own dot directories
    hw=$(grep -E '@\{HOME\}/' <<<"$al" | grep -E '\s[a-z]*w[a-z]*,\s*$' \
      | grep -vE '@\{HOME\}/(\.Private/|tmp/|Documents/\.remove-metadata\*/\*\*\.cleaned\.\*" |Documents/"? |Documents/\*\*"? |Pictures/vlcsnap|\.cache/|\.config/|\.local/share/|\.local/state/|\.audacity-data/|\.gnupg/|\*\*\.kdbx|\.Xauthority|\.fonts|\.recently)' \
      | grep -vE '@\{HOME\}/(\.\{,cache/\}fontconfig|tmp/|\.xsession-errors w|\.local/ rw|\.pulse-cookie|\.pulse/)' )
    [ -z "$hw" ] && ok "$f: writes only the shared ~/Documents and its own directories" || bad "$f home writes: $hw"
    # 2.1 (L-5, revised): the shared ~/Documents is writable (the editors' folder); no write in any other file folder
    sw=$(grep -E '@\{HOME\}/(\{Desktop|Desktop/|Downloads/|Pictures/\*|Music/|Videos/|Public/|Templates/|OnionShare/)' <<<"$al" \
      | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -vE 'Pictures/vlcsnap')
    [ -z "$sw" ] && ok "$f: no write outside the shared ~/Documents (L-5)" || bad "$f shared folder writes: $sw"
    # 2.1 (review of 6bf1234): volumes under /media are read-only (KeePassXC keeps its *.kdbx files there)
    mw=$(grep -E '\s/media/' <<<"$al" | grep -E '\s[a-z]*w[a-z]*,\s*$' | grep -vE '/media/\*\*\.kdbx(\.\*)? rwk,')
    [ -z "$mw" ] && ok "$f: no write under /media (but KeePassXC's .kdbx)" || bad "$f /media writes: $mw"
    # base and gnome grant ix and w under ~/.Private (ecryptfs) and ~/tmp: denied by prestium-viewer
    for d in '@{HOME}/.Private/** wx' '@{HOME}/tmp/** wx'; do
      grep -qF "deny $d," <<<"$x" && ok "$f: deny $d" || bad "$f: no deny $d"; done
    grep -Eq '^\S* \s*(owner\s+)?@\{HOME\}/\*\* [a-z]*w' <<<"$al" && bad "$f: write anywhere in the home"
    grep -Eq '^\S* \s*(owner\s+)?(@\{HOME\}/\*\*|/\*\*) r' <<<"$al" && bad "$f: read anywhere"
    # 2.1 (review of db6601c): no unconfined or environment-keeping exec; only ix, Cx, Px, Pix
    ux=$(grep -vE '^\S* \s*(signal|unix|dbus|ptrace)' <<<"$al" | grep -E '\s[a-zA-Z]*(Ux|ux|Ix)[a-zA-Z]*( -> \S+)?,\s*$')
    [ -z "$ux" ] && ok "$f: no unconfined exec" || bad "$f: $ux"
    # child profiles (bwrap, dirmngr) never wider than the parent on /run, /dev, /proc and secrets
    ch=$(grep -E '^(bwrap|dirmngr) ' <<<"$al")
    if [ -n "$ch" ]; then
      wide=$(grep -E '\s(owner\s+)?(/run/\*\*|@\{run\}/\*\*|/dev/\*\*|@\{PROC\}/\*\*|/proc/\*\*)\s+[a-z]*w' <<<"$ch")
      [ -z "$wide" ] && ok "$f: child profiles get no blanket /run, /dev or /proc writes" || bad "$f child: $wide"
      grep -E '^(bwrap|dirmngr) .*(/dev/video|/dev/hidraw|/dev/snd|@\{run\}/user/[^ ]*bus|gnupg/S\.gpg-agent|/run/i2pd)' <<<"$ch" && bad "$f child: camera, key, sound, bus, agent or I2P"
      if grep -q '^bwrap ' <<<"$ch"; then
        for d in '@{HOME}/.ssh/** rw' '@{run}/user/** rw' '/dev/video* rw' '/dev/hidraw* rw' '@{HOME}/.gnupg/** rw'; do
          awk '/^[[:space:]]*profile bwrap/{c=1} c' <<<"$x" | grep -qF "deny $d," && ok "$f//bwrap: deny $d" || bad "$f//bwrap: no deny $d"; done
      fi
    fi
  done <<<"$TABLE"
  grep -q 'deny @{HOME}/.gnupg/\*.conf{,.\*} w,' "$A/usr.bin.kleopatra" && ok "kleopatra: GnuPG configs read-only" || bad "kleopatra may write GnuPG configs"
else echo "SKIP apparmor_parser missing (compile, expanded checks)"; fi
# 2.1 (audit of a5fd1fb, L-7): the unconfined file manager makes no thumbnails and mounts nothing by itself
L="$R/config/includes.chroot/etc/xdg/libfm/libfm.conf" P="$R/config/includes.chroot/etc/xdg/pcmanfm/default/pcmanfm.conf"
# review N-1: libfm reads show_thumbnail from [ui] only; [config] keeps the local-only, size-capped defaults
ini() { python3 -c 'import configparser,sys; c=configparser.ConfigParser(interpolation=None); c.read(sys.argv[1]); print(c.get(sys.argv[2],sys.argv[3],fallback=""))' "$L" "$1" "$2"; }
[ "$(ini ui show_thumbnail)" = 0 ] && ok "libfm: [ui] show_thumbnail=0" || bad "libfm: thumbnails not off in [ui]"
[ "$(ini config thumbnail_local)" = 1 ] && [ "$(ini config thumbnail_max)" = 2048 ] && ok "libfm: thumbnails local-only and capped" || bad "libfm: thumbnail_local/thumbnail_max widened"
[ -n "$(ini config terminal)" ] && ok "libfm: terminal set" || bad "libfm: no terminal"
grep -qx 'mount_removable=0' "$P" && grep -qx 'mount_on_startup=0' "$P" && ok "pcmanfm: no automount" || bad "pcmanfm automounts"
for f in "$A"/usr.bin.{loupe,ristretto,file-roller,xarchiver,featherpad,mat2,metadata-cleaner,gimp,keepassxc,kleopatra}; do
  grep -q 'abstractions/audio' "$f" && bad "$(basename "$f"): sound access" || ok "$(basename "$f"): no sound access"; done
grep -q 'abstractions/audio' "$R/config/includes.chroot/etc/apparmor.d/abstractions/prestium-app-common" && bad "app-common gives sound" || ok "app-common: no sound"
exit $fail
