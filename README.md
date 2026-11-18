Disclaimer: This project and all associated materials (including software, repositories, scripts, and ISO files) are provided strictly "as is" and "as available," for informational, educational, and experimental purposes only, without any express or implied warranties of any kind—including, but not limited to, fitness for a particular purpose, security, accuracy, or non-infringement. The creator and publisher make no claims regarding the safety, integrity, or audit status of any code or binaries, explicitly disclaim any expertise or maintenance obligations, and shall not be held liable for any direct, indirect, incidental, or consequential damages, security breaches, data loss, or legal issues arising from downloading, compiling, or using this material. You assume all responsibility and risk for your use of this software, and you are solely responsible for ensuring compliance with all applicable local, state, and international laws.

# PrestiumOS

PrestiumOS is a privacy-focused live operating system for USB sticks, with Tor and I2P built in. It
is built with Debian's **live-build** on Debian 13 "trixie" (amd64), with broad hardware
support: the current Debian release, kernel line and firmware set, with Secure Boot through shim and GRUB.

**Status:** Prestium **2.1** is the current release. It builds on **Prestium 2.0**, a full
modernization of the 2023 Prestium build, with tighter security and new features.

- **Download:** build the 2.1 ISO with [BUILDING.md](BUILDING.md) (`sudo ./build.sh`). The previous
  2.0 ISO is still available through [`Prestium-2.0-amd64.iso.torrent`](Prestium-2.0-amd64.iso.torrent).
- **What changed:** [CHANGELOG.md](CHANGELOG.md)

## Highlights

- **Built from git:** the whole image is built from the live-build configuration here, and every
  third-party download (Tor Browser, Firefox, Node.js, The Lounge, Feather) is checked against its
  publisher's signature, in a keyring holding only that publisher's key, and a pinned SHA-256 (Tor
  Browser: the newest signed release at build time, no older than a pinned minimum; uBlock Origin: the
  newest Mozilla-signed release on addons.mozilla.org at build time). The I2P reseed
  file ships in this repository (`i2pseeds.su3`) and is signature-checked at every build.
- **Wayland desktop** (labwc, waybar, swaylock, mako) with a restricted Wayland socket for apps:
  no screen capture, input injection or window snooping. A root broker keeps the full socket away from
  apps. The look is stock Adwaita light (GTK 2, 3 and 4, Qt through adwaita-qt, KDE apps), with a black
  top bar (Applications menu, clock, Tor and I2P status pills, a clock-sync symbol until the time is
  set, volume, network, battery, power) and a black bottom taskbar with one colour icon per window.
- **Sandboxed browsers:** Tor Browser and LibreWolf (I2P Browser) run in bubblewrap with their own empty
  network namespace. Tor Browser can reach only Tor, and LibreWolf only i2pd's HTTP proxy.
- **Browser Updater:** install the latest publisher-signed Tor Browser or I2P Browser for this session,
  over Tor or the I2P outproxy, and reset to the copy on the image.
- **Enforced AppArmor profiles** for the browsers and their launchers, Claws Mail, Gajim, OnionShare,
  Feather, LibreOffice, The Lounge (both instances), the local-only Firefox, KeePassXC, Kleopatra, the
  passphrase prompt, Tor's control-port filter and the programs that open downloaded files (Loupe,
  Evince, VLC, File Roller, FeatherPad, mat2, Metadata Cleaner, Audacity); the helpers those viewers start in
  bubblewrap run in stricter inner profiles. The build fails if another profile could attach to a
  program a Prestium profile confines, and the boot checks the loaded set again. Neither Claws Mail's
  GnuPG nor Kleopatra may write or hard-link GnuPG's `*.conf` files, which can name helper programs.
  Audacity runs in an empty network namespace.
