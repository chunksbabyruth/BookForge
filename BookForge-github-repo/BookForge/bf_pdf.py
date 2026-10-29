"""BookForge PDF typesetter (reportlab)."""
import io
import os
import re
import html
import unicodedata

from reportlab.lib.colors import black, HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, PageBreak, Flowable, Image, CondPageBreak)
from reportlab.platypus.flowables import DocIf, ImageAndFlowables
from reportlab.platypus.doctemplate import ActionFlowable
from reportlab.platypus.tableofcontents import TableOfContents, drawPageNumbers
from reportlab.platypus import TableStyle, Table

from bf_core import page_size_inches, plain, esc, blank_pages
import bf_matter
import bf_folio

GREY = HexColor("#555555")

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
from bf_fonts import BUILTIN_NAMES, SAME_BODY, SAME_HEAD, resolve, migrate


def _font_index():
    # Keep PDF fallback glyph discovery aligned with the font picker on each OS.
    # Modern Linux systems commonly use ~/.local/share/fonts; macOS has system,
    # shared, and per-user font directories.
    dirs = []
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs.append(os.path.join(win, "Fonts"))
    la = os.environ.get("LOCALAPPDATA")
    if la:
        dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    if os.name != "nt":
        import sys
        if sys.platform == "darwin":
            dirs += [
                "/System/Library/Fonts",
                "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"),
            ]
        else:
            dirs += [
                "/usr/share/fonts",
                "/usr/local/share/fonts",
                os.path.expanduser("~/.local/share/fonts"),
                os.path.expanduser("~/.fonts"),
            ]
    idx = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _sub, files in os.walk(d):
            for f in files:
                idx.setdefault(f.lower(), os.path.join(root, f))
    return idx

_FONT_INDEX = None


def font_index():
    global _FONT_INDEX
    if _FONT_INDEX is None:
        _FONT_INDEX = _font_index()
    return _FONT_INDEX


def _ttf(name, path):
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    kw = {"subfontIndex": 0} if path.lower().endswith(".ttc") else {}
    pdfmetrics.registerFont(TTFont(name, path, **kw))
    return name


def font_roles(s, log=print):
    """(body, headings, drop cap) font families as reportlab (R, B, I, BI) name tuples."""
    migrate(s)
    body = resolve(s.get("font_family") or "Times (built-in)", s, log)
    hf = s.get("heading_font") or SAME_BODY
    head = body if hf == SAME_BODY else resolve(hf, s, log)
    dc = s.get("dropcap_font") or SAME_HEAD
    drop = head if dc == SAME_HEAD else body if dc == SAME_BODY else resolve(dc, s, log)
    return body, head, drop


def register_fonts(s, log=lambda m: None):
    return font_roles(s, log)[0]


# --------------------------------------------------------------------------
# Hyphenation (pyphen dictionaries + the user's own word list)
# --------------------------------------------------------------------------
HYPH_LANGS = {"Off": None, "English (US)": "en_US", "English (UK)": "en_GB", "French": "fr",
              "German": "de_DE", "Spanish": "es", "Italian": "it_IT", "Portuguese (Brazil)": "pt_BR",
              "Portuguese (Portugal)": "pt_PT", "Dutch": "nl_NL", "Swedish": "sv", "Danish": "da_DK",
              "Norwegian": "nb_NO", "Finnish": "fi_FI", "Polish": "pl_PL", "Czech": "cs_CZ",
              "Hungarian": "hu_HU", "Russian": "ru_RU", "Ukrainian": "uk_UA", "Greek": "el_GR",
              "Latin": "la"}


def parse_hyph_words(text):
    """'Ka-la-din' -> {'kaladin': [2, 4]}; a word with no hyphens is never split."""
    out = {}
    for tok in re.split(r"[,;\s]+", text or ""):
        tok = tok.strip()
        if not tok:
            continue
        parts = re.split(r"[-\u00ad\u00b7=]", tok)
        word, pos, n = "".join(parts), [], 0
        for part in parts[:-1]:
            n += len(part)
            pos.append(n)
        out[word.lower()] = pos
    return out


def make_hyphenator(s):
    lang = HYPH_LANGS.get(s.get("hyph_lang", "English (US)"))
    if not lang:
        return None
    try:
        import pyphen
        dic = pyphen.Pyphen(lang=lang if lang in pyphen.LANGUAGES else "en_US", left=2, right=3)
    except Exception:
        dic = None
    custom = parse_hyph_words(s.get("hyph_words", ""))

    def hyphenate(word):
        if "\xa0" in word:              # words tied by a no-break space: only split the first one
            first, rest = word.split("\xa0", 1)
            return [(a, b + "\xa0" + rest) for a, b in hyphenate(first)]
        m = re.match(r"^(\W*)(.*?)(\W*)$", word, re.S)
        pre, core, post = m.groups()
        key = core.lower()
        if key in custom:
            pos = custom[key]
        elif dic is not None and core.isalpha():
            pos = [int(x) for x in dic.positions(core)]
        else:
            pos = []
        return [(pre + core[:p], core[p:] + post) for p in sorted(pos, reverse=True) if 1 < p < len(core) - 1]
    return hyphenate


def no_runt(markup):
    """Tie the last two words together so a paragraph never ends with one short word alone."""
    depth, i = 0, len(markup) - 1
    while i > 0:
        ch = markup[i]
        if ch == ">":
            depth += 1
        elif ch == "<":
            depth -= 1
        elif ch == " " and depth == 0:
            tail = plain(markup[i + 1:]).strip()
            if 0 < len(tail) <= 7:
                return markup[:i] + "&#160;" + markup[i + 1:]
            return markup
        i -= 1
    return markup


