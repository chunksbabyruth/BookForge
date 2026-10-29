"""BookForge front & back matter: the pages around the chapters as editable sections.

Every section is "automatic" until it is edited: its content is then made from the settings and the source exactly
as before (so books and projects from before 1.8.0 print the same). Editing a section in Specific Text Edit stores
its content as Blocks - the same model chapters use, with the same formatting markup - in Book.matter:

    book.matter[key] = {"blocks": [Block, ...] or None, "title": heading or None}

The PDF, the preview and the EPUB / Word / web page / text exports all get a section's content from here
(section_blocks / section_heading), so an edit reaches every output. No window code here.

Which text is the "source of truth":
- Title page lines: the words are the Book info fields (title, subtitle, author, credit - also used for the
  cover, e-book details, running heads and file names); an edited title page keeps its formatting, lines and
  order, and always shows the current words. Editing a line in the editor changes the Book info field.
- Bookplate: the words are the "Bookplate wording" setting, the same way.
- Dedication, extra front page, back-cover blurb: the edited section; its plain text is kept in the old settings
  (dedication, note_text, blurb) so presets, older versions and anything reading the settings see the same words.
- Work info, summary, author's notes, text before chapter 1, contents: the edit is kept beside what was read from
  the source (Book.fic_meta, fic_summary, fic_notes, front_blocks, toc are never changed by it).
"""
import copy
import dataclasses
import re

from bf_core import Block, esc, plain

# key: (list name, "front"/"back", default heading (None = the section has no heading), editor styles,
#       pictures allowed, comes from the source (lost when the source is read again))
SECTIONS = {
    "title": ("Title page", "front", None, ["btitle", "bsub", "bauth", "bcred", "para"], False, False),
    "bookplate": ("Bookplate", "front", None, ["plate", "para"], False, False),
    "dedication": ("Dedication", "front", None, ["ded", "para", "head"], False, False),
    "note": ("Extra front page", "front", "", ["para", "flush", "head", "quote", "item", "verse", "scene", "anote"],
             True, False),
    "work_info": ("Work info", "front", "Work Info", ["meta", "flush", "head"], False, True),
    "summary": ("Summary", "front", "Summary", ["flush", "para", "head", "quote", "item"], False, True),
    "work_notes": ("Author's notes (whole work)", "front", "Notes", ["flush", "para", "head", "quote", "item"],
                   False, True),
    "contents": ("Contents", "front", None, ["tocentry"], False, True),
    "front_text": ("Text before chapter 1", "front", None,
                   ["para", "flush", "head", "subtitle", "quote", "item", "verse", "scene", "anote"], True, True),
    "the_end": ("THE END", "back", None, ["endline", "para"], False, False),
    "end_matter": ("End pages (afterword, notes...)", "back", "",
                   ["para", "flush", "head", "subtitle", "quote", "item", "verse", "scene", "anote"], True, False),
    "notes_page": ("Notes pages", "back", "Notes", ["flush", "para"], False, False),
    "blurb": ("Back-cover blurb", "back", None, ["para"], False, False),
}
FRONT = [k for k, v in SECTIONS.items() if v[1] == "front"]
BACK = [k for k, v in SECTIONS.items() if v[1] == "back"]
USER_KEYS = [k for k, v in SECTIONS.items() if not v[5]]       # kept when the source is read again
TITLE_LINES = (("btitle", "title"), ("bsub", "subtitle"), ("bauth", "author"), ("bcred", "credit"))


# --------------------------------------------------------------------------- stored edits
def _store(book):
    m = getattr(book, "matter", None)
    if m is None:
        m = {}
        try:
            book.matter = m
        except AttributeError:
            pass
    return m


def override(book, key):
    """The edited content of a section (a list of Blocks), or None while it is automatic."""
    e = (getattr(book, "matter", None) or {}).get(key) or {}
    b = e.get("blocks")
    return list(b) if b is not None else None


def heading_override(book, key):
    e = (getattr(book, "matter", None) or {}).get(key) or {}
    return e.get("title")


def set_override(book, key, blocks):
    _store(book).setdefault(key, {})["blocks"] = [copy.copy(b) for b in blocks]


def set_heading(book, key, text):
    _store(book).setdefault(key, {})["title"] = text


def clear(book, key):
    """Back to automatic (the edited content and heading are forgotten)."""
    m = getattr(book, "matter", None) or {}
    m.pop(key, None)


def is_edited(book, key):
    e = (getattr(book, "matter", None) or {}).get(key) or {}
    return e.get("blocks") is not None or e.get("title") is not None


def user_pages(book):
    """A copy of the user's own pages (title page, dedication, end pages...: not read from the source)."""
    m = (getattr(book, "matter", None) or {}) if book is not None else {}
    return {k: copy.deepcopy(m[k]) for k in USER_KEYS if m.get(k)}


