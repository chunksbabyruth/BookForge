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
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus import TableStyle

from bf_core import page_size_inches, plain, esc

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
                 body_start=False):
        Marker.__init__(self, self._run)
        self.key, self.outline, self.olevel = key, outline, olevel
        self.toc_text, self.toc_level, self.title = toc_text, toc_level, title
        self.opener, self.body_start = opener, body_start

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
    def __init__(self, width, thickness=0.6, space=6, diamond=False):
        Flowable.__init__(self)
        self.w, self.t, self.space, self.diamond = width, thickness, space, diamond

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, self.space * 2

    def draw(self):
        c = self.canv
        x0 = (self.aw - self.w) / 2
        y = self.space
        c.setStrokeColor(black)
        c.setLineWidth(self.t)
        if self.diamond:
            g = 4
            c.line(x0, y, self.aw / 2 - g * 2, y)
            c.line(self.aw / 2 + g * 2, y, x0 + self.w, y)
            p = c.beginPath()
            p.moveTo(self.aw / 2, y + g)
            p.lineTo(self.aw / 2 + g, y)
            p.lineTo(self.aw / 2, y - g)
            p.lineTo(self.aw / 2 - g, y)
            p.close()
            c.setFillColor(black)
            c.drawPath(p, fill=1, stroke=0)
        else:
            c.line(x0, y, x0 + self.w, y)


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
    def __init__(self, filename, s, book, **kw):
        BaseDocTemplate.__init__(self, filename, **kw)
        self.s, self.book = s, book
        self.beforeDocument()

    def beforeDocument(self):
        # Reset every pass; the body start is only trusted once reached in THIS pass.
        self.bf = {"body_start": None, "opener": {}, "content": {}, "nonum": {}, "cur": ""}

    def page_label(self, p):
        mode = self.s.get("pn_mode", "")
        if mode.startswith("Every"):
            return str(p)
        bs = self.bf.get("body_start")
        if bs is None or p < bs:
            return roman(p).lower() if mode.startswith("Roman") else ""
        return str(p - bs + 1)

    def afterFlowable(self, f):
        if isinstance(f, Anchor):
            if f.toc_text is not None:
                lab = self.page_label(self.page)
                num = int(lab) if lab.isdigit() else 0
                self.notify("TOCEntry", (f.toc_level, f.toc_text, num, f.key))
            return
        if isinstance(f, (Paragraph, Image, TableOfContents, Rule, WriteLines, ImageAndFlowables)):
            self.bf["content"][self.page] = True


