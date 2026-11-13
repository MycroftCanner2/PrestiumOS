Disclaimer: This project and all associated materials (including software, repositories, scripts, and ISO files) are provided strictly "as is" and "as available," for informational, educational, and experimental purposes only, without any express or implied warranties of any kind—including, but not limited to, fitness for a particular purpose, security, accuracy, or non-infringement. The creator and publisher make no claims regarding the safety, integrity, or audit status of any code or binaries, explicitly disclaim any expertise or maintenance obligations, and shall not be held liable for any direct, indirect, incidental, or consequential damages, security breaches, data loss, or legal issues arising from downloading, compiling, or using this material. You assume all responsibility and risk for your use of this software, and you are solely responsible for ensuring compliance with all applicable local, state, and international laws.

# PrestiumOS

PrestiumOS is a privacy-focused live operating system for USB sticks, with Tor and I2P built in. It
is built with Debian's **live-build** on Debian 13 "trixie" (amd64), and it follows Tails for hardware
support: the same Debian release, kernel line and firmware set, with Secure Boot through shim and GRUB.

**Status:** Prestium **2.1** is the current release. It builds on **Prestium 2.0**, a full
modernization of the 2023 Prestium build, with tighter security and new features.

- **Download:** build the 2.1 ISO with [BUILDING.md](BUILDING.md) (`sudo ./build.sh`). The previous
  2.0 ISO is still available through [`Prestium-2.0-amd64.iso.torrent`](Prestium-2.0-amd64.iso.torrent).
- **What changed:** [CHANGELOG.md](CHANGELOG.md)

## Highlights

- **Built from git:** the whole image is built from the live-build configuration here, and every
  third-party download (Tor Browser, Firefox, Node.js, The Lounge, Feather, lurch, the I2P reseed file)
  is checked against its publisher's signature and a pinned SHA-256 (Tor Browser: the newest signed
  release at build time, no older than a pinned minimum).
- **Wayland desktop** (labwc, waybar, swaylock, mako) with a restricted Wayland socket for apps:
  no screen capture, input injection or window snooping. A root broker keeps the full socket away from apps.
- **Sandboxed browsers:** Tor Browser and LibreWolf (I2P Browser) run in bubblewrap with their own empty
  network namespace. Tor Browser can reach only Tor, and LibreWolf only i2pd's HTTP proxy.
- **Browser Updater:** install the latest publisher-signed Tor Browser or I2P Browser for this session,
  over Tor or the I2P outproxy, and reset to the copy on the image.
- **Enforced AppArmor profiles** for the browsers, Claws Mail, Gajim, Pidgin, OnionShare, Feather,
  LibreOffice, The Lounge (both instances), the local-only Firefox, KeePassXC, Kleopatra and the programs that open
  downloaded files.
- **Shared folders:** the apps share two folders, `~/Downloads` (the local Firefox, Claws Mail, Gajim
  and Pidgin) and `~/Documents` (LibreOffice, GIMP, FeatherPad, File Roller, Xarchiver, Audacity,
  Kleopatra, Metadata Cleaner and Feather). Only three folders are app-specific: the I2P Browser's
  (`~/I2P Browser`), I2P Torrents' (`~/Torrents`) and Tor Browser's
  (`~/Tor Browser`); the shared apps can't write in those three. The file manager pins exactly those
  five, labelled i2P Browser, i2P Torrents, Tor Browser, Documents and Downloads. To attach a document
  you made, copy it from `~/Documents` to `~/Downloads` first: mail and chat can't read `~/Documents`.
  Volumes under `/media` are read-only for the apps; move files onto them with the file manager.
- **Network privacy:** MAC address spoofing with a guard against leaks of the real address,
  default-deny firewall that stays closed when stopped, no system DNS, IPv6 off, no LAN access.
  In the terminal, `http_proxy` and `https_proxy` point to i2pd (127.0.0.1:4450), an I2P-only proxy with
  no outproxy, so command-line tools reach `.i2p` sites only. For clearnet, use Tor
  (`curl --socks5-hostname 127.0.0.1:9050`) or the I2P outproxy (`curl -x http://127.0.0.1:4444`).
- **Tor Connection Assistant:** Direct, Snowflake, WebTunnel, obfs4 and meek, with bootstrap progress,
  Cancel, Retry and Revert at any point.
- **I2P:** i2pd with a per-boot port, signature-checked reseeding (over Tor or from a file), I2P mail
  (Claws Mail), IRC, torrents and Feather on I2P. To get the browser going sooner after boot, i2pd
  keeps only 38 tunnels ready: 2+2 for the browser proxy, 1+1 for most other services, and i2pd's
  default 5+5 for the torrent client. Torrents (I2P) announces to I2P's usual open trackers (postman,
  DgTrack, InsulaOcculta, skank, atia, dg2) as well as the DHT, so magnet links without a tracker still find
  peers; its *Add .torrent* button can open `.torrent` files from the I2P Browser's download folder
  (read-only). Torrents keep their list and progress across i2pd restarts (persistent destination and
  DHT peer list), on the Connection Assistant's hops (default 3). i2pd relays
  other people's traffic at the *Medium* share level by default (64 KB/s, at most half of it for
  relaying); the I2P Connection Assistant sets Low, Medium or High.
