"""BookForge core: book model, defaults, and source parsers.

Text is kept verbatim. Only whitespace that exists purely for source-file
line wrapping is normalised; italics/bold/superscripts and line breaks are
carried through as a tiny markup subset: <i> <b> <super> <sub> <br/>.
"""
import html
import math
import os
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag, Comment

APP_NAME = "BookForge"
APP_VERSION = "1.8.0"
BUILD_DATE = "2026-10-28"     # shown next to the version so different builds can be told apart
APP_AUTHOR = "ChunksBabyRuth"

# --------------------------------------------------------------------------
# Defaults (every option the GUI exposes lives here)
# --------------------------------------------------------------------------
DEFAULTS = {
    # Source
    "source_mode": "file", "source_path": "", "split_mode": "Auto",
    "custom_regex": "", "strip_gutenberg": True, "skip_contents": True,
    "skip_cover": True, "include_images": False, "keep_front_text": False,
    "drop_empty": True, "line_paragraphs": "Auto", "preserve_breaks": False,
    "pdf_mode": "Keep the pages as they are", "keep_format": False,
    # Book info
    "title": "", "subtitle": "", "author": "", "credit": "",
    # Layout
    "page_size": "Letter (8.5 x 11 in)", "custom_w": 6.0, "custom_h": 9.0,
    "margin_top": 0.85, "margin_bottom": 0.85, "margin_inner": 1.0,
    "margin_outer": 1.0, "font_family": "Times (built-in)",
    "custom_font_path": "", "body_size": 13.0, "line_spacing": 1.38,
    "align": "Justified", "indent": 0.25, "para_space": 6.0,
    "first_para_indent": True, "title_size": 23.0, "sub_size": 14.5,
    "heading_font": "Same as body text", "dropcap_font": "Same as headings", "heading_bold": True,
    "custom_fonts": [], "fonts_dir": "", "dark_mode": True,
    "hyph_lang": "English (US)", "hyph_min": 6, "hyph_words": "", "avoid_runts": True,
    "drop_cap_lines": 2, "drop_cap_quote": "Hang the quote in the margin",
    "scene_markers": "***, * * *, *, ~, ~~~, #, ###, o0o, oOo, xXx, -o-, \u2042, \u00a7",
    "scene_symbols": True,
    "fic_info": "Leave out", "fic_summary": "Add a summary page",
    "an_mode": "Set apart (smaller, indented)",
    "chapter_label": "None", "title_case": "As written",
    "chapter_start": "New page", "chapter_sink": 0.0, "ornament": False,
    # Titles: alignment and position (the defaults print exactly as before these settings existed)
    "tp_align": "Centered",            # title page: title, subtitle, author and credit lines
    "tp_pos": 20.0,                    # title page: where the title starts, % down the text area
    "tp_title_size": 0.0,              # book title size in pt (0 = automatic: 1.5 x chapter title size, min 30)
    "ch_align": "Centered",            # chapter number line, title, subtitle, ornament + generated headings
    "part_align": "Centered",          # part label, part title and its ornament
    "part_pos": 30.0,                  # part pages: where the part title starts, % down the text area
    "part_size": 0.0,                  # part title size in pt (0 = automatic: 1.2 x chapter title size)
    "drop_cap": False, "scene_break": "Keep the source's own", "verse_style": "Centered italic",
    "pn_position": "Bottom center", "pn_style": "Rule above",
    "pn_mode": "Every page (title page = 1)", "pn_hide_openers": False,
    "pn_hide_blank": True, "pn_hide_title": False, "running_heads": False,
    # Front & back matter
    "title_page": True, "bookplate": "On title page",
    "bookplate_text": "This Book Belongs To", "dedication": "", "toc": True,
    "toc_title": "CONTENTS", "toc_dots": False, "toc_numbers": "None",
    "toc_case": "Title Case", "toc_spacing": "Automatic (avoid a nearly empty last page)",
    "note_title": "", "note_text": "",
    "note_place": "After contents", "the_end": False, "notes_pages": 0,
    "blank_pages_start": 0, "blank_pages_end": 0,     # blank pages before / after the book (0 = none)
    # Output
    "out_dir": "", "fmt_pdf": True, "fmt_impose": True, "fmt_cover": False,
    "fmt_epub": False, "fmt_docx": False, "fmt_html": False, "fmt_txt": False,
    "sheet_size": "Letter", "sig_sheets": 8, "fold_marks": True,
    "sig_marks": True, "rotate_back": False,
    "paper": "20 lb / 75 gsm (0.0040 in)", "blurb": "", "open_when_done": True,
    "spine_width": 0.0, "cover_front_image": "", "cover_back_image": "",
    "cover_image_fit": "Fill the panel (edges may be trimmed)", "cover_text_over_art": False,
    "cover_art_in_book": False,
    "cover_align": "Same as title page",    # front cover: title, subtitle and author lines
    "cover_pos": 32.0,                       # front cover: where the title line sits, % down the front panel
    # App
    "check_updates": True,
}
PDF_MODES = ["Keep the pages as they are", "Rebuild as an editable book"]
TITLE_ALIGNS = ["Centered", "Left", "Right"]
# Title alignment/position settings added in 1.8.0: projects and settings files from before then don't have
# them and open with these defaults, which print the titles exactly where earlier versions did.
TITLE_LAYOUT_KEYS = ("tp_align", "tp_pos", "tp_title_size", "ch_align", "part_align", "part_pos", "part_size",
                     "cover_align", "cover_pos")
# The front cover's title lines: the title page's alignment unless one is chosen for the cover itself.
COVER_ALIGNS = ["Same as title page"] + TITLE_ALIGNS
# "Blank pages at beginning / end": at most this many each, which keeps building and imposing quick
# (a block of 500 blank pages is far thicker than anything bound by hand).
BLANK_PAGES_MAX = 500
_BLANK_LABEL = {"start": "Blank pages at beginning", "end": "Blank pages at end"}


def parse_blank_count(v, label="Blank pages"):
    """A number of blank pages -> int. Whole numbers 0..BLANK_PAGES_MAX only; anything else raises ValueError
    with a plain message (nothing is rounded or replaced)."""
    if isinstance(v, bool):
        raise ValueError(f"{label}: type a whole number from 0 to {BLANK_PAGES_MAX}.")
    if isinstance(v, int):
        n = v
    elif isinstance(v, float):
        if not math.isfinite(v) or v != int(v):
            raise ValueError(f"{label}: use a whole number of pages (0 to {BLANK_PAGES_MAX}), not {v:g}.")
        n = int(v)
    else:
        t = str(v if v is not None else "").strip()
        if not re.fullmatch(r"[+-]?\d+", t):
            raise ValueError(f"{label}: \u201c{t}\u201d isn't a whole number of pages (0 to {BLANK_PAGES_MAX}).")
        n = int(t)
    if n < 0:
        raise ValueError(f"{label}: the number of pages can't be negative.")
    if n > BLANK_PAGES_MAX:
        raise ValueError(f"{label}: at most {BLANK_PAGES_MAX} pages.")
    return n


def blank_pages(s, which):
    """How many blank pages to put at the 'start' or 'end' of the book (checked; see parse_blank_count)."""
    return parse_blank_count(s.get(f"blank_pages_{which}", 0), _BLANK_LABEL[which])

