# Changelog

## 2.1: changes since Prestium 2.0

Prestium 2.1 is a security and features release on top of Prestium 2.0. It adds a Browser Updater, an
I2P Connection Assistant, Tor onion time sync on Kicksecure's design, a new desktop look, tighter
confinement and firewall rules, signed release files, and fixes for apps that broke or were too open
in 2.0. It is still built with live-build on Debian 13 "trixie".

This is one combined summary of everything that changed from 2.0 to 2.1, as the image now ships it.

### Build system and supply chain
- **Tor Browser is the newest signed release at every build.** `scripts/tb-latest.sh` asks the Tor
  Project's update service for the version, then downloads from dist.torproject.org. The tarball must
  be signed by the pinned Tor Browser key, no older than `TB_MIN_VERSION` (16.0.1), and must actually
  contain that release (`Browser/tbb_version.json`). A compromised server can't serve an older signed
  tarball under a newer name. To pin a release for a reproducible build, set `PRESTIUM_TB_VERSION` and
  `PRESTIUM_TB_SHA256`. torbrowser-launcher is not used.
- **Signature checks refuse expired and revoked publisher keys.** gpg can still exit 0 on those;
  every third-party signature (Tor Browser, Firefox, Feather, Node.js) is checked line by line, each
  in a throw-away keyring that holds only that publisher's key. A failed import stops the build
  (`scripts/sigcheck.sh`).
- **Node.js is pinned to 24.22.3** (11 November 2026 security release: high-severity HTTP/2 and TLS
  issues in 24.x). The Lounge's runtime is the official linux-x64 tarball in `/opt/nodejs`. The
  signature must come from one of the current releasers' primary keys (`NODE_KEYS` in
  `thirdparty/versions.sh`). The previous pin was 24.22.2.
- **The Lounge's `npm ci` works on Debian 13's npm (9.2.0).** A package.json override that pointed
  irc-framework at a local tarball made npm 9 treat the git request as a version range ("Invalid
  comparator"). The working copy of the lockfile now asks for the locked version and has no override;
  npm still runs with `--git=false`. irc-framework is installed from a `git archive` of the pinned
  commit with a pinned SHA-256, so npm never packs it or runs unpinned build tools on the host.
- **Python no longer loads the user's site-packages.** Hook 0460 used to patch `site.py`, which
  Python 3.13 loads frozen, so the hook failed the image build. It now installs a `sitecustomize`
  that turns the user site off, and sessions also get `PYTHONNOUSERSITE=1` so a `.pth` can't run
  first.
- **Release files.** `build.sh` writes `SHA256SUMS` (the ISO, its manifest and its package list) and
  `Prestium-2.1-amd64.manifest`: image SHA-256 and size, build date, source commit, Debian package
  count, and the Tor Browser, Firefox, Node.js, The Lounge, Feather, Tor, i2pd and LibreWolf versions
  that went in. `scripts/sign-release.sh FINGERPRINT`, run by the release key's holder, writes and
  checks a detached `SHA256SUMS.asc`. The ISO itself is not signed yet.
- **Repeatable builds (first step).** `PRESTIUM_SNAPSHOT=20261110T000000Z` builds Debian from
  snapshot.debian.org at that time, and `build.sh` sets `SOURCE_DATE_EPOCH` to the commit's time. The
  image is not yet bit-for-bit reproducible. The Tor, i2pd and LibreWolf repositories have no snapshots.
- `tests/ci.sh` (run by hand on Debian 13) runs shellcheck, compiles every AppArmor profile, scans for
  committed private keys and tokens, checks `systemd-analyze security` scores, and runs the tests that
  don't need a live Wayland session.

- **The live system is checked with dm-verity at boot.** The build makes a dm-verity hash tree for
  `live/filesystem.squashfs` (`auto/config --dm-verity`, `veritysetup` on the build host) and puts its
  root hash on the kernel command line of every GRUB and isolinux entry (hook 9010, which also checks the
  tree once with `veritysetup verify`). The initramfs refuses to boot when the hash tree is missing, the
  command line has no well-formed root hash for the image, an extra or non-squashfs image or "plain
  root" mode turns up, or dm-verity can't be set up (hook 0405 patches live-boot, which otherwise falls
  back to a plain mount or to a root hash file on the same stick). A changed block of the image is an
  I/O error at mount time (the boot stops) or a kernel panic later (`dm-verity-oncorruption=panic`). The
  root hash is in the release files (`Prestium-2.1-amd64.roothash`, the manifest, `SHA256SUMS`), so
  a signed release signs it too. The kernel, initramfs and boot menu are not covered (see Known security limits).

