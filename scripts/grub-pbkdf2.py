#!/usr/bin/env python3
"""Prestium 2.1: a GRUB PBKDF2 password hash for the locked boot menu (hook 9020).

  scripts/grub-pbkdf2.py > grub-password.pbkdf2     asks for the password twice (not echoed)
  scripts/grub-pbkdf2.py --random                    hash of a random password nobody knows
  scripts/grub-pbkdf2.py --check HASH                exit 0 when HASH is a well-formed GRUB hash

Output: grub.pbkdf2.sha512.<iterations>.<salt>.<hash>, the format grub-mkpasswd-pbkdf2 writes and
GRUB's password_pbkdf2 reads (PBKDF2-HMAC-SHA512, 64-byte salt and key, upper-case hex). The password
itself is never printed or stored. grub-password.pbkdf2 is gitignored; build.sh reads it.
"""
import getpass
import hashlib
import re
import secrets
import sys

ITERATIONS = 100000
MIN_ITERATIONS = 10000
FORMAT = re.compile(r"grub\.pbkdf2\.sha512\.([0-9]+)\.([0-9A-F]{32,1024})\.([0-9A-F]{128})")


def make(password: bytes, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(64)
    key = hashlib.pbkdf2_hmac("sha512", password, salt, iterations, 64)
    return "grub.pbkdf2.sha512.%d.%s.%s" % (iterations, salt.hex().upper(), key.hex().upper())


def well_formed(h: str) -> bool:
    m = FORMAT.fullmatch(h)
    return bool(m) and int(m.group(1)) >= MIN_ITERATIONS and len(m.group(2)) % 2 == 0


def main(argv):
    if argv[1:2] == ["--check"] and len(argv) == 3:
        return 0 if well_formed(argv[2]) else 1
    if argv[1:] == ["--random"]:
        print(make(secrets.token_bytes(48)))
        return 0
    if argv[1:]:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    p1 = getpass.getpass("GRUB boot menu password: ")
    if len(p1) < 12:
        print("use at least 12 characters (the hash is readable on the USB stick)", file=sys.stderr)
        return 1
    if getpass.getpass("again: ") != p1:
        print("the passwords differ", file=sys.stderr)
        return 1
    print(make(p1.encode()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
