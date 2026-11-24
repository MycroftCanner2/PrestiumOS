# Changelog

## quick_qubes branch: Prestium 2.1 for VMs and Qubes OS

A variant of 2.1 that runs as a virtual machine guest (KVM/QEMU, VirtualBox, VMware) or as a Qubes OS
standalone HVM booting the ISO. It builds `Prestium-2.1-quick_qubes-amd64.iso`. The hypervisor owns
the hardware, so bare-metal support is left out. The security layers are unchanged: firewall, AppArmor,
sandboxes, Tor/I2P isolation, dm-verity, lockdown and the kernel command line with its guard. How to
run it is in the README's quick_qubes section.

### Removed
- **Bare-metal firmware and CPU microcode:** the `prestium-firmware` package list (`firmware-*`,
  `amd64-microcode`, `intel-microcode`, `iucode-tool`, `atmel-firmware`, `wireless-regdb`), the
  trixie-backports firmware pin (`config/archives/prestium-firmware.pref.chroot`,
  `/etc/apt/preferences.d/prestium`), `firmware-sof-signed`, the extra firmware in
  `optional-packages.txt`, the firmware licence preseeds and the `non-free-firmware` archive area.
  `--firmware-chroot`/`--firmware-binary` stay `false`. **New hook 9980** stops the build if a firmware
  or microcode package is installed anyway.
- **Wi-Fi** (`wpasupplicant`, `wireless-tools`), **mobile broadband and tethering** (`modemmanager`,
  `ppp`, `usb-modeswitch`, `usb-modeswitch-data`, `usbmuxd`), with their units and D-Bus aliases.
- **Graphics tablets** (`xserver-xorg-input-wacom`, `libwacom-bin`) and the **real-GPU X drivers**
  (`xserver-xorg-video-all`, `-amdgpu`, `-ati`, `-intel`, `-nouveau`, `-radeon`). QXL, VMware, fbdev,
  VESA and modesetting stay for virtual GPUs.
- `xinput`, and the System menu's **Brightness** and **Touchpad** entries (no backlight or touchpad in a
  VM; the tools stay, hidden).

### Changed
- **Name:** the ISO is `Prestium-2.1-quick_qubes-amd64.iso`, os-release has
  `VARIANT_ID=quick_qubes`, and hook 9000 labels the boot entries "Prestium 2.1 quick_qubes". Only the
  labels changed: the command lines, `cmdline.policy` and hook 9030 are the same as on `main`.
- **VM notice:** "running in a virtual machine" is now information (normal urgency, the usual timeout,
  no warning icon), since the VM is the expected environment. It still says what the host can see.
