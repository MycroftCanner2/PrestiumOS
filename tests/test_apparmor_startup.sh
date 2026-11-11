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
cp -r "${AA_SYSTEM_DIR:-/etc/apparmor.d}"/. "$W"/ 2>/dev/null; rm -f "$W/loupe"; cp -r "$A"/. "$W"/
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
allow kleopatra $H/Downloads/key.asc r
deny kleopatra $G/gpg.conf w
deny kleopatra $G/gpg-agent.conf w
deny kleopatra $G/dirmngr.conf w
deny kleopatra $G/common.conf w
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
run usr.bin.loupe <<EOT
allow loupe / r
allow loupe /proc/meminfo r
allow loupe /usr/bin/bwrap x:C
$(bw loupe//bwrap)
allow loupe//bwrap /usr/libexec/glycin-loaders/1+/glycin-image-rs x:i
allow loupe//bwrap /usr/libexec/glycin-loaders/1+/glycin-svg x:i
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
allow mat2 /tmp/tmpab12cd/ w
allow mat2 $H/Downloads/clip.cleaned.mp4 w
$(bw mat2//bwrap)
allow mat2//bwrap /usr/bin/ffmpeg x:i
allow mat2//bwrap /usr/bin/exiftool x:i
allow mat2//bwrap $H/Downloads/clip.mp4 r
allow mat2//bwrap $H/Downloads/clip.cleaned.mp4 w
allow mat2//bwrap $H/Downloads/photo.cleaned.heic_exiftool_tmp w
allow mat2//bwrap "$H/Tor Browser/clip.cleaned.mp4" w
allow mat2//bwrap /media/user/STICK/clip.cleaned.mp4 w
deny mat2//bwrap $H/Downloads/clip.mp4 w
deny mat2//bwrap $H/Downloads/other.txt w
deny mat2//bwrap $H/x.cleaned.mp4 w
deny mat2//bwrap $H/.config/autostart/x.cleaned.desktop w
deny mat2//bwrap $H/.bashrc w
deny mat2//bwrap $G/pubring.kbx r
EOT

echo "== Metadata Cleaner (mat2 writes to /tmp, then it moves the file)"
run usr.bin.metadata-cleaner <<EOT
$(bw metadata-cleaner//bwrap)
allow metadata-cleaner//bwrap /tmp/0123abcd.mp4 w
deny metadata-cleaner//bwrap $H/Downloads/clip.cleaned.mp4 w
allow metadata-cleaner /tmp/0123abcd.mp4 rw
allow metadata-cleaner $H/Downloads/clip.mp4 rw
EOT

echo "== GIMP (system configuration, plug-ins)"
run usr.bin.gimp <<EOT
allow gimp /etc/gimp/3.0/gimprc r
allow gimp /etc/gimp/3.0/unitrc r
allow gimp /etc/gimp/3.0/templaterc r
allow gimp /usr/lib/x86_64-linux-gnu/gimp/3.0/plug-ins/file-png/file-png x:i
allow gimp /usr/lib/x86_64-linux-gnu/gimp/3.0/plug-ins/foggify/foggify.py x:i
allow gimp /usr/bin/env x:i
allow gimp /usr/bin/python3.13 x:i
allow gimp /usr/bin/gjs-console x:i
allow gimp /usr/bin/gimp-script-fu-interpreter-3.0 x:i
deny gimp /etc/shadow r
EOT

echo "== Audacity (audio through PipeWire)"
run usr.bin.audacity <<EOT
allow audacity /usr/lib/audacity/lib-ipc.so mr
allow audacity /run/user/1000/pipewire-0 rw
allow audacity /run/user/1000/pulse/native rw
allow audacity $H/.local/share/audacity/x rw
deny audacity $G/pubring.kbx r
EOT

echo "== The browser launchers' bubblewrap children (Tor Browser, LibreWolf from mail and chat)"
run prestium.browser-launcher <<EOT
$(bw prestium_tor_browser_launcher//bwrap)
$(bw prestium_librewolf_launcher//bwrap)
deny prestium_tor_browser_launcher//bwrap $H/.librewolf/x w
deny prestium_librewolf_launcher//bwrap $H/.tor-browser/x w
EOT

echo "== KeePassXC, VLC, the others: no ~/.gnupg, offline"
run usr.bin.keepassxc <<EOT
allow keepassxc $H/Documents/Passwords.kdbx rw
allow keepassxc /tmp/keepassxc-user.socket rw
allow keepassxc /dev/hidraw0 rw
deny keepassxc $G/pubring.kbx r
EOT
run usr.bin.vlc <<EOT
allow vlc /usr/lib/x86_64-linux-gnu/vlc/vlc-cache-gen x:i
allow vlc $H/.config/vlc/vlcrc rw
deny vlc $G/pubring.kbx r
EOT
# network: only Audacity has a TCP rule among the viewers, and only "inet stream" (test_viewer_confinement.sh)
[ $fail = 0 ] && echo "apparmor startup: OK"; exit $fail