- **Locked boot menus.** Nobody at the keyboard can edit a boot entry or open GRUB's command line, so
  nobody can boot with AppArmor off or with `init=`. GRUB (UEFI) has a superuser with a PBKDF2 password
  hash, and every boot entry is `--unrestricted`, so booting needs no password; only "UEFI Firmware
  Settings" asks for it. isolinux (BIOS) takes no added options (`allowoptions 0`, `noescape 1`). The
  hash comes from `PRESTIUM_GRUB_PASSWORD_HASH` or the gitignored `grub-password.pbkdf2`
  (`scripts/grub-pbkdf2.py` makes it). Without one, the build locks the menu with the hash of a random
  password nobody knows and prints a warning. Hook 9020 also stops the build if any entry passes
  `apparmor=` other than 1, `security=` other than apparmor, `lsm=`, `init=` or `break=`.

### Base system
- **Tor Browser 16.0.1** (or newer, as above) with Firefox security fixes and tor 0.4.9.16.
  **System Tor 0.4.9.16** comes from deb.torproject.org at build time. LibreWolf and the local Firefox
  still come from their apt repositories at build time.
- **The desktop says when the image is old.** Prestium does not update itself during a session. Five
  minutes after login, a notice says how many days old the image is once it is past 45 days.
  `/etc/os-release` has the build date as `BUILD_ID`, and `/usr/share/prestium/build-date` records the
  build time used as the lower bound for setting the clock.

### New: Browser Updater
- **Network → Browser Updater** installs the latest **publisher-signed** Tor Browser or I2P Browser
  (LibreWolf) **in place** of the copy on the USB image, for this session only. Each browser has
  **Update using Tor** (Tor's SOCKS port 9050, remote DNS, a fresh SOCKS username so the update gets
  its own circuits) and **Update using I2P OutProxy** (i2pd's HTTP proxy on 127.0.0.1:4444; the
  outproxy can see the host names, and the window says so). Only the transport that was clicked is
  used. Downloads go only to `https://` on the publisher's own hosts; curl never follows redirects
  itself. Nothing is fetched when the window opens. The local-only Firefox is not offered in this
  release.
- **Verified twice:** the window checks the signature as the user; the root helper
  `prestium-browser-install` copies the staged files as the user into a root-only directory and
  verifies them again with the keys shipped in the image, using the same policy as the build. Tor
  Browser: the tarball's detached signature, and the version in the file name must match the changelog
  inside it. LibreWolf: the repository's signed `InRelease`, then `Packages`, then the `.deb`'s
  SHA-256. An expired key gives "key expired, use a newer ISO". Nothing older than the installed
  version is installed. **Reset to shipped copy** is the only way back.
- **Install is a bind mount, Reset is an unmount.** The update is unpacked on a tmpfs at
  `/run/prestium/browsers` and bind-mounted read-only over the shipped path, so launchers and AppArmor
  paths stay the same. LibreWolf's `.deb` is unpacked with `dpkg-deb -x`; its maintainer scripts never
  run. A failed re-update puts the previous update of this session back. The helper refuses while the
  browser is running. Prestium has no persistence, so an update lasts until Reset or reboot and stays
  in RAM. The window shows the RAM cost and refuses to start without enough free memory. If an updated
  browser doesn't start (for example because it needs AppArmor rules the shipped profile doesn't have),
  press Reset to shipped copy.

