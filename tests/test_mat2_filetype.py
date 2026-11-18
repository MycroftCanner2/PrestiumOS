#!/usr/bin/python3
"""Prestium 2.1: mat2 / Metadata Cleaner on images whose name does not match their content.
Booted ISO: a browser download "ap<digits>.png" gave "Error while setting up parser for ...png: " with an
empty reason and "Unable to Read the File": PNGParser hands any .png to cairo and turns its error into a
bare ValueError(). libmat2/prestium_filetype.py (loaded by mat2's parser_factory with its parsers) reads
the real type. Runs the module against a stand-in for libmat2.images shaped like mat2 0.13.5's, with real
cairo, GdkPixbuf and Pillow (verified in a VM with the real mat2 0.13.5 and Metadata Cleaner 2.5.2 under
AppArmor). Static checks always run."""
import io, os, sys, tempfile, types
sys.dont_write_bytecode = True
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
M = os.path.join(I, "usr/lib/python3/dist-packages/libmat2/prestium_filetype.py")
H = os.path.join(R, "config/hooks/live/0465-prestium-mat2.hook.chroot")
fail = 0
def check(c, msg):
    global fail
    print(("OK   " if c else "FAIL ") + msg); fail |= not c

src = open(M).read()
check(os.access(H, os.X_OK) and "py_compile" in open(H).read() and "_png_init" in open(H).read(),
      "build hook checks mat2 loads it and byte-compiles it")
check("python3-pil" in open(os.path.join(R, "config/package-lists/prestium.list.chroot")).read().split(), "Pillow installed")
check('formats=["WEBP"]' in src, "Pillow limited to its WebP decoder")
check("raise ValueError\n" not in src and "raise ValueError(\"" in src, "no bare ValueError")

try:
    import cairo
    import gi; gi.require_version("GdkPixbuf", "2.0"); from gi.repository import GdkPixbuf, GLib
    from PIL import Image, features
    import numpy
except Exception as e:
    print("OK   (functional part skipped: %s)" % e); sys.exit(fail)

# stand-in for libmat2 (abstract/exiftool/images as in mat2 0.13.5, without exiftool)
pkg = types.ModuleType("libmat2"); pkg.__path__ = []
sys.modules["libmat2"] = pkg
class ExiftoolParser:
    lightweight_cleaning = False
    def __init__(self, filename): self.filename = filename; self.output_filename = None
images = types.ModuleType("libmat2.images"); images.__package__ = "libmat2"
class PNGParser(ExiftoolParser):
    mimetypes = {"image/png"}
    def __init__(self, filename):
        super().__init__(filename)
        try: cairo.ImageSurface.create_from_png(self.filename)
        except: raise ValueError
    def remove_all(self):
        cairo.ImageSurface.create_from_png(self.filename).write_to_png(self.output_filename); return True
class GIFParser(ExiftoolParser):
    mimetypes = {"image/gif"}
class GdkPixbufAbstractParser(ExiftoolParser):
    def __init__(self, filename):
        super().__init__(filename)
        try: GdkPixbuf.Pixbuf.new_from_file(self.filename)
        except GLib.GError: raise ValueError
    def remove_all(self):
        ext = os.path.splitext(self.filename)[1].lower()
        ext = {".jpg": ".jpeg", ".tif": ".tiff"}.get(ext, ext)
        GdkPixbuf.Pixbuf.new_from_file(self.filename).savev(self.output_filename, ext[1:], [], []); return True
class JPGParser(GdkPixbufAbstractParser): mimetypes = {"image/jpeg"}
class TiffParser(GdkPixbufAbstractParser): mimetypes = {"image/tiff"}
class HEICParser(ExiftoolParser): mimetypes = {"image/heic"}
for c in (PNGParser, GIFParser, GdkPixbufAbstractParser, JPGParser, TiffParser, HEICParser):
    setattr(images, c.__name__, c)
sys.modules["libmat2.images"] = images; pkg.images = images
import importlib.util
spec = importlib.util.spec_from_file_location("libmat2.prestium_filetype", M)
mod = importlib.util.module_from_spec(spec); mod.__package__ = "libmat2"; spec.loader.exec_module(mod)

d = tempfile.mkdtemp()
img = Image.fromarray((numpy.random.rand(60, 80, 3) * 255).astype("uint8"))
def f(name, **kw):
    p = os.path.join(d, name); img.save(p, **kw); return p
ex = Image.Exif(); ex[0x013B] = "Secret Person"
files = {"png": f("ok.png", format="PNG"), "webp": f("ap26322454124065.png", format="WEBP", exif=ex.tobytes()),
         "jpeg": f("jpeg_as.png", format="JPEG", exif=ex.tobytes()), "gif": f("gif_as.png", format="GIF")}
p = os.path.join(d, "empty.png"); open(p, "wb").close(); files["empty"] = p
p = os.path.join(d, "trunc.png"); open(p, "wb").write(open(files["png"], "rb").read()[:200]); files["trunc"] = p
p = os.path.join(d, "huge.png"); Image.new("RGB", (40000, 2)).save(p); files["huge"] = p
p = os.path.join(d, "avif_as.png"); open(p, "wb").write(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 40); files["avif"] = p
p = os.path.join(d, "page.png"); open(p, "wb").write(b"<!DOCTYPE html><html>blocked</html>"); files["html"] = p

def err(path, cls=PNGParser):
    try: cls(path); return None
    except ValueError as e: return str(e)

o = PNGParser(files["png"]); check(type(o) is PNGParser, "a real PNG still uses PNGParser")
for k, want in (("empty", "The file is empty."), ("trunc", "incomplete or damaged"),
                ("avif", "really in AVIF format, but its name ends in .png"), ("html", "a web page (HTML), not an image"),
                ("gif", "Rename it to end in .gif")):
    e = err(files[k]); check(e and want in e, "%s named .png: %r" % (k, e))
o = PNGParser(files["jpeg"]); check(type(o) is JPGParser, "a JPEG named .png goes to JPGParser")
o.output_filename = os.path.join(d, "out-j.png"); o.remove_all()
check(open(o.output_filename, "rb").read(8) == b"\x89PNG\r\n\x1a\n", "...and is saved as a real PNG")
o = PNGParser(files["huge"]); o.output_filename = os.path.join(d, "out-h.png")
check(o.remove_all() and Image.open(o.output_filename).size == (40000, 2), "a PNG too large for cairo is re-encoded with GdkPixbuf")
if features.check("webp"):
    o = PNGParser(files["webp"]); o.output_filename = os.path.join(d, "out-w.png")
    check(type(o) is PNGParser and o.remove_all(), "a WebP named .png is cleaned")
    out = Image.open(o.output_filename)
    check(out.format == "PNG" and not out.info and b"Secret" not in open(o.output_filename, "rb").read(),
          "...into a real PNG with no EXIF/XMP/ICC")
    a = os.path.join(d, "anim.png"); img.save(a, format="WEBP", save_all=True, append_images=[img.rotate(90)])
    e = err(a); check(e and "animated WebP" in e, "animated WebP: %r" % e)
o = JPGParser(files["png"]); check(type(o) is PNGParser, "a PNG named .jpg goes to PNGParser")
bad = os.path.join(d, "bad.jpg"); open(bad, "wb").write(b"\xff\xd8\xff\xe0" + b"\x00" * 30)
e = err(bad, JPGParser); check(e and e.startswith("The image could not be decoded ("), "broken JPEG gives GdkPixbuf's reason: %r" % e)
sys.exit(fail)
