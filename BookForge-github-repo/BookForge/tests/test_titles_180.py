"""Title and heading alignment & position settings (1.8.0) - plain Python: python tests/test_titles_180.py

Layout tab > "Titles: alignment & position": title page alignment / position / book title size, chapter title
alignment (+ the existing "Drop chapter start down"), part title alignment / position / size.
Checked in the PDF itself (text positions, sizes, fonts, ornament lines):
1. defaults print every title exactly where 1.7.0/1.8.0-before-these-settings did (measured positions)
2. each alignment moves the right lines (and only those); headings inside the text keep their own alignment
3. the positions move the titles by the expected amount; a title block is never pushed off its page
4. heading font / sizes / bold stay as chosen; the body font is untouched
5. chapter starts, page numbers, running heads still work; imposition is unchanged
6. bad values are clamped, never break a book; "Drop chapter start down" with a long first paragraph no longer
   leaves an empty page
7. preview = final Print PDF (text, fonts, positions)
8. window: the settings survive tabs, Re-read source, settings files, projects (old ones get the defaults),
   light/dark, and reach the preview (window checks run only where a display is available)
"""
import copy
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_titles_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402

import bf_edit                                                        # noqa: E402
import bf_impose                                                      # noqa: E402
from bf_build import build_preview, run_build                         # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, TITLE_LAYOUT_KEYS  # noqa: E402
from bf_pdf import build_pdf, title_layout                            # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def settings(**kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP))
    s.update(kw)
    return s


def para(t, n=1):
    return Block("para", text=(t + " ") * n)


def golden_book():
    return Book(title="Golden Title", subtitle="Golden Subtitle", author="Golden Author", credit="Golden Credit",
                chapters=[Chapter("Golden Part", label="Part One", level=0),
                          Chapter("Golden Chapter", blocks=[Block("subtitle", text="Golden chapter subtitle"),
                                                            para("Golden body text.", 40),
                                                            Block("head", text="Golden Inner Heading"),
                                                            para("More golden text.", 20)]),
                          Chapter("Second Golden", blocks=[para("Second chapter text.", 30)])])


def lines(path):
    """{line text: (page, x0, x1, top, size, font)} for the first line with each text."""
    out = {}
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            rows = {}
            for w in pg.extract_words(extra_attrs=["size", "fontname"]):
                rows.setdefault(round(w["top"], 1), []).append(w)
            for top, ws in sorted(rows.items()):
                txt = " ".join(w["text"] for w in ws)
                if txt not in out:
                    out[txt] = (pg.page_number, round(min(w["x0"] for w in ws), 2), round(max(w["x1"] for w in ws), 2),
                                round(top, 2), round(ws[0]["size"], 2), ws[0]["fontname"].split("+")[-1])
    return out


def make(book=None, name=None, **kw):
    s = settings(**kw)
    out = os.path.join(TMP, (name or f"t{len(os.listdir(TMP))}") + ".pdf")
    logs = []
    n = build_pdf(apply_info(book or golden_book(), s), s, out, log=logs.append)
    return out, n, logs


def near(a, b, tol=0.06):
    return abs(a - b) <= tol


L, R, FW = 72.0, 540.0, 468.0          # Letter, 1 in side margins: the text area runs from 72 to 540 pt
MT, FH = 61.2, 792 - 2 * 61.2          # 0.85 in top/bottom margins

# ======================================================================================== 1. defaults unchanged
GOLDEN = {   # measured with BookForge 1.8.0 before these settings existed: (page, x0, x1, top)
    "Golden Title": (1, 213.51, 398.49, 202.6), "Golden Subtitle": (1, 257.56, 354.44, 253.9),
    "Golden Author": (1, 262.3, 349.7, 310.6), "Golden Credit": (1, 272.69, 339.31, 342.3),
    "CONTENTS": (2, 242.74, 369.26, 66.2), "Part One": (3, 280.43, 331.57, 265.2),
    "Golden Part": (3, 233.55, 378.45, 290.9), "Golden Chapter": (4, 226.45, 385.55, 66.2),
    "Golden chapter subtitle": (4, 244.61, 367.39, 108.8), "Golden Inner Heading": (4, 236.31, 375.69, 318.5),
    "Second Golden": (5, 232.19, 379.81, 66.2)}
GOLDEN_SINK = {"Golden Chapter": (4, 226.45, 385.55, 163.0), "Golden chapter subtitle": (4, 244.61, 367.39, 205.6),
               "Golden Inner Heading": (4, 236.31, 375.69, 437.3), "Second Golden": (5, 232.19, 379.81, 163.0)}
