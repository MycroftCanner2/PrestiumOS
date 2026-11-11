# Changelog

## 2.1 (in progress)

Enhanced security and new features. Changes will be listed here as they land.

### Updates
- **The Lounge ships the 10 Theme Factory themes, and Tech Innovation is the new default.** Ocean
  Depths, Sunset Boulevard, Forest Canopy, Modern Minimalist, Golden Hour, Arctic Frost, Desert Rose,
  Tech Innovation, Botanical Garden and Midnight Galaxy are local theme packages
  (`/var/lib/thelounge/packages/node_modules/thelounge-theme-*`, root-owned and read-only like the
  others). Prestium and The Lounge's own themes can still be picked in Settings. This replaces the
  Prestium theme as the default (see below): in it, your own messages were dimmed and Settings fields
  could show black text on a dark box. Every theme now sets the colour and background of text fields
  (Settings, Connect, message box and placeholders) and of chat text explicitly; chat text is white on
  the dark themes and a dark palette colour on the light ones, and each text/background pair is at
  least 4.5:1 (WCAG AA), using a slightly lighter or darker shade of a palette colour where the raw one
  fell short. Nothing is loaded from outside: no web fonts, images or URLs; Theme Factory's fonts map
  to ones Prestium ships (DejaVu Sans, Nimbus Sans, Nimbus Roman, C059). The sign-in splash uses Tech
  Innovation's colours. Palettes: Theme Factory (github.com/anthropics/skills, commit
  `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`), Apache License 2.0, notice in
  `/var/lib/thelounge/packages/THEME-FACTORY-NOTICE.txt`. The CSS is generated from one template by
  `scripts/thelounge-themes.py` (`tests/test_thelounge_theme.sh`).
- **Node.js 24.22.3** (security release, 2026-11-11). The Lounge's runtime is the official
  linux-x64 tarball in `/opt/nodejs`, pinned in `thirdparty/versions.sh`. This release
  fixes high-severity HTTP/2 and TLS issues in 24.x. The signed `SHASUMS256.txt` verifies
  with a current Node.js releaser key (`NODE_KEYS`). The previous pin was 24.22.2.
- **Tor Browser 16.0.1** (released 2026-11-10: Firefox security fixes, tor 0.4.9.16). `thirdparty/versions.sh`
  pins the new tarball's SHA-256; its signature verifies with the shipped Tor Browser key through the signing
  subkey. dist.torproject.org no longer serves 16.0, so the old pin could not build. The Tor daemon and
  LibreWolf still come from their apt repositories at build time.
- **Tor Browser is now the newest release at every build**, with no version file to edit.
  `scripts/tb-latest.sh` asks the Tor Project's update service (aus1, HTTPS, no redirects) for the version
  number only, then builds the download URL on dist.torproject.org. The tarball must carry a valid
  signature by the pinned Tor Browser key (the same expired and revoked key checks) and be no older than
  `TB_MIN_VERSION` (16.0.1), so an older release that is still validly signed can't be slipped in. With no
  pin, the signature is the only check (there was a pinned SHA-256 too). The build log prints the
  version and SHA-256 it shipped. To pin a release for a reproducible build, set
  `PRESTIUM_TB_VERSION` and `PRESTIUM_TB_SHA256` (`tests/test_tb_latest.sh`). torbrowser-launcher is
  not used: it downloads Tor Browser on first launch, which on a live system means every boot.
- **Tor 0.4.9.16** (the system Tor daemon). deb.torproject.org's trixie repository has served
  `0.4.9.16-1~d13.trixie+1` since 2026-11-10, and the next build installs it. Tor isn't pinned to a version, so no
  other change is needed.

### New: virtual machine warning and network diagnosis
- **Prestium tells you when it runs in a virtual machine**, the way Tails does: a notification at login
  says the host and the virtualization software can see and record everything done in Prestium.
  Detection is `systemd-detect-virt --vm`, run at boot by `prestium-vm-netcheck.service`
  (`ConditionVirtualization=vm`, so it never runs on real hardware); `prestium-vm-notify` shows it.
- **If Tor or I2P hasn't connected in a VM after 10 minutes, the desktop says why.** The service checks
  every 2 minutes, for about 40 minutes. It looks at Tor's bootstrap and clock-skew messages, the skew
  prestium-timesync measured, i2pd's TCP connections to other computers and the default route. Then it
  names the likely cause and the setting that fixes it: no network adapter or no route; user-mode
  networking (gateway 10.0.2.2: QEMU user/SLIRP, VirtualBox NAT, virt-manager's "User session"); a VM
  clock set to local time (virt-manager `<clock offset='utc'>`, VirtualBox "Hardware Clock in UTC Time",
  Hyper-V time synchronization); or Tor working while I2P has no peers, which points to a VPN or
  firewall on the host blocking I2P's ports. The diagnosis disappears once both connect. Read-only: it
  never changes the clock, the network, Tor or i2pd (`tests/test_vm_check.sh`). i2pd's connections are
  matched on the whole `uid:2000` field, so another user such as uid 20000 is never counted as an I2P peer.
  Only established TCP (NTCP2) connections count, so an I2P session that uses only UDP (SSU2) can look
  like no peers.

### New: Prestium theme for The Lounge
- **The Lounge (IRC) now uses a dark Prestium theme** by default, with the same palette as the i2pd
  console and I2P Torrents pages. It's a local theme package
  (`/var/lib/thelounge/packages/node_modules/thelounge-theme-prestium`) built on The Lounge's own dark
  "Morning" theme. It loads no fonts, images or anything else from outside. The other themes are still
  in Settings. The sign-in page is dark too, so it no longer flashes white
  (`tests/test_thelounge_theme.sh`).

### Security audit fixes (2026-11-10)
Two source audits of `95f2f6c` (no booted ISO). Each item has a regression test.
- **Browser launchers take nothing from the caller's environment.** Claws Mail, Gajim and Pidgin start
  `tor-browser` and `librewolf-i2p` with AppArmor `Ux`, which keeps their environment. The launchers
  honoured `PRESTIUM_SANDBOX_LIB`, `PRESTIUM_BWRAP`, `PRESTIUM_WL_BASE`, `PRESTIUM_LIBREWOLF` and
  `PRESTIUM_I2P_HTTP_PORT` (test hooks), and bash also reads `BASH_ENV` and exported functions, so a
  compromised mail or chat client could run its own code outside its profile. They now run as
  `bash -p`, set a fixed PATH and use fixed paths only; the tests run patched copies
  (`tests/test_launcher_env.sh`).
- **The Tor Browser tarball must contain the release that was asked for.** An OpenPGP signature does not
  cover the file name, so a compromised download server could serve an older (or alpha) tarball that is
  still signed by the Tor Browser key under the newest release's name, below `TB_MIN_VERSION`. The build now
  reads `Browser/tbb_version.json` from the signed tarball (release channel, linux-x86_64) and requires it
  to equal the requested version, and hook 0200 checks the installed copy again. The tarball is verified,
  hashed and staged from one private copy, so a change in the shared cache between those steps can't slip
  in. `tb_version_ok` accepts one line only. Detached signatures (build and Browser Updater) must be one
  signature and no embedded data (`sigstatus_detached_ok`; GnuPG 2.4.7 already refuses an inline-signed
  file there, this does not depend on it). (`tests/test_tb_latest.sh`, `tests/test_sigcheck.sh`)
- **Browser Updater root helper, tighter.** The new browser tree gets Prestium's settings, root
  ownership and its final permissions while it is still in the root-only work directory, and is moved
  where the desktop user can see it only after that; permissions are set through a descriptor that never
  follows a symlink. Archives and packages with an entry not owned by root, a group- or world-writable
  entry, or the same name twice are refused (signed Tor Browser 16.0 and LibreWolf trees have none). The
  copy of each staged file (made as the user) is read with a size cap on its error output and a
  15-minute limit, so a stopped or held copier can't keep the helper and its lock. Reset no longer
  allows installing a release older than one already installed this session
  (`/var/lib/prestium/browser-updates-highest`, in RAM). (`tests/test_browser_install.py`)
- **onion-grater can only read, not trace.** The Tor control-port filter keeps `CAP_SYS_PTRACE` to read
  `/proc/<pid>/exe` of the app that connects, but that capability also allows attaching to and writing
  the memory of any process, root's included, and the filter parses requests from Tor Browser. Its unit
  now filters out the `@debug` syscalls (ptrace, process_vm_*) on top of an `@system-service` allow-list,
  and a new enforced AppArmor profile (`prestium_onion_grater`) allows `ptrace (read)` only and denies
  `/proc/*/mem`. Tor Browser's profile allows that read (`ptrace (readby)`), since AppArmor checks both
  sides. Not yet run on a booted ISO: NEWNYM and the circuit display must still work there.
  (`tests/test_onion_grater_hardening.sh`)
- **i2pd and Tor can no longer reach Prestium's local services.** Both had a blanket firewall accept
  that also covered loopback, so a compromised i2pd or Tor could connect to The Lounge (9000), the
  i2pd console (7070) and the torrent RPC (7685). Their accepts are now for the network only; on
  loopback i2pd keeps only its SOCKS outproxy tunnel (4500) and Tor only the kernel's ephemeral ports
  32768-60999, where its pluggable transports listen. Bridges must be re-checked on a booted ISO.
  (`tests/test_ferm_loopback.sh`)
- **The Lounge can't rewrite its own code.** It `require()`s `config.js` and its packages (the sign-in
  page and the theme) at every start, and they belonged to the thelounge uid. They are now root-owned
  and read-only for The Lounge (`root:thelounge` 0640/0750, `ReadOnlyPaths=` in the unit, `deny ... wl`
  in its AppArmor profile). The real The Lounge 4.5.2 still starts and loads both packages with its
  package files made read-only (checked in a copy, not yet as its own uid on a booted system). i2pd and
  Tor now run with `ProtectProc=invisible`, so they can't read other processes' command lines.
  (`tests/test_thelounge_readonly.sh`)