# Finished book page sizes (the trimmed book page), width x height in INCHES, always upright (portrait or
# square). Sizes defined in millimetres are stored exactly (mm / 25.4); the name only shows them rounded and
# is never read back. Names are what projects store, so existing names never change.
_MM = 25.4
PAGE_SIZES = {
    "Letter (8.5 x 11 in)": (8.5, 11.0),
    "Half Letter / Digest (5.5 x 8.5 in)": (5.5, 8.5),
    "Trade Paperback (6 x 9 in)": (6.0, 9.0),
    "Paperback (5 x 8 in)": (5.0, 8.0),
    "Mass Market (4.25 x 6.87 in)": (4.25, 6.87),
    "A4 (8.27 x 11.69 in)": (210 / _MM, 297 / _MM),
    "A5 (5.83 x 8.27 in)": (148 / _MM, 210 / _MM),
    "Legal (8.5 x 14 in)": (8.5, 14.0),
    # more US trade sizes
    "Pocket (4 x 6 in)": (4.0, 6.0),
    "Trade (5.25 x 8 in)": (5.25, 8.0),
    "Textbook (7 x 10 in)": (7.0, 10.0),
    "Large (8 x 10 in)": (8.0, 10.0),
    "Square (8 x 8 in)": (8.0, 8.0),
    "Square (8.5 x 8.5 in)": (8.5, 8.5),
    "5.06 x 7.81 in": (5.06, 7.81),
    "6.69 x 9.61 in": (6.69, 9.61),
    "7.5 x 9.25 in": (7.5, 9.25),
    "8.25 x 11 in": (8.25, 11.0),
    # ISO and JIS
    "A6 (105 x 148 mm)": (105 / _MM, 148 / _MM),
    "B4 (250 x 353 mm)": (250 / _MM, 353 / _MM),
    "B5 (176 x 250 mm)": (176 / _MM, 250 / _MM),
    "B6 (125 x 176 mm)": (125 / _MM, 176 / _MM),
    "JIS B5 (182 x 257 mm)": (182 / _MM, 257 / _MM),
    "JIS B6 (128 x 182 mm)": (128 / _MM, 182 / _MM),
    # traditional British book sizes (metric) and paperbacks
    "A-format Paperback (111 x 178 mm)": (111 / _MM, 178 / _MM),
    "Penguin Small Paperback (111 x 181 mm)": (111 / _MM, 181 / _MM),
    "Crown Octavo (123 x 186 mm)": (123 / _MM, 186 / _MM),
    "Large Crown Octavo / B-format (129 x 198 mm)": (129 / _MM, 198 / _MM),
    "Demy Octavo (138 x 216 mm)": (138 / _MM, 216 / _MM),
    "Royal Octavo (156 x 234 mm, 6.14 x 9.21 in)": (156 / _MM, 234 / _MM),
    "Crown Quarto (189 x 246 mm, 7.44 x 9.69 in)": (189 / _MM, 246 / _MM),
    "Large Crown Quarto (201 x 258 mm)": (201 / _MM, 258 / _MM),
    "Demy Quarto (219 x 276 mm)": (219 / _MM, 276 / _MM),
    "Royal Quarto (237 x 312 mm)": (237 / _MM, 312 / _MM),
    "Custom": None,
}
CUSTOM_PAGE_MIN_IN, CUSTOM_PAGE_MAX_IN = 0.1, 200.0     # a custom finished page: 0.1 to 200 inches a side (PDF limit)
PAPERS = {"20 lb / 75 gsm (0.0040 in)": 0.0040,
          "24 lb / 90 gsm (0.0045 in)": 0.0045,
          "28 lb / 105 gsm (0.0050 in)": 0.0050,
          "32 lb / 120 gsm (0.0055 in)": 0.0055}


def page_size_inches(s):
    """The finished book page (width, height) in inches: a preset, or the custom size (checked)."""
    v = PAGE_SIZES.get(s["page_size"])
    if v is None:
        return custom_page_inches(s.get("custom_w"), s.get("custom_h"))
    return v


def custom_page_inches(w, h):
    """A custom finished page size in inches, checked: ordinary numbers from CUSTOM_PAGE_MIN_IN to CUSTOM_PAGE_MAX_IN."""
    out = []
    for name, v in (("width", w), ("height", h)):
        try:
            x = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"Custom book page {name}: \u201c{v}\u201d isn't a number of inches.") from None
        if not math.isfinite(x) or not CUSTOM_PAGE_MIN_IN <= x <= CUSTOM_PAGE_MAX_IN:
            raise ValueError(f"Custom book page {name} must be between {CUSTOM_PAGE_MIN_IN:g} and "
                             f"{CUSTOM_PAGE_MAX_IN:g} inches (it is {v}).")
        out.append(x)
    return tuple(out)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
@dataclass
class Block:
    kind: str            # para | verse | quote | head | scene | image
    text: str = ""       # markup for para/quote/head
    lines: list = field(default_factory=list)   # verse lines (markup)
    image: bytes = None
    image_name: str = ""
    bullet: str = ""     # list items: "\u2022", "1." ...
    depth: int = 0       # list nesting level
    label: str = ""      # author's notes: "Notes", "Chapter End Notes", "Summary" ...
    align: str = ""      # set in the editor: "" (style default) | left | center | right | justify
    indent: int = 0      # set in the editor: extra left indent, in steps of 0.25 in
    space: int = 0       # set in the editor: extra space above the paragraph, in points
    img_width: int = 0   # pictures: width as a % of the text width (0 = automatic size)
    img_place: str = ""  # pictures: "" in the text | "page" on a page of its own | "full" whole page, edge to edge


def new_uid():
    import uuid
    return uuid.uuid4().hex[:12]


@dataclass
class Chapter:
    title: str
    label: str = ""      # e.g. "CHAPTER I" when the source splits label/title
    level: int = 1       # 0 = part, 1 = chapter
    blocks: list = field(default_factory=list)
    include: bool = True
    heading_kind: str = "head"   # what the heading was in the source: "head" (a heading) or "para" (a line)
    uid: str = field(default_factory=new_uid)   # stays the same when chapters are renamed or moved

    def display(self):
        if self.label and self.title:
            return f"{self.label} \u2014 {self.title}"
        return self.title or self.label


@dataclass
class Book:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    credit: str = ""
    language: str = "en"
    chapters: list = field(default_factory=list)
    front_blocks: list = field(default_factory=list)
    fic_meta: list = field(default_factory=list)      # fanfic work info lines (markup)
    fic_summary: list = field(default_factory=list)   # Blocks
    fic_notes: list = field(default_factory=list)     # Blocks (work-level author's notes)
    # Changes made in "Edit contents": [{"uid", "title", "page", "show", "level", "custom"}] in display
    # order. Empty = the automatic contents. Saved in projects with the book.
    toc: list = field(default_factory=list)
    # Front & back pages edited in Specific Text Edit (see bf_matter): {key: {"blocks": [Block] or None,
    # "title": heading or None}}. Empty = every page made automatically, as before. Saved in projects.
    matter: dict = field(default_factory=dict)
    # Copies of the cover pictures, saved in projects so they still work if the picture files move
    cover_front: bytes = None
    cover_back: bytes = None
    # A PDF whose own pages are printed as they are ("Keep the pages as they are"); no chapters then
    fixed_pdf: str = ""
    fixed_pages: int = 0

    def active(self):
        return [c for c in self.chapters if c.include]


# --------------------------------------------------------------------------
# Markup helpers
# --------------------------------------------------------------------------
# Invisible / typographic-spacing characters that fonts often lack. Removing or
# normalising them changes spacing only, never the words themselves.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\ufe0e\ufe0f\u00ad\u200a"), None)
_INVISIBLE.update({ord(c): " " for c in "\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u202f\u205f"})
_INVISIBLE[0x2011] = "-"


def clean_chars(t):
    return t.translate(_INVISIBLE)


def esc(t):
    return html.escape(clean_chars(t), quote=False)


def norm_ws(m):
    m = re.sub(r"\s+", " ", m)
    m = re.sub(r"\s*<br/>\s*", "<br/>", m)
    for _ in range(4):
        m = re.sub(r"<(i|b|super|sub|strike|u)>\s*</\1>", "", m)
        m = re.sub(r"^\s*(<br/>\s*)+|(\s*<br/>)+\s*$", "", m)
    return m.strip()


def plain(markup):
    t = re.sub(r"<br/>", "\n", markup)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)


ITAL = {"i", "em", "cite", "var", "dfn"}
BOLD = {"b", "strong"}
INLINE = ITAL | BOLD | {"a", "span", "sup", "sub", "small", "big", "u", "s",
                        "abbr", "br", "font", "code", "tt", "q", "ins",
                        "del", "mark", "label", "acronym", "strike", "img"}
SKIP = {"script", "style", "head", "title", "meta", "link", "svg", "math"}
PG_IDS = {"pg-header", "pg-footer", "pg-machine-header", "pg-start-separator",
          "pg-end-separator"}


def _classes(tag):
    c = tag.get("class") or []
    return " ".join(c).lower() if isinstance(c, list) else str(c).lower()


BACK_ARROWS = re.compile(r"^[\s\u21a9\u21aa\u2191\u2934\u2b11\u21b5\u2b8c\ufe0e\ufe0f^]+$")


def _semantics(tag):
    return " ".join(str(tag.get(k, "")) for k in ("epub:type", "role", "class", "rel")).lower()


def _is_backlink(tag):
    sem = _semantics(tag)
    if "backlink" in sem or "footnote-back" in sem or "footnote-return" in sem:
        return True
    return bool(BACK_ARROWS.match(tag.get_text() or "")) and bool(tag.get_text().strip())


def _is_noteref(tag):
    sem = _semantics(tag)
    if "noteref" in sem or "footnote-ref" in sem or "fnref" in sem:
        return tag.find("sup") is None and tag.parent is not None and tag.parent.name != "sup"
    return False


def _keepfmt_ctx():
    """The "keep the source's look" context while a file is read with that option on, else None."""
    import bf_keepfmt
    return bf_keepfmt.current()


