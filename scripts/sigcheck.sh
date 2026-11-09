# Prestium 2.1: OpenPGP signature policy for scripts/fetch-thirdparty.sh (sourced; also used by tests/).
# gpg and gpgv print VALIDSIG and exit 0 for a cryptographically good signature by an EXPIRED key
# (with EXPKEYSIG/KEYEXPIRED), so neither the exit status nor VALIDSIG alone is enough: read every
# status line. sigstatus_ok NAME STATUS-TEXT FPR
#   FPR: the pinned primary fingerprint; it must appear on the VALIDSIG line (VALIDSIG carries the
#   signing key's fingerprint and, as its last field, the primary key's). Empty FPR (Node.js keybox,
#   where the keybox is the pin): any VALIDSIG.
sigstatus_ok(){
  local name=$1 st=$2 fpr=$3
  if printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] (REVKEYSIG|KEYREVOKED)( |$)'; then
    echo "ERROR: $name is signed by a REVOKED key (do not use it; check the publisher's current key)"; return 1
  fi
  if printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] (EXPKEYSIG|EXPSIG)( |$)'; then
    echo "ERROR: $name: the signing key or the signature has EXPIRED (refresh the key in thirdparty/keys/)"; return 1
  fi
  if printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] (BADSIG|ERRSIG)( |$)'; then
    echo "ERROR: bad signature on $name"; return 1
  fi
  if ! printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] GOODSIG '; then
    echo "ERROR: bad signature on $name (no good signature)"; return 1
  fi
  if [ -n "$fpr" ]; then
    printf '%s\n' "$st" | grep -E '^\[GNUPG:\] VALIDSIG ' | grep -qw -- "$fpr" \
      || { echo "ERROR: bad signature on $name (not made by the pinned key $fpr)"; return 1; }
  else
    printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] VALIDSIG ' || { echo "ERROR: bad signature on $name"; return 1; }
  fi
  return 0
}