### App confinement and sandboxes
- **Each confined app has its own download or output folder, and writes files nowhere else (L-5).** A
  compromised app can no longer change a file another app wrote or will open. Network apps save in
  `~/Downloads/<App>`: I2P Browser, Local Firefox, Mail (Claws attachments), Gajim and Pidgin (Tor
  Browser keeps `~/Tor Browser`, I2P Torrents `~/Downloads/Torrents`). Editors save in
  `~/Documents/<App>`: LibreOffice, GIMP, FeatherPad, File Roller, Xarchiver, Audacity, Kleopatra and
  Metadata Cleaner (which cleans files in place, so copy a file there first). mat2 ("Remove metadata")
  writes only its `name.cleaned.ext` copy next to the original. Viewers and editors still open files from
  every folder, but read-only. A document opened elsewhere opens read-only in LibreOffice; use Save As.
  The browsers see only their own folder, so to upload a file, put it there first, as with Tor Browser.
  Mail and chat can also read files you put directly in `~/Downloads`, for attachments, but not another
  app's folder. Unlocked volumes under `/media` stay writable for the editors. Hook 0500 creates the
  folders, the apps' settings point at them, and the file chooser has bookmarks for the download folders.
- **The file manager makes no thumbnails and mounts no drives by itself.** PCManFM isn't confined, so it no
  longer decodes downloaded pictures for previews (`/etc/xdg/libfm/libfm.conf`). USB drives are mounted with
  a click, not on insert or at start-up.
- **The file viewers, editors, KeePassXC and Kleopatra have no sound or microphone access.** VLC, Audacity,
  the browsers and the chat and mail apps keep it.
- **Programs that open downloaded files are confined:** Loupe, Ristretto, VLC, File Roller, Xarchiver,
  FeatherPad, mat2, Metadata Cleaner, GIMP and Audacity run under enforced AppArmor profiles (no
  network, no camera, no admin tools, no other app's mail/chat/browser data, no OpenPGP keys or
  KeePassXC databases). They may read the file folders (Desktop, Documents, Downloads and the others),
  save only in their own folder (see above) and use their own settings. Files outside those folders need to be moved into Documents first. VLC plays
  local files only (no network streams). Loupe's image decoders and mat2's helpers keep their own
  bubblewrap sandbox, in a child profile with the same limits.
- **KeePassXC and Kleopatra are confined too.** KeePassXC has no network and no browser integration.
  Kleopatra and the GnuPG tools it starts may use `~/.gnupg`, read the file folders and save in `~/Documents/Kleopatra`; only dirmngr opens
  TCP (through Tor), and passphrase prompts use a confined pinentry. Kleopatra may not write the GnuPG
  configuration files (those can name helper programs). The pinentry profile also applies when the
  session's own gpg-agent starts a prompt.
- **Browsers opened from mail and chat stay confined.** Claws Mail, Gajim and Pidgin used to start the
  Tor Browser and I2P Browser launchers unconfined, and the launchers honoured the caller's
  environment. They now enter dedicated launcher profiles, take a fixed PATH and fixed paths only, and
  run as `bash -p`. Of the home directory, the sandbox child may write only its own browser's folders.
- **The first session password can only be set from the lock dialog.** The Wayland broker shows that
  dialog on the compositor's full socket and sets the password as root. `sudo prestium-session-password`
  no longer allows `set`, and plain `passwd` is no longer setuid. The password must have at least 8
  characters; each wrong attempt at the lock screen costs at least 4 seconds. There is no lockout.