def inline_markup(node):
    out = []
    for c in node.children:
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            if type(c) is NavigableString:
                out.append(esc(str(c)))
            continue
        if not isinstance(c, Tag):
            continue
        n = c.name.lower()
        if n in SKIP or n == "img":
            continue
        if n == "a" and _is_backlink(c):
            continue
        kf = _keepfmt_ctx()
        kf_o, kf_c = kf.span_font(c) if kf is not None and n != "br" else ("", "")
        start = len(out)
        if n == "br":
            out.append("<br/>")
        elif n == "a" and _is_noteref(c):
            out.append("<super>" + inline_markup(c) + "</super>")
        elif n in ITAL or (n == "span" and ("ital" in _classes(c) or
                           "italic" in (c.get("style") or "").lower())):
            out.append("<i>" + inline_markup(c) + "</i>")
        elif n in BOLD or (n == "span" and "bold" in _classes(c)):
            out.append("<b>" + inline_markup(c) + "</b>")
        elif n in ("s", "strike", "del") or (n == "span" and (
                "line-through" in (c.get("style") or "").lower() or "strike" in _classes(c))):
            out.append("<strike>" + inline_markup(c) + "</strike>")
        elif n in ("u", "ins") or (n == "span" and (
                "underline" in (c.get("style") or "").lower() or "underline" in _classes(c))):
            out.append("<u>" + inline_markup(c) + "</u>")
        elif n == "sup":
            out.append("<super>" + inline_markup(c) + "</super>")
        elif n == "sub":
            out.append("<sub>" + inline_markup(c) + "</sub>")
        else:
            out.append(inline_markup(c))
        if kf_o:                                   # the source's own font/size/colour for this tag
            seg = "".join(out[start:])
            del out[start:]
            out.append(kf_o + seg + kf_c if seg.strip() else seg)
    return "".join(out)


# --------------------------------------------------------------------------
# HTML walker -> flat event list
#   ("head", level, text) ("para", markup) ("verse", lines) ("quote", markup)
#   ("scene",) ("image", src)
# --------------------------------------------------------------------------
BOILER_TYPES = {"imprint", "colophon", "copyright-page", "titlepage", "halftitlepage"}


def _is_pg(tag):
    if tag.get("id") in PG_IDS:
        return True
    c = _classes(tag)
    if "pg-boilerplate" in c or "pgheader" in c:
        return True
    types = set(str(tag.get("epub:type", "")).lower().split())
    return bool(types & BOILER_TYPES)


def _verse_lines(tag):
    stanzas = tag.find_all(lambda t: isinstance(t, Tag) and "stanza" in _classes(t))
    stanzas = stanzas or [tag]
    lines = []
    for st in stanzas:
        if lines:
            lines.append("")
        buf = []
        for ch in st.children:
            if isinstance(ch, Tag) and ch.name.lower() not in ("br",) and \
                    ch.name.lower() not in INLINE:
                if buf:
                    lines.extend(x for x in norm_ws("".join(buf)).split("<br/>") if x)
                    buf = []
                t = norm_ws(inline_markup(ch))
                lines.extend(x for x in t.split("<br/>") if x)
            elif isinstance(ch, Tag):
                if ch.name.lower() == "br":
                    buf.append("<br/>")
                else:
                    tmp = BeautifulSoup("", "html.parser")
                    wrap = tmp.new_tag("x")
                    wrap.append(ch.__copy__())
                    buf.append(inline_markup(wrap))
            elif type(ch) is NavigableString:
                buf.append(esc(str(ch)))
        if buf:
            lines.extend(x for x in norm_ws("".join(buf)).split("<br/>") if x)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


NOTE_WORDS = {"notes", "note", "endnotes", "end-notes", "chapter-notes", "chapternotes", "summary",
              "authors-note", "author-note", "authors-notes", "authornote", "fff_chapter_notes",
              "fff_head_notes", "fff_foot_notes", "fff_chapter_summary", "chapter-summary"}
BULLETS = ("\u2022", "\u2013", "\u2022")


def _note_kind(tag):
    """'notes' / 'summary' when an element is an author's-note box (AO3, FanFicFare...), else None."""
    sem = _semantics(tag)
    if any(k in sem for k in ("endnote", "footnote", "rearnote")) and "fff" not in sem:
        return None                      # real endnotes (Standard Ebooks etc.) stay as text
    words = set(_classes(tag).replace(",", " ").split()) | {str(tag.get("id", "")).lower()}
    if not words & NOTE_WORDS:
        return None
    return "summary" if any("summary" in w for w in words) else "notes"


def walk(node, out, strip_pg, depth=0):
    buf = []

    def flush():
        if buf:
            m = norm_ws("".join(buf))
            if m:
                out.append(("para", m))
            buf.clear()

    lvl = 2
    for c in node.children:
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            if type(c) is NavigableString:
                buf.append(esc(str(c)))
            continue
        if not isinstance(c, Tag):
            continue
        n = c.name.lower()
        if n in SKIP:
            continue
        if strip_pg and _is_pg(c):
            flush()
            continue
        if n in INLINE and n != "img":
            if n == "br":
                buf.append("<br/>")
            else:
                tmp = BeautifulSoup("", "html.parser").new_tag("x")
                tmp.append(c.__copy__())
                buf.append(inline_markup(tmp))
            for im in c.find_all("img"):
                flush()
                out.append(("image", im.get("src", "")))
            continue
        flush()
        cls = _classes(c)
        nk = _note_kind(c) if n in ("div", "section", "aside", "blockquote") else None
        if nk:
            sub = []
            walk(c, sub, strip_pg, depth)
            out.append(("note_open", nk))
            out.extend(sub)
            out.append(("note_close",))
            continue
        if n in ("header", "hgroup") and c.find(re.compile(r"^h[1-6]$")):
            for ch in c.children:
                if not isinstance(ch, Tag):
                    continue
                cn = ch.name.lower()
                if re.fullmatch(r"h[1-6]", cn):
                    t = norm_ws(esc(ch.get_text(" ")))
                    if t:
                        out.append(("head", int(cn[1]), html.unescape(t)))
                        lvl = int(cn[1])
                elif cn in ("p", "div", "span"):
                    m = norm_ws(inline_markup(ch))
                    if not m:
                        continue
                    et = str(ch.get("epub:type", "")).lower().split()
                    if "title" in et and len(plain(m)) < 90:
                        out.append(("head", lvl, plain(m)))
                    else:
                        out.append(("subtitle", m))
                else:
                    walk(ch, out, strip_pg, depth)
        elif re.fullmatch(r"h[1-6]", n):
            t = norm_ws(esc(c.get_text(" ")))
            if t:
                out.append(("head", int(n[1]), html.unescape(t)))
        elif n == "img":
            out.append(("image", c.get("src", "")))
        elif n == "pre":
            lines = [esc(l.rstrip()) for l in c.get_text().split("\n")]
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            lines = [re.sub(r"\s+", " ", l).strip() for l in lines]
            if lines:
                out.append(("verse", lines))
        elif n == "div" and any(k in cls for k in ("poem", "verse", "stanza", "poetry")):
            lines = _verse_lines(c)
            if lines:
                out.append(("verse", lines))
        elif n == "p":
            m = norm_ws(inline_markup(c))
            kf = _keepfmt_ctx()
            if m and kf is not None:
                o, cl = kf.span_font(c)
                fmt = kf.block_fmt(c)
                out.append(("para", o + m + cl, fmt) if fmt else ("para", o + m + cl))
            elif m:
                out.append(("para", m))
            for im in c.find_all("img"):
                out.append(("image", im.get("src", "")))
        elif n == "hr":
            out.append(("scene",))
        elif n == "blockquote":
            sub = []
            walk(c, sub, strip_pg, depth)
            for ev in sub:
                out.append(("quote",) + tuple(ev[1:]) if ev[0] == "para" else ev)
        elif n in ("ul", "ol"):
            try:
                start = int(c.get("start", 1))
            except ValueError:
                start = 1
            for i, li in enumerate(c.find_all("li", recursive=False)):
                sub = []
                walk(li, sub, strip_pg, depth + 1)
                bullet = BULLETS[depth % 3] if n == "ul" else f"{start + i}."
                if sub and sub[0][0] == "para":
                    out.append(("item", sub[0][1], bullet, depth))
                    sub = sub[1:]
                else:
                    out.append(("item", "", bullet, depth))
                for ev in sub:      # further paragraphs of the same item line up with its text
                    out.append(("item", ev[1], "", depth) if ev[0] == "para" else ev)
        elif n == "dl":
            term = None
            for ch in c.find_all(["dt", "dd"], recursive=False):
                m = norm_ws(inline_markup(ch))
                if ch.name == "dt":
                    if term:
                        out.append(("para", term))
                    term = m
                else:
                    out.append(("para", (f"<b>{term}</b> " if term else "") + m))
                    term = None
            if term:
                out.append(("para", term))
        elif n == "table":
            for tr in c.find_all("tr"):
                cells = [norm_ws(inline_markup(td)) for td in tr.find_all(["td", "th"])]
                cells = [x for x in cells if x]
                if cells:
                    out.append(("para", "\u2003".join(cells)))
        else:
            walk(c, out, strip_pg, depth)
    flush()


