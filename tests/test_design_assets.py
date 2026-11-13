#!/usr/bin/env python3
# Prestium 2.1: design assets. The 256 px logo is rendered from the final SVG (checked pixel by pixel
# when rsvg-convert is installed), the three wallpapers are 2560x1440 PNGs of a sane size, every
# icon name the volume/microphone/brightness OSD and the notification-sound toggle use exists in
# Papirus-Dark (checked against an unpacked papirus-icon-theme when PAPIRUS_ROOT is set), and no
# adwaita-qt is left in the tree.
import os, re, shutil, struct, subprocess, sys, tempfile, zlib

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fails = 0
def ok(m):
    print("OK", m); return True
def bad(m):
    global fails; fails += 1; print("FAIL", m)
def skip(m): print("SKIP", m)

def png(path):
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError("not a PNG")
    i, idat, hdr, chunks = 8, b"", None, []
    while i < len(d):
        n, = struct.unpack(">I", d[i:i+4]); t = d[i+4:i+8]; c = d[i+8:i+8+n]; chunks.append(t)
        if t == b"IHDR": hdr = struct.unpack(">IIBBBBB", c)
        elif t == b"IDAT": idat += c
        i += 12 + n
    return hdr, idat, chunks

def rgba(path):
    (w, h, bd, ct, _, _, il), idat, _ = png(path)
    assert bd == 8 and ct == 6 and il == 0, "need 8-bit RGBA, not interlaced"
    raw = zlib.decompress(idat); out = bytearray(); prev = bytearray(w * 4); p = 0
    for _ in range(h):
        f = raw[p]; line = bytearray(raw[p+1:p+1+w*4]); p += 1 + w * 4
        for x in range(len(line)):
            a = line[x-4] if x >= 4 else 0; b = prev[x]; c = prev[x-4] if x >= 4 else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                q = a + b - c; pa, pb, pc = abs(q-a), abs(q-b), abs(q-c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line; prev = line
    return w, h, out

# logo
B = os.path.join(I, "usr/share/prestium/branding")
L = os.path.join(B, "prestium-logo-256.png")
(w, h, bd, ct, *_), _, ch = png(L)
(w, h, ct) == (256, 256, 6) and ok("logo PNG is 256x256 RGBA") or bad("logo PNG is %sx%s colour type %s" % (w, h, ct))
b"tIME" not in ch and b"tEXt" not in ch and ok("logo PNG carries no timestamp or text chunks") or bad("logo PNG has metadata")
rs = shutil.which("rsvg-convert")
if rs:
    t = tempfile.mkdtemp()
    try:
        o = os.path.join(t, "l.png")
        subprocess.run([rs, "-w", "256", "-h", "256", "-o", o, os.path.join(B, "prestium-logo.svg")], check=True)
        _, _, a = rgba(L); _, _, b = rgba(o)
        diff = max(abs(x - y) for x, y in zip(a, b))
        diff <= 2 and ok("logo PNG matches the SVG (max channel difference %d)" % diff) or bad("logo PNG differs from the SVG (max %d): regenerate it" % diff)
    finally:
        shutil.rmtree(t)
else:
    skip("rsvg-convert missing: logo not compared with the SVG")

# wallpapers
W = os.path.join(I, "usr/share/backgrounds/prestium")
names = sorted(f for f in os.listdir(W) if f.endswith(".png"))
names == ["circuit.png", "horizon.png", "mark.png"] and ok("three wallpapers") or bad("wallpapers: %s" % names)
for n in names:
    p = os.path.join(W, n); (w, h, bd, ct, *_), _, ch = png(p); sz = os.path.getsize(p)
    (w, h) == (2560, 1440) and ok("%s is 2560x1440" % n) or bad("%s is %sx%s" % (n, w, h))
    sz <= 3_000_000 and ok("%s is %d bytes (<= 3 MB)" % (n, sz)) or bad("%s is %d bytes" % (n, sz))
    b"tIME" not in ch and b"tEXt" not in ch and ok("%s carries no metadata chunks" % n) or bad("%s has metadata" % n)
wp = open(os.path.join(I, "usr/local/bin/prestium-wallpaper")).read()
all(x[:-4] in wp for x in names) and ok("prestium-wallpaper knows all three") or bad("prestium-wallpaper misses a wallpaper")

# OSD and notification icons
# 2.1 (UI pass): Papirus's 48 px notification-* icons (mako draws icons at 48 px)
OSD = ["notification-audio-volume-muted", "notification-audio-volume-low", "notification-audio-volume-medium",
       "notification-audio-volume-high", "notification-microphone-sensitivity-muted",
       "notification-microphone-sensitivity-high", "notification-display-brightness"]
used = set()
for f in ("usr/local/bin/prestium-media-key", "usr/local/bin/prestium-notify-sound"):
    s = open(os.path.join(I, f)).read()
    used |= set(re.findall(r"(?<![\w-])(?:notification-)?(?:audio|microphone|weather|display)-[a-z-]+\b", s))
used.discard("audio-input")
sorted(used) == sorted(OSD) and ok("OSD icon names are the checked list") or bad("OSD icon names changed: %s (update OSD in this test)" % sorted(used ^ set(OSD)))
mk = open(os.path.join(I, "etc/xdg/mako/config")).read()
"/usr/share/icons/Papirus-Dark:/usr/share/icons/Papirus" in mk and ok("mako looks in Papirus-Dark, then Papirus") or bad("mako icon-path lost Papirus-Dark")
PR = os.environ.get("PAPIRUS_ROOT")
if PR:
    D = os.path.join(PR, "usr/share/icons/Papirus-Dark")
    for n in OSD:
        hit = [d for d in sorted(os.listdir(D)) if os.path.isdir(os.path.join(D, d)) for c in os.listdir(os.path.join(D, d))
               if os.path.exists(os.path.join(D, d, c, n + ".svg"))]
        hit and ok("Papirus-Dark has %s (%s)" % (n, ", ".join(hit[:3]))) or bad("Papirus-Dark lacks %s" % n)
else:
    skip("PAPIRUS_ROOT not set: icon names not checked against papirus-icon-theme")

# adwaita-qt
g = subprocess.run(["git", "-C", R, "grep", "-n", "-i", "adwaita-qt", "--", ".", ":!tests/test_design_assets.py"],
                   capture_output=True, text=True)
if g.returncode > 1:  # not a git checkout
    g = subprocess.run(["grep", "-rniI", "--exclude=test_design_assets.py", "--exclude-dir=.git", "--exclude-dir=cache",
                        "adwaita-qt", R], capture_output=True, text=True)
out = g.stdout
left = [l for l in out.splitlines() if not re.search(r"2\.0 r\d+", l)]
not left and ok("no adwaita-qt mentions (outside 2.0 rN history)") or bad("adwaita-qt still mentioned: %s" % left)

sys.exit(1 if fails else 0)