- **onion-grater can only read, not trace**, and it checks how a Python client was started. Its unit
  filters out ptrace and process_vm syscalls; a new AppArmor profile allows `ptrace (read)` only. A
  client started with `PYTHON*` (other than a short allow-list), `LD_*` or code from outside `/usr`
  and `/lib` is refused (libffi's own `/memfd:libffi` trampolines excepted). The profile allows
  `identify()` to stat only the Nyx, Tor Connection Assistant and OnionShare script paths (through
  `/proc/<pid>/root` and on the host). The filter also holds `CAP_DAC_READ_SEARCH`, read-only, because
  a client's `/proc/<pid>/environ` is readable by its owner only; its unit hides the shadow files,
  sudoers, `/etc/ssh` and `/var/lib` from it. Every refusal is logged with its reason
  (`journalctl -u prestium-onion-grater`).
- **The Lounge can't rewrite its own code.** `config.js` and its packages are root-owned and read-only
  for The Lounge. The sign-in token works once and never appears in a command line: it is handed to
  the local-only Firefox through a one-off page in a private folder, which is the only `file://`
  exception in Firefox's policy.
- **Audacity can no longer reach the network**, not even the Tor and I2P proxy ports on 127.0.0.1. It
  runs in its own empty network namespace. Its single-instance check still listens on that private
  loopback, the microphone still works, and a second start joins the first namespace through a session
  socket (no ptrace, which `ptrace_scope=2` would block). After joining, start is refused unless the
  namespace has only loopback. Audacity may start its own plug-in host (the same program, same
  profile, same namespace), so the Measure RMS plug-in (`rms.ny`) is no longer reported incompatible.
- **prestium-gnupg-check** (a root timer) raises a safety flag when an unconfined GnuPG daemon is
  running and that user's configuration names a helper outside `/usr`. Claws Mail and Kleopatra still
  share `~/.gnupg` and the session's gpg-agent; nothing is masked or killed.
- **Root daemons ignore their test overrides when installed.** The Wayland broker, prestium-wl-config
  and the MAC guard read `PRESTIUM_*` variables only when run from the source tree.

### Network, firewall and privileges
- **Time over Tor onion services, on Kicksecure's design.** `prestium-timesync` is now a daemon built on
  sdwdate's design (written for Prestium, not Kicksecure's code). Each round it asks one source from each
  of three pools of onion web servers run by unrelated operators (Kicksecure's own list, kept under its
  AGPL-3+ licence in `/usr/share/prestium/timesync/pools.conf`), each on its own Tor circuit as the
  firewalled `prestium-htp` user, and uses the median. A pool with more than a third of its members
  failing aborts the round. An answer outside the current Tor consensus window is rejected. The clock is
  never set earlier than the build date, the last time it set this boot, or `/etc/minimum-unixtime`
  (time replay protection). Up to one second of random nanoseconds is added. The first sync, and any
  later difference over 10 seconds, steps the clock; smaller ones are slewed smoothly by the kernel. It re-syncs at random
  60 to 180 minute intervals instead of once per boot.
- **Boot clock randomization.** `prestium-bootclock.service` moves the clock a random 0 to 50 seconds
  into the past or future (inside the 60 s i2pd allows between peers), with random nanoseconds, before Tor, i2pd and the time sync start.
- **Clock-sync symbol in the bar.** An amber clock symbol shows until the time is set over Tor, and a red
  one if the sync refused a time it could not trust. It disappears once the clock is synced. The
  previous one-shot sync from clearnet HTTPS sites is gone.
- **The control-port filter checks Python clients more strictly.** Nyx, OnionShare and the Tor Connection
  Assistant must start with `PYTHONNOUSERSITE=1` (`prestium-run` and `prestium-nyx` set it), because Python
  runs `.pth` files from the user's site-packages before `sitecustomize` can switch them off. The filter's
  service won't start without its AppArmor profile.
- **The Wayland broker's socket is open to group `user` only** (0660, was 0666).
- **i2pd and Tor can no longer reach Prestium's local services.** Their firewall accepts are for the
  network only. On loopback, i2pd keeps only its SOCKS outproxy tunnel (4500) and Tor only the kernel's
  ephemeral ports 32768-60999, where its pluggable transports listen, and OnionShare's web server
  (127.0.0.1:17600-17650), which its onion services forward to.
- **The early firewall reports failure.** `prestium-firewall-early` checks every step, applies as much
  drop-all as it can, and exits non-zero if IPv4 or IPv6 isn't DROP with only loopback allowed.
  iptables and ip6tables are pinned to the legacy xtables backend, and the build fails if that pin
  can't be set.
- **The MAC guard keeps its egress filter current**, re-installing the rule that drops frames with a
  card's real address on every device event.
- **The Wayland broker and the MAC guard keep only the root powers they use.** The time sync, bootclock,
  clockfix and the USB watchdog run in a systemd sandbox. The VM network check runs as its own user, not as root,
  and never copies Tor's log text.
- **Setting the clock has bounds.** `sudo date -s` is replaced by `sudo prestium-set-clock`. timesync,
  clockfix and set-clock all refuse a time before the image was built (one day of slack) or more than
  10 years after it. timesync raises a safety flag when it refuses, or when it moves the clock by more
  than a day.
- **Fewer filesystem drivers can be loaded.** 21 rarely used ones (hfs, minix, jfs, reiserfs and
  others) are blocked. FAT, exFAT, NTFS, ext4, Btrfs, XFS, F2FS, ISO 9660, UDF and HFS+ still work.
  udisks still lets the desktop user attach disk images (needed for VeraCrypt file containers).

