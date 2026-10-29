"""BookForge editing: book paragraphs <-> editable formatted text, project files, fonts for the editor.

There is no window code here, so everything can be tested on any machine. The Edit step in BookForge.py
shows the paragraphs of one chapter in a text box; this module converts between that and the book model
(chapters made of Blocks whose text is markup such as "<i>word</i>") that the preview and every output use.
"""
import base64
import dataclasses
import html
import json
import os
import tempfile
from html.parser import HTMLParser

from bf_core import Book, Chapter, Block, esc, plain

# paragraph styles offered in the editor (Block kinds)
STYLES = [("para", "Normal text"), ("head", "Heading"), ("subtitle", "Chapter subtitle"),
          ("quote", "Quotation"), ("item", "List item"), ("verse", "Poetry line"),
          ("scene", "Section break"), ("anote", "Author's note"), ("image", "Picture")]
# styles of the front & back pages (bf_matter): offered in the editor only for the pages they belong to
MATTER_STYLES = [("btitle", "Book title"), ("bsub", "Book subtitle"), ("bauth", "Author line"),
                 ("bcred", "Credit line"), ("plate", "Bookplate line"), ("ded", "Dedication"),
                 ("meta", "Work info line"), ("flush", "Text, no indent"), ("endline", "Closing line"),
                 ("tocentry", "Contents entry")]
STYLE_NAMES = dict(STYLES + MATTER_STYLES)
FLAGS = ("b", "i", "u", "s", "sup", "sub")                 # character formatting the editor can toggle
_TAGS = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "s": "s", "strike": "s", "del": "s",
         "super": "sup", "sup": "sup", "sub": "sub"}
_OUT = {"b": "b", "i": "i", "u": "u", "s": "strike", "sup": "super", "sub": "sub"}
BR = "\u21b5"                                             # a line break inside a paragraph (shown as the ↵ sign)
PROJECT_FORMAT = 1


# --------------------------------------------------------------------------- markup <-> runs
class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs, self.stack = [], []

    def _fmt(self):
        f = {}
        for kind, v in self.stack:
            if kind == "t":
                f[v] = True
            elif kind == "f":
                face, size, color = v
                if face:
                    f["font"] = face
                if size:
                    f["size"] = size
                if color:
                    f["color"] = color
        return f

    def handle_starttag(self, tag, attrs):
        tag, a = tag.lower(), dict(attrs)
        if tag == "br":
            self.runs.append((BR, self._fmt()))
        elif tag in _TAGS:
            self.stack.append(("t", _TAGS[tag]))
        elif tag == "font":
            self.stack.append(("f", (a.get("face") or a.get("name"), a.get("size"), a.get("color"))))
        else:
            self.stack.append(("x", tag))                  # other tags: keep the text, drop the tag

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.runs.append((BR, self._fmt()))

    def handle_endtag(self, tag):
        tag = tag.lower()
        want = ("t", _TAGS[tag]) if tag in _TAGS else ("f", None) if tag == "font" else ("x", tag)
        for i in range(len(self.stack) - 1, -1, -1):
            k, v = self.stack[i]
            if k == want[0] and (k == "f" or v == want[1]):
                del self.stack[i]
                break

    def handle_data(self, d):
        if d:
            self.runs.append((d, self._fmt()))


def parse_markup(markup):
    """Markup -> [(text, {"b": True, "font": "EB Garamond", "size": "14", ...}), ...]."""
    p = _Parser()
    p.feed(markup or "")
    p.close()
    return merge(p.runs)


def merge(runs):
    out = []
    for text, f in runs:
        if not text:
            continue
        if out and out[-1][1] == f:
            out[-1] = (out[-1][0] + text, f)
        else:
            out.append((text, dict(f)))
    return out


def runs_to_markup(runs):
    """[(text, fmt), ...] -> markup understood by the typesetter and every export."""
    out = []
    for text, f in merge(runs):
        body = esc(text).replace(BR, "<br/>")
        opening, closing = "", ""
        attrs = "".join(f' {k}="{html.escape(str(f[n]), quote=True)}"'
                        for k, n in (("face", "font"), ("size", "size"), ("color", "color")) if f.get(n))
        if attrs:
            opening, closing = f"<font{attrs}>", "</font>"
        for flag in FLAGS:
            if f.get(flag):
                opening += f"<{_OUT[flag]}>"
                closing = f"</{_OUT[flag]}>" + closing
        out.append(opening + body + closing)
    return "".join(out)


# --------------------------------------------------------------------------- blocks <-> paragraphs
@dataclasses.dataclass
class Para:
    style: str
    runs: list
    align: str = ""
    indent: int = 0
    space: int = 0
    label: str = ""          # author's-note heading ("Chapter Notes" ...)
    bullet: str = ""
    depth: int = 0
    group: int = None        # poetry lines from the same poem
    block: object = None     # the original Block (pictures and section breaks keep it)


