#!/bin/bash
# Security review F-04 and F-15: the kernel command line keeps kernel pointer hashing and turns on
# every CPU mitigation with SMT off.
#  - F-04: slub_debug (any value) makes kernels before 6.17 switch pointer hashing off
#    (no_hash_pointers, commit 792702911f58), so %p in logs and /proc prints real kernel addresses.
#    Its hardening is kept by slab_nomerge, init_on_alloc=1, init_on_free=1 and page_poison=1.
#  - F-15: mitigations=auto,nosmt, besides the per-issue options (mds=full,nosmt, pti=on,
#    spec_store_bypass_disable=on), so every mitigation the kernel knows is on and SMT is off for
#    all the issues that need it, not only MDS.
# The cmdline guard (test_boot_cmdline_guard.sh) checks that APPEND and cmdline.policy agree.
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
A=$(sed -n 's/^APPEND="\(.*\)"$/\1/p' "$R/auto/config"); P=$R/config/includes.chroot/usr/share/prestium/boot/cmdline.policy
[ -n "$A" ] || { bad "no APPEND in auto/config"; exit 1; }
has(){ printf '%s\n' $A | grep -qx -- "$1"; }
printf '%s\n' $A | grep -q '^slub_debug' && bad "F-04: APPEND has slub_debug" || ok "F-04: no slub_debug in APPEND"
grep -Eq '^(require|allow) slub_debug' "$P" && bad "F-04: policy has slub_debug" || ok "F-04: no slub_debug in the policy"
grep -q 'slub_debug' "$R/config/binary" && bad "F-04: config/binary still has slub_debug" || ok "F-04: config/binary"
printf '%s\n' $A | grep -Eq '^(no_hash_pointers|hash_pointers=never)$' && bad "F-04: pointer hashing turned off" || ok "F-04: pointer hashing on"
for t in slab_nomerge init_on_alloc=1 init_on_free=1 page_poison=1; do
  has "$t" && ok "F-04: kept $t" || bad "F-04: $t missing"
done
has mitigations=auto,nosmt && ok "F-15: mitigations=auto,nosmt" || bad "F-15: mitigations=auto,nosmt missing"
grep -qx 'require mitigations=auto,nosmt' "$P" && ok "F-15: policy requires it" || bad "F-15: policy"
[ "$(grep -o 'mitigations=auto,nosmt' "$R/config/binary" | wc -l)" = 2 ] && ok "F-15: config/binary (live and failsafe)" || bad "F-15: config/binary"
printf '%s\n' $A | grep -Eq '^(mitigations|pti|mds|spectre_v2|spectre_bhi|spec_store_bypass_disable|l1tf|tsx_async_abort|mmio_stale_data|retbleed|srbds|gather_data_sampling|reg_file_data_sampling)=off$|^nospectre|^nopti$' && bad "a mitigation is turned off" || ok "no mitigation turned off"
for t in mds=full,nosmt pti=on spec_store_bypass_disable=on; do has "$t" && ok "kept $t" || bad "$t missing"; done
# F-16: lockdown=confidentiality everywhere, and the docs don't still promise integrity
has lockdown=confidentiality && ! has lockdown=integrity && ok "F-16: APPEND has lockdown=confidentiality" || bad "F-16: APPEND lockdown"
grep -qx 'require lockdown=confidentiality' "$P" && ok "F-16: policy requires it" || bad "F-16: policy"
[ "$(grep -o 'lockdown=confidentiality' "$R/config/binary" | wc -l)" = 2 ] && ! grep -q 'lockdown=integrity' "$R/config/binary" && ok "F-16: config/binary (live and failsafe)" || bad "F-16: config/binary"
grep -n 'lockdown=integrity' "$R/README.md" "$R/BUILDING.md" && bad "F-16: README/BUILDING still say lockdown=integrity" || ok "F-16: docs say confidentiality"
exit $fail