### Safety and virtual machines
- **AppArmor health alert.** The safety notifier warns when the AppArmor module is off, when
  apparmor.service isn't active, or when one of Prestium's profiles isn't in enforce mode. A bug that
  could raise ten false alerts at every login (the profiles file looks readable to the user but only
  root may open it) is fixed.
- **Prestium tells you when it runs in a virtual machine**, the way Tails does: a notification at
  login says the host and the virtualization software can see and record everything done in Prestium.
- **If Tor or I2P hasn't connected in a VM after 10 minutes, the desktop says why** (no route,
  user-mode networking, a VM clock set to local time, or a host firewall blocking I2P). The diagnosis
  is read-only and disappears once both connect.

### Desktop
- **A new Prestium look.** One palette everywhere: dark grey surfaces, an Electric Blue `#0066ff` accent
  and Neon Cyan `#00ffff` highlights (the colours of The Lounge's Tech Innovation theme), with Cantarell
  as the UI font. GTK 3 and 4 (libadwaita) apps are dark (prefer-dark, dconf `accent-color='blue'`) and
  take the palette from a colour-only `gtk.css`; GTK 2 (Pidgin) uses Adwaita-dark. Qt 5 and 6 apps use
  Kvantum with a "Prestium" theme (`QT_STYLE_OVERRIDE=kvantum`; adwaita-qt is gone). KDE apps use a
  `Prestium` colour scheme, and Kleopatra picks it by default (`/etc/xdg/kleopatrarc`) instead of
  Breeze Dark. Audacity, KeePassXC and the foot terminal (11 pt, readable red, blue, magenta and grey)
  are dark too. Tor Browser keeps its own fonts. The build fails if the system dconf database isn't
  compiled.
- **Windows.** The labwc theme uses the same palette, with 8 px rounded corners and drop shadows. Every
  window gets one labwc title bar; GTK and libadwaita apps no longer draw a second close button
  (`button-layout ':'`). There is one desktop. Minimize and Maximize have icons in the window menu.
- **Papirus-Dark icons.** The Prestium icon theme holds the new logo mark (a blue-to-cyan "P.") and
  inherits Papirus-Dark first; Adwaita, AdwaitaLegacy and gnome are fallbacks. Menus, notifications and
  the bar use it.
- **A floating bar.** waybar floats with rounded corners and margins and uses Font Awesome symbols. Its
  status area is icons only (network, volume capped at 100 %, battery) with a two-line clock: time over
  date, in UTC, no tooltip. Tor and I2P pills show connecting (amber), ready (cyan) or failed (red), and
  a click opens the matching Connection Assistant. With no network
  connection the Tor pill goes back to amber instead of staying ready. The state comes from `prestium-netstatus.service`
  (its own user, read-only, writes only `/run/prestium/netstatus`, never copies log text). A clock symbol
  shows until the time is set over Tor (see Network). Hover colours fade in; labwc and mako have no open
  or close animations.
- **The menu opens in one place, grouped by task.** The Menu button and Super+Space open it at the
  bottom-left, its bottom edge on the bar; right-clicking the desktop opens it at the pointer. The top
  level has I2P Browser, Tor Browser, I2P Router Console, Text Editor and File Manager, then Office,
  Multimedia, Accessories, Security (KeePassXC, Kleopatra, Metadata Cleaner, Unlock Encrypted Volume,
  Feather), Communication, Sharing (OnionShare, Torrents), Network and System, then Log Out…, Restart…
  and Shut Down…. Networked apps name their network ("Gajim (XMPP, Tor)", "IRC (I2P)", "IRC (Tor)",
  "Claws Mail (Email, I2P)"). Every entry has an icon Debian ships, and wording, ellipses and title case
  are the same everywhere.
- **Notifications.** One look per urgency (low: grey edge, 5 s; normal: blue edge, 8 s; critical: red
  edge, stays and always shows), with app icons drawn at no more than 32 px so small ones stay sharp; only identical repeats are grouped. The volume and
  brightness display is compact, at the top centre. Optional quiet sounds, off by default (System,
  Notification Sounds (On/Off)). The VM, image-age and safety notices are no longer held up at login.
- **Wallpapers and lock screen.** Three Prestium wallpapers (Horizon, Circuit, Mark) are picked in
  System, Wallpaper; the broker takes only one of those names, never a path. The lock screen uses the
  palette and shows Caps Lock and keypresses on its ring.
- **Keys and dialogs.** Alt+arrows go to the browsers (Back/Forward), not labwc; Super+Return opens the
  terminal. Log Out asks first; Restart and Shut Down have named buttons, and Restart… in the I2P
  Connection Assistant uses the same confirmation. Long dialog texts wrap on small screens, file names
  are shown as text, and the Prestium tools have keyboard shortcuts and a highlighted default button.
  PCManFM makes no thumbnails (`[ui] show_thumbnail=0`). Boot menu labels take the version from the
  image.
- **Broker dialogs can't be answered by other programs.** The I2P settings confirmation and the
  lock-screen password form run on the compositor's full socket with accessibility off (`GTK_A11Y=none`,
  `NO_AT_BRIDGE=1`), and so do waybar and wdisplays, so other programs can't press their buttons or fill
  in the password. They use the Prestium colours from a root-owned directory. A dialog that times out
  closes. The I2P dialog names the program that asked; that line is self-reported, normalised (NFC),
  stripped of control and invisible characters, length-limited, and shows up to three quoted arguments.
