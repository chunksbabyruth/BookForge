"""BookForge page numbers: how a page's number is written and where it sits on the page. No window code here.

Numerals (setting "pn_numerals"):
  - Arabic numerals 1, 2, 3 (the standard: what every earlier version printed),
  - lowercase or uppercase Roman numerals (iv, ix, xl...; 1 to 3999 - a bigger number prints in Arabic),
  - custom digit pictures: a folder with a picture for each digit 0-9, put side by side (128 = 1, 2, 8),
  - custom whole-number pictures: a folder with one picture per page number (e.g. Cistercian numerals, where
    128 is a single glyph), named by a pattern such as {number}.png. Only the pictures of the pages being
    printed are read. Numbers 1 to 9999 (the largest a single Cistercian glyph shows); there is no number 0.
The numerals are for the book's main numbering; with "Roman front matter, 1 on first chapter" the pages before
chapter 1 keep i, ii, iii. A picture that's missing or can't be read: that page gets its number in Arabic
numerals instead, and the log, the printing notes and the preview say which pages.

Positions (setting "pn_position"): the four of earlier versions (Bottom center - standard -, Bottom outside,
Top outside, None) and Top left / center / right, Bottom left / right, Middle outside edge (in the outside
margin halfway down: on the left of left-hand pages, on the right of right-hand pages; left / right-hand is the
page's place in the book, never its place on a printer sheet).
"""
import io
import os
import re

ARABIC = "Arabic numerals (1, 2, 3)"
ROMAN_LOWER = "Lowercase Roman (i, ii, iii)"
ROMAN_UPPER = "Uppercase Roman (I, II, III)"
DIGIT_IMAGES = "Custom digit images (0-9)"
WHOLE_IMAGES = "Custom whole-number images"
NUMERALS = [ARABIC, ROMAN_LOWER, ROMAN_UPPER, DIGIT_IMAGES, WHOLE_IMAGES]
PICTURE_MODES = (DIGIT_IMAGES, WHOLE_IMAGES)

POSITIONS = ["Bottom center", "Bottom left", "Bottom right", "Bottom outside",
             "Top center", "Top left", "Top right", "Top outside",
             "Middle outside edge", "None"]
MIDDLE = "Middle outside edge"

