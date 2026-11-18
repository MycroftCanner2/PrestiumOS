#!/bin/bash
# Prestium 2.1 (review of 7242e00): what the confined apps need to start, and what Kleopatra's
# self-test (Settings > Self-Test: gpgconf, gpg, gpgsm, gpg-agent, scdaemon, dirmngr, uiserver,
# libkleopatrarc) and Claws Mail's OpenPGP use touch, checked against the compiled profiles
# (apparmor_parser -p, abstractions expanded; tests/aa_eval.py), together with what must stay denied.
# The GnuPG paths come from an strace of gpgconf --list-components/--list-options for every
# component, gpg/gpgsm --version, gpg-connect-agent, key generation, sign+encrypt, decrypt, import
# and export, and dirmngr; bubblewrap's from an strace of glycin's and mat2's bwrap command lines.
# AA_SYSTEM_DIR: Debian's /etc/apparmor.d (default). Needs apparmor_parser (PATH may need /usr/sbin).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); A=$R/config/includes.chroot/etc/apparmor.d; fail=0
command -v apparmor_parser >/dev/null || PATH=$PATH:/usr/sbin
command -v apparmor_parser >/dev/null || { echo "SKIP apparmor_parser missing"; exit 0; }
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; rm -f "$W/loupe" "$W/usr.bin.evince"; cp -r "$A"/. "$W"/
run() { # profile file, then check lines on stdin
  apparmor_parser -p -b "$W" "$W/$1" > "$W/.exp" 2>"$W/.err" || { echo "FAIL $1 does not compile"; fail=1; cat > /dev/null; return; }
  python3 -B "$R/tests/aa_eval.py" "$W/.exp" || fail=1
}
H=/home/user; G=$H/.gnupg; S=/run/user/1000/gnupg

echo "== Kleopatra (self-test, keys, sign/encrypt; GnuPG daemons it starts)"
run usr.bin.kleopatra <<EOT
allow kleopatra /usr/bin/gpgconf x:i
allow kleopatra /usr/bin/gpg x:i
allow kleopatra /usr/bin/gpgsm x:i
allow kleopatra /usr/bin/gpg-agent x:i
allow kleopatra /usr/bin/gpg-connect-agent x:i
allow kleopatra /usr/bin/gpgtar x:i
allow kleopatra /usr/lib/gnupg/scdaemon x:i
allow kleopatra /usr/lib/gnupg/keyboxd x:i
allow kleopatra /usr/lib/gnupg/tpm2daemon x:i
allow kleopatra /usr/bin/dirmngr x:C
allow kleopatra /usr/bin/pinentry x:P
allow kleopatra /usr/bin/pinentry-gnome3 x:P
allow kleopatra /usr/bin/kwatchgnupg x:i
allow kleopatra /etc/xdg/libkleopatrarc r
allow kleopatra $H/.config/libkleopatrarc rw
allow kleopatra $H/.config/kleopatrarc rw
allow kleopatra $H/.local/state/kleopatrastaterc rw
allow kleopatra $H/.local/share/kleopatra/kleopatragroupsrc rw
allow kleopatra $G/ rw
allow kleopatra $G/gpg.conf r
allow kleopatra $G/gpg-agent.conf r
allow kleopatra $G/dirmngr.conf r
allow kleopatra $G/common.conf r
allow kleopatra $G/pubring.kbx rw
allow kleopatra $G/pubring.kbx.lock rwl
allow kleopatra $G/pubring.kbx.tmp rw
allow kleopatra $G/trustdb.gpg rwk
allow kleopatra $G/random_seed rw
allow kleopatra $G/private-keys-v1.d/0123456789ABCDEF0123456789ABCDEF01234567.key rw
allow kleopatra $G/openpgp-revocs.d/0123456789ABCDEF.rev w
allow kleopatra $G/public-keys.d/pubring.db rwk
allow kleopatra $G/.#lk0x0000558fb42ed6e0.host.4242 rwl
allow kleopatra $G/gnupg_spawn_agent_sentinel.lock rwl
allow kleopatra $S/S.gpg-agent rw
allow kleopatra $S/S.keyboxd rw
allow kleopatra $S/S.dirmngr rw
allow kleopatra $S/S.uiserver rw
allow kleopatra $H/Documents/letter.txt.gpg rw
deny kleopatra $H/Downloads/letter.txt.gpg w
deny kleopatra "$H/I2P Browser/letter.txt.gpg" w
allow kleopatra $H/Downloads/key.asc r
deny kleopatra $G/gpg.conf w
deny kleopatra $G/gpg-agent.conf w
deny kleopatra $G/dirmngr.conf w
deny kleopatra $G/common.conf w
deny kleopatra $G/gpg.conf l
deny kleopatra $G/gpg-agent.conf l
deny kleopatra $G/dirmngr.conf l
deny kleopatra $G/common.conf l
deny kleopatra $G/gpg-agent.conf.new l
deny kleopatra $H/.ssh/id_ed25519 r
deny kleopatra $H/.bashrc w
deny kleopatra $H/.config/autostart/x.desktop w
allow kleopatra//dirmngr /usr/bin/dirmngr mr
allow kleopatra//dirmngr $G/dirmngr.conf r
allow kleopatra//dirmngr $G/crls.d/DIR.txt rw
allow kleopatra//dirmngr $S/S.dirmngr rw
allow kleopatra//dirmngr /etc/ssl/certs/ca-certificates.crt r
allow kleopatra//dirmngr /etc/resolv.conf r
allow kleopatra//dirmngr /proc/4242/task/4243/comm rw
deny kleopatra//dirmngr $G/pubring.kbx r
deny kleopatra//dirmngr $G/dirmngr.conf w
EOT

