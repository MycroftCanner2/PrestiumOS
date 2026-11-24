# Building PrestiumOS (live-build)

PrestiumOS is built from scratch with Debian's **live-build**, the same tool Debian's own live
images use. Everything that makes it Prestium is in this repository: the package lists, the
customised files, the setup hooks and the pinned third-party downloads.

- Base: Debian 13 "trixie", amd64. Archive areas `main contrib non-free-firmware`, plus
  `trixie-updates`, `trixie-security` and `trixie-backports`.
- Kernel: Debian's trixie `linux-image-amd64` (the 6.12 line).
- Firmware: the full set, with `firmware-*` pinned to trixie-backports
  (`config/archives/prestium-firmware.pref.chroot`, priority 990), so `firmware-linux` is
  20260916 or newer. Extra firmware beyond the base set (network cards, TV tuners, Qualcomm, Samsung) is
  installed when the archive has it (`optional-packages.txt`).
- Boot: hybrid ISO, BIOS (isolinux) and UEFI, with **Secure Boot** through Debian's signed boot chain:
  `EFI/boot/bootx64.efi` is Debian's shim (signed by Microsoft), which loads
  `EFI/boot/grubx64.efi`, Debian's signed GRUB for removable media (`gcdx64.efi.signed` from
  `grub-efi-amd64-signed`), which loads Debian's signed kernel (`linux-image-amd64` from
  `linux-signed-amd64`). live-build sets this up (`--uefi-secure-boot enable`); hook 9040 stops the
  build when any of the three is not Debian's signed file (see Secure Boot below). Kernel command line: hardening options, the
  internal-disk (ahci/libata) blacklist with the patched live-boot fallback, `module.sig_enforce=1`,
  `lockdown=confidentiality` and AppArmor. The live image is mounted through dm-verity (root hash on the command line).

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
   (`thirdparty/keys/`) **and** the SHA-256 pinned in `thirdparty/versions.sh` (Tor Browser and Feather:
   the newest signed release at build time instead, see below: their signature, in a keyring holding only
   that publisher's key, is the trust anchor, with a pinned minimum version), and stages them in
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
3. runs `lb bootstrap`, `lb chroot`, `lb installer` and `lb binary` (the final apt sources go in between chroot and installer) and writes `Prestium-2.1-amd64.iso`, `Prestium-2.1-amd64.iso.sha256`, `SHA256SUMS`, the `.manifest`, the `.roothash` (the image's dm-verity root hash) and the `.packages` list.

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
includes `lockdown=confidentiality`, so the kernel is locked down (confidentiality, security review F-16)
even with Secure Boot off: unsigned modules, `/dev/mem`, kexec of unsigned kernels and hibernation are
refused, and so are the interfaces that let root read kernel memory (`/proc/kcore`, kprobes, BPF and
perf reads of kernel memory, tracefs). Prestium needs none of them; `module.sig_enforce=1` already
refused unsigned modules. Not signed and not checked by
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
| `config/package-lists/prestium-firmware.list.chroot` | firmware and CPU microcode (full coverage) |
| `config/package-lists/prestium-2.0.list.chroot` | 2.0 additions: PipeWire/WirePlumber audio, pasystray, the assistant's GTK bindings |
| `config/package-lists/live.list.chroot` | live-boot (no live-config: Prestium sets up its user itself) |
| `config/archives/` | build-time apt sources and keys: Tor Project, LibreWolf, each `signed-by` its own keyring in `/etc/apt/keyrings/` (the keys are in `config/apt-keyrings/`; build.sh installs them after `lb bootstrap`, never in `trusted.gpg.d`, where apt would trust them for Debian's sources too: review F-06); origin pins limiting each repo to its own packages; firmware pin to backports |
| `config/preseed/` | non-interactive answers (firmware licences, locale, keyboard, ferm) |
| `config/includes.chroot/` | Prestium's own files and the package files it changes, carried over from the earlier Prestium root filesystem as a diff against the packaged files (see below), plus the 2.0 changes |
| `config/includes.chroot/usr/share/prestium/build/` | build-only data used by the hooks (owners/modes manifest, enabled units, optional packages, final apt sources); deleted from the image |
| `config/hooks/live/*.hook.chroot` | setup steps, in order (below) |
| `config/hooks/live/9000-prestium-boot-menu.hook.binary` | boot menu labels |
| `config/hooks/live/9020-prestium-boot-lock.hook.binary` | locks the boot menus: GRUB superuser (PBKDF2 hash, exported for submenus, also in the EFI image's and per-platform grub.cfg; needs mtools), every entry `--unrestricted`; isolinux `allowoptions 0`; every kernel line checked against a banned list (shells, init, security modules, debug, persistence, findiso=) and must have exactly one `lockdown=confidentiality` (review F-16); findiso= and loopback.cfg removed |
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
| `scripts/translate-models.py` | Prestium Translate's models: checks Mozilla's content signature over the Remote Settings collection `main/translations-models`, then downloads each pinned model file named by a signed record and checks its size and SHA-256 (run by `fetch-thirdparty.sh`) |
| `build.sh` | the whole build |

### Hooks

| Hook | Does |
| --- | --- |
| `0001-prestium-build-dns` | build only: gives the hooks a resolver (Prestium's own `resolv.conf` has none) |
| `0005-prestium-i2pd` | installs i2pd from the staged GitHub `.deb` after checking it again against its pinned SHA-256, package name, version and architecture (apt takes its dependencies from Debian; Prestium's `/etc/i2pd` config files are kept); Debian's own i2pd is pinned out (`Pin-Priority: -1`) |
| `0010-prestium-optional-packages` | installs the earlier releases' dependency/recommends set (parity) and extra firmware, skipping names the archive no longer has |
| `0100-prestium-users` | `user` (1000, autologin, empty password until a session password is set), `i2pd` moved to uid/gid 2000, `thelounge`, `thelounge-tor` (2.1, IRC (Tor)), `onion-grater`, `prestium-htp`, `prestium-ptdns` (2.0); groups `autologin`, `i2ptorrents`, `prestium-localweb`; root locked |
| `0200-prestium-thirdparty` | Tor Browser in `/opt/tor-browser` (read-only, Prestium policies + the newest uBlock Origin, also for LibreWolf), Firefox in `/opt/firefox` (local pages only, no first-run screens), Node.js, The Lounge (+ offline patch, lobby text for networks that are not connected, connecting line only when a connection starts, 320s IRC ping timeout, and for the Tor instance every network through Tor's SOCKS port), Feather |
| `0210-prestium-translate` | Prestium Translate: checks the staged engine source tar and the six model files against `SHA256SUMS` (exactly those files, the pinned SHA-256 of each), builds the engine (bergamot-translator + `thirdparty/translate/prestium-translate-engine.cpp`, CPU only, x86-64 with SSE4.1, no BLAS) with cmake/g++/make installed for the build and purged again, allows it to link only the C/C++ runtime, installs it and the models read-only in `/usr/share/prestium-translate/`, checks the installed models again and translates a test sentence both ways; any failure stops the build |
| `0400-prestium-system` | the exact set of enabled/masked units carried over from earlier releases + PipeWire user units, gvfs network backends diverted, alternatives (iptables/ip6tables pinned to legacy, the backend ferm and `prestium-firewall-early` share), CA list (emSign roots distrusted), dconf, plymouth theme, locale, version strings |
| `0405-prestium-verity` | live-boot mounts the image only through dm-verity: every image needs its hash tree and a root hash on the command line (`/usr/lib/live/boot/9989-prestium-verity.sh`), no plain-mount or root-hash-file fallback, no plain root, no `.fec`/`.fec.roots`/`.roothash`/`.roothash.p7s`/`*.module` next to the image; live-boot's initramfs hook stops sourcing `boot.conf` from the medium; the initramfs gets libcryptsetup (`/etc/initramfs-tools/hooks/prestium-verity`) |
| `0500-prestium-permissions` | restores owners/modes of every included file (git does not store them); copies The Lounge's packages for the Tor instance (root:thelounge-tor, read-only) |
| `0600-prestium-apparmor` | enforces all Prestium profiles (LibreWolf included) and compiles them to catch errors |
| `0625-prestium-app-confine` | every start of a confined desktop application goes through `app-confine` (shims in `/usr/local/bin`, desktop-file, autostart and D-Bus activation overrides; the build stops on anything it can't redirect); checks every per-application bus policy (`app-confine --check`), the portals and setuid `fusermount3`, links the GTK portal back end into Prestium's back-end directory, and refuses a `/.flatpak-info` in the image (security review F-01) |
| `0700-prestium-i2pd` | i2pd's real config in `/var/lib/i2pd`, owned by uid 2000; `tunnels.conf.d` root:i2pd 0750 (written by root helpers only through `/usr/local/lib/prestium/safefile`); Prestium's dark theme inlined into the torrent web UI |
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
`PRESTIUM_TB_VERSION=<v> PRESTIUM_TB_SHA256=<sha>`). Feather works the same way (`scripts/feather-latest.sh`):
each build asks GitHub for feather-wallet/feather's latest release (the releases API, or the
`/releases/latest` redirect if the API can't be read; never a draft or prerelease, and the tag must be a
plain version such as `2.9.1`), downloads `feather-<version>-linux.zip` and its `.asc` from
`github.com/feather-wallet/feather/releases/download/<version>/`, and requires a valid signature by
`FEATHER_KEY` (a keyring holding only `thirdparty/keys/feather.asc`). No SHA-256 can be pinned for a
release that isn't out yet, so that signature is Feather's trust anchor; `FEATHER_MIN_VERSION` is a floor
(an older, still validly signed release stops the build; raise it, never lower it), and the signed zip's
only entry must be `feather-<that version>`. The build log (`OK FEATHER <sha> (Feather <v>, ...)`) and the
image manifest record the version and SHA-256 shipped. Pin one release with
`PRESTIUM_FEATHER_VERSION=<v> PRESTIUM_FEATHER_SHA256=<sha>` (or in `thirdparty/versions.sh`); the
signature is checked then too. If Feather ever changes its signing key, replace `thirdparty/keys/feather.asc`
and `FEATHER_KEY`. Neither does uBlock Origin: each build takes the
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

Prestium Translate's engine and models are pinned in `thirdparty/versions.sh`. bergamot-translator publishes
no release or signature and GitHub's tarballs leave out its submodules, so `fetch-thirdparty.sh` clones
`BERGAMOT_COMMIT`, checks out the submodules in `BERGAMOT_MODULES` at the commits the parent records,
exports each with `git archive` into one tar and checks it against `BERGAMOT_TAR_SHA256` (the pinned commit
and that SHA-256 are the trust anchor). The models are Mozilla's Firefox Translations models: Firefox gets
them from the Remote Settings collection `main/translations-models`, whose records carry Mozilla's content
signature. `scripts/translate-models.py` checks that signature (the certificate chain to the pinned AMO root
`thirdparty/keys/mozilla-amo-root.pem`, code-signing use, the signer name
`remote-settings.content-signature.mozilla.org`, then the ECDSA P-384 signature over the canonical
collection), picks the signed record for each file of `TR_ENRU_VERSION` and `TR_RUEN_VERSION`, downloads
it over HTTPS and checks its size and SHA-256 against the record; `fetch-thirdparty.sh` then compares
each SHA-256 with `TR_*_SHA256`. To update: change the commit or version, set the matching SHA-256 values
to `""` and run `--repin`. The build needs to reach github.com, firefox.settings.services.mozilla.com,
content-signature-2.cdn.mozilla.net and firefox-settings-attachments.cdn.mozilla.net.

### Release checklist (security review F-12, F-13)

"Newest at build time" trusts a publisher's signature plus a version floor: whoever controls the answer
of the Tor Project's update service or of GitHub's API can choose any validly signed release at or above
the floor (a controlled rollback), and two builds of one commit can ship different versions. Before each
Prestium release:

1. Raise `TB_MIN_VERSION` and `FEATHER_MIN_VERSION` in `thirdparty/versions.sh` to the versions current
   on the publishers' own pages that day (never lower them). For a release build, pin both with
   `PRESTIUM_TB_VERSION`/`PRESTIUM_TB_SHA256` and `PRESTIUM_FEATHER_VERSION`/`PRESTIUM_FEATHER_SHA256`,
   after checking the versions against a second source (torproject.org's download page, the Feather
   site), so the release is reproducible from its commit.
2. Check that the build log's `OK TB`/`OK FEATHER` lines and the image manifest name the versions you expect.
3. i2pd has no signature, only the SHA-256 in `versions.sh`. When re-pinning it: compare the SHA-256
   that `--repin` prints with the asset digest on PurpleI2P's GitHub release page and, if you can, with a
   second download (another network or mirror); inspect its maintainer scripts, which run as root in the
   chroot (`dpkg-deb -e i2pd_*.deb ctl && cat ctl/*inst ctl/*rm`), and diff them against the previous
   version; and add a CHANGELOG line naming the version and SHA-256.
4. Sign `SHA256SUMS` with `scripts/sign-release.sh` and publish the full fingerprint in README.md
   (*Verify a download*, F-11).

### Kernel: why Debian 13's 6.12 line stays (security review follow-up, November 2026)

trixie-backports has newer signed kernels (on 23 November 2026, `linux-image-amd64` 7.3.4-1~bpo13+1,
from `linux-signed-amd64`, its vmlinuz signed by "Debian Secure Boot Signer 2022 - linux" under the
Debian Secure Boot CA that Debian's shim trusts). It is not used, because the reason to switch, AppArmor
mediating `connect()` on Unix socket paths (kernel 6.17 and later), needs AppArmor 5 userspace and
profiles written for `abi/5.0`; Debian 13 has AppArmor 4.1.0 and trixie-backports has no newer one.
AppArmor 4.1 doesn't support the upstream 6.17+ Unix mediation, and its downgrade of network and Unix
rules on those kernels has known bugs (unix sockets refused for profiles with `network,`, `deny unix`
ignored; apparmor issues #561, #564). The switch would add that risk without the protection.
`app-confine` (F-01, F-05) hides the session bus, the broker and other apps' sockets by mount namespace
instead, which works on 6.12. Revisit when AppArmor 5 reaches trixie(-backports): the backports kernel
packages also moved the kernel to `/usr/lib/modules/<version>/vmlinuz` (`linux-binary-*`), copied to
`/boot` only by `linux-base` 4.16 or later, so hook 9040's check that `/boot/vmlinuz-*` belongs to a signed
`linux-image-*` package must learn that layout too.

### Confined applications: per-application session bus and portals (security review F-01)

`/usr/local/lib/prestium/app-confine` starts each AppArmor-confined desktop application (its table:
Gajim, Claws Mail, Kleopatra, KeePassXC, LibreOffice, OnionShare, Feather, FeatherPad, Evince, VLC,
File Roller, Loupe, Metadata Cleaner, mat2, Audacity, Prestium Translate, Prestium Keys) in its own
mount namespace. What it may reach on the session bus is its policy file in
`config/includes.chroot/usr/share/prestium/app-confine/<policy>.policy`: an allowlist, default deny,
for an `xdg-dbus-proxy` run for that one start. The directives (`talk`, `own`, `call`, `broadcast`,
`include`, `documents`, `env`, `own-if`, `bus none`) and their rules are in app-confine's header; it
refuses (the application doesn't start, the build stops in hook 0625) any name of systemd, logind,
dconf, the bus driver, Flatpak, a portal back end, the keyring or Prestium itself, any `talk` other
than notifications and the tray, and any portal call outside its fixed list. To change what an
application may do, edit its policy file and run `tests/test_app_confine_policy.py`, which also holds
the expected matrix (which applications get no bus, the file chooser, links, the Qt portal plugin).

The proxy runs outside the application's namespace, in a small user and mount namespace of its own
whose root holds `/usr`, `/etc`, the session bus socket, app-confine's socket directory and a
`/.flatpak-info` naming the application (`org.prestium.Confined.<policy>`). xdg-desktop-portal identifies
a caller by reading `/proc/<pid>/root/.flatpak-info` of the bus peer, which is the proxy, so it treats the
application as sandboxed: its file chooser hands the picked file over through the document portal
(`/run/user/<uid>/doc/by-app/<app id>`, bound at `/run/user/<uid>/doc` in the application's view;
`abstractions/prestium-app-documents` allows that path only to the profiles of the applications with
`documents`), not by widening an AppArmor profile. app-confine writes
`$XDG_RUNTIME_DIR/.flatpak/<instance>/bwrapinfo.json` (the application's pid, for the portal's checks)
and removes it when the application exits. The application's own namespace has no `/.flatpak-info`, so
GLib, GTK and Qt don't switch into Flatpak mode; GTK 4 uses the portals it can see, Qt uses them through
`QT_QPA_PLATFORMTHEME=xdgdesktopportal` (`env qt-portal`), GTK 3 applications keep their own dialogs
(`GTK_USE_PORTAL` would also send GIO's file launches to the portal's `OpenFile`, which no policy
allows). `prestium.xdg-dbus-proxy` is the proxy's AppArmor profile (no network, runs nothing).

The portal side: `xdg-desktop-portal`, `xdg-desktop-portal-gtk` and the Qt 5 and Qt 6 portal plugins are
in the package list (`-wlr` is not: no screen sharing). Its systemd drop-in
(`etc/systemd/user/xdg-desktop-portal.service.d/prestium.conf`) makes it read back ends only from
`usr/share/prestium/portal/portals` (`portals.conf`: no back end by default; GTK's for the file chooser,
the application chooser and the settings) and look link handlers up only in
`usr/share/prestium/portal/open`, whose one handler, `usr/local/lib/prestium/portal-open`, opens http and
https in Tor Browser and mailto in Claws Mail (address, subject, body, cc, bcc only) and refuses anything
else. Desktop files and `mimeapps.list` in the home are never used by the portal.

Not reachable, on purpose: the system bus (no policy needs it, logind included); dconf writes
(`ca.desrt.dconf`: xdg-dbus-proxy can't limit them to one application's keys, and a write could change
any application's or the desktop's settings, the GIO proxy settings included; a shared keyfile backend
has the same problem); screen-lock signals for KeePassXC (labwc has no ScreenSaver service). Checks:
`tests/test_app_confine_policy.py` (static), `tests/test_app_confine_portal.py` (a private bus with the
real portals and a fake back end: identity, document portal, links, refusals; skips without the
portals), `tests/test_app_confine.py` and `tests/test_app_confine_hook.sh`.

## Tor Connection Assistant and DNS

See the "Tor Connection Assistant" section of [README.md](README.md).
