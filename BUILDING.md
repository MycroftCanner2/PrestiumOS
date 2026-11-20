# Building PrestiumOS (live-build)

PrestiumOS is built from scratch with Debian's **live-build**, the same tool Debian's own live
images use. Everything that makes it Prestium is in this repository: the package lists, the
customised files, the setup hooks and the pinned third-party downloads.

**quick_qubes branch:** this branch builds the VM / Qubes OS variant,
`Prestium-2.1-quick_qubes-amd64.iso`, with no bare-metal firmware (see the quick_qubes section of
[README.md](README.md)). The build steps, requirements and checks are the same as on `main`. Only the
package set, the archive areas and the output names differ, as described below.

- Base: Debian 13 "trixie", amd64. Archive areas `main contrib` (quick_qubes: no `non-free-firmware`), plus
  `trixie-updates`, `trixie-security` and `trixie-backports`.
- Kernel: Debian's trixie `linux-image-amd64` (the 6.12 line). It has the guest drivers built in or
  as modules (virtio, Xen PV front ends for Qubes OS, VMware and Hyper-V), so no extra package is needed.
- Firmware (quick_qubes): none. No `firmware-*`, no CPU microcode (the host loads it) and no firmware
  pin. `--firmware-chroot false` and `--firmware-binary false` stay set, and hook 9980 stops the build
  if a firmware or microcode package is installed anyway. Wi-Fi, mobile broadband, tethering, tablet
  and real-GPU X driver packages are left out too (see the quick_qubes section of README.md).
- Boot: hybrid ISO, BIOS (isolinux) and UEFI, with **Secure Boot** through Debian's signed boot chain:
  `EFI/boot/bootx64.efi` is Debian's shim (signed by Microsoft), which loads
  `EFI/boot/grubx64.efi`, Debian's signed GRUB for removable media (`gcdx64.efi.signed` from
  `grub-efi-amd64-signed`), which loads Debian's signed kernel (`linux-image-amd64` from
  `linux-signed-amd64`). live-build sets this up (`--uefi-secure-boot enable`); hook 9040 stops the
  build when any of the three is not Debian's signed file (see Secure Boot below). Kernel command line: hardening options, the
  internal-disk (ahci/libata) blacklist with the patched live-boot fallback, `module.sig_enforce=1`,
  `lockdown=integrity` and AppArmor. The live image is mounted through dm-verity (root hash on the command line).

## Requirements

A Debian 13 host (a VM is fine) with about 25 GB free and root access:

    sudo apt install live-build debootstrap squashfs-tools xorriso mtools dosfstools \
        curl gnupg gpgv git unzip npm python3 openssl cryptsetup-bin sbsigntool

On a host that is not amd64 (e.g. arm64), also install `qemu-user-static` and make sure
`/proc/sys/fs/binfmt_misc/qemu-x86_64` exists with flag `F`. The amd64 chroot then runs emulated,
which works but is several times slower.

## Build

    git clone https://github.com/MycroftCanner2/PrestiumOS.git
    cd PrestiumOS
    sudo ./build.sh

`build.sh`:

1. runs `scripts/fetch-thirdparty.sh`: downloads Tor Browser, Firefox, Node.js, Feather (zip and `.asc`
   from its GitHub releases, `github.com/feather-wallet/feather`), The Lounge
   (npm), checks each one against its publisher's OpenPGP signature
   (`thirdparty/keys/`) **and** the SHA-256 pinned in `thirdparty/versions.sh`, and stages them in
   `config/includes.chroot/usr/src/prestium-thirdparty/` (not committed; removed from the image by
   the last hook); it also downloads i2pd, PurpleI2P's trixie amd64 `.deb` from its GitHub releases
   (`github.com/PurpleI2P/i2pd`, version and SHA-256 pinned as `I2PD_VERSION`/`I2PD_DEB_VERSION`/`I2PD_SHA256`).
   PurpleI2P publishes no detached signature for the `.deb`, so it has **no** signature check: the
   SHA-256 pinned in `thirdparty/versions.sh` is its only trust anchor. Its package name, version and
   architecture are checked too, and it is staged as `i2pd.deb` (hook 0005 installs it); it also fetches the newest uBlock Origin from addons.mozilla.org (`scripts/amo-latest.py`:
   the AMO API's SHA-256 and size, Mozilla's add-on signature chained to the pinned AMO root
   `thirdparty/keys/mozilla-amo-root.pem` with the add-on id as signer, every file against
   `META-INF/manifest.mf`, the manifest's id and version; any failure stops the build, there is no
   committed fallback), which hook 0200 checks again (and its `strict_min_version` against Tor
   Browser's and LibreWolf's Firefox versions) and installs for both browsers and their opt-overlay; it also stages an I2P reseed file — the repo-shipped `i2pseeds.su3` first (see CHANGELOG), checks it with
   `config/includes.chroot/usr/local/lib/prestium/verify-su3` (SU3 format, RSA-4096/SHA-512 signature against `thirdparty/keys/reseed/`,
   at most 14 days old for downloads; the repo-shipped `i2pseeds.su3` is the primary source and its age only warns) and puts it at `config/includes.chroot/var/lib/i2pd/stormycloud-i2pseeds.su3`;
   (2.1: the image also ships copies of `thirdparty/keys/torbrowser.asc` and `mozilla.asc` in
   `/usr/share/prestium/keys/` and of `scripts/sigcheck.sh` in `/usr/local/lib/prestium/` for the
   Browser Updater, and keeps `/usr/share/prestium/opt-overlay`; when a key or `sigcheck.sh` changes,
   update both copies; `tests/test_browser_install.py` and `tests/test_sigcheck.sh` compare them)
