#!/usr/bin/env python3
"""Prestium 2.1 (Secure Boot): read-only facts about a UEFI PE/COFF file for hook 9040.

  scripts/efi-inspect.py sbat FILE            the .sbat section (SBAT CSV), NULs stripped
  scripts/efi-inspect.py has-cert FILE PEM     exit 0 when the certificate's DER bytes are inside FILE
                                               (shim's built-in vendor certificate: which keys it trusts)
  scripts/efi-inspect.py grub FILE             a GRUB EFI image's built-in objects: "prefix <p>",
                                               "config <first line>", "memdisk <bytes>",
                                               "disable-shim-lock" (when present) and "module <name>" lines

No signature is checked here (sbverify does that); this only reads the file. Exit 2: not a PE file or
not the expected layout.
"""
import base64
import re
import struct
import sys


def die(msg):
    print("efi-inspect: " + msg, file=sys.stderr)
    sys.exit(2)


def sections(pe):
    if pe[:2] != b"MZ":
        die("not a PE file (no MZ header)")
    off = struct.unpack_from("<I", pe, 0x3C)[0]
    if pe[off:off + 4] != b"PE\0\0":
        die("not a PE file (no PE signature)")
    nsec, = struct.unpack_from("<H", pe, off + 6)
    symtab, nsym = struct.unpack_from("<II", pe, off + 12)
    optsz, = struct.unpack_from("<H", pe, off + 20)
    strtab = symtab + nsym * 18
    s = off + 24 + optsz
    out = {}
    for _ in range(nsec):
        raw = pe[s:s + 8].rstrip(b"\0")
        if raw.startswith(b"/") and raw[1:].isdigit() and symtab:  # long name in the COFF string table
            p = strtab + int(raw[1:])
            raw = pe[p:pe.index(b"\0", p)]
        vsz, va, rsz, roff = struct.unpack_from("<IIII", pe, s + 8)
        out[raw.decode("ascii", "replace")] = pe[roff:roff + min(rsz, vsz) if vsz else roff + rsz]
        s += 40
    return out


def elf_modname(elf):
    if elf[:4] != b"\x7fELF" or elf[4] != 2:
        return "?"
    shoff, = struct.unpack_from("<Q", elf, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", elf, 0x3A)

    def sh(i):
        return struct.unpack_from("<IIQQQQIIQQ", elf, shoff + i * shentsize)
    names = sh(shstrndx)
    for i in range(shnum):
        h = sh(i)
        n = elf[names[4] + h[0]:].split(b"\0", 1)[0]
        if n == b".modname":
            return elf[h[4]:h[4] + h[5]].split(b"\0", 1)[0].decode("ascii", "replace")
    return "?"


def grub_objects(pe):
    m = sections(pe).get("mods")
    if m is None:
        die("no GRUB 'mods' section: not a GRUB EFI image")
    magic, _pad, off, size = struct.unpack_from("<IIQQ", m, 0)
    if magic != 0x676D696D:  # "mimg"
        die("bad GRUB module info magic")
    p, end = off, min(size, len(m))
    while p + 8 <= end:
        t, sz = struct.unpack_from("<II", m, p)
        if sz < 8:
            die("bad GRUB object size")
        data = m[p + 8:p + sz]
        if t == 0:
            yield "module " + elf_modname(data)
        elif t == 1:
            yield "memdisk %d" % len(data)
        elif t == 2:
            lines = data.split(b"\0", 1)[0].decode("ascii", "replace").splitlines()
            yield "config " + (lines[0] if lines else "")
        elif t == 3:
            yield "prefix " + data.split(b"\0", 1)[0].decode("ascii", "replace")
        elif t == 4:
            yield "pubkey"
        elif t == 6:  # OBJ_TYPE_DISABLE_SHIM_LOCK
            yield "disable-shim-lock"
        else:
            yield "object %d" % t
        p += sz


def pem_der(path):
    txt = open(path, encoding="ascii").read()
    b = re.search(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", txt, re.S)
    if not b:
        die(path + ": no PEM certificate")
    return base64.b64decode("".join(b.group(1).split()))


def main(a):
    try:
        run(a)
    except (struct.error, ValueError, IndexError, UnicodeDecodeError) as e:
        die("malformed file (%s)" % e)


def run(a):
    if len(a) == 2 and a[0] == "sbat":
        s = sections(open(a[1], "rb").read()).get(".sbat")
        if s is None:
            die("no .sbat section")
        sys.stdout.write(s.replace(b"\0", b"").decode("ascii", "replace"))
    elif len(a) == 3 and a[0] == "has-cert":
        sys.exit(0 if pem_der(a[2]) in open(a[1], "rb").read() else 1)
    elif len(a) == 2 and a[0] == "grub":
        for line in grub_objects(open(a[1], "rb").read()):
            print(line)
    else:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
