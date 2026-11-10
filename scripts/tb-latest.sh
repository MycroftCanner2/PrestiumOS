# Prestium 2.1: find the newest Tor Browser release at build time (sourced by scripts/fetch-thirdparty.sh).
# Only the version number is taken from the Tor Project's update service (aus1, HTTPS, no redirects);
# the download URL is built from it on dist.torproject.org, and fetch-thirdparty.sh then verifies the
# tarball's OpenPGP signature with the pinned Tor Browser key (TB_KEY). The version must not be older
# than TB_MIN_VERSION (no downgrade to an older release that is still validly signed).
TB_JSON_URL=${PRESTIUM_TB_JSON_URL:-https://aus1.torproject.org/torbrowser/update_3/release/downloads.json}

tb_version_ok() { # 16.0, 16.0.1, 15.0.26 (two to four numeric parts, no leading zeros or junk)
  case $1 in ''|*[!0-9.]*) return 1;; esac   # 2.1 audit: one line only (grep -x matches any line)
  printf '%s' "$1" | grep -qxE '[1-9][0-9]{0,2}(\.(0|[1-9][0-9]{0,3})){1,3}'
}
tb_version_ge() { # $1 >= $2 (version order)
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}
tb_latest() { # prints the newest Tor Browser version, or fails with a message on stderr
  local json v
  if [ -n "${PRESTIUM_TB_JSON_FILE:-}" ]; then json=$(cat "$PRESTIUM_TB_JSON_FILE") || return 1
  else
    json=$(curl -sf --proto =https --max-redirs 0 --retry 3 -m 120 "$TB_JSON_URL") \
      || { echo "ERROR: cannot read the Tor Browser release list ($TB_JSON_URL)" >&2; return 1; }
  fi
  v=$(printf '%s' "$json" | python3 -c 'import json,sys; d=json.load(sys.stdin); v=d.get("version"); import re; print(v if isinstance(v,str) and re.fullmatch(r"[0-9.]{1,32}", v) else "")' 2>/dev/null)
  tb_version_ok "$v" || { echo "ERROR: Tor Browser release list gave no usable version (${v:-none})" >&2; return 1; }
  tb_version_ge "$v" "$TB_MIN_VERSION" \
    || { echo "ERROR: Tor Browser release list says $v, older than the minimum $TB_MIN_VERSION (refusing a downgrade)" >&2; return 1; }
  printf '%s\n' "$v"
}
tb_tarball_version() { # TARBALL: prints the release version from the signed tarball's own tbb_version.json
  # (release channel, linux-x86_64 only). The signature does not bind the file name, so this binds
  # the tarball to the version that was asked for.
  python3 -I -c '
import json, re, sys, tarfile
with tarfile.open(sys.argv[1], "r:xz") as t:
    f = t.extractfile("tor-browser/Browser/tbb_version.json")
    d = json.loads(f.read(4096))
v = d.get("version")
if d.get("channel") != "release" or d.get("architecture") != "linux-x86_64" \
        or not isinstance(v, str) or not re.fullmatch(r"[0-9.]{1,32}", v):
    sys.exit(1)
print(v)' "$1" 2>/dev/null
}