- **The VM network check no longer runs as root**, and never copies Tor's log text. It runs as its own
  user `prestium-vmcheck` (group systemd-journal, to read Tor's and i2pd's journal) with a tighter
  sandbox (`ProtectProc=invisible`, `IPAddressDeny=any`, `@system-service` syscalls only, no
  namespaces). Tor's clock-skew line can name the relay it came from; the world-readable diagnosis now
  says only "clock is 7 hours, 3 minutes behind" (or "clock skew reported"). (`tests/test_vm_check.sh`)
- **The Wayland broker and the MAC guard keep only the root powers they use.** The MAC guard (it reads
  settings the user controls) is limited to `CAP_NET_ADMIN`, D-Bus and netlink sockets and
  `@system-service` syscalls. The Wayland broker keeps chown/chmod, access to the user's runtime
  directory, setuid/setgid/kill for the tools it starts, and reading labwc's `/proc` entry, and loses
  every admin, network, module, raw I/O and clock capability. It gets no syscall filter or
  `NoNewPrivileges`, because the session tools it starts inherit them (swaylock's PAM helper is setgid,
  the idle lock uses sudo). (`tests/test_service_hardening.sh`)
- **Setting the clock by hand has limits.** `sudo date -s` let any unconfined program of the user move
  the clock anywhere, and the clock decides whether Tor's consensus, TLS certificates and the Browser
  Updater's publisher keys count as valid. It is replaced by `sudo prestium-set-clock 2026-11-10 14:30`
  (UTC): strict date and time, never before the image was built (one day of slack) or more than 10
  years after, and a safety notice on the desktop afterwards. The build records its date in
  `/usr/share/prestium/build-date`. (`tests/test_set_clock.sh`)
- **Fewer filesystem drivers can be loaded.** udisks lets the desktop user attach disk images (needed
  for VeraCrypt file containers), so any program of the user can make the kernel parse a filesystem
  image it chose. 21 rarely used filesystem drivers (hfs, minix, jfs, reiserfs, nilfs2, ufs, erofs and
  others) are now blocked like cramfs, freevxfs and jffs2 were. FAT, exFAT, NTFS, ext4, Btrfs, XFS,
  F2FS, ISO 9660, UDF and HFS+ still work. (`tests/test_fs_blacklist.sh`)
- **Stronger screen lock.** The session password (screen lock and administration prompts) must now have
  at least 8 characters, and the dialog suggests a few unrelated words. Each wrong password at the lock
  screen costs at least 4 seconds (`/etc/pam.d/swaylock`, pam_faildelay). There is no lockout, which
  would shut the only user out of the session. (`tests/test_session_lock.sh`)
- **Signature checks at build time use one publisher key each.** The build imported every publisher key
  into one keyring and hid import errors; each signature is now checked in a throw-away keyring that
  holds only its publisher's key (Tor Browser, Mozilla, Feather), and a failed import stops the build.
  Node.js: the releasers' keybox holds 29 keys, 9 of them expired and most of them retired; the
  signature must now come from one of the 8 current releasers' primary keys (`NODE_KEYS` in
  `thirdparty/versions.sh`, from the Node.js README on 2026-11-10; Node 24.22.2 is signed by one of
  them). (`tests/test_sigcheck.sh`)
- **Cleanup.** `/etc/i2pd/i2pd.conf`, which i2pd does not use, had drifted from the live
  `/var/lib/i2pd/i2pd.conf` (SAM was on there); hook 0700 now installs the live file in its place. The
  desktop user is no longer in group i2pd, which gave it nothing (`/var/lib/i2pd` is 0700). It stays in
  prestium-localweb, which the local-only Firefox needs. (`tests/test_i2pd_config_copy.sh`)
- **One script for all checks.** `tests/ci.sh` (run by hand on Debian 13) runs shellcheck at error
  level on all shell scripts, compiles every AppArmor profile, scans for committed private keys and
  tokens, prints `systemd-analyze security` scores, and runs the tests that don't need a live Wayland
  session.
