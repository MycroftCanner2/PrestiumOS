#!/usr/bin/python3
# 2.1 (Phrack 73): no confined program may open an AF_ALG socket (the kernel crypto API, a common
# kernel attack surface), and the VeraCrypt/TrueCrypt/LUKS unlock path keeps it: the algif modules are
# not blacklisted, and nothing on that path (Unlock Volume, udisks, cryptsetup, the file manager) is
# confined. Checks every profile block (children included) with the repo's abstractions expanded.
import glob, os, re, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot"); A = os.path.join(I, "etc/apparmor.d")
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; fail = 1; print("FAIL " + m)
def strip(s): return "\n".join(l.split("#", 1)[0] if not re.match(r"\s*#include", l) else l.replace("#include", "include") for l in s.splitlines())
def expand(text, seen=()):
    out = []
    for l in text.splitlines():
        m = re.match(r"\s*include (?:if exists )?<(abstractions/prestium[^>]*)>", l)
        if m and m.group(1) not in seen:
            out.append(expand(strip(open(os.path.join(A, m.group(1))).read()), seen + (m.group(1),)))
        else: out.append(l)
    return "\n".join(out)
def blocks(text):
    """(name, body without child blocks) for every profile block"""
    res, stack = [], []
    for l in text.splitlines():
        m = re.match(r"\s*profile (\S+)[^{]*\{\s*$", l)
        if m: stack.append([m.group(1), []]); continue
        if re.match(r"\s*\}\s*$", l) and stack:
            n, b = stack.pop(); res.append(("//".join([s[0] for s in stack] + [n]), "\n".join(b))); continue
        if stack: stack[-1][1].append(l)
    return res
DENY = re.compile(r"^\s*deny\s+network\s+alg\s*,", re.M)
n = 0
for f in sorted(glob.glob(os.path.join(A, "*"))):
    if not os.path.isfile(f): continue
    for name, body in blocks(strip(open(f).read())):
        n += 1
        body = expand(body)
        if DENY.search(body): ok("%s: deny network alg" % name)
        else: bad("%s (%s): no 'deny network alg,'" % (name, os.path.basename(f)))
        if re.search(r"^\s*(allow\s+)?network\s+alg\b", body, re.M): bad("%s allows network alg" % name)
(ok if n >= 25 else bad)("%d profile blocks checked" % n)
# the unlock path stays unconfined (it needs AF_ALG for cryptsetup's TCRYPT/LUKS key derivation)
hdr = "\n".join(l for f in glob.glob(os.path.join(A, "*")) if os.path.isfile(f) for l in open(f) if re.match(r"\s*profile \S+ /", l))
for b in ["cryptsetup", "udisksd", "pcmanfm", "prestium-unlock-volume", "prestium-unlock-veracrypt", "veracrypt"]:
    (bad if re.search(r"/" + re.escape(b) + r"\b", hdr) else ok)("no Prestium profile attaches to %s" % b)
uv = open(os.path.join(I, "usr/local/bin/prestium-unlock-volume")).read()
(ok if "org.freedesktop.UDisks2" in uv else bad)("Unlock Volume unlocks through udisks (root, unconfined), not in a confined app")
# no system-wide AF_ALG blacklist (VeraCrypt unlocks need it)
txt = ""
for root in ("config/hooks", "config/includes.chroot/etc", "config/binary", "auto"):
    for dp, _, fs in os.walk(os.path.join(R, root)) if os.path.isdir(os.path.join(R, root)) else [(os.path.dirname(os.path.join(R, root)), [], [os.path.basename(root)])]:
        for x in fs:
            try: txt += open(os.path.join(dp, x), errors="ignore").read()
            except OSError: pass
(bad if re.search(r"(blacklist|install)\s+(af_alg|algif_\w+)|modprobe\.blacklist=[^ \"]*(af_alg|algif)", txt) else ok)("af_alg/algif_* are not blacklisted")
print("test_af_alg_deny: " + ("OK" if not fail else "FAILED")); sys.exit(fail)