# --------------------------------------------------------------------------
# Events -> Book
# --------------------------------------------------------------------------
START_RE = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", re.I)
END_RE = re.compile(r"(\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG|"
                    r"^\s*End of (the )?Project Gutenberg|FULL PROJECT GUTENBERG LICEN[CS]E)", re.I)
BYLINE_RE = re.compile(r"^\s*((translated|illustrated|edited|written|retold)\s+)?by\s", re.I)
CONTENTS_RE = re.compile(r"^\s*(table of )?contents\.?\s*$|^\s*list of (illustrations|plates)\.?\s*$", re.I)
NUM_WORDS = (r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
             r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
             r"ninety|hundred|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|final)"
             r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine|first|second|third|fourth|fifth|"
             r"sixth|seventh|eighth|ninth))?)")
LABEL_RE = re.compile(r"^\s*((chapter|chap\.|part|book|section|canto|letter|stave|act)\s+"
                      r"([ivxlcdm]+|\d+|" + NUM_WORDS + r")\.?|[ivxlcdm]+\.?|\d+\.?)\s*$", re.I)
# AO3 / fanfic page labels that start with "Chapter" but are not chapters
AO3_LABEL_RE = re.compile(r"^\s*(chapter\s+(summary|notes|end\s+notes|text)|(work\s+)?(end\s+)?notes|"
                          r"summary|author'?s'?\s+notes?)\s*:?\s*$", re.I)
PARA_CHAPTER_RE = re.compile(r"^\s*(chapter|part|prologue|epilogue|interlude)\b.{0,50}$", re.I)
FIC_FRONT_RE = re.compile(r"^\s*(preface|afterword)\s*$", re.I)


def _ev_text(ev):
    if ev[0] == "head":
        return ev[2]
    if ev[0] in ("para", "quote", "subtitle", "item"):
        return plain(ev[1])
    if ev[0] == "verse":
        return " ".join(plain(l) for l in ev[1])
    return ""


def cut_gutenberg(events):
    start = 0
    for i, ev in enumerate(events):
        if START_RE.search(_ev_text(ev)):
            start = i + 1
            break
    end = len(events)
    for i in range(start, len(events)):
        if END_RE.search(_ev_text(events[i])):
            end = i
            break
    return events[start:end]


NOTE_LABEL_RE = re.compile(r"^\(?\s*((chapter|work)\s+)?(end\s+)?(notes?|summary|author'?s'?\s+notes?)"
                           r"(\s*\(.*\))?\s*:?\s*\)?$", re.I)
SEE_END_RE = re.compile(r"^\(?\s*see the end of the (chapter|work) for (more )?notes\.?\s*\)?$", re.I)
AN_RE = re.compile(r"^\s*[\(\[]?\s*(?:A/N\b|A/N:|AN\s*:|(?i:author'?s'?\s+notes?)\s*:)")
META_RE = re.compile(r"^(rating|archive warnings?|warnings?|categor(y|ies)|fandoms?|relationships?|"
                     r"pairings?|characters?|additional tags|freeform tags|tags|language|series|stats|"
                     r"published|updated|completed|words|chapters|comments|kudos|bookmarks|hits|status|"
                     r"collections?|genres?|rated|story url|author url|source|packaged)\s*:", re.I)
SUMMARY_RE = re.compile(r"^\s*summary\s*:\s*", re.I)
FIC_BOILER_RE = re.compile(r"^(please drop by the archive and comment|posted originally on the archive of our own|"
                           r"works inspired by this one|for more notes, see|this story was (archived|downloaded))",
                           re.I)
SYMBOLS_ONLY = re.compile(r"^[^\w\s\"'\u2018\u2019\u201c\u201d\u00ab\u00bb()\[\]]"
                          r"[^\w\"'\u2018\u2019\u201c\u201d\u00ab\u00bb()\[\]]{0,24}$")


def scene_markers(s):
    raw = s.get("scene_markers") or ""
    return {m.strip().lower() for m in re.split(r"[,\n]", raw) if m.strip()}


def is_scene(text, s, markers=None):
    t = text.strip()
    if not t or len(t) > 30:
        return False
    markers = scene_markers(s) if markers is None else markers
    if t.lower() in markers or re.sub(r"\s+", " ", t).lower() in markers:
        return True
    return bool(s.get("scene_symbols", True) and SYMBOLS_ONLY.match(t))


def _evfmt(ev):
    """Paragraph formatting a reader kept from the source ("keep_format"): a dict at the end of an event."""
    f = ev[-1] if len(ev) > 2 and isinstance(ev[-1], dict) else {}
    out = {}
    if f.get("align") in ("left", "center", "right", "justify"):
        out["align"] = f["align"]
    for k in ("indent", "space"):
        try:
            if int(f.get(k) or 0) > 0:
                out[k] = int(f[k])
        except (TypeError, ValueError):
            pass
    return out