- **Shared folders:** the apps share two folders, `~/Downloads` (the local Firefox, Claws Mail
  and Gajim) and `~/Documents` (LibreOffice, FeatherPad, Evince, File Roller, Audacity,
  Kleopatra and Feather). Only three folders are app-specific: the I2P Browser's
  (`~/I2P Browser`), I2P Torrents' (`~/Torrents`) and Tor Browser's
  (`~/Tor Browser`); the shared apps can't write in those three. Metadata Cleaner is the exception:
  it cleans a file in place wherever you keep it in the home (never in a hidden folder, `~/bin`, a
  desktop launcher, a wallet or a password database; volumes stay read-only). The viewers, players and editors
  (Loupe, Evince, VLC, LibreOffice, FeatherPad, Audacity, mat2, Metadata Cleaner) can open files anywhere in the home
  read-only, hidden folders and those three included, so a file opens in place from the file manager;
  keys, password databases, keyrings, wallets, browser profiles, mail and chat accounts and shell
  histories stay denied, and each still saves only in its own folders. The file manager pins those
  five, labelled I2P Browser, Torrents, Tor Browser, Documents and Downloads, plus Claws Mail's
  mailbox `~/Mail`, labelled Mail. To attach a document
  you made, copy it from `~/Documents` to `~/Downloads` first: mail and chat can't read `~/Documents`.
  Volumes under `/media` are read-only for the apps (KeePassXC may save its `.kdbx` there); move files
  onto them with the file manager.
- **Network privacy:** MAC address spoofing with a guard against leaks of the real address,
  default-deny firewall that stays closed when stopped (and fails loudly if it can't close at boot),
  no system DNS, IPv6 off, no LAN access. Tor and i2pd can't reach Prestium's local services.
  In the terminal, `http_proxy` and `https_proxy` point to i2pd (127.0.0.1:4450), an I2P-only proxy with
  no outproxy, so command-line tools reach `.i2p` sites only. For clearnet, use Tor
  (`curl --socks5-hostname 127.0.0.1:9050`) or the I2P outproxy (`curl -x http://127.0.0.1:4444`).
- **Tor Connection Assistant:** Direct, Snowflake, WebTunnel, obfs4 and meek, with bootstrap progress,
  Cancel, Retry and Revert at any point. Every change (Apply, Cancel, Revert, Reconnect) goes through
  the Wayland broker and is confirmed in a dialog only the person at the screen can answer, as for the
  I2P settings, so another program can't move Tor onto its own bridge or stop it; sudo allows only
  reading the status.
- **Time over Tor:** the clock is set from three pools of onion web servers (on Kicksecure's sdwdate
  design: median of three, Tor consensus check, never before the build date), re-synced at random
  intervals, and moved by a random offset at boot. No NTP and no clearnet time sources.
- **I2P:** i2pd with a per-boot port, signature-checked reseeding (over Tor or from a file), I2P mail
  (Claws Mail, which asks for your postman account on first start), IRC, torrents and Feather on I2P.
  The **I2P Connection Assistant** sets tunnel hops (1 to 7, default 3), the share level and the
  outproxy (Acetone by default, StormyCloud, or your own), each change confirmed at the screen, and
  reseeds. To get the browser going sooner after boot, i2pd keeps only 38 tunnels ready: 2+2 for the browser proxy, 1+1 for most other services, and i2pd's
  default 5+5 for the torrent client. Torrents (I2P) announces to I2P's usual open trackers (postman,
  DgTrack, InsulaOcculta, skank, atia, dg2) as well as the DHT, so magnet links without a tracker still find
  peers; its *Add .torrent* button can open `.torrent` files from the I2P Browser's download folder
  (read-only). Torrents keep their list and progress across i2pd restarts (persistent destination and
  DHT peer list), on the Connection Assistant's hops (default 3). i2pd relays
  other people's traffic at the *Low* share level by default (`i2pd.conf`: bandwidth class L, 32 KB/s,
  at most 30 % of it for relaying; floodfill off); the assistant also offers Medium (50 % of 64 KB/s)
  and High (80 % of 128 KB/s).
- **Messenger (Gajim):** Tor and I2P proxies ready to use. Gajim ships Tor
  (SOCKS5 127.0.0.1:9050) plus I2P (SOCKS5 127.0.0.1:4447 and HTTP 127.0.0.1:4444) proxy
  profiles, with Tor as the global default; choose another per account in Account Settings.
  Its menu entry is plain *Gajim*.
- **IRC over I2P and over Tor:** two separate The Lounge instances in the local-only Firefox, each
  signed in automatically. *IRC (I2P)* has IRC2P and Ilita. *IRC (Tor)* reaches IRC only through Tor's
  SOCKS port (the firewall allows its user nothing else, not even DNS), with onion presets and its own
  Tor circuits per network: OFTC (default), Ergo, DarkScience and IRCNow, none of which needs an
  account. Networks connect only when you choose Connect. A network you add yourself checks the
  server's TLS certificate by default; only the OFTC preset doesn't (its onion address authenticates
  it). Both instances use the Tech Innovation theme by default (10 bundled themes) and can't rewrite
  their own code or configuration.
