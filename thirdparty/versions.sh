# Prestium 2.0: third-party software that is not in Debian (sourced by scripts/fetch-thirdparty.sh).
# Each download is checked against the publisher's OpenPGP signature (keys in thirdparty/keys/)
# AND against the SHA-256 pinned here. To update: change the version, set the SHA to "" and run
# scripts/fetch-thirdparty.sh --repin (it verifies the signature, then prints the new SHA to pin).
# LibreWolf, i2pd and Tor come from their signed apt repositories (config/archives/), not from here.

TB_VERSION=16.0
TB_SHA256=de3370b67389c2848738cdd515bb2e3b232a4ae93290eae74185c4c43a291a24
TB_KEY=EF6E286DDA85EA2A4BA7DE684E2C6E8793298290          # Tor Browser Developers (signing key)

FF_VERSION=159.0.1
FF_SHA256=469ce17120018e1c95411d254cf3c5f8db2dd1768a7acde5a2a089b00072ac65
FF_KEY=14F26682D0916CDD81E37B6D61B7B526D98F0353          # Mozilla Software Releases

NODE_VERSION=v24.22.2
NODE_SHA256=48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75   # node-$V-linux-x64.tar.xz; SHASUMS256.txt.asc signed by a Node.js releaser

THELOUNGE_VERSION=4.5.2                                  # npm; package-lock.json integrity hashes pinned in thirdparty/thelounge/
# irc-framework 4.14.0 is a git dependency of The Lounge (kiwiirc/irc-framework#9578e59a1056499e4a03a0f0fd2c260e9aadc541)
# with no integrity in package-lock.json: fetch-thirdparty.sh checks each installed file against this commit's git checkout
IRC_FRAMEWORK_COMMIT=9578e59a1056499e4a03a0f0fd2c260e9aadc541

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