def events_to_book(events, s, meta=None, images=None):
    meta = meta or {}
    images = images or {}
    if s.get("strip_gutenberg") and not s.get("_gut_cut_done"):
        events = cut_gutenberg(events)
    # headings inside author's-note boxes are note labels, not chapters
    depth, fixed = 0, []
    for ev in events:
        if ev[0] == "note_open":
            depth += 1
        elif ev[0] == "note_close":
            depth = max(0, depth - 1)
        elif ev[0] == "head" and depth:
            ev = ("notelabel", ev[2])
        fixed.append(ev)
    events = fixed
    toc = {re.sub(r"\W+", "", t.lower()) for t in (meta or {}).get("toc_titles", [])}
    toc.discard("")
    heads = [e for e in events if e[0] == "head" and not AO3_LABEL_RE.match(e[2])]
    events = [e for e in events if not (e[0] == "head" and AO3_LABEL_RE.match(e[2]))]
    # Chapters marked only by "Chapter 1." paragraphs (e.g. AO3 one-shots with chapters in the text)
    para_mode = False
    if s.get("split_mode", "Auto") == "Auto":
        mtitle = re.sub(r"\W+", "", (meta or {}).get("title", "").lower())
        story_heads = {re.sub(r"\W+", "", e[2].lower()) for e in heads if not FIC_FRONT_RE.match(e[2])}
        story_heads = {h for h in story_heads if h and not (mtitle and mtitle.startswith(h))}
        para_marks = [i for i, e in enumerate(events) if e[0] == "para" and len(plain(e[1]).strip()) <= 60
                      and PARA_CHAPTER_RE.match(plain(e[1]).strip()) and not AO3_LABEL_RE.match(plain(e[1]).strip())]
        if len(story_heads) <= 1 and len(para_marks) >= 2:
            para_mode = True
            for i in para_marks:
                events[i] = ("head", 99, plain(events[i][1]).strip())
            heads = [e for e in events if e[0] == "head"]
    counts = {}
    for e in heads:
        counts[e[1]] = counts.get(e[1], 0) + 1
    mode = s.get("split_mode", "Auto")
    part_level = None
    if para_mode:
        chap_level = 99
    elif mode.startswith("Heading level"):
        chap_level = int(mode[-1])
    elif mode == "No chapters":
        chap_level = None
    else:
        levels = sorted(l for l, n in counts.items() if n >= 2)
        chap_level = levels[0] if levels else None
        if chap_level is not None:
            deeper = [l for l in levels if l > chap_level]
            if deeper and counts[deeper[0]] >= 2 * counts[chap_level] and counts[chap_level] <= 12:
                part_level, chap_level = chap_level, deeper[0]

    book = Book(title=meta.get("title", ""), author=meta.get("author", ""),
                language=meta.get("language", "en") or "en")
    markers = scene_markers(s)
    strip = s.get("strip_gutenberg", True)
    # EPUB table of contents: if it lists most chapter headings, headings it leaves out are
    # headings the author used inside the story, not chapters.
    lvl_heads = [e[2] for e in heads if chap_level is not None and e[1] == chap_level]
    in_toc = [h for h in lvl_heads if re.sub(r"\W+", "", h.lower()) in toc]
    use_toc = bool(toc) and len(in_toc) >= 2 and len(in_toc) >= 0.6 * len(lvl_heads)
    cur = None
    note_depth, note_label = 0, ""
    see_label = ""
    pending_label = None

    def add_block(b):
        if cur is None:
            book.front_blocks.append(b)
        else:
            cur.blocks.append(b)

    def note(text, label):
        add_block(Block("anote", text, label=label))

    for idx, ev in enumerate(events):
        k = ev[0]
        nxt = events[idx + 1][0] if idx + 1 < len(events) else None
        if k == "note_open":
            note_depth += 1
            note_label = "Summary" if ev[1] == "summary" else ""
            continue
        if k == "note_close":
            note_depth = max(0, note_depth - 1)
            if not note_depth:
                note_label = ""
            continue
        if k == "notelabel":
            note_label = ev[1].strip().rstrip(":").strip()
            continue
        if k == "head" and chap_level is not None and (ev[1] == chap_level or ev[1] == part_level):
            pending_label = None
            text = ev[2].strip()
            if use_toc and cur is not None and not LABEL_RE.match(text) and \
                    not FIC_FRONT_RE.match(text) and re.sub(r"\W+", "", text.lower()) not in toc:
                add_block(Block("head", esc(text)))         # heading inside the story text
                continue
            lvl = 0 if ev[1] == part_level else 1
            if cur is not None and not cur.blocks and cur.level == lvl and \
                    LABEL_RE.match(cur.title) and not cur.label and not LABEL_RE.match(text):
                cur.label, cur.title = cur.title, text
                continue
            cur = Chapter(title=text, level=lvl,
                          heading_kind="para" if (s.get("_gut_cut_done") or para_mode) else "head")
            book.chapters.append(cur)
            continue
        txt = _ev_text(ev).strip() if k in ("para", "quote", "verse", "item", "subtitle") else ""
        # ---- author's notes, summaries, work info (fanfiction downloads)
        if note_depth and k in ("para", "quote", "verse", "item", "subtitle"):
            if k == "para" and len(txt) < 45 and NOTE_LABEL_RE.match(txt):
                note_label = txt.rstrip(":").strip()
                continue
            note(ev[1] if k != "verse" else "<br/>".join(ev[1]), note_label)
            continue
        if k == "quote" and pending_label is not None:
            note(ev[1], pending_label)
            continue
        pending_label = None
        if k == "para":
            if len(txt) < 45 and NOTE_LABEL_RE.match(txt) and nxt == "quote":
                pending_label = txt.rstrip(":").strip()
                continue
            if len(txt) < 45 and NOTE_LABEL_RE.match(txt) and nxt == "para" and \
                    SEE_END_RE.match(_ev_text(events[idx + 1]).strip()):
                see_label = txt.rstrip(":").strip()
                continue
            if SEE_END_RE.match(txt) or AN_RE.match(txt):
                note(ev[1], see_label if SEE_END_RE.match(txt) else "")
                see_label = ""
                continue
            if strip and FIC_BOILER_RE.match(txt):
                continue
            segs = ev[1].split("<br/>")
            if len(segs) > 1 and sum(1 for sg in segs if META_RE.match(plain(sg).strip())) >= 2:
                for sg in segs:          # title-page block of "Label: value" lines (FanFicFare)
                    pt = plain(sg).strip()
                    if not pt:
                        continue
                    if SUMMARY_RE.match(pt):
                        note(SUMMARY_RE.sub("", re.sub(r"^\s*<b>(.*?)</b>", r"\1", sg)).strip(), "Summary")
                    elif META_RE.match(pt):
                        add_block(Block("meta", sg))
                    else:
                        add_block(Block("para", sg))
                continue
            if SUMMARY_RE.match(txt) and (cur is None or len(cur.blocks) < 20) and \
                    any(b.kind == "meta" for b in (cur.blocks if cur else book.front_blocks)):
                note(SUMMARY_RE.sub("", re.sub(r"^\s*<b>(.*?)</b>", r"\1", ev[1])).strip(), "Summary")
                continue
            if META_RE.match(txt) and len(txt) < 4000:      # AO3 tag lists can be long
                add_block(Block("meta", ev[1]))
                continue
            if is_scene(txt, s, markers):
                add_block(Block("scene", ev[1]))
                continue
        # ---- ordinary content
        if k == "head":
            if chap_level is not None and ev[1] < chap_level and cur is None:
                continue          # book title etc. before first chapter
            if strip and chap_level is not None and ev[1] != chap_level and FIC_FRONT_RE.match(ev[2]):
                continue          # AO3 "Afterword" page heading
            add_block(Block("head", esc(ev[2])))
        elif k == "para":
            add_block(Block("para", ev[1], **_evfmt(ev)))
        elif k == "quote":
            add_block(Block("quote", ev[1], **_evfmt(ev)))
        elif k == "item":
            add_block(Block("item", ev[1], bullet=ev[2], depth=ev[3], **_evfmt(ev)))
        elif k == "subtitle":
            add_block(Block("subtitle", ev[1]) if cur is not None and not cur.blocks
                      else Block("para", ev[1], **_evfmt(ev)))
        elif k == "verse":
            add_block(Block("verse", lines=ev[1]))
        elif k == "scene":
            add_block(Block("scene", ev[1] if len(ev) > 1 else ""))
        elif k == "image":
            if s.get("include_images") and ev[1] in images:
                add_block(Block("image", image=images[ev[1]], image_name=ev[1]))

    if not book.chapters:
        ch = Chapter(title=book.title or "Untitled", blocks=book.front_blocks)
        book.chapters = [ch]
        book.front_blocks = []

    # ---- fanfic work info / summary / notes: from the front, or from a preface "chapter"
    def harvest(blocks):
        rest = []
        for b in blocks:
            if b.kind == "meta":
                book.fic_meta.append(b.text)
            elif b.kind == "anote" and "summary" in b.label.lower():
                book.fic_summary.append(b)
            elif b.kind == "anote":
                book.fic_notes.append(b)
            else:
                rest.append(b)
        return rest

    book.front_blocks = harvest(book.front_blocks)
    for ch in book.chapters[:2]:
        if sum(1 for b in ch.blocks if b.kind == "meta") >= 3:
            ch.blocks = harvest(ch.blocks)
            if all(b.kind in ("para", "head", "scene") and len(plain(b.text)) < 200 for b in ch.blocks):
                ch.include = False          # nothing but the work's title page
    if len(book.fic_meta) >= 3:              # a fanfic download: its "Preface" pages are not chapters
        tnorm = re.sub(r"\W+", "", (book.title or "").lower())
        for ch in book.chapters[:3]:
            if not ch.include or not (FIC_FRONT_RE.match(ch.title or "") and ch.title.strip().lower() == "preface"
                                      or (tnorm and re.sub(r"\W+", "", ch.title.lower()) == tnorm)):
                continue
            if sum(len(plain(b.text)) for b in ch.blocks if b.kind in ("para", "verse")) > 4000:
                continue                     # real story text: leave it alone
            rest = harvest(ch.blocks)
            for b in rest:                   # e.g. "Translation into ... available" lists
                pt = plain(b.text).strip()
                if b.kind in ("para", "item") and pt and not BYLINE_RE.match(pt) and \
                        not FIC_BOILER_RE.match(pt) and pt.lower() != (book.title or "").lower() and \
                        "posted originally on the archive" not in pt.lower():
                    book.fic_meta.append(b.text)
            ch.include = False
    if len(book.fic_meta) < 3:              # not really a fanfic header: put lines back
        book.front_blocks = [Block("para", m) for m in book.fic_meta] + book.front_blocks
        book.fic_meta = []
    for ch in book.chapters:                # stray meta lines inside a story stay as text
        for b in ch.blocks:
            if b.kind == "meta":
                b.kind = "para"
    if len([c for c in book.chapters if c.include and c.level == 1]) == 1:
        only = next(c for c in book.chapters if c.include and c.level == 1)
        if only.title.strip().lower() == "chapter text" and book.title:
            only.title = book.title

    # ---- clean up
    out = []
    seen_real = False
    for ch in book.chapters:
        if not ch.include:
            continue
        if not seen_real and BYLINE_RE.match(ch.title or "") and len(ch.blocks) <= 3:
            book.front_blocks.extend(ch.blocks)
            continue
        if ch.blocks:
            seen_real = True
        while ch.blocks and ch.blocks[0].kind == "scene":
            ch.blocks.pop(0)
        while ch.blocks and ch.blocks[-1].kind == "scene":
            ch.blocks.pop()
        if s.get("skip_contents") and CONTENTS_RE.match(ch.title or ""):
            continue
        if strip and re.match(r"^\s*afterword\s*$", ch.title or "", re.I) and \
                all(b.kind == "anote" for b in ch.blocks):
            if out:                          # AO3 "Afterword" = the work's end notes
                out[-1].blocks.extend(ch.blocks)
            continue
        if s.get("drop_empty") and ch.level == 1 and not ch.blocks:
            continue
        out.append(ch)
    book.chapters = out
    if not s.get("keep_front_text"):
        book.front_blocks = []
    else:
        book.front_blocks = [b for b in book.front_blocks if b.kind != "scene"]
    return book


# --------------------------------------------------------------------------
# EPUB
# --------------------------------------------------------------------------
NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/",
      "c": "urn:oasis:names:tc:opendocument:xmlns:container"}