# --------------------------------------------------------------------------
# Missing-character fallback: any character the chosen font can't draw is
# switched to an installed font that can (Greek, accents, symbols, CJK...).
# --------------------------------------------------------------------------
FALLBACKS = [
    ("Times New Roman", "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    ("Palatino Linotype", "pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    ("Cambria", "cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    ("Segoe UI", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    ("Segoe UI Symbol", "seguisym.ttf", "", "", ""),
    ("Segoe UI Emoji", "seguiemj.ttf", "", "", ""),       # emoji drawn as plain (one-colour) shapes
    ("Segoe UI Historic", "seguihis.ttf", "", "", ""),
    ("Nirmala UI", "nirmala.ttf", "nirmalab.ttf", "", ""),
    ("Ebrima", "ebrima.ttf", "ebrimabd.ttf", "", ""),
    ("Microsoft YaHei", "msyh.ttc", "msyhbd.ttc", "", ""),
    ("Yu Gothic", "yugothr.ttc", "yugothb.ttc", "", ""),
    ("Malgun Gothic", "malgun.ttf", "malgunbd.ttf", "", ""),
    ("Arial Unicode MS", "arialuni.ttf", "", "", ""),
    ("FreeSerif", "freeserif.ttf", "freeserifbold.ttf", "freeserifitalic.ttf", "freeserifbolditalic.ttf"),
    ("DejaVu Serif", "dejavuserif.ttf", "dejavuserif-bold.ttf", "dejavuserif-italic.ttf",
     "dejavuserif-bolditalic.ttf"),
    ("DejaVu Sans", "dejavusans.ttf", "dejavusans-bold.ttf", "dejavusans-oblique.ttf",
     "dejavusans-boldoblique.ttf"),
]
_CMAPS = {}
RTL_RUN = re.compile(r"[\u0590-\u05ff\ufb1d-\ufb4f](?:[\u0590-\u05ff\ufb1d-\ufb4f\s'\"\u05f3\u05f4]*"
                     r"[\u0590-\u05ff\ufb1d-\ufb4f])?")


def _cmap(fontname):
    if fontname not in _CMAPS:
        try:
            _CMAPS[fontname] = set(pdfmetrics.getFont(fontname).face.charToGlyph.keys())
        except Exception:
            _CMAPS[fontname] = set()
    return _CMAPS[fontname]


class Coverage:
    def __init__(self, regular):
        self.regular = regular
        self.builtin = regular in BUILTIN_NAMES
        self.choice = {}
        self.missing = set()
        self._fbs = None

    def _base_has(self, ch):
        if self.builtin:
            try:
                ch.encode("cp1252")
                return True
            except UnicodeEncodeError:
                return False
        return ord(ch) in _cmap(self.regular)

    def _fallbacks(self):
        if self._fbs is None:
            self._fbs = []
            idx = font_index()
            for fam, *files in FALLBACKS:
                if files[0] not in idx:
                    continue
                tag = "BFfb_" + re.sub(r"\W", "", fam)
                try:
                    names = [_ttf(f"{tag}-{suf}", idx[f]) if f and f in idx else None
                             for f, suf in zip(files, ("R", "B", "I", "BI"))]
                except Exception:
                    continue
                r = names[0]
                if not r:
                    continue
                registerFontFamily(r, normal=r, bold=names[1] or r, italic=names[2] or r,
                                   boldItalic=names[3] or names[2] or names[1] or r)
                self._fbs.append(r)
        return self._fbs

    def font_for(self, ch):
        """None = base font is fine; otherwise the name of a fallback font."""
        if ch in self.choice:
            return self.choice[ch]
        res = None
        if not (ch.isspace() or self._base_has(ch)):
            res = next((f for f in self._fallbacks() if ord(ch) in _cmap(f)), None)
            if res is None:
                self.missing.add(ch)
        self.choice[ch] = res
        return res

    @staticmethod
    def _rtl(part):
        """PDF text is drawn left to right, so Hebrew runs are reversed (keeping vowel points)."""
        def flip(m):
            clusters = []
            for ch in m.group(0):
                if clusters and unicodedata.combining(ch):
                    clusters[-1] += ch
                else:
                    clusters.append(ch)
            return "".join(reversed(clusters))
        return RTL_RUN.sub(flip, part)

    def apply(self, markup):
        if markup.isascii():
            return markup
        out = []
        for part in re.split(r"(<[^>]+>|&#?\w+;)", markup):
            if not part or part[0] in "<&" or part.isascii():
                out.append(part)
                continue
            part = self._rtl(part)
            runs, cur, buf = [], None, []
            for ch in part:
                f = cur if ch == " " else self.font_for(ch)
                if f != cur:
                    if buf:
                        runs.append((cur, "".join(buf)))
                    cur, buf = f, []
                buf.append(ch)
            if buf:
                runs.append((cur, "".join(buf)))
            for f, txt in runs:
                out.append(f'<font face="{f}">{txt}</font>' if f else txt)
        return "".join(out)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
SMALL = {"a", "an", "the", "and", "but", "or", "nor", "for", "of", "in", "on",
         "at", "to", "by", "with", "from", "as", "into", "over", "upon"}
ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " Hundred" + (" " + words(n % 100) if n % 100 else "")
    return str(n)


def roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, r in vals:
        while n >= v:
            out += r
            n -= v
    return out


def title_case(t):
    out = []
    for i, w in enumerate(t.split(" ")):
        lw = w.lower()
        if i and lw.strip("([\"'\u2018\u201c") in SMALL:
            out.append(lw)
            continue
        parts = lw.split("-")
        parts = [re.sub(r"^([^A-Za-z]*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), p)
                 for p in parts]
        out.append("-".join(parts))
    return " ".join(out)


def apply_case(t, mode):
    if mode == "Title Case":
        return title_case(t)
    if mode == "UPPERCASE":
        return t.upper()
    return t


LABELISH = re.compile(r"^\s*(chapter|chap\.|part|book|section|canto|stave|letter|act|"
                      r"prologue|epilogue|[ivxlcdm]+\.?\s|\d+\.?\s)", re.I)


def auto_label(style, n):
    return {"Chapter 1": f"Chapter {n}", "Chapter One": f"Chapter {words(n)}",
            "CHAPTER I": f"CHAPTER {roman(n)}", "1": str(n), "I": roman(n)}.get(style, "")


# --------------------------------------------------------------------------
# Flowables
# --------------------------------------------------------------------------
class Marker(Flowable):
    """Zero-size flowable that runs a callback while the page is laid out."""

    def __init__(self, fn):
        Flowable.__init__(self)
        self.fn = fn
        self.width = self.height = 0

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        self.fn(self.canv, self.canv._doctemplate)


class Anchor(Marker):
    def __init__(self, key, outline, olevel, toc_text=None, toc_level=0, title="", opener=False,
                 body_start=False, uid=None):
        Marker.__init__(self, self._run)
        self.key, self.outline, self.olevel = key, outline, olevel
        self.toc_text, self.toc_level, self.title = toc_text, toc_level, title
        self.opener, self.body_start, self.uid = opener, body_start, uid

    def _run(self, canv, doc):
        p = canv.getPageNumber()
        if self.body_start and doc.bf.get("body_start") is None:
            doc.bf["body_start"] = p
        if self.opener:
            doc.bf["opener"][p] = True
            doc.bf["cur"] = self.title
        doc.bf.setdefault("anchors", {})[self.key] = p      # where each chapter starts (for the preview)
        canv.bookmarkPage(self.key)
        canv.addOutlineEntry(self.outline, self.key, level=self.olevel, closed=True)


class Rule(Flowable):
    def __init__(self, width, thickness=0.6, space=6, diamond=False, align=TA_CENTER):
        Flowable.__init__(self)
        self.w, self.t, self.space, self.diamond, self.align = width, thickness, space, diamond, align

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, self.space * 2

    def draw(self):
        c = self.canv
        w = self.w
        x0 = 0 if self.align == TA_LEFT else (self.aw - w) if self.align == TA_RIGHT else (self.aw - w) / 2
        cx = x0 + w / 2                 # the diamond sits in the middle of the line
        y = self.space
        c.setStrokeColor(black)
        c.setLineWidth(self.t)
        if self.diamond:
            g = 4
            c.line(x0, y, cx - g * 2, y)
            c.line(cx + g * 2, y, x0 + w, y)
            p = c.beginPath()
            p.moveTo(cx, y + g)
            p.lineTo(cx + g, y)
            p.lineTo(cx, y - g)
            p.lineTo(cx - g, y)
            p.close()
            c.setFillColor(black)
            c.drawPath(p, fill=1, stroke=0)
        else:
            c.line(x0, y, x0 + w, y)


class Gap(Flowable):
    """Space after something (a picture, a dedication line, a block of notes). At the bottom of a page it takes
    only the room that is left there, and none at the top of a page. A plain Spacer that doesn't fit below the
    last line moves to the top of the next page on its own; when a new page follows (the next chapter, the
    contents, an own-page picture...) that page is left with nothing on it - an unwanted blank page in the book
    and on the printing sheets. Where it fits, it takes exactly the room a Spacer takes."""

    def __init__(self, width, height):
        Flowable.__init__(self)
        self.width, self.height = width, height

    def wrap(self, aw, ah):                 # (only used when something measures it)
        return self.width, max(0.0, min(self.height, ah))

    def frameAction(self, frame):           # placed by the frame itself: it can never move to another page
        if not frame._atTop:
            frame._y -= min(self.height, max(0.0, frame._y - frame._y1p))
            if frame._oASpace:
                frame._prevASpace = 0      # (as after a Spacer)


class KeepTop(Spacer):
    """Space above a chapter title. It takes exactly the room a Spacer takes, but it remembers whether it
    started a page, so AtTopAgain (right after it) can keep the page counted as "at the top": a title kept
    with a long first paragraph is then not pushed on to the next page, which used to leave an empty page."""

    def wrap(self, aw, ah):
        f = getattr(self, "_frame", None)
        self.was_top = bool(f is not None and getattr(f, "_atTop", 0))
        return Spacer.wrap(self, aw, ah)


class AtTopAgain(Flowable):
    """Follows a KeepTop. When the space started a page, the page still counts as "at the top", and the space
    above the next line (which ReportLab leaves out at the top of a page) is added here, so every line stays
    exactly where it was."""

    def __init__(self, space):
        Flowable.__init__(self)
        self.space, self.extra = space, 0.0

    def frameAction(self, frame):
        if getattr(self.space, "was_top", False) and not frame._atTop:
            frame._y -= min(self.extra, max(0.0, frame._y - frame._y1p))
            frame._atTop = 1


TITLE_ALIGN = {"Centered": TA_CENTER, "Left": TA_LEFT, "Right": TA_RIGHT}


def _num(v, default, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, x))


def title_layout(s):
    """The title alignment and position settings, checked: an unknown or unusable value means its default
    (the defaults print every title where versions before 1.8.0 did)."""
    al = lambda k: TITLE_ALIGN.get(s.get(k), TA_CENTER)        # noqa: E731
    size = lambda k: (lambda v: 0.0 if v < 6 else v)(_num(s.get(k), 0.0, 0.0, 144.0))   # noqa: E731
    return {"tp_align": al("tp_align"), "tp_pos": _num(s.get("tp_pos"), 20.0, 0.0, 90.0),
            "tp_title_size": size("tp_title_size"), "ch_align": al("ch_align"), "part_align": al("part_align"),
            "part_pos": _num(s.get("part_pos"), 30.0, 0.0, 90.0), "part_size": size("part_size"),
            "sink": _num(s.get("chapter_sink"), 0.0, 0.0, 12.0)}


def _block_height(flowables, width, height):
    """How tall a run of flowables is on the page (their own spacing included)."""
    total = 0.0
    for i, f in enumerate(flowables):
        _w, h = f.wrap(width, height)
        total += h + (f.getSpaceBefore() if i else 0) + f.getSpaceAfter()
    return total


DROP_RE = re.compile(r"^((?:<[^>]+>)*)((?:&\w+;|['\"\u2018\u201c\u201e\u00ab(\u00bf\u00a1])*)(\w)")


class DropLetter(Flowable):
    """A big initial spanning `lines` lines of text (used with ImageAndFlowables).

    quote_mode: how an opening quotation mark is handled
      "hang"  - quote hangs in the margin so the letter lines up with the text
      "small" - quote at text size just before the big letter
      "big"   - quote is drawn as large as the letter
    """

    def __init__(self, letter, font, body_size, lead, lines=2, quote="", quote_mode="hang", qfont=None):
        Flowable.__init__(self)
        from reportlab.pdfbase.pdfmetrics import stringWidth
        cap = 0.7
        lines = max(2, int(lines))
        self.size = (lead * (lines - 1) + body_size * cap) / cap
        self.letter, self.font, self.lead, self.body, self.lines = letter, font, lead, body_size, lines
        self.quote, self.mode, self.qfont = quote, quote_mode, qfont or font
        if quote and quote_mode == "big":
            self.letter = quote + letter
            self.quote = ""
        self.lw = stringWidth(self.letter, font, self.size)
        self.qsize = body_size if quote_mode == "small" else self.size * 0.6
        self.qw = stringWidth(self.quote, self.qfont, self.qsize) if self.quote else 0
        self.width = self.lw + (self.qw + 1 if self.quote and quote_mode == "small" else 0)
        self.height = lead * lines - (lead - body_size) * 0.5

    def wrap(self, aw, ah):
        return self.width, self.height

    def _restrictSize(self, aw, ah):
        return self.width, self.height

    def _unRestrictSize(self):
        # ImageAndFlowables calls this when the paragraph is laid out again (e.g. moved to the next page);
        # the letter never shrinks, so there is nothing to undo. Without it those books failed to build.
        pass

    def draw(self):
        c = self.canv
        c.setFillColor(black)
        base = self.height - self.body * 0.95 - self.lead * (self.lines - 1)
        x = 0
        if self.quote:
            top = base + self.size * 0.7
            c.setFont(self.qfont, self.qsize)
            if self.mode == "small":
                c.drawString(0, self.height - self.body * 0.95, self.quote)
                x = self.qw + 1
            else:                           # hang in the margin, top-aligned with the letter
                c.drawString(-self.qw - 1, top - self.qsize * 0.7, self.quote)
        c.setFont(self.font, self.size)
        c.drawString(x, base, self.letter)


def _bigger_text(markup, size):
    """True if the markup sets some words bigger than `size` points (font size="14" or size="130%")."""
    for v in re.findall(r'<font\b[^>]*\bsize="([^"]+)"', markup):
        try:
            n = size * float(v[:-1]) / 100 if v.endswith("%") else float(v)
        except ValueError:
            continue
        if n > size * 1.05:
            return True
    return False


class PagePicture(Flowable):
    """A picture on a page of its own, centred in the text area - or, with full=True, covering the
    whole page edge to edge (no page number or running head is printed on that page).
    It takes the whole frame, so whatever follows starts on the next page."""

    def __init__(self, data, pct=0, align="", full=False):
        Flowable.__init__(self)
        self.data, self.pct, self.align, self.full = data, int(pct or 0), align or "center", full
        self.iw, self.ih = ImageReader(io.BytesIO(data)).getSize()

    def wrap(self, aw, ah):
        self.aw, self.ah = aw, ah
        return aw, max(0, ah - 0.5)

    def split(self, aw, ah):
        return []

    def drawOn(self, canvas, x, y, _sW=0):
        from bf_pictures import fit_box
        doc = canvas._doctemplate
        p = canvas.getPageNumber()
        img = ImageReader(io.BytesIO(self.data))
        canvas.saveState()
        if self.full:
            pw, ph = doc.pagesize
            bx, by, bw, bh = fit_box(self.iw, self.ih, 0, 0, pw, ph, fill=True)
            path = canvas.beginPath()
            path.rect(0, 0, pw, ph)
            canvas.clipPath(path, stroke=0, fill=0)
            doc.bf.setdefault("fullpage", {})[p] = True
        else:
            top = y + self.ah
            bx, by, bw, bh = fit_box(self.iw, self.ih, x, top - self.ah, self.aw, self.ah - 1, fill=False)
            if self.pct:
                k = min(self.aw * self.pct / 100 / self.iw, (self.ah - 1) / self.ih)
                bw, bh = self.iw * k, self.ih * k
                by = top - self.ah + (self.ah - bh) / 2
            bx = {"left": x, "right": x + self.aw - bw}.get(self.align, x + (self.aw - bw) / 2)
            doc.bf.setdefault("plate", {})[p] = True
        canvas.drawImage(img, bx, by, bw, bh, mask="auto")
        canvas.restoreState()


class PageForPicture(ActionFlowable):
    """Before a picture on a page of its own: a new page - unless nothing has been printed on this page yet
    (a chapter that starts with the picture), then the picture takes this page, from its top. ReportLab's
    PageBreakIfNotEmpty counted a chapter's invisible marks (its contents link, the space of "Drop chapter start
    down") as something on the page and broke anyway, which left an empty page before the picture."""

    def __init__(self):
        ActionFlowable.__init__(self, ("pageBreak",))

    def apply(self, doc):
        if doc.bf["content"].get(doc.page):
            doc.handle_pageBreak()
        else:
            doc.frame._reset()


def picture_flowables(b, fw, fh):
    """The flowables for a picture block (see Block.img_width / img_place / align)."""
    if b.img_place in ("page", "full"):
        return [PageForPicture(), PagePicture(b.image, b.img_width, b.align, full=b.img_place == "full")]
    from bf_pictures import picture_scale
    ir = ImageReader(io.BytesIO(b.image))
    iw, ih = ir.getSize()
    k = picture_scale(iw, ih, int(b.img_width or 0), "", fw, fh, fw, fh)
    img = Image(io.BytesIO(b.image), width=iw * k, height=ih * k)
    img.hAlign = {"left": "LEFT", "right": "RIGHT"}.get(b.align, "CENTER")
    return [Spacer(1, 6), img, Gap(1, 8)]


class WriteLines(Flowable):
    def __init__(self, gap):
        Flowable.__init__(self)
        self.gap = gap

    def wrap(self, aw, ah):
        self.aw, self.ah = aw, ah - 2
        return aw, self.ah

    def draw(self):
        c = self.canv
        c.setStrokeColor(HexColor("#999999"))
        c.setLineWidth(0.4)
        y = self.ah - self.gap
        while y > 0:
            c.line(0, y, self.aw, y)
            y -= self.gap


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
class BookDoc(BaseDocTemplate):
    folio = bf_folio.Folio()           # how the numbers are written (build_pdf sets the book's own)

    def __init__(self, filename, s, book, **kw):
        BaseDocTemplate.__init__(self, filename, **kw)
        self.s, self.book = s, book
        self.beforeDocument()

    def beforeDocument(self):
        # Reset every pass; the body start is only trusted once reached in THIS pass.
        self.bf = {"body_start": None, "opener": {}, "content": {}, "nonum": {}, "cur": "", "userblank": {}}
        self.folio.text_pages.clear()                # (numbers printed as text instead: this pass's pages only)

    def handle_pageBegin(self):
        # Odd (right-hand) pages use the "odd" frame, even pages the "even" one, so the inside margin is
        # always on the spine side. (ReportLab's autoNextPageTemplate alone kept each template for two
        # pages in a row, putting the wide inside margin on the outside of every other pair of pages.)
        if len(self.pageTemplates) == 2:
            self.pageTemplate = self.pageTemplates[0 if (self.page + 1) % 2 else 1]
        BaseDocTemplate.handle_pageBegin(self)

    def page_value(self, p):
        """Page p's number: (n, front) - front = True for the front matter's own i, ii, iii ("Roman front
        matter, 1 on first chapter") - or None when the page has no number. Blank pages added before the book
        ("Blank pages at beginning") are not counted: the book's own numbering starts after them."""
        mode = self.s.get("pn_mode", "")
        fb = int(self.s.get("blank_pages_start") or 0)
        if p <= fb:
            return None
        if mode.startswith("Every"):
            return p - fb, False
        bs = self.bf.get("body_start")
        if bs is None or p < bs:
            return (p - fb, True) if mode.startswith("Roman") else None
        return p - bs + 1, False

    def page_label(self, p):
        """The number printed on page p as text (in the chosen numerals; the Roman front matter keeps i, ii,
        iii), or "" for a page without a number. With number pictures this is the Arabic number (the contents
        and Edit contents use it; the page itself gets the pictures)."""
        v = self.page_value(p)
        if v is None:
            return ""
        n, front = v
        return roman(n).lower() if front else self.folio.text(n)

    def afterFlowable(self, f):
        if isinstance(f, Anchor):
            if f.toc_text is not None:
                # the contents shows the number printed on that page (1, 2... or i, ii...)
                lab = self.page_label(self.page)
                self.notify("TOCEntry", (f.toc_level, f.toc_text, lab, f.key, f.uid))
                if f.uid:
                    self.bf.setdefault("toc_labels", {})[f.uid] = lab
            return
        # Table: the contents page splits into tables when it runs over a page; those pages are not blank
        # (their page numbers were hidden as if they were).
        if isinstance(f, (Paragraph, Image, TableOfContents, Table, Rule, WriteLines, ImageAndFlowables,
                          PagePicture)):
            self.bf["content"][self.page] = True


def empty_pages(doc):
    """Pages of the finished book with nothing printed on them that nobody asked for: not "Blank pages at
    beginning/end", not the left-hand page before a right-hand start, not the back of the front cover picture.
    (Checked after every book is typeset, so an unwanted blank page is reported instead of printed unnoticed.)"""
    bf = doc.bf
    return [p for p in range(1, doc.page + 1) if not bf["content"].get(p) and not bf["userblank"].get(p)
            and not bf.get("planned", {}).get(p) and not bf.get("fullpage", {}).get(p)]


def empty_pages_note(pages):
    shown = ", ".join(map(str, pages[:12])) + (f" and {len(pages) - 12} more" if len(pages) > 12 else "")
    return (f"page{'s' if len(pages) > 1 else ''} {shown} of the book (counting every page of the print PDF) "
            f"{'have' if len(pages) > 1 else 'has'} nothing printed on {'them' if len(pages) > 1 else 'it'}, "
            "and no setting asked for a blank page there. Check the print PDF and the imposed files before "
            "printing; an empty chapter, or a chapter or page with only space in it, can cause this.")


# --------------------------------------------------------------------------
# Contents page
# --------------------------------------------------------------------------
def contents_entries(book, s):
    """The automatic contents: one entry per included part/chapter, in book order.
    [{"uid", "level", "text"}] - text is plain (not markup), exactly as the contents page prints it."""
    chapters = book.active()
    has_parts = any(c.level == 0 for c in chapters)
    out, chap_no, seen_part = [], 0, False
    up = str.upper if s.get("toc_case") == "UPPERCASE" else str
    for ch in chapters:
        if ch.level == 0:
            seen_part = True
            title = apply_case(ch.title, s["title_case"])
            lbl = ch.label
            disp = f"{lbl} \u2014 {title}" if lbl and title else (title or lbl)
            out.append({"uid": ch.uid, "level": 0, "text": apply_case(disp, s["toc_case"])})
            continue
        chap_no += 1
        tn = s.get("toc_numbers", "None")
        tt = apply_case(ch.title, s["toc_case"])
        # The "Chapter N:" prefix and a chapter's own label follow UPPERCASE too (Title Case
        # leaves them as they are, so labels such as "CHAPTER IV" keep their numerals).
        if ch.label:
            text = f"{up(ch.label)} \u2014 {tt}" if tt else up(ch.label)
        elif tn == "Number (1.)":
            text = f"{chap_no}. {tt}"
        elif tn == "Chapter N:":
            text = f"{up('Chapter')} {chap_no}: {tt}"
        else:
            text = tt
        out.append({"uid": ch.uid, "level": 1 if (has_parts and seen_part) else 0, "text": text})
    return out


def contents_rows(auto, edits):
    """Every entry for the "Edit contents" window, hidden ones included, in display order:
    [{"uid", "custom", "auto", "title", "page", "show", "level", "auto_level", "markup", "space"}].
    "markup" (fonts, bold... set in Specific Text Edit) and "space" (points above) are None/0 unless set.

    auto: contents_entries(); edits: the book's saved changes (see Book.toc). "title"/"page" are None/""
    unless the user typed them. Chapters added since the contents was edited appear after the chapter
    before them; edits for chapters that no longer exist are dropped."""
    def fresh(a):
        return {"uid": a["uid"], "custom": False, "auto": a["text"], "title": None, "page": "",
                "show": True, "level": a["level"], "auto_level": a["level"], "markup": None, "space": 0}

    def look(r, ed):
        r["markup"] = ed.get("markup") or None
        try:
            r["space"] = max(0, min(int(ed.get("space") or 0), 72))
        except (TypeError, ValueError):
            r["space"] = 0
        return r
    if not edits:
        return [fresh(a) for a in auto]
    by_uid = {a["uid"]: a for a in auto}
    rows, seen = [], set()
    for ed in edits:
        if ed.get("custom"):
            if (ed.get("title") or "").strip():
                lvl = int(ed.get("level") or 0)
                rows.append(look({"uid": None, "custom": True, "auto": "", "title": ed["title"].strip(),
                                  "page": (ed.get("page") or "").strip(), "show": bool(ed.get("show", True)),
                                  "level": lvl, "auto_level": lvl}, ed))
            continue
        a = by_uid.get(ed.get("uid"))
        if a is None or a["uid"] in seen:
            continue                                   # that chapter was deleted or left out
        seen.add(a["uid"])
        r = fresh(a)
        title = ed.get("title")
        r["title"] = title.strip() if isinstance(title, str) and title.strip() else None
        r["page"] = (ed.get("page") or "").strip()
        r["show"] = bool(ed.get("show", True))
        if ed.get("level") is not None:
            r["level"] = int(ed["level"])
        rows.append(look(r, ed))
    for i, a in enumerate(auto):                       # chapters the edits don't know about yet
        if a["uid"] in seen:
            continue
        at = 0
        for prev in reversed(auto[:i]):
            pos = next((k for k, r in enumerate(rows) if r["uid"] == prev["uid"]), None)
            if pos is not None:
                at = pos + 1
                break
        rows.insert(at, fresh(a))
        seen.add(a["uid"])
    return rows


def rows_to_edits(rows, auto):
    """The rows of the "Edit contents" window -> what is saved in the book ([] = automatic contents)."""
    key = lambda r: (r["uid"], r["custom"], r["title"], r["page"], r["show"], r["level"],   # noqa: E731
                     r.get("markup") or None, r.get("space") or 0)
    if [key(r) for r in rows] == [key(r) for r in contents_rows(auto, [])]:
        return []
    out = []
    for r in rows:
        if r["custom"]:
            e = {"custom": True, "title": r["title"], "page": r["page"], "level": r["level"], "show": r["show"]}
        else:
            e = {"uid": r["uid"], "title": r["title"], "page": r["page"], "show": r["show"],
                 "level": None if r["level"] == r["auto_level"] else r["level"]}
        if r.get("markup"):
            e["markup"] = r["markup"]
        if r.get("space"):
            e["space"] = r["space"]
        out.append(e)
    return out


def merged_contents_page(p_keep, p_gone, choice=None):
    """The page number typed for the surviving chapter's contents entry after another chapter is merged into
    it (p_keep / p_gone: the numbers typed for the two entries, '' = none). Only the absorbed chapter had one:
    it is kept (moved to the surviving entry). Both had different ones: choice, the one the user picked.
    Otherwise None: the surviving entry stays as it is."""
    if p_gone and p_keep and p_gone != p_keep:
        return choice
    if p_gone and not p_keep:
        return p_gone
    return None


def merge_contents_edits(edits, keep_uid, gone_uid, page=None):
    """Book.toc after the chapter gone_uid is merged into the chapter keep_uid ("Merge into previous").
    The absorbed chapter's entry goes: its typed text, formatting and hidden setting belonged to a heading
    that is no longer a chapter. page (see merged_contents_page), when given, becomes the surviving entry's
    typed page number. The surviving chapter keeps its uid, so its entry stays attached to it when it is
    renamed or moved. A typed number is only what the contents page prints beside the entry - it never
    moves the chapter. Returns a new list; the one given is not changed."""
    out, at = [], None
    for e in edits or []:
        if not e.get("custom") and e.get("uid") == gone_uid:
            at = len(out)
            continue
        out.append(dict(e))
    if page:
        k = next((n for n, e in enumerate(out) if not e.get("custom") and e.get("uid") == keep_uid), None)
        if k is None:            # the surviving chapter had no saved entry: one where the absorbed entry was
            out.insert(len(out) if at is None else at,
                       {"uid": keep_uid, "title": None, "page": page, "show": True, "level": None})
        else:
            out[k]["page"] = page
    return out


def swap_contents_entries(edits, uid_a, uid_b):
    """Book.toc after two chapters swapped places on the Chapters step (Move up / Move down): their contents
    entries swap places too, so an edited contents keeps following the chapter order. Entries added in Edit
    contents stay where they are. Returns a new list."""
    out = [dict(e) for e in edits or []]
    at = {e.get("uid"): n for n, e in enumerate(out) if not e.get("custom")}
    if uid_a in at and uid_b in at:
        a, b = at[uid_a], at[uid_b]
        out[a], out[b] = out[b], out[a]
    return out


def keep_left_out(new, old, book):
    """Contents edits written again from the entries shown (Edit contents, or the contents page in Specific Text
    Edit), plus the saved entries of chapters that are left out for now (unticked on the Chapters step): those
    aren't shown, so they used to be dropped, and a chapter put back lost its typed page number and words.
    Each goes back after the entry it followed. Returns a new list."""
    out_uids = {c.uid for c in getattr(book, "chapters", []) if not c.include}
    old = list(old or [])
    kept = [(n, e) for n, e in enumerate(old) if not e.get("custom") and e.get("uid") in out_uids]
    if not kept:
        return new
    out = [dict(e) for e in new or []]
    for n, e in kept:
        if any(not x.get("custom") and x.get("uid") == e["uid"] for x in out):
            continue
        at = 0
        for prev in reversed(old[:n]):
            pos = next((k for k, x in enumerate(out) if not prev.get("custom") and not x.get("custom")
                        and x.get("uid") == prev.get("uid")), None)
            if pos is not None:
                at = pos + 1
                break
        out.insert(at, dict(e))
    return out


def apply_contents_edits(auto, edits):
    """The entries the contents page prints: auto entries ({"uid", "level", "text", ...}) with the edits
    applied. Typed titles get "edited": True, typed page numbers replace the automatic ones."""
    by_uid = {a["uid"]: a for a in auto}
    out = []
    for r in contents_rows(auto, edits):
        if not r["show"]:
            continue
        if r["custom"]:
            e = {"uid": None, "level": r["level"], "text": r["title"], "page": r["page"], "custom": True,
                 "typed_page": True}
        else:
            e = dict(by_uid[r["uid"]])
            e["level"] = r["level"]
            if r["title"]:
                e["text"], e["edited"] = r["title"], True
            if r["page"]:
                e["page"] = r["page"]
                e["typed_page"] = True      # (printed as typed, never as a page-number picture)
        if r.get("markup"):                 # formatted in Specific Text Edit: that look, with the entry's words
            e["markup"] = bf_matter.restyle(r["markup"], e["text"])
        if r.get("space"):
            e["space"] = r["space"]
        out.append(e)
    return out


class BookTOC(TableOfContents):
    """The contents page: the automatic entries (reported while the chapters are typeset) with the
    changes from "Edit contents" applied. Page numbers are printed as the page shows them (1, 2... or
    i, ii...); a number typed in "Edit contents" replaces the automatic one."""

    folio = None                                       # number pictures, when the page numbers are pictures

    def __init__(self, edits=None, **kw):
        TableOfContents.__init__(self, **kw)
        self.edits = edits or []

    def addEntry(self, level, text, page, key=None, uid=None):
        self._entries.append((level, text, page, key, uid))

    def final_entries(self):
        auto = [{"uid": u, "level": lv, "text": tx, "page": str(pg), "key": k}
                for lv, tx, pg, k, u in self._lastEntries]
        out = apply_contents_edits(auto, self.edits)
        for e in out:
            if e.get("markup"):                          # formatted in Specific Text Edit
                e["text"] = self.markup(self.fix(e["markup"]))
            elif e.get("custom") or e.get("edited"):     # typed in "Edit contents": plain text
                e["text"] = self.markup(esc(e["text"]))
        return out

    pages = 1                                          # pages the contents took in the last pass

    def beforeBuild(self):
        TableOfContents.beforeBuild(self)
        self.pages = 1

    def split(self, availWidth, availHeight):
        parts = TableOfContents.split(self, availWidth, availHeight)
        if len(parts) > 1:
            self.pages += 1
        return parts

    markup = staticmethod(lambda m: m)                 # replaced by the font-coverage helper in build_pdf
    fix = staticmethod(lambda m: m)                    # replaced by build_pdf's font-name helper

    def wrap(self, availWidth, availHeight):
        entries = self.final_entries()
        if not self._lastEntries and not entries:
            entries = [{"level": 0, "text": "Contents", "page": "", "key": None}]

        def drawTOCEntryEnd(canvas, kind, label):
            e = entries[int(label)]
            if not e.get("page"):
                return
            style = self.getLevelStyle(e["level"])
            dot = " . " if (self.dotsMinLevel >= 0 and e["level"] >= self.dotsMinLevel) else ""
            f = self.folio
            if f is not None and f.pictures and not e.get("typed_page") and str(e["page"]).isdigit() and \
                    bf_folio.draw_contents_number(f, canvas, style, int(e["page"]), availWidth, dot, e.get("key")):
                return                                   # the page's number pictures, as on the page itself
            drawPageNumbers(canvas, style, [(e["page"], e.get("key"))], availWidth, availHeight, dot)
        self.canv.setNamedCB("drawTOCEntryEnd", drawTOCEntryEnd)
        data = []
        for i, e in enumerate(entries):
            style = self.getLevelStyle(e["level"])
            text = e["text"]
            if e.get("key"):
                text = '<a href="#%s">%s</a>' % (e["key"], text)
            try:
                para = Paragraph('%s<onDraw name="drawTOCEntryEnd" label="%d"/>' % (text, i), style)
            except Exception:
                para = Paragraph('%s<onDraw name="drawTOCEntryEnd" label="%d"/>' % (esc(plain(text)), i), style)
            if style.spaceBefore:
                data.append([Spacer(1, style.spaceBefore)])
            if e.get("space"):                           # space above this entry (Specific Text Edit)
                data.append([Spacer(1, float(e["space"]))])
            data.append([para])
        if not data:
            data = [[Spacer(1, 1)]]
        self._table = Table(data, colWidths=(availWidth,), style=self.tableStyle)
        self.width, self.height = self._table.wrapOn(self.canv, availWidth, availHeight)
        return self.width, self.height


TOC_SPACING = ["Automatic (avoid a nearly empty last page)", "Normal", "Compact"]


def contents_styles(R, B, size, variant):
    """Paragraph and table styles of the contents page. variant 0 = normal; higher = tighter (less space
    between entries first, then slightly smaller type - never below 8 pt)."""
    fs = size * (0.92 if variant < 4 else 0.85)
    leading = {0: size * 1.45, 1: size * 1.45, 2: size * 1.3, 3: size * 1.2, 4: fs * 1.2}[variant]
    gap = 1 if variant == 0 else 0
    ts0 = ParagraphStyle("toc0", fontName=R, fontSize=fs, leading=leading,
                         leftIndent=0, firstLineIndent=0, spaceBefore=gap, rightIndent=0.45 * inch)
    tsP = ParagraphStyle("tocP", parent=ts0, fontName=B, spaceBefore=8 if variant == 0 else 5)
    ts1 = ParagraphStyle("toc1", parent=ts0, leftIndent=0.3 * inch)
    table = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), gap),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), gap)])
    return ts0, tsP, ts1, table, fs


