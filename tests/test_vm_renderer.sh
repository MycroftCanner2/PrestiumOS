#!/bin/bash
# 2.1: in a VM the Wayland session uses wlroots' pixman renderer (GPU-buffer apps crashed labwc);
# on hardware it doesn't. Runs prestium-session up to labwc with stubs on PATH.
R=$(cd "$(dirname "$0")/.." && pwd); S=$R/config/includes.chroot/usr/local/bin/prestium-session
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; fail=0
ok(){ echo "OK   $*"; }; bad(){ echo "FAIL $*"; fail=1; }
mkdir "$T/bin"
printf '#!/bin/sh\n[ "${VIRT:-none}" != none ]\n' > "$T/bin/systemd-detect-virt"
printf '#!/bin/sh\nexit 1\n' > "$T/bin/sudo"
printf '#!/bin/sh\necho "R=${WLR_RENDERER:-} C=${WLR_NO_HARDWARE_CURSORS:-} ARGS=$*"\n' > "$T/bin/labwc"
chmod 755 "$T"/bin/*
o=$(env -i PATH="$T/bin:/usr/bin:/bin" VIRT=kvm sh "$S")
[ "$o" = "R=pixman C=1 ARGS=-C /etc/xdg/labwc" ] && ok "VM: pixman, no hardware cursor ($o)" || bad "VM: $o"
o=$(env -i PATH="$T/bin:/usr/bin:/bin" VIRT=none sh "$S")
[ "$o" = "R= C= ARGS=-C /etc/xdg/labwc" ] && ok "hardware: default renderer ($o)" || bad "hardware: $o"
exit $fail
