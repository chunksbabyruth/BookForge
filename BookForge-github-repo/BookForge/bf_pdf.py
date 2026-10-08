"""BookForge PDF typesetter (reportlab)."""
import io
import os
import re
import html
import unicodedata

from reportlab.lib.colors import black, HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
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
BUILTIN = {
    "Times (built-in)": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "Helvetica (built-in)": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "Courier (built-in)": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
}
WIN_FAMILIES = {
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Palatino Linotype": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    "Book Antiqua": ("bkant.ttf", "antquab.ttf", "antquai.ttf", "antquabi.ttf"),
    "Garamond": ("gara.ttf", "garabd.ttf", "garait.ttf", ""),
    "Cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "Constantia": ("constan.ttf", "constanb.ttf", "constani.ttf", "constanz.ttf"),
    "Century Schoolbook": ("schlbk.ttf", "schlbkb.ttf", "schlbki.ttf", "schlbkbi.ttf"),
    "Bookman Old Style": ("bookos.ttf", "bookosb.ttf", "bookosi.ttf", "bookosbi.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Sitka Text": ("sitka.ttc", "sitkab.ttc", "sitkai.ttc", "sitkaz.ttc"),
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "Comic Sans MS": ("comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf"),
}
CUSTOM_LABEL = "Custom font file (.ttf)..."


def _font_index():
    dirs = []
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs.append(os.path.join(win, "Fonts"))
    la = os.environ.get("LOCALAPPDATA")
    if la:
        dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    if os.name != "nt":
        dirs += ["/usr/share/fonts", os.path.expanduser("~/.fonts")]
    idx = {}
    for d in dirs:
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


def available_fonts():
    idx = font_index()
    names = list(BUILTIN)
    for fam, files in WIN_FAMILIES.items():
        if files[0] in idx:
            names.append(fam)
    names.append(CUSTOM_LABEL)
    return names


def _ttf(name, path):
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    kw = {"subfontIndex": 0} if path.lower().endswith(".ttc") else {}
    pdfmetrics.registerFont(TTFont(name, path, **kw))
    return name


def register_fonts(s):
    """Return (regular, bold, italic, bolditalic) reportlab font names."""
    fam = s.get("font_family", "Times (built-in)")
    if fam in BUILTIN:
        return BUILTIN[fam]
    paths = [None, None, None, None]
    tag = "BF_" + re.sub(r"\W", "", fam)
    if fam == CUSTOM_LABEL:
        p = s.get("custom_font_path", "")
        if not p or not os.path.exists(p):
            return BUILTIN["Times (built-in)"]
        paths[0] = p
        d, b = os.path.split(p)
        stem, ext = os.path.splitext(b)
        for i, word in ((1, "Bold"), (2, "Italic"), (3, "BoldItalic")):
            for cand in (stem.replace("Regular", word), stem + "-" + word, stem + word):
                cp = os.path.join(d, cand + ext)
                if cand != stem and os.path.exists(cp):
                    paths[i] = cp
                    break
        tag = "BF_Custom_" + re.sub(r"\W", "", stem)
    else:
        idx = font_index()
        for i, f in enumerate(WIN_FAMILIES.get(fam, ())):
            if f and f in idx:
                paths[i] = idx[f]
        if not paths[0]:
            return BUILTIN["Times (built-in)"]
    try:
        r = _ttf(tag + "-R", paths[0])
        b = _ttf(tag + "-B", paths[1]) if paths[1] else r
        i = _ttf(tag + "-I", paths[2]) if paths[2] else r
        bi = _ttf(tag + "-BI", paths[3]) if paths[3] else (b if b != r else i)
        registerFontFamily(r, normal=r, bold=b, italic=i, boldItalic=bi)
        return r, b, i, bi
    except Exception:
        return BUILTIN["Times (built-in)"]


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
        self.builtin = regular in {v[0] for v in BUILTIN.values()}
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


class DropLetter(Flowable):
    """A big initial letter that spans two lines of text (used with ImageAndFlowables)."""

    def __init__(self, letter, font, body_size, lead):
        Flowable.__init__(self)
        from reportlab.pdfbase.pdfmetrics import stringWidth
        self.letter, self.font = letter, font
        cap = 0.7
        self.size = (lead + body_size * cap) / cap
        self.lead, self.body = lead, body_size
        self.width = stringWidth(letter, font, self.size)
        self.height = lead * 2 - (lead - body_size) * 0.5

    def wrap(self, aw, ah):
        return self.width, self.height

    def _restrictSize(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFont(self.font, self.size)
        c.setFillColor(black)
        base = self.height - self.body * 0.95 - self.lead
        c.drawString(0, base, self.letter)


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
    R, B, I, BI = register_fonts(s)
    size = float(s["body_size"])
    lead = size * float(s["line_spacing"])
    ts, ss = float(s["title_size"]), float(s["sub_size"])
    align = TA_JUSTIFY if s["align"] == "Justified" else TA_LEFT

    st = {}
    st["body"] = ParagraphStyle("body", fontName=R, fontSize=size, leading=lead, alignment=align,
                                firstLineIndent=float(s["indent"]) * inch,
                                spaceAfter=float(s["para_space"]), allowWidows=0, allowOrphans=0,
                                textColor=black)
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
    st["sub"] = ParagraphStyle("sub", fontName=B, fontSize=ss, leading=ss * 1.25,
                               alignment=TA_CENTER, spaceBefore=12, spaceAfter=8, keepWithNext=1)
    st["label"] = ParagraphStyle("label", fontName=R, fontSize=ss, leading=ss * 1.3,
                                 alignment=TA_CENTER, spaceAfter=4, keepWithNext=1)
    st["ctitle"] = ParagraphStyle("ctitle", fontName=B, fontSize=ts, leading=ts * 1.25,
                                  alignment=TA_CENTER, spaceBefore=6, spaceAfter=16, keepWithNext=1)
    st["csub"] = ParagraphStyle("csub", fontName=I, fontSize=size, leading=lead, alignment=TA_CENTER,
                                leftIndent=0.3 * inch, rightIndent=0.3 * inch, spaceBefore=0,
                                spaceAfter=18, keepWithNext=1)
    st["part"] = ParagraphStyle("part", fontName=B, fontSize=ts * 1.2, leading=ts * 1.5,
                                alignment=TA_CENTER)
    st["scene"] = ParagraphStyle("scene", fontName=R, fontSize=size, leading=lead,
                                 alignment=TA_CENTER, spaceBefore=6, spaceAfter=12)
    bt = max(30.0, ts * 1.5)
    st["btitle"] = ParagraphStyle("btitle", fontName=B, fontSize=bt, leading=bt * 1.2,
                                  alignment=TA_CENTER)
    st["bsub"] = ParagraphStyle("bsub", fontName=I, fontSize=ss + 1, leading=(ss + 1) * 1.35,
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
    st["toct"] = ParagraphStyle("toct", fontName=B, fontSize=ts, leading=ts * 1.3,
                                alignment=TA_CENTER, spaceAfter=20)
    ts0 = ParagraphStyle("toc0", fontName=R, fontSize=size * 0.92, leading=size * 1.45,
                         leftIndent=0, firstLineIndent=0, spaceBefore=1)
    tsP = ParagraphStyle("tocP", parent=ts0, fontName=B, spaceBefore=8)
    ts1 = ParagraphStyle("toc1", parent=ts0, leftIndent=0.3 * inch)

    cov = Coverage(R)

    def P(markup, style):
        try:
            return Paragraph(cov.apply(markup), style)
        except Exception:
            return Paragraph(cov.apply(esc(plain(markup))), style)

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
        for b in blocks:
            if b.kind == "para":
                txt = b.text
                sty = st["flush"] if (fresh and not s["first_para_indent"]) else st["body"]
                m = re.match(r"^((?:<[^>]+>)*)((?:&\w+;|['\"\u2018\u201c(])?)(\w)", txt) \
                    if (cap_pending and txt) else None
                cap_pending = False
                if m:
                    letter = html.unescape(m.group(2)) + m.group(3)
                    rest = m.group(1) + txt[m.end():]
                    try:
                        story.append(ImageAndFlowables(DropLetter(letter, R, size, lead),
                                                       [P(rest, st["flush"])], imageSide="left",
                                                       imageRightPadding=3, imageBottomPadding=0,
                                                       imageTopPadding=0, imageLeftPadding=0))
                    except Exception:
                        story.append(P(txt, sty))
                else:
                    story.append(P(txt, sty))
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
                story.append(P(esc(s["scene_break"]) if s["scene_break"] != "Blank space" else "&#160;",
                               st["scene"]))
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
    used = sorted({f for f in cov.choice.values() if f})
    if used:
        log("Some characters aren't in the chosen font, so they were drawn with: " +
            ", ".join(sorted({u.split("_", 1)[1].rsplit("-", 1)[0] for u in used})))
    if cov.missing:
        log(f"WARNING: {len(cov.missing)} character(s) aren't in any installed font and may show as "
            "boxes: " + " ".join(sorted(cov.missing))[:120])
    return doc.page
