"""Prestium 2.1: mat2 (and Metadata Cleaner, which uses it) on images whose name does not match their
content, or that cairo can't open, instead of "Unable to Read the File" with an empty reason.

mat2 picks a parser by the file name only (parser_factory.get_parser -> mimetypes.guess_type). Browsers
often save a WebP, AVIF or JPEG under a ".png" name (sites serve another format for the same URL), so
PNGParser handed the file to cairo, cairo failed, and mat2 raised a bare ValueError(): Metadata Cleaner
logged "Error while setting up parser for x.png: " (empty) and showed no reason. The same happened for
an empty or truncated PNG, and for a valid PNG wider or taller than cairo's 32767 pixels.

parser_factory imports every module in this directory before it is used, so this file is loaded with
the parsers (it defines no parser of its own) and changes them:
  * the file's real type is read from its first bytes. A JPEG, PNG or TIFF with the wrong name goes to
    the right parser (a JPEG named .png is cleaned and saved as a real PNG, as mat2 does for its
    extension); a WebP named .png is decoded with Pillow (its WebP decoder only) and cleaned by writing
    its pixels to a new, real PNG; a GIF or HEIC (cleaned by exiftool, which needs the right name) asks
    to be renamed; a type mat2 can't clean (AVIF, JPEG XL, BMP, animated WebP, ...) says so;
  * a PNG cairo rejects says why (empty, incomplete or damaged, not decodable); one only too large for
    cairo is read and re-encoded with GdkPixbuf, which writes no metadata;
  * a JPEG or TIFF GdkPixbuf can't decode gives GdkPixbuf's reason.
The messages appear on Metadata Cleaner's details page under "Unable to Read the File".
"""
import os

import cairo
from gi.repository import GdkPixbuf, GLib

from . import images

_NAMES = {"image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF", "image/tiff": "TIFF",
          "image/heic": "HEIC", "image/webp": "WebP", "image/avif": "AVIF", "image/jxl": "JPEG XL",
          "image/bmp": "BMP", "image/x-icon": "ICO"}
_PARSERS = {}
# re-encoded by cairo or GdkPixbuf, which read the content whatever the name (mat2 saves in the format
# the name says: a JPEG named .png becomes a real PNG)
_REENCODE = {"image/png", "image/jpeg", "image/tiff"}
_EXT = {"image/gif": ".gif", "image/heic": ".heic"}


