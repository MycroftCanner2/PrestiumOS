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

# 2.1 (security audit): a DETACHED signature check (gpg --verify SIG DATA). Given an inline-signed
# (opaque) message as SIG, gpg verifies the text embedded in it, prints PLAINTEXT and only warns that
# DATA was NOT verified, with GOODSIG/VALIDSIG and exit 0. So: no PLAINTEXT, exactly one signature,
# then the policy above. sigstatus_detached_ok NAME STATUS-TEXT FPR
sigstatus_detached_ok(){
  local name=$1 st=$2 n
  if printf '%s\n' "$st" | grep -qE '^\[GNUPG:\] PLAINTEXT( |$)'; then
    echo "ERROR: $name: the signature file is not a detached signature (it carries its own signed data)"; return 1
  fi
  n=$(printf '%s\n' "$st" | grep -cE '^\[GNUPG:\] (GOODSIG|BADSIG|ERRSIG|EXPSIG|EXPKEYSIG|REVKEYSIG) ')
  [ "$n" = 1 ] || { echo "ERROR: $name: expected exactly one signature, found $n"; return 1; }
  sigstatus_ok "$@"
}

# 2.1 (security audit): like sigstatus_ok, but the signature's primary key (the last VALIDSIG field)
# must be one of a list of pinned fingerprints (Node.js: the current releasers).
# sigstatus_oneof_ok NAME STATUS-TEXT "FPR1 FPR2 ..."
sigstatus_oneof_ok(){
  local name=$1 st=$2 list=$3 p f
  [ -n "$list" ] || { echo "ERROR: $name: no pinned keys"; return 1; }
  sigstatus_ok "$name" "$st" "" || return 1
  p=$(printf '%s\n' "$st" | awk '$1 == "[GNUPG:]" && $2 == "VALIDSIG" { print $NF }')
  [ "$(printf '%s\n' "$p" | grep -c .)" = 1 ] || { echo "ERROR: $name: expected exactly one signature"; return 1; }
  for f in $list; do [ "$p" = "$f" ] && return 0; done
  echo "ERROR: $name is signed by $p, which is not one of the pinned keys"; return 1
}
