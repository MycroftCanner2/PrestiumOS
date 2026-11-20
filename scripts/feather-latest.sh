# Prestium 2.1: find the newest Feather release at build time (sourced by scripts/fetch-thirdparty.sh),
# the same way scripts/tb-latest.sh does for Tor Browser. Only the version number is taken from GitHub:
# the "latest release" of feather-wallet/feather from the releases API (HTTPS, no redirects; GitHub's
# "latest" is never a draft or a prerelease, and both flags are checked again here). If the API can't be
# read (e.g. its rate limit), the redirect of github.com/feather-wallet/feather/releases/latest to
# .../releases/tag/<version> is used instead. The download URLs are built from the version, and
# fetch-thirdparty.sh then verifies the zip's OpenPGP signature with the pinned Feather key (FEATHER_KEY,
# a keyring holding only thirdparty/keys/feather.asc). The version must not be older than
# FEATHER_MIN_VERSION (no downgrade to an older release that is still validly signed).
FEATHER_API_URL=${PRESTIUM_FEATHER_API_URL:-https://api.github.com/repos/feather-wallet/feather/releases/latest}
FEATHER_LATEST_URL=${PRESTIUM_FEATHER_LATEST_URL:-https://github.com/feather-wallet/feather/releases/latest}

feather_version_ok() { # 2.9.1, 3.0 (two to four numeric parts, no leading zeros, no "v", one line only)
  case $1 in ''|*[!0-9.]*) return 1;; esac
  printf '%s' "$1" | grep -qxE '[1-9][0-9]{0,2}(\.(0|[1-9][0-9]{0,3})){1,3}'
}
feather_version_ge() { # $1 >= $2 (version order)
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}
feather_api_version() { # JSON on stdin -> the tag of a published, non-prerelease release, or nothing
  python3 -I -c '
import json, re, sys
d = json.load(sys.stdin)
v = d.get("tag_name")
if d.get("draft") is False and d.get("prerelease") is False and isinstance(v, str) and re.fullmatch(r"[0-9.]{1,32}", v):
    print(v)' 2>/dev/null
}
feather_redirect_version() { # Location header value -> the tag, or nothing
  printf '%s' "$1" | sed -nE 's#^https://github\.com/feather-wallet/feather/releases/tag/([0-9.]{1,32})$#\1#p'
}
feather_latest() { # prints the newest Feather version, or fails with a message on stderr
  local json v="" loc
  if [ -n "${PRESTIUM_FEATHER_JSON_FILE:-}" ]; then
    v=$(feather_api_version < "$PRESTIUM_FEATHER_JSON_FILE")
  elif json=$(curl -sf --proto =https --max-redirs 0 --retry 3 -m 120 -H 'Accept: application/vnd.github+json' "$FEATHER_API_URL"); then
    v=$(printf '%s' "$json" | feather_api_version)
  else
    echo "Feather: cannot read the GitHub releases API ($FEATHER_API_URL), trying $FEATHER_LATEST_URL" >&2
    loc=$(curl -sf --proto =https --max-redirs 0 --retry 3 -m 120 -o /dev/null -w '%{redirect_url}' "$FEATHER_LATEST_URL") \
      || { echo "ERROR: cannot find the newest Feather release on GitHub" >&2; return 1; }
    v=$(feather_redirect_version "$loc")
  fi
  feather_version_ok "$v" || { echo "ERROR: GitHub gave no usable Feather release version (${v:-none})" >&2; return 1; }
  feather_version_ge "$v" "$FEATHER_MIN_VERSION" \
    || { echo "ERROR: GitHub's newest Feather release is $v, older than the minimum $FEATHER_MIN_VERSION (refusing a downgrade)" >&2; return 1; }
  printf '%s\n' "$v"
}
feather_zip_version() { # ZIP: prints the version from the signed zip's only entry, feather-<version>.
  # The signature does not bind the file name, so this binds the zip to the version that was asked for.
  python3 -I -c '
import re, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    n = z.namelist()
m = re.fullmatch(r"feather-([0-9.]{1,32})", n[0]) if len(n) == 1 else None
if not m:
    sys.exit(1)
print(m.group(1))' "$1" 2>/dev/null
}