def sniff(path):
    """The image type from the file's first bytes, or None if it is not one of the known ones."""
    try:
        with open(path, "rb") as f:
            h = f.read(64)
    except OSError:
        return None
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if h.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "image/heic"
    if h.startswith(b"\xff\x0a") or h.startswith(b"\x00\x00\x00\x0cJXL \r\n\x87\n"):
        return "image/jxl"
    if h[:2] == b"BM":
        return "image/bmp"
    if h[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    if h.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        return "text/html"
    return None


def _ext(path):
    return os.path.splitext(path)[1] or "(no extension)"


def _new(cls, filename, *args, **kwargs):
    try:
        if os.path.getsize(filename) == 0:
            raise ValueError("The file is empty.")
    except OSError:
        pass    # the parser reports it
    real = sniff(filename)
    if real == "image/webp" and cls is images.PNGParser and _pil_webp():
        return object.__new__(cls)      # _png_init decodes it with Pillow; saved as a real PNG
    if real == "text/html":
        raise ValueError("This file is a web page (HTML), not an image, although its name ends in %s: the "
                         "download probably failed. There is nothing to clean." % _ext(filename))
    if real is not None and real not in cls.mimetypes:
        name, ext = _NAMES.get(real, real), _ext(filename)
        target = _PARSERS.get(real)
        if target is not None and real in _REENCODE:
            return target(filename)
        if target is not None:
            # GIF and HEIC are cleaned by exiftool, which refuses a file whose name says another type
            raise ValueError("This file is really in %s format, but its name ends in %s. Rename it to "
                             "end in %s, then clean it." % (name, ext, _EXT[real]))
        raise ValueError("This file is really in %s format, but its name ends in %s. %s files can't be "
                         "cleaned." % (name, ext, name))
    return object.__new__(cls)


def _pil_webp():
    try:
        from PIL import features
        return bool(features.check("webp"))
    except Exception:
        return False


def _webp_open(path):
    from PIL import Image
    return Image.open(path, formats=["WEBP"])   # only the WebP decoder, whatever else Pillow has


def _png_init(self, filename):
    super(images.PNGParser, self).__init__(filename)
    self._prestium_pixbuf = False
    self._prestium_webp = False
    if sniff(self.filename) == "image/webp":
        # 2.1: a WebP saved under a .png name (the usual browser case): decoded by Pillow, cleaned by
        # writing its pixels to a new, real PNG (which then matches the name)
        try:
            with _webp_open(self.filename) as im:
                if getattr(im, "is_animated", False):
                    raise ValueError("This file is really an animated WebP, but its name ends in %s. "
                                     "Animated WebP files can't be cleaned." % _ext(self.filename))
                im.load()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError("This file is really in WebP format, but its name ends in %s, and it could "
                             "not be decoded (%s)." % (_ext(self.filename), e))
        self._prestium_webp = True
        return
    try:
        cairo.ImageSurface.create_from_png(self.filename)
        return
    except MemoryError:
        why = "not enough memory"
        status = None
    except Exception as e:      # cairo.Error / IOError
        status = getattr(e, "status", None)
        why = str(e.args[0] if getattr(e, "args", None) else e) or type(e).__name__
    if status == cairo.Status.INVALID_SIZE:
        # larger than cairo's 32767 pixels: GdkPixbuf reads it and re-encodes it without metadata
        try:
            GdkPixbuf.Pixbuf.new_from_file(self.filename)
            self._prestium_pixbuf = True
            return
        except GLib.Error as g:
            raise ValueError("The PNG image is too large to open (%s)." % g.message)
    if status == cairo.Status.READ_ERROR:
        raise ValueError("The PNG file is incomplete or damaged (%s)." % why)
    raise ValueError("The PNG file could not be decoded (%s)." % why)


_png_remove_all = images.PNGParser.remove_all


def _png_remove(self):
    if getattr(self, "_prestium_webp", False):
        from PIL import Image
        with _webp_open(self.filename) as im:
            im.load()
            alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            px = im.convert("RGBA" if alpha else "RGB")
            # a new image from the pixels only: nothing of the WebP's EXIF, XMP or ICC data comes along
            clean = Image.frombytes(px.mode, px.size, px.tobytes())
        clean.save(self.output_filename, "PNG")
        return True
    if getattr(self, "_prestium_pixbuf", False) and not self.lightweight_cleaning:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.filename)
        try:
            pixbuf.savev(self.output_filename, "png", [], [])
        except GLib.Error:
            return False
        return True
    return _png_remove_all(self)


def _pixbuf_init(self, filename):
    super(images.GdkPixbufAbstractParser, self).__init__(filename)
    try:
        GdkPixbuf.Pixbuf.new_from_file(self.filename)
    except GLib.Error as g:
        raise ValueError("The image could not be decoded (%s)." % g.message)


def _install():
    for name in ("PNGParser", "JPGParser", "TiffParser", "GIFParser", "HEICParser"):
        cls = getattr(images, name, None)
        if cls is None or not getattr(cls, "mimetypes", None):
            continue
        for m in cls.mimetypes:
            _PARSERS.setdefault(m, cls)
        cls.__new__ = staticmethod(_new)
    if hasattr(images, "PNGParser"):
        images.PNGParser.__init__ = _png_init
        images.PNGParser.remove_all = _png_remove
    if hasattr(images, "GdkPixbufAbstractParser"):
        images.GdkPixbufAbstractParser.__init__ = _pixbuf_init


_install()