- **Verified live image:** the root filesystem is mounted through dm-verity, and Prestium refuses to
  boot when it doesn't match the root hash in the boot menu (the kernel, initramfs and boot menu
  themselves are not covered yet; see the CHANGELOG's Known security limits).
- **UEFI Secure Boot:** boots with Secure Boot on, through Debian's signed boot chain:
  Debian's shim (signed by Microsoft), Debian's signed GRUB and Debian's signed kernel. The kernel
  command line includes `lockdown=integrity`, so the kernel is locked down even with Secure Boot off
  or on BIOS. The build stops if any of the signed boot files isn't Debian's signed file. The
  initramfs and the boot menus (and so the kernel command line) are not signed, as on Debian live images; a signed
  unified kernel image is future work. Booting with Secure Boot off, or on BIOS, works as before, and
  Prestium tells you when Secure Boot is off.
- **Fail-closed safety alerts** when the USB watchdog, MAC guard, Wayland broker, ptrace protection,
  AppArmor (module, service or any Prestium profile not in enforce mode), kernel lockdown, the boot
  settings check or the shutdown memory wipe isn't working, and when the time sync refuses a time.
  Prestium also says when it runs in a virtual machine (and, after 10 minutes, why Tor or I2P hasn't
  connected there) and when the image is more than 45 days old.
