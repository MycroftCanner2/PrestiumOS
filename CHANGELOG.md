# Prestium 2.0 (draft, work in progress): changes since 1.9.1.3

Prestium 2.0 is rebuilt from scratch with Debian's live-build (see BUILDING.md); the desktop looks
and works the same. Not released yet: the download, size and SHA-256 will be added here when the
ISO is published. Changes listed are against the last release, 1.9.1.3; the 1.9.1.3 notes (changes
since 1.8) follow below.

## 2.0 r20 (The Lounge starts again)

- The Lounge crashed at once (SIGABRT, core-dump, restarting every 5 s), so "IRC (The Lounge)" said the service was not running.
  systemd opens the service's stdin (/dev/null) before it moves the process into its private /dev and /tmp; under the
  `thelounge` AppArmor profile that fd is a disconnected path, AppArmor denied Node's `fstat(0)`, and Node aborts when
  fd 0 to 2 can't be checked (systemd issue #12302). The profile now has `flags=(attach_disconnected)`; its rules are unchanged.
  The same Node and The Lounge started fine under the profile through `aa-exec` on the r18 boot, which ruled out the rules themselves.
- Mail (I2P) did not start: Claws Mail 4.3.1 creates its control socket in `$XDG_RUNTIME_DIR/claws-mail/`, which its AppArmor
  profile did not allow ("Error creating socket_dir /run/user/1000/claws-mail"). The profile now allows that directory only.
- Gajim did not start: its multiprocessing pool needs POSIX semaphores, and glibc creates them with link() in /dev/shm,
  which the profile did not allow (PermissionError 13 in SemLock). The Gajim profile now allows `owner /dev/shm/sem.* rwkl`.
- Panel: window buttons are icons only (title on hover), so many windows no longer push the tray, volume and clock off screen.
- Panel Menu button did nothing: waybar's children only get the restricted Wayland socket, where labwc offers no
  virtual keyboard, so `wtype` could not connect. The button now runs `prestium-wl menu`; the broker presses
  Super+Space on a full-socket connection.
- Panel: the local-only Firefox (The Lounge, I2P console, torrents) has an icon (`prestium-localfox.desktop`).

## 2.0 r19 (desktop fixes from the first r18 boot)

- Browsers had no title bar with minimise, maximise and close. The labwc window rule that forces a frame on apps from the
  restricted Wayland socket matched the security-context engine "org.prestium.bwrap", but the broker registers
  "org.prestium.apps", so it matched nothing. The rule now uses the broker's name (a test checks they agree), and Tor Browser,
  LibreWolf and the local Firefox no longer put tabs in the title bar (`browser.tabs.inTitlebar` 0).
- Panel: a "Menu" button at the left opens the desktop menu (it sends Super+Space with `wtype`, the same shortcut as before,
  because labwc has no command to open a menu). Right-clicking the desktop still works too.

## 2.0 r18 (MAC spoofing: "NetworkManager runs but won't connect")

- MAC spoofing could silently not happen. The udev rule handed the spoofing script the device's kernel name (`%k`), but udev
  expands `RUN+=` when it reads the rule, before `80-net-setup-link.rules` renames the device (`eth0` to `enp1s0`). The script
  then found no such device and exited without spoofing, and the MAC guard, seeing the card about to use its real address,
  disconnected it every time. The rule now passes the interface index, which survives the rename, and the script looks the
  current name up from it.
- The `nomacspoof` boot option had no effect on the udev side: within one rule line udev tests `ENV{}` before it runs
  `IMPORT{cmdline}` (keys are sorted by type), so the option was never seen. The import now has a line of its own.
- The spoofing script leaves a device alone if it already has a spoofed address (a second "add" event no longer takes a
  connected card down), and logs every outcome.
- Boot menu: new entry "Prestium 2.0 (MAC address spoofing off)" (boot option `nomacspoof`), in both the UEFI and BIOS menus.
- Firewall: NetworkManager's DHCP lease renewal (root, UDP 68 to 67) is allowed out. The first lease never needed a rule (it
  goes over a packet socket); without this, renewals were refused and the lease fell back to a full re-discovery.

## 2.0 r17 (fixes from the first boot of an r16 build)

- Tor Browser: "Tor is not running (no SOCKS socket)". Tor skipped the Unix SOCKS socket, because with `GroupWritable` it
  requires the directory's group to be its own or root, and `/run/prestium-tbb` is group `prestium-tbb`. The socket is now
  `WorldWritable` and the directory (2750 debian-tor:prestium-tbb) decides who can reach it. Reproduced with Tor 0.4.9.15:
  `GroupWritable` refuses the directory, `WorldWritable` opens the socket.
- Tor Connection Assistant: "control port: FileNotFoundError". The control filter (onion-grater) exited at every start: it
  tried `chown(socket, root, user)` without CAP_CHOWN. The socket is now 0660 group `prestium-tbb` (a supplementary group of
  the service), and the filter refuses to start if that group is missing.
- Local Firefox (i2pd console, IRC, torrents): "Profile Missing". Firefox 147+ keeps profiles.ini under `~/.config/mozilla`
  and `~/.local/share/mozilla` when `~/.mozilla` doesn't exist. Its AppArmor profile now allows those two directories.