def parse_epub(path, s):
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    if "META-INF/encryption.xml" in names:
        enc = z.read("META-INF/encryption.xml").decode("utf-8", "ignore")
        if "EncryptedData" in enc and "obfuscation" not in enc.lower():
            raise ValueError("This EPUB is DRM-protected and can't be opened.")
    cont = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = cont.find(".//c:rootfile", NS).get("full-path")
    base = posixpath.dirname(opf_path)
    opf = ET.fromstring(z.read(opf_path))
    meta = {}
    t = opf.find(".//dc:title", NS)
    creators = [(x.text or "").strip() for x in opf.findall(".//dc:creator", NS) if (x.text or "").strip()]
    l = opf.find(".//dc:language", NS)
    meta["title"] = (t.text or "").strip() if t is not None else ""
    meta["author"] = " and ".join(creators[:3])
    meta["language"] = (l.text or "en").strip() if l is not None else "en"
    manifest = {}
    for it in opf.find("opf:manifest", NS):
        manifest[it.get("id")] = (posixpath.normpath(posixpath.join(base, it.get("href", ""))),
                                  it.get("media-type", ""), it.get("properties", "") or "")
    toc_titles = []
    for _id, (href, mt, props) in manifest.items():
        try:
            if mt == "application/x-dtbncx+xml" and href in names:
                import warnings
                from bs4 import XMLParsedAsHTMLWarning
                warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
                ncx = BeautifulSoup(z.read(href), "html.parser")
                toc_titles += [x.get_text(" ", strip=True) for x in ncx.find_all("navlabel")]
            elif "nav" in props and href in names:
                nav = BeautifulSoup(z.read(href), "html.parser")
                toc_titles += [a.get_text(" ", strip=True) for a in nav.find_all("a")]
        except Exception:
            pass
    meta["toc_titles"] = toc_titles
    if s.get("keep_format"):
        import bf_keepfmt
        css = ""
        for _id, (href, mt, _props) in manifest.items():
            if mt == "text/css" and href in names:
                css += z.read(href).decode("utf-8", "ignore") + "\n"
        bf_keepfmt.set_current(bf_keepfmt.Context(bf_keepfmt.css_rules(css)))
    try:
        return _epub_spine(z, names, opf, manifest, meta, s)
    finally:
        if s.get("keep_format"):
            import bf_keepfmt
            bf_keepfmt.set_current(None)


def _epub_spine(z, names, opf, manifest, meta, s):
    spine = [ir.get("idref") for ir in opf.find("opf:spine", NS)
             if ir.get("linear", "yes") != "no"]
    events, images = [], {}
    first_doc = True
    for idref in spine:
        if idref not in manifest:
            continue
        href, mt, props = manifest[idref]
        if "nav" in props and s.get("skip_contents"):
            continue
        if href not in names:
            continue
        soup = BeautifulSoup(z.read(href), "html.parser")
        body = soup.body or soup
        doc_events = []
        walk(body, doc_events, s.get("strip_gutenberg", True))
        if first_doc and s.get("skip_cover"):
            texty = [e for e in doc_events if e[0] != "image"]
            if not texty:
                first_doc = False
                continue
        first_doc = False
        ddir = posixpath.dirname(href)
        for e in doc_events:
            if e[0] == "image":
                src = posixpath.normpath(posixpath.join(ddir, e[1].split("#")[0]))
                if src in names and s.get("include_images"):
                    images[src] = z.read(src)
                events.append(("image", src))
            else:
                events.append(e)
    return events_to_book(events, s, meta, images)


def parse_html_file(path, s):
    raw = open(path, "rb").read()
    soup = BeautifulSoup(raw, "html.parser")
    events = []
    if s.get("keep_format"):
        import os
        import bf_keepfmt
        css = "\n".join(st.get_text() for st in soup.find_all("style"))
        for ln in soup.find_all("link", rel=lambda v: v and "stylesheet" in (v if isinstance(v, list) else [v])):
            cp = os.path.normpath(os.path.join(os.path.dirname(path), ln.get("href", "")))
            if os.path.isfile(cp):
                css += "\n" + open(cp, encoding="utf-8", errors="ignore").read()
        bf_keepfmt.set_current(bf_keepfmt.Context(bf_keepfmt.css_rules(css)))
    try:
        walk(soup.body or soup, events, s.get("strip_gutenberg", True))
    finally:
        if s.get("keep_format"):
            import bf_keepfmt
            bf_keepfmt.set_current(None)
    meta = {"title": (soup.title.get_text().strip() if soup.title else "")}
    h1 = soup.find("h1")
    h1t = " ".join(h1.get_text(" ").split()) if h1 else ""
    if h1t and meta["title"].startswith(h1t) and len(h1t) < len(meta["title"]):
        meta["title"] = h1t           # e.g. AO3: "<Title> - <Author> - <Fandom>" -> "<Title>"
    images = {}
    if s.get("include_images"):
        import os
        d = os.path.dirname(path)
        for e in events:
            if e[0] == "image":
                p = os.path.normpath(os.path.join(d, e[1]))
                if os.path.exists(p):
                    images[e[1]] = open(p, "rb").read()
    return events_to_book(events, s, meta, images)


