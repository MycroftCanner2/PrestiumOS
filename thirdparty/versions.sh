# Prestium 2.0: third-party software that is not in Debian (sourced by scripts/fetch-thirdparty.sh).
# Each download is checked against the publisher's OpenPGP signature (keys in thirdparty/keys/)
# AND against the SHA-256 pinned here. To update: change the version, set the SHA to "" and run
# scripts/fetch-thirdparty.sh --repin (it verifies the signature, then prints the new SHA to pin).
# LibreWolf and Tor come from their signed apt repositories (config/archives/), not from here.
# i2pd is PurpleI2P's .deb from GitHub releases, pinned below by SHA-256 only (no signature is published).
# 2.1: Prestium Translate's engine (bergamot-translator, built from a pinned source tar by hook 0210) and
# Mozilla's en->ru/ru->en models (Mozilla's signed Remote Settings records + pinned SHA-256), at the end.
# 2.1: Tor Browser and Feather are the newest signed releases unless pinned (below).
# 2.1: uBlock Origin is not pinned here either: every build takes the newest Mozilla-signed release
# from addons.mozilla.org (scripts/amo-latest.py; Mozilla's AMO root in thirdparty/keys/mozilla-amo-root.pem).

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

NODE_VERSION=v24.22.3
NODE_SHA256=4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb   # node-$V-linux-x64.tar.xz; SHASUMS256.txt.asc signed by a Node.js releaser
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

# 2.1: Feather is the newest release at build time, like Tor Browser (scripts/feather-latest.sh asks
# GitHub for feather-wallet/feather's latest release, never a draft or prerelease; the zip and .asc come
# from github.com/feather-wallet/feather/releases/download/<version>/). No SHA-256 can be pinned for a
# release that isn't out yet, so the zip's signature by FEATHER_KEY (a keyring holding only
# thirdparty/keys/feather.asc) is the trust anchor, with FEATHER_MIN_VERSION as a floor against
# rollbacks. The build log shows the version and SHA-256 it shipped ("OK FEATHER <sha> (Feather <v>,
# ...)"), and the image manifest records them. To pin one release instead (reproducible builds), set
# FEATHER_VERSION to it and FEATHER_SHA256 to its SHA-256, or build with
# PRESTIUM_FEATHER_VERSION=<v> PRESTIUM_FEATHER_SHA256=<sha> (2.9.1: f1d40d619664d9e6318c086b9015ee72bc69741ec86148ce2ea2ef75ef47feed).
FEATHER_VERSION=${PRESTIUM_FEATHER_VERSION:-latest}
FEATHER_SHA256=${PRESTIUM_FEATHER_SHA256:-}
FEATHER_MIN_VERSION=2.9.1                               # never ship anything older (raise it, never lower it)
FEATHER_KEY=8185E158A33330C7FD61BC0D1F76E155CEFBA71C     # Feather release key (dsc)

# i2pd: https://github.com/PurpleI2P/i2pd/releases/download/$I2PD_VERSION/i2pd_${I2PD_DEB_VERSION}_amd64.deb
# (PurpleI2P's trixie build). PurpleI2P publishes no detached signature for its .deb files, so this
# SHA-256, committed here, is the only trust anchor (no OpenPGP check). To update: set the versions, set
# I2PD_SHA256 to "", run scripts/fetch-thirdparty.sh --repin, and check the printed value against the
# release page's asset digest before pinning it. Installed in the chroot by hook 0005-prestium-i2pd.
I2PD_VERSION=3.0.0
I2PD_DEB_VERSION=3.0.0-1trixie1
I2PD_SHA256=c48c9e2e44fb67e9c650b01225ccf816d8b2cecf3246a5112ccdcf5a6e4fbe70

# Prestium Translate (2.1). Engine: Bergamot, the engine of Firefox Translations (bergamot-translator, MPL-2.0;
# github.com/browsermt/bergamot-translator). Debian 13 has neither translateLocally nor bergamot-translator, so
# hook 0210-prestium-translate builds it in the chroot (CPU only, x86-64 with SSE4.1, no BLAS library: Ruy for
# float GEMM, intgemm for the int8 models). The project publishes no signed source release, and GitHub's
# tarballs leave out its git submodules, so fetch-thirdparty.sh clones BERGAMOT_COMMIT with only the
# submodules the CPU build needs (BERGAMOT_MODULES, each at the commit the parent records), exports each with
# "git archive" (appended with tar -A, in this order) and checks the tar against BERGAMOT_TAR_SHA256. No
# signature exists, so the pinned commit and this SHA-256 are the trust anchor (as for irc-framework).
# To update: set the commit, set BERGAMOT_TAR_SHA256 to "", run scripts/fetch-thirdparty.sh --repin.
BERGAMOT_COMMIT=9271618ebbdc5d21ac4dc4df9e72beb7ce644774      # main, 2024-05-12
BERGAMOT_MODULES=". 3rd_party/marian-dev 3rd_party/ssplit-cpp 3rd_party/marian-dev/src/3rd_party/sentencepiece 3rd_party/marian-dev/src/3rd_party/intgemm 3rd_party/marian-dev/src/3rd_party/ruy 3rd_party/marian-dev/src/3rd_party/ruy/third_party/cpuinfo"
BERGAMOT_TAR_SHA256=adf861f4a569848abe60216cf05e68658d4462b5a1b9b2fe39a91b5c95a04764
# Models: Mozilla's Firefox Translations models (MPL-2.0), English->Russian and Russian->English, version 2.1 of
# each (int8 "base-memory" models with a shortlist: model.<pair>.intgemm.alphas.bin 31.6 MB, lex.50.50.<pair>.s2t.bin
# 2.8/4.4 MB, vocab.<pair>.spm 0.9 MB). Firefox gets them from Mozilla's Remote Settings collection
# main/translations-models, whose records (file name, size, SHA-256) carry Mozilla's content signature:
# scripts/translate-models.py checks that signature (chain to the pinned AMO root in thirdparty/keys/
# mozilla-amo-root.pem), takes each file's size and SHA-256 from its signed record, downloads it, and
# fetch-thirdparty.sh then compares each SHA-256 with the pin below. To update: set the version, set its three
# SHA-256 values to "", run --repin (it prints what Mozilla's signed records name).
TR_ENRU_VERSION=2.1
TR_ENRU_MODEL_SHA256=184cb5cda528eeefc0f75f5d0035d787b71d74af135e3c5608d01ae02ecfb920
TR_ENRU_LEX_SHA256=4d91839726b960e70b6d05c53d0cffd16262832b1c0e1ea99d66f412dcc6a239
TR_ENRU_VOCAB_SHA256=56ee63e14e8cb926c394242adc3ed7cc602644c3d33058cff2ce2959d52a6258
TR_RUEN_VERSION=2.1
TR_RUEN_MODEL_SHA256=aa0efa194b3dbd2da129ba0b8db8ef139126cb0914e57072f62061294746f1e2
TR_RUEN_LEX_SHA256=c944e753f298bbdf6506388de7257fb48cbd12c83e2807e2c284fc323771895b
TR_RUEN_VOCAB_SHA256=de8af5f87e231ee4016cec4bb482e6b584cb1ca34dcb624fc7b8398f25bb35df