ROMAN_MAX = 3999                  # MMMCMXCIX: the largest number written the usual way
WHOLE_MAX = 9999                  # the largest number one Cistercian glyph shows
PATTERNS = ["{number}.png", "{number:3}.png", "{number:4}.png", "cistercian_{number}.png"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
MAX_SIDE = 4000                   # pixels: a page-number picture bigger than this is refused
IMG_HEIGHT_MAX = 72.0             # pt: the largest picture height that can be set
GAP_MAX = 24.0                    # pt: the most space between digit pictures

_TOKEN = re.compile(r"\{number(?::(\d+))?\}")


# --------------------------------------------------------------------------- numerals as text
def roman_numeral(n, upper=False):
    """n in Roman numerals with the usual subtractive forms (IV, IX, XL, XC, CD, CM), or None outside 1..3999
    (there is no zero, and 4000 and up have no usual form)."""
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= ROMAN_MAX:
        return None
    out = ""
    for v, r in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                 (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += r
            n -= v
    return out if upper else out.lower()


def numerals(s):
    """The numerals setting, checked (anything unknown = Arabic, as earlier versions printed)."""
    v = (s or {}).get("pn_numerals") or ARABIC
    return v if v in NUMERALS else ARABIC


# --------------------------------------------------------------------------- file-name patterns
def pattern_problem(pattern):
    """A plain message if a whole-number file-name pattern can't be used, else None."""
    p = (pattern or "").strip()
    if not p:
        return "Type the pictures' file names as a pattern, e.g. {number}.png."
    tokens = _TOKEN.findall(p)
    if len(tokens) != 1:
        return "The file-name pattern needs {number} exactly once (e.g. {number}.png or cistercian_{number}.png)."
    if tokens[0] and not 1 <= int(tokens[0]) <= 6:
        return "Zero-padding in the pattern goes from {number:1} to {number:6} (e.g. {number:4}.png = 0001.png)."
    rest = _TOKEN.sub("", p)
    if "{" in rest or "}" in rest:
        return "Only {number} or {number:4} can go in braces in the file-name pattern."
    if "/" in p or "\\" in p or ":" in rest:
        return "The pattern is just a file name (no folders), e.g. {number}.png."
    if os.path.splitext(p)[1].lower() not in IMAGE_EXTS:
        return "The pattern should end with the pictures' file type, e.g. .png (or " + \
            ", ".join(IMAGE_EXTS[1:]) + ")."
    return None


def pattern_name(pattern, n):
    """The file name of number n's picture: pattern_name("{number:4}.png", 12) = "0012.png"."""
    p = pattern.strip()
    m = _TOKEN.search(p)
    return p[:m.start()] + str(n).zfill(int(m.group(1) or 0)) + p[m.end():]


def _pattern_regex(pattern):
    p = pattern.strip()
    m = _TOKEN.search(p)
    flags = re.IGNORECASE if os.name == "nt" else 0
    return re.compile(re.escape(p[:m.start()]) + r"(\d+)" + re.escape(p[m.end():]), flags), int(m.group(1) or 0)


def pack_numbers(folder, pattern):
    """The page numbers (1..WHOLE_MAX) a whole-number folder has a picture for, by file name only (no picture is
    opened). An empty set if the folder or pattern can't be used."""
    if pattern_problem(pattern) or not folder or not os.path.isdir(folder):
        return set()
    rx, width = _pattern_regex(pattern)
    out = set()
    try:
        names = os.listdir(folder)
    except OSError:
        return set()
    for name in names:
        m = rx.fullmatch(name)
        if m:
            n = int(m.group(1))
            if 1 <= n <= WHOLE_MAX and str(n).zfill(width) == m.group(1):
                out.add(n)
    return out


def detect_pattern(folder):
    """Work out the file-name pattern of a folder of whole-number pictures (e.g. cistercian_128.png ->
    "cistercian_{number}.png", 0128.png -> "{number:4}.png"). Returns the pattern, or None."""
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    groups = {}
    for name in names:
        m = re.fullmatch(r"(.*?)(\d+)(\.[A-Za-z0-9]+)", name)
        if not m or m.group(3).lower() not in IMAGE_EXTS or "{" in m.group(1) or "}" in m.group(1):
            continue
        groups.setdefault((m.group(1), m.group(3)), []).append(m.group(2))
    if not groups:
        return None
    (prefix, ext), nums = max(groups.items(), key=lambda kv: (len(kv[1]), kv[0][0] == ""))
    padded = [d for d in nums if len(d) > 1 and d.startswith("0")]
    width = max(len(d) for d in padded) if padded else 0
    return prefix + ("{number:%d}" % width if width else "{number}") + ext


def describe_numbers(numbers):
    """'1-9999 (9,999 pictures)', with the first page number that has no picture if there's a gap."""
    if not numbers:
        return "no pictures with that file-name pattern"
    lo, hi = min(numbers), max(numbers)
    text = f"{lo}–{hi} ({len(numbers):,} picture{'s' if len(numbers) != 1 else ''})"
    if lo != 1:
        text += "; there is no picture for 1"
    else:
        n = 1
        while n in numbers:
            n += 1
        if n <= hi:
            text += f"; the first missing number is {n}"
    return text


# --------------------------------------------------------------------------- pictures
def load_picture(src, name):
    """A page-number picture (a file path or bytes) -> RGBA PIL image. Raises ValueError with a plain message
    (missing, unreadable, empty or huge)."""
    from PIL import Image
    try:
        if isinstance(src, (bytes, bytearray)):
            im = Image.open(io.BytesIO(bytes(src)))
        else:
            with open(src, "rb") as f:
                im = Image.open(io.BytesIO(f.read()))
        im.load()
    except FileNotFoundError:
        raise ValueError(f"“{name}” isn't there") from None
    except Exception as e:                     # (any damaged or non-picture file)
        raise ValueError(f"“{name}” isn't a picture BookForge can read ({type(e).__name__})") from None
    w, h = im.size
    if w < 1 or h < 1:
        raise ValueError(f"“{name}” is an empty picture")
    if w > MAX_SIDE or h > MAX_SIDE:
        raise ValueError(f"“{name}” is too big for a page number ({w} x {h} pixels; at most "
                         f"{MAX_SIDE} on a side)")
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    return im.convert("RGBA")


def digit_files(folder):
    """The digit pictures in a folder: ({"0": path, ... "9": path}, problem or None). Files are named by their
    digit: 0.png ... 9.png, or with the same words in front (digit_0.png ... digit_9.png)."""
    if not (folder or "").strip():
        return {}, "Choose the folder with the digit pictures (0.png to 9.png)."
    if not os.path.isdir(folder):
        return {}, f"The digit pictures' folder isn't there: {folder}"
    try:
        names = sorted(os.listdir(folder))
    except OSError as e:
        return {}, f"The digit pictures' folder can't be read ({e})."
    groups = {}
    for name in names:
        stem, ext = os.path.splitext(name)
        m = re.fullmatch(r"(.*?)(\d)", stem)
        if m and ext.lower() in IMAGE_EXTS:
            groups.setdefault(m.group(1).lower(), {}).setdefault(m.group(2), os.path.join(folder, name))
    if not groups:
        return {}, "There are no digit pictures in that folder (name them 0.png, 1.png ... 9.png)."
    best = max(groups.values(), key=lambda g: (len(g), "0" in g))
    missing = [d for d in "0123456789" if d not in best]
    if missing:
        return best, ("Missing digit picture" + ("s" if len(missing) > 1 else "") + ": " + ", ".join(missing) +
                      " (the folder needs a picture for each digit, 0.png to 9.png).")
    return best, None


def check_digits(folder):
    """Read and check a folder of digit pictures: ({digit: RGBA image} for all ten, []) or ({}, [problems])."""
    files, problem = digit_files(folder)
    if problem:
        return {}, [problem]
    out, problems = {}, []
    for d in "0123456789":
        try:
            out[d] = load_picture(files[d], os.path.basename(files[d]))
        except ValueError as e:
            problems.append(str(e) + ".")
    return (out, []) if not problems else ({}, problems)


def digit_copies(folder):
    """The ten digit pictures' file bytes ({digit: bytes}) to keep in a saved project (like the cover
    pictures), or None if the folder's set isn't complete and readable."""
    files, problem = digit_files(folder)
    if problem or check_digits(folder)[1]:
        return None
    out = {}
    for d in "0123456789":
        with open(files[d], "rb") as f:
            out[d] = f.read()
    return out


def check_pack(folder, pattern):
    """Check a whole-number folder: (numbers it has, sample number, sample RGBA image, problems)."""
    if not (folder or "").strip():
        return set(), None, None, ["Choose the folder with a picture for each page number."]
    if not os.path.isdir(folder):
        return set(), None, None, [f"The number pictures' folder isn't there: {folder}"]
    problem = pattern_problem(pattern)
    if problem:
        return set(), None, None, [problem]
    nums = pack_numbers(folder, pattern)
    if not nums:
        return nums, None, None, [f"No pictures in that folder are named like “{pattern_name(pattern, 128)}"
                                  f"” (pattern {pattern}). Check the file-name pattern."]
    sample = 128 if 128 in nums else min(nums)
    try:
        img = load_picture(os.path.join(folder, pattern_name(pattern, sample)), pattern_name(pattern, sample))
    except ValueError as e:
        return nums, sample, None, [str(e) + "."]
    return nums, sample, img, []


def compose_preview(images, height_px, gap_px, colour=None):
    """Pictures side by side, scaled to one height (keeping their shapes), bottoms lined up - the GUI's preview
    of a composed number. images: RGBA PIL images; the tallest sets the scale (as in the PDF)."""
    from PIL import Image
    ref = max(im.size[1] for im in images)
    scale = height_px / ref
    parts = [im.resize((max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale))), Image.LANCZOS)
             for im in images]
    w = sum(p.size[0] for p in parts) + int(gap_px) * (len(parts) - 1)
    out = Image.new("RGBA", (max(1, w), max(1, height_px)), colour or (0, 0, 0, 0))
    x = 0
    for p in parts:
        out.alpha_composite(p, (x, height_px - p.size[1]))
        x += p.size[0] + int(gap_px)
    return out


