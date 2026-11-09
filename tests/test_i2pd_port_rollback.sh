#!/bin/bash
# 2.0 r7 regression: prestium-i2pd-port restores the COMPLETE previous state on failure
# (i2pd.conf + /run/prestium/i2pd.port + i2pd-console.pass), and exits non-zero.
# Runs the real script with its system paths redirected into a temp dir; no root needed.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HERE/../config/includes.chroot/usr/local/sbin/prestium-i2pd-port
fail=0
t() {  # name ferm_rc getter_mode
  local name=$1 ferm_rc=$2 getter=$3 T; T=$(mktemp -d)
  mkdir -p "$T/run/prestium" "$T/var" "$T/bin"
  printf 'port = 12345\n\n[http]\naddress = 127.0.0.1\n' > "$T/var/i2pd.conf"
  echo 12345 > "$T/run/prestium/i2pd.port"; echo oldpass > "$T/run/prestium/i2pd-console.pass"
  cp "$T/var/i2pd.conf" "$T/conf.before"
  cat > "$T/bin/safefile" <<EOF
#!/bin/sh
case "\$1" in read) cat "$T/var/\$3" ;; write) cat > "$T/var/\$3" ;; esac
EOF
  cat > "$T/bin/systemctl" <<EOF
#!/bin/sh
exit $ferm_rc
EOF
  if [ "$getter" = right ]; then
    printf '#!/bin/sh\ncat "%s/run/prestium/i2pd.port"\n' "$T" > "$T/bin/getter"
  else
    printf '#!/bin/sh\necho 999\n' > "$T/bin/getter"
  fi
  chmod +x "$T/bin/"*
  sed -e "s#/usr/local/lib/prestium/safefile#$T/bin/safefile#g" \
      -e "s#/usr/local/lib/prestium/i2pd-port-get#$T/bin/getter#g" \
      -e "s#/usr/bin/systemctl#$T/bin/systemctl#g" \
      -e "s#/run/prestium#$T/run/prestium#g" \
      -e "s#install -d -o root -g root -m 0755#mkdir -p#g" \
      -e "s#chown root:user \"\$CF\" 2>/dev/null || chown root:root \"\$CF\"#true#" \
      "$SRC" > "$T/port.sh"
  sh "$T/port.sh" >/dev/null 2>"$T/err"; rc=$?
  if [ "$name" = success ]; then
    [ $rc = 0 ] && ! grep -q '^port = 12345' "$T/var/i2pd.conf" && grep -q '^auth = true' "$T/var/i2pd.conf" \
      && [ "$(cat "$T/run/prestium/i2pd.port")" != 12345 ] && echo "OK   $name" || { echo "FAIL $name rc=$rc"; cat "$T/err"; fail=1; }
  else
    [ $rc != 0 ] && cmp -s "$T/var/i2pd.conf" "$T/conf.before" \
      && [ "$(cat "$T/run/prestium/i2pd.port")" = 12345 ] && [ "$(cat "$T/run/prestium/i2pd-console.pass")" = oldpass ] \
      && grep -q "rolling back" "$T/err" && echo "OK   $name (rc=$rc)" || { echo "FAIL $name rc=$rc"; cat "$T/err"; fail=1; }
  fi
  rm -rf "$T"
}
t success 0 right
t ferm-reload-fails 1 right
t getter-mismatch 0 wrong
exit $fail