echo "== Claws Mail's GnuPG child (same keyring and agent as Kleopatra)"
run usr.bin.claws-mail <<EOT
allow claws-mail /usr/bin/gpg x:C
allow claws-mail /usr/bin/gpgconf x:C
allow claws-mail//gpg /usr/bin/gpg-agent x:i
allow claws-mail//gpg /usr/lib/gnupg/keyboxd x:i
allow claws-mail//gpg /usr/lib/gnupg/scdaemon x:i
allow claws-mail//gpg /usr/bin/pinentry-gnome3 x:P
allow claws-mail//gpg $G/pubring.kbx rw
allow claws-mail//gpg $G/trustdb.gpg rwk
allow claws-mail//gpg $G/private-keys-v1.d/0123456789ABCDEF0123456789ABCDEF01234567.key rw
allow claws-mail//gpg $G/gpg.conf r
allow claws-mail//gpg $G/pubring.kbx.lock rwl
deny claws-mail//gpg $G/gpg-agent.conf w
deny claws-mail//gpg $G/gpg-agent.conf l
deny claws-mail//gpg $G/common.conf l
allow claws-mail//gpg $S/S.gpg-agent rw
allow claws-mail//gpg $S/S.keyboxd rw
EOT

echo "== pinentry (started by a socket-started or app-started gpg-agent)"
run prestium.pinentry <<EOT
allow prestium_pinentry /usr/bin/pinentry-gnome3 mr
allow prestium_pinentry /run/user/1000/bus rw
allow prestium_pinentry /tmp/.X11-unix/X0 rw
allow prestium_pinentry /dev/tty rw
deny prestium_pinentry $G/private-keys-v1.d/x.key r
deny prestium_pinentry $H/.bashrc w
EOT

# bubblewrap's setup inside its private mount namespace (strace of glycin's and mat2's command lines)
BW="r:/ w:/proc/ w:/tmp/newroot/ w:/tmp/oldroot/ w:/newroot/usr/ w:/newroot/dev/ w:/newroot/dev/null
w:/newroot/dev/stdin w:/newroot/dev/shm/ w:/newroot/etc/ w:/newroot/etc/ld.so.cache w:/newroot/tmp-home/
w:/newroot/lib64 w:/newroot/home/user/ w:/newroot/run/user/1000/wayland-0 rw:/proc/4242/uid_map
rw:/proc/4242/setgroups r:/proc/sys/kernel/overflowuid"
bw() { for e in $BW; do echo "allow $1 ${e#*:} ${e%%:*}"; done; }