base, n_base, _l = make(name="default")
got = lines(base)


def matches(got, want):
    bad = [k for k, v in want.items() if k not in got or got[k][0] != v[0] or
           not all(near(a, b) for a, b in zip(got[k][1:4], v[1:]))]
    return bad
check(not matches(got, GOLDEN), f"defaults: every title, subtitle, author, credit, part, chapter and contents heading "
                                f"prints where it did before {matches(got, GOLDEN)}")
check(got["Golden Title"][4] == 34.5 and got["Golden Part"][4] == 27.6 and got["Golden Chapter"][4] == 23.0,
      "defaults: book title 34.5 pt (1.5 x chapter title), part title 27.6 pt (1.2 x), chapter title 23 pt")
sink, _n, _l = make(name="sink", chapter_sink=1.0, ornament=True, chapter_label="Chapter One")
check(not matches(lines(sink), GOLDEN_SINK), "Drop chapter start down 1 in (+ number line, ornament): chapter titles "
                                             f"where they were before {matches(lines(sink), GOLDEN_SINK)}")
explicit, n_exp, _l = make(name="explicit", **{k: DEFAULTS[k] for k in TITLE_LAYOUT_KEYS})
check(lines(explicit) == got and n_exp == n_base, "the standard values typed in = the defaults, page for page")

# ======================================================================================== 2. alignment
def edges(line, align):
    x0, x1 = line[1], line[2]
    if align == "Left":
        return near(x0, L, 0.6)
    if align == "Right":
        return near(x1, R, 0.6)
    return near((x0 + x1) / 2, (L + R) / 2, 0.6)


for al in ("Left", "Right", "Centered"):
    out, _n, _l = make(name=f"tp_{al}", tp_align=al)
    g = lines(out)
    tp = [g[k] for k in ("Golden Title", "Golden Subtitle", "Golden Author", "Golden Credit")]
    check(all(edges(x, al) for x in tp) and edges(g["This Book Belongs To"], "Centered") and
          all(edges(g[k], "Centered") for k in ("Golden Chapter", "Golden Part")),
          f"title page alignment {al}: title, subtitle, author and credit move; bookplate, chapters, parts don't")
    out, _n, _l = make(name=f"ch_{al}", ch_align=al, chapter_label="Chapter One", ornament=True,
                       fic_info="Add a work info page")
    g = lines(out)
    ch = [g[k] for k in ("CHAPTER ONE" if "CHAPTER ONE" in g else "Chapter One", "Golden Chapter",
                         "Golden chapter subtitle", "CONTENTS")]
    check(all(edges(x, al) for x in ch) and edges(g["Golden Inner Heading"], "Centered") and
          edges(g["Golden Title"], "Centered") and edges(g["Golden Part"], "Centered"),
          f"chapter title alignment {al}: number line, title, subtitle, contents heading move; a heading inside the "
          "text, the title page and parts don't")
    with pdfplumber.open(out) as pdf:
        pg = pdf.pages[g["Golden Chapter"][0] - 1]
        xs = [(ln["x0"], ln["x1"]) for ln in pg.lines] + [(c["x0"], c["x1"]) for c in pg.curves]
        lo, hi = min(x for x, _ in xs), max(x for _, x in xs)
    ok = near(lo, L, 0.6) if al == "Left" else near(hi, R, 0.6) if al == "Right" else near((lo + hi) / 2, 306, 0.6)
    check(ok, f"chapter title alignment {al}: the ornament under the title follows ({lo:.1f}..{hi:.1f})")
    out, _n, _l = make(name=f"pt_{al}", part_align=al, ornament=True)
    g = lines(out)
    check(edges(g["Part One"], al) and edges(g["Golden Part"], al) and edges(g["Golden Chapter"], "Centered"),
          f"part title alignment {al}: part label and title move; chapter titles don't")
# a paragraph aligned in Specific Text Edit never moves the next chapter's title (it used to)
leak = Book(title="Leak", chapters=[Chapter("First", blocks=[para("Words.", 30), Block("para", text="Signed",
                                                                                         align="right", indent=2)]),
                                    Chapter("Second Chapter", blocks=[para("More.", 30)])])
out, _n, _l = make(leak, name="leak", toc=False, title_page=False, bookplate="None", the_end=True)
g = lines(out)
check(edges(g["Second Chapter"], "Centered") and edges(g["THE END"], "Centered"),
      f"a right-aligned last paragraph doesn't move the next chapter title or THE END ({g['Second Chapter'][1:3]})")