# --------------------------------------------------------------------------- the PDF: numbers on the pages
def anchor(pos, odd, W, H, mi, mo, mt, mb, fw, fh, nsize):
    """Where a page number's text goes: (x, baseline y, "left" | "center" | "right"). The four positions of
    earlier versions are worked out exactly as they always were."""
    if pos == MIDDLE:                     # outside margin, halfway down the text area
        return (W - mo / 2 if odd else mo / 2), mb + fh / 2 - nsize * 0.35, "center"
    y = H - mt * 0.55 if pos.startswith("Top") else mb * 0.5
    if pos.endswith("center"):
        return (mi if odd else mo) + fw / 2, y, "center"
    if pos.endswith("left"):
        return (mi if odd else mo), y, "left"
    if pos.endswith("right"):
        return (mi if odd else mo) + fw, y, "right"
    return (W - mo, y, "right") if odd else (mo, y, "left")    # outside (and any unknown name, as before)


class Folio:
    """The page numbers of one book being typeset: the numerals as text, the pictures (read when a page needs
    them, each only once), and what to tell the user (pictures that are missing, numbers too big for Roman
    numerals, pictures made smaller to fit the margin)."""

    def __init__(self, s=None, book=None):
        s = s or {}
        self.mode = numerals(s)
        self.notes = []                   # plain warnings for the log, printing notes and preview
        self.text_pages = set()           # numbers printed as Arabic text instead (Roman range, missing picture)
        self.shrunk = False
        self.height = _num(s.get("pn_img_height"), 0.0, 0.0, IMG_HEIGHT_MAX)
        self.gap = _num(s.get("pn_img_gap"), 1.0, 0.0, GAP_MAX)
        self.digits, self.ref_h, self._cache, self._said = {}, 1, {}, set()
        self.folder, self.pattern = "", ""
        if self.mode == DIGIT_IMAGES:
            folder = (s.get("pn_digits_dir") or "").strip()
            imgs, problems = check_digits(folder)
            if problems:
                copies = getattr(book, "pn_digits", None) or {}
                try:
                    imgs = {d: load_picture(copies[d], f"{d} (saved in the project)") for d in "0123456789"}
                    self.notes.append("Page numbers: the digit pictures' folder can't be used (" + problems[0] +
                                      ") - the copies saved in the project were used.")
                except (KeyError, ValueError):
                    imgs = {}
                    self.notes.append("Page numbers: " + " ".join(problems) +
                                      " The page numbers were printed in Arabic numerals (1, 2, 3) instead.")
            if imgs:
                from reportlab.lib.utils import ImageReader
                self.digits = {d: (ImageReader(im), im.size[0], im.size[1]) for d, im in imgs.items()}
                self.ref_h = max(v[2] for v in self.digits.values())
            else:
                self.mode = ARABIC
        elif self.mode == WHOLE_IMAGES:
            self.folder = (s.get("pn_glyphs_dir") or "").strip()
            self.pattern = (s.get("pn_glyph_pattern") or PATTERNS[0]).strip()
            problem = pattern_problem(self.pattern)
            if not self.folder:
                problem = "no folder of number pictures was chosen"
            elif not os.path.isdir(self.folder):
                problem = f"the number pictures' folder isn't there ({self.folder})"
            if problem:
                self.notes.append(f"Page numbers: {problem[0].lower() + problem[1:]}".rstrip(".") +
                                  " - the page numbers were printed in Arabic numerals (1, 2, 3) instead.")
                self.mode = ARABIC

    @property
    def pictures(self):
        return self.mode in PICTURE_MODES

    def text(self, n):
        """Number n as text: the page's label on the contents page and in Edit contents (with pictures: Arabic,
        the pictures are drawn by draw())."""
        if self.mode in (ROMAN_LOWER, ROMAN_UPPER):
            r = roman_numeral(n, self.mode == ROMAN_UPPER)
            if r is None:
                self.text_pages.add(n)
                return str(n)
            return r
        return str(n)

    def parts(self, n):
        """The pictures for number n: [(ImageReader, pixel width, pixel height)], or None if there's no usable
        picture (that page then gets n in Arabic numerals)."""
        if self.mode == DIGIT_IMAGES and self.digits:
            return [self.digits[d] for d in str(n)] if n >= 0 else None
        if self.mode != WHOLE_IMAGES:
            return None
        if n in self._cache:
            if self._cache[n] is None:
                self.text_pages.add(n)
            return self._cache[n]
        part = None
        if 1 <= n <= WHOLE_MAX:               # (no picture is looked up for 0 or a number past 9999)
            name = pattern_name(self.pattern, n)
            try:
                im = load_picture(os.path.join(self.folder, name), name)
                from reportlab.lib.utils import ImageReader
                part = [(ImageReader(im), im.size[0], im.size[1])]
            except ValueError:
                part = None
        if part is None:
            self.text_pages.add(n)
        self._cache[n] = part
        return part

    def auto_height(self, nsize):
        """The pictures' height in pt: as set, or (0 = automatic) the number text's size for digit pictures and
        twice that for whole-number pictures (glyphs such as Cistercian numerals are tall)."""
        if self.height > 0:
            return self.height
        return nsize if self.mode == DIGIT_IMAGES else nsize * 2

    def sizes(self, parts, h):
        """[(width, height)] in pt for the pictures of one number at height h: digit pictures share one scale
        (the tallest digit = h), so every digit keeps its size next to the others; a whole-number picture is
        scaled to h."""
        if self.mode == DIGIT_IMAGES:
            sc = h / self.ref_h
            return [(pw * sc, ph * sc) for _r, pw, ph in parts]
        return [(pw * h / ph, h) for _r, pw, ph in parts]

    def draw(self, canv, parts, x, y, h, align, dash_font=None, dash_size=0, dash_y=0):
        """Draw the pictures of one number with their bottoms on y, at height h, left / centred / right of x,
        with "— " and " —" around them when dash_font is given. Returns (left, right) of what was drawn."""
        sz = self.sizes(parts, h)
        gap = self.gap if self.mode == DIGIT_IMAGES else 0
        w = sum(a for a, _b in sz) + gap * (len(sz) - 1)
        dl = dr = 0
        if dash_font:
            from reportlab.pdfbase.pdfmetrics import stringWidth
            dl, dr = stringWidth("— ", dash_font, dash_size), stringWidth(" —", dash_font, dash_size)
        total = dl + w + dr
        left = x if align == "left" else (x - total if align == "right" else x - total / 2)
        if dash_font:
            canv.setFont(dash_font, dash_size)
            canv.drawString(left, dash_y, "— ")
            canv.drawString(left + dl + w, dash_y, " —")
        px = left + dl
        for (reader, _pw, _ph), (a, b) in zip(parts, sz):
            canv.drawImage(reader, px, y, a, b, mask="auto")
            px += a + gap
        return left, left + total

    def fit(self, parts, h, max_w=None, max_h=None):
        """The height to draw at: h, made smaller when the number would be wider than max_w or taller than max_h
        (said once in the notes)."""
        out = h
        if max_h is not None and out > max_h:
            out = max(1.0, max_h)
        if max_w is not None:
            sz = self.sizes(parts, out)
            gaps = (self.gap if self.mode == DIGIT_IMAGES else 0) * (len(sz) - 1)
            w = sum(a for a, _b in sz)
            if w + gaps > max_w > 0 and w > 0:          # (the pictures shrink; the space between them doesn't)
                out = max(1.0, out * max(1.0, max_w - gaps) / w)
        if out < h - 0.01 and not self.shrunk:
            self.shrunk = True
            self.notes.append("Page numbers: some number pictures were drawn smaller than set so they stay in the "
                              "page margin (choose a smaller picture height or a bigger margin).")
        return out

    def note_once(self, key, msg):
        if key not in self._said:
            self._said.add(key)
            self.notes.append(msg)

    def report(self):
        """The warnings to show after the book was typeset."""
        out = list(self.notes)
        if self.text_pages:
            nums = sorted(self.text_pages)
            what = ", ".join(map(str, nums[:12])) + (f" and {len(nums) - 12} more" if len(nums) > 12 else "")
            if self.mode in (ROMAN_LOWER, ROMAN_UPPER):
                out.append(f"Page numbers: Roman numerals go up to {ROMAN_MAX} (MMMCMXCIX), so page number"
                           f"{'s' if len(nums) > 1 else ''} {what} {'were' if len(nums) > 1 else 'was'} "
                           "printed in Arabic numerals.")
            else:
                out.append(f"Page numbers: no usable picture for page number{'s' if len(nums) > 1 else ''} {what} "
                           f"(file name like “{pattern_name(self.pattern, nums[0])}” in "
                           f"{self.folder}"
                           + (f"; pictures go up to {WHOLE_MAX}" if nums[-1] > WHOLE_MAX else "") +
                           f") - {'they were' if len(nums) > 1 else 'it was'} printed in Arabic numerals.")
        return out