- **Release files for a signed download.** `build.sh` now also writes `SHA256SUMS` (the ISO, its manifest
  and its package list) and `Prestium-<version>-amd64.manifest`: the image's SHA-256 and size, build
  date, source commit, Debian package count, the Tor Browser version and SHA-256 that went in, the pinned
  Firefox, Node.js, The Lounge and Feather versions, and the Tor, i2pd and LibreWolf package versions.
  `scripts/sign-release.sh FINGERPRINT`, run by the release key's holder, writes and checks a detached
  `SHA256SUMS.asc`. The ISO itself is not signed yet: that needs the release key.
  (`tests/test_release_files.sh`)
- **README: how to verify a download**, with `gpg --verify SHA256SUMS.asc` for signed releases and the
  SHA-256 comparison for 2.0, which has no signed checksum file.
- **Repeatable builds (first step).** `PRESTIUM_SNAPSHOT=20261110T000000Z` builds from
  snapshot.debian.org at that time, and `build.sh` sets `SOURCE_DATE_EPOCH` to the commit's time. The
  image is not yet bit-for-bit reproducible. (`tests/test_build_snapshot.sh`)
- **The desktop says when the image is old.** Prestium does not update itself during a session, so
  security fixes only arrive with a newer image. Five minutes after login, a notice says how many days
  old the image is once it is past 45 days. `/etc/os-release` has the build date as `BUILD_ID`.
  (`tests/test_age_notify.sh`)
- **Browsers opened from mail and chat run in their own AppArmor profiles.** Claws Mail, Gajim and Pidgin
  started the Tor Browser and I2P Browser launchers unconfined ("Ux"), so a compromised client could
  run them with a crafted HOME and overwrite a file through a symlink before the sandbox started. They
  now use "Px" into `prestium_tor_browser_launcher` and `prestium_librewolf_launcher`, which may write
  only their own browser's directories and start bubblewrap in a child profile of their own. Of the
  home directory, that child may write only its own browser's folders; it can still write what
  bubblewrap needs (/tmp, the user's own /run, ~/.bash_history from the bash abstraction) and use mount
  and user namespaces, and only bubblewrap runs there, with arguments the launcher builds. The launchers also take HOME and XDG_RUNTIME_DIR from the system, not the
  caller. From the menu, the launchers run as before. Claws Mail's passphrase prompt (pinentry) has its
  own profile too: no writes under the home directory, no programs, and no network socket but a local
  one (it uses `nameservice-strict` and denies inet, inet6 and netlink). The GTK and GNOME
  abstractions still let it write scratch files in /tmp and /var/tmp.
  (`tests/test_browser_launcher_apparmor.sh`, `tests/test_launcher_env.sh`)
- **The Lounge's sign-in token works once and never appears in a command line.** The launcher token
  was valid all boot and went to the local-only Firefox in its URL, which every user could read in
  `/proc`. Now The Lounge (patched at build time) deletes the launcher's session when it is used, gives
  the browser a session token of its own, and writes the next launcher token to
  `/run/prestium-thelounge-launch/token` (readable by the desktop user only). "IRC (The Lounge)" hands
  the token to Firefox through a one-off page in a private folder (0700, the file 0600, deleted after
  two minutes). Firefox's policy allows that one folder as its only `file://` exception.
  (`tests/test_thelounge_launch_token.sh`, run against the real The Lounge 4.5.2)

### Fresh audit of 96468c5 (2026-11-10)
- **The first session password is set only from the lock dialog** (L-2). Any program of the desktop
  user could run "sudo prestium-session-password set" before the person at the screen did, and so choose
  the lock password. Now the Wayland broker shows the dialog on the compositor's full socket (no
  application can draw over it, type into it or read it) and sets the password as root; sudo allows only
  "status", and the helper refuses "set" through sudo. (`tests/test_session_lock.sh`)
- **The clock sync over Tor has bounds** (L-3). prestium-timesync and prestium-clockfix now refuse a
  time before the image was built (one day of slack) or more than 10 years after it, as
  prestium-set-clock does; timesync raises a safety flag when it refuses, or when it moves the clock by
  more than a day. (`tests/test_timesync_bounds.sh`)
- **timesync, clockfix and the USB watchdog have a systemd sandbox** (L-3): bounded capabilities and
  NoNewPrivileges for all three; a read-only system, a syscall filter and no devices for the two clock
  services; no network at all for clockfix. The watchdog keeps /tmp, the overlay and
  /proc/sysrq-trigger reachable, which it must wipe and write.
