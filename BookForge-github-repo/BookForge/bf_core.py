"""BookForge core: book model, defaults, and source parsers.

Text is kept verbatim. Only whitespace that exists purely for source-file
line wrapping is normalised; italics/bold/superscripts and line breaks are
carried through as a tiny markup subset: <i> <b> <super> <sub> <br/>.
"""
import html
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag, Comment

APP_NAME = "BookForge"
APP_VERSION = "1.2"
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
    # Book info
    "title": "", "subtitle": "", "author": "", "credit": "",
    # Layout
    "page_size": "Letter (8.5 x 11 in)", "custom_w": 6.0, "custom_h": 9.0,
    "margin_top": 0.85, "margin_bottom": 0.85, "margin_inner": 1.0,
    "margin_outer": 1.0, "font_family": "Times (built-in)",
    "custom_font_path": "", "body_size": 13.0, "line_spacing": 1.38,
    "align": "Justified", "indent": 0.25, "para_space": 6.0,
    "first_para_indent": True, "title_size": 23.0, "sub_size": 14.5,
    "chapter_label": "None", "title_case": "As written",
    "chapter_start": "New page", "chapter_sink": 0.0, "ornament": False,
    "drop_cap": False, "scene_break": "* * *", "verse_style": "Centered italic",
    "pn_position": "Bottom center", "pn_style": "Rule above",
    "pn_mode": "Every page (title page = 1)", "pn_hide_openers": False,
    "pn_hide_blank": True, "pn_hide_title": False, "running_heads": False,
    # Front & back matter
    "title_page": True, "bookplate": "On title page",
    "bookplate_text": "This Book Belongs To", "dedication": "", "toc": True,
    "toc_title": "CONTENTS", "toc_dots": False, "toc_numbers": "None",
    "toc_case": "Title Case", "note_title": "", "note_text": "",
    "note_place": "After contents", "the_end": False, "notes_pages": 0,
    # Output
    "out_dir": "", "fmt_pdf": True, "fmt_impose": True, "fmt_cover": False,
    "fmt_epub": False, "fmt_docx": False, "fmt_html": False, "fmt_txt": False,
    "sheet_size": "Letter", "sig_sheets": 8, "fold_marks": True,
    "sig_marks": True, "rotate_back": False,
    "paper": "20 lb / 75 gsm (0.0040 in)", "blurb": "", "open_when_done": True,
}

PAGE_SIZES = {
    "Letter (8.5 x 11 in)": (8.5, 11.0),
    "Half Letter / Digest (5.5 x 8.5 in)": (5.5, 8.5),
    "Trade Paperback (6 x 9 in)": (6.0, 9.0),
    "Paperback (5 x 8 in)": (5.0, 8.0),
    "Mass Market (4.25 x 6.87 in)": (4.25, 6.87),
    "A4 (8.27 x 11.69 in)": (8.27, 11.69),
    "A5 (5.83 x 8.27 in)": (5.83, 8.27),
    "Legal (8.5 x 14 in)": (8.5, 14.0),
    "Custom": None,
}
SHEET_SIZES = {"Letter": (11.0, 8.5), "Legal": (14.0, 8.5),
               "Tabloid / 11x17": (17.0, 11.0), "A4": (11.69, 8.27)}
PAPERS = {"20 lb / 75 gsm (0.0040 in)": 0.0040,
          "24 lb / 90 gsm (0.0045 in)": 0.0045,
          "28 lb / 105 gsm (0.0050 in)": 0.0050,
          "32 lb / 120 gsm (0.0055 in)": 0.0055}


def page_size_inches(s):
    v = PAGE_SIZES.get(s["page_size"])
    if v is None:
        return float(s["custom_w"]), float(s["custom_h"])
    return v


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