def _num(v, default, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:                            # NaN
        return default
    return min(hi, max(lo, f))


def draw_contents_number(folio, canvas, style, n, availWidth, dot, key=None):
    """A contents entry's page number as pictures (same pictures as on the page, at the contents' type size),
    right-aligned in the page-number column with the dot leaders before it. Returns False (draw nothing) if
    there's no picture for n - the caller then prints the number as text."""
    parts = folio.parts(n)
    if not parts:
        return False
    from reportlab.pdfbase.pdfmetrics import stringWidth
    x, y = canvas._curr_tx_info["cur_x"], canvas._curr_tx_info["cur_y"]
    h = style.fontSize * (0.85 if folio.mode == DIGIT_IMAGES else 1.0)   # (digits stand on the baseline)
    sz = folio.sizes(parts, h)
    gap = folio.gap * h / max(1.0, folio.auto_height(style.fontSize)) if folio.mode == DIGIT_IMAGES else 0
    w = sum(a for a, _b in sz) + gap * (len(sz) - 1)
    room = float(getattr(style, "rightIndent", 0) or 0) - 2      # the page-number column beside the titles
    if room > 4 and w > room:                                       # (very wide pictures: smaller, never over them)
        k = (room - gap * (len(sz) - 1)) / max(0.01, w - gap * (len(sz) - 1))
        h *= max(0.2, k)
        sz = folio.sizes(parts, h)
        w = sum(a for a, _b in sz) + gap * (len(sz) - 1)
    if dot:
        dotw = stringWidth(dot, style.fontName, style.fontSize)
        dotsn = max(0, int((availWidth - x - w) / dotw))
        if dotsn:
            tx = canvas.beginText(availWidth - w - dotsn * dotw, y)
            tx.setFont(style.fontName, style.fontSize)
            tx.setFillColor(style.textColor)
            tx.textLine(dotsn * dot)
            canvas.drawText(tx)
    px, base = availWidth - w, y - (0 if folio.mode == DIGIT_IMAGES else style.fontSize * 0.12)
    for (reader, _pw, _ph), (a, b) in zip(parts, sz):
        canvas.drawImage(reader, px, base, a, b, mask="auto")
        px += a + gap
    if key:
        canvas.linkRect("", key, (availWidth - w, base, availWidth, base + h), relative=1)
    return True


# --------------------------------------------------------------------------- the Word document
def word_number_format(s):
    """Word's page-number format for the numerals setting: 'lowerRoman', 'upperRoman' or None (Arabic)."""
    return {ROMAN_LOWER: "lowerRoman", ROMAN_UPPER: "upperRoman"}.get(numerals(s))


def word_alignment(s):
    """'left' / 'right' / 'center': where the Word document's page number sits in its header or footer."""
    pos = s.get("pn_position") or "Bottom center"
    return "left" if pos.endswith("left") else ("right" if pos.endswith("right") else "center")


def word_note(s):
    """What the Word document does differently from the page-number settings (the printing notes say it rather
    than leave it out quietly), or None."""
    pos = s.get("pn_position") or "Bottom center"
    if pos == "None":
        return None
    bits = []
    mode = numerals(s)
    if mode in PICTURE_MODES:
        bits.append("its page numbers are Arabic numerals (Word can't print pictures as page numbers)")
    if pos == MIDDLE:
        bits.append("they are centred at the bottom of the page (Word puts page numbers in the header or "
                    "footer, so not halfway down the outside edge)")
    elif pos.endswith("outside"):
        bits.append(f"they are centred at the {'top' if pos.startswith('Top') else 'bottom'} of the page "
                    "(not on the outside edge)")
    if not bits:
        return None
    return "Word document: " + "; ".join(bits) + ". The print PDF and the printing sheets have them as chosen."
