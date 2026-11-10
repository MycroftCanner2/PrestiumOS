# Prestium 2.0: third-party software that is not in Debian (sourced by scripts/fetch-thirdparty.sh).
# Each download is checked against the publisher's OpenPGP signature (keys in thirdparty/keys/)
# AND against the SHA-256 pinned here. To update: change the version, set the SHA to "" and run
# scripts/fetch-thirdparty.sh --repin (it verifies the signature, then prints the new SHA to pin).
# LibreWolf, i2pd and Tor come from their signed apt repositories (config/archives/), not from here.

# 2.1: Tor Browser is the newest release at build time (scripts/tb-latest.sh asks the Tor Project's update
# service for the version; the tarball must carry a valid signature by TB_KEY and be no older than
# TB_MIN_VERSION). The build log shows the version and SHA-256 it shipped ("OK TB <sha> (Tor Browser <v>,
# ...)"; the image's /opt/tor-browser/Browser/tbb_version.json names the version too). To pin one release instead (reproducible builds),
# set TB_VERSION to it and TB_SHA256 to its SHA-256, or build with PRESTIUM_TB_VERSION=<v> PRESTIUM_TB_SHA256=<sha>.
TB_VERSION=${PRESTIUM_TB_VERSION:-latest}
TB_SHA256=${PRESTIUM_TB_SHA256:-}
TB_MIN_VERSION=16.0.1                                    # never ship anything older (raise it, never lower it)
TB_KEY=EF6E286DDA85EA2A4BA7DE684E2C6E8793298290          # Tor Browser Developers (signing key)

FF_VERSION=159.0.1
FF_SHA256=469ce17120018e1c95411d254cf3c5f8db2dd1768a7acde5a2a089b00072ac65
FF_KEY=14F26682D0916CDD81E37B6D61B7B526D98F0353          # Mozilla Software Releases

NODE_VERSION=v24.22.2
NODE_SHA256=48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75   # node-$V-linux-x64.tar.xz; SHASUMS256.txt.asc signed by a Node.js releaser
# 2.1 (security audit): Node.js releasers allowed to sign SHASUMS256.txt (primary keys, from the
# "Release keys" list in https://github.com/nodejs/node#release-keys, 2026-11-10). The keybox in
# thirdparty/keys has these and every past releaser's key; only these count.
NODE_KEYS="5BE8A3F6C8A5C01D106C0AD820B1A390B168D356 DD792F5973C6DE52C432CBDAC77ABFA00DDBF2B7 CC68F5A3106FF448322E48ED27F5E38D5B0A215F 890C08DB8579162FEE0DF9DB8BEAB4DFCF555EF4 C82FA3AE1CBEDC6BE46B9360C43CEC45C17AB93C 108F52B48DB57BB0CC439B2997B01419BD92F80A 655F3B5C1FB3FA8D1A0CA6BDE4A7D232B936D2FD A363A499291CBBC940DD62E41F10027AF002F8B0"

THELOUNGE_VERSION=4.5.2                                  # npm; package-lock.json integrity hashes pinned in thirdparty/thelounge/
# irc-framework 4.14.0 is a git dependency of The Lounge (kiwiirc/irc-framework#9578e59a1056499e4a03a0f0fd2c260e9aadc541)
# with no integrity in package-lock.json: fetch-thirdparty.sh checks each installed file against this commit's git checkout
IRC_FRAMEWORK_COMMIT=9578e59a1056499e4a03a0f0fd2c260e9aadc541
# 2.1: installed from "git archive --format=tar --prefix=package/ $IRC_FRAMEWORK_COMMIT $IRC_FRAMEWORK_FILES"
# (no prepare/babel/webpack), pinned here; --repin prints a new value. The files are what npm ships (.npmignore).
IRC_FRAMEWORK_FILES="package.json README.md LICENSE.txt src"
IRC_FRAMEWORK_TAR_SHA256=0c25dd1efea08411f4df8e2a950efe1d720ea76650b8df8af406499ea5583a0e

FEATHER_VERSION=2.9.1
FEATHER_SHA256=f1d40d619664d9e6318c086b9015ee72bc69741ec86148ce2ea2ef75ef47feed
FEATHER_KEY=8185E158A33330C7FD61BC0D1F76E155CEFBA71C     # featherwallet.org (dsc)

# lurch (OMEMO for libpurple), built from source in a chroot hook.
# Trust: a git commit hash cryptographically binds the full tree (same content-addressing
# guarantee as pinning a tar SHA-256 of that commit). We pin lurch + both submodules and
# verify HEAD after clone. Upstream does not publish OpenPGP-signed release tarballs for
# these tags, so commit pins are the integrity control (not weaker than an unsigned tar SHA).
LURCH_COMMIT=84f72d85a6735d64ade8f8bc8619bd61699298b2    # lurch 0.7.0 (gkdr/lurch)
AXC_COMMIT=1d4454ea42d39a2064955f2a8de5f89787743f2a      # lib/axc v0.3.4
LIBOMEMO_COMMIT=7667e54d6488aba85701bb4dd6e09fd98bfb3a2c # lib/libomemo v0.7.1