@dataclass
class Chapter:
    title: str
    label: str = ""      # e.g. "CHAPTER I" when the source splits label/title
    level: int = 1       # 0 = part, 1 = chapter
    blocks: list = field(default_factory=list)
    include: bool = True

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
        m = re.sub(r"<(i|b|super|sub)>\s*</\1>", "", m)
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
        if n == "br":
            out.append("<br/>")
        elif n == "a" and _is_noteref(c):
            out.append("<super>" + inline_markup(c) + "</super>")
        elif n in ITAL or (n == "span" and ("ital" in _classes(c) or
                           "italic" in (c.get("style") or "").lower())):
            out.append("<i>" + inline_markup(c) + "</i>")
        elif n in BOLD or (n == "span" and "bold" in _classes(c)):
            out.append("<b>" + inline_markup(c) + "</b>")
        elif n == "sup":
            out.append("<super>" + inline_markup(c) + "</super>")
        elif n == "sub":
            out.append("<sub>" + inline_markup(c) + "</sub>")
        else:
            out.append(inline_markup(c))
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


def walk(node, out, strip_pg):
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
                    walk(ch, out, strip_pg)
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
            if m:
                out.append(("para", m))
            for im in c.find_all("img"):
                out.append(("image", im.get("src", "")))
        elif n == "hr":
            out.append(("scene",))
        elif n == "blockquote":
            sub = []
            walk(c, sub, strip_pg)
            for ev in sub:
                out.append(("quote", ev[1]) if ev[0] == "para" else ev)
        elif n in ("ul", "ol"):
            for i, li in enumerate(c.find_all("li", recursive=False), 1):
                sub = []
                walk(li, sub, strip_pg)
                prefix = "\u2022 " if n == "ul" else f"{i}. "
                if sub and sub[0][0] == "para":
                    sub[0] = ("para", prefix + sub[0][1])
                elif sub:
                    sub.insert(0, ("para", prefix.strip()))
                out.extend(sub)
        elif n == "table":
            for tr in c.find_all("tr"):
                cells = [norm_ws(inline_markup(td)) for td in tr.find_all(["td", "th"])]
                cells = [x for x in cells if x]
                if cells:
                    out.append(("para", "\u2003".join(cells)))
        else:
            walk(c, out, strip_pg)
    flush()


# --------------------------------------------------------------------------
# Events -> Book
# --------------------------------------------------------------------------
START_RE = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", re.I)
END_RE = re.compile(r"(\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG|"
                    r"^\s*End of (the )?Project Gutenberg|FULL PROJECT GUTENBERG LICEN[CS]E)", re.I)
BYLINE_RE = re.compile(r"^\s*((translated|illustrated|edited|written|retold)\s+)?by\s", re.I)
CONTENTS_RE = re.compile(r"^\s*(table of )?contents\.?\s*$|^\s*list of (illustrations|plates)\.?\s*$", re.I)
LABEL_RE = re.compile(r"^\s*((chapter|chap\.|part|book|section|canto|letter|stave|act)\s+"
                      r"([ivxlcdm]+|\d+|[a-z\-]+)\.?|[ivxlcdm]+\.?|\d+\.?)\s*$", re.I)


def _ev_text(ev):
    if ev[0] == "head":
        return ev[2]
    if ev[0] in ("para", "quote", "subtitle"):
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


