#!/bin/bash
# Prestium 2.1: irc-framework is installed from a local "git archive" tarball, never by npm packing the
# git dependency (which runs its "prepare": babel/webpack from the registry, on the build host).
# Offline check of the mechanism fetch-thirdparty.sh uses (scripts/npm-local-tarball.py): a project whose
# lockfile resolves a git dependency the same way The Lounge's does (a registry package, "mid", requests it
# as "github:kiwiirc/irc-framework#9578e59") is installed with "npm ci --offline --git=false": no registry,
# no git. The stand-in package has a prepare script that would leave a marker. Source checks first: that
# fetch-thirdparty.sh pins and uses the tarball.
# Run with the host's npm and, if available, npm 9.2.0 (Debian 13's npm, whose arborist threw "Invalid
# comparator: github:..." on the old package.json override): NPM9=/path/to/npm uses that one; otherwise
# npm@9.2.0 is installed into the temp dir (network; NPM9=skip or a failed install SKIPs that case).
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
grep -q 'thelounge-\$THELOUNGE_VERSION-r22' "$F" && ok "fetch: new The Lounge cache name (r22)" || bad "cache name not bumped"
grep -q 'irc-framework/dist present' "$F" && grep -q 'irc-framework file differs from commit' "$F" \
  && grep -q 'does not resolve irc-framework to \$IRC_FRAMEWORK_COMMIT' "$F" && ok "fetch: dist/, file-by-file and lockfile commit checks kept" || bad "fetch: a check was removed"
grep -q '"resolved": "git+ssh://git@github.com/kiwiirc/irc-framework.git#'"$IRC_FRAMEWORK_COMMIT"'"' "$R/thirdparty/thelounge/package-lock.json" \
  && ok "committed lockfile unchanged (git spec, pinned commit)" || bad "committed lockfile changed"
command -v npm >/dev/null || { echo "SKIP npm missing: offline install not run"; exit $fail; }
command -v openssl >/dev/null || { echo "SKIP openssl missing: offline install not run"; exit $fail; }
# stand-in for irc-framework (prepare would write a marker), packed like fetch does: git archive, no scripts
mkdir -p "$T/src/src" && cd "$T/src" || exit 1
printf '%s\n' '{"name":"irc-framework","version":"4.14.0","main":"src/index.js","scripts":{"prepare":"touch '"$T"'/PREPARE-RAN"},"devDependencies":{"webpack":"^5.0.0"}}' > package.json
echo 'module.exports = 1;' > src/index.js; echo x > README.md; echo MIT > LICENSE.txt
git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm t
git archive --format=tar --prefix=package/ HEAD package.json README.md LICENSE.txt src > "$T/irc.tar"
# a registry-style parent that depends on it by git spec (like thelounge): its tarball is seeded into each
# npm's cache so the lockfile can resolve it to a registry URL and --offline still finds it
mkdir -p "$T/mid/package" && cd "$T/mid" || exit 1
printf '%s\n' '{"name":"mid","version":"1.0.0","dependencies":{"irc-framework":"github:kiwiirc/irc-framework#9578e59"}}' > package/package.json
tar -czf "$T/mid-1.0.0.tgz" package
MI="sha512-$(openssl dgst -sha512 -binary "$T/mid-1.0.0.tgz" | base64 -w0)"
mkdir -p "$T/p0" && cd "$T/p0" || exit 1
cp "$T/irc.tar" irc-framework.tar
printf '%s\n' '{"name":"p","private":true,"dependencies":{"mid":"1.0.0"}}' > package.json
cat > package-lock.json <<J
{"name":"p","lockfileVersion":3,"requires":true,"packages":{
 "":{"name":"p","dependencies":{"mid":"1.0.0"}},
 "node_modules/mid":{"version":"1.0.0","resolved":"https://registry.npmjs.org/mid/-/mid-1.0.0.tgz","integrity":"$MI","dependencies":{"irc-framework":"github:kiwiirc/irc-framework#9578e59"}},
 "node_modules/irc-framework":{"version":"4.14.0","resolved":"git+ssh://git@github.com/kiwiirc/irc-framework.git#$IRC_FRAMEWORK_COMMIT","license":"MIT"}}}