def blocks_to_paras(blocks):
    paras = []
    for gi, b in enumerate(blocks):
        common = dict(align=b.align, indent=b.indent, space=b.space, label=b.label, bullet=b.bullet,
                      depth=b.depth, block=b)
        if b.kind == "verse":
            for line in (b.lines or [""]):
                paras.append(Para("verse", parse_markup(line), group=gi, **common))
        elif b.kind == "image":
            paras.append(Para("image", [(picture_label(b), {})], **common))
        elif b.kind == "scene":
            paras.append(Para("scene", [(plain(b.text) or "* * *", {})], **common))
        else:
            kind = b.kind if b.kind in STYLE_NAMES else "para"
            paras.append(Para(kind, parse_markup(b.text), **common))
    return paras


def picture_label(b):
    """How a picture shows in the editor's text, e.g. "[picture: map.png · 60% wide · on its own page]"."""
    bits = [b.image_name or "picture"]
    if getattr(b, "img_width", 0) and getattr(b, "img_place", "") != "full":
        bits.append(f"{int(b.img_width)}% wide")
    place = {"page": "on its own page", "full": "full page, edge to edge"}.get(getattr(b, "img_place", ""))
    if place:
        bits.append(place)
    return "[picture: " + " · ".join(bits) + "]"


def paras_to_blocks(paras):
    """Editor paragraphs -> Blocks. Empty text paragraphs are dropped; pictures keep their original image."""
    blocks, i = [], 0
    while i < len(paras):
        p = paras[i]
        fmt = dict(align=p.align, indent=p.indent, space=p.space)
        if p.style == "verse":
            lines = []
            while i < len(paras) and paras[i].style == "verse" and paras[i].group == p.group:
                lines.append(runs_to_markup(paras[i].runs))
                i += 1
            while lines and not plain(lines[-1]).strip():
                lines.pop()
            if lines:
                blocks.append(Block("verse", lines=lines, **fmt))
            continue
        i += 1
        text = "".join(t for t, _f in p.runs)
        if p.style == "image":
            if p.block is not None and p.block.kind == "image":
                b = dataclasses.replace(p.block, **fmt)
                blocks.append(b)
            continue
        if p.style == "scene":
            orig = p.block if (p.block is not None and p.block.kind == "scene") else None
            keep = orig is not None and (plain(orig.text).strip() or "* * *") == text.strip()
            blocks.append(Block("scene", text=orig.text if keep else esc(text.strip()), **fmt))
            continue
        if not text.replace(BR, "").strip():
            continue
        kind = p.style if p.style in STYLE_NAMES else "para"
        b = Block(kind, text=runs_to_markup(p.runs), **fmt)
        if kind == "anote":
            b.label = p.label
        if kind == "item":
            b.bullet, b.depth = (p.bullet or "\u2022"), p.depth
        blocks.append(b)
    return blocks


# --------------------------------------------------------------------------- project files
_TYPES = {"Book": Book, "Chapter": Chapter, "Block": Block}


def _enc(o):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        d = {"__type__": type(o).__name__}
        d.update({f.name: _enc(getattr(o, f.name)) for f in dataclasses.fields(o)})
        return d
    if isinstance(o, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(o)).decode("ascii")}
    if isinstance(o, (list, tuple)):
        return [_enc(x) for x in o]
    if isinstance(o, dict):
        return {str(k): _enc(v) for k, v in o.items()}
    return o


def _dec(o):
    if isinstance(o, list):
        return [_dec(x) for x in o]
    if isinstance(o, dict):
        if "__b64__" in o:
            return base64.b64decode(o["__b64__"])
        if "__type__" in o:
            cls = _TYPES[o["__type__"]]
            names = {f.name for f in dataclasses.fields(cls)}
            return cls(**{k: _dec(v) for k, v in o.items() if k in names})
        return {k: _dec(v) for k, v in o.items()}
    return o


def save_project(path, book, settings, app_version):
    """Write a .bookforge project (book with all edits + settings). Written to a temporary file first,
    so a failed save never destroys an earlier project file."""
    data = {"bookforge_project": PROJECT_FORMAT, "app_version": app_version,
            "settings": settings, "book": _enc(book)}
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".bookforge_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_project(path):
    """Read a .bookforge project. Returns (book, settings); raises ValueError with a plain message."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"the file can't be read ({e})") from e
    if not isinstance(data, dict) or data.get("bookforge_project") is None:
        raise ValueError("it isn't a BookForge project file")
    if int(data["bookforge_project"]) > PROJECT_FORMAT:
        raise ValueError("it was saved by a newer BookForge - please update BookForge to open it")
    try:
        book = _dec(data["book"])
        assert isinstance(book, Book)
    except Exception as e:
        raise ValueError(f"the book inside it is damaged ({type(e).__name__})") from e
    return book, dict(data.get("settings") or {})


# --------------------------------------------------------------------------- fonts for the editor display
_LOADED = set()


def load_fonts_for_editor(paths):
    """On Windows, make font files usable by the editor's text box for this session only (nothing is
    installed). Returns how many were added. Elsewhere the editor shows a similar font instead."""
    if os.name != "nt":
        return 0
    import ctypes
    added = 0
    for p in paths:
        if p in _LOADED or not os.path.isfile(p):
            continue
        try:
            if ctypes.windll.gdi32.AddFontResourceExW(p, 0x10, 0):      # 0x10 = FR_PRIVATE
                _LOADED.add(p)
                added += 1
        except Exception:
            pass
    return added