- **The Wayland broker refuses system uids and has more of a sandbox** (L-4): only login users (uid
  1000 to 60000); /usr and /boot read-only, only local and netlink sockets, no namespaces, no new
  setuid files, native syscalls only. It still has no NoNewPrivileges or syscall filter (sudo and
  swaylock's helper are setuid), and /etc and the home directory stay writable (chpasswd, screenshots).
  (`tests/test_service_hardening.sh`)
- **Root daemons ignore their test overrides when installed** (I-1). The broker, prestium-wl-config and
  the MAC guard read PRESTIUM_* variables only when run from the source tree, so the installed copies no
  longer rely on sudo's env_reset. (`tests/test_root_env_overrides.py`)
- **The programs that open downloaded files are confined** (M-1). Loupe, Ristretto, VLC, File Roller,
  Xarchiver, FeatherPad, mat2, Metadata Cleaner, GIMP and Audacity now run under enforced AppArmor
  profiles (`abstractions/prestium-viewer`): no network, no camera, no admin tools, no other app's data
  (mail, chat, browser profiles), no OpenPGP keys, no KeePassXC databases or key files. They may read
  the file folders (Desktop, Documents, Downloads, Pictures, Music, Videos, Public, Templates,
  OnionShare, the Tor Browser's downloads, unlocked volumes) and their own settings; the editors, the
  archive managers and the metadata cleaners may also save into the file folders, never into the Tor
  Browser's folder (mat2 only writes its ".cleaned" copy there), the home directory itself or a dot
  directory. Loupe's image decoders and mat2's helpers keep their own bubblewrap sandbox, in a child
  profile with the same limits. Debian's unconfined "loupe" profile is removed.
  (`tests/test_viewer_confinement.sh`, which checks the compiled profiles)
- **KeePassXC and Kleopatra are confined too.** KeePassXC may open *.kdbx databases anywhere in the
  home and key files in the file folders, and use a security key; it has no network (no icon downloads
  or breach checks), no OpenPGP keys, and can't write the browsers' directories (no browser
  integration) or start other programs. Kleopatra and the GnuPG tools it starts may use ~/.gnupg and the
  file folders; only its dirmngr, in a child profile, opens TCP sockets (the firewall lets it reach only
  Tor), and passphrase prompts go to the pinentry profile.
- Files outside the file folders (for example a text file directly in the home directory, or in a dot
  directory) can no longer be opened in these programs; move them into Documents first.
  VLC has no network access, so it can no longer play network streams (URLs, DLNA, internet radio);
  it plays local files only.
- **onion-grater checks how a Python client was started** (L-1). Before, any program of the user could
  start the real nyx, OnionShare or Tor Connection Assistant with its own PYTHONPATH or LD_PRELOAD and
  get that client's allow-list. A client whose environment sets PYTHON* (other than
  PYTHONDONTWRITEBYTECODE, PYTHONUNBUFFERED, PYTHONIOENCODING, PYTHONUTF8), LD_*, GCONV_PATH or
  GLIBC_TUNABLES, or that runs executable code from outside /usr, /lib and the Tor Browser install, is
  refused. Python no longer loads the user's own site-packages anywhere on the system (hook 0460), so a
  .pth file in the home can't run inside these clients either. onion-grater's profile may now read a
  client's environment and memory map (never its memory). (`tests/test_onion_grater_tamper.py`)
- **`tests/ci.sh` gates `systemd-analyze security`**: every Prestium unit must score 5.0 or lower
  (timesync 3.2, clockfix 2.1, USB watchdog 4.9 after this release; they were 9.4), except the Wayland
  broker (5.4, down from 7.9), the early firewall and the two shutdown wipes, which need the whole
  system by design. It runs the offline analysis in a user namespace when it isn't root.
- **Review of 4ccd585:**
  - The GnuPG passphrase prompt's profile (prestium_pinentry) is attached to the pinentry programs, so a
    prompt started by the session's own gpg-agent is confined too.
  - New prestium-gnupg-check (a root timer, every 2 minutes) raises the "gnupg-helper" safety flag when
    an unconfined gpg-agent, dirmngr, scdaemon or keyboxd runs and that user's GnuPG configuration names
    a helper program outside /usr. It logs which GnuPG daemons run and under which profile.
  - Confined apps may not run newgrp or sg either.
- **Review of 7242e00:**
  - prestium-gnupg-check resolves a helper path before it decides whether the helper is a system one:
    the path must be absolute, lie in a root-only system directory as written (/usr, or the merged-/usr
    /bin, /sbin, /lib, or /etc/alternatives) once "." and ".." are removed, and really resolve under
    /usr. So "/usr/../home/...", a relative name, an empty value, and a link in the home that points
    into /usr (its owner could point it elsewhere) are flagged; /usr/bin/pinentry through the
    alternatives link is not. The value is the whole rest of the line, quotes removed, as GnuPG reads
    it. It logs only when the result changes (daemons, profiles, or the finding), not every two
    minutes, and raises the flag once per new finding. Claws Mail and Kleopatra still share ~/.gnupg
    and the session's gpg-agent; nothing is masked, blocked or killed.
    (`tests/test_gnupg_check.sh`)
  - **The bubblewrap sandboxes could not start under their child profiles.** bubblewrap builds the
    sandbox in a private tmpfs, under /newroot (and creates /proc there) before its final pivot, and
    the child profiles allowed no writes there. Loupe's decoders, mat2's ffmpeg and exiftool, and the
    browser launchers' sandboxes (Tor Browser and LibreWolf from Claws Mail, Gajim or Pidgin) would
    have stopped at "mkdir". The children may now write only bubblewrap's own /newroot and /proc
    mount point.
  - Loupe may list / (glycin recreates the /lib64 and other lib links in the decoders' sandbox from
    it; without that no image opens), and its decoders may read the font caches.
  - mat2's "Remove metadata" for videos and other exiftool formats: ffmpeg or exiftool writes the
    "<name>.cleaned.<ext>" copy in the sandbox at the file folder's path; that one name may be
    written there now. The children still write nothing directly in the home or in a dot directory;
    Loupe's and Metadata Cleaner's write nothing in the home at all.
  - **Audacity would not start**: its single-instance check listens on a TCP socket on 127.0.0.1 and
    quits ("Audacity Startup Failure") when it can't. Its profile now allows IPv4 TCP sockets (not
    UDP, raw or IPv6), and PipeWire's socket for sound through ALSA. See Known security limits.
  - GIMP may read its system configuration (/etc/gimp: gimprc, unitrc, templaterc and the others)
    and start its Python plug-ins ("#!/usr/bin/env python3") and JavaScript ones (gjs-console).
  - Kleopatra may keep libkleo's settings (libkleopatrarc) and its window state
    (~/.local/state/kleopatrastaterc), start the GnuPG Log Viewer (kwatchgnupg), and its dirmngr may
    name its threads. Its self-test (gpgconf with every component, gpg, gpgsm, gpg-agent, scdaemon,
    keyboxd, dirmngr, the UI server, libkleopatrarc), key generation, signing, encryption, import and
    export were checked against the compiled profile, as was Claws Mail's GnuPG child on the same
    keyring and agent. The GnuPG configuration files stay read-only to Kleopatra.
    (`tests/test_apparmor_startup.sh`, `tests/aa_eval.py`: what each app needs to start and what must
    stay denied, on the compiled profiles)