- **VM network diagnosis (after 10 minutes):** now knows Xen/Qubes OS. It covers the static address a
  Qubes HVM without Qubes tools needs (no DHCP; the IP and gateway from the qube's Settings or
  `qvm-ls -n`, no DNS), the Qubes clock (dom0's clock qube), and I2P failing behind a sys-whonix or VPN
  net qube.
- **Xen paravirtual network cards keep the host's MAC address.** Qubes OS pins the address it assigned
  in the net qube, so a spoofed one cut the network, and in Qubes that address never leaves the
  computer. `prestium-spoof-mac` and `prestium-mac-guard` (`host_assigned_mac()`) skip cards on the
  `xen` bus. Emulated cards (e1000, rtl8139, virtio-net, vmxnet3) are still spoofed and guarded, and
  connection settings are still checked for every card.
- **Faster boot from a virtual CD:** live-boot loads the SATA/IDE optical drivers after 1 second instead
  of 8 when the CPU has the hypervisor flag. Real hardware keeps the 8-second USB-first wait.

### Kept on purpose
- No guest agents (`qemu-guest-agent`, `spice-vdagent`, VirtualBox Guest Additions, VMware Tools, Qubes
  tools). They are host-to-guest channels (clipboard, files, commands), and the test suite checks that
  none is listed.
- MAC spoofing and the MAC guard on emulated cards, the boot-medium watchdog (ejecting the virtual CD
  powers the VM off), Secure Boot (works in UEFI VMs; harmless in Qubes, which boots SeaBIOS), the
  internal-disk blacklist, the shutdown memory wipe, time over Tor, PipeWire audio, `pcscd`, the
  on-screen keyboard and the camera/microphone-off entry.

### Docs and tests
- README: a quick_qubes section covering what changed and why, plus how to run it in KVM/QEMU,
  VirtualBox, VMware and Qubes OS (standalone HVM, `kernel=''`, `maxmem=0`, `--cdrom`, static
  address, sys-firewall rather than sys-whonix). The Download, Verify and Repository layout sections
  now point to `Prestium-2.1-amd64.iso.torrent`; the 2.0 torrent was deleted on `main`. BUILDING.md
  covers the firmware-free package set, the archive areas, the output name and hook 9980.
- New `tests/test_quick_qubes.sh`. `test_vm_check.sh`, `test_mac_spoof_udev.sh`,
  `test_mac_guard_policy.py` and `test_mac_guard_dbus.py` are updated for the changes above.
## Unreleased: fixes from the November 2026 security review

Each entry names the review finding (F-xx) it fixes.

- **PRE-5 (2): `build.sh --resume` (or a second run without `--clean`) threw the built chroot away.**
  `lb bootstrap`'s cache step puts `cache/bootstrap` back over `chroot/` whenever that cache exists and
  its "restore" stage file does not, and a fresh build never writes that file. The chroot stage's stage
  files then skipped the package install, so the image was the bare Debian bootstrap (found resuming the
  failed build above: `lb binary` stopped at `binary_linux-image`, no kernel). build.sh now marks the
  restore done when the bootstrap stage is complete and the chroot exists. Test:
  `tests/test_build_resume_bootstrap.sh`.

- **PRE-5: the build stopped after the chroot stage ("Failed to parse keyring /etc/apt/keyrings/prestium-*.gpg").**
  `lb installer` and `lb binary` build their tool chroot from a fresh copy of live-build's bootstrap cache
  (`cache/bootstrap`) and run `chroot_archives chroot install` there, which copies the build-time lists
  (`config/archives/*.list.chroot`) and runs `apt-get update`. F-06 put the Tor Project and LibreWolf
  keyrings only in the image chroot, so apt refused both repositories as unsigned in that copy. build.sh now
  installs the same pinned keyrings in `cache/bootstrap/etc/apt/keyrings` too (on every run, so
  `--resume` repairs an older cache) and checks for them before `lb installer`. The keys stay scoped
  with signed-by, none goes to `trusted.gpg.d` (build.sh checks again after `lb installer`), and the image's
  final lists are unchanged. Test: `tests/test_apt_keyrings.sh` runs build.sh's keyring block on a stand-in
  tree, makes the tool chroots the way live-build does, and checks every signed-by file in each one.

- **Launch check: every menu application opens, three start-up errors fixed.** All 55 menu, panel and
  desktop entries were started the way the menu does in a booted image chroot (labwc session, the
  Wayland broker, PipeWire, the portals, app-confine), with a window check and screenshot each, and every
  file each one opened was compared with its compiled AppArmor profile (denials replayed as EACCES to see
  which ones matter). All open. Fixed:
  - *Gajim:* its profile's rule for GStreamer's plugin scanner had the wrong path (Debian installs it in
    `/usr/lib/<multiarch>/gstreamer1.0/gstreamer-1.0/`), so GStreamer loaded every plugin inside Gajim
    itself instead; that path is now allowed (ix, nothing else there).
  - *Local Firefox (I2P console, I2P Torrents, IRC pages):* Firefox's Wayland proxy needs a socket in
    `$XDG_RUNTIME_DIR` its profile does not allow and printed a `bind() error` at every start;
    `prestium-localfox` now turns the proxy off (`MOZ_DISABLE_WAYLAND_PROXY=1`, as the browser sandbox
    already does). The profile is unchanged.
  - *Metadata Cleaner:* GTK's file chooser asked each GVfs volume monitor, D-Bus services app-confine keeps
    off its bus, and printed five D-Bus errors at every start; its policy now sets `env gio-local`
    (`GVFS_REMOTE_VOLUME_MONITOR_IGNORE=1`: local mounts only). `org.gtk.vfs.*` stays forbidden.
  Test: `tests/test_app_launch_check.py`.

- **Gajim stores account passwords in its own settings, never in GNOME Keyring.** With `use_keyring` on
  (Gajim's default) Gajim could not save a password at all, since app-confine keeps
  `org.freedesktop.secrets` out of its bus, and asked for it at every start. `/etc/gajim/app-overrides.json`
  (`{"use_keyring": false}`, Gajim's own override mechanism) now applies to every profile at each start,
  new and existing, without rewriting their other settings; Gajim's profile may read it. A saved password
  is in `~/.config/gajim/settings.sqlite` (account settings, not encrypted; the other confined apps' profiles
  don't allow reading it, unconfined programs of the desktop user can). Test: `tests/test_gajim_no_keyring.py`
  (Gajim's own settings and password code on a profile with `use_keyring` on).

- **Compatibility audit of the F-01/F-05 namespaces: passphrase prompts, Qt tray icons, later volumes and
  Gajim's links work again.** A second review ran the applications under app-confine on a test system:
  - *GnuPG passphrase prompts.* gpg passes the application's `DBUS_SESSION_BUS_ADDRESS`
    (`$XDG_RUNTIME_DIR/prestium-bus`, which existed only inside the namespace) to gpg-agent for
    pinentry-gnome3. Claws Mail and Kleopatra use the session's agent, outside every namespace, so signing,
    decrypting with a protected key or creating a key with a passphrase failed with "pinentry error".
    app-confine now also links `prestium-bus` to `bus` in the real runtime directory (the pinentry
    profile may read it). Gajim and the Gajim keys tool run their own agent inside: their filtered bus
    may now talk to GCR's prompter only (`pinentry.inc`: `talk org.gnome.keyring.SystemPrompter`; the
    keyring and `org.freedesktop.secrets` stay refused, and no other policy may name the prompter). The
    keys tool therefore has a bus again (that one name), so keys with a passphrase can be made, backed up
    and edited.
  - *Qt 5 tray icons (VLC, KeePassXC).* Qt 5 registers `org.kde.StatusNotifierItem-<pid>-<n>`, which no
    policy allowed, so the icon was missing (KeePassXC set to start minimised to the tray had no window
    and no icon). `tray.inc` adds `tray-items`: the proxy, now started after the application's process
    exists, may own those names for that process id only (n = 1..16).
  - *Volumes mounted after an application started* (USB stick, VeraCrypt) were invisible in it: the
    namespace's mounts are now slaves of the host's (`MS_SLAVE`, still nothing propagates back).
  - *Links in Gajim did nothing.* Gajim opens links with GIO, which outside Flatpak does not use the
    OpenURI portal; its only web handler was the I2P Browser, which Gajim's profile may not start, and the
    profile could not read the entry or run GIO's `gio-launch-desktop`. `env links-tor` makes Tor Browser
    GIO's default for Gajim (`/usr/share/prestium/links-tor/mimeapps.list`), and the profile allows that
    one entry and the wrapper.
  Not changed (security tradeoffs): GNOME Keyring stays out of Gajim's bus (the Secret Service cannot be
  filtered per item; see the next entry), KeePassXC's SSH agent integration (no `SSH_AUTH_SOCK`), dconf
  writes, the accessibility bus.
  Tests: `tests/test_app_confine_compat.py` (policy refusals, a real `xdg-dbus-proxy` and gpg-agent
  with a stand-in prompter, mount propagation, GIO's link handler), `tests/test_app_confine_policy.py`.

- **F-03: DHCP no longer sends the hostname.** NetworkManager sent `prestium` to every DHCP server
  (DHCPv4 option 12/FQDN, DHCPv6), naming Prestium on the local network. The new global defaults in
  `NetworkManager/conf.d/45-prestium-dhcp.conf` set `ipv4.dhcp-send-hostname=false` and
  `ipv6.dhcp-send-hostname=false`, pin NetworkManager's internal DHCP client, and derive the client
  identifiers from the (random, per-boot) MAC address only (`dhcp-client-id=mac`, `dhcp-iaid=mac`,
  `dhcp-duid=ll`). Hook 0400 also comments out `send host-name` in dhclient.conf and fails the build if
  either setting is missing. Test: `tests/test_nm_dhcp_privacy.sh` (also checks NetworkManager's own
  merged configuration when it is installed).

- **F-02: Gajim's GnuPG no longer gets Kleopatra's agent.** The `gpg` child profiles of `gajim` and
  `prestium_gajim_keys` allowed every socket under `$XDG_RUNTIME_DIR/gnupg/`, including the sockets of
  `~/.gnupg`'s agent (Kleopatra's and Claws Mail's secret keys). They now allow only their own
  `gnupg/d.<hash>/` directory and deny `gnupg/S.*`. Because the 6.12 kernel does not mediate
  `connect()` by socket path, the effective fix is app-confine (F-01): Gajim and the Gajim keys tool
  get their own `$XDG_RUNTIME_DIR`, in which `~/.gnupg`'s agent does not exist. Tests:
  `test_apparmor_gajim.sh` and `test_apparmor_gajim_keys.sh` (compiled-profile checks).

- **F-04: kernel pointers are hashed again.** `slub_debug=FZP` made the 6.12 kernel switch off
  pointer hashing (`no_hash_pointers` is forced by slub_debug before 6.17), so `%p` printed real kernel
  addresses. It is gone from APPEND, `cmdline.policy` and `config/binary`. Its hardening is still covered
  by `slab_nomerge`, `init_on_alloc=1`, `init_on_free=1` and `page_poison=1`; the slab consistency checks
  (`F`) and red zones (`Z`) are lost. Test: `tests/test_cmdline_hardening.sh`.
- **F-15: all CPU mitigations, SMT off.** `mitigations=auto,nosmt` is added to APPEND and required by
  `cmdline.policy` (the per-issue options such as `mds=full,nosmt` stay), so every mitigation the kernel
  knows is on and SMT is disabled for all the issues that need it. On CPUs with SMT this halves the
  logical CPU count, as `mds=full,nosmt` already did on affected Intel CPUs. Test:
  `tests/test_cmdline_hardening.sh`.

- **F-06: third-party apt keys are trusted for their own repository only.** live-build put the Tor
  Project and LibreWolf build-time keys (`config/archives/*.key.chroot`) in `/etc/apt/trusted.gpg.d`,
  where apt trusts a key for every source, Debian's included, during the build. The keys moved to
  `config/apt-keyrings/`; `build.sh` installs them in `/etc/apt/keyrings/` after `lb bootstrap`, the
  build-time lists name them with `signed-by`, and the build stops if a `.key` file reappears in
  `config/archives` or a Prestium key lands in `trusted.gpg.d`. The final image's sources were already
  scoped (`/usr/share/keyrings`). Test: `tests/test_apt_keyrings.sh` (also pins both fingerprints).

- **F-01: confined applications no longer reach the session bus, the system bus or the Wayland
  broker.** On the 6.12 kernel AppArmor does not mediate `connect()` on a Unix socket path and enforces
  no D-Bus rules, so the `deny` rules for `/run/user/*/bus`, the system bus and
  `/run/prestium-wl/broker` did not stop a confined application from, for example, asking
  `systemd --user` (StartTransientUnit) to run any program outside every profile. The new
  `/usr/local/lib/prestium/app-confine` starts Gajim, the Gajim keys tool, Claws Mail, Kleopatra,
  KeePassXC, LibreOffice, OnionShare, Feather, FeatherPad, Evince, VLC, File Roller, Loupe, Metadata
  Cleaner, mat2, Prestium Translate and Audacity in a user and mount namespace of their own (no
  bubblewrap and no `no_new_privs`, so every AppArmor profile and its Px/Cx transitions, such as
  gpg and pinentry, work as before; the same user and group ids; no capabilities). In it:
  `/run/user/<uid>` is the application group's own runtime directory with only PulseAudio's and
  PipeWire's sockets and dconf's cache bound in (and the real `gnupg/` for Kleopatra and Claws Mail;
  Gajim's is private: F-02); `/run/dbus` and `/run/prestium-wl` are empty except the restricted Wayland
  socket; the session bus is either absent (Gajim keys tool, mat2, Translate, Audacity, onionshare-cli)
  or an `xdg-dbus-proxy --filter` that lets the application own its own names and talk to
  notifications and the panel's tray, nothing else (no systemd, portals, dconf writes or other
  applications). Every way to start one goes through it: `/usr/local/bin` shims (hook 0625) first in
  PATH, `prestium-run` for the programs that live in `/usr/local/bin`, `claws-mail-i2p`, the Audacity
  shim (hook 0620), and overrides of desktop files and D-Bus activation files that name a real path;
  the build stops if anything is left that starts one directly. A second Audacity start still joins
  the first (audacity-ns now also hands over and checks the mount namespace). Tests:
  `tests/test_app_confine.py` (table vs. profiles, launch paths, and a functional run in a real
  namespace with a private bus, fake system bus and broker), `tests/test_app_confine_hook.sh`,
  `tests/test_audacity_netns.sh`. Needs a live-boot check of every application (see the review page).
- **F-05: a private `/tmp` and `/dev/shm` for each confined application.** app-confine gives each
  application group its own `/tmp` (`/tmp/.prestium-confine-<uid>/<group>`, shared by its own
  instances for single-instance sockets, with Xwayland's `/tmp/.X11-unix` bound in read-only) and a new
  `/dev/shm` for each start, so the profiles' `owner /tmp/** rwk` and `owner /dev/shm/** rwk` rules
  no longer reach other applications' files (the Gajim keys tool's keyring copies, LibreOffice and
  KeePassXC sockets, Feather's temporary files).

- **Clock and I2P reseed need a confirmation at the screen (security review F-07).** The NOPASSWD
  sudo rules for `prestium-set-clock` and `prestium-i2p-reseed` are gone: any program of the user
  could run them silently (move the clock within the build-date bounds, or bootstrap i2pd from a
  .su3 file it chose). Both now go through the Wayland broker like Tor's and I2P's settings: a dialog
  on the compositor's full socket (accessibility off) shows the exact time, or the file, and who asked;
  only after *Set clock* / *Reseed* does the broker run the helper as root in a transient service.
  `sudo prestium-set-clock` is replaced by `prestium-wl set-clock YYYY-MM-DD HH:MM`; the I2P reseed
  button works as before, with one extra confirmation. The helpers refuse to run without root and no
  longer re-run themselves through sudo. Tests: `tests/test_broker_confirm_f07.py`, updated
  `test_set_clock.sh` and `test_i2p_reseed.py`.

- **The screen lock asks for its password at the start of the session (security review F-10).**
  Without a session password the idle lock and the lock before suspend could only show a
  notification, so a laptop left alone or closed came back unlocked. The broker now opens the
  password dialog once when the session starts; *Not now* skips it (Lock Screen… or Super+L asks
  again, and the automatic locks keep notifying). Test: `tests/test_session_lock.sh`.

- **The README points at the 2.1 torrent and says what is verifiable (security review F-11).** It
  named `Prestium-2.0-amd64.iso.torrent`, which is no longer in the repository, while
  `Prestium-2.1-amd64.iso.torrent` was undocumented. *Verify a download* now has a *Release key
  fingerprint* line, marked *not yet published* until the key holder publishes the full fingerprint
  with `SHA256SUMS.asc` (`scripts/sign-release.sh`); until then the torrent is described as unverified.
  Test: `tests/test_readme_release.sh`.

- **Kernel lockdown is confidentiality, not integrity (security review F-16).** `lockdown=confidentiality`
  replaces `lockdown=integrity` on every live entry (`auto/config`, `config/binary`, the command-line
  policy and hook 9020, which accepts no other value). On top of integrity's refusals it stops root
  reading kernel memory (`/proc/kcore`, kprobes, BPF and perf reads of kernel memory, tracefs), which
  protects for example the keys of unlocked volumes after a root compromise. Prestium has no swap or
  hibernation and uses none of these. The safety notifier now raises *Protection NOT active* when the
  kernel is locked down only to integrity. Tests: `test_boot_lock.sh`, `test_boot_cmdline_guard.sh`,
  `test_secure_boot.sh`, `test_safety_notify_apparmor.sh`.

- **Release checklist and documented limits (security review F-12, F-13, F-14).** BUILDING.md has a
  *Release checklist*: raise `TB_MIN_VERSION` and `FEATHER_MIN_VERSION` each release and pin both for
  release builds after a second-source check (the "newest at build time" floor otherwise allows a
  signed rollback chosen by whoever answers the update query); re-pin i2pd only after comparing
  GitHub's asset digest, ideally a second download, and reading its maintainer scripts. Known limit
  (F-14): options the kernel consumes itself (`rdinit=`, `init=`) act before the initramfs
  command-line guard; hook 9020 bans them at build time and getting one onto the command line needs
  the GRUB password or write access to the stick (the USB-writer limit; the fix is a signed UKI).
  BUILDING.md also records why the kernel stays on Debian 13's 6.12 line: trixie-backports' signed
  7.3 kernel would need AppArmor 5 (not in trixie) for Unix-socket path mediation.
  Test: `tests/test_release_docs.sh`.

- **quick_qubes warns on real hardware (security review F-08, quick_qubes only).** This build has no
  CPU microcode or hardware firmware, which is right in a VM (the hypervisor loads the microcode) but
  leaves a real computer without its CPU security fixes. `prestium-bare-metal.service`
  (`ConditionVirtualization=!vm`, root without capabilities, writes only the safety-flag directory)
  raises a *Protection NOT active* warning for the session when no VM is found, and the boot menu
  labels read "Prestium 2.1 quick_qubes, VM only". Test: `tests/test_quick_qubes_bare_metal.sh`.

- **The Xen MAC exemption is limited to Qubes OS (security review F-09, quick_qubes only).** The MAC
  spoofing script and the MAC guard kept the host-assigned address of every Xen paravirtual card; on
  XCP-ng or another Xen host with bridged networking that persistent address reached the LAN and linked
  sessions. They now keep it only when it is in Qubes OS's range (`00:16:3e:5e:6c:xx`); any other Xen card
  is spoofed and guarded like an emulated card. A qube with a custom `mac` loses its network unless
  started with *MAC address spoofing off*. Tests: `test_mac_spoof_udev.sh`, `test_mac_guard_policy.py`,
  `test_mac_guard_dbus.py`.
- **F-01 (follow-up): each confined application gets its own filtered session bus, and the desktop
  portal's file chooser and links come back.** app-confine's bus permissions moved from a table in the
  script to one policy file per application (`/usr/share/prestium/app-confine/<policy>.policy`, an
  allowlist for `xdg-dbus-proxy`, default deny; `bus none` for no bus at all). app-confine refuses any
  policy that names systemd, logind, dconf, the bus driver, Flatpak, a portal back end, the keyring or
  Prestium's own services, talks to anything but notifications and the tray, or calls a portal method
  outside a fixed list (FileChooser OpenFile/SaveFile/SaveFiles, OpenURI.OpenURI, Settings, Request,
  `Properties.Get`, the document portal's GetMountPoint); hook 0625 checks every policy at build time.
  Never allowed: OpenURI's OpenFile and OpenDirectory, Background, Camera, ScreenCast, RemoteDesktop,
  Screenshot, Inhibit, Print, Email, Trash, DynamicLauncher, Secret, FileTransfer, `Properties.Set`,
  `Documents.Add`. Per application: Gajim (GTK 4) gets the file chooser and links; OnionShare,
  FeatherPad and VLC (Qt, through `qt5/qt6-xdgdesktopportal-platformtheme`) the file chooser; Claws Mail,
  Kleopatra, KeePassXC, LibreOffice, Feather, Evince, File Roller, Loupe, Metadata Cleaner and kwatchgnupg
  keep notifications, the tray and their own names (single instance) as before; KeePassXC may own
  `org.freedesktop.secrets` only while its own Secret Service setting is on; the Gajim keys tool, mat2,
  onionshare-cli, Prestium Translate and Audacity get no bus. Each proxy now runs in a small user and
  mount namespace of its own (its own root: `/usr`, `/etc`, the bus socket, its socket directory and a
  `/.flatpak-info` naming the application), so xdg-desktop-portal treats the application as sandboxed
  (`org.prestium.Confined.<policy>`) and hands a picked file over through the document portal
  (`/run/user/<uid>/doc/by-app/<app id>`, bound into the application's view; AppArmor
  `abstractions/prestium-app-documents`, only for those four applications) instead of a path; the
  application itself sees no `/.flatpak-info`. New AppArmor profile for xdg-dbus-proxy
  (`prestium.xdg-dbus-proxy`: no network, runs nothing). New packages: `xdg-desktop-portal`,
  `xdg-desktop-portal-gtk`, `qt5-xdgdesktopportal-platformtheme`, `qt6-xdgdesktopportal-platformtheme`.
  The portal reads back ends only from `/usr/share/prestium/portal/portals` (`portals.conf`: none by
  default; GTK's for the file chooser, the application chooser and the settings) and link handlers only
  from `/usr/share/prestium/portal/open` (systemd drop-in), whose one handler, `portal-open`, opens http
  and https in Tor Browser (through `prestium-run`) and mailto in Claws Mail (address, subject, body, cc,
  bcc: never `attach`), and refuses everything else; a desktop file or `mimeapps.list` in the home is
  never used. Still blocked, on purpose: the system bus, dconf writes (no per-key filter in
  xdg-dbus-proxy), the screen-lock signals KeePassXC listens for (labwc has no ScreenSaver service).
  Tests: `test_app_confine_policy.py` (every policy, crafted bad policies, portal configuration,
  portal-open), `test_app_confine_portal.py` (a private bus with the real xdg-desktop-portal, document
  portal and permission store and a fake back end: identity, a picked file read through the document
  portal, another document invisible, an https link reaching the handler and nothing else, every
  forbidden call refused), `test_app_confine.py` and `test_app_confine_hook.sh` updated.

## 2.1: changes since Prestium 2.0

Prestium 2.1 is a security and features release on top of Prestium 2.0, still built with live-build
on Debian 13 "trixie". It adds a verified and locked boot chain, a Browser Updater, an I2P
Connection Assistant, time sync over Tor onion services, IRC over Tor, a new Adwaita desktop,
tighter confinement and firewall rules, and signed release files.

This section describes what 2.1 ships compared with 2.0, as one summary (not the order the work was
done in).

### Boot and integrity
- **dm-verity for the live system.** The build makes a hash tree for `live/filesystem.squashfs`
  (`auto/config --dm-verity`, hook 9010) and puts its root hash on every GRUB and isolinux entry. The
  initramfs (live-boot, patched by hook 0405) refuses to boot when the hash tree is missing, the root
  hash is missing or malformed, an extra or non-squashfs image or "plain root" mode turns up, or
  dm-verity can't be set up; there is no fallback to a plain mount. A changed block is an I/O error at
  mount time or a kernel panic later (`dm-verity-oncorruption=panic`). Files live-boot would read from
  the stick into its mount options (`.fec`, `.roothash`, `*.module` lists and similar) stop the boot,
  and live-boot no longer sources `live/boot.conf` from the stick. The root hash is in the release
  files, so a signed release signs it too.
- **Only the image's own kernel command line boots.** `/usr/share/prestium/boot/cmdline.policy` lists
  the command line (the APPEND options, the root hash, `dm-verity-oncorruption=panic`, `panic=10`,
  `lockdown=integrity`), each exactly once; only `quiet`, `splash`, `nomodeset`, `prestium.nocammic`,
  `nomacspoof`, `verify-checksums`, plain `toram`, `prestium.network-logs` and the
  `BOOT_IMAGE=`/`initrd=` the loaders add may be added. Anything else (a missing, extra or repeated
  option, odd characters, no policy) stops the boot. The check runs three times: in the initramfs's
  `/init` before it reads `break=`, `init=` or `debug` (a mismatch restarts the computer after 10
  seconds and never opens a shell), in `prestium-cmdline-check.service` from the verified image before
  AppArmor loads (`FailureAction=reboot-force`), and in the safety notifier, which names the wrong
  options. Every entry has `panic=10`, so a failed check reboots instead of opening a root shell.
- **Locked boot menus.** GRUB (UEFI) has a superuser with a PBKDF2 password hash and every entry is
  `--unrestricted`: booting needs no password, but editing an entry or opening GRUB's command line
  does (submenus and the configs that run before the menu included). isolinux (BIOS) takes no added
  options. The hash comes from `PRESTIUM_GRUB_PASSWORD_HASH` or a gitignored `grub-password.pbkdf2`
  (`scripts/grub-pbkdf2.py`); without one the menu is locked with a random password nobody knows.
- **GRUB boots only this stick's files.** It searches for `/.disk/prestium-<id>`, unique to each build
  (from the root hash), trying the disk it started from first, and restarts the computer if that file
  is missing, instead of booting the first disk that has `/.disk/info`. `findiso=` and `loopback.cfg`
  are removed.
- **The build checks every boot config.** Hook 9020 checks every kernel line word by word (no
  `apparmor=0`, `init=`, `break`, `rd.*` shells, `systemd.unit=`, `debug`, `persistence`,
  `module.sig_enforce=0`, a missing `panic=10` or `lockdown=integrity`, and others). Hook 9030 runs the
  same policy code as the initramfs over every GRUB and isolinux entry and also refuses another root
  hash, `chainloader`, `linux16`, `multiboot`, `loopback`, `load_env`/`save_env`, other searches,
  configs outside `/boot/grub`, isolinux `config`/`localboot`/`com32` modules other than `hdt.c32`, a
  policy that drifts from `LB_BOOTAPPEND_LIVE`, a kernel with a built-in or forced command line, and an
  initrd (matched to the chroot's by content) without the check.
- **Secure Boot uses Debian's signed chain, and the build proves it.** Firmware → Debian's shim
  (signed by Microsoft) → Debian's signed GRUB → Debian's signed kernel. Hook 9040 stops the build if
  `LB_UEFI_SECURE_BOOT` isn't `enable`, if there is any other EFI program or the ISO tree and
  `efi.img` differ (live-build's unused root `efi.img` with an unsigned GRUB is removed), or if shim,
  GRUB or the kernel isn't the expected Debian-signed file (Microsoft UEFI CA 2011/2023, Debian's CA,
  SBAT entries, GRUB's prefix and built-in modules, dpkg's MD5 for the kernel), checked with `sbverify`
  against CA certificates pinned in `thirdparty/keys/secure-boot/`. The kernel runs with
  `lockdown=integrity` even with Secure Boot off or on BIOS; the safety notifier alerts when lockdown
  is off and says once per session when a UEFI computer started with Secure Boot off.
- **Network Logs boot entry.** *Prestium 2.1 (Network Logs)* is the only entry with
  `prestium.network-logs`. Only in that boot do Tor and i2pd log, does `prestium-logs` run and does the
  menu show *Network > Network Logs*. In the default boot Tor logs to `/dev/null` and i2pd runs with
  `--loglevel=none`.

### Desktop
- **Adwaita light look.** GTK 2, 3 and 4 apps use stock Adwaita (light, blue accent, Cantarell),
  set once in dconf (`/etc/dconf/db/local.d/10-prestium-desktop`; the build fails if it isn't
  compiled), Qt apps use adwaita-qt (`QT_STYLE_OVERRIDE=Adwaita`) and KDE apps, Kleopatra included, a
  matching light `Prestium` colour scheme. Kvantum, the Prestium-Dark GTK theme and the dark CSS are
  gone. Windows get one labwc title bar (`Prestium-Adwaita` theme, 8 px corners, shadows) with
  minimise, maximise and close; apps don't draw a second one.
- **Two bars.** A black top bar: the Applications button (opens the menu under itself), the clock in
  UTC in the centre, then the tray, Tor and I2P pills (red: not connected, amber: connecting, green:
  connected; a click opens the matching Connection Assistant), a clock-sync symbol (amber until the
  time is set over Tor, red if the sync refused a time), volume (capped at 100 %), network, battery
  and power. A black bottom taskbar shows one colour icon per window; clicking it selects the window.
  The pills' state comes from `prestium-netstatus.service` (its own user, read-only, writes only
  `/run/prestium/netstatus`), which asks Tor's bootstrap state through the control-port filter, so
  it is right in the default boot, where Tor keeps no log.
- **The menu is grouped by task.** Top level: I2P Browser, Tor Browser, I2P Router Console, Text
  Editor, File Manager; then Office (LibreOffice, Document Viewer), Multimedia, Accessories, Security, Communication, Sharing,
  Network and System; then Restart… and Shut Down… (Log Out is gone). The Applications button and
  Super+Space open it, under the button; nothing else does, no click on the desktop either (labwc's
  left, right and middle-click menus there are cleared). Clicking a Tor/I2P pill or a taskbar icon
  could open the menu instead: the button opened it on the press, labwc then took the pointer before
  the release reached waybar, and GTK sent the next click in either bar to Applications again (until
  the mouse moved away or a few more clicks). It now opens on the release; reproduced and checked
  with labwc 0.8.3 and waybar 0.12 on a headless output. Networked apps name their network ("Claws Mail (Email, I2P)", "IRC (Tor)", "Feather
  (Monero Wallet, I2P)"); Gajim is plain *Gajim*.
- **Icons, logo and wallpapers.** A `Prestium` icon theme holds the final logo mark and falls back to
  Adwaita, then Papirus. Three wallpapers (Horizon, Circuit, Mark) are picked in *System >
  Wallpaper*; the broker takes only one of those names, never a path.
- **Notifications** (mako): one look per urgency, critical ones stay; the volume and brightness
  display is compact; optional quiet sounds, off by default. The VM, image-age and safety notices
  are no longer held up at login.
- **Lock screen and dialogs.** The swaylock prompt is always visible and shows Caps Lock, key presses,
  verifying and wrong-password states at high contrast. Prestium's own dialogs (assistants, Browser
  Updater, broker confirmations) share one style, with named buttons (no bare "OK"), wrapping text and
  readable links and progress text; `test_contrast.py` checks every text pair from the shipped files.
- **Keys and behaviour.** Super+Return opens the terminal; Alt+arrows go to the browsers. lxpolkit is
  no longer started. When the screen is due to lock and no password is set, a notification says so.
  The file manager makes no thumbnails and mounts no drives by itself. Images open only in Loupe; the
  file manager's *Remove Metadata* action is gone (`prestium-remove-metadata` stays for the terminal).
  Volume Control opens on the Playback tab.
- **In a virtual machine** the session uses wlroots' software renderer (`WLR_RENDERER=pixman`), so
  apps that hand the compositor GPU buffers (VLC, QtQR) no longer crash it. Nothing changes on real
  hardware.

### Network, firewall and Tor
- **Tor connection changes need confirmation at the screen.** Apply, Cancel, Revert and Reconnect in
  the Tor Connection Assistant go through the Wayland broker (`prestium-wl tor-mode …`): it checks the
  request with the helper's own parser, shows the connection type, the bridges and the program that
  asked in a dialog only the person at the screen can answer, then runs the helper as root, passes its
  progress back, logs the change and sends a notification. sudo allows only `status` and `features`,
  so another program can no longer move Tor onto its own bridge or stop it.
- **Tighter firewall.** i2pd's and Tor's accepts are for the network only: on loopback i2pd keeps only
  its SOCKS outproxy tunnel (4500) and Tor only the ephemeral ports 32768-60999 (pluggable transports)
  and OnionShare's 127.0.0.1:17600-17650. The early firewall checks every step, applies as much
  drop-all as it can and fails if IPv4 or IPv6 isn't DROP; iptables is pinned to the legacy backend.
  The Wayland broker's socket is group `user` only (0660). The MAC guard re-installs its egress filter
  on every device event.
- **Fewer root powers.** The Wayland broker has a capability bounding set; the MAC guard keeps only
  `CAP_NET_ADMIN`, Unix and netlink sockets. The time sync, boot clock, clock fix and USB watchdog run
  in systemd sandboxes; the VM network check and the network-status and log services run as their own
  users. Root daemons read `PRESTIUM_*` test overrides only when run from the source tree. Sessions get
  `PYTHONNOUSERSITE=1` and a `sitecustomize` that turns the user site off.
- **Control-port filter (onion-grater).** It runs under an enforced AppArmor profile (`ptrace (read)`
  only) with ptrace and `process_vm` syscalls filtered, refuses a Python client started with `PYTHON*`
  (other than a short allow-list), `LD_*` or code from outside `/usr` and `/lib`, and logs each refusal
  with an escaped reason. Nyx, OnionShare, the Tor Connection Assistant and a read-only
  `tor-bootstrap.py` (used by the bar, the time sync and the VM check) are its only clients; Nyx and
  the assistant work through it again. Private OnionShare addresses open in Tor Browser (it asks for
  the key, kept until Tor restarts, never on disk).
- **Network → Network Logs** (in the Network Logs boot only) shows the last 400 entries of Tor, i2pd and
  the filter, copied every 10 seconds by `prestium-logs` (its own user, no network) to files only the
  desktop user can read, one line per entry with control and invisible characters escaped. `torrc`
  sets `SafeLogging 1`.
- **Setting the clock has bounds.** `sudo date` is replaced by `sudo prestium-set-clock` (strict UTC
  format). It, the time sync and the clock fix refuse a time before the build date (one day of slack)
  or more than 10 years after it.
- **Fewer filesystem drivers.** 21 rarely used ones (hfs, minix, jfs, reiserfs and others) can't be
  loaded; FAT, exFAT, NTFS, ext4, Btrfs, XFS, F2FS, ISO 9660, UDF and HFS+ still work.

### Time over Tor
- **`prestium-timesync`**, on Kicksecure's sdwdate design (written for Prestium; Kicksecure's source
  list ships under AGPL-3+ in `/usr/share/prestium/timesync/pools.conf`). Each round asks one onion web
  server from each of three pools run by unrelated operators, each on its own Tor circuit as the
  firewalled `prestium-htp` user, and uses the median. A pool with more than a third of its members
  failing aborts the round; an answer outside Tor's consensus window is rejected; the clock never goes
  before the build date, the last time set this boot or `/etc/minimum-unixtime`. Up to a second of
  random nanoseconds is added. The first sync, or a difference over 10 seconds, steps the clock;
  smaller ones are slewed. It re-syncs every 60 to 180 minutes. A refused time, or a move of more than
  a day, raises a safety flag. The old one-shot clearnet HTTPS sync is gone.
- **Boot clock randomization.** `prestium-bootclock.service` moves the clock a random 0 to 50 seconds
  either way (inside the 60 s i2pd allows) before Tor, i2pd and the sync start.

### I2P
- **New: I2P Connection Assistant** (Network menu). It shows i2pd's per-boot port and sets tunnel
  hops (1 to 7, default 3), the share level (Low: 30 % of 32 KB/s, the default; Medium: 50 % of
  64 KB/s; High: 80 % of 128 KB/s) and the outproxy (Acetone by default, StormyCloud, which also takes
  the SOCKS outproxy, or a custom HTTP outproxy). Apply goes through the Wayland broker's confirmation
  dialog, then a root helper (`prestium-i2p-mode`, a checked JSON request) writes the files and
  restarts i2pd, and puts the old settings back if the browser proxy doesn't return. sudo allows only
  reading the settings. Reseed (over Tor through the control-port filter, or from a file) and *Restart*
  are in the same window, which scrolls on small screens. The old *I2P Tunnel Hops*, *Restart I2P* and
  reseed menu items are gone; `prestium-tunnel-hops` still works in a terminal.
- **`i2pd.conf` ships the Low share level** (`bandwidth = L`, `share = 30`), with transit on and
  floodfill off.
- **Fewer tunnels at boot, so the browser's come first.** Every pool sets its size: browser proxy 2+2,
  terminal proxy (4450), IRC2P, Ilita, postman SMTP and POP3, SOCKS (4447) and the SOCKS outproxy
  (4500) 1+1, exploratory 3+3, the shared destination 2+2 and the torrent client 5+5: 38 tunnels
  (was 68). The assistant changes hops, never counts.
- **I2P Torrents.** It announces to I2P's open trackers (postman, DgTrack, InsulaOcculta, skank, atia,
  dg2; as `.b32.i2p` addresses, since the address book is empty at boot, and by name) as well as the
  DHT, so magnet links without a tracker find peers. It keeps a persistent destination and DHT file,
  so torrents and peer discovery survive i2pd restarts (not reboots). Its tunnels follow the
  assistant's hop count. Its *Add .torrent* button can read `.torrent` files in the I2P Browser's
  folder.
- **Locking.** `prestium-i2pd-port` (before every i2pd start) and the assistant's helper share a
  root-only config lock (`/run/prestium-hops.lock`, made by tmpfiles, opened with `O_NOFOLLOW`), with
  bounded waits, so neither overwrites the other's edits; i2pd's start and stop timeouts fit the
  rollback.
- **Feather** uses I2P everywhere (i2pd's SOCKS 4447; its bundled Tor can't start).

### App confinement and sandboxes
- **Profiles are checked as they load.** Debian's complain-mode LibreOffice profiles attached to the
  same programs as Prestium's, so the kernel attached neither and LibreOffice ran unconfined. Hook
  0600 removes the four known Debian conflicts and runs `aa-attach-check.py`, which fails the build if
  any other profile attaches to a program a Prestium profile confines, or if another file defines a
  Prestium profile's name; apparmor.service runs it again at boot, and every profile must compile.
- **Programs that open downloaded files are confined:** Loupe, Evince, VLC, File Roller, FeatherPad,
  mat2, Metadata Cleaner and Audacity (no network, camera, admin tools, other apps' mail, chat or browser
  data, OpenPGP keys or KeePassXC databases; they read the file folders and save only in
  `~/Documents`). VLC plays local files only. The bubblewrap helpers of Loupe (glycin) and mat2/Metadata
  Cleaner run stacked with capability-stripped inner profiles (`glycin-inner`, `mat2-inner`,
  `metadata-cleaner-inner`, which may write only the one cleaned-copy name) on top of their bwrap
  profile. Viewers can't ptrace or reach
  the session bus.
- **New: Evince (Document Viewer)**, in *Office*, the default for PDF, PostScript, DjVu, DVI, XPS and
  comic books (TIFF stays with Loupe). It runs under Prestium's enforced `prestium.evince` profile
  (`evince`, plus `evince-previewer` for print preview and `evince-thumbnailer`); hook 0600 removes
  Debian's `usr.bin.evince`, which attached to the same programs and whose helper children may start
  browsers and mail apps. Evince has no network, sound or camera and only the restricted Wayland
  socket. It is a `~/Documents` app: it reads and saves there ("Save a Copy", annotations). Like the
  other viewers it opens files read-only (no write, no hard link) in `~/Downloads`, `~/Tor Browser`,
  `~/I2P Browser`, `~/Torrents`, the other file folders and unlocked volumes, so a PDF a browser or
  I2P Torrents downloaded opens in place from the file manager (the browsers can't start other
  programs; they show PDFs in their own viewer). It can't read the keys, KeePassXC databases or other
  apps' data, and the browsers' profiles and sandboxes can't read Evince's settings, cache or
  documents. Links in a document open nothing. It draws one header bar with minimise, maximise and close, like
  the other header-bar apps.
- **KeePassXC and Kleopatra are confined.** KeePassXC has no network or browser integration and saves
  `*.kdbx` (with its lock and safe-save files) in the home, `~/Documents` and unlocked volumes.
  Kleopatra and its GnuPG tools use `~/.gnupg`, read the file folders and save in `~/Documents`; only
  dirmngr opens TCP (through Tor) and the passphrase prompt is a confined pinentry. The file viewers,
  editors, KeePassXC and Kleopatra have no sound or microphone.
- **GnuPG's configuration files are off limits.** Neither Kleopatra nor the child profile Claws Mail
  runs gpg in may write or hard-link `~/.gnupg/*.conf` or `common.conf`, which can name helper
  programs that a socket-started gpg-agent would run outside the profile. `prestium-gnupg-check` (a
  root timer) flags such options written by anything else.
- **Shared folders.** Apps share `~/Downloads` (the local Firefox, Claws Mail, Gajim) and
  `~/Documents` (LibreOffice, FeatherPad, Evince, File Roller, Audacity, Kleopatra, Metadata Cleaner,
  Feather);
  only `~/I2P Browser`, `~/Torrents` and `~/Tor Browser` are app-specific, and the shared apps can't
  write there. The file manager pins those five and Claws Mail's mailbox (`~/Mail`, labelled Mail,
  made with its folders at build time). Mail and chat read only files directly in
  `~/Downloads`. Volumes under `/media` are read-only for the apps (except KeePassXC databases).
  LibreOffice can't save over a document opened from elsewhere (Save As) and writes no `.~lock` files.
  mat2 writes only in a work folder under `~/Documents`.
- **The viewers, players and editors open files anywhere in the home, read-only.** Loupe (and its
  glycin decoders, which get the file as a descriptor checked against their stacked profiles too),
  Evince (with its previewer and thumbnailer), VLC, LibreOffice, FeatherPad and Audacity read every
  folder of the home, hidden ones and `~/Tor Browser`, `~/I2P Browser` and `~/Torrents` included
  (shared abstraction `prestium-viewer-home-read`); Loupe's next/previous works in any folder. No write
  or link comes with it, each app saves only where it did before, and none has network. Denied
  whatever the folder: `~/.gnupg`, `~/.ssh`, `*.kdbx`, key files, keyrings, `~/.pki`, the password
  store, KeePassXC's, Kleopatra's and Feather's settings, Monero wallets, OnionShare's onion keys, the
  browser profiles, Claws Mail's and Gajim's/Pidgin's account data and shell histories. LibreOffice no
  longer takes app-base's "no `~/Tor Browser`" deny, so a document downloaded there opens in place.
- **Browser launchers and sandboxes.** Browsers started from mail and chat stay confined: the
  launchers have their own profiles, run as `bash -p` with a fixed PATH and ignore the caller's
  environment. The bubblewrap child reads a read-only system, the browser in `/opt` and only the
  sockets it binds, with the secrets and the other browser's folders denied. Tor Browser binds the
  socket directories read-only, so it reconnects after Tor restarts.
- **Audacity has no network,** not even the local proxy ports: it runs in its own empty network
  namespace (a second start joins it through a session socket), with the microphone and its plug-in
  host working.
- **LibreOffice, KeePassXC and the viewers work under their profiles** on a fresh home (first start,
  headless conversion, saving, recent files).
- **KeePassXC saves databases again,** in `~/Documents`, the home folder and on unlocked volumes.
  Every save failed with "Writing the database failed: Permission denied": Qt's safe save writes an
  unnamed temporary file, which AppArmor names `<folder>/#<number>`, so none of the `.kdbx` rules
  matched it, and the link that puts it in place needs the lock permission on it too. The temporary
  name now gets read, write and lock in the places a database may be saved; files written there are
  still `.kdbx` only, and the secret folders stay denied. Its window state in `~/.cache/keepassxc`
  is saved again too. Found in the kernel's AppArmor log on a Debian 13 VM (KeePassXC 2.7.10, the GUI
  and `keepassxc-cli`); `test_apparmor_startup.sh` checks those names.
- **Loupe opens images and Metadata Cleaner reads metadata again.** bubblewrap sets `no_new_privs`,
  and under it the kernel refuses a plain switch into another AppArmor profile, so every glycin
  decoder and every exiftool/ffmpeg run in bwrap failed to start (`operation="exec" info="no new
  privs"`). Loupe showed "Loader process exited early with status 159" (glycin's seccomp filter then
  killed bwrap's exit, SIGSYS) and Metadata Cleaner "Unable to Check for Metadata" for images. The
  helpers are now stacked with their inner profile, the transition `no_new_privs` allows; they run
  under both profiles, so nothing is loosened. Also: "Remove metadata" (mat2) can create its worker
  lock in `/dev/shm`, and Loupe can stop a decoder it no longer needs. Tested on a Debian 13 VM with
  AppArmor and the image's kernel options and sysctls; `test_apparmor_startup.sh` and
  `test_viewer_confinement.sh` check the stacked transitions.
- **KeePassXC's file dialog remembers its last folder.** It may write `~/.config/QtProject.conf`
  (with Qt's `.lock` and `QtProject.conf.XXXXXX` save files), and nothing else in `~/.config`.
  Creating, editing and reopening new databases in `~/Documents` and `~` was tested on an overlay
  home like the live system's, with no saving denials.
- **LibreOffice starts again.** Its first start stopped with "Fatal Error: User installation could not
  be completed" (exit 77) because the profile denied `/etc/passwd` and `/etc/nsswitch.conf`: LibreOffice
  finds the home folder through the user database, not `$HOME`, so it never got as far as creating
  `~/.config/libreoffice`. The profile now includes `nameservice-strict` (user lookups only, no
  network rules); it still has no network. Found in the kernel's AppArmor log under the profile on a
  Debian 13 VM; `test_apparmor_startup.sh` checks those reads.
- **The first session password can only be set from the lock dialog,** which the broker shows on the
  compositor's full socket; `passwd` is no longer setuid and sudo allows only `status`. The password
  needs at least 8 characters, and each wrong attempt at the lock screen costs at least 4 seconds.
- **Broker dialogs can't be answered by other programs.** The confirmations and the password form run
  on the full socket with accessibility off and Prestium's style from a root-owned directory, time
  out and close, and show the requesting program's (self-reported, sanitised) name.

### Browsers and Browser Updater
- **New: Browser Updater** (*Network > Browser Updater*) installs the latest publisher-signed Tor
  Browser or I2P Browser (LibreWolf) for this session, through Tor (its own circuit) or the I2P
  outproxy, only from the publisher's `https://` hosts. The window checks the signature as the user;
  the root helper `prestium-browser-install` copies the files into a root-only directory and checks
  them again with the image's keys (Tor Browser: detached signature and the version inside; LibreWolf:
  `InRelease`, `Packages`, the `.deb`'s SHA-256). Nothing older than the installed version is
  installed, and an expired key says to use a newer ISO. The update is unpacked on a tmpfs and
  bind-mounted read-only over the shipped path (no maintainer scripts run), so launchers and AppArmor
  paths stay the same; it lasts until *Reset to shipped copy* or reboot, and the window shows the RAM
  it costs. The helper refuses while the browser runs.
- **Tor Browser is the newest signed release at build time** (at least 16.0.1), from the Tor Project's
  update service and dist.torproject.org; the tarball must contain that release. `PRESTIUM_TB_VERSION`
  and `PRESTIUM_TB_SHA256` pin one.
- **uBlock Origin is the newest release at build time**, from addons.mozilla.org, no longer a copy in
  the repository. The build reads AMO's API, checks the download's size and SHA-256 against it, checks
  Mozilla's add-on signature (`META-INF/mozilla.rsa` chained to the AMO root, pinned in
  `thirdparty/keys/mozilla-amo-root.pem`, signer = the add-on id, every file covered by
  `manifest.mf`), the add-on id and version, and that its `strict_min_version` fits the Tor Browser
  and LibreWolf it ships with; any failure stops the build. During a session both browsers keep
  updating it from AMO themselves (over Tor, or the I2P outproxy for LibreWolf).
- **The local-only Firefox launcher** passes its profile and URL through the environment, never a
  command string; its only `file://` exception is The Lounge's one-off sign-in page.

### Messaging, IRC and mail
- **New: IRC (Tor)**, a second The Lounge next to *IRC (I2P)*: its own system user `thelounge-tor`,
  state directory, read-only `config.js`, web UI on 127.0.0.1:9010, systemd unit and AppArmor profile.
  The firewall lets it reach only Tor's SOCKS port; every network goes through it, names are resolved
  by Tor, and each network has its own random SOCKS username (its own circuits). Presets, all onion
  services that need no account: OFTC (default), Ergo, DarkScience and IRCNow. Networks start
  disconnected with a random nick. The Connect form checks TLS certificates by default; only the OFTC
  preset doesn't (its certificate is for irc.oftc.net, and the onion address authenticates it). For a
  network you add that needs SASL (Libera.Chat, AlphaChat), the lobby says what to fill in before
  connecting. Pirate IRC is no longer a preset.
- **The Lounge, both instances.** `config.js` and the packages are root-owned and read-only; the
  sign-in token works once and never appears in a command line. Ten Theme Factory themes are bundled
  as local packages, Tech Innovation by default. The ping timeout is 320 seconds (hook 0200 stops the
  build if The Lounge's code changes), so I2P networks drop less often, and the lobby no longer says
  it is connecting when it isn't.
- **Gajim** ships Tor (SOCKS5 9050, default), I2P SOCKS (4447) and I2P HTTP (4444) proxy profiles.
- **Mail (I2P)** asks for your account on first start (postman's servers filled in) instead of
  shipping a placeholder, and Claws Mail can generate a PGP key again. Kleopatra's self-test passes
  (scdaemon is installed).

### Safety and virtual machines
- **Safety alerts** also cover AppArmor (module off, service not active, any Prestium profile not in
  enforce mode), kernel lockdown, the boot settings check and the time sync's flags.
- **Virtual machines.** A notice at login says the host can see and record everything. If Tor or I2P
  hasn't connected after 10 minutes, the desktop says why (no route, user-mode networking, a VM clock
  on local time, a host firewall blocking I2P); the check runs as its own user and never copies log
  text.
- **The image says when it is old:** a notice five minutes after login once the build is more than 45
  days old (the build date is `BUILD_ID` in `/etc/os-release`), pointing to the Browser Updater.
- **The session wipe reports failure.** At shutdown `prestium-wipe-session` deletes the overlay's
  read-write branch and work directory and the runtime secrets under `/run` (the assistant's bridge
  lines, the DoH cache, network logs, IRC sign-in tokens, Tor's control cookie, the filter's, i2pd's
  and sudo's state, user runtime directories), checks each tree afterwards and logs "session wipe
  FAILED" and exits 1 if anything is left. The USB watchdog's emergency wipe does the same.

### Removed
- **Pidgin** (GTK 2, XWayland-only) with its Tor launcher, OMEMO (lurch), OTR and XMPP extras; Gajim is
  the messenger.
- **GIMP, Xarchiver and Ristretto** with their profiles (Loupe views images, File Roller handles
  archives), and lxpolkit.

### Build and release
- **Signature checks refuse expired and revoked keys** and check each signature line by line in a
  throw-away keyring holding only that publisher's key; a failed import stops the build
  (`scripts/sigcheck.sh`). Node.js must be signed by a current releaser's primary key.
- **Versions:** Tor Browser newest signed (16.0.1 or later), system Tor 0.4.9.16 from
  deb.torproject.org, Node.js 24.22.3 (November 2026 security release), The Lounge 4.5.2, Feather
  newest signed (2.9.1 or later), Firefox 159.0.1, i2pd 3.0.0 (PurpleI2P's pinned GitHub `.deb`); LibreWolf from its repository
  at build time.
- **The Lounge's `npm ci` works on Debian 13's npm 9**; irc-framework is installed from a `git
  archive` of the pinned commit with a pinned SHA-256, so npm never packs it or runs build tools.
- **The I2P reseed file ships in the repository** (`i2pseeds.su3`, signer certificate in
  `thirdparty/keys/reseed/`), signature-checked at every build, with an age warning; the StormyCloud
  download is only a fallback.
- **Release files.** `build.sh` writes `SHA256SUMS` (the ISO, its manifest, its dm-verity root hash
  and its package list) and `Prestium-2.1-amd64.manifest` (image hash and size, build date, source
  commit, package count and the third-party versions). `scripts/sign-release.sh FINGERPRINT` writes
  and checks `SHA256SUMS.asc`.
- **Repeatable builds, first step.** `PRESTIUM_SNAPSHOT` builds Debian from snapshot.debian.org and
  `SOURCE_DATE_EPOCH` is the commit's time. Not yet bit-for-bit reproducible.
- **Version strings** (`/etc/os-release`, `/etc/issue`, `/etc/issue.net`, boot menu labels) come from
  one `VERSION` setting in the build hooks.

### Tests
- 85 test scripts under `tests/`, for the boot chain (`test_dm_verity.sh`, `test_boot_lock.sh`,
  `test_boot_cmdline_guard.sh`, `test_secure_boot.sh`), AppArmor (`test_apparmor_startup.sh` evaluates
  the compiled profiles, `test_apparmor_boot_load.sh`, `test_aa_attach_check.sh`,
  `test_apparmor_claws.sh`), the firewall, the Wayland broker and its dialogs, the MAC guard, the Tor
  and I2P helpers (`test_tor_mode_confirm.py`, `test_i2p_tunnel_budget.py`,
  `test_i2pd_config_lock.py`), the time sync, The Lounge, the Browser Updater, the session wipe and
  the desktop's design (`test_ui_consistency.py`, `test_contrast.py`). `tests/ci.sh` (run by hand on
  Debian 13) runs shellcheck, compiles every profile, scans for committed keys and tokens, checks
  `systemd-analyze security` scores and runs the tests that don't need a live session.

### Late 2.1 additions
- **Metadata Cleaner: "Unable to Read the File" on browser-saved .png images.** mat2 chooses a parser
  by the file name, and PNGParser turned any cairo failure into an empty `ValueError()`. Browsers often
  save a WebP (or JPEG, AVIF) under a `.png` name, which then failed with no reason. A small add-on that
  mat2 loads with its parsers (`libmat2/prestium_filetype.py`, checked and byte-compiled by hook 0465)
  reads the real type from the file's first bytes: a WebP named `.png` is cleaned into a real PNG
  (Pillow's WebP decoder only), a JPEG/TIFF/PNG with the wrong name goes to the right parser, a PNG too
  large for cairo is re-encoded with GdkPixbuf, and everything else (AVIF, GIF/HEIC with the wrong name,
  an empty, truncated or HTML file) says why on the details page.
- **Apps opened from the panel run outside the broker's sandbox.** The panel (waybar) is started by
  prestium-wl-broker and lives in its unit, whose `RestrictAddressFamilies=AF_UNIX AF_NETLINK` and
  `RestrictNamespaces=yes` seccomp filters every child inherited, through sudo too. The Tor and I2P
  assistants, Volume and Power opened from the panel had no IP sockets and could not start bwrap, so
  "Open in Tor Browser" from them, and Tor Browser, I2P Browser, Loupe or mat2 started from them,
  failed. The panel now starts them with `prestium-launch`, a transient unit of the user's systemd
  manager (like D-Bus-activated programs), still on the restricted Wayland socket; labwc's autostart
  imports the session's settings there. The broker keeps its hardening.
- **File chooser with one header** (Unlock Volume's "Unlock a file container" and keyfiles, VeraCrypt):
  `zenity --file-selection` now opens Prestium's own GTK 4 picker (`/usr/local/lib/prestium/file-picker`).
  zenity's chooser is a GTK 4 dialog with its own header bar, and labwc's title bar for zenity windows sat
  above it (two bars, the title twice). The picker has one header bar with Cancel, the title, search, Open
  and minimise, maximise and close, like the other apps, and keeps the user's bookmarks and recent files.
  Options it does not handle run zenity's chooser as before.
- **Tor:** `VanguardsLiteEnabled 1` is pinned after the torrc drop-ins, so no bridge or transport
  drop-in can turn off the slowly rotating second-hop guards that protect onion-service circuits.
- **No AF_ALG sockets for confined apps** (`deny network alg,` in prestium-no-admin, the browser
  launchers, the Tor Browser and onion-grater profiles). It is not blacklisted system-wide: cryptsetup
  uses AF_ALG for VeraCrypt and TrueCrypt volumes, and the unlock path (Unlock Volume, udisks,
  cryptsetup, the file manager) stays outside these profiles.
- **`ia32_emulation=0`** on the kernel command line (and required by the boot policy): nothing on the
  image is 32-bit, so the 32-bit system call entry points are off.
- **Landlock for Prestium's Python helpers** (time sync, MAC guard, logs, network logs): each restricts
  itself at start to the paths it reads and writes, programs from `/usr` and (time sync only) Tor's
  SOCKS port, through a small ctypes module with no new dependency. Without Landlock it logs that and
  carries on. The Wayland broker and onion-grater are left out: they read other processes'
  `/proc/<pid>` entries, which Landlock refuses, and the broker starts setuid tools.
- **KeePassXC** starts with its light theme.
- **Feather:** its settings (recent wallets, node) were never saved, because Qt's save links a
  temporary file into `~/.config/feather` (AppArmor `l`), and Monero's shared ring database in
  `~/.shared-ringdb` was denied; both allowed.
- **Metadata Cleaner** cleans files in place wherever they are in the home, `~/Downloads` included,
  and opens files elsewhere in the home (before, every file outside `~/Documents` failed with
  "Permission denied" or "Unable to Read the File"). Hidden folders, `~/bin`, launchers, secrets and
  volumes stay read-only for it; mat2 reads anywhere in the home too, and still writes only its work folder.
- **Dialogs:** zenity dialogs (Power, Unlock Volume, confirmations) show one title, in the title bar,
  over a flat content area, instead of a second bold title on a rounded card inside the frame.
- **Refresh reseed (via Tor)** works when the I2P Connection Assistant was opened from the panel's
  I2P button. The panel and everything it starts inherit the Wayland broker's sandbox (IP sockets
  refused), which sudo and runuser keep, so the helper reported "cannot reach Tor's SOCKS port" with
  Tor running. The SOCKS check and every download now run in their own transient systemd service as
  `prestium-htp` (no capabilities, IPv4 to 127.0.0.1 only, clean environment). The helper tries
  StormyCloud first, then seven more reseed servers built into i2pd, each over Tor and pinned to its
  signer; a server that is down, slow, has a bad certificate or serves a bad, wrongly signed or stale
  file is skipped with a reason, and when all fail the dialog lists each server's reason. There is no
  clearnet fallback.
- **Feather and i2pd are downloaded from GitHub.** Feather's zip and `.asc` come from
  `github.com/feather-wallet/feather` releases instead of featherwallet.org, still checked against
  Feather's signing key and the pinned SHA-256 (unchanged: the GitHub file is the same). i2pd is no
  longer installed from the repo.i2pd.xyz apt repository: `scripts/fetch-thirdparty.sh` downloads
  PurpleI2P's `i2pd_3.0.0-1trixie1_amd64.deb` from `github.com/PurpleI2P/i2pd` releases, checks it
  against the SHA-256 pinned in `thirdparty/versions.sh` and its package name, version and
  architecture, and stages it; hook 0005 checks it again and installs it, with its dependencies from
  Debian. PurpleI2P publishes no signature for the `.deb`, so the pinned SHA-256 is its only trust
  anchor (the apt repository was signed, but unpinned). The i2pd version is now pinned instead of
  "newest at build time", and Debian's own older i2pd is pinned out. The repository's apt source,
  key, keyring (`purplei2p.gpg`) and origin pins are removed; the i2pd user, its uid 2000 and the
  config set up by hooks 0100 and 0700 are unchanged.
- **Feather is the newest signed release at build time**, like Tor Browser (`scripts/feather-latest.sh`).
  Each build asks GitHub for feather-wallet/feather's latest release (never a draft or prerelease; the
  tag must be a plain version), downloads its zip and `.asc` from the GitHub release and requires a valid
  signature by Feather's key in a keyring holding only that key. That signature is now Feather's trust
  anchor instead of a pinned SHA-256, with `FEATHER_MIN_VERSION` (2.9.1) as a floor so an older, still
  validly signed release stops the build; the signed zip must hold `feather-<that version>`. The build
  log and the image manifest record the version and SHA-256 shipped, and
  `PRESTIUM_FEATHER_VERSION`/`PRESTIUM_FEATHER_SHA256` pin one release for reproducible builds. i2pd stays
  pinned.
- **Gajim: "GPGME: Invalid crypto engine" when connecting an account.** The OpenPGP plugin
  (gajim-openpgp) uses GPGME, which runs `gpgconf`, `gpg --version` and `gpgsm --version` to check the
  engine. Gajim's profile let it run none of them, so the engine check failed and the plugin raised
  `GPGMEError` at connect. GnuPG now runs in a child profile `gajim//gpg`, as Claws Mail's does: it may
  use only Gajim's own keyrings (`~/.local/share/gajim/openpgp/<account>/`, never `~/.gnupg`) and the
  agent's sockets, has no TCP/UDP and no dirmngr (the plugin runs gpg offline), may not write or
  hard-link GnuPG's `*.conf` there (neither may Gajim), and a passphrase prompt runs in
  `prestium_pinentry`. Tested by `tests/test_apparmor_gajim.sh` and new start-up checks in
  `tests/test_apparmor_startup.sh` (paths from an strace of the plugin's GPGME calls).
- **Build: hook 0700 stopped with "/var/lib/i2pd/i2pd.conf is still the package symlink".** PurpleI2P's
  `.deb` ships `/var/lib/i2pd/i2pd.conf` and `tunnels.conf` as symlinks to `/etc/i2pd` (not conffiles, so
  `--force-confold` doesn't cover them). The apt package used to be installed before live-build copied
  `config/includes.chroot`, which then replaced the symlinks; hook 0005 installs the `.deb` after the
  copy, so dpkg replaced Prestium's files with the symlinks instead. Hook 0005 now keeps a copy of
  `/var/lib/i2pd` as the includes left it, puts every entry back after the install, and stops the build
  if anything still differs (the package's extra `certificates` symlink, which 0700 sets anyway, may
  stay). 0700's check and all the `.deb` checks are unchanged. Tested by `tests/test_i2pd_deb.sh`
  (a package with the same symlinks, and a `/var/lib/i2pd` that can't be put back stops the build).
- **New: Gajim OpenPGP Keys** (`/usr/local/bin/prestium-gajim-keys`, *Communication* menu after Gajim),
  a GTK 3 window for the keys of Gajim's OpenPGP plugin. gajim-openpgp keeps one keyring per account
  (`~/.local/share/gajim/openpgp/<address>/`), uses its first secret key, accepts it only if its first
  `xmpp:` user ID is exactly `xmpp:<address>`, and ignores (and asks GnuPG to delete) keys with no
  `xmpp:` user ID, so a key made in Kleopatra could not be used and there was no way to see why. The
  window lists Gajim's accounts (read from `settings.sqlite` in memory, never locked or written; any
  address can be typed), shows each key's fingerprint, user IDs, expiry and status, and runs the checks
  with a fix for each (clock, keyring folder 700, one secret key, revoked, expired, created in the future,
  secret key present, the `xmpp:` user ID Gajim reads, encryption and signing, ownertrust; whether the
  server has the key is not checked, the tool has no network). It generates a key as the plugin does
  (GnuPG's default Ed25519/Curve25519, no expiry, optional passphrase), imports one from Kleopatra and
  adds the `xmpp:` user ID to Gajim's copy, adds, revokes and promotes user IDs (with a warning before
  revoking the `xmpp:` one), sets ultimate ownertrust, deletes a key, and backs a key up to a new
  `*.gajim-key.asc` file (a key with no passphrase is wrapped in AES-256 with a passphrase GnuPG asks
  for) and restores it. It warns before a change while Gajim is running. `--check [address]` prints
  the same report. All of it is the system gpg with `--homedir` (no new crypto library; the logic is in
  `/usr/local/lib/prestium-keys/gajim_keys.py`, no GTK) and a passphrase is only ever typed into
  pinentry. The import never runs gpg on `~/.gnupg`: the public keyring (or keyboxd's database) is
  copied into a private `/tmp/prestium-keys-*` directory for gpg, and the secret key files are copied
  byte for byte, still protected by their passphrase, so nothing in `~/.gnupg` is written, locked or
  started. Its enforced profile `usr.local.bin.prestium-gajim-keys` allows no TCP/UDP or bus, reads
  `~/.gnupg`'s public keyring and secret key files only, reads and writes Gajim's keyrings (never their
  `*.conf`, the plugin's `contacts.db` or Gajim's messages), reads Gajim's settings, and writes only new
  `*.gajim-key.asc` files in `~/Documents` or under `/media`; its gpg runs in a child profile that may
  not touch `~/.gnupg` at all, with pinentry in `prestium_pinentry`. Gajim's own profile is unchanged.
  Tested by `tests/test_gajim_keys.py` (real gpg in temporary keyrings: every status, the Kleopatra
  import from a `pubring.kbx` and a keyboxd keyring left unchanged, backups and restores, the command
  line, and Gajim's own plugin backend accepting the keys) and `tests/test_apparmor_gajim_keys.sh`
  (paths from an strace of every flow, against the compiled profile). Not yet tested on a booted ISO.
- **New: Prestium Translate** (`/usr/local/bin/prestium-translate`, *Accessories* menu after QR
  Generator, also listed under Office), offline English↔Russian translation and a style rewriter in one
  GTK 3 window in the style of Gajim OpenPGP Keys. The engine is bergamot-translator (Firefox
  Translations' engine; Debian 13 packages neither it nor translateLocally), built by the new hook 0210
  from a pinned source tar with a small pipe front end (`thirdparty/translate/prestium-translate-engine.cpp`)
  for x86-64 with SSE4.1 and no BLAS library (11 MB, links only the C/C++ runtime). The models are
  Mozilla's English→Russian and Russian→English models, version 2.1 of each (69 MB together), taken
  from the records of Mozilla's signed Remote Settings collection (content signature checked against
  the pinned AMO root by `scripts/translate-models.py`) and pinned by SHA-256; engine and models add
  about 52 MB to the compressed image. Hook 0210 fails closed on a missing, extra or changed file,
  installs them read-only in `/usr/share/prestium-translate/`, and stops the build if the engine
  can't translate a test sentence both ways. The engine starts once (on first use) and is fed
  through a pipe, inside bubblewrap (every namespace unshared, no network, no home, read-only
  libraries and models, private `/tmp`). Translate runs as you pause or on Ctrl+Enter, with a
  direction button and Cyrillic auto-detect. Rewrite has Light (invisible and look-alike characters,
  emoji and emoticons, fillers, slang and British spellings, punctuation, quotes, dashes, case and
  contractions evened out, with some choices random) and Strong (Light, then a round trip through the
  other language, then Light again), *Show changes* (word diff), and a *Check before sending* list of
  names, places, times, dates, numbers, addresses and repeated rare words a rewrite can't hide, with an
  honest note. Paste & go (Ctrl+Shift+V), Copy, Copy & clear (Ctrl+Shift+C), Clear, an optional
  60-second clipboard clear (only if the clipboard still holds the copied text). Status line
  "Offline, nothing saved": no history, no temporary files, no recent-files entries; only the mode,
  direction, strength and two switches go to `~/.config/prestium-translate/settings.json`, and the
  boxes are emptied on Clear and on close. The logic is in `/usr/local/lib/prestium-translate/core.py`
  (no GTK), also behind `--translate en-ru|ru-en|auto` and `--rewrite light|strong [--leftovers]` (stdin
  to stdout). Its enforced profile `usr.local.bin.prestium-translate` allows only a unix stream
  socket (Wayland; no TCP/UDP, netlink or bus), nothing of the home but its settings file, and no
  writes in `/tmp`; bubblewrap runs in the child profile `engine`, and the engine program, stacked
  (bubblewrap sets no_new_privs), in `prestium_translate_engine`, which denies all networking, user
  namespaces, mounts and capabilities and reads only its models and the runtime. On a recent
  processor a long paragraph takes about 0.5 seconds on one core and both models use about 300 MB.
  Tested by `tests/test_translate.py` (Light rules, leftovers, diff, settings, command line, and with
  the real engine and models: both directions, auto-detect, Strong keeps numbers and varies, the
  bubblewrap sandbox), `tests/test_translate_hook.sh` (pins, fetch steps, hook 0210 refusing changed,
  missing and extra files) and `tests/test_apparmor_translate.sh` (paths from an strace, against the
  compiled profiles). The button labels are in sentence case ("Paste & go", "Copy & clear") as the
  rest of Prestium. Not yet tested on a booted ISO.

### Known security limits
- **A kernel memory-corruption bug can be turned into an escape through the vDSO** (Phrack 73):
  `CONFIG_MSEAL_SYSTEM_MAPPINGS`, which blocks it, needs kernel 6.15 or later; Debian 13 ships 6.12.
- **Someone who can write to the USB stick can change the next boot.** Secure Boot checks shim, GRUB
  and the kernel, but the boot menus (with the root hash and the password hash), the initramfs and
  live-boot in it are unsigned files on the stick. Replacing them together with the image defeats
  dm-verity, the menu lock and the command line check. A copy of the stick can also answer GRUB's
  marker search when the boot disk doesn't. The fix, a signed unified kernel image booted by shim,
  isn't implemented. Keep the stick with you and check it from another computer against a signed
  release (`Prestium-2.1-amd64.roothash` is the hash the menu must carry; the hash tree's salt is
  random, so two builds of one commit differ). dm-verity does stop a changed or swapped image on its
  own, an extra image, a missing hash tree and blocks that change after boot.
- **The boot menu lock is only as strong as the stick:** the password hash is on it, so a chosen
  password must be long. Firmware boot menus and other boot media are outside Prestium's control.
- **The ISO itself is not signed** (`SHA256SUMS` is), and builds are not bit-for-bit reproducible.
- **Unprivileged user namespaces are on**, because the browser sandboxes (bubblewrap) need them.
- **X11 programs share one Xwayland server**, so an X11-only program can read the input and windows of
  the other X11 programs (not of Wayland apps such as the browsers).
- **Programs running as the desktop user can attach a disk image** (udisks loop-setup, needed for
  VeraCrypt containers); confined apps can't reach udisks.
- **Per-app folders limit writes, not reads.** A compromised viewer can read every file folder (it has
  no network), mail and chat can read files directly in `~/Downloads`, and the file manager and other
  unconfined programs of the desktop user can write everywhere. A compromised Metadata Cleaner can
  change your files outside the hidden folders (it cleans them in place).
- **The bubblewrap children of Loupe, mat2 and Metadata Cleaner keep bubblewrap's mount rights**, so a
  compromised parent could present files at a path the child may write.
- **GnuPG's socket-started daemons** may run outside Kleopatra's and Claws Mail's profiles; their
  configuration files can't be written or linked from those profiles, their pinentry is confined, and
  `prestium-gnupg-check` flags a helper from outside `/usr`.
- **Audacity keeps an IPv4 TCP rule** for its single-instance check, usable only inside its own
  namespace; the real program in `/usr/libexec` can still be started by hand outside it.
- **AppArmor's D-Bus rules are not enforced** on Debian 13's kernel (6.12).
- **Tor's uid may reach loopback ports 32768-60999** (pluggable transports) and 127.0.0.1:17600-17650
  (OnionShare).
- **The desktop user's programs may change NetworkManager's system connections** (to add Wi-Fi); the
  MAC guard and the firewall keep the real MAC and IP addresses from leaking that way.
- **The local-only Firefox's network rule follows a group** (`prestium-localweb`) that the desktop
  user's programs can also use, and **the i2pd console's per-boot password** is readable by them.
- **The desktop user may restart i2pd** without a prompt (`sudo systemctl restart i2pd`).

Still to confirm on a booted 2.1 ISO: booting from USB and DVD with Secure Boot on and off (shim,
signed GRUB, the locked menu, the marker search, `lockdown` showing `[integrity]`); the kernel
enforcing the GnuPG `*.conf` write and link denies; Kleopatra key generation, signing and settings;
Audacity (microphone, second start, no proxy access); the Tor Connection Assistant and Nyx through
the filter, with bridges under the tighter loopback rules; the Browser Updater on the live overlay;
the onion time sync and boot clock randomization; and the new look.

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
- Debian 13 trixie with updates and security fixes, kernel from the 6.12 line, firmware
  from trixie-backports plus extra network, TV tuner, Qualcomm and Samsung firmware.
- Tor Browser 16.0, Firefox 159.0.1 (local pages only), Node.js 24.22.2, The Lounge 4.5.2, Feather 2.9.1,
  and current LibreWolf, i2pd and Tor. uBlock Origin 1.75.4 (2.1: the newest at build time) and NoScript 13.6.37.
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
