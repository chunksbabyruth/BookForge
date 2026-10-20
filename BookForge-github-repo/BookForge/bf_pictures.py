"""BookForge pictures: reading picture files, sizes, thumbnails and cover art. No window code here.

Pictures are kept in the book as PNG, JPEG or GIF bytes, because every output (PDF, EPUB, Word, web page)
can use those. Other formats (BMP, TIFF, WebP...) are converted when they are added, and phone photos are
turned the right way up (their EXIF rotation is applied), so they never print sideways.
"""
import io
import os

PICTURE_FILES = [("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff *.webp"), ("All files", "*.*")]

# Where a picture goes (Block.img_place) and what the editor calls it
PLACES = [("", "In the text"), ("page", "On a page of its own"), ("full", "Full page, edge to edge")]
PLACE_NAMES = dict(PLACES)
ALIGNS = [("left", "Left"), ("center", "Centre"), ("right", "Right")]
COVER_FITS = ["Fill the panel (edges may be trimmed)", "Fit inside the panel (whole picture shows)"]

_KEEP = {"PNG", "JPEG", "GIF"}


def _pil():
    from PIL import Image, ImageOps
    return Image, ImageOps


def kind(data):
    """'png' / 'jpg' / 'gif' for bytes BookForge keeps as they are, else None."""
    if not data:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"GIF8":
        return "gif"
    return None


def normalise(data, name="picture"):
    """Picture bytes -> (bytes BookForge can use everywhere, name). Raises ValueError with a plain message."""
    Image, ImageOps = _pil()
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        raise ValueError(f"“{name}” isn't a picture BookForge can read ({type(e).__name__})") from e
    fmt = (im.format or "").upper()
    try:
        orient = im.getexif().get(0x0112, 1)
    except Exception:
        orient = 1
    if fmt in _KEEP and orient in (None, 1):
        return data, name
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = ImageOps.exif_transpose(im)
    alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    icc = {"icc_profile": im.info["icc_profile"]} if im.info.get("icc_profile") else {}
    out = io.BytesIO()
    if alpha or fmt in ("PNG", "GIF", "BMP", "TIFF"):
        im = im.convert("RGBA" if alpha else "RGB")
        im.save(out, "PNG", optimize=True, **icc)
        ext = "png"
    else:                                   # photos (JPEG turned upright, WebP...)
        if im.mode not in ("RGB", "L", "CMYK"):
            im = im.convert("RGB")
        im.save(out, "JPEG", quality=92, subsampling=0, **icc)
        ext = "jpg"
    base = os.path.splitext(name)[0] or "picture"
    return out.getvalue(), f"{base}.{ext}"


def read_picture(path):
    """A picture file -> (bytes, file name). Raises ValueError with a plain message."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ValueError(f"the picture couldn't be opened ({e.strerror or e})") from e
    return normalise(data, os.path.basename(path))


def size(data):
    """(width, height) in pixels, or None."""
    try:
        Image, _ = _pil()
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return None


def thumbnail(data, max_w, max_h):
    """A small RGB(A) PIL image of the picture, or None."""
    try:
        Image, _ = _pil()
        im = Image.open(io.BytesIO(data))
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "PA", "P") else "RGB")
        im.thumbnail((max(1, int(max_w)), max(1, int(max_h))))
        return im
    except Exception:
        return None


def fit_box(iw, ih, bx, by, bw, bh, fill):
    """Where to draw an iw x ih picture in the box (bx, by, bw, bh): (x, y, w, h).
    fill=True covers the whole box (edges are trimmed); fill=False shows the whole picture inside it."""
    k = (max if fill else min)(bw / iw, bh / ih)
    w, h = iw * k, ih * k
    return bx + (bw - w) / 2, by + (bh - h) / 2, w, h


def picture_scale(iw, ih, pct, place, fw, fh, pw, ph, unit=72):
    """How big one pixel of an iw x ih picture is on the page, in the units of the other sizes (points
    with unit=72, inches with unit=1). fw/fh = the text area, pw/ph = the page. The PDF uses these rules."""
    if place == "full":
        return max(pw / iw, ph / ih)
    if place == "page":
        return min(fw * pct / 100 / iw, fh / ih) if pct else min(fw / iw, fh / ih)
    k = fw * min(100, max(5, pct)) / 100 / iw if pct else min(fw / iw, fh * 0.65 / ih, 1.5 * unit / 72)
    return min(k, (fh - 16 * unit / 72) / ih)          # never taller than the text area


def cover_art(book, s, which):
    """Bytes of the front or back cover picture ('front' / 'back'), or None. Uses the file chosen in the
    settings; if that file is missing (e.g. a project opened on another computer), the copy saved inside
    the project. Raises ValueError if a chosen file exists but isn't a picture."""
    path = (s.get(f"cover_{which}_image") or "").strip()
    if not path:
        return None
    if os.path.isfile(path):
        return read_picture(path)[0]
    return getattr(book, f"cover_{which}", None) or None