def events_to_book(events, s, meta=None, images=None):
    meta = meta or {}
    images = images or {}
    if s.get("strip_gutenberg"):
        events = cut_gutenberg(events)
    heads = [e for e in events if e[0] == "head"]
    counts = {}
    for e in heads:
        counts[e[1]] = counts.get(e[1], 0) + 1
    mode = s.get("split_mode", "Auto")
    part_level = None
    if mode.startswith("Heading level"):
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
    cur = None
    pending_label = None

    def add_block(b):
        if cur is None:
            book.front_blocks.append(b)
        else:
            cur.blocks.append(b)

    for ev in events:
        k = ev[0]
        if k == "head" and chap_level is not None and (ev[1] == chap_level or ev[1] == part_level):
            text = ev[2].strip()
            lvl = 0 if ev[1] == part_level else 1
            if cur is not None and not cur.blocks and cur.level == lvl and \
                    LABEL_RE.match(cur.title) and not cur.label and not LABEL_RE.match(text):
                cur.label, cur.title = cur.title, text
                continue
            cur = Chapter(title=text, level=lvl)
            book.chapters.append(cur)
            continue
        if k == "head":
            if chap_level is not None and ev[1] < chap_level and cur is None:
                continue          # book title etc. before first chapter
            add_block(Block("head", esc(ev[2])))
        elif k == "para":
            add_block(Block("para", ev[1]))
        elif k == "quote":
            add_block(Block("quote", ev[1]))
        elif k == "subtitle":
            add_block(Block("subtitle", ev[1]) if cur is not None and not cur.blocks
                      else Block("para", ev[1]))
        elif k == "verse":
            add_block(Block("verse", lines=ev[1]))
        elif k == "scene":
            add_block(Block("scene"))
        elif k == "image":
            if s.get("include_images") and ev[1] in images:
                add_block(Block("image", image=images[ev[1]], image_name=ev[1]))

    if not book.chapters:
        ch = Chapter(title=book.title or "Untitled", blocks=book.front_blocks)
        book.chapters = [ch]
        book.front_blocks = []
    # clean up
    out = []
    seen_real = False
    for ch in book.chapters:
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
    walk(soup.body or soup, events, s.get("strip_gutenberg", True))
    meta = {"title": (soup.title.get_text().strip() if soup.title else "")}
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
    d = docx.Document(path)
    events = []
    for p in d.paragraphs:
        sty = (p.style.name or "").lower() if p.style is not None else ""
        if sty.startswith("heading") or sty == "title":
            lvl = 1 if sty == "title" else int(re.sub(r"\D", "", sty) or 1)
            if p.text.strip():
                events.append(("head", lvl, p.text.strip()))
            continue
        parts = []
        for r in p.runs:
            t = esc(r.text).replace("\n", "<br/>")
            if not t:
                continue
            if r.italic:
                t = f"<i>{t}</i>"
            if r.bold:
                t = f"<b>{t}</b>"
            parts.append(t)
        m = norm_ws("".join(parts))
        if m:
            events.append(("para", m))
    cp = d.core_properties
    return events_to_book(events, s, {"title": cp.title or "", "author": cp.author or ""})


# --------------------------------------------------------------------------
# Plain text / Markdown
# --------------------------------------------------------------------------
KEYWORD_RE = re.compile(r"^\s*(chapter|chap\.|part|book|section|prologue|epilogue|preface|"
                        r"introduction|foreword|afterword|interlude|canto|stave|act)\b", re.I)
NUM_RE = re.compile(r"^\s*([IVXLCDM]+|\d+)\.?\s*$")
SCENE_RE = re.compile(r"^\s*((\*\s*){3,}|#|~{3,}|-{3,}|_{3,}|(\u2022\s*){3,})\s*$")


def _md_inline(t):
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
    n = len(lines)

    def standalone(i):
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i == n - 1 or not lines[i + 1].strip()
        return prev_blank and next_blank

    mode = s.get("split_mode", "Auto")
    md_heads = [i for i, l in enumerate(lines) if re.match(r"^#{1,6}\s+\S", l)]
    kw_heads = [i for i, l in enumerate(lines) if len(l.strip()) < 80 and
                (KEYWORD_RE.match(l) or NUM_RE.match(l)) and standalone(i)]
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

    for i, raw in enumerate(lines):
        if i in skip_next:
            continue
        l = raw.rstrip()
        if i in head_set:
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
                if kind == "kw" and LABEL_RE.match(title) and j < n and j not in head_set:
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
        if SCENE_RE.match(l):
            flush()
            events.append(("scene",))
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
    flush()
    s2 = dict(s)
    s2["strip_gutenberg"] = False
    if kind in ("kw", "caps", "custom"):
        s2["split_mode"] = "Auto"
    if kind == "none":
        s2["split_mode"] = "No chapters"
    return events_to_book(events, s2, meta or {})


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------
def load_book(s, paste_text=""):
    import os
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