- **Locking.** lxpolkit is no longer started (no prompt in Prestium used it), so the password dialog
  says only that it unlocks the screen. When the screen is due to lock automatically and no password
  is set, a notification says it is not locked instead of opening a dialog nobody sees. Lock Screen
  from the menu still asks for a password first.
- **Private OnionShare addresses open in Tor Browser.** Tor Browser's Tor socket has `ExtendedErrors`,
  so Tor Browser asks for the private key instead of failing with "Unable to connect". onion-grater
  drops `Flags=Permanent`, so "Remember this key" keeps the key until Tor restarts or Prestium shuts
  down; nothing is written to disk. The key prompt's arguments are checked before they reach Tor.
- **I2P settings need confirmation.** Apply in the I2P Connection Assistant goes through the Wayland
  broker, which shows the change in a dialog only the person at the screen can answer, then logs it and
  sends a notification. sudo allows only reading the settings. The helper checks that the restarted
  listener on 4444 belongs to i2pd and reports a failed rollback.
- The image-age notice mentions the Browser Updater. The README says command-line tools use the I2P
  outproxy (`http_proxy`), not Tor. The reseed and torrent messages point to steps that exist.

### Apps
- **New: IRC (Tor)**, a second The Lounge (Communication menu, next to *IRC (I2P)*, which was "The Lounge
  (IRC, I2P)"). It reaches IRC only through Tor: its own system user `thelounge-tor`, state directory
  `/var/lib/thelounge-tor`, root-owned read-only `config.js`, web UI on 127.0.0.1:9010, systemd unit
  `thelounge-tor.service` with the same sandbox, and AppArmor profile `thelounge-tor`. It shares
  `/opt/thelounge`, Node.js, the one-use sign-in token, the local-only Firefox and the 10 themes (Tech
  Innovation by default) with the I2P instance, and neither can read the other's files. The firewall
  lets `thelounge-tor` reach only Tor's SOCKS port 127.0.0.1:9050: no clearnet, no DNS, no other local
  service. Every network goes through that port (hook 0200 forces it, whatever a network's proxy
  setting says), the server name is resolved by Tor, never locally, and each network has its own
  random SOCKS username, so its own Tor circuits. Networks start disconnected with a random nick each,
  as on I2P. Presets, all onion services: OFTC (default, no registration), Libera.Chat, hackint,
  AlphaChat and Pirate IRC (through `MapAddress` lines in torrc, so their TLS certificates check
  out), Ergo, DarkScience and IRCNow (plain IRC on the onion, which already encrypts). OFTC's onion
  takes TLS but its certificate is for irc.oftc.net, so certificate checking is off for that one only.
  Libera.Chat over Tor needs SASL EXTERNAL (client certificate) or ECDSA-NIST256P-CHALLENGE, not a
  password, and the account and certificate must be set up beforehand over a normal connection;
  AlphaChat needs SASL with a verified account, and Pirate IRC likely SASL too.
- **New: I2P Connection Assistant** (Network menu). One window shows i2pd's port, which is random and new
  at every start, and sets:
  - tunnel hops, 1 to 7 (default 3);
  - share level: Low 30 % at 32 KB/s (default), Medium 50 % at 64 KB/s, High 80 % at 128 KB/s;
  - outproxy: Acetone (default), StormyCloud, or a custom I2P address.
  StormyCloud also takes the SOCKS outproxy. A custom outproxy is HTTP only, so SOCKS stays on Acetone.
  Local port 4500 never changes. *Apply* writes the settings through a root helper
  (`prestium-i2p-mode`: sudo, a checked JSON request, no free-form arguments) and restarts i2pd.
  If the browser proxy doesn't come back, the old settings are put back. Reseed (over Tor, or from a
  file) and *Reboot* are in the same window. The old *I2P Tunnel Hops*, *Restart I2P* and reseed menu
  items are gone. `prestium-tunnel-hops` still works from a terminal.
  The window fits the screen: on small screens its content scrolls, and it can be resized.