# ======================================================================================== 3. positions and sizes
g20, g50 = got, lines(make(name="tp50", tp_pos=50)[0])
check(near(g50["Golden Title"][3] - g20["Golden Title"][3], 0.30 * FH, 0.2) and
      near(g50["Golden Author"][3] - g20["Golden Author"][3], 0.30 * FH, 0.2),
      f"title page position 20 -> 50 %: the title block moves down {0.30 * FH:.1f} pt")
g0 = lines(make(name="tp0", tp_pos=0)[0])
check(g0["Golden Title"][3] < g20["Golden Title"][3] - 100, "title page position 0 %: the title starts at the top")
long_tp = Book(title="Long Title", subtitle="A subtitle", author="An Author", credit="Credit",
               chapters=[Chapter("One", blocks=[para("Text.", 20)])])
out, _n, _l = make(long_tp, name="tp90", tp_pos=90, page_size="Pocket (4 x 6 in)")
g = lines(out)
check(g["Credit"][0] == 1 and g["This Book Belongs To"][0] == 1 and g["One"][0] > 1,
      "title page position 90 % on a small page: the title block is moved up just enough to stay on its page")
p60 = lines(make(name="part60", part_pos=60)[0])
check(near(p60["Golden Part"][3] - got["Golden Part"][3], 0.30 * FH, 0.2) and p60["Golden Part"][0] == 3,
      "part title position 30 -> 60 %: the part title moves down 30 % of the text area")
c1 = lines(make(name="sink1", chapter_sink=1.0)[0])
check(near(c1["Golden Chapter"][3] - got["Golden Chapter"][3], 72 + 6, 0.2),
      "Drop chapter start down 1 in: the chapter title moves down 72 pt (+ its own 6 pt space above, which is "
      "left out only at the very top of a page - as before)")
gs = lines(make(name="sizes", tp_title_size=48, part_size=40)[0])
check(gs["Golden Title"][4] == 48 and gs["Golden Part"][4] == 40 and gs["Golden Chapter"][4] == 23.0,
      "book title size 48 and part title size 40 are used; the chapter title size stays")

# ======================================================================================== 4. fonts
gf = lines(make(name="fonts", heading_font="Cinzel", tp_align="Left", ch_align="Right", part_align="Left",
                tp_pos=35, chapter_sink=0.5)[0])
body = [v for k, v in gf.items() if k.startswith("Golden body text.")]
check(gf["Golden Title"][5] == gf["Golden Chapter"][5] == gf["Golden Part"][5] == "Cinzel-Bold" and
      all(v[5] == "Times-Roman" for v in body),
      f"alignment/position settings keep the heading font (Cinzel-Bold) and the body font (Times-Roman) "
      f"({gf['Golden Title'][5]}, {body[0][5] if body else None})")
gb = lines(make(name="nobold", heading_font="Cinzel", heading_bold=False, ch_align="Left")[0])
check(gb["Golden Chapter"][5] == "Cinzel-Regular", "bold titles off still works with the new settings")

# ======================================================================================== 5. starts, numbers, imposition
out, n, _l = make(name="recto", chapter_start="Right-hand page", ch_align="Right", chapter_sink=1.0,
                  running_heads=True)
g = lines(out)
check(g["Golden Chapter"][0] % 2 == 1 and g["Second Golden"][0] % 2 == 1,
      "Right-hand page starts still put chapters on odd pages")
def numbered(path):
    with pdfplumber.open(path) as pdf:
        return [next((w["text"] for w in pg.extract_words() if w["text"].isdigit() and w["top"] > 720), None)
                for pg in pdf.pages]


plain_recto, n_plain, _l = make(name="recto_std", chapter_start="Right-hand page", chapter_sink=1.0,
                                running_heads=True)
with pdfplumber.open(out) as pdf:
    heads = [pg.extract_words()[0]["text"] for pg in pdf.pages if pg.extract_words()]
check(n == n_plain and numbered(out) == numbered(plain_recto) and sum(1 for x in numbered(out) if x) >= 4,
      f"page numbers are the same as with the standard title settings ({numbered(out)})")
check(any(h.isupper() or h == "Golden" for h in heads), "running heads still printed")
sizes = [(612.0, 792.0)] * n_base
info_a, sides_a = bf_impose.plan_imposition(sizes, settings())
info_b, sides_b = bf_impose.plan_imposition(sizes, settings(tp_align="Right", ch_align="Left", tp_pos=60,
                                                            part_pos=10, chapter_sink=2.0))