2. runs `lb config` (options in `auto/config`);
3. runs `lb bootstrap`, `lb chroot`, `lb installer` and `lb binary` (the final apt sources go in between chroot and installer) and writes `Prestium-2.1-quick_qubes-amd64.iso`, `Prestium-2.1-quick_qubes-amd64.iso.sha256`, `SHA256SUMS`, the `.manifest`, the `.roothash` (the image's dm-verity root hash) and the `.packages` list.

**Secure Boot.** The UEFI boot chain is Debian's signed one, the same as Debian's live images:
firmware → shim → GRUB → kernel. live-build installs `shim-signed` and `grub-efi-amd64-signed`
only for the binary stage (they are not in the live system) and copies `shimx64.efi.signed` to
`EFI/boot/bootx64.efi` and `gcdx64.efi.signed` to `EFI/boot/grubx64.efi`, in the ISO tree and in
`boot/grub/efi.img`. Hook 9040 checks the result with `sbverify` (sbsigntool) against the CA
certificates in `thirdparty/keys/secure-boot/` (pinned by SHA-256 in the hook): shim is signed for the
Microsoft UEFI CA 2011 or 2023 and has Debian's Secure Boot CA built in; GRUB is signed by Debian's
`grub2` key, has every module the locked menu needs built in and does not turn shim's kernel check off;
every `live/vmlinuz*` is the chroot's kernel from a `linux-signed-*` package (not `-unsigned`), matches
dpkg's MD5 and is signed by Debian's `linux` key; there are no other EFI programs. With Secure Boot on,
the firmware checks shim, shim checks GRUB, and GRUB has shim check the kernel. The kernel command line
includes `lockdown=integrity`, so the kernel is locked down (integrity) even with Secure Boot off:
unsigned modules, `/dev/mem`, kexec of unsigned kernels and hibernation are refused (Prestium needs
none of them; `module.sig_enforce=1` already refused unsigned modules). Not signed and not checked by
the firmware: the initramfs, the GRUB configs (menu, root hash, password hash) and so the kernel
command line, as on Debian live images. A signed unified kernel image (UKI) would cover them; it is future
work. Booting with Secure Boot off still works (shim then checks nothing; the kernel is still locked
down from the command line). The BIOS path (isolinux) is unchanged.

**Boot menu password.** The boot menus are locked (hook 9020): the entries boot without a password,
but editing an entry or GRUB's command line needs the GRUB superuser `prestium`. To set its password,
make a hash once and keep it next to the tree (gitignored; only the hash, never the password):

    scripts/grub-pbkdf2.py > grub-password.pbkdf2
    sudo ./build.sh

or pass it as `sudo PRESTIUM_GRUB_PASSWORD_HASH=grub.pbkdf2.sha512.... ./build.sh` (a hash from
`grub-mkpasswd-pbkdf2` works too). Without one, the build uses the hash of a random password nobody
knows: the menu is locked for everyone, which is the safe default for a release; build with your own
hash when you need to edit boot entries. The manifest says which (`boot_menu_lock`).
Edited entries still have to follow the image's kernel command line policy
(`config/includes.chroot/usr/share/prestium/boot/cmdline.policy`). The initramfs refuses any option
the policy doesn't list and restarts the computer. To boot with other options, add them to the policy
and rebuild.

An interrupted build can be continued with `sudo ./build.sh --resume`; `sudo ./build.sh --clean`
starts over (`lb clean --purge`). Expect 1-2 hours on a normal amd64 machine (much longer emulated).

Repeatable builds: `sudo PRESTIUM_SNAPSHOT=20261110T000000Z ./build.sh` takes Debian (main and
security) from snapshot.debian.org at that time, and `build.sh` sets `SOURCE_DATE_EPOCH` to the source
commit's time. The Tor and LibreWolf repositories have no snapshots (i2pd is a pinned `.deb`), and the image is not yet
bit-for-bit reproducible; compare two builds with their `.manifest` files.

## Checks

`tests/ci.sh` runs every check by hand (on Debian 13, with the same packages installed):
shellcheck (errors) on every shell script, every AppArmor profile compiled with `apparmor_parser`,
a scan for committed private keys and tokens, `systemd-analyze security` scores for the hardened
services, and the test suite. Four tests need a real Wayland session, bwrap and sudo
(`test_wayland_broker.sh`, `test_wayland_session.sh`, `test_browser_sandbox.sh`,
`test_onion_grater_identity.py`); run those on a build machine or the live system.

## Layout

| Path | What it is |
| --- | --- |
| `auto/config` | the `lb config` options (distribution, archive areas, boot loaders, Secure Boot, kernel command line, squashfs compression) |
| `config/package-lists/prestium.list.chroot` | the packages installed by hand in earlier Prestium releases (derived from their dpkg selections, build-only packages removed) |
| `config/package-lists/prestium-2.0.list.chroot` | 2.0 additions: PipeWire/WirePlumber audio, pasystray, the assistant's GTK bindings |
| `config/package-lists/live.list.chroot` | live-boot (no live-config: Prestium sets up its user itself) |
| `config/archives/` | build-time apt sources and keys: Tor Project, LibreWolf, each `signed-by` its own key (live-build installs `<name>.key.chroot` as `/etc/apt/trusted.gpg.d/<name>.key.chroot.gpg`); origin pins limiting each repo to its own packages (quick_qubes: no firmware pin) |
| `config/preseed/` | non-interactive answers (locale, keyboard, ferm; quick_qubes: no firmware licences) |
| `config/includes.chroot/` | Prestium's own files and the package files it changes, carried over from the earlier Prestium root filesystem as a diff against the packaged files (see below), plus the 2.0 changes |
| `config/includes.chroot/usr/share/prestium/build/` | build-only data used by the hooks (owners/modes manifest, enabled units, optional packages, final apt sources); deleted from the image |
| `config/hooks/live/*.hook.chroot` | setup steps, in order (below) |
| `config/hooks/live/9000-prestium-boot-menu.hook.binary` | boot menu labels ("Prestium 2.1 quick_qubes": version and os-release `VARIANT_ID`) |
| `config/hooks/live/9020-prestium-boot-lock.hook.binary` | locks the boot menus: GRUB superuser (PBKDF2 hash, exported for submenus, also in the EFI image's and per-platform grub.cfg; needs mtools), every entry `--unrestricted`; isolinux `allowoptions 0`; every kernel line checked against a banned list (shells, init, security modules, debug, persistence, findiso=) and must have exactly one `lockdown=integrity`; findiso= and loopback.cfg removed |
| `scripts/grub-pbkdf2.py` | makes the GRUB password hash (`--random` for one nobody knows) |
| `scripts/efi-inspect.py` | read-only facts about an EFI file for hook 9040: SBAT, a built-in certificate (shim's vendor CA), a GRUB image's built-in modules, prefix and objects |
| `config/hooks/live/9010-prestium-verity-boot.hook.binary` | checks the image against its dm-verity hash tree and puts the root hash and `panic=10` (no initramfs shell) on every boot entry |
| `config/hooks/live/9030-prestium-boot-cmdline.hook.binary` | only the image's own kernel command line: GRUB's EFI config searches for this build's `/.disk/prestium-<id>` on the boot disk first (no other disk's `/.disk/info`), reboots when it's missing; every boot entry checked against `cmdline.policy` with the initramfs's own code; no chainloader/loopback/load_env/foreign search or kernel; policy = `LB_BOOTAPPEND_LIVE`; no built-in kernel command line; the initrd runs the guard (needs mtools) |
| `config/hooks/live/9040-prestium-secure-boot.hook.binary` | Secure Boot chain: `LB_UEFI_SECURE_BOOT="enable"`; the only EFI programs are `EFI/boot/bootx64.efi` and `grubx64.efi`, the same in the ISO tree and efi.img; shim signed for Microsoft's UEFI CA with Debian's CA built in, GRUB and every `live/vmlinuz*` signed by Debian (sbverify, CA certificates in `thirdparty/keys/secure-boot/`), GRUB's built-in modules, the kernel from `linux-signed-*` (needs sbsigntool, mtools) |
| `config/bootloaders/` | boot menu entries: Prestium 2.1, nomodeset, camera and microphone off |
| `thirdparty/` | pinned versions/SHA-256 (`versions.sh`), publisher keys, The Lounge's npm lockfile, the Secure Boot CA certificates (`keys/secure-boot/`: Microsoft UEFI CA 2011 and 2023, Debian Secure Boot CA; pinned in hook 9040) |
| `scripts/fetch-thirdparty.sh` | download + verify + stage third-party software |
| `scripts/amo-latest.py` | newest uBlock Origin from addons.mozilla.org: AMO hash, Mozilla signature, id, version, `strict_min_version` |
| `scripts/thelounge-themes.py` | regenerates The Lounge's 10 Theme Factory theme packages from `scripts/thelounge-theme.css.in` and checks their contrast (`--check` only verifies; the generated files are committed) |
| `build.sh` | the whole build |

### Hooks

| Hook | Does |
| --- | --- |
| `0001-prestium-build-dns` | build only: gives the hooks a resolver (Prestium's own `resolv.conf` has none) |
| `0005-prestium-i2pd` | installs i2pd from the staged GitHub `.deb` after checking it again against its pinned SHA-256, package name, version and architecture (apt takes its dependencies from Debian; Prestium's `/etc/i2pd` config files are kept); Debian's own i2pd is pinned out (`Pin-Priority: -1`) |
| `0010-prestium-optional-packages` | installs the earlier releases' dependency/recommends set (parity), skipping names the archive no longer has (quick_qubes: no extra firmware) |
| `0100-prestium-users` | `user` (1000, autologin, empty password until a session password is set), `i2pd` moved to uid/gid 2000, `thelounge`, `thelounge-tor` (2.1, IRC (Tor)), `onion-grater`, `prestium-htp`, `prestium-ptdns` (2.0); groups `autologin`, `i2ptorrents`, `prestium-localweb`; root locked |
| `0200-prestium-thirdparty` | Tor Browser in `/opt/tor-browser` (read-only, Prestium policies + the newest uBlock Origin, also for LibreWolf), Firefox in `/opt/firefox` (local pages only, no first-run screens), Node.js, The Lounge (+ offline patch, lobby text for networks that are not connected, connecting line only when a connection starts, 320s IRC ping timeout, and for the Tor instance every network through Tor's SOCKS port), Feather |
| `0400-prestium-system` | the exact set of enabled/masked units carried over from earlier releases + PipeWire user units, gvfs network backends diverted, alternatives (iptables/ip6tables pinned to legacy, the backend ferm and `prestium-firewall-early` share), CA list (emSign roots distrusted), dconf, plymouth theme, locale, version strings |
| `0405-prestium-verity` | live-boot mounts the image only through dm-verity: every image needs its hash tree and a root hash on the command line (`/usr/lib/live/boot/9989-prestium-verity.sh`), no plain-mount or root-hash-file fallback, no plain root, no `.fec`/`.fec.roots`/`.roothash`/`.roothash.p7s`/`*.module` next to the image; live-boot's initramfs hook stops sourcing `boot.conf` from the medium; the initramfs gets libcryptsetup (`/etc/initramfs-tools/hooks/prestium-verity`) |
| `0500-prestium-permissions` | restores owners/modes of every included file (git does not store them); copies The Lounge's packages for the Tor instance (root:thelounge-tor, read-only) |
| `0600-prestium-apparmor` | enforces all Prestium profiles (LibreWolf included) and compiles them to catch errors |
| `0700-prestium-i2pd` | i2pd's real config in `/var/lib/i2pd`, owned by uid 2000; `tunnels.conf.d` root:i2pd 0750 (written by root helpers only through `/usr/local/lib/prestium/safefile`); Prestium's dark theme inlined into the torrent web UI |
| `9980-prestium-vm-no-firmware` | quick_qubes: stops the build if any `firmware-*`, `*-microcode`, `iucode-tool` or `atmel-firmware` package is installed |
| `9990-prestium-cleanup` | final apt sources with signed-by keyrings, package list record, removes build-only files |

### How `config/includes.chroot/` was made

From the earlier Prestium root filesystem: every file not owned by a package, every package file whose
checksum differs from the package (`dpkg` md5sums and conffile hashes), and the package symlinks
Prestium replaced with real files (`/var/lib/i2pd/*.conf`). Generated files (alternatives, caches,
enablement symlinks, user database, locale data, `ld.so.cache`, `/etc/ssl/certs`) are left to the
packages and hooks. Package files Prestium deleted are handled by hooks (`dpkg-divert` for the gvfs
backends, removal of LibreWolf's packaged AppArmor profile and i2pd's init script). The large
third-party trees in `/opt` are not copied: they are downloaded and verified at build time.

## Updating third-party software

Tor Browser needs nothing: each build takes the newest release, verified by its signature with the
pinned Tor Browser key and held to `TB_MIN_VERSION` (see `thirdparty/versions.sh`; pin one release with
`PRESTIUM_TB_VERSION=<v> PRESTIUM_TB_SHA256=<sha>`). Neither does uBlock Origin: each build takes the
newest Mozilla-signed release from addons.mozilla.org (the build needs to reach addons.mozilla.org
and its download CDN; if AMO is down or anything fails verification, the build stops). If Mozilla
ever changes its add-on root, replace `thirdparty/keys/mozilla-amo-root.pem` with Firefox's
`security/manager/ssl/addons-public.pem` and update `ROOT_FPR` in `scripts/amo-latest.py`. Tor and LibreWolf come from their signed apt
repositories, also at the newest version. For everything else (i2pd too, which has no signature: `--repin`
only prints the SHA-256 GitHub served, so compare it with the asset digest on the release page first):

Edit the version in `thirdparty/versions.sh`, set its `*_SHA256` to `""`, run
`scripts/fetch-thirdparty.sh --repin` (it checks the signature and prints the new SHA-256), paste
the value in, rebuild. The Lounge is updated by regenerating `thirdparty/thelounge/package-lock.json`
(`npm install thelounge@<version> --package-lock-only` in `thirdparty/thelounge/`, with npm
11.10 or newer so `.npmrc`'s `min-release-age=7` is enforced: older npm ignores it and may pick a
release published minutes ago; review the lockfile diff), then set `IRC_FRAMEWORK_COMMIT` in `versions.sh` to the commit the
lockfile resolves irc-framework to, if it changed, set `IRC_FRAMEWORK_TAR_SHA256` to `""` and run
`--repin` for its new value. The build itself only runs `npm ci --ignore-scripts`, which installs
exactly the lockfile; Debian 13's apt npm (9.2.0) is enough, and npm 11 works too. irc-framework is a git dependency with no lockfile integrity, and
npm packing it would run its `prepare` script (babel + webpack, unpinned) even with `--ignore-scripts`.
So the build exports `IRC_FRAMEWORK_COMMIT` with `git archive --format=tar --prefix=package/ <commit>
$IRC_FRAMEWORK_FILES` (the files npm ships, per the package's `.npmignore`), checks the tarball against
`IRC_FRAMEWORK_TAR_SHA256`, and points a working copy of the lockfile at it
(`scripts/npm-local-tarball.py`: irc-framework's entry gets the `file:` tarball and its sha512, and
thelounge's `github:kiwiirc/irc-framework#<commit>` request becomes the locked version, so no git spec
is left; no package.json override, which npm 9.2.0 rejects with "Invalid comparator" and then
misreports as a missing package-lock.json). npm then runs with `--git=false`, and the image ships the committed package.json and lockfile. Every
installed irc-framework file is still checked against a git checkout of the commit, and `dist/` must
be absent. Hook 0200 then patches The Lounge in the image (no outbound fetches, lobby text for disconnected networks, a connecting line only when a connection starts, and a 320-second IRC ping timeout); those exact source strings must still be present, or the build stops. If upstream's file list changes, update `IRC_FRAMEWORK_FILES` with the commit. LibreWolf and Tor come from their
signed apt repositories and are always the newest at build time; i2pd is the `.deb` pinned in `thirdparty/versions.sh`.

## Tor Connection Assistant and DNS

See the "Tor Connection Assistant" section of [README.md](README.md).