def restore_user_pages(book, pages):
    """Give a book read again from the source the user's own pages back (see user_pages)."""
    if book is None:
        return
    m = _store(book)
    for k, e in (pages or {}).items():
        if k not in m:                 # (already given back)
            m[k] = copy.deepcopy(e)


def carry_over(old, new):
    """The source was read again: keep the user's own pages (title page, dedication, end pages...)."""
    restore_user_pages(new, user_pages(old))


def source_edits(book):
    """The names of the edited pages that come from the source (reading the source again replaces them)."""
    return [SECTIONS[k][0] for k in SECTIONS if SECTIONS[k][5] and k != "contents" and is_edited(book, k)]


# --------------------------------------------------------------------------- content
def _paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]


def restyle(markup, words):
    """markup's look (its first run's fonts, bold...) with other words (markup itself when they are its words)."""
    from bf_edit import parse_markup, runs_to_markup
    if " ".join(plain(markup or "").split()) == " ".join((words or "").split()):
        return markup
    runs = parse_markup(markup)
    fmt = runs[0][1] if runs else {}
    return runs_to_markup([(words, fmt)])


def _synced(blocks, values):
    """Edited lines whose words come from fields (title page, bookplate): each first line of a kind shows the
    field's current words, keeping its formatting; a line whose field is now empty is left out."""
    out, seen = [], set()
    for b in blocks:
        if b.kind in values and b.kind not in seen:
            seen.add(b.kind)
            words = (values[b.kind] or "").strip()
            if not words:
                continue
            if plain(b.text).strip() != words:
                b = dataclasses.replace(b, text=restyle(b.text, words))
        out.append(b)
    return out


def auto_blocks(book, s, key):
    """A section's content as BookForge makes it when it hasn't been edited (what earlier versions printed)."""
    if key == "title":
        out = [Block("btitle", esc(book.title or ""))]
        for kind, field in TITLE_LINES[1:]:
            if getattr(book, field, ""):
                out.append(Block(kind, esc(getattr(book, field))))
        return out
    if key == "bookplate":
        return [Block("plate", esc(s.get("bookplate_text") or ""))]
    if key == "dedication":
        return [Block("ded", esc(p).replace("\n", "<br/>")) for p in _paras(s.get("dedication"))]
    if key == "note":
        return [Block("para", esc(" ".join(p.split()))) for p in _paras(s.get("note_text"))]
    if key == "work_info":
        return [Block("meta", m) for m in book.fic_meta]
    if key == "summary":
        return [Block("flush", b.text) for b in book.fic_summary]
    if key == "work_notes":
        return [Block("flush", b.text) for b in book.fic_notes]
    if key == "front_text":
        return [copy.copy(b) for b in book.front_blocks if b.kind == "para"]
    if key == "the_end":
        return [Block("endline", "THE END")]
    if key == "blurb":
        return [Block("para", esc(" ".join(p.split()))) for p in _paras(s.get("blurb"))]
    return []                       # end_matter, notes_page: nothing until something is written


def section_blocks(book, s, key):
    """What a section holds now: its edited content (title page and bookplate showing the current words), or
    the automatic content."""
    ov = override(book, key)
    if ov is None:
        return auto_blocks(book, s, key)
    if key == "title":
        return _synced(ov, {k: getattr(book, f, "") for k, f in TITLE_LINES})
    if key == "bookplate":
        return _synced(ov, {"plate": s.get("bookplate_text") or ""})
    return ov


def section_heading(book, s, key):
    """The heading printed above a section ('' = none)."""
    if key == "note":
        return (s.get("note_title") or "").strip()
    if key == "contents":
        return s.get("toc_title") or ""
    if SECTIONS[key][2] is None:
        return ""
    h = heading_override(book, key)
    if h is not None:
        return h
    if key == "summary" and book.fic_summary:
        return book.fic_summary[0].label or "Summary"
    if key == "work_notes" and book.fic_notes:
        return book.fic_notes[0].label or "Notes"
    return SECTIONS[key][2]


def has_text(blocks):
    for b in blocks or []:
        if b.kind == "image" and b.image:
            return True
        if b.kind == "verse" and any(plain(x).strip() for x in b.lines or []):
            return True
        if b.kind not in ("image", "verse") and plain(b.text or "").strip():
            return True
    return False


def plain_text(blocks):
    """The words of a section as plain paragraphs separated by blank lines (for the old settings)."""
    out = []
    for b in blocks or []:
        if b.kind == "verse":
            out.append("\n".join(plain(x) for x in b.lines))
        elif b.kind != "image":
            t = plain((b.text or "").replace("<br/>", "\n"))
            if t.strip():
                out.append(t.strip())
    return "\n\n".join(out)
