"""Checks for the core reliability fixes in 1.8.0 (plain Python - run: python tests/test_regressions_180.py).

1. Pictures in Specific Text Edit stay pictures: typing, Backspace/Delete, Enter, styles, find & replace, cut and
   paste, picture settings, replace/remove, switching chapters/tabs, preview, build and projects keep the
   picture's own bytes, settings and place.
2. Source and book: Re-read source, edits never replaced without asking, a failed read keeps the book, an open
   preview never keeps showing pages that aren't the current result.
3. Nothing to print: an empty book is refused with a message (preview and build), never made silently.
4. Titles & headings font: every title element follows it in the PDF (font resources checked), body independent,
   "Same as body text", bold on/off, included / installed / custom fonts; preview = final Print PDF; an open
   preview is marked out of date when a setting changes; settings and projects keep the choice.
5. Edit contents page numbers: typed numbers (28 chapters: 1-14 -> 2, 15-28 -> 3) reach the preview and the
   Print PDF even while the window is still open, survive save/reopen, and clearing one goes back to automatic.
Sections 1-5 run their window checks only where a display is available. Nothing needs the internet.
"""
import io
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_180_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import collections                                                    # noqa: E402
import dataclasses                                                    # noqa: E402

import pdfplumber                                                     # noqa: E402
from PIL import Image                                                 # noqa: E402
from pypdf import PdfReader                                           # noqa: E402

import bf_edit                                                        # noqa: E402
import bf_fonts                                                       # noqa: E402
from bf_build import (book_problem, build_preview, check_book, run_build, NothingToPrint,  # noqa: E402
                      empty_chapters_note)
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, load_book, APP_VERSION  # noqa: E402
from bf_pdf import build_pdf, contents_entries, contents_rows, rows_to_edits  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def settings(**kw):
    s = dict(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP), source_mode="paste")
    s.update(kw)
    return s


def png(w, h, color, fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, fmt)
    return b.getvalue()


def para(text, n=1):
    return Block("para", text=(text + " ") * n)


def pdf_info(path):
    """[{text, images, lines: [(text, font)]}] per page."""
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            rows = collections.defaultdict(list)
            for c in pg.chars:
                rows[round(c["top"])].append(c)
            lines = []
            for top in sorted(rows):
                cs = rows[top]
                txt = "".join(c["text"] for c in cs).strip()
                fonts = collections.Counter(c["fontname"].split("+")[-1] for c in cs if c["text"].strip())
                if txt and fonts:
                    lines.append((txt, fonts.most_common(1)[0][0]))
            out.append({"text": pg.extract_text() or "", "images": len(pg.images), "lines": lines})
    return out


def font_of(pages, needle, page_from=0):
    """The font of the first line (on or after page_from) that is exactly / starts with needle."""
    for i, p in enumerate(pages[page_from:], page_from):
        for txt, f in p["lines"]:
            if txt == needle or txt.startswith(needle):
                return f
    return None


def base_fonts(path):
    names = set()
    for p in PdfReader(path).pages:
        fonts = (p.get("/Resources", {}) or {}).get("/Font", {}) or {}
        for v in fonts.values():
            names.add(str(v.get_object()["/BaseFont"]).split("+")[-1].lstrip("/"))
    return names


def chapters_text(n, words=20):
    return "".join(f"\n\nChapter {k}\n\n" + ("Words in this chapter go on for a while. " * words) for k in range(1, n + 1))


def contents_numbers(path, title="CONTENTS"):
    """{chapter number: printed page} read from the contents page(s) of a PDF."""
    out = {}
    with pdfplumber.open(path) as pdf:
        on = False
        for pg in pdf.pages:
            txt = pg.extract_text() or ""
            if title in txt:
                on = True
            elif on:
                break
            if on:
                for m in re.finditer(r"^Chapter (\d+)\s+(\S+)$", txt, re.M):
                    out[int(m.group(1))] = m.group(2)
    return out


# ======================================================================================== 1. pictures (book model)
P1, P2, P3 = png(320, 200, (200, 40, 40)), png(240, 360, (40, 160, 60), "JPEG"), png(500, 300, (40, 60, 200))
pic_a = Block("image", image=P1, image_name="red.png", img_width=40, img_place="", align="right")
pic_b = Block("image", image=P2, image_name="green.jpg", img_width=0, img_place="page")
pic_c = Block("image", image=P3, image_name="blue.png", img_place="full")
blocks = [para("Before the pictures.", 30), pic_a, para("Between.", 30), pic_b, pic_c, para("After.", 20)]
back = bf_edit.paras_to_blocks(bf_edit.blocks_to_paras(blocks))
imgs = [b for b in back if b.kind == "image"]
check([b.image for b in imgs] == [P1, P2, P3], "editor round trip keeps every picture's own bytes, in order")
check([(b.img_width, b.img_place, b.align, b.image_name) for b in imgs] ==
      [(40, "", "right", "red.png"), (0, "page", "", "green.jpg"), (0, "full", "", "blue.png")],
      "editor round trip keeps size, placement, alignment and name")
