#!/usr/bin/python3
"""Prestium 2.1: point an npm project's lockfile at a local tarball for one package, so "npm ci"
installs that tarball instead of cloning and packing a git dependency (packing a git dependency runs
its "prepare" script, which pulls unpinned devDependencies from the registry and runs them on the
build host, even with --ignore-scripts).
  npm-local-tarball.py DIR NAME TARBALL
DIR holds package.json and package-lock.json (a working copy, not the committed files); TARBALL is a
file name inside DIR. In the lockfile:
 - packages["node_modules/NAME"] gets resolved "file:TARBALL" and the tarball's sha512 integrity;
 - every dependency spec that requests NAME by git URL (git+ssh:, git+https:, github:, owner/repo#ref,
   ...), e.g. packages["node_modules/thelounge"].dependencies["irc-framework"], becomes the entry's
   exact "version" (4.14.0), which that entry satisfies, so the parent's request is met by the
   locked tarball and npm has no git spec left to clone. (Not "file:TARBALL": a file: spec in a
   nested package's dependencies resolves relative to that package, node_modules/thelounge/TARBALL.)
No package.json "overrides" entry is written (and one for NAME is removed): rewriting the parent specs
is enough for npm 9 and 11, and npm 9.2.0 (Debian 13) throws "Invalid comparator" when an override
meets a dependency edge whose spec is not semver (arborist OverrideSet.getEdgeRule calls
semver.intersects(edge.spec, ...)), which npm ci then misreports as a missing package-lock.json.
Nothing else in either file changes; package.json is rewritten only if it changed."""
import base64, hashlib, json, os, re, sys

DEP_FIELDS = ("dependencies", "optionalDependencies", "peerDependencies", "devDependencies")
# npm-package-arg's git forms: git URLs, hosted shortcuts, and "owner/repo[#ref]" GitHub shorthand
GIT_SPEC = re.compile(r"^(git\+[a-z]+:|git:|github:|gitlab:|bitbucket:|gist:|[^@:/\s][^:/\s]*/[^/\s]+$)")

def is_git(spec):
    return isinstance(spec, str) and bool(GIT_SPEC.match(spec.strip())) and not spec.startswith("file:")

def main(d, name, tar):
    path = os.path.join(d, tar)
    with open(path, "rb") as f:
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(f.read()).digest()).decode()
    lp, pp = os.path.join(d, "package-lock.json"), os.path.join(d, "package.json")
    with open(lp) as f:
        lock = json.load(f)
    with open(pp) as f:
        pkg = json.load(f)
    pkgs = lock.get("packages", {})
    key = "node_modules/" + name
    if key not in pkgs:
        sys.exit("npm-local-tarball: %s not in %s" % (key, lp))
    e = pkgs[key]
    e["resolved"], e["integrity"] = "file:" + tar, integrity
    pkg0, spec, n = json.dumps(pkg), e.get("version"), 0
    if not spec:
        sys.exit("npm-local-tarball: %s has no version in %s" % (key, lp))
    for loc, ent in pkgs.items():
        for field in DEP_FIELDS:
            deps = ent.get(field) or {}
            if is_git(deps.get(name)):
                deps[name] = spec; n += 1
                if loc == "":   # the root's specs must stay in sync with package.json for npm ci
                    pkg.setdefault(field, {})[name] = spec
    ov = pkg.get("overrides")
    if isinstance(ov, dict) and name in ov:
        del ov[name]
        if not ov:
            del pkg["overrides"]
    for p, v in ((lp, lock), (pp, pkg)):
        if p == pp and json.dumps(pkg) == pkg0:
            continue
        with open(p, "w") as f:
            json.dump(v, f, indent=2); f.write("\n")
    print(integrity)
    print("npm-local-tarball: %s -> file:%s (parent specs -> %s), %d git dependency spec(s) rewritten" % (name, tar, spec, n), file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