def contents_styles_sized(R, B, fs, leading, gap, part_gap):
    """Contents styles with the given type size, line spacing, space between entries and space above part
    entries (used by "Fit contents on one page"; the same structure as contents_styles)."""
    ts0 = ParagraphStyle("toc0", fontName=R, fontSize=fs, leading=leading,
                         leftIndent=0, firstLineIndent=0, spaceBefore=gap, rightIndent=0.45 * inch)
    tsP = ParagraphStyle("tocP", parent=ts0, fontName=B, spaceBefore=part_gap)
    ts1 = ParagraphStyle("toc1", parent=ts0, leftIndent=0.3 * inch)
    table = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), gap),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), gap)])
    return ts0, tsP, ts1, table, fs


def contents_height(entries, styles, has_parts, width):
    """The height of the contents list (without its heading) laid out exactly as the contents page draws it
    (BookTOC.wrap): the same paragraphs, styles, space above entries and table."""
    ts0, tsP, ts1, table_style, _fs = styles
    data = []
    for e in entries:
        st = ts1 if e["level"] >= 1 else (tsP if has_parts else ts0)
        try:
            para = Paragraph(e["text"], st)
        except Exception:
            para = Paragraph(esc(plain(e["text"])), st)
        if st.spaceBefore:
            data.append([Spacer(1, st.spaceBefore)])
        if e.get("space"):
            data.append([Spacer(1, float(e["space"]))])
        data.append([para])
    if not data:
        return 0.0
    tbl = Table(data, colWidths=(width,), style=table_style)
    return tbl.wrap(width, 1e9)[1]


