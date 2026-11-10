# Changelog

## 2.1 (in progress)

Enhanced security and new features. Changes will be listed here as they land.

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
    update and checked against available RAM; `/run` itself is noexec and is not used), with archive checks: no `..`, absolute
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
  - A failed re-update puts the previous update of this session back, never the factory copy.
  - The helper refuses while the browser is running (matched by device and inode) or while its files
    are busy.
  - Reset unmounts the update. After the last browser is reset, it also unmounts the tmpfs, which
    frees the RAM.
- **Session only.** Prestium has no persistence, so an update lasts until Reset or reboot and stays in
  RAM: about 356 MB for Tor Browser 16.0 unpacked. The window shows the RAM cost and refuses to start
  with less than 700 MB free for the download or under 1 GB of available RAM. A newer browser may need
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
    `/proc/PID/attr/current` of the updated browser). That VM check is still needed before release.

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