book = Book(title="Pictures", chapters=[Chapter("One", blocks=blocks), Chapter("Two", blocks=[para("Text.", 40)])])
proj = os.path.join(TMP, "pics.bookforge")
bf_edit.save_project(proj, book, settings(), APP_VERSION)
b2, _s = bf_edit.load_project(proj)
check([b.image for b in b2.chapters[0].blocks if b.kind == "image"] == [P1, P2, P3] and
      [b.img_place for b in b2.chapters[0].blocks if b.kind == "image"] == ["", "page", "full"],
      "project save/reopen keeps the picture bytes and settings")
out = os.path.join(TMP, "pics.pdf")
logs = []
build_pdf(apply_info(book, settings(toc=False)), settings(toc=False), out, log=logs.append)
pages = pdf_info(out)
check(sum(p["images"] for p in pages) == 3 and not any("[picture" in p["text"] for p in pages),
      f"the PDF has the 3 pictures and no '[picture' text ({[p['images'] for p in pages]})")
bad = Book(title="Bad", chapters=[Chapter("One", blocks=[para("Text.", 10), Block("image", image=b"\x89PNG broken",
                                                                                       image_name="bad.png")])])
logs = []
try:
    build_pdf(apply_info(bad, settings(toc=False)), settings(toc=False), os.path.join(TMP, "bad.pdf"),
              log=logs.append)
    ok = any("couldn't be used" in m for m in logs)
except Exception as e:                     # noqa: BLE001
    ok = False
    logs.append(repr(e))
check(ok, f"an unreadable picture is left out with a message, the book is still made ({logs[-1:]})")

# ======================================================================================== 3. nothing to print
check(book_problem(Book(title="x")) and "no chapters" in book_problem(Book(title="x")), "no chapters: refused")
empty = Book(title="E", chapters=[Chapter("A", blocks=[Block("para", "  ")]), Chapter("B", blocks=[Block("scene")])])
check(bool(book_problem(empty)), "chapters with only spaces or a section break: refused")
left = Book(title="L", chapters=[Chapter("A", blocks=[para("Words.")], include=False)])
check("left out" in (book_problem(left) or ""), "every chapter left out: refused, and it says so")
check(book_problem(Book(title="P", chapters=[Chapter("Pic", blocks=[pic_a])])) is None, "a chapter with only a picture is fine")
check(book_problem(Book(title="V", chapters=[Chapter("Poem", blocks=[Block("verse", lines=["a line"])])])) is None,
      "a chapter with only a poem is fine")
check(book_problem(Book(title="F", chapters=[Chapter("Empty")], front_blocks=[para("Opening words.")])) is None,
      "text before the first chapter is printable content")
mixed = Book(title="M", chapters=[Chapter("Part", level=0), Chapter("Full", blocks=[para("Words.", 5)]),
                                  Chapter("Hollow")])
check(book_problem(mixed) is None and "Hollow" in empty_chapters_note(mixed) and "Part" not in empty_chapters_note(mixed),
      "one empty chapter (and an empty part) is fine; the empty chapter is named in the log")
for fn, label in ((lambda: build_preview(apply_info(empty, settings()), settings()), "preview"),
                  (lambda: run_build(apply_info(empty, settings()), settings()), "build")):
    try:
        fn()
        refused = False
    except NothingToPrint as e:
        refused = "Re-read source" in str(e)
    check(refused, f"{label}: an empty book is refused with what to do about it")
s_out = settings()
try:
    run_build(apply_info(empty, s_out), s_out)
except NothingToPrint:
    pass
check(not os.listdir(s_out["out_dir"]), "a refused build writes no files")
logs = []
check_book(mixed, logs.append)
check(any("no text" in m for m in logs), "check_book logs the empty chapter")

# ======================================================================================== 4. heading fonts (PDF)
INSTALLED = bf_fonts.scan_installed()
inst = next((f for f in ("DejaVu Sans", "Georgia", "Arial", "Verdana", "Liberation Sans", "FreeSans", "Helvetica Neue")
             if f in INSTALLED and INSTALLED[f].get("R") and INSTALLED[f].get("B")), None)


def font_book():
    return Book(title="Probe Book", subtitle="Sub", author="Ann Author", chapters=[
        Chapter("First Part", label="Part One", level=0),
        Chapter("The Opening", blocks=[para("Body words here.", 30), Block("head", text="Inner Heading"),
                                       para("More body words.", 30)]),
        Chapter("Second Chapter", blocks=[para("Body text again.", 30)])])


def fonts_for(**kw):
    s = settings(toc=True, chapter_label="Chapter 1", **kw)
    out = os.path.join(TMP, f"fonts_{len(os.listdir(TMP))}.pdf")
    logs = []
    build_pdf(apply_info(font_book(), s), s, out, log=logs.append)
    pages = pdf_info(out)
    start = next(i for i, p in enumerate(pages) if any(t == "The Opening" for t, _f in p["lines"]))
    els = {"book title": font_of(pages, "Probe Book"), "contents heading": font_of(pages, s["toc_title"]),
           "part label": font_of(pages, "Part One", 2), "part title": font_of(pages, "First Part", 2),
           "chapter line": font_of(pages, "Chapter 1", start), "chapter title": font_of(pages, "The Opening", start),
           "heading": font_of(pages, "Inner Heading"), "body": font_of(pages, "Body words here.")}
    return els, base_fonts(out), logs