# "Fit contents on one page": how far the contents page may be tightened before it counts as not fitting.
TOC_FIT_MIN_SIZE = 8.0            # pt, never smaller than this ...
TOC_FIT_MIN_SCALE = 0.7           # ... nor than this x the body text size
TOC_FIT_MIN_LEADING = 1.15        # line spacing (x the contents type size): lines never touch
TOC_FIT_TITLE_GAP = 6.0           # pt below the contents heading at the most (normally 20)


def fit_contents(entries, R, B, size, variant, has_parts, width, room, title_gap):
    """"Fit contents on one page": the least change to the contents page's look that puts every entry on one
    page. room = the height below the contents heading on its page; title_gap = the space under the heading;
    variant = the look the contents have without the option (Normal, Compact, or what Automatic chose).
    Tried in this order, the first that fits is used:
      0. that look (contents_styles(variant)): nothing changes if it already fits;
      1. less space between entries (and above part entries);
      2. tighter line spacing, down to 1.15 x the type size;
      3. smaller type, in 0.25 pt steps, down to max(8 pt, 0.7 x the body text size);
      4. less space under the contents heading (20 -> 6 pt), with the largest type that then fits.
    Entries are never left out, cut or overlapped (the same table as the contents page; titles wrap) and the
    body text, chapter titles and margins are not touched. Returns a dict: fits, styles (None when it doesn't
    fit), title_gap, step (0-4), size, leading, room, need (the height at the most compact readable look)."""
    base = contents_styles(R, B, size, variant)
    h0 = contents_height(entries, base, has_parts, width)
    out = {"fits": True, "styles": base, "title_gap": title_gap, "step": 0, "size": base[0].fontSize,
           "leading": base[0].leading, "room": room, "need": h0, "normal": h0}
    if h0 <= room - 0.5:
        return out
    fs0, lead0 = base[0].fontSize, base[0].leading
    part0 = base[1].spaceBefore
    floor = max(TOC_FIT_MIN_SIZE, TOC_FIT_MIN_SCALE * size)
    cands = []                                         # (step, fs, leading, gap, part_gap) in order
    for pg in sorted({min(part0, 4.0), 2.0}, reverse=True):
        cands.append((1, fs0, lead0, 0, pg))
    lead = lead0
    while lead * 0.95 >= fs0 * TOC_FIT_MIN_LEADING:
        lead *= 0.95
        cands.append((2, fs0, lead, 0, 2.0))
    cands.append((2, fs0, fs0 * TOC_FIT_MIN_LEADING, 0, 2.0))
    fs = fs0
    while fs - 0.25 >= floor - 1e-6:
        fs -= 0.25
        cands.append((3, fs, fs * TOC_FIT_MIN_LEADING, 0, 2.0))
    if floor < fs0 and abs(fs - floor) > 1e-6:
        cands.append((3, floor, floor * TOC_FIT_MIN_LEADING, 0, 2.0))
    for gap_now, extra, step4 in ((title_gap, 0.0, False), (min(title_gap, TOC_FIT_TITLE_GAP),
                                                          title_gap - min(title_gap, TOC_FIT_TITLE_GAP), True)):
        if step4 and extra <= 0:
            continue
        # (the heights only grow with the type size, so the largest size that fits is found by halving)
        ok = lambda c: contents_height(entries, contents_styles_sized(R, B, c[1], c[2], c[3], c[4]),  # noqa
                                       has_parts, width) <= room + extra - 0.5
        lo, hi = 0, len(cands) - 1
        if not ok(cands[hi]):
            last = cands[hi]
            out.update(need=contents_height(entries, contents_styles_sized(R, B, *last[1:]), has_parts, width))
            continue
        while lo < hi:                                 # the first (least changed) candidate that fits
            mid = (lo + hi) // 2
            if ok(cands[mid]):
                hi = mid
            else:
                lo = mid + 1
        step, fs, lead, gap, pg = cands[lo]
        out.update(fits=True, styles=contents_styles_sized(R, B, fs, lead, gap, pg), title_gap=gap_now,
                   step=4 if step4 else step, size=fs, leading=lead)
        return out
    out.update(fits=False, styles=None, floor=min(floor, fs0))
    return out