check((info_a["sheets"], info_a["signatures"], info_a["blanks"], info_a["trim"]) ==
      (info_b["sheets"], info_b["signatures"], info_b["blanks"], info_b["trim"]) and
      [[(i, round(g.x, 3), round(g.y, 3), round(g.w, 3)) for i, g in sd["places"]] for sd in sides_a] ==
      [[(i, round(g.x, 3), round(g.y, 3), round(g.w, 3)) for i, g in sd["places"]] for sd in sides_b],
      "imposition and page placement don't depend on the title settings")

# ======================================================================================== 6. bad values, empty pages
for bad in (dict(tp_pos="abc", part_pos=None, tp_title_size="x", ch_align="Diagonal"),
            dict(tp_pos=float("nan"), part_pos=float("inf"), part_size=-5, tp_align=7)):
    try:
        out, _n, _l = make(name=f"bad{len(os.listdir(TMP))}", **bad)
        g = lines(out)
        ok = edges(g["Golden Title"], "Centered") and g["Golden Title"][0] == 1
    except Exception as e:                 # noqa: BLE001
        ok = False
        print("   ", repr(e))
    check(ok, f"unusable values {sorted(bad)} fall back to the standard ones; the book is made")
tl = title_layout({"tp_pos": 1e9, "part_pos": -40, "tp_title_size": 3, "chapter_sink": 99})
check(tl["tp_pos"] == 90 and tl["part_pos"] == 0 and tl["tp_title_size"] == 0 and tl["sink"] == 12,
      "values out of range are clamped (positions 0-90 %, sizes 6-144 pt or automatic, drop 0-12 in)")
longp = Book(title="L", chapters=[Chapter(f"Chapter {i}", blocks=[para("A very long opening paragraph that keeps "
                                                                        "going and going.", 80), para("End.")])
                                  for i in (1, 2)])
for start, drop in (("New page", 1.0), ("Right-hand page", 2.0)):
    out, n, _l = make(longp, name=f"long_{start[:3]}", chapter_start=start, chapter_sink=drop, toc=False,
                      title_page=False, bookplate="None", page_size="Half Letter / Digest (5.5 x 8.5 in)")
    with pdfplumber.open(out) as pdf:
        empty = [i + 1 for i, pg in enumerate(pdf.pages)
                 if not [w for w in pg.extract_words() if not w["text"].isdigit()]]
    g = lines(out)
    intended = [p for p in empty if start == "Right-hand page" and p % 2 == 0]
    check(empty == intended and near(g["Chapter 1"][3], got["Golden Chapter"][3] + drop * 72 + 6, 0.2),
          f"{start}, drop {drop} in, long first paragraph: no empty page (only intended blank backs {intended}), "
          f"title at the drop position ({g['Chapter 1'][3]})")
cont = Book(title="C", chapters=[Chapter("Part", label="Part One", level=0),
                                 Chapter("Opening", blocks=[para("A very long paragraph goes on.", 120)])])
out, n, _l = make(cont, name="cont", chapter_start="Continuous", toc=False, title_page=False, bookplate="None",
                  page_size="Half Letter / Digest (5.5 x 8.5 in)")
with pdfplumber.open(out) as pdf:
    empty = [i + 1 for i, pg in enumerate(pdf.pages) if not [w for w in pg.extract_words() if not w["text"].isdigit()]]
check(not empty, f"Continuous: a chapter with a long first paragraph after a part page leaves no empty page {empty}")

# ======================================================================================== 7. preview = Print PDF
s = settings(tp_align="Right", tp_pos=40, tp_title_size=40, ch_align="Left", chapter_sink=0.75, part_align="Right",
             part_pos=15, part_size=34, heading_font="Cinzel", ornament=True, fmt_impose=True)
prev = build_preview(apply_info(golden_book(), s), s, log=lambda m: None)
s2 = dict(s, fmt_epub=False, fmt_docx=False, fmt_html=False, fmt_txt=False)
folder, made, _notes = run_build(apply_info(golden_book(), s2), s2, log=lambda m: None)
printed = [m for m in made if m.endswith("Print.pdf")][0]
check(lines(prev["pdf"]) == lines(printed) and prev["pages"] == len(pdfplumber.open(printed).pages),
      "preview and the final Print PDF: same pages, text, positions, sizes and fonts")