def parse_docx(path, s):
    import docx
    from docx.oxml.ns import qn
    d = docx.Document(path)
    numbering = None
    try:
        numbering = d.part.numbering_part.element
    except Exception:
        pass

    def num_format(num_id, ilvl):
        if numbering is None:
            return None
        for num in numbering.findall(qn("w:num")):
            if num.get(qn("w:numId")) == str(num_id):
                an = num.find(qn("w:abstractNumId"))
                aid = an.get(qn("w:val")) if an is not None else None
                for ab in numbering.findall(qn("w:abstractNum")):
                    if ab.get(qn("w:abstractNumId")) == aid:
                        for lv in ab.findall(qn("w:lvl")):
                            if lv.get(qn("w:ilvl")) == str(ilvl):
                                nf = lv.find(qn("w:numFmt"))
                                return nf.get(qn("w:val")) if nf is not None else None
        return None

    def fmt_number(n, fmt):
        if fmt in ("lowerLetter", "upperLetter"):
            c = chr(ord("a") + (n - 1) % 26)
            return (c.upper() if fmt == "upperLetter" else c) + "."
        if fmt in ("lowerRoman", "upperRoman"):
            vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                    (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
            r, x = "", n
            for v, sym in vals:
                while x >= v:
                    r, x = r + sym, x - v
            return (r.lower() if fmt == "lowerRoman" else r) + "."
        return f"{n}."

    from docx.text.run import Run
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    W_R, W_HL = qn("w:r"), qn("w:hyperlink")
    # Wrappers whose runs are part of the text Word shows: tracked insertions and moves, smart tags,
    # custom XML, simple fields and content controls. Tracked deletions (w:del, w:moveFrom) are left out.
    W_INTO = {qn("w:ins"), qn("w:moveTo"), qn("w:smartTag"), qn("w:customXml"), qn("w:fldSimple"),
              qn("w:sdt"), qn("w:sdtContent")}
    R_EMBED, R_ID = qn("r:embed"), qn("r:id")
    pictures = {}

    def runs_of(p):
        """The paragraph's runs in order, including the words of links and tracked insertions
        (p.runs only has the runs directly in the paragraph)."""
        out = []

        def visit(el):
            for c in el:
                if c.tag == W_R:
                    out.append(Run(c, p))
                elif c.tag == W_HL or c.tag in W_INTO:
                    visit(c)
        visit(p._p)
        return out

    def run_pictures(r):
        """Pictures in a run, as event names (their bytes go in `pictures`)."""
        if not s.get("include_images"):
            return []
        names = []
        for el in r._r.iter():
            rid = el.get(R_EMBED) if el.tag == qn("a:blip") else el.get(R_ID) if el.tag.endswith("}imagedata") else None
            if not rid:
                continue
            try:
                part = d.part.related_parts[rid]
            except KeyError:
                continue
            name = posixpath.basename(str(part.partname)) or "picture"
            pictures.setdefault(name, part.blob)
            names.append(name)
        return names

    keep = bool(s.get("keep_format"))

    def chain(style, get):
        """A style's own value, else the value of the style it is based on (and so on)."""
        for _ in range(12):
            if style is None:
                return None
            try:
                v = get(style)
            except Exception:
                v = None
            if v is not None:
                return v
            style = style.base_style
        return None

    def defaults():
        face, size = "", None
        try:
            rpr = d.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
            rf, sz = rpr.find(qn("w:rFonts")), rpr.find(qn("w:sz"))
            face = (rf.get(qn("w:ascii")) or "") if rf is not None else ""
            size = int(sz.get(qn("w:val"))) / 2 if sz is not None else None
        except Exception:
            pass
        return face, size
    base_face, base_size = "", 11.0
    if keep:
        import bf_keepfmt
        try:
            normal = d.styles["Normal"]
        except KeyError:
            normal = None
        dface, dsize = defaults()
        base_face = chain(normal, lambda st: st.font.name) or dface or ""
        base_size = chain(normal, lambda st: st.font.size.pt if st.font.size else None) or dsize or 11.0

    def kept_font(r):
        """('<font ...>', '</font>') where this run looks different from the document's normal text."""
        try:
            para = r._parent if isinstance(getattr(r, "_parent", None), Paragraph) else None
            pstyle = para.style if para is not None else None
        except Exception:
            pstyle = None
        cstyle = None
        try:
            cstyle = r.style if r.style is not None and r.style.name != "Default Paragraph Font" else None
        except Exception:
            pass
        name = r.font.name or chain(cstyle, lambda st: st.font.name) or chain(pstyle, lambda st: st.font.name) \
            or base_face
        size = (r.font.size.pt if r.font.size else None) or chain(cstyle, lambda st: st.font.size.pt
                                                                  if st.font.size else None) or \
            chain(pstyle, lambda st: st.font.size.pt if st.font.size else None) or base_size
        col = ""
        try:
            if r.font.color is not None and r.font.color.type is not None and r.font.color.rgb is not None:
                col = bf_keepfmt.colour("#" + str(r.font.color.rgb))
        except Exception:
            col = ""
        face_kept = bf_keepfmt.usable_face(name) if name and name != base_face else ""
        return bf_keepfmt.font_open(face_kept, bf_keepfmt.pct(size, base_size), col)

    def para_fmt(p, item=False):
        """{'align', 'indent'} where this paragraph is laid out differently from normal text."""
        out = {}
        try:
            al = p.alignment if p.alignment is not None else chain(p.style, lambda st: st.paragraph_format.alignment)
            al = int(al) if al is not None else None
        except Exception:
            al = None
        if al == 1:
            out["align"] = "center"
        elif al == 2:
            out["align"] = "right"
        if not item:
            try:
                li = p.paragraph_format.left_indent
                if li is None:
                    li = chain(p.style, lambda st: st.paragraph_format.left_indent)
                n = bf_keepfmt.indent_steps(li.inches) if li is not None else 0
                if n:
                    out["indent"] = n
            except Exception:
                pass
        return out

    def styled(r):
        t = esc(r.text).replace("\n", "<br/>")
        if not t:
            return ""
        if keep:
            o, c = kept_font(r)
            t = o + t + c
        if r.font.strike or r.font.double_strike:
            t = f"<strike>{t}</strike>"
        if r.underline:
            t = f"<u>{t}</u>"
        if r.italic:
            t = f"<i>{t}</i>"
        if r.bold:
            t = f"<b>{t}</b>"
        return t

    def cell_text(tc):
        """A table cell's text: its paragraphs (and any table inside it) joined with spaces."""
        bits = []
        for c in tc:
            if c.tag == qn("w:p"):
                bits.append("".join(styled(r) for r in runs_of(Paragraph(c, None))))
            elif c.tag == qn("w:tbl"):
                for tr in c.iter(qn("w:tr")):
                    bits.extend(cell_text(x) for x in tr.findall(qn("w:tc")))
        return norm_ws(" ".join(b for b in bits if b))

    def body_items():
        """Paragraphs and tables in document order (d.paragraphs leaves the tables out)."""
        for c in d.element.body:
            if c.tag == qn("w:p"):
                yield Paragraph(c, d._body)
            elif c.tag == qn("w:tbl"):
                yield Table(c, d._body)

    counters = {}
    events = []
    for p in body_items():
        if isinstance(p, Table):
            # Like tables in web pages and EPUBs: each row becomes a line, cells separated by a wide space.
            for tr in p._tbl.iter(qn("w:tr")):
                if tr.getparent() is not p._tbl:
                    continue                      # rows of a table inside a cell go with that cell
                cells = [x for x in (cell_text(tc) for tc in tr.findall(qn("w:tc"))) if x]
                if cells:
                    events.append(("para", "\u2003".join(cells)))
            if s.get("include_images"):
                for r in p._tbl.iter(W_R):
                    events.extend(("image", n) for n in run_pictures(Run(r, None)))
            continue
        runs = runs_of(p)
        sty = (p.style.name or "").lower() if p.style is not None else ""
        if sty.startswith("heading") or sty == "title":
            lvl = 1 if sty == "title" else int(re.sub(r"\D", "", sty) or 1)
            text = "".join(r.text for r in runs).strip()
            if text:
                events.append(("head", lvl, text))
            for r in runs:
                events.extend(("image", n) for n in run_pictures(r))
            continue
        parts, pics = [], []          # pics: (where in parts the picture sits, picture name)
        for r in runs:
            pics.extend((len(parts), n) for n in run_pictures(r))
            t = styled(r)
            if t:
                parts.append(t)
        m = norm_ws("".join(parts))
        ppr = p._p.pPr
        numpr = ppr.numPr if ppr is not None else None
        is_item = numpr is not None and numpr.numId is not None and numpr.numId.val != 0 or "list" in sty
        if pics and not is_item:
            # Pictures in an ordinary paragraph: the text before each picture, the picture, the rest.
            cut = 0
            for pos, name in pics:
                seg = norm_ws("".join(parts[cut:pos]))
                if seg:
                    events.append(("para", seg))
                events.append(("image", name))
                cut = pos
            seg = norm_ws("".join(parts[cut:]))
            if seg:
                events.append(("para", seg))
            continue
        if not m:
            events.extend(("image", name) for _pos, name in pics)
            continue
        if is_item:
            num_id = numpr.numId.val if numpr is not None and numpr.numId is not None else sty
            ilvl = numpr.ilvl.val if numpr is not None and numpr.ilvl is not None else 0
            fmt = num_format(num_id, ilvl) if numpr is not None else (
                "decimal" if "number" in sty else "bullet")
            if fmt in (None, "bullet", "none"):
                bullet = BULLETS[ilvl % 3]
            else:
                key = (num_id, ilvl)
                counters[key] = counters.get(key, 0) + 1
                for k2 in [k for k in counters if k[0] == num_id and k[1] > ilvl]:
                    counters.pop(k2)
                bullet = fmt_number(counters[key], fmt)
            pf = para_fmt(p, item=True) if keep else {}
            events.append(("item", m, bullet, int(ilvl), pf) if pf else ("item", m, bullet, int(ilvl)))
            events.extend(("image", name) for _pos, name in pics)
        else:
            pf = para_fmt(p) if keep else {}
            events.append(("para", m, pf) if pf else ("para", m))
    cp = d.core_properties
    return events_to_book(events, s, {"title": cp.title or "", "author": cp.author or ""}, pictures)


# --------------------------------------------------------------------------
# Plain text / Markdown
# --------------------------------------------------------------------------
KEYWORD_RE = re.compile(r"^\s*(chapter|chap\.|part|book|section|prologue|epilogue|preface|"
                        r"introduction|foreword|afterword|interlude|canto|stave|act)\b", re.I)
NUM_RE = re.compile(r"^\s*([IVXLCDM]+|\d+)\.?\s*$")
SCENE_RE = re.compile(r"^\s*((\*\s*){3,}|#|~{3,}|-{3,}|_{3,}|(\u2022\s*){3,})\s*$")


MD_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(\S.*)$")
TXT_LIST_RE = re.compile(r"^(\s*)([\u2022\u25e6\u25aa\u2023\u00b7])\s+(\S.*)$")


def _md_inline(t):
    t = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", t)
    return t


def parse_text(text, s, is_md=False, meta=None):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    lines = text.split("\n")
    if s.get("strip_gutenberg"):
        st = next((i for i, l in enumerate(lines) if START_RE.search(l)), -1)
        lines = lines[st + 1:]
        en = next((i for i, l in enumerate(lines) if END_RE.search(l)), len(lines))
        lines = lines[:en]
    # "Rating:" on one line and its value on the next (copied AO3 work info) -> one line
    for i, l in enumerate(lines):
        if META_RE.match(l.strip()) and l.strip().endswith(":"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip() and not META_RE.match(lines[j].strip()):
                lines[i] = l.rstrip() + " " + lines[j].strip()
                lines[j] = ""
    n = len(lines)

    def standalone(i):
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i == n - 1 or not lines[i + 1].strip()
        return prev_blank and next_blank

    mode = s.get("split_mode", "Auto")
    md_heads = [i for i, l in enumerate(lines) if re.match(r"^#{1,6}\s+\S", l)]
    kw_heads = [i for i, l in enumerate(lines) if len(l.strip()) < 80 and
                (KEYWORD_RE.match(l) or NUM_RE.match(l)) and standalone(i) and not AO3_LABEL_RE.match(l)]
    # When the chapter lines are numbered ("Chapter 12: ..."), an un-numbered "Chapter ..." line
    # (e.g. "Chapter triggers!" in an author's note) is ordinary text, not a chapter.
    chap_lines = [i for i in kw_heads if re.match(r"^\s*chapter\b", lines[i], re.I)]
    numbered = [i for i in chap_lines if re.match(r"^\s*chapter\s+([ivxlcdm]+\b|\d+|" + NUM_WORDS + r"\b)",
                                                 lines[i], re.I)]
    if len(numbered) >= 2 and len(numbered) > len(chap_lines) / 2:
        kw_heads = [i for i in kw_heads if i not in chap_lines or i in numbered]
    caps_heads = [i for i, l in enumerate(lines) if 3 < len(l.strip()) <= 60 and standalone(i)
                  and l.strip() == l.strip().upper() and re.search(r"[A-Z]{3}", l)
                  and not l.strip().endswith(("!", "?", ",")) and not SCENE_RE.match(l)]
    custom = []
    if mode == "Custom pattern" and s.get("custom_regex"):
        rx = re.compile(s["custom_regex"], re.I)
        custom = [i for i, l in enumerate(lines) if rx.search(l)]

    if mode == "Markdown # headings" or (mode == "Auto" and md_heads and (is_md or len(md_heads) >= 2)):
        head_idx, kind = md_heads, "md"
    elif mode in ("Chapter / Part lines",) or (mode == "Auto" and len(kw_heads) >= 2):
        head_idx, kind = kw_heads, "kw"
    elif mode == "ALL-CAPS lines" or (mode == "Auto" and len(caps_heads) >= 2):
        head_idx, kind = caps_heads, "caps"
    elif mode == "Custom pattern":
        head_idx, kind = custom, "custom"
    else:
        head_idx, kind = [], "none"

    lp = s.get("line_paragraphs", "Auto")
    nonblank = sum(1 for l in lines if l.strip())
    blank = n - nonblank
    each_line = lp == "Each line is a paragraph" or (lp == "Auto" and nonblank > 20 and blank < nonblank * 0.08)

    events = []
    markers = scene_markers(s)
    head_set = set(head_idx)
    skip_next = set()
    para = []

    def flush():
        if para:
            if s.get("preserve_breaks"):
                m = "<br/>".join(p.strip() for p in para)
            else:
                m = " ".join(p.strip() for p in para)
            m = norm_ws(m)
            if m:
                events.append(("para", m))
            para.clear()

    has_ct = any(l.strip().lower() == "chapter text" for l in lines)
    note = {"open": False, "left": None}

    def close_note():
        if note["open"]:
            flush()
            events.append(("note_close",))
            note["open"], note["left"] = False, None

    seen_head = False
    for i, raw in enumerate(lines):
        if i in skip_next:
            continue
        l = raw.rstrip()
        st = l.strip()
        if st and standalone(i) and AO3_LABEL_RE.match(st) and kind != "md":
            close_note()
            flush()
            if st.lower() == "chapter text":
                continue                      # AO3 landmark: the story starts here
            lab = st.rstrip(":").strip()
            events.append(("note_open", "summary" if "summary" in lab.lower() else "notes"))
            events.append(("notelabel", lab))
            note["open"] = True
            starts_chapter = seen_head and not re.search(r"end", lab, re.I)
            note["left"] = 1 if (starts_chapter and not has_ct) else None
            continue
        if note["open"] and note["left"] is not None and not st and para:
            flush()
            note["left"] -= 1
            if note["left"] <= 0:
                close_note()
            continue
        if i in head_set:
            close_note()
            seen_head = seen_head or not FIC_FRONT_RE.match(st)
            flush()
            if kind == "md":
                mm = re.match(r"^(#{1,6})\s+(.*)$", l)
                events.append(("head", len(mm.group(1)), html.unescape(_md_inline(esc(mm.group(2).strip())))
                               .replace("<i>", "").replace("</i>", "").replace("<b>", "").replace("</b>", "")))
            else:
                lvl = 1
                if kind == "kw" and re.match(r"^\s*(part|book)\b", l, re.I) and \
                        any(re.match(r"^\s*chapter\b", lines[j], re.I) for j in head_idx):
                    lvl = 0
                title = l.strip()
                # "Chapter 1" + short title line underneath -> one heading
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                k2 = j + 1
                while k2 < n and not lines[k2].strip():
                    k2 += 1
                has_body = k2 < n and k2 not in head_set     # text must follow, or it isn't a title
                if kind == "kw" and LABEL_RE.match(title) and j < n and j not in head_set and has_body:
                    cand = lines[j].strip()
                    after_blank = j + 1 >= n or not lines[j + 1].strip()
                    if cand and len(cand) < 70 and after_blank and not cand.endswith((".", ",", ";")) \
                            or (cand and cand.isupper() and len(cand) < 70 and after_blank):
                        events.append(("head", 2 if lvl == 1 else 1, title))
                        events.append(("head", 2 if lvl == 1 else 1, cand))
                        skip_next.add(j)
                        continue
                events.append(("head", 2 if lvl == 1 else 1, title))
            continue
        if not l.strip():
            flush()
            continue
        if SCENE_RE.match(l) or is_scene(l, s, markers):
            flush()
            events.append(("scene", esc(l.strip())))
            continue
        lm = (MD_LIST_RE if is_md else TXT_LIST_RE).match(l)
        if lm:
            flush()
            ind = len(lm.group(1).expandtabs(4))
            depth = 0 if ind < 2 else (1 if ind < 6 else 2)
            mark = lm.group(2)
            bullet = BULLETS[depth % 3] if not mark[0].isdigit() else mark
            body = esc(lm.group(3))
            events.append(("item", norm_ws(_md_inline(body) if is_md else body), bullet, depth))
            continue
        t = esc(l)
        if is_md:
            t = _md_inline(t)
        if each_line:
            flush()
            para.append(t)
            flush()
        else:
            para.append(t)
    close_note()
    flush()
    s2 = dict(s)
    s2["_gut_cut_done"] = True
    if kind in ("kw", "caps", "custom"):
        s2["split_mode"] = "Auto"
    if kind == "none":
        s2["split_mode"] = "No chapters"
    return events_to_book(events, s2, meta or {})


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------
def load_book(s, paste_text="", log=None):
    import os
    log = log or (lambda m: None)
    if s.get("source_mode") == "paste":
        if not paste_text.strip():
            raise ValueError("The paste box is empty.")
        is_md = bool(re.search(r"^#{1,6}\s", paste_text, re.M))
        book = parse_text(paste_text, s, is_md=is_md)
    else:
        p = s.get("source_path", "")
        if not p or not os.path.exists(p):
            raise ValueError("Choose a source file first.")
        ext = os.path.splitext(p)[1].lower()
        if ext == ".epub":
            book = parse_epub(p, s)
        elif ext in (".html", ".htm", ".xhtml"):
            book = parse_html_file(p, s)
        elif ext == ".docx":
            book = parse_docx(p, s)
        elif ext == ".pdf":
            import bf_pdfin
            if s.get("pdf_mode", PDF_MODES[0]) != PDF_MODES[1]:
                meta = bf_pdfin.pdf_meta(p)          # the pages are printed as they are
                book = Book(title=meta["title"], author=meta["author"], fixed_pdf=os.path.abspath(p),
                            fixed_pages=meta["pages"])
            else:
                events, meta, images = bf_pdfin.pdf_events(p, s, log)
                book = events_to_book(events, s, meta, images)
        else:
            raw = open(p, "rb").read()
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    txt = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            book = parse_text(txt, s, is_md=ext in (".md", ".markdown"),
                              meta={"title": os.path.splitext(os.path.basename(p))[0]})
    return book


def apply_info(book, s):
    """User-entered book info overrides what the source said."""
    for k in ("title", "subtitle", "author", "credit"):
        v = (s.get(k) or "").strip()
        if v:
            setattr(book, k, v)
    if not book.title:
        book.title = "Untitled"
    return book


def safe_name(t):
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", t).strip().rstrip(".")
    return t[:80] or "Book"


def source_file(s):
    """The file the book is read from ('' for pasted text or a source that isn't there)."""
    if s.get("source_mode", "file") != "file":
        return ""
    p = (s.get("source_path") or "").strip()
    return p if p and os.path.isfile(p) else ""


def _same_file(a, b):
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def not_the_source(path, s):
    """Where to write a file BookForge makes: path itself, or - when path is the book's own source file (the
    source kept in the book's output folder under the name BookForge gives that file, e.g. "My Book.txt", or
    BookForge's "My Book - Print.pdf" used again as a source) - the same name with " (BookForge)" added, so
    making the book never overwrites the file it was read from."""
    src = source_file(s)
    if not src or not _same_file(path, src):
        return path
    root, ext = os.path.splitext(path)
    alt, n = f"{root} (BookForge){ext}", 2
    while _same_file(alt, src):                      # (only if the source itself has that name)
        alt, n = f"{root} (BookForge {n}){ext}", n + 1
    return alt