- **Session wipe at shutdown:** the session's files on the live overlay and the runtime secrets under
  `/run` (bridge lines, Tor's control cookie, IRC sign-in tokens and more) are deleted and checked; a
  failure is logged as "session wipe FAILED", never as success.
- **Network Logs, only when you ask:** in the default boot Tor and i2pd keep no logs. The boot menu
  entry *Prestium 2.1 (Network Logs)* turns on their logs and *Network > Network Logs*, a read-only
  view of the Tor, I2P and control-port filter logs of that boot.
- **Apps:** besides the above, OnionShare, KeePassXC, Kleopatra, LibreOffice, Evince (Document Viewer,
  the default for PDF, PostScript, DjVu, XPS and comic books), Audacity, VLC, Loupe, Metadata Cleaner, Feather (Monero, on I2P) and *Unlock Encrypted Volume* for LUKS, VeraCrypt,
  TrueCrypt and BitLocker volumes and file containers, without root.
- **Only its own boot settings:** Prestium refuses to start, and restarts the computer, when the
  kernel command line isn't exactly the one in its boot menu. The initramfs checks first, then a
  service runs before AppArmor loads. GRUB loads only this stick's own boot files.
- **Hardware:** current firmware, PipeWire audio, HiDPI scaling, laptop keys, touchpad settings and an
  on-screen keyboard.

## Known limits

- **Someone who can write to the USB stick can change the next boot.** dm-verity checks the root
  filesystem and the boot menu is password-locked, but both checks live in unsigned files on the stick:
  the boot menus (`grub.cfg`, with the root hash and the password hash), the initramfs and live-boot in
  it, and the initramfs check that refuses any kernel command line other than the image's own. Secure
  Boot covers only shim, GRUB and the kernel (Debian's signed files); GRUB doesn't check the initramfs.
  Replacing those files together with the image defeats both checks. The future fix is a signed unified kernel image (UKI: kernel, initramfs and
  command line in one Secure Boot-signed file); it isn't implemented. Keep the stick with you, and
  check it against a signed release from another computer (see Verify a download).
- **X11-only programs share one Xwayland server**, so they can see each other's input and windows
  (not those of Wayland apps such as the browsers).
- **Per-app folders limit writes, not reads:** a compromised viewer can still read the file folders
  (it has no network to send them anywhere).
- **A kernel memory-corruption bug can still be turned into an escape through the vDSO.** The
  technique in Phrack 73 ([Escaping from a Docker container through vDSO](https://phrack.org/issues/73/escaping-from-a-docker-container-through-vdso_md.html))
  moves or remaps the vDSO (`mremap()`, or `arch_prctl()` with checkpoint/restore support) so that even a
  weak primitive such as an arbitrary increment can rewrite code every process runs, which escapes
  AppArmor, bubblewrap and Landlock alike. The fix, `CONFIG_MSEAL_SYSTEM_MAPPINGS` (system mappings
  sealed with `mseal`), needs kernel 6.15 or later; Debian 13's 6.12 doesn't have it. `vsyscall=none`
  and `ia32_emulation=0` remove the legacy mappings and the 32-bit entry points, not this one.
- The ISO itself isn't signed (`SHA256SUMS` is), and builds are not yet bit-for-bit reproducible.
- More, with details, in the CHANGELOG's Known security limits.

## Tor Connection Assistant: DNS design

**DNS design.** Prestium has no system DNS on purpose, which is why Snowflake and WebTunnel did not
work in earlier releases: they need to look up host names (Snowflake's front domains and STUN servers, meek's
front, the WebTunnel bridge's host). Since 2.0:

- **Tor traffic is not routed through I2P.** Tor and its pluggable transports connect directly.
- Only those **host-name look-ups** go through I2P: the helper asks several DNS-over-HTTPS providers
  **in parallel** (Cloudflare, Google, Quad9, AdGuard, Mullvad; port 443 only, keep-alive HTTPS
  connections) through i2pd's HTTP proxy (127.0.0.1:4444), which forwards them to the I2P outproxy
  (`proxy4uwdijqxac2bvdx4fuhem6njmiwukuk2gelejv2nzxka2xq.b32.i2p`). The first valid answer (public
  IPv4 only) wins, failing providers are dropped, and answers are cached.
- The answers are pinned in a marked block of `/etc/hosts`, which the transports (run by Tor as
  `debian-tor`) read; nothing else on the system resolves names. So a network that blocks or
  poisons DNS for Tor infrastructure cannot stop Snowflake or WebTunnel from finding their servers.
- The look-ups run as a dedicated user, `prestium-ptdns`, which the firewall lets reach
  127.0.0.1:4444 and nothing else.
- **Firewall stays strict**: Tor's uid may use TCP as before; **UDP is allowed for Tor's uid only
  while Snowflake mode is on** (WebRTC/STUN), never to loopback, via `/etc/ferm/prestium-tor-pt.conf`
  which the helper rewrites and ferm includes.
- **Snowflake under AppArmor:** Debian's `system_tor` profile blocked the transports from reading the
  system CA bundle, so Snowflake's TLS to its broker failed; `/etc/apparmor.d/local/system_tor`
  adds `abstractions/ssl_certs` and the network reads Snowflake's WebRTC stack needs.

## Verify a download

Check a download before you write it to a USB stick.

- **2.1** writes `SHA256SUMS` (the ISO, its manifest, its dm-verity root hash and its package list). When a release is signed
  (`SHA256SUMS.asc` from `scripts/sign-release.sh`): import the Prestium release key, compare its full
  fingerprint with the one published with the release, then

  ```
  gpg --verify SHA256SUMS.asc SHA256SUMS
  sha256sum --ignore-missing -c SHA256SUMS
  ```

  The first command must say "Good signature" from that fingerprint; a warning that the key is not
  certified is normal. The second must say `OK` for the ISO.
- **2.0** has no signed checksum file. Compare `sha256sum Prestium-2.0-amd64.iso` with the SHA-256 on
  prestium.org, and get the torrent from this repository: the torrent's piece hashes check the data
  as it downloads, but neither proves who made the image.

To build the same image yourself, see [BUILDING.md](BUILDING.md); each build writes a manifest of what
went into it.

## Repository layout

- `auto/`, `config/`, `build.sh`, `scripts/`, `thirdparty/`: the live-build configuration
  (see [BUILDING.md](BUILDING.md)); `thirdparty/` holds the pinned versions, hashes and publisher keys.
- `i2pseeds.su3`: the signed I2P reseed file the build ships.
- `Prestium-2.0-amd64.iso.torrent`: the torrent for the previous release.
- `tests/`: checks for the boot chain (dm-verity, boot menu lock, command line policy, Secure Boot),
  the firewall, sandboxes and AppArmor profiles, the Wayland broker and its dialogs, the MAC guard,
  the Tor and I2P helpers, The Lounge, the Browser Updater and the desktop's design; `tests/ci.sh`
  runs the ones that don't need a live session.

## License

MIT, see [LICENSE.txt](LICENSE.txt).