els, names, logs = fonts_for(heading_font="Cinzel", heading_bold=True)
title_els = ("book title", "contents heading", "part title", "chapter title", "heading")
check(all(els[k] == "Cinzel-Bold" for k in title_els) and els["part label"] == els["chapter line"] == "Cinzel-Regular"
      and els["body"] == "Times-Roman", f"included heading font (Cinzel, bold): every title element, body stays Times {els}")
check({"Cinzel-Bold", "Cinzel-Regular", "Times-Roman"} <= names, f"PDF font resources hold the chosen fonts {sorted(names)}")
els, names, _l = fonts_for(heading_font="Cinzel", heading_bold=False)
check(all(els[k] == "Cinzel-Regular" for k in title_els) and "Cinzel-Bold" not in names,
      f"bold titles off: regular heading font everywhere, no bold in the PDF {els}")
els, names, _l = fonts_for(font_family="Lora", heading_font="Cinzel")
check(els["body"] == "Lora-Regular" and els["chapter title"] == "Cinzel-Bold", f"body font independent of the heading font {els}")
els, names, _l = fonts_for(font_family="Lora", heading_font=bf_fonts.SAME_BODY)
check(els["chapter title"] == "Lora-Bold" and els["body"] == "Lora-Regular" and not any("Cinzel" in n for n in names),
      f"Same as body text: titles in the body font (bold) {els}")
els, names, _l = fonts_for(heading_font="Helvetica (built-in)")
check(els["chapter title"] == "Helvetica-Bold" and els["body"] == "Times-Roman", f"built-in heading font {els}")
if inst:
    els, names, logs = fonts_for(heading_font=inst)
    ok = els["chapter title"] not in (None, "Times-Bold", "Times-Roman") and els["body"] == "Times-Roman"
    check(ok and not any("WARNING" in m for m in logs), f"installed heading font {inst!r}: {els['chapter title']}")
    custom = {"name": "My Heading Face", "R": INSTALLED[inst]["R"][0], "B": INSTALLED[inst]["B"][0]}
    els2, names2, logs2 = fonts_for(heading_font="My Heading Face", custom_fonts=[custom])
    check(els2["chapter title"] == els["chapter title"] and not any("WARNING" in m for m in logs2),
          f"a custom font family ('My fonts') as heading font resolves to its own files ({els2['chapter title']})")
else:
    print("SKIP  installed and custom heading fonts (no usable installed font found)")
els, names, logs = fonts_for(heading_font="A Font Nobody Has")
check(els["chapter title"] == "Times-Bold" and any("isn't installed" in m for m in logs),
      "a heading font that isn't on this computer falls back to Times and says so")

# ======================================================================================== 5. contents numbers (PDF)
s28 = settings(toc=True)
b28 = apply_info(load_book(s28, chapters_text(28)), s28)
auto = contents_entries(b28, s28)
rows = contents_rows(auto, [])
for i, r in enumerate(rows):
    r["page"] = "2" if i < 14 else "3"
b28.toc = rows_to_edits(rows, auto)
out = os.path.join(TMP, "toc28.pdf")
build_pdf(b28, s28, out, log=lambda m: None)
nums = contents_numbers(out)
check(len(nums) == 28 and all(nums[k] == ("2" if k <= 14 else "3") for k in nums),
      f"28 chapters: 1-14 print page 2, 15-28 print page 3 ({sorted(nums.items())[:3]}...{sorted(nums.items())[-2:]})")
rows[0]["page"] = ""
b28.toc = rows_to_edits(rows, auto)
build_pdf(b28, s28, out, log=lambda m: None)
nums2 = contents_numbers(out)
check(nums2.get(1) == b28._toc_labels.get(b28.chapters[0].uid) and nums2.get(2) == "2" and nums2.get(15) == "3",
      f"clearing a typed number goes back to the real page ({nums2.get(1)}), the others stay as typed")

# ======================================================================================== window checks
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as e:                     # noqa: BLE001
    have_display = False
    print(f"SKIP  window checks (no display: {e})")