- **Tor Browser reconnects after Tor restarts.** Changing the method in the Tor Connection Assistant
  restarts Tor, which makes a new SOCKS socket. The browser's sandbox had bound the old socket file,
  so Tor Browser never reached Tor again until it was restarted. The sandbox now binds the socket
  directories read-only (`/run/prestium-tbb`, `/run/onion-grater`), and onion-grater keeps its
  directory across restarts.
- **Apps no longer crash the session in a VM.** In a virtual machine, apps that hand the compositor
  GPU buffers (VLC, the QtQR webcam view and others) crashed labwc, which dropped back to the login
  screen. On real hardware, as on a USB stick, this didn't happen. (This replaces an earlier
  workaround that ran VLC and QtQR through Xwayland; they are native Wayland apps again.) In a VM the session now uses
  wlroots' software renderer (`WLR_RENDERER=pixman`, no hardware cursor). Apps then send plain
  shared-memory buffers. Nothing changes on real hardware.
- **The Lounge ships the 10 Theme Factory themes, and Tech Innovation is the default.** Ocean Depths,
  Sunset Boulevard, Forest Canopy, Modern Minimalist, Golden Hour, Arctic Frost, Desert Rose, Tech
  Innovation, Botanical Garden and Midnight Galaxy are local packages. The old Prestium theme is
  removed; The Lounge's own themes can still be picked in Settings. Every theme sets the colour and
  background of text fields and of chat text explicitly, at least 4.5:1 contrast (WCAG AA). Nothing
  is loaded from outside; Theme Factory's fonts map to ones Prestium ships. The sign-in splash uses
  Tech Innovation's colours. Palettes: Theme Factory (github.com/anthropics/skills, commit
  `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`), Apache License 2.0.
- **The Lounge waits 320 seconds for an IRC ping reply**, so connections over I2P (IRC2P and Ilita)
  are less likely to drop with "Ping timeout". irc-framework's default is 120 seconds. Hook 0200 sets
  `ping_timeout: 320` where The Lounge creates the client; `ping_interval` stays 30 seconds. If a later
  Lounge version changes that code, the build stops.
- **The Lounge no longer says it is connecting when it is not.** On boot the lobby still printed
  "Network created, connecting to 127.0.0.1:6668..." even though Prestium leaves networks
  disconnected. That line now appears only when a connection actually starts; `/connect` and the
  Connect menu show "Connecting to 127.0.0.1:6668...".
- **Mail (I2P) asks for your account on first start**, instead of shipping a placeholder
  `username@mail.i2p` account. Claws Mail can generate a PGP key again (an empty name line had made
  GnuPG refuse). To use your own key, import it with Kleopatra; both use the same `~/.gnupg`.
- **Kleopatra's self-test passes.** scdaemon is now installed, so the "scdaemon Configuration Check"
  no longer fails at every start.
- **The Tor Connection Assistant and Nyx can use the control-port filter again.** onion-grater had
  refused them (`ConnectionError`, then `510 ... client not allowed` or `Broken pipe`, and Nyx's
  terminal just closed): a missing AppArmor rule, then no permission to read their environment as
  another user, and for the assistant the libffi memory GTK callbacks use. The assistant says when the
  filter refused it and where to look; Nyx's window stays open when Nyx fails (`prestium-nyx`).
- **The local-only Firefox launcher no longer builds a command string**, so a home directory with a
  quote in its name can't change the command.