J
printf 'ignore-scripts=true\n' > .npmrc
# the rewrite itself (working copy only): resolved + integrity, parent git spec -> locked version, no override
cp -a "$T/p0" "$T/rw" && python3 "$R/scripts/npm-local-tarball.py" "$T/rw" irc-framework irc-framework.tar >/dev/null 2>&1 || bad "npm-local-tarball.py failed"
python3 - "$T/rw" <<'P' && ok "rewrite: resolved file:irc-framework.tar + sha512, parent git spec -> 4.14.0, no override" || bad "rewrite: unexpected lockfile/package.json"
import json, sys
d = sys.argv[1]; l = json.load(open(d + "/package-lock.json")); p = json.load(open(d + "/package.json"))
e = l["packages"]["node_modules/irc-framework"]
assert e["resolved"] == "file:irc-framework.tar" and e["integrity"].startswith("sha512-"), e
assert l["packages"]["node_modules/mid"]["dependencies"]["irc-framework"] == "4.14.0", l["packages"]["node_modules/mid"]
assert "git" not in json.dumps(l).replace("github.com/kiwiirc", ""), "git spec left in lockfile"
assert "overrides" not in p, p
P
grep -q 'github:\|git+' "$T/rw/package-lock.json" && bad "rewritten lockfile still has a git spec" || ok "rewritten lockfile has no git/github spec left"

install_case(){ # label npm
  local lbl=$1 npm=$2 w=$T/case-$1 c=$T/cache-$1
  rm -rf "$w" "$T/PREPARE-RAN"; cp -a "$T/p0" "$w"; cd "$w" || return
  "$npm" cache add "$T/mid-1.0.0.tgz" --cache "$c" >/dev/null 2>&1 || { bad "$lbl: could not seed the npm cache"; return; }
  # without the rewrite, npm wants git (and would pack + prepare): --git=false makes that fail
  "$npm" ci --cache "$c" --offline --git=false --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 \
    && bad "$lbl: npm installed the git dependency without the tarball" || ok "$lbl: unmodified lockfile: npm needs git (refused with --git=false)"
  rm -rf node_modules
  python3 "$R/scripts/npm-local-tarball.py" "$w" irc-framework irc-framework.tar >/dev/null 2>&1 || bad "$lbl: npm-local-tarball.py failed"
  if "$npm" ci --cache "$c" --offline --git=false --omit=dev --omit=optional --ignore-scripts --no-audit --no-fund >"$T/npm-$lbl.log" 2>&1; then
    ok "$lbl: rewritten lockfile: npm ci --offline --git=false installs (no registry, no git)"
  else bad "$lbl: npm ci from the tarball failed: $(grep -m3 'ERR\|error' "$T/npm-$lbl.log")"; fi
  [ -f node_modules/irc-framework/src/index.js ] && cmp -s node_modules/irc-framework/src/index.js "$T/src/src/index.js" \
    && [ -f node_modules/mid/package.json ] && ok "$lbl: installed files are the tarball's" || bad "$lbl: irc-framework not installed from the tarball"
  [ ! -e "$T/PREPARE-RAN" ] && [ ! -e node_modules/irc-framework/dist ] && [ ! -e node_modules/webpack ] \
    && ok "$lbl: prepare did not run, no devDependencies installed" || bad "$lbl: prepare ran or devDependencies installed"
}
install_case "npm-$(npm --version)" npm
N9=${NPM9:-}
if [ "$N9" = skip ]; then N9=
elif [ -z "$N9" ]; then
  npm install -g --prefix "$T/npm9" npm@9.2.0 --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 && N9=$T/npm9/bin/npm
fi
if [ -n "$N9" ] && [ "$("$N9" --version 2>/dev/null)" = 9.2.0 ]; then install_case npm-9.2.0 "$N9"
else echo "SKIP npm 9.2.0 (Debian 13) case: not available (set NPM9=/path/to/npm-9.2.0, or allow network for npm@9.2.0)"; fi
[ $fail = 0 ] && echo "irc-framework tarball: OK"; exit $fail
