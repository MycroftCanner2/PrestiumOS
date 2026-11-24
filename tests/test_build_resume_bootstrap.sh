#!/bin/bash
# PRE-5: build.sh run again on a tree with a finished chroot (--resume, or no --clean) must not let
# "lb bootstrap" put the bootstrap cache back over it. live-build's bootstrap_cache restore runs
# "rm -rf chroot; cp -a cache/bootstrap chroot" whenever cache/bootstrap exists and the stage file
# .build/bootstrap_cache.restore does not; a fresh build only writes bootstrap_cache.save. Then the
# chroot stage's stage files skipped the package install and the image was the bare bootstrap.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); B=$R/build.sh; fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
g=$(grep -n '^if \[ -e .build/bootstrap \] && \[ -d chroot/etc \] && \[ -d cache/bootstrap \]; then$' "$B" | cut -d: -f1)
b=$(grep -n '^run_lb bootstrap$' "$B" | cut -d: -f1)
if [ -n "$g" ] && [ -n "$b" ] && [ "$g" -lt "$b" ]; then ok "build.sh guards the chroot before lb bootstrap"
else bad "build.sh: no guard for the chroot before lb bootstrap"; fi
# live-build's restore step (the installed one, if any): the stage file name the guard writes
LBC=/usr/lib/live/build/bootstrap_cache
if [ -f "$LBC" ]; then
  grep -q 'STAGE_FILE="bootstrap_cache.${_ACTION}"' "$LBC" && grep -q 'cp -a cache/bootstrap chroot' "$LBC" \
    && ok "live-build restores cache/bootstrap unless .build/bootstrap_cache.restore exists" \
    || bad "live-build's bootstrap_cache changed: check the guard's stage file"
else echo "SKIP live-build not installed (its bootstrap_cache)"; fi
# the guard on stand-in trees, then live-build's restore rule
restore(){ # $1 tree: what bootstrap_cache restore does
  [ -f "$1/.build/bootstrap_cache.restore" ] && return 0
  [ -d "$1/cache/bootstrap" ] && { rm -rf "$1/chroot"; cp -a "$1/cache/bootstrap" "$1/chroot"; }; return 0; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
[ -n "$g" ] && awk -v s="$g" 'NR>=s{print} NR>s && /^fi$/{exit}' "$B" > "$T/guard.sh"
mk(){ mkdir -p "$T/$1/.build" "$T/$1/chroot/etc" "$T/$1/cache/bootstrap/etc"; echo image > "$T/$1/chroot/etc/marker"; echo boot > "$T/$1/cache/bootstrap/etc/marker"; }
mk resume; touch "$T/resume/.build/bootstrap" "$T/resume/.build/bootstrap_cache.save"
(cd "$T/resume" && bash -eu ../guard.sh 2>/dev/null); restore "$T/resume"
[ "$(cat "$T/resume/chroot/etc/marker")" = image ] && ok "a built chroot survives lb bootstrap" || bad "lb bootstrap replaced the built chroot with the bootstrap cache"
mk fresh; rm -rf "$T/fresh/chroot"   # a clean tree with a cache: the restore still happens
(cd "$T/fresh" && bash -eu ../guard.sh 2>/dev/null); restore "$T/fresh"
[ "$(cat "$T/fresh/chroot/etc/marker" 2>/dev/null)" = boot ] && ok "a tree without a chroot still restores the bootstrap cache" || bad "the guard stopped the bootstrap cache restore on a clean tree"
mk partial; rm -f "$T/partial/.build/bootstrap"   # interrupted bootstrap (build.sh removes its chroot)
(cd "$T/partial" && bash -eu ../guard.sh 2>/dev/null)
[ ! -e "$T/partial/.build/bootstrap_cache.restore" ] && ok "an unfinished bootstrap is not marked restored" || bad "guard marked an unfinished bootstrap"
exit $fail