echo "== Loupe (glycin decoders in bubblewrap)"
echo "== Evince (document backends, settings, print preview; no secrets, no other app's folders)"
run prestium.evince <<EOT
allow evince /usr/bin/evince x:i
allow evince /usr/lib/x86_64-linux-gnu/evince/4/backends/libpdfdocument.so mr
allow evince /usr/lib/x86_64-linux-gnu/evince/4/backends/pdfdocument.evince-backend r
allow evince /usr/lib/x86_64-linux-gnu/libevdocument3.so.4 mr
allow evince /usr/share/poppler/cMap/Adobe-Japan1/H r
allow evince /usr/bin/evince-previewer x:P
allow evince $H/.config/evince/accels rw
allow evince $H/.local/share/recently-used.xbel rw
allow evince /tmp/evince-1234/print.pdf rw
allow evince /run/prestium-wl/1000/apps rw
deny evince /run/user/1000/wayland-0 rw
deny evince /run/user/1000/bus rw
deny evince /usr/bin/librewolf x
deny evince /usr/local/bin/tor-browser x
deny evince /usr/bin/xdg-open x
deny evince /usr/bin/sudo x
deny evince $G/pubring.kbx r
deny evince $H/Documents/db.kdbx r
deny evince $H/.ssh/id_ed25519 r
deny evince $H/.claws-mail/accountrc r
deny evince $H/.tor-browser/profile/key4.db r
deny evince $H/.bashrc w
deny evince $H/Downloads/f.pdf w
allow evince "$H/Tor Browser/f.pdf" r
allow evince "$H/I2P Browser/f.pdf" r
allow evince $H/Torrents/f.pdf r
deny evince "$H/Tor Browser/f.pdf" w
deny evince "$H/I2P Browser/f.pdf" w
deny evince $H/Torrents/f.pdf w
deny evince $H/Torrents/f.pdf l
deny evince /dev/video0 r
deny evince /dev/snd/pcmC0D0p w
allow evince-previewer /tmp/evince-1234/print.pdf r
allow evince-previewer /usr/lib/x86_64-linux-gnu/evince/4/backends/libpdfdocument.so mr
deny evince-previewer $G/pubring.kbx r
allow evince-thumbnailer $H/.cache/thumbnails/large/x.png w
deny evince-thumbnailer $G/pubring.kbx r
EOT
run usr.bin.loupe <<EOT
allow loupe / r
allow loupe /proc/meminfo r
allow loupe /usr/bin/bwrap x:C
$(bw loupe//bwrap)
# 2.1 (boot fix): bwrap sets no_new_privs, and the kernel refuses a plain Px under it (exec EPERM,
# then glycin's seccomp filter kills bwrap's exit_group: "Loader process exited early with status
# 159"); only a stacked transition ("ix -> &glycin-inner") is allowed. Same for mat2's helpers.
allow loupe//bwrap /usr/libexec/glycin-loaders/1+/glycin-image-rs x:&glycin-inner
allow loupe//bwrap /usr/libexec/glycin-loaders/1+/glycin-svg x:&glycin-inner
allow loupe//bwrap /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 mr
allow loupe//bwrap /var/cache/fontconfig/abc-le64.cache-9 mr
allow loupe//bwrap $H/.cache/fontconfig/abc-le64.cache-9 r
allow loupe//bwrap $H/Pictures/a.png r
deny loupe//bwrap $H/Pictures/a.png w
deny loupe//bwrap $H/.cache/fontconfig/abc-le64.cache-9 w
deny loupe//bwrap /run/user/1000/bus rw
deny loupe//bwrap $G/pubring.kbx r
deny loupe $H/.bashrc w
deny loupe $G/pubring.kbx r
EOT

echo "== mat2 (\"Remove metadata\"; ffmpeg and exiftool in bubblewrap)"
run usr.bin.mat2 <<EOT
allow mat2 /usr/bin/bwrap x:C
# 2.1 (boot fix): mat2's ProcessPoolExecutor semaphore (glibc links sem.XXXXXX to sem.mp-<random>)
allow mat2 /dev/shm/sem.mp-4zvivvcm rwkl
deny mat2 /dev/shm/other l
allow mat2 /tmp/tmpab12cd/ w
allow mat2 "$H/Documents/.remove-metadata.Ab12Cd/1/clip.cleaned.mp4" w
allow mat2 "$H/Documents/.remove-metadata.Ab12Cd/1/clip.mp4" r
deny mat2 "$H/Documents/.remove-metadata.Ab12Cd/1/clip.mp4" w
deny mat2 $H/Downloads/clip.cleaned.mp4 w
deny mat2 $H/Documents/clip.cleaned.mp4 w
deny mat2 /media/user/STICK/clip.cleaned.mp4 w
deny mat2 $H/Torrents/clip.mp4 w
deny mat2 $H/Downloads/clip.mp4 w
$(bw mat2//bwrap)
allow mat2//bwrap /usr/bin/ffmpeg x:&mat2-inner
allow mat2//bwrap /usr/bin/exiftool x:&mat2-inner
allow mat2//bwrap $H/Downloads/clip.mp4 r
allow mat2//bwrap "$H/Documents/.remove-metadata.Ab12Cd/1/clip.cleaned.mp4" w
allow mat2//bwrap "$H/Documents/.remove-metadata.Ab12Cd/1/photo.cleaned.heic_exiftool_tmp" w
deny mat2//bwrap $H/Downloads/clip.cleaned.mp4 w
deny mat2//bwrap $H/Downloads/photo.cleaned.heic_exiftool_tmp w
deny mat2//bwrap "$H/Tor Browser/clip.cleaned.mp4" w
deny mat2//bwrap /media/user/STICK/clip.cleaned.mp4 w
deny mat2//bwrap $H/Downloads/clip.mp4 w
deny mat2//bwrap $H/Downloads/other.txt w
deny mat2//bwrap $H/x.cleaned.mp4 w
deny mat2//bwrap $H/.config/autostart/x.cleaned.desktop w
deny mat2//bwrap $H/.bashrc w
deny mat2//bwrap $G/pubring.kbx r
EOT

echo "== Metadata Cleaner (cleans a file in place wherever it is in the home, outside the dot directories)"
# 2.1 (Metadata Cleaner fix, reproduced in an enforcing VM): limited to ~/Documents, every file in ~/Downloads
# failed with "Permission denied" and one elsewhere in the home showed "Unable to Read the File"
run usr.bin.metadata-cleaner <<EOT
$(bw metadata-cleaner//bwrap)
allow metadata-cleaner//bwrap /usr/bin/exiftool x:&metadata-cleaner-inner
allow metadata-cleaner//bwrap /usr/bin/ffmpeg x:&metadata-cleaner-inner
allow metadata-cleaner//bwrap /tmp/0123abcd.mp4 w
allow metadata-cleaner//bwrap $H/Downloads/clip.cleaned.mp4 w
allow metadata-cleaner//bwrap $H/clip.cleaned.mp4 w
allow metadata-cleaner//bwrap $H/Notes/clip.mp4 r
deny metadata-cleaner//bwrap $H/Downloads/clip.mp4 w
deny metadata-cleaner//bwrap $H/.config/autostart/x.cleaned.desktop w
deny metadata-cleaner//bwrap $H/bin/x.cleaned.sh w
allow metadata-cleaner /tmp/0123abcd.mp4 rw
allow metadata-cleaner "$H/Documents/clip.mp4" rw
allow metadata-cleaner $H/Downloads/clip.mp4 rw
allow metadata-cleaner $H/Downloads/clip.cleaned.mp4 rw
allow metadata-cleaner $H/Downloads/.goutputstream-A3OWY3 rw
allow metadata-cleaner "$H/Tor Browser/photo.jpg" rw
allow metadata-cleaner $H/Pictures/sub/photo.jpg rw
allow metadata-cleaner $H/photo.jpg rw
allow metadata-cleaner $H/photo.cleaned.jpg rw
allow metadata-cleaner $H/.goutputstream-A3OWY3 rw
allow metadata-cleaner $H/Notes/a.odt rw
deny metadata-cleaner $H/.bashrc w
deny metadata-cleaner $H/.profile w
deny metadata-cleaner $H/.config/autostart/x.desktop w
deny metadata-cleaner $H/.config/labwc/autostart w
deny metadata-cleaner $H/.local/bin/sudo w
deny metadata-cleaner $H/bin w
deny metadata-cleaner $H/bin/sudo w
deny metadata-cleaner $H/Desktop/x.desktop w
deny metadata-cleaner $H/Monero/wallets/wallet_1.keys rw
deny metadata-cleaner $H/Documents/db.kdbx rw
deny metadata-cleaner $G/pubring.kbx r
deny metadata-cleaner $H/.claws-mail/accountrc r
deny metadata-cleaner /media/user/STICK/photo.jpg w
EOT

echo "== inner payloads: decoders and helpers, no namespaces, capabilities, mounts, network or writes"
run usr.libexec.glycin-inner <<EOT
allow glycin-inner $H/Pictures/a.png r
deny glycin-inner $H/Pictures/a.png w
deny glycin-inner $H/Documents/notes.txt w
deny glycin-inner $G/pubring.kbx r
EOT
run usr.bin.mat2-inner <<EOT
allow mat2-inner $H/Downloads/clip.mp4 r
allow mat2-inner "$H/Documents/.remove-metadata.Ab12Cd/1/clip.cleaned.mp4" w
deny mat2-inner "$H/Documents/.remove-metadata.Ab12Cd/1/clip.mp4" w
deny mat2-inner $H/Downloads/clip.cleaned.mp4 w
deny mat2-inner $G/pubring.kbx r
EOT
run usr.bin.metadata-cleaner-inner <<EOT
allow metadata-cleaner-inner "$H/Documents/clip.mp4" r
allow metadata-cleaner-inner $H/clip.mp4 r
allow metadata-cleaner-inner "$H/Documents/clip.cleaned.mp4" w
allow metadata-cleaner-inner $H/Downloads/clip.cleaned.mp4 w
allow metadata-cleaner-inner $H/clip.cleaned.mp4 w
deny metadata-cleaner-inner "$H/Documents/clip.mp4" w
deny metadata-cleaner-inner $H/Downloads/clip.mp4 w
deny metadata-cleaner-inner $H/.config/autostart/x.cleaned.desktop w
deny metadata-cleaner-inner $G/pubring.kbx r
EOT

echo "== Audacity (audio through PipeWire; started in its own network namespace by prestium-audacity)"
run usr.bin.audacity <<EOT
allow audacity /usr/libexec/prestium-audacity mr
allow audacity /usr/lib/audacity/lib-ipc.so mr
allow audacity /usr/lib/audacity/modules/mod-flac.so mr
allow audacity /usr/lib/lv2/x.lv2/x.so mr
allow audacity /usr/lib/ladspa/x.so mr
allow audacity /usr/share/audacity/x r
allow audacity /run/user/1000/pipewire-0 rw
allow audacity /dev/snd/pcmC0D0c rw
allow audacity /run/user/1000/pulse/native rw
allow audacity $H/.local/share/audacity/x rw
allow audacity $H/.config/audacity/audacity.cfg rw
allow audacity $H/Documents/take1.aup3 rw
allow audacity $H/Music/take1.aup3 r
deny audacity $H/Music/take1.aup3 w
deny audacity $G/pubring.kbx r
deny audacity /dev/video0 rw
deny audacity /usr/bin/bwrap x
deny audacity /usr/bin/nsenter x
deny audacity /usr/local/bin/prestium-audacity x
deny audacity /usr/local/lib/prestium/audacity-ns x
deny audacity /usr/bin/audacity x
EOT

echo "== The browser launchers' bubblewrap children (Tor Browser, LibreWolf from mail and chat)"
run prestium.browser-launcher <<EOT
$(bw prestium_tor_browser_launcher//bwrap)
$(bw prestium_librewolf_launcher//bwrap)
allow prestium_tor_browser_launcher//bwrap $H/.tor-browser/profile.default/x rw
allow prestium_librewolf_launcher//bwrap $H/.librewolf/prestium/x rw
allow prestium_tor_browser_launcher//bwrap /opt/tor-browser/Browser/firefox.real r
allow prestium_tor_browser_launcher//bwrap /run/prestium-tbb/socks rw
allow prestium_tor_browser_launcher//bwrap /run/onion-grater/control rw
allow prestium_tor_browser_launcher//bwrap /run/prestium-wl/1000/apps rw
allow prestium_librewolf_launcher//bwrap /run/user/1000/prestium-sandbox/i2p-http-4242 rw
allow prestium_tor_browser_launcher//bwrap /dev/dri/card0 rw
allow prestium_tor_browser_launcher//bwrap $H/.config/gtk-3.0/settings.ini r
deny prestium_tor_browser_launcher//bwrap $H/.librewolf/x r
deny prestium_tor_browser_launcher//bwrap $H/.librewolf/x w
deny prestium_librewolf_launcher//bwrap $H/.tor-browser/x r
deny prestium_librewolf_launcher//bwrap $H/.tor-browser/x w
deny prestium_librewolf_launcher//bwrap "$H/Tor Browser/x" r
deny prestium_tor_browser_launcher//bwrap $G/private-keys-v1.d/x.key r
deny prestium_librewolf_launcher//bwrap $G/private-keys-v1.d/x.key r
deny prestium_tor_browser_launcher//bwrap $H/.ssh/id_ed25519 r
deny prestium_tor_browser_launcher//bwrap $H/Passwords.kdbx r
deny prestium_tor_browser_launcher//bwrap $H/.mozilla/firefox/profiles.ini r
deny prestium_tor_browser_launcher//bwrap $H/.purple/accounts.xml r
deny prestium_tor_browser_launcher//bwrap $H/.claws-mail/clawsrc r
deny prestium_tor_browser_launcher//bwrap $H/.config/feather/settings.json r
deny prestium_tor_browser_launcher//bwrap /etc/shadow r
deny prestium_tor_browser_launcher//bwrap /run/user/1000/bus rw
deny prestium_librewolf_launcher//bwrap /run/user/1000/bus rw
deny prestium_tor_browser_launcher//bwrap /run/user/1000/gnupg/S.gpg-agent rw
deny prestium_tor_browser_launcher//bwrap /run/prestium-wl/broker rw
deny prestium_tor_browser_launcher//bwrap /run/prestium/logs/tor.log r
deny prestium_tor_browser_launcher//bwrap $H/Downloads/x r
deny prestium_tor_browser_launcher//bwrap $H/Documents/x r
deny prestium_tor_browser_launcher//bwrap /dev/video0 rw
deny prestium_tor_browser_launcher//bwrap /dev/hidraw0 rw
deny prestium_tor_browser_launcher//bwrap /usr/bin/sudo x
EOT

echo "== LibreOffice (first start creates its user profile folders)"
# 2.1 (boot fix): first start looks the user up with getpwuid() before it can name its profile folder;
# with /etc/passwd or /etc/nsswitch.conf denied it stops with "User installation could not be
# completed" (exit 77). Seen in the kernel log on a Debian 13 VM running this profile.
run usr.lib.libreoffice.program <<EOT
allow libreoffice /etc/nsswitch.conf r
allow libreoffice /etc/passwd r
allow libreoffice /etc/group r
deny libreoffice /etc/shadow r
allow libreoffice $H/ w
allow libreoffice $H/.config/ w
allow libreoffice $H/.config/libreoffice/ rw
allow libreoffice $H/.cache/ w
allow libreoffice $H/.cache/libreoffice/ rw
allow libreoffice $H/.local/ w
allow libreoffice $H/.local/share/ w
allow libreoffice $H/.local/share/libreoffice/ rw
allow libreoffice $H/.config/libreoffice/4/ rw
allow libreoffice $H/.config/libreoffice/4/user/ rw
allow libreoffice $H/.config/libreoffice/4/user/registrymodifications.xcu mrw
allow libreoffice /tmp/lo.tmp m
allow libreoffice /var/tmp/lo.tmp m
allow libreoffice /dev/shm/lo.tmp m
allow libreoffice /tmp/ w
allow libreoffice /var/tmp/ w
allow libreoffice /dev/shm/ w
allow libreoffice $H/.config/libreoffice/4/user/extensions/ w
allow libreoffice $H/.config/libreoffice/4/user/uno_packages/cache/ w
allow libreoffice $H/.cache/libreoffice/4/ w
allow libreoffice $H/.local/share/libreoffice/4/user/ w
allow libreoffice $H/Documents/letter.odt rw
allow libreoffice $H/Downloads/letter.odt r
deny libreoffice $H/Downloads/letter.odt w
deny libreoffice $G/pubring.kbx r
EOT
# the user lookup comes from nameservice-strict, not nameservice (no inet or netlink rules), and it stays offline
L=$A/usr.lib.libreoffice.program
grep -q '^ *include <abstractions/nameservice-strict>' "$L" || { echo "FAIL LibreOffice has no nameservice-strict (first start: exit 77)"; fail=1; }
grep -q '^ *include <abstractions/nameservice>' "$L" && { echo "FAIL LibreOffice includes the full nameservice abstraction"; fail=1; }
grep -q '^ *deny network inet,' "$L" && grep -q '^ *deny network inet6,' "$L" || { echo "FAIL LibreOffice lost its network deny"; fail=1; }

echo "== the viewers, players and editors read anywhere in the home, read-only, secrets denied"
# 2.1: prestium-viewer-home-read. Loupe's decoder gets the file as a descriptor, which AppArmor checks
# against loupe//bwrap and glycin-inner too (the decoder runs as glycin-inner stacked on loupe//bwrap).
hr() { for p in "$@"; do cat <<EOR
allow $p $H/Pictures/x.png r
allow $p $H/.local/share/y.jpg r
allow $p $H/Mail/inbox/1 r
allow $p "$H/Tor Browser/a.pdf" r
allow $p "$H/I2P Browser/b.png" r
allow $p $H/Torrents/t.mkv r
allow $p $H/Downloads/sub/dir/c.ogg r
deny $p $H/Pictures/x.png l
deny $p $H/.local/share/y.jpg w
deny $p $H/.ssh/id_ed25519 r
deny $p $G/pubring.kbx r
deny $p $H/Documents/Passwords.kdbx r
deny $p $H/.local/share/keyrings/login.keyring r
deny $p $H/.mozilla/firefox/profiles.ini r
deny $p $H/.tor-browser/profile.default/key4.db r
deny $p $H/.librewolf/x/logins.json r
deny $p $H/.claws-mail/accountrc r
deny $p $H/.purple/accounts.xml r
deny $p $H/.config/gajim/x r
deny $p $H/Monero/wallets/w.keys r
deny $p $H/.config/onionshare/onionshare.json r
deny $p $H/.config/keepassxc/keepassxc.ini r
deny $p $H/.bash_history r
EOR
done; }
run usr.bin.loupe <<EOT
$(hr loupe loupe//bwrap)
EOT
run usr.libexec.glycin-inner <<EOT
$(hr glycin-inner)
EOT
run usr.bin.vlc <<EOT
$(hr vlc)
EOT
run prestium.evince <<EOT
$(hr evince evince-previewer evince-thumbnailer)
EOT
run usr.lib.libreoffice.program <<EOT
$(hr libreoffice)
EOT
run usr.bin.featherpad <<EOT
$(hr featherpad)
EOT
run usr.bin.audacity <<EOT
$(hr audacity)
EOT

echo "== KeePassXC (directory write, and link for Qt 6 linkat commit; files stay .kdbx-only), VLC, the others: no ~/.gnupg, offline"
run usr.bin.keepassxc <<EOT
allow keepassxc $H/ w
allow keepassxc $H/Documents/ w
allow keepassxc $H/Documents/Passwords.kdbx rwk
allow keepassxc $H/Documents/New.kdbx w
allow keepassxc $H/Documents/Passwords.kdbx.lock w
allow keepassxc $H/Documents/Passwords.kdbxAbC123 w
allow keepassxc $H/Documents/Passwords.kdbx.AbC123 w
allow keepassxc $H/Documents/Passwords.kdbx l
allow keepassxc $H/Documents/Passwords.kdbx.AbC123 l
allow keepassxc $H/Passwords.kdbxAbC123 w
deny keepassxc $H/Documents/notes.txt w
allow keepassxc /media/user/STICK/ w
allow keepassxc /media/user/STICK/Passwords.kdbx rwk
allow keepassxc /media/user/STICK/Passwords.kdbxAbC123 w
allow keepassxc /media/user/STICK/Passwords.kdbx l
allow keepassxc /media/user/STICK/Passwords.kdbx.AbC123 l
deny keepassxc /media/user/STICK/notes.txt w
# 2.1 (boot fix): Qt's safe save opens an unnamed O_TMPFILE, which AppArmor names "<dir>/#<inode>"
# (kernel log on a Debian 13 VM: name="/home/user/Documents/#135221" denied_mask="w"), then links it
# onto the .kdbx name; the link may not carry more than the temp has, so the temp needs "k" too
# (denied_mask="k" on the link without it). Without these, every save failed: "Permission denied".
allow keepassxc $H/Documents/#135221 rwk
allow keepassxc $H/#135221 rwk
allow keepassxc /media/user/STICK/#135221 rwk
# its window state (~/.cache/keepassxc/keepassxc.ini) is saved the same way: link onto the name
allow keepassxc $H/.cache/keepassxc/#135222 rwk
allow keepassxc $H/.cache/keepassxc/keepassxc.ini l
allow keepassxc $H/.local/share/keepassxc/#135223 rwk
# the temp name opens no secret folder or startup file
deny keepassxc $H/.ssh/#135221 w
deny keepassxc $H/.gnupg/#135221 w
deny keepassxc $H/.config/autostart/#135221 w
deny keepassxc $H/Documents/#notes w
# 2.1: the Qt file dialog's QtProject.conf (it remembers the last folder), saved with a .lock and
# an O_TMPFILE linked to "QtProject.conf.XXXXXX" and renamed onto it (overlay home on a Debian 13 VM:
# mknod ".config/QtProject.conf.lock" and link ".config/QtProject.conf.DEteDY" denied without these)
allow keepassxc $H/.config/QtProject.conf rwl
allow keepassxc $H/.config/QtProject.conf.DEteDY rwl
allow keepassxc $H/.config/QtProject.conf.lock rwk
allow keepassxc $H/.config/#108 rwk
# and nothing else in ~/.config
deny keepassxc $H/.config/QtProject.confX w
deny keepassxc $H/.config/QtProject.conf.toolong w
deny keepassxc $H/.config/kdeglobals w
deny keepassxc $H/.config/gajim/settings.sqlite w
deny keepassxc $H/.config/librewolf/prefs.js w
deny keepassxc $H/.config/autostart/x.desktop w
allow keepassxc $H/.config/keepassxc/keepassxc.ini rwk
allow keepassxc $H/.cache/ w
allow keepassxc $H/.cache/keepassxc/ rw
allow keepassxc $H/.local/ w
allow keepassxc $H/.local/share/ w
allow keepassxc $H/.local/share/keepassxc/ rw
allow keepassxc /tmp/keepassxc-user.socket rw
allow keepassxc /dev/hidraw0 rw
deny keepassxc $G/pubring.kbx r
EOT
run usr.bin.vlc <<EOT
allow vlc /usr/lib/x86_64-linux-gnu/vlc/vlc-cache-gen x:i
allow vlc $H/.config/vlc/vlcrc rw
deny vlc $G/pubring.kbx r
EOT
# network: only Audacity has a TCP rule among the viewers, and only "inet stream" (test_viewer_confinement.sh);
# it is started only in its own, empty network namespace, so that reaches its own loopback only
# (tests/test_audacity_netns.sh)
[ $fail = 0 ] && echo "apparmor startup: OK"; exit $fail
