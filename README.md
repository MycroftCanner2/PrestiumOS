Disclaimer: This project and all associated materials (including software, repositories, scripts, and ISO files) are provided strictly "as is" and "as available," for informational, educational, and experimental purposes only, without any express or implied warranties of any kind—including, but not limited to, fitness for a particular purpose, security, accuracy, or non-infringement. The creator and publisher make no claims regarding the safety, integrity, or audit status of any code or binaries, explicitly disclaim any expertise or maintenance obligations, and shall not be held liable for any direct, indirect, incidental, or consequential damages, security breaches, data loss, or legal issues arising from downloading, compiling, or using this material. You assume all responsibility and risk for your use of this software, and you are solely responsible for ensuring compliance with all applicable local, state, and international laws.

# PrestiumOS

PrestiumOS is a privacy-focused live operating system for USB sticks, with Tor and I2P built in. It
is built with Debian's **live-build** on Debian 13 "trixie" (amd64), and it follows Tails for hardware
support: the same Debian release, kernel line and firmware set, with Secure Boot through shim and GRUB.

**Status:** active development. PrestiumOS starts from **Prestium 2.0**, a full modernization of the
2023 Prestium build. Version **2.1** is in progress here, with enhanced security and new features.

- **Download:** the 2.0 ISO through [`Prestium-2.0-amd64.iso.torrent`](Prestium-2.0-amd64.iso.torrent)
- **Build it yourself:** [BUILDING.md](BUILDING.md) (`sudo ./build.sh`)
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
- **Enforced AppArmor profiles** for the browsers, Claws Mail, Gajim, Pidgin, OnionShare, Feather,
  LibreOffice, The Lounge and the local-only Firefox.
- **Network privacy:** MAC address spoofing with a guard against leaks of the real address,
  default-deny firewall that stays closed when stopped, no system DNS, IPv6 off, no LAN access.
- **Tor Connection Assistant:** Direct, Snowflake, WebTunnel, obfs4 and meek, with bootstrap progress,
  Cancel, Retry and Revert at any point.
- **I2P:** i2pd with a per-boot port, signature-checked reseeding (over Tor or from a file), I2P mail
  (Claws Mail), IRC (The Lounge), torrents and Feather on I2P.
- **Fail-closed safety alerts** when the USB watchdog, MAC guard, Wayland broker, ptrace protection or
  shutdown memory wipe isn't working.
- **Hardware:** current firmware, PipeWire audio, HiDPI scaling, laptop keys, touchpad settings and an
  on-screen keyboard.

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

- **Releases with `SHA256SUMS` and `SHA256SUMS.asc`** (from 2.1 on, once they are signed): import the
  Prestium release key, compare its full fingerprint with the one published with the release, then

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