# ======================================================================================== 8. the window
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
    for k in ("askyesno", "askyesnocancel", "showinfo", "showerror", "showwarning", "askokcancel"):
        setattr(messagebox, k, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, message))
                                              or True))(k))
    PICK = []
    filedialog.askopenfilename = lambda **kw: PICK.pop(0) if PICK else ""
    filedialog.asksaveasfilename = lambda **kw: PICK.pop(0) if PICK else ""
    import BookForge as BF
    import bf_theme as th
    app = BF.App()
    app._no_save = True
    errors = []
    app.report_callback_exception = lambda *a: errors.append("".join(__import__("traceback").format_exception(*a)))

    def pump(sec=0.2):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    def idle(sec=240):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            if not app.busy:
                return True
            time.sleep(0.02)
        return False

    def tab(key):
        app.shelf.select(th.tab_index(key))
        pump(0.15)

    CHOSEN = dict(tp_align="Left", tp_pos=35.0, tp_title_size=40.0, ch_align="Right", chapter_sink=0.5,
                  part_align="Left", part_pos=45.0, part_size=30.0)

    def current():
        return {k: app.var(k).get() for k in CHOSEN}

    text = "Part One\n\nChapter 1\n\n" + "Words in the first chapter. " * 40 + "\n\nChapter 2\n\n" + \
        "Words in the second chapter. " * 40 + "\n"
    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].insert("1.0", text)
    app.var("title").set("Window Title")
    app.var("author").set("Window Author")
    tab("lay")
    for k, v in CHOSEN.items():
        app.var(k).set(v)
    for key in ("src", "info", "front", "chap", "edit", "out", "lay"):
        tab(key)
    idle(60)
    check(current() == CHOSEN, "the new settings stay when switching between all tabs")
    app.reread_source()
    idle(60)
    check(current() == CHOSEN and app.book is not None, "Re-read source doesn't reset them")
    sp = os.path.join(TMP, "settings.json")
    app.save_settings(sp)
    for k in CHOSEN:
        app.var(k).set(DEFAULTS[k])
    app.load_settings(sp)
    check(current() == CHOSEN, "saved and loaded in a settings file")
    app.toggle_dark()
    pump(0.5)
    check(current() == CHOSEN, "kept when switching light/dark")
    app.toggle_dark()
    pump(0.5)
    n = len(SAID)
    app.preview_book()
    idle()
    pump(0.2)
    res = app.preview_win.result if getattr(app, "preview_win", None) else None
    g = lines(res["pdf"]) if res else {}
    tp_line = g.get("Window Title")
    ch_line = g.get("Chapter 1")
    check(res and tp_line and edges(tp_line, "Left") and tp_line[4] == 40 and ch_line and edges(ch_line, "Right"),
          f"the preview uses them (title page left, 40 pt; chapter titles right) {SAID[n:]}")
    outdir = tempfile.mkdtemp(dir=TMP)
    app.var("out_dir").set(outdir)
    app.var("open_when_done").set(False)
    for k, v in dict(fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False, fmt_docx=False,
                     fmt_html=False, fmt_txt=False).items():
        app.var(k).set(v)
    app.build()
    idle()
    printed = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")]
    check(printed and res and lines(printed[0]) == lines(res["pdf"]),
          "Make the book: the Print PDF is the preview (same text, positions, sizes, fonts)")
    proj = os.path.join(TMP, "titles.bookforge")
    PICK.append(proj)
    app.save_project_dialog()
    for k in CHOSEN:
        app.var(k).set(DEFAULTS[k])
    PICK.append(proj)
    app.open_project_dialog()
    pump(0.3)
    check(current() == CHOSEN, "saved in a project and back when it is opened")
    book, sett = bf_edit.load_project(proj)
    for k in TITLE_LAYOUT_KEYS:
        sett.pop(k, None)                  # a project from before these settings existed
    old = os.path.join(TMP, "old.bookforge")
    bf_edit.save_project(old, book, sett, "1.7.0")
    PICK.append(old)
    app.open_project_dialog()
    pump(0.3)
    check(all(app.var(k).get() == DEFAULTS[k] for k in TITLE_LAYOUT_KEYS) and
          app.var("chapter_sink").get() == CHOSEN["chapter_sink"],
          "an older project opens with the standard title settings (its own drop-down setting kept)")
    app.var("tp_pos").set(55.0)
    app.var("ch_align").set("Left")
    tab("lay")
    page = app.pages[th.tab_index("lay")]
    spins = []
    todo = [page]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == "TSpinbox" and str(w.cget("textvariable")) == str(app.var("tp_pos")):
            spins.append(w)
    check(spins and spins[0].get() in ("55.0", "55"), "the Layout tab shows the title page position")
    if spins:
        spins[0].delete(0, "end")
        spins[0].insert(0, "not a number")
    s_now = app.collect()
    check(s_now["tp_pos"] == DEFAULTS["tp_pos"], "a position typed as text counts as the standard value, not an error")
    n = len(SAID)
    app.preview_book()
    idle()
    check(not [x for x in SAID[n:] if x[0] == "showerror"], "... and the preview is still made")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