if have_display:
    from tkinter import messagebox, filedialog
    SAID = []
    ANSWER = {}
    for k in ("askyesno", "askyesnocancel", "showinfo", "showerror", "showwarning", "askokcancel"):
        setattr(messagebox, k, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, title, message))
                                              or ANSWER.get(kind, True)))(k))
    PICK = []
    filedialog.askopenfilename = lambda **kw: PICK.pop(0) if PICK else ""
    filedialog.asksaveasfilename = lambda **kw: PICK.pop(0) if PICK else ""
    import BookForge as BF
    import bf_theme as th
    app = BF.App()
    app._no_save = True
    errors = []
    app.report_callback_exception = lambda *a: errors.append("".join(__import__("traceback").format_exception(*a)))
    ASK = []
    app.ask_text = lambda parent, title, prompt, initial="": ASK.pop(0) if ASK else None
    ed, t = app.editor, app.editor.txt

    def pump(sec=0.2):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    def wait(cond, sec=180):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def idle(sec=240):
        return wait(lambda: not app.busy, sec)

    def tab(key):
        app.shelf.select(th.tab_index(key))
        pump(0.15)

    def paste_source(text):
        app.var("source_mode").set("paste")
        app._mode_changed()
        box = app.texts["paste_text"]
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        pump(0.05)

    def read_now():
        app.scan(force=True)
        return idle(60) and app.book is not None

    def preview():
        n = len(SAID)
        app.preview_book()
        idle()
        pump(0.2)
        pw = getattr(app, "preview_win", None)
        return (pw.result if pw is not None and pw.alive() else None), SAID[n:]

    def key(keysym, char=None):
        t.focus_force()
        app.update()
        kw = {"keysym": keysym}
        t.event_generate("<KeyPress>", **kw)
        t.event_generate("<KeyRelease>", **kw)
        pump(0.05)

    def pic_blocks(ch=None):
        ed.commit()
        ch = ch or ed.cur_obj
        return [b for b in ch.blocks if b.kind == "image"]

    def text_of(ch=None):
        ch = ch or ed.cur_obj
        return " ".join(b.text for b in ch.blocks if b.kind != "image")

    def pic_line():
        return int(ed._pics()[0][0].split(".")[0])

    def png_file(name, w, h, color):
        p = os.path.join(TMP, name)
        Image.new("RGB", (w, h), color).save(p)
        return p

    RED, GREEN = png_file("red.png", 300, 200, (220, 30, 30)), png_file("green.png", 200, 300, (30, 200, 30))
    RED_BYTES = open(RED, "rb").read()
    BOOK3 = "".join(f"Chapter {i}\n\n" + "\n\n".join(f"Paragraph {i}.{j}: " + "words of text here " * 10
                                                     for j in range(1, 5)) + "\n\n" for i in range(1, 4))

    def fresh(insert_at="2.end"):
        """Chapter 1 open in the editor with one picture (red.png) inserted after paragraph 2."""
        paste_source(BOOK3)
        read_now()
        tab("edit")
        ed.select(0)
        t.mark_set("insert", insert_at)
        PICK.append(RED)
        ed.insert_picture()
        pump(0.05)
        return ed.cur_obj

    # ---------------------------------------------------------------- 1. pictures in the editor
    ch = fresh()
    pics = pic_blocks()
    check(len(pics) == 1 and pics[0].image == RED_BYTES, "insert: the chapter holds the picture's own bytes")
    ln = pic_line()
    t.mark_set("insert", f"{ln}.0")
    key("BackSpace")
    check(len(pic_blocks()) == 1 and "[picture" not in text_of() and "Paragraph 1.2" in text_of(),
          "Backspace at the start of the picture line keeps the picture and the text above")
    ln = pic_line()
    t.mark_set("insert", f"{ln}.0")
    key("x")
    check(len(pic_blocks()) == 1 and "[picture" not in text_of() and len(ed._pics()) == 1 and
          t.get(f"{pic_line() - 1}.0", f"{pic_line() - 1}.end") == "x" and
          t.get(f"{pic_line()}.0", f"{pic_line()}.end") == bf_edit.picture_label(pic_blocks()[0]),
          "a key typed before the picture starts a new paragraph above it")
    ln = pic_line()
    t.mark_set("insert", f"{ln}.end")
    for c in "typed":
        key(c)
    check(len(pic_blocks()) == 1 and any(b.kind == "para" and "typed" in b.text for b in ed.cur_obj.blocks),
          "words typed after the picture's label are kept as a paragraph after it")
    ln = pic_line()
    t.mark_set("insert", f"{ln}.end")
    key("Return")
    check(len(pic_blocks()) == 1 and t.get(f"{pic_line() + 1}.0", f"{pic_line() + 1}.end") == "",
          "Enter at the end of the picture line makes an empty paragraph below it")
    ln = pic_line()
    t.mark_set("insert", f"{ln - 1}.end")
    key("Delete")
    check(len(pic_blocks()) == 1 and len(ed._pics()) == 1, "Delete at the end of the line above doesn't swallow the picture")
    # programmatic damage (what selections, IMEs or other tools can do) is repaired, never lost
    ch = fresh()
    ln = pic_line()
    t.delete(f"{ln}.0-1c", f"{ln}.0")                     # join the picture onto the line above
    t.insert(f"{pic_line()}.end", " tail words")         # text after the label
    ed.normalise_pictures()
    check(len(pic_blocks()) == 1 and "tail words" in text_of() and "[picture" not in text_of() and
          all(len(ed._pics(f"{i}.0", f"{i}.end")) == 0 or
              t.get(f"{i}.0", f"{i}.end") == bf_edit.picture_label(pic_blocks()[0]) for i in range(1, 30)),
          "a picture joined onto another line is put back on its own line; nothing is lost")
    ch = fresh()
    ln = pic_line()
    t.tag_add("sel", f"{ln - 1}.0", f"{ln + 1}.end")
    ed.set_style("quote")
    t.tag_remove("sel", "1.0", "end")
    check(len(pic_blocks()) == 1 and [b.kind for b in ed.cur_obj.blocks].count("quote") >= 2,
          "a paragraph style over a selection with the picture styles the text, the picture stays a picture")
    ed.find_window()
    fv, rv, find, replace, replace_all = ed.find_funcs
    fv.set("picture")
    rv.set("PHOTO")
    replace_all()
    ed.find_win.destroy()
    check(len(pic_blocks()) == 1 and pic_blocks()[0].image_name == "red.png", "find & replace never changes a picture's label")
    ch = fresh()
    ln = pic_line()
    t.tag_add("sel", f"{ln}.0", f"{ln + 1}.0")
    t.event_generate("<<Cut>>")
    pump(0.05)
    check(len(pic_blocks()) == 0, "cut takes the picture out")
    t.tag_remove("sel", "1.0", "end")
    t.mark_set("insert", "1.0")
    t.event_generate("<<Paste>>")
    pump(0.1)
    pics = pic_blocks()
    check(len(pics) == 1 and pics[0].image == RED_BYTES and ed.cur_obj.blocks[0].kind == "image",
          "paste puts the same picture back where it is pasted")
    t.tag_add("sel", f"{pic_line()}.0", f"{pic_line() + 1}.0")
    t.event_generate("<<Copy>>")
    t.tag_remove("sel", "1.0", "end")
    t.mark_set("insert", "end-1c")
    t.event_generate("<<Paste>>")
    pump(0.1)
    pics = pic_blocks()
    check(len(pics) == 2 and pics[0].image == pics[1].image == RED_BYTES and pics[0] is not pics[1],
          "copy and paste makes a second, separate copy of the picture")
    # picture settings window: size, alignment, placement; replace; remove + undo
    ch = fresh()
    ed.picture_settings(pic_line())
    pump(0.1)
    w = ed.picture_win

    def widgets(root, cls):
        out, todo = [], [root]
        while todo:
            x = todo.pop()
            todo.extend(x.winfo_children())
            if x.winfo_class() == cls:
                out.append(x)
        return out
    for cb in widgets(w, "TCheckbutton"):
        cb.invoke()                                       # "Automatic" off
    for sp in widgets(w, "TSpinbox"):
        sp.set("40")
    for cb in widgets(w, "TCombobox"):
        cb.set("Right")
    for rb in widgets(w, "TRadiobutton"):
        if rb.cget("text") == "On a page of its own":
            rb.invoke()
    next(b for b in widgets(w, "TButton") if b.cget("text") == "OK").invoke()
    pump(0.05)
    b = pic_blocks()[0]
    check((b.img_width, b.img_place, b.align, b.image) == (40, "page", "right", RED_BYTES),
          f"picture settings: size, placement and alignment set, bytes unchanged ({b.img_width}, {b.img_place}, {b.align})")
    ed.picture_settings(pic_line())
    pump(0.1)
    PICK.append(GREEN)
    next(x for x in widgets(ed.picture_win, "TButton") if x.cget("text") == "Replace picture...").invoke()
    next(x for x in widgets(ed.picture_win, "TButton") if x.cget("text") == "OK").invoke()
    pump(0.05)
    b = pic_blocks()[0]
    check(b.image == open(GREEN, "rb").read() and b.image_name == "green.png" and b.img_place == "page",
          "Replace picture changes the picture and keeps its settings")
    ed.picture_settings(pic_line())
    pump(0.1)
    next(x for x in widgets(ed.picture_win, "TButton") if x.cget("text") == "Remove picture").invoke()
    pump(0.05)
    check(len(pic_blocks()) == 0 and "[picture" not in text_of(), "Remove picture removes it (and leaves no label text)")
    ed.undo()
    check(len(pic_blocks()) == 1 and pic_blocks()[0].image_name == "green.png", "Undo brings the removed picture back")
    # chapters, tabs, preview, build, project
    ch0 = ed.cur_obj
    ed.select(1)
    ed.select(0)
    tab("lay")
    tab("edit")
    check(len(pic_blocks(ch0)) == 1 and len(ed._pics()) == 1, "switching chapters and tabs keeps the picture")
    t.mark_set("insert", "1.3")
    key("a")
    res, said = preview()
    pages = pdf_info(res["pdf"]) if res else []
    check(res and sum(p["images"] for p in pages) == 1 and not any("[picture" in p["text"] for p in pages),
          f"preview: the picture is printed, never its label ({said})")
    outdir = tempfile.mkdtemp(dir=TMP)
    app.var("out_dir").set(outdir)
    app.var("open_when_done").set(False)
    for k, v in dict(fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False, fmt_docx=False,
                     fmt_html=False, fmt_txt=False).items():
        app.var(k).set(v)
    app.build()
    idle()
    printed = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")]
    check(printed and sum(p["images"] for p in pdf_info(printed[0])) == 1, "Make the book: the Print PDF has the picture")
    proj = os.path.join(TMP, "editor.bookforge")
    PICK.append(proj)
    app.save_project_dialog()
    PICK.append(proj)
    app.open_project_dialog()
    pump(0.2)
    tab("edit")
    ed.select(0)
    pics = [b for b in app.book.chapters[0].blocks if b.kind == "image"]
    check(len(pics) == 1 and pics[0].image == open(GREEN, "rb").read() and pics[0].img_place == "page" and
          len(ed._pics()) == 1, "save project and open it again: the picture comes back with its settings")
    # pictures that can't be shown or read
    n = len(SAID)
    PICK.append(os.path.join(TMP, "notes.txt"))
    open(PICK[-1], "w").write("not a picture")
    ed.commit()
    before = [(b.kind, b.text, b.image) for b in ed.cur_obj.blocks]
    ed.insert_picture()
    ed.commit()
    check(any(k == "showerror" for k, *_x in SAID[n:]) and [(b.kind, b.text, b.image) for b in ed.cur_obj.blocks] == before,
          "a file that isn't a picture is refused with a message; the chapter is unchanged")
    odd = Block("image", image=b"\x89PNG not really", image_name="odd.png")
    app.book.chapters[1].blocks.insert(0, odd)
    ed.select(1)
    check(len(ed._pics()) == 1, "a picture whose small copy can't be made still shows (as a grey box)")
    ed.dirty = True
    ed.commit()
    kept = [b for b in app.book.chapters[1].blocks if b.kind == "image"]
    check(len(kept) == 1 and kept[0].image == b"\x89PNG not really", "... and its bytes are kept, not lost")

    # ---------------------------------------------------------------- 2. source and book
    tab("src")
    check(str(app.reread_btn.cget("text")).endswith("Re-read source"), "the Source tab has a Re-read source button")
    paste_source(BOOK3)
    read_now()
    check(len(app.book.chapters) == 3 and not app.edited, "reading the pasted text: 3 chapters")
    paste_source(BOOK3 + "Chapter 4\n\nA fourth chapter, added to the text.\n\n")
    n = len(SAID)
    app.reread_source()
    idle()
    pump(0.1)
    check(len(app.book.chapters) == 4 and not SAID[n:], "Re-read source (no edits): the book follows the text, no question")
    check(ed.chapters() is app.book.chapters and len(app.editor.chapter_rows()) == 4,
          "the chapter list and the editor follow")
    tab("edit")
    ed.select(1)
    t.insert("1.0", "EDITED ")
    ed.dirty = True
    tab("src")
    check(app.edited, "an edit in Specific Text Edit marks the book as edited")
    ANSWER["askyesno"] = False
    n = len(SAID)
    app.reread_source()
    idle()
    check(any(k == "askyesno" and "lost" in m for k, _ti, m in SAID[n:]) and "EDITED" in app.book.chapters[1].blocks[0].text,
          "Re-read source with edits asks first; No keeps the edited book")
    ANSWER["askyesno"] = True
    app.reread_source()
    idle()
    check("EDITED" not in app.book.chapters[1].blocks[0].text and not app.edited, "... Yes reads the source again")
    # a failed read keeps the book and its edits
    tab("edit")
    ed.select(0)
    t.insert("1.0", "KEEP ")
    ed.dirty = True
    tab("src")
    app.texts["paste_text"].delete("1.0", "end")
    n = len(SAID)
    app.reread_source()
    idle()
    check(any(k == "showwarning" for k, *_x in SAID[n:]) and "KEEP" in app.book.chapters[0].blocks[0].text and app.edited,
          "Re-read source with an empty paste box: a message, the edited book stays")
    app.scan(force=True)                                   # Find chapters again, reading fails
    idle()
    check("KEEP" in app.book.chapters[0].blocks[0].text and app.edited,
          "a failed read keeps the book still marked as edited (nothing replaces it later without asking)")
    paste_source(BOOK3 + "Chapter 4\n\nA changed source.\n\n")
    tab("chap")
    pump(0.5)
    idle(30)
    check("KEEP" in app.book.chapters[0].blocks[0].text, "... opening Chapters doesn't silently read the source over it")
    # "Keep your chapter changes?" is asked once
    paste_source(BOOK3 + "Chapter 4\n\nNew words.\n\n")
    ANSWER["askyesno"] = True
    res, said = preview()
    asked1 = sum(1 for k, ti, _m in said if ti == "Keep your chapter changes?")
    res2, said2 = preview()
    asked2 = sum(1 for k, ti, _m in said2 if ti == "Keep your chapter changes?")
    check(asked1 == 1 and asked2 == 0 and res2, "Keep your chapter changes? Yes: used, and not asked again for the same source")
    # an open preview is marked out of date when a preview can't be made
    pw = app.preview_win
    app.texts["paste_text"].delete("1.0", "end")
    ANSWER["askyesno"] = False                            # No = read the (now empty) source again: fails
    res, said = preview()
    check(pw.alive() and pw.result is None and "out of date" in pw.w.title(),
          f"a preview that fails marks the open preview out of date ({[x[1] for x in said]})")
    ANSWER["askyesno"] = True
    # a commit that fails keeps you in Specific Text Edit and stops Preview
    paste_source(BOOK3)
    read_now()
    tab("edit")
    ed.select(0)
    t.insert("1.0", "X")
    ed.dirty = True
    real = bf_edit.paras_to_blocks
    bf_edit.paras_to_blocks = lambda paras: (_ for _ in ()).throw(RuntimeError("simulated"))
    n = len(SAID)
    tab("lay")
    stayed = th.TABS[app.cur_page][0] == "edit"
    res, said = preview()
    bf_edit.paras_to_blocks = real
    check(stayed and any(k == "showerror" and "Edit" == ti for k, ti, _m in SAID[n:]),
          "an editor commit that fails: stays in Specific Text Edit with the message, edits still there")
    check(not any(x[1] == "Problem" for x in said) and not app.busy, "... and Preview doesn't start on stale text")
    ed.commit()

    # an edit made after a preview: the open preview says it is out of date, Update preview shows the edit
    paste_source(BOOK3)
    read_now()
    res, said = preview()
    pw = app.preview_win
    tab("edit")
    ed.select(0)
    t.insert("1.0", "FRESHWORD ")
    ed.dirty = True
    tab("chap")                                            # leaving the editor applies the edit
    wait(lambda: pw.result is None, 5)
    check(pw.result is None and "out of date" in pw.w.title(), "an edit after the preview marks the open preview out of date")
    res, said = preview()
    check(res and any("FRESHWORD" in p["text"] for p in pdf_info(res["pdf"])), "... and Update preview shows the edit")

    # ---------------------------------------------------------------- 3. nothing to print (window)
    paste_source(BOOK3)
    read_now()
    if getattr(app, "preview_win", None) is not None:
        app.preview_win.close()
    for c in app.book.chapters:
        c.blocks = []
    app.edited = True
    tab("chap")
    res, said = preview()
    check(res is None and any(ti == "Nothing to print" for _k, ti, _m in said), "every chapter emptied: Preview says there's nothing to print")
    n = len(SAID)
    outdir = tempfile.mkdtemp(dir=TMP)
    app.var("out_dir").set(outdir)
    app.build()
    idle()
    check(any(ti == "Nothing to print" for _k, ti, _m in SAID[n:]) and not os.listdir(outdir),
          "... and Make the book says so too, writing nothing")
    read_now()
    for c in app.book.chapters:
        c.include = False
    app.edited = True
    res, said = preview()
    check(res is None and any("left out" in m for _k, _t, m in said), "every chapter left out: refused with how to fix it")

    # ---------------------------------------------------------------- 4. heading font in the window
    paste_source("Chapter 1\n\n" + "Opening words of the book. " * 3 + "\n\nA Heading Inside\n\nMore words follow here.\n\n"
                 "Chapter 2\n\nThe second chapter's words.\n\n")
    read_now()
    tab("edit")
    ed.select(0)
    hl = next(i for i in range(1, 40) if t.get(f"{i}.0", f"{i}.end") == "A Heading Inside")
    t.mark_set("insert", f"{hl}.2")
    ed.set_style("head")
    tab("lay")
    app.var("heading_font").set("Cinzel")
    app.var("heading_bold").set(True)
    app.var("toc").set(True)
    res, said = preview()
    pv = pdf_info(res["pdf"])
    start = next(i for i, p in enumerate(pv) if p["lines"] and p["lines"][0][0] == "Chapter 1")
    check(font_of(pv, "Chapter 1", start) == "Cinzel-Bold" and font_of(pv, "Opening words") == "Times-Roman",
          "Layout heading font -> the preview's chapter titles (body unchanged)")
    pw = app.preview_win
    app.var("heading_font").set("Helvetica (built-in)")
    wait(lambda: pw.result is None, 5)
    check(pw.result is None and "out of date" in pw.w.title(), "changing the heading font marks the open preview out of date")
    res, said = preview()
    pv = pdf_info(res["pdf"])
    check(font_of(pv, "Chapter 1", start) == "Helvetica-Bold", "Update preview shows the new heading font")
    pump(0.8)
    check(app.preview_win.result is not None, "a preview made with the current settings isn't marked out of date")
    app.var("heading_bold").set(False)
    res, said = preview()
    pv = pdf_info(res["pdf"])
    check(font_of(pv, "Chapter 1", start) == "Helvetica", "bold titles off reaches the preview")
    app.var("heading_font").set("Cinzel")
    app.var("heading_bold").set(True)
    res, said = preview()
    outdir = tempfile.mkdtemp(dir=TMP)
    app.var("out_dir").set(outdir)
    app.build()
    idle()
    printed = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")][0]
    pv, pp = pdf_info(res["pdf"]), pdf_info(printed)
    check(len(pv) == len(pp) and [p["lines"] for p in pv] == [p["lines"] for p in pp] and
          base_fonts(res["pdf"]) == base_fonts(printed),
          f"preview and the final Print PDF: same pages, text and fonts ({len(pv)} pages, {sorted(base_fonts(printed))})")
    hd = font_of(pp, "A Heading Inside")
    check(hd == "Cinzel-Bold", f"an ordinary heading in the text uses the heading font ({hd})")
    sp = os.path.join(TMP, "settings.json")
    app.save_settings(sp)
    app.var("heading_font").set(bf_fonts.SAME_BODY)
    app.var("heading_bold").set(False)
    app.load_settings(sp)
    check(app.var("heading_font").get() == "Cinzel" and app.var("heading_bold").get() is True,
          "settings file keeps the heading font and bold choice")
    proj = os.path.join(TMP, "fonts.bookforge")
    PICK.append(proj)
    app.save_project_dialog()
    app.var("heading_font").set("Lora")
    PICK.append(proj)
    app.open_project_dialog()
    pump(0.2)
    check(app.var("heading_font").get() == "Cinzel", "a project keeps the heading font")
    # the editor shows headings in the heading font; a heading made from a paragraph set in one font prints in it
    show = inst or "DejaVu Sans"
    app.var("heading_font").set(show)
    tab("edit")
    ed.select(0)
    hl = next(i for i in range(1, 40) if "st|head" in t.tag_names(f"{i}.0"))
    fams = {x.split("|")[1] for x in t.tag_names(f"{hl}.1") if x.startswith("df|")}
    check(fams == {ed._tk_family(show)}, f"the editor shows headings in the Titles & headings font ({fams})")
    pl = next(i for i in range(1, 40) if t.get(f"{i}.0", f"{i}.end").startswith("More words"))
    t.tag_add("sel", f"{pl}.0", f"{pl}.end")
    ed.set_value("ff|", "Courier (built-in)")
    t.tag_remove("sel", "1.0", "end")
    t.mark_set("insert", f"{pl}.2")
    ed.set_style("head")
    app.var("heading_font").set("Cinzel")
    res, said = preview()
    check(font_of(pdf_info(res["pdf"]), "More words follow") == "Cinzel-Bold",
          "a paragraph set in one font, made a Heading, prints in the Titles & headings font")

    # ---------------------------------------------------------------- 5. Edit contents in the window, 28 chapters
    if getattr(app, "preview_win", None) is not None:
        app.preview_win.close()
    app.var("heading_font").set(bf_fonts.SAME_BODY)
    paste_source(chapters_text(28))
    read_now()
    app.var("toc").set(True)
    app.var("toc_numbers").set("None")
    tab("front")
    app.edit_contents()
    pump(0.2)
    cw = app.contents_win
    for i in range(28):
        cw.tree.selection_set(str(i))
        ASK.append("2" if i < 14 else "3")
        cw.set_page()
    check([cw.tree.item(str(i))["values"][2] for i in (0, 13, 14, 27)] ==
          ["2   (typed)", "2   (typed)", "3   (typed)", "3   (typed)"], "Edit contents shows the typed numbers")
    res, said = preview()                                  # main Preview, the window still open (no OK yet)
    nums = contents_numbers(res["pdf"])
    check(len(nums) == 28 and all(nums[k] == ("2" if k <= 14 else "3") for k in nums),
          f"main Preview with Edit contents still open: 1-14 print 2, 15-28 print 3 ({len(nums)} entries)")
    cw = app.contents_win
    cw.ok()
    uids = [c.uid for c in app.book.chapters]
    check([e["page"] for e in app.book.toc] == ["2"] * 14 + ["3"] * 14 and [e["uid"] for e in app.book.toc] == uids,
          "OK: each typed number is saved for its own chapter")
    outdir = tempfile.mkdtemp(dir=TMP)
    app.var("out_dir").set(outdir)
    app.build()
    idle()
    printed = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")][0]
    nums = contents_numbers(printed)
    check(len(nums) == 28 and all(nums[k] == ("2" if k <= 14 else "3") for k in nums), "Make the book: the Print PDF prints them")
    proj = os.path.join(TMP, "toc28.bookforge")
    PICK.append(proj)
    app.save_project_dialog()
    PICK.append(proj)
    app.open_project_dialog()
    idle()
    pump(0.2)
    res, said = preview()
    nums = contents_numbers(res["pdf"])
    check(len(nums) == 28 and all(nums[k] == ("2" if k <= 14 else "3") for k in nums), "after save and reopen: still printed")
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    cw.tree.selection_set("0")
    ASK.append("")
    cw.set_page()
    cw.ok()
    res, said = preview()
    nums = contents_numbers(res["pdf"])
    real1 = app.toc_labels.get(app.book.chapters[0].uid)
    check(nums.get(1) == real1 and nums.get(1) != "2" and nums.get(2) == "2",
          f"clearing a typed number: back to the real page ({nums.get(1)} = {real1}), the others stay")
    # the window's close button never drops changes silently; Cancel goes back
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    cw.tree.selection_set("1")
    ASK.append("77")
    cw.set_page()
    ANSWER["askyesnocancel"] = False
    n = len(SAID)
    cw.close_asking()
    check(any(k == "askyesnocancel" for k, *_x in SAID[n:]) and app.book.toc[1]["page"] == "2",
          "closing Edit contents with changes asks; No leaves the contents as they were")
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    cw.tree.selection_set("1")
    ASK.append("88")
    cw.set_page()
    res, said = preview()                                   # used by the preview while open...
    cw.cancel()                                             # ...then Cancel
    check(app.book.toc[1]["page"] == "2", "Cancel puts back the contents as they were when the window opened")
    # renaming, hiding, adding and indenting still work
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    cw.tree.selection_set("2")
    ASK.append("A Renamed Entry")
    cw.rename()
    cw.tree.selection_set("3")
    cw.toggle()
    cw.tree.selection_set("4")
    cw.indent()
    ASK.extend(["Map of the island", "9"])
    cw.add()
    cw.ok()
    res, said = preview()
    txt = "\n".join(p["text"] for p in pdf_info(res["pdf"])[:4])
    check("A Renamed Entry" in txt and "Map of the island" in txt and not re.search(r"^Chapter 4\s", txt, re.M),
          "rename, hide and add entries still work alongside typed numbers")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