### Known security limits
Not changed in 2.1, so you know where the edges are:
- **Unprivileged user namespaces are on**, because the browser sandboxes (bubblewrap) need them.
  Turning them off would mean a setuid bubblewrap instead.
- **X11 programs share one Xwayland server**, so an X11-only program can read the keyboard input and
  windows of the other X11 programs (not of Wayland apps such as the browsers).
- **dm-verity covers the root filesystem image only.** Secure Boot checks the bootloader (shim, GRUB)
  and the kernel, but not the initramfs or the boot menu (`grub.cfg`, `isolinux/live.cfg`), and those
  hold the check and the expected root hash. So someone who can write to the USB stick can still change
  the next boot by replacing the initramfs or the boot menu together with the image. What dm-verity
  does stop: a changed or swapped `filesystem.squashfs` on its own, an extra image or a missing hash
  tree, and blocks of the image that change after the boot check (a faulty or malicious stick). To
  check a stick against a signed release, compare it from another computer with `SHA256SUMS`
  (`Prestium-2.1-amd64.roothash` is the hash the boot menu must carry). Closing the gap needs a signed
  unified kernel image (kernel, initramfs and command line in one Secure Boot-signed file), which
  Debian's shim and GRUB don't offer for a live image yet. The hash tree's salt is random, so two
  builds of the same commit have different root hashes.
- **The boot menu lock is only as strong as the USB stick.** It stops changes made at the keyboard,
  not someone who can write `grub.cfg` on the stick (see dm-verity above). The password hash is on the
  stick, so a chosen password needs to be long; the default random one can't be guessed. Firmware
  boot menus and other boot media are outside Prestium's control; a firmware password helps there.
- **Programs running as the desktop user can still attach a disk image** (udisks loop-setup). The
  confined apps can't reach udisks, and rarely used filesystem drivers can't be loaded.
- **Per-app folders limit writes, not reads.** A compromised viewer or editor can still read every
  file folder (it has no network, so it would need another app to send anything out), and mail and
  chat can read the files you put directly in `~/Downloads`. The file manager and other unconfined
  programs of the desktop user can still write everywhere. Unlocked volumes under `/media` are shared
  by the editors.
- **The i2pd console's per-boot password is readable by the desktop user's programs**, because the
  local-only Firefox's launcher runs as the user and needs it.
- **The bubblewrap children of Loupe, mat2 and Metadata Cleaner keep bubblewrap's mount rights**, so a
  compromised parent could present files at a path the child may write (rules are path-based).
- **GnuPG's socket-started daemons** may run outside Kleopatra's and Claws Mail's profiles; their
  configuration files are read-only to Kleopatra, their pinentry is confined, and prestium-gnupg-check
  flags a helper program from outside `/usr`.
- **Audacity keeps an IPv4 TCP rule**, which its single-instance check needs. The rule only works
  inside Audacity's own network namespace. Abstract Unix sockets of the desktop (such as Xwayland's)
  can't be reached from there; X11 still connects through `/tmp/.X11-unix`. The real program in
  `/usr/libexec` can still be started by hand outside the namespace. Two first starts at the same
  instant can still race.
- **AppArmor's D-Bus rules are not enforced on Debian 13's kernel** (6.12 has no D-Bus mediation).
- **Tor's uid may reach any loopback port from 32768 to 60999**, which its pluggable transports need. It may also reach
  127.0.0.1:17600-17650, where OnionShare's web server listens for its onion services.
- **Programs of the desktop user may change NetworkManager's system connections** (to add Wi-Fi). The
  MAC guard and the firewall keep the real MAC address and real IP address from leaking that way.
- **The local-only Firefox's network rule follows a group** (`prestium-localweb`) that the desktop
  user's programs can also use.

A booted 2.1 ISO should still be used to confirm: Audacity (start, microphone, second-file handoff, no
reach to Tor or I2P proxies); the Tor Connection Assistant and Nyx through onion-grater, including
NEWNYM and the circuit display; Browser Updater on the live overlay (download through Tor or I2P,
bind-mount install and Reset, onion-grater's mount namespace, RAM freed after the last Reset); bridges
after the tighter loopback firewall rules; the onion time sync and boot clock randomization; and the
new look (Kvantum, libadwaita accent, Kleopatra's colours, the bar's pills and Papirus-Dark tray icons).

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
