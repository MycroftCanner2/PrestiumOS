#!/bin/bash
# Prestium 2.1: irc-framework is installed from a local "git archive" tarball, never by npm packing the
# git dependency (which runs its "prepare": babel/webpack from the registry, on the build host).
# Offline check of the mechanism fetch-thirdparty.sh uses (scripts/npm-local-tarball.py): a project whose
# lockfile resolves a git dependency the same way The Lounge's does is installed with
# "npm ci --cache "$T/npmcache" --offline --git=false": no registry, no git. The stand-in package has a prepare script that
# would leave a marker. Then source checks that fetch-thirdparty.sh pins and uses the tarball.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
F=$R/scripts/fetch-thirdparty.sh; V=$R/thirdparty/versions.sh
. "$V"
[ ${#IRC_FRAMEWORK_TAR_SHA256} = 64 ] && ok "versions.sh pins the irc-framework tarball SHA-256" || bad "no tarball pin"
grep -q 'git -C "\$IG" archive --format=tar --prefix=package/ "\$IRC_FRAMEWORK_COMMIT" \$IRC_FRAMEWORK_FILES' "$F" \
  && grep -q 'pin IRC_FRAMEWORK_TAR "\$IT" "\$IRC_FRAMEWORK_TAR_SHA256"' "$F" && ok "fetch: tarball from git archive, SHA-256 checked" || bad "fetch: tarball not built/pinned"
grep -q 'npm-local-tarball.py" "\$L" irc-framework irc-framework.tar' "$F" && grep -q 'npm ci .*--git=false' "$F" \
  && ok "fetch: npm ci installs the tarball with git disabled" || bad "fetch: npm may still use the git URL"
grep -q 'thelounge-\$THELOUNGE_VERSION-r21' "$F" && ok "fetch: new The Lounge cache name" || bad "cache name not bumped"
grep -q 'irc-framework/dist present' "$F" && grep -q 'irc-framework file differs from commit' "$F" \
  && grep -q 'does not resolve irc-framework to \$IRC_FRAMEWORK_COMMIT' "$F" && ok "fetch: dist/, file-by-file and lockfile commit checks kept" || bad "fetch: a check was removed"
grep -q '"resolved": "git+ssh://git@github.com/kiwiirc/irc-framework.git#'"$IRC_FRAMEWORK_COMMIT"'"' "$R/thirdparty/thelounge/package-lock.json" \
  && ok "committed lockfile unchanged (git spec, pinned commit)" || bad "committed lockfile changed"
command -v npm >/dev/null || { echo "SKIP npm missing: offline install not run"; exit $fail; }
# stand-in for irc-framework (prepare would write a marker), packed like fetch does: git archive, no scripts
mkdir -p "$T/src/src" && cd "$T/src"
printf '%s\n' '{"name":"irc-framework","version":"4.14.0","main":"src/index.js","scripts":{"prepare":"touch '"$T"'/PREPARE-RAN"},"devDependencies":{"webpack":"^5.0.0"}}' > package.json
echo 'module.exports = 1;' > src/index.js; echo x > README.md; echo MIT > LICENSE.txt
git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm t
git archive --format=tar --prefix=package/ HEAD package.json README.md LICENSE.txt src > "$T/irc.tar"
# a parent that depends on it by git spec, packed the same way (file: tarball with integrity)
mkdir -p "$T/mid" && cd "$T/mid"
printf '%s\n' '{"name":"mid","version":"1.0.0","dependencies":{"irc-framework":"github:kiwiirc/irc-framework#9578e59"}}' > package.json
tar --transform 's,^,package/,' -cf "$T/mid.tar" package.json
mkdir -p "$T/p" && cd "$T/p"; cp "$T/mid.tar" mid.tar; cp "$T/irc.tar" irc-framework.tar
MI="sha512-$(openssl dgst -sha512 -binary mid.tar | base64 -w0)"
printf '%s\n' '{"name":"p","private":true,"dependencies":{"mid":"file:mid.tar"}}' > package.json
cat > package-lock.json <<J
{"name":"p","lockfileVersion":3,"requires":true,"packages":{
 "":{"name":"p","dependencies":{"mid":"file:mid.tar"}},
 "node_modules/mid":{"version":"1.0.0","resolved":"file:mid.tar","integrity":"$MI","dependencies":{"irc-framework":"github:kiwiirc/irc-framework#9578e59"}},
 "node_modules/irc-framework":{"version":"4.14.0","resolved":"git+ssh://git@github.com/kiwiirc/irc-framework.git#$IRC_FRAMEWORK_COMMIT","license":"MIT"}}}
J
printf 'ignore-scripts=true\n' > .npmrc
# without the rewrite, npm wants git (and would pack + prepare): --git=false makes that fail
rm -rf node_modules; npm ci --cache "$T/npmcache" --offline --git=false --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 \
  && bad "npm installed the git dependency without the tarball" || ok "unmodified lockfile: npm needs git (refused with --git=false)"
python3 "$R/scripts/npm-local-tarball.py" "$T/p" irc-framework irc-framework.tar >/dev/null || bad "npm-local-tarball.py failed"
if npm ci --cache "$T/npmcache" --offline --git=false --omit=dev --omit=optional --ignore-scripts --no-audit --no-fund >"$T/npm.log" 2>&1; then
  ok "rewritten lockfile: npm ci --offline --git=false installs (no registry, no git)"
else bad "npm ci from the tarball failed: $(tail -3 "$T/npm.log")"; fi
[ -f node_modules/irc-framework/src/index.js ] && cmp -s node_modules/irc-framework/src/index.js "$T/src/src/index.js" \
  && ok "installed files are the tarball's" || bad "irc-framework not installed from the tarball"
[ ! -e "$T/PREPARE-RAN" ] && [ ! -e node_modules/irc-framework/dist ] && [ ! -e node_modules/webpack ] \
  && ok "prepare did not run, no devDependencies installed" || bad "prepare ran or devDependencies installed"
[ $fail = 0 ] && echo "irc-framework tarball: OK"; exit $fail