- **Review of db6601c:**
  - Plain `passwd` is no longer setuid (hook 0500, checked), and confined apps may not run passwd,
    gpasswd, chsh, chfn, chage or expiry. Before, a program of the user could still choose the first
    session password with passwd, which asks a user with an empty password for no old one.
  - The bubblewrap children of Loupe, mat2 and Metadata Cleaner are no wider than their parents: no
    session /run (bus, gpg-agent, Wayland, I2P, Tor), only bubblewrap's own few /dev nodes (never a
    camera, sound or hardware-key node), only their own /proc entries, and the same secrets denies.
  - Kleopatra may no longer write the GnuPG configuration files (~/.gnupg/*.conf), which can name
    helper programs for a gpg-agent or dirmngr that systemd starts outside Kleopatra's profile. Its
    settings dialog can't change them.
  - prestium-safety-notify checks the 12 new profiles; clockfix raises a safety flag when it refuses a
    consensus time, and its bounds are tested on a run; ci.sh gives each score exemption its own
    ceiling and fails, as root, on a unit it can't score; the viewer test also checks for unconfined
    exec and for the child profiles' /run, /dev and /proc rules.
- **Review of d327e65:**
  - **The Lounge's `npm ci` failed on Debian 13's npm (9.2.0)** with "can only install with an existing
    package-lock.json", although the lockfile was there. The real error was npm 9's "Invalid comparator:
    github:kiwiirc/irc-framework#9578e59": the package.json override that pointed irc-framework at the
    local tarball made npm compare thelounge's git request as a version range. The working copy of the
    lockfile now has thelounge's request rewritten to the locked version (4.14.0, which the tarball
    entry satisfies) and no override at all; npm still runs with `--git=false`, never packs the git
    dependency, and the image still ships the committed package.json and lockfile. Checked with npm
    9.2.0 and npm 11 on the real lockfile (same files, irc-framework identical to the commit, no
    `dist/`); the test runs the offline install with both when npm 9.2.0 is available. New cache
    directory (`-r22`): the hidden lockfile in node_modules differs. (`scripts/npm-local-tarball.py`,
    `tests/test_irc_framework_tarball.sh`)
- **Review of 778baf7:**
  - **Hook 0460 no longer patches `site.py`.** Python 3.13 loads `site` as a frozen module, so that
    edit never ran and the hook failed the image build (`ENABLE_USER_SITE` stayed True). It now
    installs `/usr/local/lib/prestium/sitecustomize.py` as `sitecustomize` for every Python 3.x
    (`dpkg-divert` keeps Debian's apport hook and the file through upgrades). That sets
    `ENABLE_USER_SITE` to False, drops any user-site path already on `sys.path`, and stops
    `usercustomize.py`. Session processes also get `PYTHONNOUSERSITE=1` from `/etc/environment`,
    which stops a `.pth` in an already-existing user-site directory from running before
    sitecustomize; onion-grater allows that variable (it does not point the interpreter at other
    code). The hook fails the build if the disable does not take effect, including in the chroot
    where `/etc/environment` is not loaded. (`tests/test_python_usersite.sh`,
    `tests/test_onion_grater_tamper.py`)
- **Review of 6d14434:**
  - **Audacity can no longer reach the network**, not even the Tor and I2P proxy ports on 127.0.0.1.
    It runs in its own, empty network namespace (bubblewrap `--unshare-net --die-with-parent`), whose
    127.0.0.1 belongs to it alone: the single-instance check still listens there, so its AppArmor TCP
    rule reaches nothing else. Every way to start it goes through the namespace. Hook 0620 moves the
    real program to `/usr/libexec/prestium-audacity` (dpkg-divert; from there its RPATH still finds
    `/usr/lib/audacity`) and makes `/usr/bin/audacity` a shim for `/usr/local/bin/prestium-audacity`.
    So the menu (`prestium-run audacity`), a terminal and Debian's desktop file all reach the shim,
    and the AppArmor profile now attaches to the real program. The whole filesystem stays visible.
    PipeWire's and PulseAudio's sockets, `/dev/snd` (the microphone), the session bus, the Wayland
    socket and the file folders work as before. X11 works too: libxcb falls back from Xwayland's
    abstract socket to `/tmp/.X11-unix`. A second start joins the running Audacity's namespace and
    hands it the files, through a Unix socket in the session runtime directory that passes the
    namespace file descriptors (not `nsenter --target` of the first process, which Prestium's
    `ptrace_scope=2` would block). After joining, start is refused unless the namespace has only
    loopback, so a same-user replacement of that socket cannot put Audacity back on the host network.
    With no bubblewrap, no session runtime directory, or if the namespace can't be made, Audacity
    doesn't start, and a notification says why. (`tests/test_audacity_netns.sh`: the wrapper, the
    helper, the hook on a stand-in tree, the profile's attachment, and live isolation where
    bubblewrap works: no connection to a listener on the host's 127.0.0.1, a listener of its own,
    a second start that does not call nsenter, Unix sockets and X11 still connect, a host-network
    socket is refused)
- **Review of 772dfbf:**
  - **The Tor Connection Assistant and Nyx can use the control-port filter again.** onion-grater's
    AppArmor profile allowed a client's `/proc/<pid>/exe`, environment and maps, but not the
    script path `identify()` compares with `same_file` through `/proc/<pid>/root` (and not
    `/usr/bin/nyx` or `/usr/local/bin/prestium-tor-assistant` on the host). The check failed
    closed, so those two got `510 client not allowed` (the assistant showed
    `ConnectionError`; Nyx exited and the terminal closed). Tor Browser only stats
    `/proc/<pid>/exe` and `/opt/tor-browser/Browser/firefox.real`, which were already
    allowed, so it kept working. The profile now allows those script paths only, not the
    client's whole filesystem. The assistant's status line also shows the filter's reply,
    not only the exception class. (`tests/test_onion_grater_hardening.sh`)
- The i2pd web console already has a per-boot password (prestium-i2pd-port sets auth, user and pass
  every boot), which the audit (I-3) read from the commented template; nothing changed there.

### Known security limits (from the 2026-11-10 audits)
Not changed in 2.1, so you know where the edges are:
- **Unprivileged user namespaces are on**, because the browser sandboxes (bubblewrap) need them. They
  are a common route for kernel exploits; turning them off would mean a setuid bubblewrap instead.
- **X11 programs share one Xwayland server**, so an X11-only program can read the keyboard input and
  windows of the other X11 programs (not of Wayland apps such as the browsers).
- **The live system is not verified at boot** (no dm-verity, no signed root filesystem): someone who can
  write to the USB stick can change Prestium for the next boot. Secure Boot checks only the bootloader
  and kernel. dm-verity would need a hash tree in the image and a root hash in a signed boot chain; it is
  being evaluated for a later release.
- **The boot menu can be edited** (no GRUB password): anyone at the keyboard can change the kernel
  options, for example to boot without AppArmor. A password would not stop someone who can rewrite the
  stick.
- **Programs running as the desktop user can still attach a disk image** (udisks loop-setup), and the
  kernel then parses that image's filesystem. Debian's udisks allows this to the active user anyway, and
  polkit can't tell the unlock helpers from other programs with the same uid. The confined apps can't
  reach udisks at all, and rarely used filesystem drivers can't be loaded.
- **Most confined apps share ~/Downloads** (Claws Mail, Gajim, Pidgin, LibreWolf, the local Firefox,
  LibreOffice and the file viewers can write there), so a compromised one could change a file another
  app later opens. Separate folders per app would change where your files end up; not done in 2.1.
- **The i2pd console's per-boot password is readable by the desktop user's programs**
  (/run/prestium/i2pd-console.pass, root:user 0640), because the local-only Firefox's launcher runs
  as the user and needs it.
- **The bubblewrap children of Loupe, mat2 and Metadata Cleaner keep bubblewrap's mount rights**, so a
  compromised parent could present files at a path the child may write (rules are path-based). Device
  nodes stay protected, since their owner rules don't match root-owned nodes. Same class as the browser
  launchers' bubblewrap children.
- **GnuPG's socket-started daemons** (gpg-agent, dirmngr) may run outside Kleopatra's and Claws Mail's
  profiles; their configuration files are read-only to Kleopatra, their pinentry is confined, and
  prestium-gnupg-check flags a helper program from outside /usr.
- **Audacity keeps an IPv4 TCP rule**, which its single-instance check needs. Since the review of
  6d14434 the rule only works inside Audacity's own network namespace, which has nothing but its own
  loopback. Abstract Unix sockets of the desktop (such as Xwayland's) can't be reached from there
  either, so anything that depends on one won't work in Audacity, though X11 still connects through
  `/tmp/.X11-unix`. The real program in `/usr/libexec` can still be started by hand outside the
  namespace (its profile still applies). Two first starts at the same instant can still race. A
  booted ISO must still confirm that Audacity starts, records from the microphone, hands a second
  file to the running window, can't reach 127.0.0.1:9050 or the I2P proxies, and leaves a clean
  DENIED log.
- **AppArmor's D-Bus rules are not enforced on Debian 13's kernel** (6.12 has no D-Bus mediation), so
  the confined apps may still call any session-bus service. Should the image move to a kernel that
  enforces them, Kleopatra (which quits when it can't take its bus name) and the GTK apps that
  register theirs need bind rules first.
- **Tor's uid may reach any loopback port from 32768 to 60999**, which its pluggable transports need.
- **Programs of the desktop user may change NetworkManager's system connections** (to add Wi-Fi). The
  MAC guard and the firewall keep the real MAC address and real IP address from leaking that way.
- **The local-only Firefox's network rule follows a group** (prestium-localweb) that the desktop user's
  programs can also use; such a program may reach the same three local pages.

### Security review fixes
- **Expired and revoked publisher keys are refused.** gpg and gpgv report a good signature, and exit 0,
  when the key that made it has since expired. Every third-party signature (Tor Browser, Firefox,
  Feather, and now the Node.js releasers' keybox too) is checked line by line: an expired or revoked
  key, an expired signature, or a bad signature stops the build, each with its own message. The pinned
  fingerprints are unchanged (`scripts/sigcheck.sh`, `tests/test_sigcheck.sh`).
- **No unpinned build tools run for The Lounge.** npm used to pack irc-framework, a git dependency,
  by running its `prepare` script, which pulled babel and webpack from the registry at whatever version
  resolved that day and ran them on the build host. irc-framework is now installed from a `git archive`
  of the pinned commit with a pinned SHA-256; npm never sees the git URL (`--git=false`) and runs no
  scripts. The installed files, and every other The Lounge package, are the same as before. The
  file-by-file check against the commit stays, and the cache directory is new (`-r21`).
- **The local-only Firefox launcher no longer builds a command string.** The profile path (from
  `$HOME`) and the URL are no longer quoted into `sh -c`, so a home directory with a quote in its name
  can't change the command. They reach Firefox through the environment, because Debian's `sg` accepts
  only `sg GROUP -c CMD` and refuses further arguments; the `-c` string is a fixed literal. Same URL
  allow-list and flags (`tests/test_localfox_argv.sh` now uses an `sg` stub that refuses extra
  arguments the way the real one does).
- **The early firewall reports failure.** `prestium-firewall-early` (before ferm, and on ferm stop)
  used to skip a missing backend and always exit 0. It now checks every step, still applies as much
  drop-all as it can, reads the policies back, and exits non-zero if IPv4 or IPv6 isn't DROP with only
  loopback allowed. Both layers already used legacy xtables (this script calls `*-legacy` directly,
  and ferm 2.5.1 prefers the `-legacy` tools when they are installed); the iptables and ip6tables
  alternatives are now also pinned to legacy so plain `iptables` and any other tool see the same tables,
  and the build fails if the pin can't be set.
- **The AppArmor alert doesn't misfire.** The check that Prestium's profiles are in enforce mode
  used `[ -r ]` on `/sys/kernel/security/apparmor/profiles`, which is true for the live user even
  though only root may open the file, so every login could have raised ten false alerts. It now reads
  the list and skips the check when the read fails or is empty. The module and service checks are
  unchanged (`tests/test_safety_notify_apparmor.sh` adds unreadable, denied and empty lists).
- **The MAC guard keeps its egress filter current.** The nft rule that drops frames carrying a card's
  real address was installed once per interface name and never refreshed. It's now re-installed on
  every device event, including a changed permanent address and after a failed or flushed install, and
  a removed device is forgotten.
- **AppArmor health alert.** The safety notifier now warns on the desktop when the AppArmor module is
  off, when apparmor.service isn't active (not while it's still starting), or when one of Prestium's
  profiles isn't loaded in enforce mode.

### Fixes
- **Claws Mail can generate PGP keys.** "Generate a new key pair" failed with "General error": an
  account with no full name had an empty `name=` line, Claws reads that as an empty name rather than
  none and passes it to GnuPG, which refuses an empty name. Accounts are now written without the line,
  and the `claws-mail-i2p` launcher (menu entry and mail links) drops an empty one before each start,
  since Claws writes it back whenever the account is saved; Claws then names the key after the address.
  The AppArmor profile is unchanged. Generating a key, using a key imported outside Claws, signing and
  verifying were checked by hand in a Debian 13 VM with the profile enforced (no denials);
  `tests/test_claws_pgp_keygen.sh` covers the launcher and the GnuPG side, not Claws or AppArmor. The
  key choices on the account's Privacy page stay greyed out until a secret key exists, which is how
  Claws works. To use your own key, import it with Kleopatra; both use the same `~/.gnupg`.
- **Mail (I2P) asks for your account on first start.** Prestium used to ship a ready-made account
  with the placeholder address `username@mail.i2p`, which had to be found and edited in the account
  settings. Now, when there is no account yet, a short form asks for your name (optional) and your
  @mail.i2p address, and the launcher writes the account before Claws starts: POP3 on 127.0.0.1:7660
  and SMTP on 127.0.0.1:7659 through the i2pd tunnels to postman, SMTP login on, no TLS (the tunnel
  encrypts), no `X-Mailer` header, and `mail.i2p` instead of the hostname in the SMTP greeting and
  Message-ID. Claws asks for your postman password the first time it connects and keeps it in its
  password store; the launcher never handles it. Claws' own wizard isn't used because it can't set
  those privacy options, and an account it creates keeps Claws' defaults for the whole session, which
  without persistence is every session. The launcher also re-applies those three settings to any
  @mail.i2p account on each start (the address is matched case-insensitively). Cancelling the form
  leaves Mail closed. If the form can't be shown (zenity missing or failing; the error is logged),
  Claws' wizard opens with the same servers filled in (`accountrc.tmpl`, ports as `server:port`, which
  is the only form Claws reads there).
- **Kleopatra's self-test passes.** Kleopatra opened with "scdaemon Configuration Check: Failed" at
  every start: its check runs `gpgconf --list-options scdaemon`, and scdaemon (the smartcard daemon)
  wasn't installed: gpg-agent only suggests it, and apt never installs suggested packages. scdaemon is now installed (pcscd already was). "Compliance Check: Skipped" is normal: it
  only applies when GnuPG is set to de-vs compliance (`tests/test_kleopatra_selftest.sh`).

### New: Browser Updater
- **Network → Browser Updater** installs the latest **publisher-signed** Tor Browser or I2P Browser
  (LibreWolf) **in place** of the copy on the USB image. Each browser has **Update using Tor** (Tor's
  SOCKS port 9050 with remote DNS and a fresh SOCKS username per update, so the update gets its own
  circuits) and **Update using I2P OutProxy** (i2pd's HTTP proxy on 127.0.0.1:4444 and its configured
  outproxy, which can see the host names; the window says so). Only the transport that was clicked is
  used. Proxy variables from `/etc/environment` are dropped, and there's no fallback to the other
  transport. Downloads go only to `https://` on the publisher's own hosts (dist/aus1.torproject.org,
  repo.librewolf.net). curl never follows redirects itself: each `Location` is resolved and checked
  against those hosts first. Nothing is fetched when the window opens. Firefox (local pages) is not in
  this first release. Its recipe is in the library and the helper, but the window and sudoers don't
  offer it.
- **Verified twice.** The window checks the signature as the user. The scoped root helper
  `prestium-browser-install` (sudo, fixed `install|revert tor-browser|librewolf` only, no paths) then
  copies the staged files *as the user* into a root-only directory and verifies them again with the
  key shipped in the image (`/usr/share/prestium/keys/`, LibreWolf's `/usr/share/keyrings/librewolf.gpg`,
  each pinned by fingerprint) and `sigcheck.sh`, the same policy that checks the build.
  - **Tor Browser:** the tarball's detached signature, with the version from the signed file name
    matching `Browser/TorBrowser/Docs/ChangeLog.txt` inside it.
  - **LibreWolf:** the repository's signed `InRelease` (and its `Valid-Until`), then `Packages`, then
    the `.deb`'s SHA-256.
  - An expired key gives "key expired, use a newer ISO".
  - Nothing older than the installed version is installed. Equal means up to date, and **Reset to
    shipped copy** is the only way back.
- **Install = bind mount, Reset = umount.** The helper:
  - unpacks onto its own **tmpfs at `/run/prestium/browsers`** (`exec,nosuid,nodev`, sized for the
    update and checked against available RAM; `/run` itself is not used, since it's expected to be noexec; the VM `findmnt` check confirms that), with archive checks: no `..`, absolute
    paths, escaping symlinks, devices, fifos, hard links or setuid/setgid;
  - re-applies Prestium's policies and extensions from `/usr/share/prestium/opt-overlay`, which the
    image now keeps;
  - **bind-mounts** the new tree read-only (`ro,exec,nosuid,nodev`, checked in mountinfo) over
    `/opt/tor-browser`, or over `/usr/share/librewolf` (plus `/usr/lib/librewolf` when needed).
  Launchers, AppArmor exec paths and onion-grater were not changed: the paths stay the same.
  LibreWolf's `.deb` is **not** installed with `dpkg -i`. After an `apt-get -s --no-download`
  dependency check (only `librewolf` itself may be installed), it is unpacked with `dpkg-deb -x`. Its
  maintainer scripts never run, and its own AppArmor profile and `distribution/` are not used. The dpkg
  database and alternatives are untouched, so `dpkg -l` still shows the shipped version.
  - A failed re-update puts the previous update of this session back, never the factory copy. Any
    error during the bind rolls back. The rollback itself never raises, and it never binds on top of a
    new bind it couldn't remove. SIGTERM, SIGINT, SIGHUP and SIGQUIT are held from the first unmount
    until the new unit is bound and recorded, so a signal can't leave the factory copy showing or a
    read-write bind in place.
  - The helper sizes its tmpfs again from the real unpacked size once the archive or package listing
    is known, so a LibreWolf larger than the estimate doesn't fail with "Not enough space" while RAM
    is free.
  - If the update's record (the stamp) can't be written after the bind is up, the install reports
    success with a warning. Reset stays available whenever a helper bind is on the browser's path
    (read from mountinfo). A re-update is refused until Reset, because the shipped copy's details
    are then unknown. LibreWolf's shipped `/usr/lib/librewolf` and `/usr/bin/librewolf` types are
    recorded before the first bind and read from that record later.
  - The helper refuses while the browser is running (matched by device and inode) or while its files
    are busy.
  - Reset unmounts the update. After the last browser is reset, it also unmounts the tmpfs, which
    frees the RAM.
- **Session only.** Prestium has no persistence, so an update lasts until Reset or reboot and stays in
  RAM: about 360 MB for Tor Browser 16.0 unpacked. The window shows the RAM cost and refuses to start
  with less than 700 MB free for the download. It also uses the same RAM formula as the helper (the
  helper's tmpfs need plus 512 MB, at least 1 GB, plus the download, which is already in RAM when the
  helper runs): about 1.34 GB available for Tor Browser. For LibreWolf the window checks again with
  the signed index's real sizes before the package download. A newer browser may need
  AppArmor rules the shipped profile doesn't have, and the helper can't detect that. If an updated
  browser doesn't start, press Reset to shipped copy.
- Also: `torrc`'s 9050 SocksPort now says `IsolateSOCKSAuth` explicitly (it was already Tor's
  default). New tests: `tests/test_browser_update.py`, `tests/test_browser_install.py`,
  `tests/test_browser_updater_gui.py` and `tests/test_publisher_key_expiry.py` (fails when a pinned key
  expires within 90 days). The helper's bind, re-update, rollback and reset steps run against a real
  tmpfs and real bind mounts in an unprivileged user and mount namespace. That run used throw-away
  keys, the real Tor Browser 16.0 tarball (with the shipped key) and the real LibreWolf 157.0.1-1
  `.deb`.
  - **Not run:** a download through live Tor or I2P, the GTK window on a display (its logic is tested
    with a stand-in), and the bind-mount install and Reset on a Prestium live VM (overlay root, real
    /proc and AppArmor, `findmnt -o TARGET,OPTIONS,SIZE /run`, the bind's `exec` flag,
    `/proc/PID/attr/current` of the updated browser, mount(8)'s tmpfs remount as real root). Also:
    that the new bind on `/opt/tor-browser` shows inside onion-grater's own mount namespace
    (`ProtectSystem=strict`), since it matches Tor Browser by device and inode; and that the RAM is
    really freed after the last Reset (a copy of the mount in another namespace can keep the tmpfs
    alive). That VM check is still needed before release.
  - The Details log no longer shows the per-job SOCKS username. Close during the final signature
    check no longer starts the install. The tests and `build.sh` keep Python bytecode out of
    `config/includes.chroot`, and hook 9990 removes any `__pycache__` under `/usr/local`, so the root
    helper never reads a stale `.pyc`.

## 2.0: changes since Prestium 1.9.1.3

Prestium 2.0 is the base of PrestiumOS. Its goal was to fully modernize
the original 2023 Prestium build. It is rebuilt from scratch with Debian's live-build on Debian 13
"trixie" (see BUILDING.md), and it moves the desktop to Wayland with app sandboxing and stricter
failure handling.

This is one combined list of everything that changed since the last release, 1.9.1.3.

### Build system and supply chain
- **Built with live-build** from a configuration in git (package lists, Prestium's files, hooks)
  instead of upgrading and patching an unpacked root filesystem. Anyone can rebuild the ISO with
  `sudo ./build.sh`. `build.sh` runs the live-build stages itself, holds an exclusive build lock, and
  `--resume` cleans up leftover chroot mounts and duplicate apt sources.
- The legacy 1.9.1.3 trees (`rootfs/`, `iso/`, `build-1.9.1.3/`) are gone; the image is built only from
  this configuration.
- **Every third-party download** (Tor Browser, Firefox, Node.js, The Lounge, Feather, lurch, the I2P
  reseed file) is checked against its publisher's signature and a SHA-256 pinned in the repository.
  Downloads are HTTPS-only, redirects included, and the Debian mirrors use `https://`.
- i2pd, LibreWolf and Tor come from their own signed apt repositories. Each is `signed-by` its own key,
  and apt pins let each repository supply only its own packages, at build time and in the image.
- The Lounge is pinned exactly (4.5.2) and installed from a committed lockfile. Its git dependency,
  irc-framework, is checked file by file against the pinned commit on every build.
- Cached downloads and installs are re-checked before reuse. The I2P reseed file is cached and reused
  (default 24 hours) so rate limits don't break rebuilds, and every copy still passes signature and age checks.
- Fixed: 1.9.1.3 shipped the build machine's `/etc/resolv.conf`. 2.0 ships `nameserver 127.0.0.1`
  (no system DNS).

### Base system, hardware and audio
- Debian 13 trixie with updates and security fixes, kernel from the 6.12 line (Tails' line), firmware
  from trixie-backports (the Tails 7.15 set or newer) plus extra network, TV tuner, Qualcomm and Samsung firmware.
- Tor Browser 16.0, Firefox 159.0.1 (local pages only), Node.js 24.22.2, The Lounge 4.5.2, Feather 2.9.1,
  and current LibreWolf, i2pd and Tor. uBlock Origin 1.75.4 and NoScript 13.6.37.
- Secure Boot (shim + GRUB), BIOS boot and the hybrid ISO are kept.
- **PipeWire** with WirePlumber, pipewire-pulse and pipewire-alsa replaces plain ALSA (USB, HDMI and
  DisplayPort, SOF laptop DSPs, Surface devices). The panel volume control works with PipeWire.
- Galculator replaces SpeedCrunch, which is no longer in Debian 13.

### Wayland desktop
- **labwc** replaces Openbox (same menu and key bindings), **waybar** replaces tint2, swaylock and
  swayidle replace i3lock, mako handles notifications, grim and slurp take screenshots, wvkbd is the
  on-screen keyboard, foot is the terminal, and wdisplays replaces the X display settings.
- **Restricted socket for apps.** Apps get a Wayland socket on which the compositor hides screen capture,
  input injection, clipboard managers, the window list, overlays, the session lock and output control.
- **Wayland broker** (`prestium-wl-broker`). It makes the compositor's full socket root-owned so no app
  can reach it, and it starts the trusted desktop parts (panel, notifications, lock screen, screenshots,
  display settings, on-screen keyboard) with their own connections. labwc reads only a root-owned
  configuration, so no app can add key bindings or autostart commands.
- X11-only programs run through Xwayland and can't see or type into Wayland windows.
- Screenshots need a real click (Print) or drag (Alt+Print), so no app can take one unnoticed.
- Panel: a **Menu** button, icon-only window buttons (titles on hover), and an icon for the local-only
  Firefox. Browsers and dialogs get title bars with minimise, maximise and close.
- **Display:** resolution, arrangement and mirroring in Display Settings, monitor hotplug, and
  **Display Scale** (Auto or 100-200 %) applied by the compositor so every app follows at once.
- **Laptops:** working volume, mute, mic-mute and brightness keys with on-screen feedback, a Brightness
  slider, and touchpad settings (tap to click, natural scrolling, disable while typing).

### Network privacy
- **MAC address spoofing works reliably**, including after the kernel renames the network device. The
  `nomacspoof` boot option works again and has its own boot menu entry.
- **MAC address guard:** a connection set to the real or a fixed MAC address is reset to a spoofed one,
  a device about to use its real address is disconnected, and an egress filter drops frames sent with
  the real address. A safety alert appears if the guard isn't running.
- The firewall stays default-deny. Stopping or restarting it, including at shutdown, falls back to a
  drop-all (loopback only) instead of opening everything. DHCP lease renewal is allowed out.
- i2pd's per-boot port is opened inbound for IPv4 only, from the firewall config itself, so a reload
  no longer drops it. UPnP is off, the node is never a floodfill, and it still relays transit tunnels.
- polkit: the desktop user gets only the NetworkManager actions it needs (connect, Wi-Fi, save
  connections). Hotspot sharing, hostname and DNS changes need authentication.

### App confinement and sandboxes
- **Tor Browser and LibreWolf (I2P Browser) run in bubblewrap sandboxes:** an empty network namespace,
  only their own folders and `~/Downloads` from home, no D-Bus, no X11, Wayland only, and no_new_privs.
  Tor Browser can reach only Tor's SOCKS socket. LibreWolf can reach only i2pd's HTTP proxy.
- **Enforced AppArmor profiles** for LibreWolf (complain mode in 1.9.1.3), Tor Browser, Claws Mail,
  Gajim, Pidgin, OnionShare, Feather, LibreOffice (no network), The Lounge and the local-only Firefox.
  Confined apps can't use sudo, su, pkexec, Prestium's helpers, Tor's control socket or the system bus.
- onion-grater recognises apps by the file they really run, not by a path that could be faked.
- No swap ever, and internal NVMe disks are hidden like SATA disks.
- Yama `ptrace_scope=2`, so one program can't read another's memory or take its connections.

### Fail-closed behaviour
- Tor mode never reports success after a failed firewall reload. It rolls back, and if that fails, Tor
  stays stopped and the assistant says to restart before going online.
- Changing the i2pd port, tunnel hops or the reseed file rolls back completely on any failure, and
  the previous reseed data is kept until the new file has worked.
- **Safety notifier:** a persistent alert when the USB watchdog, MAC guard, Wayland broker, ptrace
  protection or shutdown memory wipe isn't working.
- Audit fixes: a local root escalation through the I2P Torrents helper is fixed, root helpers no longer
  follow symlinks in i2pd's or The Lounge's directories, the sudo helpers run Python isolated from the
  caller's directory, and OnionShare's onion services are limited to its own ports.

### Tor Connection Assistant (new)
- **Network → Tor Connection Assistant**: bootstrap progress, Reconnect, and modes **Direct, Snowflake,
  WebTunnel, obfs4 and meek** with Tor Browser 16.0's built-in bridges or your own.
- Snowflake and WebTunnel work without system DNS. Only the names they need are resolved with parallel
  DNS-over-HTTPS through the I2P outproxy. Tor's own traffic never goes through I2P.
- **Apply and connect** restarts Tor cleanly. **Cancel**, **Retry** and **Revert to previous** work at
  any point. The window stays inside the screen, and long errors scroll.
- Network menu: **Refresh I2P reseed (via Tor)** and **Manual reseed file**, both signature-checked.

### Apps
- **Feather is back on I2P** (i2pd's SOCKS proxy 127.0.0.1:4447), as in 1.7 and 1.8.
- **IRC (The Lounge)** no longer auto-connects before I2P is ready. It opens with a per-start login
  token, and it runs under its own AppArmor profile and hardened systemd unit.
- **I2P Torrents** has a dark Prestium theme.
- The local-only Firefox no longer shows Terms of Use and welcome pages at every boot.
- Fixed start-up failures of Claws Mail, Gajim and The Lounge under their AppArmor profiles.

### Known limitations
- Protected settings (Tor mode, tunnel hops, reseed, clock) work without a password for the desktop
  user. Confined apps can't use them, but unconfined programs can.
- Not every app path has been tested under AppArmor on real hardware, so a profile may still miss a rule
  an app needs.
- Open items from the final security review (signature key validity, irc-framework's build
  toolchain, early firewall self-checks, MAC guard rule refresh, an AppArmor health alert) are planned for 2.1.