def contents_fit_note(fit, ahead=False):
    """What "Fit contents on one page" did, in words (the log, the printing notes and the preview; ahead=True:
    what it will do, for the Front & back step)."""
    if fit.get("fits"):
        bits = []
        if fit["step"] >= 1:
            bits.append("less space between entries")
        if fit["step"] >= 2:
            bits.append(f"line spacing {fit['leading']:.3g} pt")
        if fit["step"] >= 3:
            bits.append(f"type {fit['size']:.3g} pt")
        if fit["step"] >= 4:
            bits.append("less space under the heading")
        return ", ".join(bits) or "it fits as it is"
    pages = fit.get("pages")
    return ("Fit contents on one page: the contents list is too long for one page. Even at its most compact "
            f"readable look (tighter spacing, type down to "
            f"{fit.get('floor', TOC_FIT_MIN_SIZE):.3g} pt) it would need about "
            f"{fit['need'] / max(1.0, fit['room']):.1f} pages, so it "
            + ("will keep" if ahead else "keeps") + " its normal look over "
            + (f"{pages} pages" if pages else "more than one page") + ", as without this option (nothing is "
            "left out). To get it onto one page: shorten long chapter titles, hide entries you don't need there "
            "(Edit contents), or choose a bigger book page or smaller margins. Or untick \u201cFit contents on "
            "one page\u201d if more contents pages are fine.")


def contents_fit_estimate(book, s, log=lambda m: None):
    """Whether the contents would fit on one page, worked out the way build_pdf does it but without typesetting
    the book (for the Front & back step, before a preview): None when there is no contents page, else a dict
    like fit_contents' plus "pages" (how many pages the contents take with the option off) and "asked"."""
    if book is None or not s.get("toc") or getattr(book, "fixed_pdf", ""):
        return None
    pw, ph = page_size_inches(s)
    fw = (pw - float(s["margin_inner"]) - float(s["margin_outer"])) * inch
    fh = (ph - float(s["margin_top"]) - float(s["margin_bottom"])) * inch
    if fw < 1.5 * inch or fh < 2 * inch:
        return None
    (R, B, _i, _bi), (HR, HB, _hi, _hbi), _d = font_roles(s, log)
    HT = HB if s.get("heading_bold", True) else HR
    size, ts = float(s["body_size"]), float(s["title_size"])
    title = Paragraph(esc(s["toc_title"]), ParagraphStyle("toct", fontName=HT, fontSize=ts, leading=ts * 1.3))
    gap = 20.0
    room = fh - title.wrap(fw, fh)[1] - gap
    cov = Coverage(R)

    def fonts(m):                                      # editor fonts by name -> fonts the PDF can use
        return re.sub(r'<font face="([^"]+)"', lambda x: '<font face="%s"' % (
            html.unescape(x.group(1)) if html.unescape(x.group(1)) in pdfmetrics.getRegisteredFontNames() else R), m)
    shown = [dict(e, text=fonts(e["markup"]) if e.get("markup") else esc(e["text"]))
             for e in apply_contents_edits(contents_entries(book, s), book.toc)]
    if not shown:
        return None
    has_parts = any(c.level == 0 for c in book.active())
    spacing = s.get("toc_spacing", TOC_SPACING[0])
    variant = 2 if spacing == "Compact" else 0
    if spacing.startswith("Automatic") and len(shown) > 1:          # (the look without the option)
        v, _base = automatic_contents_variant(shown, R, B, size, has_parts, fw, room, fh)
        variant = variant if v is None else v
    fit = fit_contents([dict(e, text=cov.apply(e["text"])) for e in shown], R, B, size, variant, has_parts, fw,
                       room, gap)
    fit["pages"] = len(contents_pages(shown, contents_styles(R, B, size, variant), has_parts, fw, room, fh))
    fit["asked"] = bool(s.get("toc_one_page"))
    fit["styles"] = None
    return fit


