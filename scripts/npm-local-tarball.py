#!/usr/bin/python3
"""Prestium 2.1: point an npm project's lockfile entry for one package at a local tarball, so
"npm ci" installs that tarball instead of cloning and packing a git dependency (packing a git
dependency runs its "prepare" script, which pulls unpinned devDependencies from the registry and
runs them on the build host, even with --ignore-scripts).
  npm-local-tarball.py DIR NAME TARBALL
DIR holds package.json and package-lock.json (a working copy, not the committed files); TARBALL is a
file name inside DIR. The lockfile entry gets resolved "file:TARBALL" and the tarball's sha512
integrity, and package.json an "overrides" entry for NAME, without which npm sees the parent's git
spec as unmet and clones the git URL anyway. Nothing else in either file changes."""
import base64, hashlib, json, os, sys

def main(d, name, tar):
    path = os.path.join(d, tar)
    with open(path, "rb") as f:
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(f.read()).digest()).decode()
    lp, pp = os.path.join(d, "package-lock.json"), os.path.join(d, "package.json")
    lock, pkg = json.load(open(lp)), json.load(open(pp))
    key = "node_modules/" + name
    if key not in lock.get("packages", {}):
        sys.exit("npm-local-tarball: %s not in %s" % (key, lp))
    e = lock["packages"][key]
    e["resolved"], e["integrity"] = "file:" + tar, integrity
    pkg.setdefault("overrides", {})[name] = "file:" + tar
    for p, v in ((lp, lock), (pp, pkg)):
        with open(p, "w") as f:
            json.dump(v, f, indent=2); f.write("\n")
    print(integrity)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