- Browsers: no more `/etc/dconf` denials (read-only access in the LibreWolf and local Firefox profiles). LibreWolf and Tor Browser
  no longer start Firefox's Wayland proxy inside the sandbox (`MOZ_DISABLE_WAYLAND_PROXY=1`).

## 2.0 r16 (no Signed-By clash in the binary stage)

- r15 was not enough: `lb binary` sets up its tool chroot with `chroot_archives chroot install`. Without
  `cache/bootstrap`, that tool chroot is a full copy of the image chroot, final sources included, so apt hit the Signed-By clash.
- The final sources now have the same file names as live-build's build-time lists (`prestium-tor.list`,
  `prestium-i2pd.list`, `prestium-librewolf.list`, all one-line format). Whenever live-build adds its lists, it overwrites
  them in that chroot instead of adding a second entry. The image chroot that becomes the squashfs keeps the final files.
- `build.sh` removes leftover final copies (and r14's old names) before each run, and installs them after the chroot stage.

## 2.0 r15 (--resume no longer hits duplicate apt sources)

- `--resume` failed with apt's `Conflicting values set for option Signed-By`. The cleanup hook had already installed the
  final sources (package keyrings), and live-build re-added its build-time lists for the same repositories (trusted.gpg.d keys).
- `build.sh` now runs `lb bootstrap`, `lb chroot`, `lb installer` and `lb binary` itself. It removes the final sources
  before each run, and installs them only after the chroot stage, once live-build has removed its build-time lists
  (checked). The cleanup hook no longer installs them. The image ends up with the same sources as before.
- `--resume` unmounts leftover chroot mounts recursively (`umount -R`), so nested mounts under `chroot/sys` don't
  block the installer copy.
- Not changed: building in rootless podman (sysfs mounts are refused there). Use a root container or a VM.

## 2.0 r14 (reseed download survives rate limits)

- StormyCloud rate-limits reseed downloads per IP (HTTP 429), so rebuilds and `--resume` runs failed after the first.
- `fetch-thirdparty.sh` keeps the last verified su3 in `cache/thirdparty/reseed/` and reuses it, verified again,
  when it was downloaded less than `PRESTIUM_RESEED_REUSE_HOURS` ago (default 24; `0` always downloads).
- When a download fails, a cached copy is used only if its signed version is at most 3 days old (with a WARN line).
  Otherwise the build stops as before. Every file used still passes signature, signer, format and age checks.

## 2.0 r13 (irc-framework check works with any npm)

- The build failed on hosts with a different npm with `IRC_FRAMEWORK_TREE SHA-256 ... != pinned`. Cause: npm runs
  irc-framework's `prepare` script (babel + webpack) when it packs this git dependency, so its `dist/` browser bundle
  depends on the toolchain versions npm resolves that day. The server never loads `dist/` (Node uses `main`: `src/`).
- `fetch-thirdparty.sh` now deletes `irc-framework/dist` after `npm ci` and checks every remaining file against a git
  checkout of `IRC_FRAMEWORK_COMMIT` (same path, same bytes, `package.json` equal as JSON, no extra files). It also
  checks that `package-lock.json` resolves to that commit. `IRC_FRAMEWORK_TREE_SHA256` is gone, so there is nothing to repin.
- The Lounge cache directory is now `thelounge-<version>-r13`, so trees from older builds are installed again.
- Known residual: `npm ci` still runs irc-framework's `prepare` on the build host with unpinned dev dependencies.
  Its output is deleted, but the code runs. Vendoring irc-framework would remove this.

## 2.0 r12 (Claws Mail confined)

- **Claws Mail** (I2P mail) now has an enforced AppArmor profile (`usr.bin.claws-mail`), like the
  other apps. Before, it ran unconfined, so a malicious message that compromised it could have used
  the passwordless protected settings (Tor mode, tunnel hops, reseed, clock) and the user's whole
  home directory. Now it gets the shared rules (no sudo/su/pkexec, no Prestium helpers, no Tor
  control socket, no system bus, no full Wayland socket, no browser, wallet, chat or KeePassXC
  data) and of `$HOME` only `~/.claws-mail`, its mailbox `~/Mail` and `~/Downloads`. GnuPG runs in a
  child profile that alone may use `~/.gnupg`; links open in the sandboxed browsers.
- `/etc/apparmor.d/local/usr.bin.claws-mail` can add rules (for example another folder for
  attachments).
- `fetch-thirdparty.sh` (r11.1): the lurch "done" marker is kept beside the source tree, not in it;
  the untracked file made the r7 clean-tree check fail on every fresh clone.
- CHANGELOG: the Display section described the X11 desktop (tint2, Openbox, Onboard,
  xfce4-display-settings); it now describes the Wayland one.
- Profile compiles (`apparmor_parser -QK`); not tested on a booted ISO yet.

## 2.0 r11 (no program can reach the compositor's full Wayland socket)

- **Wayland broker** (`prestium-wl-broker`, root). At login it makes labwc's own socket
  root-owned (mode 600) after checking it really is labwc's, so no process of the user, confined or
  not, can connect to it, chmod it back or take it over by renaming. It creates the restricted
  socket for applications in a root-owned directory (`/run/prestium-wl/<uid>/apps`), so it can't be
  replaced by a fake that would sit between applications and the compositor.
- The trusted parts that need the full protocol set (panel, notifications, wallpaper, idle lock,
  screen lock, on-screen keyboard, display settings, scaling, screenshots) are started by the
  broker, each with one connection passed as an inherited file descriptor (`WAYLAND_SOCKET`). Their
  own children get the restricted socket. They run with fixed config files and an empty root-owned
  `XDG_CONFIG_HOME`, so nothing an application can write changes what they do.
- **Screenshots** need a real click on a screen (Print) or a drag (Alt+Print) on an overlay;
  applications can't fake input, so none can take a screenshot unnoticed.
- **labwc reads only a root-owned configuration** (`labwc -C /run/prestium-wl/<uid>/labwc`, written
  by `prestium-wl-config` through sudo). Before, `~/.config/labwc` (writable by any application) could
  add key bindings, window rules or an autostart that run commands with the full socket. Touchpad
  settings are copied in as four checked values.
- Browsers use the shared restricted socket (no per-browser context helper any more).
- Taking the socket out of another process (pidfd_getfd, /proc/PID/mem) is blocked by Yama
  `ptrace_scope=2`, which Prestium already sets. The safety notifier alerts if it's lower, if the
  full socket isn't root-owned or if the broker isn't running.
- Tests: `tests/test_wayland_broker.sh` (28 checks, plus one skipped on this build host: its kernel
  has no Yama), `tests/test_wayland_session.sh` (10, including a control showing that plain labwc does
  run `~/.config/labwc/autostart`), `tests/test_browser_sandbox.sh` (35).
- Not tested on a booted ISO yet.

## 2.0 r10 (Wayland desktop, MAC guard, LibreWolf sandbox; boot password removed)

- **The administration password from r9 is removed** (no welcome dialog at login, protected settings
  work without a password as in r8). Confined apps still can't use sudo (AppArmor, no_new_privs).
- **Wayland desktop.** labwc replaces Openbox (same menu and key bindings), waybar replaces tint2,
  swaylock/swayidle replace i3lock/xss-lock, mako replaces notification-daemon, grim/slurp replace
  scrot, wvkbd replaces Onboard, foot is the terminal, wdisplays/wlr-randr replace the X display
  settings. Display scaling is done by the compositor, so every app follows at once. X11-only
  programs still run through Xwayland, and they can't see or inject into Wayland windows.
- **Restricted Wayland socket for applications** (security-context-v1). Apps started from the
  menu, the panel or the file manager get a socket on which the compositor hides screen capture,
  input injection (virtual keyboard and pointer), clipboard managers, the list of other windows,
  overlays (layer-shell), the session lock and output/gamma control. The full socket is only used by
  the panel, notifications, the screen lock, the on-screen keyboard, screenshots (Print) and display
  settings. Confined apps (AppArmor) can't open the full socket at all.
- **Browsers: Wayland only, each in its own security context**, with no X11 socket inside the
  sandbox (and Xwayland's abstract socket is unreachable from their network namespace).
- **LibreWolf (I2P Browser) gets the Tor Browser sandbox**: its own empty network namespace, of
  $HOME only ~/.librewolf and ~/Downloads, no D-Bus, no_new_privs, own PID/IPC/hostname namespaces.
  Its only way out is i2pd's HTTP proxy, through a Unix-socket relay (socat). The default browser
  (x-www-browser) is the sandboxed launcher.
- **MAC address guard** (`prestium-mac-guard`, root service). NetworkManager connections may still
  be edited by the desktop user, so a connection set to the real ("permanent") or a fixed MAC
  address is reset to the spoofed one at once, an active device using it is disconnected, and a
  safety alert is shown. A device about to use its real address is disconnected. An nftables egress
  filter on each card drops frames sent with the real address. The safety notifier alerts if the
  guard isn't running. Boot option `nomacspoof` still turns spoofing (and the guard) off.
- Tests: `tests/test_browser_sandbox.sh` (both browsers against a headless labwc, 34 checks),
  `tests/test_wayland_session.sh` (the session's config and restricted socket, 11 checks),
  `tests/test_mac_guard_policy.py` (11) and `tests/test_mac_guard_dbus.py` (5, against a mocked
  NetworkManager on D-Bus). All AppArmor profiles parse.
- Not tested on a booted ISO yet: real hardware/QEMU graphics, LightDM starting the Wayland
  session, real NetworkManager and nftables egress (the sandbox has no netfilter), Tor Browser
  and LibreWolf actually rendering under Wayland in the sandbox.

## 2.0 r9 (Tails parity: admin password, sandboxed Tor Browser, app confinement)

- **Administration password (optional, Tails-style).** A welcome dialog at login offers to set one.
  It can only be set then (within 15 minutes of boot, before an app is started). With it, the
  settings that change how anonymous you are ask for it every time: the Tor connection (bridges,
  transport, revert), the I2P tunnel hops, a manual I2P reseed file and the clock. Before r9 any
  program running as the desktop user could change these silently (for example point Tor at a
  bridge it controls, or drop I2P to one hop). Without a password they work as before, but never
  from a confined app. The screen-lock password is separate and grants nothing.
- **Confined apps can't ask for root.** Every app profile denies sudo, su, pkexec, Prestium's helpers,
  Tor's control socket and the system bus.
- **Tor Browser sandbox.** Tor Browser runs in bubblewrap: its own empty network namespace (only
  loopback; Tor's SOCKS port is a Unix socket bound in, so it can reach nothing else at all), a
  private filesystem with only ~/.tor-browser and ~/Tor Browser from your home, no D-Bus, its own
  PID/IPC/hostname namespaces and no_new_privs. The AppArmor profile still applies inside. Known
  limit: X11 is shared with the desktop.
- **onion-grater:** apps are now recognised by the file they really run (device and inode), not by a
  path. Before r9 any program could pose as Tor Browser or OnionShare by binding another file over
  that path in its own mount namespace.
- **More apps confined (AppArmor, enforced):** Gajim, OnionShare, Feather, LibreOffice (no network at
  all), The Lounge (also via its systemd unit) and the local-only Firefox. Pidgin is enforced.
- **No swap, ever:** swapon is a no-op (as in Tails) and `systemd.gpt_auto=0` is on the kernel command line.
- **Internal NVMe disks are hidden,** like SATA disks already were (`modprobe.blacklist=nvme` and modprobe.d).
- Tests: `tests/test_admin_password.sh`, `tests/test_tor_browser_sandbox.sh`,
  `tests/test_onion_grater_identity.py`; all AppArmor profiles parse with apparmor_parser 4.1.
- Not tested on a booted ISO yet. The new AppArmor profiles may still miss rules an app needs.

## 2.0 r8 (firewall stop fails closed)

- Stopping or restarting the firewall (ferm), including at shutdown, now falls back to the boot-time
  drop-all (loopback only, IPv4 and IPv6) instead of Debian's default, which cleared every rule and
  allowed all traffic until ferm started again. Policies are set to DROP before the old rules are
  cleared, so there is no open moment. Firewall reloads were already atomic and are unchanged.
- Not tested on a booted ISO yet.

## 2.0 r7 (failure handling)

- **Tor mode never reports success after a failed firewall reload:** `ferm_reload()` now checks its result. A failed reload during apply rolls back; Tor is started again only after the previous firewall reloads cleanly. If that reload fails too, Tor stays **stopped**, the state file records `firewall_error`, and the assistant tells the user to restart before going online. `revert` and cancel-during-apply fail closed the same way.
- **Tor mode restores the complete previous state:** the backup records files that did not exist (they are removed on restore, instead of leaving the new ones in place) and is only used when complete (`.complete` marker). A failed `tor stop` at the start of apply aborts the change.
- **i2pd port: complete rollback:** once `i2pd.conf` is touched, any failure (including `set -e` exits) restores the previous `i2pd.conf` **and** the previous `/run/prestium/i2pd.port` and `i2pd-console.pass` (or their absence), reloads ferm to match, and exits non-zero so i2pd does not start. A failed rollback is reported as such (exit 2).
- **Reseed refresh keeps a usable fallback:** the build-shipped/previous `.su3` (possibly stale) and the existing netDb are kept aside, not deleted, until i2pd has started with the freshly verified file downloaded through Tor. On any failure both come back and the message says the previous (possibly stale) data is in use. If the current file cannot be backed up, nothing is changed. A failed `systemctl stop i2pd` aborts before netDb is touched.
- **USB watchdog non-arming is visible:** only `toram` is an expected reason not to arm. No medium, an unresolvable medium, or a fallback process that did not start → unit fails (exit 3, no restart loop) and a safety flag is raised.
- **Shutdown memory-wipe preparation is visible:** `prestium-initramfs-unpack` fails on any decompress or cpio error or a missing `/shutdown`, and raises a safety flag.
- **New `prestium-safety-notify` (session autostart):** shows a persistent critical notification and a warning dialog for every safety flag, a watchdog unit that is not running (non-`toram` boots), and a failed `prestium-initramfs-shutdown.service`. Flags are written by `/usr/local/lib/prestium/safety-flag` to `/run/prestium/safety/` and logged to the kernel log and auth log.
- **Build locking and cache integrity:** `build.sh` holds an exclusive lock for the whole run (`--resume` removes live-build's `.lock`, which is only safe when nothing else builds). `fetch-thirdparty.sh` locks the shared cache. Cached The Lounge installs are reused only when their whole tree matches the hash recorded right after the lockfile-verified `npm ci`; the cached tar has a recorded SHA-256 that is checked after staging. Cached lurch work trees must be clean against their pinned commits. Staged Tor Browser, Firefox, Node and Feather copies are re-checked against their pins after copying.
- **Tests:** `tests/test_tor_mode_failures.py` (runs the real helper with mocked systemctl and ferm) and `tests/test_i2pd_port_rollback.sh` (runs the real script with redirected paths).
- **Not tested on a booted ISO yet.**

## 2.0 r6 (security / state-machine)

- **Tor mode cancel:** cancel with no apply no longer restores PREV and stops a connected Tor; connected → refuse (use revert); connecting → stop Tor, keep config; apply-in-progress → signal apply (restore PREV). Lock/PID race: cancel waits briefly if the apply lock is held.
- **Tor Connection Assistant:** cancel UI matches the new semantics; poller no longer drives phase during applying/cancelling; external Tor stop while connecting returns to idle.
- **i2pd port:** blocking ferm reload; on reload failure restore previous `i2pd.conf`, remove `/run/prestium/i2pd.port`, exit non-zero (fail closed). Per-boot console `auth`/`pass`; password in `/run/prestium/i2pd-console.pass` for localfox.
- **I2P Torrents:** bind-mount Torrents onto itself after create (blocks post-start symlink swap); `/run/prestium-torrents/status` distinguishes `ready` vs `disabled:<reason>`.
- **i2pd systemd:** `10-hardening.conf` with `ProtectHome=read-only` (not tmpfs) so Torrents stays visible via `ReadWritePaths`.
- **onion-grater:** control socket `0660` root:user (PEERCRED unchanged).
- **tunnel-hops:** flock; success text states `:4444` is limited readiness, not tunnels built.
- **reseed:** keep previous `.su3`, one retry on start failure, restore previous file if start still fails.
- **clockfix:** only verified consensus files (`cached-*-consensus`), never `unverified-*`. `prestium-timesync` ordered `After=prestium-clockfix`.
- **The Lounge launcher:** require active unit + 128-hex token; clearer recovery text.
- **Rejected / already fixed earlier:** sudoers `--file /*` is valid (`*` matches `/` in command arguments); UDP NEW + share template + blocking ferm reload landed in 515d178; lurch commit pins are content-addressed integrity (documented), not weaker than an unsigned tar SHA.

## Build system
- **Built with live-build** from a configuration in git (package lists, Prestium's files, hooks)
  instead of upgrading and patching an unpacked root filesystem. Anyone can rebuild the ISO with
  `sudo ./build.sh`.
- Every third-party download (Tor Browser, Firefox, Node.js, The Lounge, Feather, lurch) is checked
  against its publisher's OpenPGP signature and a SHA-256 pinned in the repository; LibreWolf, i2pd
  and Tor come from their signed apt repositories.
- Fixed: 1.9.1.3 shipped the build machine's `/etc/resolv.conf` (a private nameserver address).
  2.0 ships Prestium's own (`nameserver 127.0.0.1`, no system DNS). The firewall blocked DNS anyway.
- Build downloads are HTTPS-only, redirects included (`curl --proto =https --proto-redir =https`),
  and the Debian mirrors (bootstrap, chroot, security, and the shipped sources) use `https://`.
- Removed the legacy 1.9.1.3 trees (`rootfs/`, `iso/`, `build-1.9.1.3/`) and `LARGE_FILES.md` from
  this branch; 2.0 is built only from the live-build config. They remain in the
  `prestium-1.6-update` branch and in git history.
- Supply chain (audit): the build-time apt sources for i2pd, LibreWolf and Tor are each `signed-by`
  their own key, and apt pins (`Pin: origin`) let each repository supply only its own packages
  (i2pd; LibreWolf; tor, tor-geoipdb, the keyring, lyrebird, snowflake-client, webtunnel). The
  same pins ship in the image (`/etc/apt/preferences.d/prestium-thirdparty`).
- The Lounge is pinned exactly (`thelounge` 4.5.2, not `^4.5.2`) and its npm settings
  (`thirdparty/thelounge/.npmrc`: `ignore-scripts`, `save-exact`, `min-release-age=7`) are used by the
  build. Its one git dependency, `irc-framework` (commit-pinned, no integrity hash in the lockfile),
  is now checked against a pinned SHA-256 of its installed files on every build.

## Hardware and packages
- Everything current at build time: Debian 13 trixie with updates and security fixes, kernel from
  the trixie 6.12 line (Tails' line), firmware from trixie-backports (`firmware-linux` 20260916 or
  newer, the Tails 7.15 set) plus extra firmware for network cards, TV tuners, Qualcomm and Samsung
  devices where Debian has it.
- Tor Browser 16.0, Firefox 159.0.1 (local pages only), Node.js 24.22.2, The Lounge 4.5.2,
  Feather 2.9.1 (was 2.8.1), LibreWolf, i2pd and Tor at the newest versions of their repositories.
- Secure Boot (shim + GRUB), BIOS boot and the hybrid ISO are kept.
- SpeedCrunch is no longer in Debian 13 (1.9.x carried the Debian 12 package); the menu's
  Calculator is now Galculator.
- LibreWolf extensions updated to uBlock Origin 1.75.4 and NoScript 13.6.37 (AMO-signed); Tor
  Browser's added uBlock Origin also 1.75.4.

## Audio
- **PipeWire** with **WirePlumber**, **pipewire-pulse** and **pipewire-alsa** replaces plain ALSA,
  so sound works on more hardware (USB, HDMI/DisplayPort, Bluetooth-free laptops with SOF DSPs,
  Surface devices), with current ALSA UCM profiles and SOF firmware. Started for the user session by
  systemd. The camera-and-microphone-off boot option still blocks capture devices.
- The panel's volume icon is now **pasystray** (works with PipeWire); "Volume Control" (pavucontrol)
  is unchanged in the menu. volumeicon (ALSA only) is gone.

## Security
- i2pd's per-boot port is opened inbound for IPv4 only (1.8 to 2.0 drafts opened it for IPv4 and
  IPv6). The rule now lives in ferm.conf, which reads the port from /run/prestium/i2pd.port, so a
  firewall reload (for example by the Tor Connection Assistant) no longer drops it. IPv6 stays closed.
  Both the TCP and UDP rules accept only new connections. The rule is in place before i2pd starts.
- The spare /etc/i2pd/i2pd.conf template now matches the live config (bandwidth L, share 30).
- I2P Torrents page: reworked dark theme with a header bar, card panels, a sticky table header,
  right-aligned numbers, softer status colours on the progress bars, red delete buttons, a
  highlighted totals row, focus rings, dark scrollbars and a narrow-window layout.
- i2pd UPnP is explicitly off (`[upnp] enabled = false`) instead of relying on the Linux default.
- i2pd sets `floodfill = false` and `notransit = false` explicitly (never a floodfill, still relays transit tunnels).
- polkit: the desktop user gets an allow-list of NetworkManager actions (connect, disconnect,
  Wi-Fi on/off and scan, save connections) instead of every NetworkManager action. Hotspot sharing,
  hostname and global DNS changes and the other admin actions now need authentication. The i2pd
  rule only allows start, stop and restart, and every rule needs the active local session.
- Fixed (audit): the two helpers the desktop user may run through sudo (`prestium-tunnel-hops`,
  `prestium-i2p-reseed`) ran Python as root in the caller's working directory, so a planted module
  (e.g. `re.py`) ran as root. Both now `cd /` and run Python isolated (`python3 -I`).
- "Refresh I2P reseed" / "Manual reseed file" install the new file through the same symlink-safe
  helper (`safefile`) as the other i2pd helpers, so an entry planted in i2pd's directory cannot
  redirect or swallow the install.
- **LibreWolf (I2P Browser) runs under an enforced AppArmor profile** (complain mode in 1.9.1.3).
  It can write only its own profile/cache/config, `~/Downloads` and temporary files, cannot read
  other apps' data (Pidgin, Claws Mail, Feather, keyrings, GnuPG, Tor Browser) and cannot reach Tor's
  control port. Opening a download in another app from inside the browser is not allowed; use the
  file manager.
- The firewall stays default-deny. New: the Tor Connection Assistant's DNS-over-HTTPS user may only
  reach i2pd's HTTP proxy, and Tor's uid gets UDP only while Snowflake mode is on.
- **Security audit fixes (2.0 audit, all confirmed findings):**
  - **Fixed a local root escalation** (high): the root helper that prepares I2P Torrents before every
    i2pd start created and re-owned `~/Downloads` and `~/Downloads/Torrents` as root, following a
    symlink the desktop user could put there, so any program running as the user could take over a
    system directory with `sudo systemctl restart i2pd`. The folders are now created as the user,
    and a symlink or non-directory is refused (I2P Torrents is then skipped; i2pd still starts).
  - Root helpers no longer write through files the i2pd account owns (medium): changing tunnel hops,
    the per-boot i2pd port and the torrent setup read and replace `/var/lib/i2pd/i2pd.conf`,
    `tunnels.conf` and `tunnels.conf.d/` only through a new symlink-safe helper (refuses symlinks
    and special files, writes a new file and renames it into place). `tunnels.conf.d` is now
    `root:i2pd 0750`, so i2pd can read but not change it.
  - The Lounge's setup (root, before every start) refuses symlinked directories and reads and writes
    the user file as the `thelounge` account, exclusively, then renames it (low).
- Hardening from the audit: OnionShare's onion services may only point at OnionShare's own local
  ports 127.0.0.1:17600-17650 (as in Tails); `sudo prestium-tunnel-hops` accepts only 1-7; the Tor
  assistant's bridge checks accept ASCII digits only; the reseed helper refuses a symlinked
  `i2pd.conf` or netDb.

## Feather
- **Feather is back on I2P**, as in 1.7 and 1.8: its I2P proxy mode through i2pd's SOCKS proxy
  (127.0.0.1:4447). 1.9.x had switched it to Tor (9050) with onion nodes only.

## Tor Connection Assistant (new)
- New menu entry **Network → Tor Connection Assistant**. Tor still connects directly at boot.
- Error messages appear in a fixed-height, scrollable area (long details go to **Details**), so a failed connection never makes the window bigger; the window always fits above the taskbar (1024x768 and up), and long bridge lines wrap.
- Shows Tor's bootstrap progress (through the control-port filter, read-only), a **Reconnect**
  button, and modes **Direct**, **Snowflake**, **WebTunnel** and **obfs4** (Tor Browser's built-in
  bridges and/or your own bridge lines).
- **Snowflake and WebTunnel now work without system DNS:** only the host names they need (Snowflake
  front domains and STUN servers, the WebTunnel bridge host) are resolved with DNS-over-HTTPS
  **through the I2P outproxy** and pinned for Tor's transports. Tor's own traffic never goes through
  I2P. Networks that block or poison DNS for Tor infrastructure can't stop these look-ups.
- Optional, experimental: Snowflake's rendezvous through the I2P outproxy (if snowflake-client
  supports `-proxy`).
- **Reworked in 2.0:** modes **Direct, Snowflake, WebTunnel, obfs4 and meek**. Opening the
  assistant never touches Tor; **Apply and connect** stops Tor first, resolves, writes the new
  configuration and starts Tor again, so progress runs from 0 %. **Cancel** works at any point (the
  previous configuration is put back and Tor stays stopped; **Retry** / **Revert to previous**
  offered). Choices are saved in `~/.config/prestium/tor-assistant.json`; the mode shown on start is
  the one Tor is actually using.
- **Parallel DNS-over-HTTPS through the I2P outproxy:** every needed name is asked of several DoH
  providers at once (Cloudflare, Google, Quad9, AdGuard, Mullvad; port 443 only, keep-alive
  connections through i2pd's HTTP proxy), first valid public IPv4 answer wins, results are cached.
  Fixes 2.0's first version, whose Quad9 JSON endpoint (port 5053) the outproxy always refused.
- **Snowflake fix:** Debian's `system_tor` AppArmor profile did not let the transports read the
  system CA bundle, so TLS to the Snowflake broker (and WebTunnel/meek) failed inside the
  confinement. `/etc/apparmor.d/local/system_tor` now includes `abstractions/ssl_certs` and the
  network-interface reads Snowflake's WebRTC stack needs.
- **Built-in bridges** are Tor Browser 16.0's own (`pt_config.json`, copied verbatim). Transports
  from deb.torproject.org: **snowflake-client 2.15.1+tpo**, **lyrebird 0.9.0**, **webtunnel 0.0.7**.

## Display, laptops and accessibility
(2.0 r10 replaced the X11 desktop with Wayland: labwc instead of Openbox, waybar instead of tint2,
wdisplays instead of xfce4-display-settings, wvkbd instead of Onboard. This section describes the
current desktop.)
- **Display Settings** (wdisplays, started by the Wayland broker): resolution, arrangement and
  mirroring; labwc handles monitors plugged in or out.
- **HiDPI:** **Display Scale** (Auto from the screen's physical size, or 100-200 %), applied by the
  compositor at every login, so the panel (waybar), GTK/Qt apps and the browsers follow at once.
  X11-only programs run through Xwayland at the same scale.
- The I2P reseed windows (**Refresh I2P reseed**, **Manual reseed file**) and other zenity dialogs
  get a title bar and open centred (labwc window rule).
- **Laptop keys:** volume, mute, mic mute and brightness keys work, with an on-screen notification
  (mako); **Brightness** slider in the menu (brightnessctl; the live user is in group `video`, and a
  udev rule makes the backlight writable for it). The display key opens Display Settings.
- **Touchpad:** tap to click, natural scrolling and disable-while-typing by default; **Touchpad**
  settings in the menu, saved to `~/.config/prestium/touchpad.json` and copied into labwc's
  root-owned configuration as four checked values.
- **Screenshots:** Print (click a screen) or Alt+Print (drag an area), saved to `~/Pictures`.
- **Accessibility:** **Screen Keyboard** (wvkbd) in the menu. (The Orca screen reader was tried
  and removed: it did not work.)

## Apps
- **IRC (The Lounge)** no longer connects to IRC by itself. At boot the I2P tunnels are not up yet,
  so the automatic connection only produced an error (EPIPE) in the page. All networks are listed
  disconnected; right-click a network and choose **Connect** (or type `/connect`) when I2P is ready.
- **I2P Torrents** (i2pd's built-in torrent client) has a Prestium dark theme by default.
- The local-only Firefox no longer shows the Terms of Use / privacy notice / welcome pages at every
  boot (policy `SkipTermsOfUse` plus the matching first-run preferences). LibreWolf and Tor Browser
  never showed them.

## Known limitations (2.0 draft)
- See the test notes on the branch for what has and has not been verified in a VM yet.

---

# Prestium 1.9.1.3: changes since 1.8

Prestium 1.9.1.3 is a major update over 1.8. It rebases on Debian 13, adds Secure Boot and broader hardware support, adds Tails-style hardening throughout, and brings new apps and updates to existing ones. The desktop looks and works the same as 1.8.

**Download:** `Prestium-1.9.1.3-amd64.iso`, 2,592,849,920 bytes
**SHA-256:** `0ef5cd8bc1129b75a932eb76d1ef0f0031cc4160faab625beba480ae17a1913f`
**Torrent:** `Prestium-1.9.1.3-amd64.iso.torrent`, info hash `af992b4b9912282a875821f2e072c103b1ed1359`

## Base system and hardware
- **Debian 13 "trixie"** replaces Debian 12 "bookworm".
- **Kernel:** 6.12.113 replaces 6.1, on the same kernel line as Tails 7.
- **Firmware:** the same firmware set as Tails, so more hardware works out of the box.
  - Includes non-free firmware: `firmware-linux` 20260916, which replaces the 20230210 set.
  - Adds Surface and modern Intel audio (`firmware-sof-signed`), NVIDIA graphics firmware and current wireless-regdb.
  - CPU microcode updated: AMD 3.20250311.1, Intel 3.20251111.1.
- **Secure Boot:** Prestium now boots with Secure Boot on, like Tails, so Surface devices and modern laptops boot unchanged.
  - Boot chain: Microsoft-signed shim, then Debian-signed GRUB, then the Debian-signed kernel.
  - Kernel lockdown is on, and every kernel module must be signed.
  - BIOS boot and the hybrid ISO for USB and DVD are kept.
- New boot menu entry **"camera and microphone off"**. Sound output keeps working.
- **Hardware clock fix:** if the PC clock is far off (for example, a Windows dual-boot set to local time), Prestium corrects it from Tor's consensus so Tor can connect. It then sets the exact time over Tor.

## Security and privacy hardening
- **AppArmor now really enforces.** Prestium 1.8 loaded no profiles on the live system. Tor, i2pd and Tor Browser are now confined.
- **Memory erasure at shutdown, the Tails design.** On shutdown, session data is deleted and freed memory is zeroed.
- **Faster emergency shutdown:** pulling the boot USB now powers off in about 6 seconds. This also works if the USB is pulled during suspend.
- **Firewall:**
  - Fails closed if it does not load.
  - Apps can only reach an explicit list of local proxy ports.
  - Invalid packets are dropped.
  - IPv6 is off everywhere.
  - Tor is TCP-only.
- **Tor control-port filter**, like Tails' onion-grater. Tor Browser, OnionShare and Nyx get only what they need, and no app can change Tor's configuration.
- **Tor:**
  - SOCKS is isolated per destination.
  - No world-writable socket.
  - Avoids disk writes.
- **i2pd:** its random inbound port actually opens now (1.8 dropped it). SAM is off.
- **MAC address spoofing** on every network device, done before NetworkManager. Turn it off with the boot option `nomacspoof`.
- **Screen lock:** Super+L, or System → Lock Screen. The first time, it asks you to set a session password.
- **Clipboard:** Diodon replaces ClipIt and keeps no history.
- **Kernel:**
  - IOMMU isolation and DMA protection
  - Extra Spectre mitigations
  - debugfs off
  - io_uring disabled
  - TIOCSTI blocked
  - fs.protected_fifos=2
- **Fewer setuid binaries:** ntfs-3g, chfn, chsh, ssh-keysign and gst-ptp-helper lose setuid.
- A sudo rule that could read root-only files (`date`) is restricted.
- **eMudhra/emSign root certificates are distrusted** system-wide and in all three browsers, matching Tails 7.15.1.
- Network file-sharing backends in the file manager (SMB, FTP, cloud and similar) are disabled.

## Browsers
- **Tor Browser 16.0** replaces 15.0.26:
  - **uBlock Origin** is added, and both uBlock and **NoScript** are pinned and visible on the toolbar.
  - The install is read-only and runs under an enforced AppArmor profile.
  - Downloads go to a **`~/Tor Browser`** folder, as in Tails.
- **I2P Browser** (LibreWolf 159), renamed from "Web Browser (I2P)":
  - Clearnet now goes through the **acetone I2P outproxy**, `proxy4uwdijqxac2bvdx4fuhem6njmiwukuk2gelejv2nzxka2xq.b32.i2p`, which replaces StormyCloud.
  - NoScript runs in private windows.
  - HTTPS-Only stays off, because I2P sites are plain http.
- **Local-only Firefox 159**, for the I2P Router Console, IRC and I2P Torrents, is still blocked from everything else.

## I2P
- The I2P **SOCKS proxy (4447)** now reaches the clearnet through the acetone outproxy, over new outproxy tunnels.
- **Mail over I2P:** the mail.i2p (postman) SMTP and POP3 tunnels are set up.
- Bandwidth is set to L with 30% sharing.
- The StormyCloud reseed file is downloaded fresh on every build and checked before it goes in (signature against i2pd's StormyCloud certificate, at most 14 days old); the build stops if either fails.
- **Refresh I2P reseed (via Tor)** (menu: Network): downloads a fresh reseed file over Tor (StormyCloud, then reseed.onion.im), checks its signature against i2pd's reseed certificates, installs it, clears the netDb and restarts i2pd. If both fail, nothing changes and it points you to https://reseed2.i2p.net/ and **Manual reseed file** (pick a downloaded .su3; it is checked the same way).

## Communication
- **Pidgin** is new. It runs over Tor and comes with:
  - **OTR** (v3)
  - **OMEMO** (lurch) for XMPP
  - **Message Carbons**
- **Claws Mail** replaces Sylpheed. The mail.i2p account comes preconfigured, with no HTML or remote content.
- **Gajim 2.1** has OMEMO built in, and its default proxy is now Tor.
- **The Lounge (IRC):**
  - Ready-made networks for each IRC tunnel: IRC2P, IRC2P (echelon), Ilita, Ilita (r4sas) and Ilita (acetone).
  - A different random nick on each network, so your identities aren't linked.
  - Joins no channels by default.

## New and changed apps
- **Unlock Volume (new):** opens LUKS1/2, BitLocker, VeraCrypt and TrueCrypt drives and containers.
  - Supports passphrases, recovery keys, keyfiles, PIM, and hidden or system volumes.
  - Lock them again from the same menu.
- **OnionShare** (new) uses the system Tor.
- **Metadata Cleaner** (new), plus a **"Remove metadata"** right-click action in the file manager.
- **Loupe** is the new image viewer, sandboxed as in Tails.
- **Archive Manager** (file-roller with 7-Zip) is new, for zip, 7z, tar and rar.
- Several apps now use Debian packages instead of AppImages:
  - **KeePassXC** 2.7.10
  - **Kleopatra**, which replaces GpgFrontend
  - **Audacity** 3.7.3
- **Feather:** Tor only, onion nodes only.
- **VLC:** no metadata lookups over the network.
- **Updated:** LibreOffice 25.2, GIMP 3.0, VLC 3.0.24, Tor 0.4.9.15, i2pd 3.0.0 (trixie build).

## Known limitations
- Snowflake and WebTunnel bridges are installed but need DNS, which Prestium deliberately doesn't provide. obfs4 bridges work.
- LibreWolf's AppArmor profile is in complain (log-only) mode for now.
- The ISO is larger than 1.8: Debian 13, the full firmware set and the new apps add to it.