- **IRC over I2P and over Tor:** two separate The Lounge instances in the local-only Firefox, each
  signed in automatically. *IRC (I2P)* has IRC2P and Ilita. *IRC (Tor)* reaches IRC only through Tor's
  SOCKS port (the firewall allows its user nothing else, not even DNS), with onion presets and its own
  Tor circuits per network. Networks connect only when you choose Connect. OFTC (default), Ergo,
  DarkScience and IRCNow need no account. Libera.Chat, hackint and AlphaChat are listed after them
  because they sign you in with SASL; see *IRC over Tor: networks that need an account* below.
- **Verified live image:** the root filesystem is mounted through dm-verity, and Prestium refuses to
  boot when it doesn't match the root hash in the boot menu (the kernel, initramfs and boot menu
  themselves are not covered yet; see the CHANGELOG's Known security limits).
- **UEFI Secure Boot:** boots with Secure Boot on, through Debian's signed boot chain as Tails does:
  Debian's shim (signed by Microsoft), Debian's signed GRUB and Debian's signed kernel. The kernel
  command line includes `lockdown=integrity`, so the kernel is locked down even with Secure Boot off
  or on BIOS. The build stops if any of the signed boot files isn't Debian's signed file. The
  initramfs and the boot menus (and so the kernel command line) are not signed, as in Tails; a signed
  unified kernel image is future work. Booting with Secure Boot off, or on BIOS, works as before, and
  Prestium tells you when Secure Boot is off.
- **Fail-closed safety alerts** when the USB watchdog, MAC guard, Wayland broker, ptrace protection or
  shutdown memory wipe isn't working.
- **Only its own boot settings:** Prestium refuses to start, and restarts the computer, when the
  kernel command line isn't exactly the one in its boot menu. The initramfs checks first, then a
  service runs before AppArmor loads. GRUB loads only this stick's own boot files.
- **Hardware:** current firmware, PipeWire audio, HiDPI scaling, laptop keys, touchpad settings and an
  on-screen keyboard.

## IRC over Tor: networks that need an account

Prestium has no shared account for these networks: a password or key shipped in the image would be
public, anyone could take the account over, and the network would ban it for everyone. Each person
brings their own account. Sign-in details live only in RAM and are gone after a reboot, so you enter
them again each session. Libera.Chat and AlphaChat don't connect until the sign-in is filled in; the
network's lobby says what's missing.

- **AlphaChat:** Tor users need a verified AlphaChat account, registered without Tor first
  (alphachat.net/tor.xhtml). In *IRC (Tor)*, right-click *AlphaChat (SASL)*, choose *Edit this
  network*, select *Username + password (SASL PLAIN)* under Authentication, enter the account and
  password, choose *Save network*, then *Connect*.
- **hackint:** works over Tor without an account. To use your hackint account, select
  *Username + password (SASL PLAIN)* the same way. hackint no longer accepts `/msg NickServ IDENTIFY`
  and lets Tor users register an account through a proof-of-work check (hackint.org/transport/tor).
- **Libera.Chat:** over Tor it only takes an account registered without Tor, signed in with a client
  certificate (SASL EXTERNAL), not a password (libera.chat/guides/connect). The preset already uses
  *Client certificate (SASL EXTERNAL)*. Its lobby shows the certificate's SHA-512 fingerprint. From a
  connection without Tor, such as a phone or another computer signed in to your account, send
  `/msg NickServ CERT ADD <fingerprint>`, then choose *Connect* in Prestium. The Lounge makes a new
  certificate every boot, so this is needed once per session, and `/msg NickServ CERT LIST` and
  `CERT DEL` tidy up old ones. Importing your own long-lived certificate isn't supported yet.


- **Someone who can write to the USB stick can change the next boot.** dm-verity checks the root
  filesystem and the boot menu is password-locked, but both checks live in unsigned files on the stick:
  the boot menus (`grub.cfg`, with the root hash and the password hash), the initramfs and live-boot in
  it, and the initramfs check that refuses any kernel command line other than the image's own. Secure Boot covers only shim, GRUB and the kernel (Debian's signed files, as in Tails); GRUB doesn't check the initramfs. Replacing those files together with the image
  defeats both checks. The future fix is a signed unified kernel image (UKI: kernel, initramfs and
  command line in one Secure Boot-signed file); it isn't implemented. Keep the stick with you, and
  check it against a signed release from another computer (see Verify a download).
- More, with details, in the CHANGELOG's Known security limits.

## Tor Connection Assistant: DNS design

**DNS design.** Prestium has no system DNS on purpose, which is why Snowflake and WebTunnel did not
work in earlier releases: they need to look up host names (Snowflake's front domains and STUN servers, meek's
front, the WebTunnel bridge's host). In 2.0:

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
- Optional, experimental: **"Snowflake rendezvous via the I2P outproxy"** (shown only if the
  installed `snowflake-client` has `-proxy`): Snowflake's broker request goes through i2pd's SOCKS
  proxy (4447) and the I2P outproxy; the WebRTC data still goes directly to the Snowflake proxy.

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
  (see [BUILDING.md](BUILDING.md)).
- `tests/`: checks for the firewall, sandboxes, AppArmor profiles, the Wayland broker and the MAC guard.

## License

MIT, see [LICENSE.txt](LICENSE.txt).