def build_pdf(book, s, out_path, log=print):
    pw, ph = page_size_inches(s)
    W, H = pw * inch, ph * inch
    mt, mb = float(s["margin_top"]) * inch, float(s["margin_bottom"]) * inch
    mi, mo = float(s["margin_inner"]) * inch, float(s["margin_outer"]) * inch
    fw, fh = W - mi - mo, H - mt - mb
    if fw < 1.5 * inch or fh < 2 * inch:
        raise ValueError("Margins are too large for this page size.")
    (R, B, I, BI), (HR, HB, HI, HBI), (DR, _db, _di, _dbi) = font_roles(s, log)
    HT = HB if s.get("heading_bold", True) else HR      # font for titles and headings
    hyph = make_hyphenator(s)
    hy = {"hyphenationLang": hyph, "embeddedHyphenation": 0, "uriWasteReduce": 0.3,
          "hyphenationMinWordLength": int(s.get("hyph_min") or 6)} if hyph else {}
    size = float(s["body_size"])
    lead = size * float(s["line_spacing"])
    ts, ss = float(s["title_size"]), float(s["sub_size"])
    align = TA_JUSTIFY if s["align"] == "Justified" else TA_LEFT

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
    st["label"] = ParagraphStyle("label", fontName=HR, fontSize=ss, leading=ss * 1.3,
                                 alignment=TA_CENTER, spaceAfter=4, keepWithNext=1)
    st["ctitle"] = ParagraphStyle("ctitle", fontName=HT, fontSize=ts, leading=ts * 1.25,
                                  alignment=TA_CENTER, spaceBefore=6, spaceAfter=16, keepWithNext=1)
    st["csub"] = ParagraphStyle("csub", fontName=I, fontSize=size, leading=lead, alignment=TA_CENTER,
                                leftIndent=0.3 * inch, rightIndent=0.3 * inch, spaceBefore=0,
                                spaceAfter=18, keepWithNext=1)
    st["part"] = ParagraphStyle("part", fontName=HT, fontSize=ts * 1.2, leading=ts * 1.5,
                                alignment=TA_CENTER)
    st["scene"] = ParagraphStyle("scene", fontName=R, fontSize=size, leading=lead,
                                 alignment=TA_CENTER, spaceBefore=6, spaceAfter=12)
    bt = max(30.0, ts * 1.5)
    st["btitle"] = ParagraphStyle("btitle", fontName=HT, fontSize=bt, leading=bt * 1.2,
                                  alignment=TA_CENTER)
    st["bsub"] = ParagraphStyle("bsub", fontName=HI if HI != HR else I, fontSize=ss + 1, leading=(ss + 1) * 1.35,
                                alignment=TA_CENTER, spaceBefore=14)
    st["bauth"] = ParagraphStyle("bauth", fontName=R, fontSize=ss, leading=ss * 1.4,
                                 alignment=TA_CENTER, spaceBefore=36)
    st["bcred"] = ParagraphStyle("bcred", fontName=R, fontSize=size * 0.9, leading=size * 1.3,
                                 alignment=TA_CENTER, spaceBefore=12)
    st["plate"] = ParagraphStyle("plate", fontName=I, fontSize=ss + 0.5, leading=(ss + 0.5) * 1.3,
                                 alignment=TA_CENTER)
    st["head"] = ParagraphStyle("head", fontName=I, fontSize=max(8.5, size * 0.75),
                                leading=max(8.5, size * 0.75) * 1.2, alignment=TA_CENTER)
    st["ded"] = ParagraphStyle("ded", fontName=I, fontSize=size, leading=lead, alignment=TA_CENTER)
    st["toct"] = ParagraphStyle("toct", fontName=HT, fontSize=ts, leading=ts * 1.3,
                                alignment=TA_CENTER, spaceAfter=20)
    ts0 = ParagraphStyle("toc0", fontName=R, fontSize=size * 0.92, leading=size * 1.45,
                         leftIndent=0, firstLineIndent=0, spaceBefore=1)
    tsP = ParagraphStyle("tocP", parent=ts0, fontName=B, spaceBefore=8)
    ts1 = ParagraphStyle("toc1", parent=ts0, leftIndent=0.3 * inch)

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
        if runts and style.name.split("_f")[0] in body_styles and len(markup) > 60:
            markup = no_runt(markup)
        c = cov_for(style.fontName)
        try:
            return Paragraph(c.apply(markup), style, **kw)
        except Exception:
            return Paragraph(c.apply(esc(plain(markup))), style, **kw)

    story = []
    recto = s["chapter_start"] == "Right-hand page"

    def new_page():
        story.append(PageBreak())
        if recto:
            story.append(DocIf("doc.page % 2 == 0", [PageBreak()]))

    # ---- Title page
    if s["title_page"]:
        story.append(Spacer(1, fh * 0.2))
        story.append(P(esc(book.title), st["btitle"]))
        if book.subtitle:
            story.append(P(esc(book.subtitle), st["bsub"]))
        if book.author:
            story.append(P(esc(book.author), st["bauth"]))
        if book.credit:
            story.append(P(esc(book.credit), st["bcred"]))
        if s.get("pn_hide_title"):
            story.append(Marker(lambda c, d: d.bf["nonum"].__setitem__(c.getPageNumber(), True)))
        if s["bookplate"] == "On title page":
            story.append(Spacer(1, 0.9 * inch))
            story.append(P(esc(s["bookplate_text"]), st["plate"]))
            story.append(Spacer(1, 0.35 * inch))
            story.append(Rule(min(4.2 * inch, fw * 0.85), 0.8, 2))
    started = bool(s["title_page"])
    if s["bookplate"] == "Separate page":
        if started:
            story.append(PageBreak())
        story.append(Spacer(1, fh * 0.35))
        story.append(P(esc(s["bookplate_text"]), st["plate"]))
        story.append(Spacer(1, 0.4 * inch))
        story.append(Rule(min(4.2 * inch, fw * 0.85), 0.8, 2))
        started = True
    if (s.get("dedication") or "").strip():
        if started:
            new_page()
        story.append(Spacer(1, fh * 0.25))
        for para in re.split(r"\n\s*\n", s["dedication"].strip()):
            story.append(P(esc(para.strip()).replace("\n", "<br/>"), st["ded"]))
            story.append(Spacer(1, 8))
        started = True

    def note_page():
        nonlocal started
        if not (s.get("note_title") or s.get("note_text") or "").strip():
            return
        if started:
            new_page()
        if s.get("note_title", "").strip():
            story.append(Anchor("note", s["note_title"].strip(), 0))
            story.append(P(esc(s["note_title"].strip()), st["sub"]))
            story.append(Rule(fw, 0.6, 3))
            story.append(Spacer(1, 8))
        for para in re.split(r"\n\s*\n", (s.get("note_text") or "").strip()):
            if para.strip():
                story.append(P(esc(" ".join(para.split())), st["body"]))
        started = True

    an_mode = s.get("an_mode", "Set apart (smaller, indented)")

    def fic_pages():
        nonlocal started
        if book.fic_meta and s.get("fic_info", "Leave out") != "Leave out":
            if started:
                new_page()
            story.append(Anchor("workinfo", "Work info", 0))
            story.append(P("Work Info", st["sub"]))
            story.append(Spacer(1, 8))
            for m in book.fic_meta:
                story.append(P(m, st["meta"]))
            started = True
        summ = book.fic_summary if s.get("fic_summary", "Add a summary page") != "Leave out" else []
        notes = book.fic_notes if not an_mode.startswith("Leave") else []
        if summ or notes:
            if started:
                new_page()
            story.append(Anchor("summary", "Summary" if summ else "Notes", 0))
            for group, default in ((summ, "Summary"), (notes, "Notes")):
                if not group:
                    continue
                story.append(P(esc(group[0].label or default), st["sub"]))
                story.append(Spacer(1, 6))
                for b in group:
                    story.append(P(b.text, st["flush"]))
                story.append(Spacer(1, 14))
            started = True

    fic_pages()
    if s.get("note_place") == "Before contents":
        note_page()

    chapters = book.active()
    has_parts = any(c.level == 0 for c in chapters)
    toc = None
    if s["toc"]:
        if started:
            new_page()
        story.append(Anchor("toc", "Contents", 0))
        story.append(P(esc(s["toc_title"]), st["toct"]))
        toc = TableOfContents()
        toc.levelStyles = [tsP if has_parts else ts0, ts1]
        toc.dotsMinLevel = 0 if s["toc_dots"] else 99
        toc.rightColumnWidth = 0.6 * inch
        toc.tableStyle = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 1),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
        story.append(toc)
        started = True

    if s.get("note_place") != "Before contents":
        note_page()

    if book.front_blocks:
        if started:
            new_page()
        for b in book.front_blocks:
            if b.kind == "para":
                story.append(P(b.text, st["body"]))
        started = True

    # ---- Chapters
    chap_no = part_no = 0
    seen_part = False
    first = True
    cont = s["chapter_start"] == "Continuous"
    for ci, ch in enumerate(chapters):
        if first:
            if started:
                new_page()
        elif ch.level == 0 or not cont:
            new_page()
        else:
            story.append(Spacer(1, 28))
            story.append(CondPageBreak(fh * 0.28))
        title = apply_case(ch.title, s["title_case"])
        if ch.level == 0:
            part_no += 1
            seen_part = True
            lbl = ch.label
            disp = f"{lbl} \u2014 {title}" if lbl and title else (title or lbl)
            story.append(Anchor(f"ch{ci}", plain(disp), 0, toc_text=cov.apply(esc(apply_case(disp, s["toc_case"]))),
                                toc_level=0, title=plain(title or lbl), opener=True, body_start=first))
            story.append(Spacer(1, fh * 0.3))
            if lbl:
                story.append(P(esc(lbl), st["label"]))
            if title:
                story.append(P(esc(title), st["part"]))
            if s["ornament"]:
                story.append(Rule(1.4 * inch, 0.8, 8, diamond=True))
            first = False
            if cont:
                story.append(PageBreak())
            continue
        chap_no += 1
        lbl = ch.label
        if not lbl and s["chapter_label"] not in ("None", "") and not LABELISH.match(ch.title + " "):
            lbl = auto_label(s["chapter_label"], chap_no)
        tn = s["toc_numbers"]
        tt = apply_case(ch.title, s["toc_case"])
        if ch.label:
            toc_text = f"{ch.label} \u2014 {tt}" if tt else ch.label
        elif tn == "Number (1.)":
            toc_text = f"{chap_no}. {tt}"
        elif tn == "Chapter N:":
            toc_text = f"Chapter {chap_no}: {tt}"
        else:
            toc_text = tt
        lvl = 1 if (has_parts and seen_part) else 0
        story.append(Anchor(f"ch{ci}", plain(toc_text), lvl, toc_text=cov.apply(esc(toc_text)), toc_level=lvl,
                            title=plain(ch.title), opener=True, body_start=first))
        first = False
        if float(s["chapter_sink"]) > 0 and not cont:
            story.append(Spacer(1, float(s["chapter_sink"]) * inch))
        if lbl:
            story.append(P(esc(lbl), st["label"]))
        if title:
            story.append(P(esc(title), st["ctitle"]))
        blocks = list(ch.blocks)
        while blocks and blocks[0].kind == "subtitle":
            story.append(P(blocks.pop(0).text, st["csub"]))
        if s["ornament"]:
            story.append(Rule(1.4 * inch, 0.8, 6, diamond=True))
            story.append(Spacer(1, 10))
        fresh = True
        cap_pending = bool(s["drop_cap"])
        prev_label, in_note = None, False
        for b in blocks:
            fmt_now[0] = b
            if b.kind != "anote" and in_note:
                in_note, prev_label = False, None
                if not an_mode.startswith("Keep"):
                    story.append(Spacer(1, 8))
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
                    story.append(Spacer(1, 4))
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
                    ir = ImageReader(io.BytesIO(b.image))
                    iw, ih = ir.getSize()
                    k = min(fw / iw, fh * 0.65 / ih, 1.5)
                    img = Image(io.BytesIO(b.image), width=iw * k, height=ih * k)
                    img.hAlign = "CENTER"
                    story.append(Spacer(1, 6))
                    story.append(img)
                    story.append(Spacer(1, 8))
                except Exception:
                    pass
        if not ch.blocks:
            story.append(Spacer(1, 1))
    if s["the_end"]:
        story.append(Spacer(1, 24))
        story.append(P("THE END", st["scene"]))
    for _ in range(int(s.get("notes_pages") or 0)):
        story.append(PageBreak())
        story.append(P("Notes", st["sub"]))
        story.append(WriteLines(0.34 * inch))

    # ---- Page furniture
    def furniture(canv, doc):
        p = canv.getPageNumber()
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
            txt = f"\u2014 {label} \u2014" if s["pn_style"] == "Dashes" else label
            if pos.startswith("Top"):
                y = H - mt * 0.55
            else:
                y = mb * 0.5
            if pos.endswith("center"):
                x = (mi if odd else mo) + fw / 2
                canv.setFont(I if s["pn_style"] == "Rule above" else R, nsize)
                canv.drawCentredString(x, y, txt)
                if s["pn_style"] == "Rule above":
                    canv.setLineWidth(0.5)
                    canv.line(x - 40, y + nsize + 2, x + 40, y + nsize + 2)
            else:
                canv.setFont(R, nsize)
                if odd:
                    canv.drawRightString(W - mo, y, txt)
                else:
                    canv.drawString(mo, y, txt)
        bs = doc.bf.get("body_start")
        if s["running_heads"] and not opener and not blank and bs and p >= bs:
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
    return doc.page