def automatic_contents_variant(entries, R, B, size, has_parts, width, first_h, h):
    """"Contents spacing: Automatic": the tighter look (contents_styles variant 1-4, type never below 8 pt) that
    keeps the last few entries from sitting alone on a page, or None for the normal look; and the entries per
    page with the normal look."""
    base = contents_pages(entries, contents_styles(R, B, size, 0), has_parts, width, first_h, h)
    cap = max(base)
    if len(base) > 1 and base[-1] <= max(3, -(-cap // 4)):
        for v in (1, 2, 3, 4):
            sty = contents_styles(R, B, size, v)
            if sty[4] < 8:
                break
            if len(contents_pages(entries, sty, has_parts, width, first_h, h)) < len(base):
                return v, base
    return None, base


def contents_pages(entries, styles, has_parts, width, first_h, h):
    """How the contents table splits over pages: [entries on page 1, entries on page 2, ...]."""
    ts0, tsP, ts1, table_style, _fs = styles
    data, rows_entry = [], []
    for e in entries:
        st = ts1 if e["level"] >= 1 else (tsP if has_parts else ts0)
        if st.spaceBefore:
            data.append([Spacer(1, st.spaceBefore)])
            rows_entry.append(False)
        if e.get("space"):
            data.append([Spacer(1, float(e["space"]))])
            rows_entry.append(False)
        data.append([Paragraph(e["text"] + " 000", st)])
        rows_entry.append(True)
    if not data:
        return [0]
    tbl = Table(data, colWidths=(width,), style=table_style)
    counts, avail, start = [], first_h, 0
    for _ in range(500):
        _w, ht = tbl.wrap(width, avail)
        n_rows = len(tbl._cellvalues)
        if ht <= avail + 0.1:
            counts.append(sum(rows_entry[start:start + n_rows]))
            break
        parts = tbl.split(width, avail)
        if len(parts) < 2:
            counts.append(sum(rows_entry[start:start + n_rows]))
            break
        k = len(parts[0]._cellvalues)
        counts.append(sum(rows_entry[start:start + k]))
        start += k
        tbl, avail = parts[1], h
    return counts


def build_pdf(book, s, out_path, log=print):
    pw, ph = page_size_inches(s)
    W, H = pw * inch, ph * inch
    mt, mb = float(s["margin_top"]) * inch, float(s["margin_bottom"]) * inch
    mi, mo = float(s["margin_inner"]) * inch, float(s["margin_outer"]) * inch
    fw, fh = W - mi - mo, H - mt - mb
    if fw < 1.5 * inch or fh < 2 * inch:
        raise ValueError(f"Margins are too large for this book page size: they leave {max(0.0, fw) / inch:.2f} \u00d7 "
                         f"{max(0.0, fh) / inch:.2f} inches for the text, and at least 1.5 \u00d7 2 inches is needed. "
                         "Make the margins smaller (Layout step).")
    (R, B, I, BI), (HR, HB, HI, HBI), (DR, _db, _di, _dbi) = font_roles(s, log)
    HT = HB if s.get("heading_bold", True) else HR      # font for titles and headings
    hyph = make_hyphenator(s)
    hy = {"hyphenationLang": hyph, "embeddedHyphenation": 0, "uriWasteReduce": 0.3,
          "hyphenationMinWordLength": int(s.get("hyph_min") or 6)} if hyph else {}
    size = float(s["body_size"])
    lead = size * float(s["line_spacing"])
    ts, ss = float(s["title_size"]), float(s["sub_size"])
    align = TA_JUSTIFY if s["align"] == "Justified" else TA_LEFT
    tl = title_layout(s)
    cha, pta, tpa = tl["ch_align"], tl["part_align"], tl["tp_align"]

    st = {}
    st["body"] = ParagraphStyle("body", fontName=R, fontSize=size, leading=lead, alignment=align,
                                firstLineIndent=float(s["indent"]) * inch,
                                spaceAfter=float(s["para_space"]), allowWidows=0, allowOrphans=0,
                                textColor=black, **hy)
    st["flush"] = ParagraphStyle("flush", parent=st["body"], firstLineIndent=0)
    if s["verse_style"] == "Centered italic":
        st["verse"] = ParagraphStyle("verse", parent=st["body"], fontName=I, alignment=TA_CENTER,
                                     firstLineIndent=0, spaceBefore=6, spaceAfter=10)
    else:
        st["verse"] = ParagraphStyle("verse", parent=st["body"], alignment=TA_LEFT,
                                     firstLineIndent=0, leftIndent=0.5 * inch,
                                     spaceBefore=6, spaceAfter=10)
    st["quote"] = ParagraphStyle("quote", parent=st["body"], fontSize=size * 0.94,
                                 leading=lead * 0.94, firstLineIndent=0, leftIndent=0.4 * inch,
                                 rightIndent=0.4 * inch)
    st["item"] = ParagraphStyle("item", parent=st["body"], firstLineIndent=0, spaceAfter=max(2.0, float(
        s["para_space"]) * 0.5))
    st["anote"] = ParagraphStyle("anote", parent=st["body"], fontSize=size * 0.88, leading=lead * 0.88,
                                 firstLineIndent=0, leftIndent=0.35 * inch, rightIndent=0.35 * inch,
                                 spaceAfter=3, alignment=TA_LEFT)
    st["anlabel"] = ParagraphStyle("anlabel", fontName=HT, fontSize=size * 0.82, leading=size * 1.1,
                                   leftIndent=0.35 * inch, spaceBefore=8, spaceAfter=2, keepWithNext=1)
    st["meta"] = ParagraphStyle("meta", fontName=R, fontSize=size * 0.9, leading=lead * 0.9,
                                alignment=TA_LEFT, spaceAfter=4, leftIndent=0.25 * inch,
                                firstLineIndent=-0.25 * inch)
    st["sub"] = ParagraphStyle("sub", fontName=HT, fontSize=ss, leading=ss * 1.25,
                               alignment=TA_CENTER, spaceBefore=12, spaceAfter=8, keepWithNext=1)
    # Generated titles and headings (their alignment and position come from the Layout tab's "Titles" settings;
    # headings inside the text keep their own alignment from Specific Text Edit).
    st["gsub"] = ParagraphStyle("gsub", parent=st["sub"], alignment=cha)      # Contents, Work info, Notes...
    st["label"] = ParagraphStyle("label", fontName=HR, fontSize=ss, leading=ss * 1.3,
                                 alignment=cha, spaceAfter=4, keepWithNext=1)
    st["plabel"] = ParagraphStyle("plabel", parent=st["label"], alignment=pta)
    st["ctitle"] = ParagraphStyle("ctitle", fontName=HT, fontSize=ts, leading=ts * 1.25,
                                  alignment=cha, spaceBefore=6, spaceAfter=16, keepWithNext=1)
    st["csub"] = ParagraphStyle("csub", fontName=I, fontSize=size, leading=lead, alignment=cha,
                                leftIndent=0 if cha == TA_LEFT else 0.3 * inch,
                                rightIndent=0 if cha == TA_RIGHT else 0.3 * inch, spaceBefore=0,
                                spaceAfter=18, keepWithNext=1)
    ps = tl["part_size"] or ts * 1.2
    st["part"] = ParagraphStyle("part", fontName=HT, fontSize=ps, leading=ps * 1.25,
                                alignment=pta)
    st["scene"] = ParagraphStyle("scene", fontName=R, fontSize=size, leading=lead,
                                 alignment=TA_CENTER, spaceBefore=6, spaceAfter=12)
    bt = tl["tp_title_size"] or max(30.0, ts * 1.5)
    st["btitle"] = ParagraphStyle("btitle", fontName=HT, fontSize=bt, leading=bt * 1.2,
                                  alignment=tpa)
    st["bsub"] = ParagraphStyle("bsub", fontName=HI if HI != HR else I, fontSize=ss + 1, leading=(ss + 1) * 1.35,
                                alignment=tpa, spaceBefore=14)
    st["bauth"] = ParagraphStyle("bauth", fontName=R, fontSize=ss, leading=ss * 1.4,
                                 alignment=tpa, spaceBefore=36)
    st["bcred"] = ParagraphStyle("bcred", fontName=R, fontSize=size * 0.9, leading=size * 1.3,
                                 alignment=tpa, spaceBefore=12)
    st["plate"] = ParagraphStyle("plate", fontName=I, fontSize=ss + 0.5, leading=(ss + 0.5) * 1.3,
                                 alignment=TA_CENTER)
    st["head"] = ParagraphStyle("head", fontName=I, fontSize=max(8.5, size * 0.75),
                                leading=max(8.5, size * 0.75) * 1.2, alignment=TA_CENTER)
    st["ded"] = ParagraphStyle("ded", fontName=I, fontSize=size, leading=lead, alignment=TA_CENTER)
    st["toct"] = ParagraphStyle("toct", fontName=HT, fontSize=ts, leading=ts * 1.3,
                                alignment=cha, spaceAfter=20)

    covs = {}

    def cov_for(fontname):
        if fontname not in covs:
            covs[fontname] = Coverage(fontname)
        return covs[fontname]
    cov = cov_for(R)
    runts = bool(s.get("avoid_runts", True))
    body_styles = ("body", "flush", "quote", "item", "anote")

    inline_fonts = {}
    fmt_now = [None]                      # the block being typeset (its editor formatting)
    styled = {}

    def fix_fonts(markup):
        """Fonts chosen in the editor are stored by name ("EB Garamond"); turn them into PDF fonts."""
        if '<font face="' not in markup:
            return markup

        def rep(m):
            fam = html.unescape(m.group(1))
            if fam not in inline_fonts:
                if fam in pdfmetrics.getRegisteredFontNames():
                    inline_fonts[fam] = fam
                else:
                    try:
                        inline_fonts[fam] = resolve(fam, s, log)[0]
                    except Exception:
                        inline_fonts[fam] = R
            return f'<font face="{inline_fonts[fam]}"'
        return re.sub(r'<font face="([^"]+)"', rep, markup)

    def with_format(style):
        b = fmt_now[0]
        if b is None or not (b.align or b.indent or b.space):
            return style
        key = (style.name, b.align, b.indent, b.space)
        if key not in styled:
            al = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
            kw = {}
            if b.align in al:
                kw["alignment"] = al[b.align]
            if b.indent:
                kw["leftIndent"] = style.leftIndent + 0.25 * inch * max(0, min(int(b.indent), 8))
            if b.space:
                kw["spaceBefore"] = style.spaceBefore + max(0, min(int(b.space), 72))
            styled[key] = ParagraphStyle(f"{style.name}_f{len(styled)}", parent=style, **kw)
        return styled[key]

    def P(markup, style, **kw):
        markup = fix_fonts(markup)
        style = with_format(style)
        if '%"' in markup:          # sizes kept from the source are relative to the paragraph's own size
            markup = re.sub(r'(<font\b[^>]*\bsize=")([\d.]+)%"',
                            lambda m: f'{m.group(1)}{style.fontSize * float(m.group(2)) / 100:.1f}"', markup)
        if 'size="' in markup and _bigger_text(markup, style.fontSize):
            # words set bigger than the paragraph (kept from the source, or chosen in the editor) get room
            key = (style.name, "auto")
            if key not in styled:
                styled[key] = ParagraphStyle(f"{style.name}_a", parent=style, autoLeading="max")
            style = styled[key]
        if runts and style.name.split("_f")[0] in body_styles and len(markup) > 60:
            markup = no_runt(markup)
        c = cov_for(style.fontName)
        try:
            return Paragraph(c.apply(markup), style, **kw)
        except Exception:
            return Paragraph(c.apply(esc(plain(markup))), style, **kw)

    def scene_mark(b):
        sb = s["scene_break"]
        if sb == "Blank space":
            return "&#160;"
        if sb == "Keep the source's own":
            return b.text or "*&#160;&#160;*&#160;&#160;*"
        return esc(sb)

    def item_style(depth):
        d = max(0, min(int(depth), 4))
        key = f"item{d}"
        if key not in st:
            st[key] = ParagraphStyle(key, parent=st["item"], leftIndent=(d + 1) * 0.3 * inch,
                                     bulletIndent=d * 0.3 * inch + 0.04 * inch, bulletFontName=R,
                                     bulletFontSize=size)
        return st[key]

    MATTER_STYLE = {"flush": "flush", "meta": "meta", "head": "sub", "subtitle": "csub", "quote": "quote",
                    "btitle": "btitle", "bsub": "bsub", "bauth": "bauth", "bcred": "bcred", "plate": "plate",
                    "endline": "scene", "tocentry": "flush"}

    def matter_flowables(blocks, base="body"):
        """The flowables for an edited front or back page: the chapter styles plus the title-page and
        front-page ones, with the alignment, indent and space set in Specific Text Edit."""
        out, prev_label = [], None
        for b in blocks:
            fmt_now[0] = b
            k = b.kind
            if k != "anote":
                prev_label = None
            if k == "image":
                if b.image:
                    try:
                        out.extend(picture_flowables(b, fw, fh))
                    except Exception:
                        log(f"A picture ({b.image_name or 'unnamed'}) couldn't be used and was left out.")
            elif k == "verse":
                out.append(P("<br/>".join(x if x else "&#160;" for x in b.lines), st["verse"]))
            elif k == "scene":
                out.append(P(scene_mark(b), st["scene"]))
            elif k == "item":
                out.append(P(b.text or "&#160;", item_style(b.depth), bulletText=b.bullet or None))
            elif k == "anote":
                if b.label and b.label != prev_label:
                    out.append(P(esc(b.label), st["anlabel"]))
                out.append(P(b.text, st["anote"]))
                prev_label = b.label
            elif k == "ded":
                out.append(P(b.text or "&#160;", st["ded"]))
                out.append(Gap(1, 8))
            elif plain(b.text or "").strip():
                out.append(P(b.text, st[MATTER_STYLE.get(k, base)]))
        fmt_now[0] = None
        return out

    def section(key):
        """(edited?, blocks) of a front/back page (bf_matter)."""
        if bf_matter.is_edited(book, key) and bf_matter.override(book, key) is not None:
            return True, bf_matter.section_blocks(book, s, key)
        return False, None

    story = []
    recto = s["chapter_start"] == "Right-hand page"
    # Pages left blank on purpose by the layout (the left-hand page before a right-hand start, the back of the
    # front cover picture): any other page with nothing printed on it is reported after typesetting.
    # (doc.bf["planned"]: page -> why; the printing notes list them apart from signature padding)
    def mark_planned(why):
        return lambda canv, doc: doc.bf.setdefault("planned", {}).__setitem__(canv.getPageNumber(), why)

    def verso_blank():
        return DocIf("doc.page % 2 == 0", [Marker(mark_planned("verso")), PageBreak()])

    def new_page():
        story.append(PageBreak())
        if recto:
            story.append(verso_blank())

    # ---- Blank pages before the book ("Blank pages at beginning"): real pages of the book, before
    # everything else, with nothing printed on them (no number, no running head). Signature padding and
    # flyleafs are added later by the imposition and are separate from these.
    n_front, n_back = blank_pages(s, "start"), blank_pages(s, "end")
    mark_blank = lambda canv, doc: doc.bf["userblank"].__setitem__(canv.getPageNumber(), True)   # noqa: E731
    for _ in range(n_front):
        story.append(Marker(mark_blank))
        story.append(PageBreak())

    # ---- Front cover picture as the first page (optional)
    started_art = False
    if s.get("cover_art_in_book"):
        from bf_pictures import cover_art
        try:
            art = cover_art(book, s, "front")
        except ValueError as e:
            art = None
            log(f"Front cover picture: {e}.")
        if art:
            try:
                story.append(PagePicture(art, full=True))
                story.append(PageBreak())                  # the back of the picture stays blank
                started_art = True
            except Exception:
                log("The front cover picture couldn't be used inside the book.")

    def plate_lines():
        edited, pblocks = section("bookplate")
        return matter_flowables(pblocks) if edited else [P(esc(s["bookplate_text"]), st["plate"])]

    # ---- Title page
    if started_art:
        story.append(Marker(mark_planned("cover")))
        story.append(PageBreak())                      # the back of the cover picture stays blank
    if s["title_page"]:
        # The title block (title, subtitle, author, credit) shares one alignment and starts tp_pos % down the
        # text area (20 % = where it always was); it is never pushed so low that it spills onto another page.
        edited, tblocks = section("title")
        if edited:                                     # edited in Specific Text Edit (words = Book info)
            block = matter_flowables(tblocks) or [Spacer(1, 1)]
        else:
            block = [P(esc(book.title), st["btitle"])]
            if book.subtitle:
                block.append(P(esc(book.subtitle), st["bsub"]))
            if book.author:
                block.append(P(esc(book.author), st["bauth"]))
            if book.credit:
                block.append(P(esc(book.credit), st["bcred"]))
        plate = []
        if s["bookplate"] == "On title page":           # the bookplate stays centred under the title block
            plate = [Spacer(1, 0.9 * inch)] + plate_lines() + [Spacer(1, 0.35 * inch),
                                                              Rule(min(4.2 * inch, fw * 0.85), 0.8, 2)]
        top = fh * tl["tp_pos"] / 100
        room = fh - _block_height(block + plate, fw, fh) - 2
        story.append(Spacer(1, top if top <= room else max(0.0, room)))
        story.extend(block)
        if s.get("pn_hide_title"):
            story.append(Marker(lambda c, d: d.bf["nonum"].__setitem__(c.getPageNumber(), True)))
        story.extend(plate)
    started = bool(s["title_page"])
    if s["bookplate"] == "Separate page":
        if started:
            story.append(PageBreak())
        story.append(Spacer(1, fh * 0.35))
        story.extend(plate_lines())
        story.append(Spacer(1, 0.4 * inch))
        story.append(Rule(min(4.2 * inch, fw * 0.85), 0.8, 2))
        started = True
    ded_edited, ded_blocks = section("dedication")
    if bf_matter.has_text(ded_blocks) if ded_edited else (s.get("dedication") or "").strip():
        if started:
            new_page()
        story.append(Spacer(1, fh * 0.25))
        if ded_edited:
            story.extend(matter_flowables(ded_blocks))
        else:
            for para in re.split(r"\n\s*\n", s["dedication"].strip()):
                story.append(P(esc(para.strip()).replace("\n", "<br/>"), st["ded"]))
                story.append(Gap(1, 8))
        started = True

    def note_page():
        nonlocal started
        edited, nblocks = section("note")
        if edited:
            if not (s.get("note_title", "").strip() or bf_matter.has_text(nblocks)):
                return
        elif not (s.get("note_title") or s.get("note_text") or "").strip():
            return
        if started:
            new_page()
        if s.get("note_title", "").strip():
            story.append(Anchor("note", s["note_title"].strip(), 0))
            story.append(P(esc(s["note_title"].strip()), st["gsub"]))
            story.append(Rule(fw, 0.6, 3))
            story.append(Spacer(1, 8))
        if edited:
            story.extend(matter_flowables(nblocks))
        else:
            for para in re.split(r"\n\s*\n", (s.get("note_text") or "").strip()):
                if para.strip():
                    story.append(P(esc(" ".join(para.split())), st["body"]))
        started = True

    an_mode = s.get("an_mode", "Set apart (smaller, indented)")

    def fic_pages():
        nonlocal started
        wi_edited, wi_blocks = section("work_info")
        has_info = bf_matter.has_text(wi_blocks) if wi_edited else bool(book.fic_meta)
        if has_info and s.get("fic_info", "Leave out") != "Leave out":
            if started:
                new_page()
            story.append(Anchor("workinfo", "Work info", 0))
            head = bf_matter.section_heading(book, s, "work_info")
            if head:
                story.append(P(esc(head), st["gsub"]))
            story.append(Spacer(1, 8))
            if wi_edited:
                story.extend(matter_flowables(wi_blocks))
            else:
                for m in book.fic_meta:
                    story.append(P(m, st["meta"]))
            started = True
        groups = []
        for key, on in (("summary", s.get("fic_summary", "Add a summary page") != "Leave out"),
                        ("work_notes", not an_mode.startswith("Leave"))):
            edited, blocks = section(key)
            orig = book.fic_summary if key == "summary" else book.fic_notes
            if on and (bf_matter.has_text(blocks) if edited else orig):
                groups.append((key, edited, blocks if edited else orig))
        if groups:
            if started:
                new_page()
            story.append(Anchor("summary", "Summary" if groups[0][0] == "summary" else "Notes", 0))
            for key, edited, group in groups:
                head = bf_matter.section_heading(book, s, key)
                if head:
                    story.append(P(esc(head), st["gsub"]))
                story.append(Spacer(1, 6))
                if edited:
                    story.extend(matter_flowables(group, "flush"))
                else:
                    for b in group:
                        story.append(P(b.text, st["flush"]))
                story.append(Gap(1, 14))
            started = True

    fic_pages()
    if s.get("note_place") == "Before contents":
        note_page()

    chapters = book.active()
    has_parts = any(c.level == 0 for c in chapters)
    book._contents_fit = None                       # "Fit contents on one page": what was done (see below)
    folio = bf_folio.Folio(s, book)                 # page numbers: numerals / pictures (bf_folio)
    auto_toc = contents_entries(book, s)
    toc_by_uid = {e["uid"]: e for e in auto_toc}
    toc = None
    if s["toc"]:
        if started:
            new_page()
        story.append(Anchor("toc", "Contents", 0))
        title_p = P(esc(s["toc_title"]), st["toct"])
        story.append(title_p)
        # Spacing: normal, unless the last contents page would hold only a few entries - then tighten the
        # spacing (and at most make the type a little smaller) so they fit on the pages before.
        shown = [dict(e, text=fix_fonts(e["markup"]) if e.get("markup") else esc(e["text"]))
                 for e in apply_contents_edits(auto_toc, book.toc)]
        spacing = s.get("toc_spacing", TOC_SPACING[0])
        variant = 2 if spacing == "Compact" else 0
        tightened = None
        if spacing.startswith("Automatic") and len(shown) > 1:
            first_h = fh - title_p.wrap(fw, fh)[1] - st["toct"].spaceAfter
            v, base = automatic_contents_variant(shown, R, B, size, has_parts, fw, first_h, fh)
            if v is not None:
                variant = v
                tightened = (f"Contents: spacing tightened so the last {base[-1]} entr"
                             f"{'y doesn' if base[-1] == 1 else 'ies don'}'t sit alone on a page.")
        styles = None
        if s.get("toc_one_page") and shown:
            # "Fit contents on one page": starting from the look the contents would have without it (so a list
            # that already takes one page doesn't change), the least change that puts the whole list on one page
            # (fit_contents), measured with the same paragraphs the contents page draws. The height doesn't
            # depend on the page numbers (they sit in a column of their own), so the choice made here holds
            # through every typesetting pass. Not possible at a readable size: the normal contents (as with the
            # option off) and a warning.
            gap = st["toct"].spaceAfter
            room = fh - title_p.wrap(fw, fh)[1] - gap
            fit_entries = [dict(e, text=cov.apply(fix_fonts(e["markup"])) if e.get("markup")
                                else cov.apply(esc(e["text"]))) for e in shown]
            fit = fit_contents(fit_entries, R, B, size, variant, has_parts, fw, room, gap)
            book._contents_fit = dict(fit, styles=None, entries=len(shown))
            if fit["fits"] and fit["step"]:
                styles = fit["styles"]
                tightened = None
                if fit["title_gap"] != gap:
                    story.pop()
                    title_p = P(esc(s["toc_title"]), ParagraphStyle("toct1", parent=st["toct"],
                                                                     spaceAfter=fit["title_gap"]))
                    story.append(title_p)
                log(f"Contents: fitted on one page ({contents_fit_note(fit)}).")
        if tightened:
            log(tightened)
        if book._contents_fit is not None and not book._contents_fit["fits"]:
            # (printed as with the option off; how many pages that takes, for the warning)
            first_h = fh - title_p.wrap(fw, fh)[1] - st["toct"].spaceAfter
            book._contents_fit["pages"] = len(contents_pages(shown, contents_styles(R, B, size, variant),
                                                             has_parts, fw, first_h, fh))
            log("WARNING: " + contents_fit_note(book._contents_fit))
        ts0, tsP, ts1, toc_table, _fs = styles or contents_styles(R, B, size, variant)
        toc = BookTOC(edits=book.toc)
        toc.folio = folio
        toc.markup = cov.apply
        toc.fix = fix_fonts
        toc.levelStyles = [tsP if has_parts else ts0, ts1]
        toc.dotsMinLevel = 0 if s["toc_dots"] else 99
        toc.rightColumnWidth = 0.6 * inch
        toc.tableStyle = toc_table
        story.append(toc)
        started = True

    if s.get("note_place") != "Before contents":
        note_page()

    ft_edited, ft_blocks = section("front_text")
    if bf_matter.has_text(ft_blocks) if ft_edited else book.front_blocks:
        if started:
            new_page()
        if ft_edited:
            story.extend(matter_flowables(ft_blocks))
        else:
            for b in book.front_blocks:
                if b.kind == "para":
                    story.append(P(b.text, st["body"]))
        started = True

    # ---- Chapters
    chap_no = part_no = 0
    first = True
    cont = s["chapter_start"] == "Continuous"
    def settle(att, at):
        """AtTopAgain (story[at - 1]) adds the space above the first line that follows it (see AtTopAgain)."""
        for f in story[at:]:
            if isinstance(f, (CondPageBreak, Anchor, KeepTop, AtTopAgain)):
                continue
            att.extra = float(f.getSpaceBefore() or 0)
            break

    for ci, ch in enumerate(chapters):
        fmt_now[0] = None              # titles never take the formatting of the last paragraph before them
        top_space, top_at = None, 0
        if first:
            if started:
                new_page()
            elif recto and (n_front or started_art):
                # nothing before the first chapter but blank pages: it still opens on a right-hand page
                story.append(verso_blank())
        elif ch.level == 0 or not cont:
            if not (cont and story and isinstance(story[-1], PageBreak)):
                new_page()             # (in Continuous mode a part already ends with a page break: no empty page)
        else:
            gap = KeepTop(1, 28)
            top_space = AtTopAgain(gap)
            story.extend([gap, top_space])
            top_at = len(story)
            story.append(CondPageBreak(fh * 0.28))
        title = apply_case(ch.title, s["title_case"])
        if ch.level == 0:
            part_no += 1
            lbl = ch.label
            disp = f"{lbl} \u2014 {title}" if lbl and title else (title or lbl)
            ce = toc_by_uid[ch.uid]
            story.append(Anchor(f"ch{ci}", plain(disp), 0, toc_text=cov.apply(esc(ce["text"])),
                                toc_level=ce["level"], title=plain(title or lbl), opener=True, body_start=first,
                                uid=ch.uid))
            # the part's title block starts part_pos % down the text area (30 % = where it always was)
            head = ([P(esc(lbl), st["plabel"])] if lbl else []) + ([P(esc(title), st["part"])] if title else []) + \
                ([Rule(1.4 * inch, 0.8, 8, diamond=True, align=pta)] if s["ornament"] else [])
            top = fh * tl["part_pos"] / 100
            room = fh - _block_height(head, fw, fh) - 2
            story.append(Spacer(1, top if top <= room else max(0.0, room)))
            story.extend(head)
            first = False
            if not ch.blocks:
                if cont:
                    story.append(PageBreak())
                continue
            # The part's own text (an epigraph, an introduction...) is printed under its title.
            story.append(Spacer(1, 14))
            blocks = list(ch.blocks)
            fresh, cap_pending = True, False
        else:
            chap_no += 1
            lbl = ch.label
            if not lbl and s["chapter_label"] not in ("None", "") and not LABELISH.match(ch.title + " "):
                lbl = auto_label(s["chapter_label"], chap_no)
            ce = toc_by_uid[ch.uid]            # contents text: see contents_entries
            toc_text, lvl = ce["text"], ce["level"]
            if not (lbl or title) and ch.blocks and ch.blocks[0].kind == "image" and \
                    ch.blocks[0].img_place in ("page", "full"):
                # no title, and the chapter opens with a picture on a page of its own: the chapter starts on that
                # page (in Continuous mode its contents entry used to point at the page before)
                story.append(PageForPicture())
            anchor = Anchor(f"ch{ci}", plain(toc_text), lvl, toc_text=cov.apply(esc(toc_text)), toc_level=lvl,
                            title=plain(ch.title), opener=True, body_start=first, uid=ch.uid)
            if cont and (lbl or title):
                # Continuous: the title is kept with the chapter's first paragraph, and when they don't fit in
                # the rest of the page ReportLab moves them to the next page together. The chapter's contents
                # link (its page number, opening page and running head) goes with them; it used to stay
                # behind, so the contents gave the page before the one the chapter starts on.
                anchor.keepWithNext = 1
            story.append(anchor)
            first = False
            sink = None
            if tl["sink"] > 0 and not cont:          # "Drop chapter start down": the title block starts lower
                sink = KeepTop(1, tl["sink"] * inch)
                top_space = AtTopAgain(sink)
                story.extend([sink, top_space])
                top_at = len(story)
            if lbl:
                story.append(P(esc(lbl), st["label"]))
            if title:
                story.append(P(esc(title), st["ctitle"]))
            blocks = list(ch.blocks)
            while blocks and blocks[0].kind == "subtitle":
                story.append(P(blocks.pop(0).text, st["csub"]))
            if s["ornament"]:
                story.append(Rule(1.4 * inch, 0.8, 6, diamond=True, align=cha))
                story.append(Spacer(1, 10))
            fresh = True
            cap_pending = bool(s["drop_cap"])
            if sink is not None:
                # Never dropped so low that the title block and what the chapter starts with (two lines of text -
                # as many as a drop cap spans -, a heading and two lines, or its opening picture) can't follow on
                # the page, as for title and part pages. A bigger drop than the page has room for left a page with
                # nothing on it but the drop space (when not even the number line or the opening picture fitted
                # below it), or the number line alone at the bottom with the title on the next page. Where it
                # fits, the drop is exactly as set.
                head = story[top_at:]
                need = (head[0].getSpaceBefore() or 0) + _block_height(head, fw, fh) if head else 0.0
                b0 = blocks[0] if blocks else None
                opening = None
                if b0 is not None and b0.kind == "image" and b0.image and b0.img_place not in ("page", "full"):
                    try:
                        opening = _block_height(picture_flowables(b0, fw, fh)[:2], fw, fh)   # space + picture
                    except Exception:
                        opening = None
                if opening is None and b0 is not None and b0.kind == "head":     # a heading, kept with its text
                    hp = P(b0.text, st["sub"])
                    opening = (hp.getSpaceBefore() or 0) + _block_height([hp], fw, fh) + 2 * lead
                if opening is None:
                    lines = int(_num(s.get("drop_cap_lines"), 2, 2, 5)) if (cap_pending and b0 is not None and
                                                                              b0.kind == "para") else 2
                    opening = lines * lead
                sink.height = min(sink.height, max(0.0, fh - need - opening - 2))
        if top_space is not None:
            settle(top_space, top_at)
        prev_label, in_note = None, False
        for b in blocks:
            fmt_now[0] = b
            if b.kind != "anote" and in_note:
                in_note, prev_label = False, None
                if not an_mode.startswith("Keep"):
                    story.append(Gap(1, 8))
            if b.kind == "para":
                txt = b.text
                sty = st["flush"] if (fresh and not s["first_para_indent"]) else st["body"]
                m = DROP_RE.match(txt) if (cap_pending and txt) else None
                cap_pending = False
                qmode = s.get("drop_cap_quote", "Hang the quote in the margin")
                if m and m.group(2) and qmode.startswith("No drop cap"):
                    m = None
                if m:
                    quote = html.unescape(m.group(2))
                    rest = m.group(1) + txt[m.end():]
                    mode = "small" if qmode.startswith("Quote at text") else "big" if qmode.startswith(
                        "Make") else "hang"
                    try:
                        story.append(ImageAndFlowables(
                            DropLetter(m.group(3), DR, size, lead, int(s.get("drop_cap_lines") or 2),
                                       quote, mode, DR),
                            [P(rest, st["flush"])], imageSide="left", imageRightPadding=3,
                            imageBottomPadding=0, imageTopPadding=0, imageLeftPadding=0))
                    except Exception:
                        story.append(P(txt, sty))
                else:
                    story.append(P(txt, sty))
                fresh = False
            elif b.kind == "anote":
                if an_mode.startswith("Leave"):
                    continue
                keep = an_mode.startswith("Keep")
                if not in_note and not keep:
                    # a Gap, not a Spacer: when the page above is full (a picture on a page of its own, text
                    # ending at the bottom) a Spacer moved to the next page, and a long note kept with its label
                    # was then pushed past it, leaving that page empty
                    story.append(Gap(1, 4))
                if b.label and b.label != prev_label:
                    story.append(P(esc(b.label), st["flush"] if keep else st["anlabel"]))
                story.append(P(b.text, st["quote"] if keep else st["anote"]))
                prev_label, in_note = b.label, True
            elif b.kind == "item":
                d = max(0, min(int(b.depth), 4))
                key = f"item{d}"
                if key not in st:
                    st[key] = ParagraphStyle(key, parent=st["item"], leftIndent=(d + 1) * 0.3 * inch,
                                             bulletIndent=d * 0.3 * inch + 0.04 * inch, bulletFontName=R,
                                             bulletFontSize=size)
                story.append(P(b.text or "&#160;", st[key], bulletText=b.bullet or None))
                fresh = False
            elif b.kind == "quote":
                story.append(P(b.text, st["quote"]))
            elif b.kind == "subtitle":
                story.append(P(b.text, st["csub"]))
                fresh = True
            elif b.kind == "verse":
                story.append(P("<br/>".join(l if l else "&#160;" for l in b.lines), st["verse"]))
            elif b.kind == "head":
                story.append(P(b.text, st["sub"]))
                fresh = True
            elif b.kind == "scene":
                sb = s["scene_break"]
                if sb == "Blank space":
                    mark = "&#160;"
                elif sb == "Keep the source's own":
                    mark = b.text or "*&#160;&#160;*&#160;&#160;*"
                else:
                    mark = esc(sb)
                story.append(P(mark, st["scene"]))
                fresh = True
            elif b.kind == "image" and b.image:
                try:
                    story.extend(picture_flowables(b, fw, fh))
                except Exception:
                    log(f"A picture ({b.image_name or 'unnamed'}) couldn't be used and was left out.")
            elif b.kind in MATTER_STYLE or b.kind == "ded":      # a front-page style used in a chapter
                story.extend(matter_flowables([b]))
                fmt_now[0] = b
        if not ch.blocks:
            story.append(Gap(1, 1))
        if ch.level == 0 and cont:
            story.append(PageBreak())          # chapters after a part's text still start on a new page
    fmt_now[0] = None
    edited, eblocks = section("the_end")
    # THE END emptied in Specific Text Edit prints nothing, like the other formats (its 24 pt of space alone
    # could move to a page of its own after a chapter ending at the bottom of a page)
    if s["the_end"] and (bf_matter.has_text(eblocks) if edited else True):
        story.append(Spacer(1, 24))
        if edited:
            story.extend(matter_flowables(eblocks))
        else:
            story.append(P("THE END", st["scene"]))
    edited, xblocks = section("end_matter")          # end pages: afterword, notes... (only when written)
    xhead = bf_matter.section_heading(book, s, "end_matter")
    if edited and (bf_matter.has_text(xblocks) or xhead):
        story.append(PageBreak())
        story.append(Marker(lambda canv, doc, h=plain(xhead): doc.bf.__setitem__("cur", h)))
        if xhead:
            story.append(Anchor("endpages", plain(xhead), 0))
            story.append(P(esc(xhead), st["gsub"]))
            story.append(Spacer(1, 8))
        story.extend(matter_flowables(xblocks))
    nhead = bf_matter.section_heading(book, s, "notes_page")
    edited, nblocks = section("notes_page")
    for i in range(int(s.get("notes_pages") or 0)):
        story.append(PageBreak())
        # running heads on these pages say "Notes" (or the heading chosen), not the last chapter's title
        story.append(Marker(lambda canv, doc, h=plain(nhead) or "Notes": doc.bf.__setitem__("cur", h)))
        if nhead:
            story.append(P(esc(nhead), st["gsub"]))
        if i == 0 and edited:
            story.extend(matter_flowables(nblocks, "flush"))
        story.append(WriteLines(0.34 * inch))
    # ---- Blank pages after the book ("Blank pages at end")
    for _ in range(n_back):
        story.append(PageBreak())
        story.append(Marker(mark_blank))

    # ---- Page furniture
    def draw_number_pictures(canv, parts, pos, x, y, how, rule, dashes, nsize):
        """A page number drawn as pictures (bf_folio.Folio), kept inside the margin it sits in: digit pictures
        stand on the number text's baseline, whole-number pictures are centred where the text would be; made
        smaller (and said once) if they don't fit."""
        h0 = folio.auto_height(nsize)
        dash = R if dashes else None
        dw = pdfmetrics.stringWidth("\u2014  \u2014", R, nsize) if dashes else 0
        if pos == bf_folio.MIDDLE:
            h = folio.fit(parts, h0, max_w=max(1.0, mo - 4 - dw), max_h=fh)
            yb = mb + fh / 2 - h / 2
        else:
            if pos.startswith("Top"):
                lo, hi = H - mt + 2, H - mt * 0.1
            else:
                lo, hi = mb * 0.1, mb - 2 - (3 if rule else 0)
            h = folio.fit(parts, h0, max_w=max(1.0, fw - dw), max_h=max(1.0, hi - lo))
            yb = y if folio.mode == bf_folio.DIGIT_IMAGES else y + nsize * 0.35 - h / 2
            yb = min(max(yb, lo), hi - h)
        folio.draw(canv, parts, x, yb, h, how, dash, nsize, yb + h / 2 - nsize * 0.35)
        if rule:
            canv.setLineWidth(0.5)
            canv.line(x - 40, yb + h + 2, x + 40, yb + h + 2)

    def furniture(canv, doc):
        p = canv.getPageNumber()
        if doc.bf.get("fullpage", {}).get(p) or doc.bf["userblank"].get(p):
            return                              # a full-page picture or an added blank page: nothing on it
        blank = not doc.bf["content"].get(p)
        if blank and s["pn_hide_blank"]:
            return
        opener = doc.bf["opener"].get(p)
        odd = p % 2 == 1
        canv.saveState()
        label = doc.page_label(p)
        pos = s["pn_position"]
        show = label and pos != "None" and not doc.bf["nonum"].get(p) and \
            not (opener and s["pn_hide_openers"])
        nsize = max(9.0, size * 0.8)
        if show:
            # Where (bf_folio.anchor: the four positions of earlier versions exactly as before, plus top/bottom
            # left/right and the middle of the outside margin - left / right-hand = the page's place in the book)
            rule, dashes = s["pn_style"] == "Rule above", s["pn_style"] == "Dashes"
            x, y, how = bf_folio.anchor(pos, odd, W, H, mi, mo, mt, mb, fw, fh, nsize)
            centred = how == "center" and pos != bf_folio.MIDDLE      # top / bottom centre: italic, rule above
            v = doc.page_value(p)
            parts = folio.parts(v[0]) if folio.pictures and v and not v[1] else None
            if parts:
                draw_number_pictures(canv, parts, pos, x, y, how, centred and rule, dashes, nsize)
            else:
                txt = f"\u2014 {label} \u2014" if dashes else label
                canv.setFont(I if centred and rule else R, nsize)
                if how == "center":
                    canv.drawCentredString(x, y, txt)
                elif how == "right":
                    canv.drawRightString(x, y, txt)
                else:
                    canv.drawString(x, y, txt)
                if centred and rule:
                    canv.setLineWidth(0.5)
                    canv.line(x - 40, y + nsize + 2, x + 40, y + nsize + 2)
                if pos == bf_folio.MIDDLE and pdfmetrics.stringWidth(txt, R, nsize) > mo - 4:
                    folio.note_once("wide", "Page numbers: some numbers are wider than the outside margin, so they "
                                            "reach into the text or the page edge (make the outside margin bigger "
                                            "or choose another position).")
        bs = doc.bf.get("body_start")
        if s["running_heads"] and not opener and not blank and bs and p >= bs and \
                not doc.bf.get("plate", {}).get(p):
            head = book.title if not odd else (doc.bf.get("cur") or book.title)
            head = plain(head)
            if len(head) > 70:
                head = head[:67] + "..."
            hp = Paragraph(cov.apply(esc(head)), st["head"])
            hp.wrapOn(canv, fw, H)
            hp.drawOn(canv, mi if odd else mo, H - mt * 0.55 - st["head"].fontSize * 0.25)
        canv.restoreState()

    odd_f = Frame(mi, mb, fw, fh, 0, 0, 0, 0, id="odd")
    even_f = Frame(mo, mb, fw, fh, 0, 0, 0, 0, id="even")
    doc = BookDoc(out_path, s, book, pagesize=(W, H), leftMargin=mi, rightMargin=mo,
                  topMargin=mt, bottomMargin=mb, title=book.title, author=book.author,
                  creator="BookForge by ChunksBabyRuth")
    doc.folio = folio
    doc.addPageTemplates([
        PageTemplate("odd", [odd_f], onPageEnd=furniture, autoNextPageTemplate="even"),
        PageTemplate("even", [even_f], onPageEnd=furniture, autoNextPageTemplate="odd"),
    ])
    log("Typesetting pages (this can take a minute for long books)...")
    if toc is not None:
        doc.multiBuild(story, maxPasses=12)
    else:
        doc.build(story)
    used = sorted({f for c in covs.values() for f in c.choice.values() if f})
    missing = set().union(*[c.missing for c in covs.values()]) if covs else set()
    if used:
        log("Some characters aren't in the chosen font, so they were drawn with: " +
            ", ".join(sorted({u.split("_", 1)[1].rsplit("-", 1)[0] for u in used})))
    if missing:
        log(f"WARNING: {len(missing)} character(s) aren't in any installed font and may show as "
            "boxes: " + " ".join(sorted(missing))[:120])
    if hyph is not None:
        log(f"Hyphenation: {s.get('hyph_lang')}" + (" + your word list" if (s.get("hyph_words") or "").strip()
                                                    else ""))
    anchors = doc.bf.get("anchors", {})
    book._chapter_pages = [(id(ch), anchors.get(f"ch{ci}")) for ci, ch in enumerate(chapters)]
    book._toc_labels = dict(doc.bf.get("toc_labels", {}))      # chapter uid -> page number (for Edit contents)
    book._empty_pages = empty_pages(doc)
    book._folio_notes = folio.report()             # page-number pictures missing, Roman range, too big...
    for note in book._folio_notes:
        log("WARNING: " + note)
    # the pages left blank on purpose by the layout (not the "Blank pages at beginning/end" ones): page -> why
    book._planned_blanks = {p: why for p, why in sorted(doc.bf.get("planned", {}).items())
                            if not doc.bf["content"].get(p)}
    if book._empty_pages:
        log("WARNING: " + empty_pages_note(book._empty_pages))
    fitted = getattr(book, "_contents_fit", None)
    if fitted is not None and toc is not None:
        fitted["split"] = toc.pages > 1             # did the contents run onto a second page (last pass)?
        if fitted["fits"] and fitted["split"]:      # (measured to fit, so this should never happen)
            fitted["fits"] = False
            log("WARNING: " + contents_fit_note(fitted))
    if s.get("toc") and book.toc:
        # A number typed in "Edit contents" is always printed as typed - but say so when it isn't the page
        # the chapter really starts on, so a stale correction is noticed instead of silently printed.
        names = {e["uid"]: e["text"] for e in contents_entries(book, s)}
        for ed in book.toc:
            real = book._toc_labels.get(ed.get("uid"))
            typed = (ed.get("page") or "").strip()
            if typed and real and typed != real and ed.get("show", True):
                log(f"Contents: you typed page {typed} for \u201c{ed.get('title') or names.get(ed['uid'], '')}\u201d "
                    f"- it starts on page {real}. (Edit contents > Page number, empty = automatic.)")
    return doc.page
