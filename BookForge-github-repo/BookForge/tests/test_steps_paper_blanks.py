"""Checks for the 1.6.0 step order, printer paper sizes / units and blank pages (plain Python - run:
python tests/test_steps_paper_blanks.py).

Every PDF is made here and measured: printed sheet sizes for every paper preset, custom sizes in each unit,
blank pages in the book and in every imposition layout and signature format. Nothing needs the internet.
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="bf_paper_blanks_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")          # keep the user's real settings out of it
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
from pypdf import PdfReader                                           # noqa: E402
from reportlab.pdfgen import canvas                                   # noqa: E402
from bf_impose import (SHEETS, UNITS, FOLD_LAYOUTS, WACKY, WACKY_LANDSCAPE, LAYOUT_NAMES, SIG_FORMATS,  # noqa: E402
                       impose, IMPOSE_DEFAULTS, sheet_points, custom_sheet_points, paper_label, to_points,
                       from_points, fmt_length)
from bf_core import DEFAULTS, BLANK_PAGES_MAX, parse_blank_count, load_book, apply_info, page_size_inches  # noqa: E402
from bf_pdf import build_pdf                                          # noqa: E402
from bf_build import run_build, add_blank_pages                       # noqa: E402
import bf_edit                                                        # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def close(a, b, tol=0.01):
    return abs(float(a) - float(b)) <= tol


# ---------------------------------------------------------------- 1. the seven steps
import bf_theme as th                                                 # noqa: E402
check([label for _k, label, _c in th.TABS] ==
      ["Source", "Book info", "Front & back", "Chapters", "Layout", "Specific Text Edit", "Output"],
      "the seven steps are in the new order with the new label")
check([k for k, _l, _c in th.TABS] == ["src", "info", "front", "chap", "lay", "edit", "out"] and
      th.tab_index("edit") == 5 and th.tab_index("chap") == 3, "the steps keep their internal names")

# ---------------------------------------------------------------- 2. paper presets
# Every standard paper size BookForge offers, from the size's own definition (US and architectural sizes in
# inches, ISO/JIS/ID-card/book sizes in millimetres), width x height as listed.
_IN, _MMPT = 72.0, 72.0 / 25.4
_INCH = {"Letter": (8.5, 11), "Legal": (8.5, 14), "Tabloid / 11x17": (11, 17), "Half Letter": (5.5, 8.5),
         "Executive": (7.25, 10.5), "Note": (7.5, 10), "Ledger (17 x 11)": (17, 11),
         "US Foolscap (8.5 x 13)": (8.5, 13), "Foolscap (9 x 13)": (9, 13), "ANSI C (17 x 22)": (17, 22),
         "ANSI D (22 x 34)": (22, 34), "ANSI E (34 x 44)": (34, 44), "Super B / A3+ (13 x 19)": (13, 19),
         "Arch A": (9, 12), "Arch B": (12, 18), "Arch C": (18, 24), "Arch D": (24, 36), "Arch E": (36, 48),
         "Arch E1 (30 x 42)": (30, 42)}
_MILLI = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297),
          "A5": (148, 210), "A6": (105, 148), "A7": (74, 105), "A8": (52, 74), "A9": (37, 52), "A10": (26, 37),
          "B0": (1000, 1414), "B1": (707, 1000), "B2": (500, 707), "B3": (353, 500), "B4": (250, 353),
          "B5": (176, 250), "B6": (125, 176), "B7": (88, 125), "B8": (62, 88), "B9": (44, 62), "B10": (31, 44),
          "JIS B0": (1030, 1456), "JIS B1": (728, 1030), "JIS B2": (515, 728), "JIS B3": (364, 515),
          "JIS B4": (257, 364), "JIS B5": (182, 257), "JIS B6": (128, 182), "JIS B7": (91, 128),
          "JIS B8": (64, 91), "JIS B9": (45, 64), "JIS B10": (32, 45), "SRA3": (320, 450), "SRA4": (225, 320),
          "ID-1": (85.6, 53.98), "ID-2": (105, 74), "ID-3": (125, 88),
          "Crown Quarto": (189, 246), "Large Crown Quarto": (201, 258), "Demy Quarto": (219, 276),
          "Royal Quarto": (237, 312), "Crown Octavo": (123, 186),
          "Large Crown Octavo / Penguin Large Paperback": (129, 198), "Demy Octavo": (138, 216),
          "Royal Octavo": (156, 234), "Small Paperback": (111, 178), "Penguin Small Paperback": (111, 181)}
EXPECTED = {k: (w * _IN, h * _IN) for k, (w, h) in _INCH.items()}
EXPECTED.update({k: (w * _MMPT, h * _MMPT) for k, (w, h) in _MILLI.items()})
EXPECTED["Postcard"] = (283.0, 416.0)            # kept as earlier versions printed it (no single standard)
presets = {k: v for k, v in SHEETS.items() if v is not None}
check(len(EXPECTED) == 68 and set(presets) == set(EXPECTED) and "Custom" in SHEETS and SHEETS["Custom"] is None,
      f"all {len(EXPECTED)} paper presets are offered, plus Custom ({len(presets)} presets) "
      f"{sorted(set(presets) ^ set(EXPECTED))}")
check(all(close(presets[k][0], v[0], 1e-9) and close(presets[k][1], v[1], 1e-9) for k, v in EXPECTED.items()),
      "every preset has its exact size")
check(len(set(SHEETS)) == len(SHEETS), "no preset is listed twice")

# labels in every display unit
lab = {u: paper_label({"sheet_size": "Letter", "sheet_unit": u}) for u in UNITS}
check(lab["in"] == "Letter (8.5 × 11.0 inches)" and lab["mm"] == "Letter (215.9 × 279.4 mm)" and
      lab["cm"] == "Letter (21.59 × 27.94 cm)" and lab["pt"] == "Letter (612 × 792 points)",
      f"Letter shown in every unit {list(lab.values())}")
check(paper_label({"sheet_size": "A4", "sheet_unit": "mm"}) == "A4 (210.0 × 297.0 mm)", "A4 in mm")
check(paper_label({"sheet_size": "ID-1", "sheet_unit": "pt"}) == "ID-1 (242.65 × 153.01 points)",
      "fractional points are shown")
check(paper_label({"sheet_size": "B1", "sheet_unit": "mm"}) == "B1 (707.0 × 1000.0 mm)", "ISO B1 in mm")
# names earlier versions saved still open the same paper
for old, new_name in (("Tabloid", "Tabloid / 11x17"), ("11x17", "Tabloid / 11x17"),
                      ("Large Crown Octavo", "Large Crown Octavo / Penguin Large Paperback"),
                      ("Penguin Large Paperback", "Large Crown Octavo / Penguin Large Paperback")):
    check(sheet_points({"sheet_size": old}) == sheet_points({"sheet_size": new_name}),
          f"the old paper name {old!r} still gives {new_name}")
check(sheet_points({"sheet_size": "No such paper"}) == (612.0, 792.0), "an unknown paper name is Letter")
# the display unit never changes the paper
check(all(sheet_points({"sheet_size": k, "sheet_unit": u}) == tuple(map(float, SHEETS[k]))
          for k in EXPECTED for u in UNITS), "changing the display unit never changes a preset's size")

# unit conversion
check(close(to_points(1, "in"), 72, 1e-12) and close(to_points(25.4, "mm"), 72, 1e-9) and
      close(to_points(2.54, "cm"), 72, 1e-9) and to_points(72, "pt") == 72, "inches, mm, cm and points to points")
check(close(from_points(612, "in"), 8.5, 1e-12) and close(from_points(612, "mm"), 215.9, 1e-9) and
      close(from_points(612, "cm"), 21.59, 1e-9) and from_points(612, "pt") == 612, "points back to each unit")
check(close(from_points(to_points(8.37, "in"), "mm"), 8.37 * 25.4, 1e-9), "decimal inches to mm")
# switching the custom size's unit back and forth many times (exact conversion, as the window does)
w, unit = 8.5, "in"
for i in range(200):
    new = ["mm", "cm", "pt", "in"][i % 4]
    w, unit = w * UNITS[unit] / UNITS[new], new
check(close(to_points(w, unit), 612, 1e-9), f"200 unit switches leave the custom size unchanged ({to_points(w, unit)!r} pt)")
check(fmt_length(to_points(215.9, "mm"), "mm") == "215.9" and fmt_length(612, "in") == "8.5",
      "display rounding is only for display")

# custom sizes and checks
check(custom_sheet_points(612, 936, "pt") == (612.0, 936.0), "a custom size typed in points")
check(all(close(a, b) for a, b in zip(custom_sheet_points("215.9", "330.2", "mm"), (612, 936))),
      "a custom size typed in millimetres (text with decimals)")
check(all(close(a, b) for a, b in zip(custom_sheet_points(21.59, 33.02, "cm"), (612, 936))), "and in centimetres")
for bad, word in (((0, 11), "more than 0"), ((-2, 11), "more than 0"), (("abc", 11), "isn't a number"),
                  ((float("nan"), 11), "ordinary number"), ((float("inf"), 11), "ordinary number"),
                  (("", 11), "type a number"), ((300, 11), "at most"), ((8.5, 1e9), "at most"),
                  ((0.001, 11), "too small")):
    try:
        custom_sheet_points(*bad, "in")
        check(False, f"custom size {bad} is refused")
    except ValueError as e:
        check(word in str(e), f"custom size {bad} is refused: {e}")
try:
    sheet_points(dict(IMPOSE_DEFAULTS, sheet_size="Custom", sheet_w=0, sheet_h=11, sheet_unit="in"))
    check(False, "an unusable custom size is never replaced by another size")
except ValueError as e:
    check("Custom paper width" in str(e), "an unusable custom size is reported, not replaced by another size")


# ---------------------------------------------------------------- 3. real printed sheets for every preset
def numbered(n, w=5.5 * 72, h=8.5 * 72, blanks=(), name=None):
    """A PDF of n pages showing P1..Pn (pages whose index is in `blanks` show B1, B2... instead)."""
    path = os.path.join(TMP, name or f"num{n}_{len(os.listdir(TMP))}.pdf")
    c = canvas.Canvas(path, pagesize=(w, h))
    b = 0
    for i in range(n):
        c.setFont("Helvetica-Bold", 30)
        if i in blanks:
            b += 1
            c.drawCentredString(w / 2, h / 2, f"B{b}")
        else:
            c.drawCentredString(w / 2, h / 2, f"P{i + 1 - b}")
        c.showPage()
    c.save()
    return path


SRC8 = numbered(8)


def imp(src, **kw):
    s = dict(IMPOSE_DEFAULTS)
    s.update(kw)
    info = impose(src, tempfile.mkdtemp(dir=TMP), "t", s, log=lambda m: None)
    return info


def expected_sheet(name, layout, rotate=False, custom=None):
    w0, h0 = custom or EXPECTED[name]
    land = FOLD_LAYOUTS[layout][3] if layout in FOLD_LAYOUTS else WACKY_LANDSCAPE[WACKY[layout]]
    w, h = (max(w0, h0), min(w0, h0)) if land else (min(w0, h0), max(w0, h0))
    if rotate != (w0 > h0):                       # "Rotate paper 90", or a paper listed landscape
        w, h = h, w
    return w, h


def sheet_sizes(info):
    out = set()
    for f in info["files"]:
        for pg in PdfReader(f).pages:
            out.add((round(float(pg.mediabox.width), 2), round(float(pg.mediabox.height), 2)))
    return out


bad = []
for name in EXPECTED:
    for layout in ("Folio - 2 pages per side", "Quarto - 4 pages per side", "Small book: 6 per side (3-folio signature)"):
        for rot in (False, True):
            info = imp(SRC8, sheet_size=name, imp_layout=layout, rotate_paper=rot)
            want = expected_sheet(name, layout, rot)
            got = sheet_sizes(info)
            if got != {(round(want[0], 2), round(want[1], 2))}:
                bad.append((name, layout, rot, got, want))
check(not bad, f"every preset prints sheets of exactly its size, portrait/landscape and rotated "
               f"({len(EXPECTED) * 6} imposed PDFs) {bad[:3]}")
for unit, (w, h) in (("pt", (650, 950)), ("in", (9.25, 13.5)), ("mm", (230.5, 340.25)), ("cm", (23.05, 34.025))):
    info = imp(SRC8, sheet_size="Custom", sheet_w=w, sheet_h=h, sheet_unit=unit,
               imp_layout="Quarto - 4 pages per side")
    want = (w * UNITS[unit], h * UNITS[unit])
    got = sheet_sizes(info).pop()
    check(close(got[0], min(want)) and close(got[1], max(want)), f"custom {w} x {h} {unit} prints {got} pt")
# every layout and path on a few papers, with marks, single-sided and rotated backs
paths_bad = []
for name in ("Letter", "A4", "Ledger (17 x 11)", "ID-1", "B5", "Arch A"):
    for layout in LAYOUT_NAMES:
        for printer in ("Duplex (two-sided printer)", "Single-sided (fronts and backs files)"):
            info = imp(numbered(20), sheet_size=name, imp_layout=layout, printer_type=printer, rotate_back=True,
                       cut_marks=True, edge_marks=True, sewing_marks=True, fold_marks=True)
            want = expected_sheet(name, layout)
            if sheet_sizes(info) != {(round(want[0], 2), round(want[1], 2))}:
                paths_bad.append((name, layout, printer))
check(not paths_bad, f"all {len(LAYOUT_NAMES)} layouts, duplex and single-sided, rotated backs and all marks print "
                     f"the right sheet size on 6 different papers {paths_bad[:3]}")
for fmt in SIG_FORMATS:
    info = imp(numbered(40), sheet_size="A4", sig_format=fmt, sig_sheets=3, sig_custom="2, 3")
    check(info["sheets"] >= 10 and sheet_sizes(info) == {(841.89, 595.28)}, f"{fmt}: {info['sheets']} A4 sheets")

# the finished page size never follows the printer paper
s0 = dict(DEFAULTS, source_mode="paste", toc=False, fmt_impose=True, page_size="Half Letter / Digest (5.5 x 8.5 in)")
book_text = "Chapter 1\n\n" + "Some words here. " * 400 + "\n\nChapter 2\n\n" + "More words. " * 400
for name in ("Letter", "A0", "ID-1", "Custom"):
    s = dict(s0, sheet_size=name, sheet_w=500, sheet_h=700, sheet_unit="pt")
    out = os.path.join(TMP, f"pages_{len(os.listdir(TMP))}.pdf")
    build_pdf(apply_info(load_book(s, book_text), s), s, out, log=lambda m: None)
    sizes = {(round(float(p.mediabox.width), 2), round(float(p.mediabox.height), 2)) for p in PdfReader(out).pages}
    check(sizes == {(396.0, 612.0)} and page_size_inches(s) == (5.5, 8.5),
          f"book pages stay 5.5 x 8.5 in with {name} printer paper")
s = dict(s0, sheet_size="A4", sheet_unit="mm", out_dir=os.path.join(TMP, "notes"), open_when_done=False)
_f, made, notes = run_build(apply_info(load_book(s, book_text), s), s, lambda m: None)
txt = open(os.path.join(_f, "READ ME - printing notes.txt"), encoding="utf-8").read()
check("A4 (210.0 × 297.0 mm) paper, printed 11.69 x 8.268 in" in txt, "printing notes give the paper and its size")

# ---------------------------------------------------------------- 4. blank pages: the numbers allowed
for v, n in ((0, 0), (3, 3), ("12", 12), (" 7 ", 7), (BLANK_PAGES_MAX, BLANK_PAGES_MAX), (2.0, 2)):
    check(parse_blank_count(v) == n, f"blank pages {v!r} -> {n}")
for v in (-1, "-2", "1.5", 1.5, "abc", "", None, float("inf"), float("nan"), BLANK_PAGES_MAX + 1, "1e3", True):
    try:
        parse_blank_count(v)
        check(False, f"blank pages {v!r} refused")
    except ValueError as e:
        check(True, f"blank pages {v!r} refused: {e}")


# ---------------------------------------------------------------- 5. blank pages in the typeset book
def typeset(**kw):
    s = dict(DEFAULTS, source_mode="paste", toc=True, fmt_impose=False, running_heads=True,
             page_size="Half Letter / Digest (5.5 x 8.5 in)")
    s.update(kw)
    out = os.path.join(TMP, f"book_{len(os.listdir(TMP))}.pdf")
    text = "".join(f"\n\nChapter {k}\n\n" + "Words in this chapter go on and on for a while. " * 200
                   for k in range(1, 4))
    n = build_pdf(apply_info(load_book(s, text), s), s, out, log=lambda m: None)
    with pdfplumber.open(out) as pdf:
        pages = [{"text": (p.extract_text() or "").strip(), "marks": len(p.chars) + len(p.images) + len(p.lines) +
                  len(p.rects) + len(p.curves), "foot": [w["text"] for w in p.extract_words()
                                                         if w["top"] > p.height - 50]} for p in pdf.pages]
    return n, pages


n0, base = typeset(running_heads=False)      # running heads follow left/right pages, which odd counts swap
for a, b in ((2, 0), (0, 3), (2, 3), (5, 5)):
    n, pages = typeset(blank_pages_start=a, blank_pages_end=b, running_heads=False)
    blank = pages[:a] + (pages[len(pages) - b:] if b else [])
    check(n == n0 + a + b, f"{a} at the beginning, {b} at the end: {n} pages (book alone: {n0})")
    check(all(p["marks"] == 0 for p in blank), "the added pages are completely empty (no text, number or lines)")
    check([p["text"] for p in pages[a:len(pages) - b]] == [p["text"] for p in base],
          "every page of the book is still there, in order, with the same page numbers")
# numbering policies
for mode, want in (("Every page (title page = 1)", "1"), ("Roman front matter, 1 on first chapter", "i")):
    n, pages = typeset(blank_pages_start=2, pn_mode=mode)
    check(pages[2]["foot"][-1:] == [want] and not pages[0]["text"],
          f"{mode}: the title page after the blanks is still {want!r}")
n, pages = typeset(blank_pages_start=2, pn_mode="Start at 1 on first chapter")
check(pages[4]["foot"][-1:] == ["1"], "Start at 1 on first chapter: the first chapter is still 1")
n, pages = typeset(blank_pages_start=2)
toc = pages[3]["text"]
starts = {}
for i, p in enumerate(pages[4:], 4):                  # first page that starts with each chapter's title
    m = re.match(r"Chapter (\d)\n", p["text"] + "\n")
    if m:
        starts.setdefault(int(m.group(1)), i)
check(all(re.search(rf"Chapter {k} {pages[i]['foot'][-1]}\b", toc) for k, i in starts.items()),
      "contents page numbers match the numbers printed on the chapters")
n, pages = typeset(blank_pages_start=1, chapter_start="Right-hand page", title_page=False, toc=False,
                   bookplate="None")
check(n % 2 == 0 and pages[2]["text"].startswith("Chapter 1") and not pages[1]["text"],
      "with 'chapters start on a right-hand page', the first chapter still opens on a right-hand page")
n, pages = typeset(blank_pages_end=2, notes_pages=1, the_end=True)
check(pages[-3]["text"].startswith("Notes") and not pages[-1]["text"] and not pages[-2]["text"],
      "end blanks come after the notes pages")
try:
    typeset(blank_pages_start=-1)
    check(False, "a negative number of blank pages is refused")
except ValueError as e:
    check("negative" in str(e), f"a negative number of blank pages is refused: {e}")

# ---------------------------------------------------------------- 6. blank pages through every layout
# The imposition takes the book's pages as they are: a book with blank pages must be imposed exactly like
# the same book with those pages marked B1, B2... (every page of the book in the same place, the blank pages
# where the marks are, padding computed on the whole book).


def tokens(info):
    """Every character on the printed sheets: (file, side, char, x, y)."""
    out = []
    for f in info["files"]:
        with pdfplumber.open(f) as pdf:
            for i, pg in enumerate(pdf.pages):
                for c in pg.chars:
                    out.append((os.path.basename(f)[-12:], i, c["text"], round(c["x0"]), round(c["top"])))
    return sorted(out)


layout_bad, checked = [], 0
for layout in LAYOUT_NAMES:
    fmts = SIG_FORMATS if layout in FOLD_LAYOUTS else ["Standard signatures"]
    for fmt in fmts:
        for a, b in ((0, 0), (3, 0), (0, 2), (3, 2)):
            n = 13
            marked = numbered(n + a + b, blanks=set(range(a)) | set(range(n + a, n + a + b)))
            plain = numbered(n)
            add_blank_pages(plain, a, b, 5.5 * 72, 8.5 * 72)
            kw = dict(imp_layout=layout, sig_format=fmt, sig_sheets=2, sig_custom="1, 2", flyleafs=1)
            ia, ib = imp(plain, **kw), imp(marked, **kw)
            ta = tokens(ia)
            tb_all = tokens(ib)
            # the marked book's B pages: their characters are the only extra ones
            extra = [t for t in tb_all if t not in ta]
            checked += 1
            pages_on_sheets = sum(1 for t in ta if t[2] == "P")          # one "P" per book page
            zine = layout.startswith("Single-sheet zine")                  # holds 8 places only
            if [t for t in tb_all if t not in extra] != ta or ia["sheets"] != ib["sheets"] or \
                    ia["blanks"] != ib["blanks"] or (not zine and pages_on_sheets != n) or \
                    (not zine and sum(1 for t in extra if t[2] == "B") != a + b):
                layout_bad.append((layout, fmt, a, b, pages_on_sheets, len(extra)))
check(not layout_bad, f"blank pages are imposed as real pages in every layout and signature format "
                      f"({checked} combinations, flyleafs and padding on top) {layout_bad[:3]}")

# kept PDF + blank pages, through the whole build
src = numbered(10)
s = dict(DEFAULTS, source_mode="file", source_path=src, blank_pages_start=2, blank_pages_end=1, fmt_impose=True,
         out_dir=os.path.join(TMP, "kept"), open_when_done=False, imp_layout="Quarto - 4 pages per side")
_f, made, notes = run_build(apply_info(load_book(s), s), s, lambda m: None)
prn = next(m for m in made if m.endswith("Print.pdf"))
with pdfplumber.open(prn) as pdf:
    seq = [(p.extract_text() or "").strip() for p in pdf.pages]
check(seq == ["", ""] + [f"P{i}" for i in range(1, 11)] + [""], f"a PDF kept as it is gets its blank pages {seq}")
check(any("Blank pages you added: 2 at the beginning and 1 at the end" in x for x in notes),
      "the printing notes mention the added blank pages")

# unusable settings stop the build before any file is written
for bad, word in (({"sheet_size": "Custom", "sheet_unit": "mm", "sheet_w": 0, "sheet_h": 297}, "more than 0"),
                  ({"sheet_size": "Custom", "sheet_unit": "cm", "sheet_w": 600, "sheet_h": 30}, "at most"),
                  ({"blank_pages_end": -3}, "negative")):
    out = os.path.join(TMP, "refused")
    s = dict(DEFAULTS, source_mode="paste", fmt_pdf=True, fmt_impose=True, fmt_epub=True, out_dir=out,
             open_when_done=False, **bad)
    try:
        run_build(apply_info(load_book(s, book_text), s), s, lambda m: None)
        msg = ""
    except ValueError as e:
        msg = str(e)
    check(word in msg and not os.path.exists(out), f"refused before anything is written: {msg!r}")

# ---------------------------------------------------------------- 7. projects keep the settings
s = dict(DEFAULTS, source_mode="paste", blank_pages_start=4, blank_pages_end=2, sheet_size="Custom",
         sheet_unit="mm", sheet_w=230.5, sheet_h=340.25)
book = apply_info(load_book(s, book_text), s)
pj = os.path.join(TMP, "p.bookforge")
bf_edit.save_project(pj, book, s, "1.6.0")
_b, s2 = bf_edit.load_project(pj)
check(all(s2[k] == s[k] for k in ("blank_pages_start", "blank_pages_end", "sheet_size", "sheet_unit", "sheet_w",
                                  "sheet_h")), "projects keep blank pages, paper, unit and custom size")
data = json.load(open(pj, encoding="utf-8"))
for k in ("blank_pages_start", "blank_pages_end"):
    data["settings"].pop(k)
json.dump(data, open(pj, "w", encoding="utf-8"))
_b, s3 = bf_edit.load_project(pj)
check("blank_pages_start" not in s3 and parse_blank_count(dict(DEFAULTS, **s3).get("blank_pages_start")) == 0,
      "a project from before blank pages existed opens with none")

# ---------------------------------------------------------------- 8. the window (needs a display)
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as e:                     # noqa: BLE001
    have_display = False
    print(f"SKIP  window checks (no display: {e})")

if have_display:
    import time
    from tkinter import messagebox
    SAID = []
    for k in ("askyesno", "askyesnocancel", "showinfo", "showerror", "showwarning", "askokcancel"):
        setattr(messagebox, k, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, message)) or True))(k))
    import BookForge as BF
    app = BF.App()
    errors = []
    app.report_callback_exception = lambda *a: errors.append(a[1])

    def pump(sec=0.3):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    pump()
    check([app.shelf.on_select is not None, len(app.pages)] == [True, 7], "seven steps in the window")
    for i, (key, _l, _c) in enumerate(th.TABS):
        app.shelf.select(i)
        pump(0.1)
        check(app.cur_page == i, f"step {i + 1} opens")
    app.shelf.select(th.tab_index("out"))
    pump()
    app.var("sheet_size").set("Letter")
    app.var("sheet_unit").set("in")
    pump()
    check(app.paper_lbl.cget("text") == "Paper size: Letter (8.5 × 11.0 inches)", app.paper_lbl.cget("text"))
    # the custom size is off until "Use a custom paper size" is ticked
    states = lambda: [str(e.cget("state")) for e in app.sheet_entries]          # noqa: E731
    check(not app.custom_paper_on.get() and states() == ["disabled", "disabled"] and app.sheet_msg.cget("text") == "",
          "a preset is chosen: the tick box is off and the custom size boxes are greyed out")
    app.sheet_w_text.set("99")
    pump()
    check(app.var("sheet_size").get() == "Letter" and app.var("sheet_w").get() == 8.5,
          "text put in the greyed-out boxes is not used")
    app.custom_paper_on.set(True)
    app._custom_paper_toggled()
    pump()
    check(app.var("sheet_size").get() == "Custom" and states() == ["normal", "normal"] and
          app.paper_lbl.cget("text").startswith("Paper size: Custom ("),
          "ticking the box sets Paper size to Custom and opens the boxes")
    app.custom_paper_on.set(False)
    app._custom_paper_toggled()
    pump()
    check(app.var("sheet_size").get() == "Letter" and states() == ["disabled", "disabled"] and
          sheet_points(app.collect()) == (612.0, 792.0), "unticking goes back to the paper chosen before (Letter)")
    app.var("sheet_size").set("A5")
    pump()
    app.var("sheet_size").set("Custom")
    pump()
    check(app.custom_paper_on.get() and states() == ["normal", "normal"], "choosing Custom in the list ticks the box")
    app.custom_paper_on.set(False)
    app._custom_paper_toggled()
    pump()
    check(app.var("sheet_size").get() == "A5", "unticking after choosing Custom in the list goes back to A5")
    app.var("sheet_size").set("Letter")
    pump()
    app.unit_disp.set("Millimeters")
    app._paper_unit_chosen()
    pump()
    check(app.paper_lbl.cget("text") == "Paper size: Letter (215.9 × 279.4 mm)" and
          app.var("sheet_unit").get() == "mm", "choosing millimetres shows Letter in mm")
    app.var("sheet_size").set("Custom")
    app.sheet_w_text.set("230.5")
    app.sheet_h_text.set("340.25")
    pump()
    want = (230.5 * UNITS["mm"], 340.25 * UNITS["mm"])
    check(all(close(a, b, 1e-9) for a, b in zip(sheet_points(app.collect()), want)), "custom size typed in mm")
    for _ in range(30):
        for name in ("Points", "Inches", "Centimeters", "Millimeters"):
            app.unit_disp.set(name)
            app._paper_unit_chosen()
    pump()
    check(all(close(a, b, 1e-9) for a, b in zip(sheet_points(app.collect()), want)) and
          app.sheet_w_text.get() == "230.5", "120 unit changes: same custom paper, same numbers shown")
    app.sheet_w_text.set("-5")
    pump()
    check(all(close(a, b, 1e-9) for a, b in zip(sheet_points(app.collect()), want)) and
          "more than 0" in app.sheet_msg.cget("text") and "is kept" in app.sheet_msg.cget("text"),
          "an invalid width keeps the last valid size and says so")
    n = len(SAID)
    app.build()
    pump()
    check(len(SAID) == n + 1 and "custom paper" in SAID[-1][1].lower() and not app.busy,
          "making the book is stopped with a message while the custom size is invalid")
    app.sheet_w_text.set("230.5")
    pump()
    check(app.sheet_msg.cget("text") == BF.SHEET_CUSTOM_HINT and str(app.sheet_msg.cget("foreground")) == ""
          and app.sheet_unit_lbl.cget("text") == "mm", "a valid size puts the hint back")
    app.var("sheet_size").set("A4")
    pump()
    check(app.var("sheet_w").get() == 230.5 and not app.custom_paper_on.get() and
          sheet_points(app.collect()) == SHEETS["A4"],
          "choosing a preset unticks the box and uses the preset; the custom size is kept for later")
    app.custom_paper_on.set(True)
    app._custom_paper_toggled()
    pump()
    check(app.sheet_w_text.get() == "230.5" and app.var("sheet_size").get() == "Custom",
          "ticking the box again brings the kept custom size back")
    app.custom_paper_on.set(False)
    app._custom_paper_toggled()
    pump()
    app.apply(dict(app.collect(), sheet_size="Custom"))
    pump()
    check(app.custom_paper_on.get() and [str(e.cget("state")) for e in app.sheet_entries] == ["normal", "normal"],
          "settings or a project with a custom paper size open with the box ticked")
    app.custom_paper_on.set(False)
    app._custom_paper_toggled()
    pump()
    app.shelf.select(th.tab_index("front"))
    pump()
    app.var("blank_pages_start").set(3)
    app.tk.globalsetvar(str(app.var("blank_pages_end")), "1.5")
    pump()
    check("whole number" in app.blank_msgs["end"].cget("text"), "a fractional number of blank pages is pointed out")
    n = len(SAID)
    app.preview_book()
    pump()
    check(len(SAID) == n + 1 and "Blank pages at end" in SAID[-1][1] and not app.busy,
          "the preview is stopped with a message for an invalid number of blank pages")
    app.var("blank_pages_end").set(2)
    pump()
    check(app.blank_msgs["end"].cget("text") == app.blank_hints["end"] and "No page numbers" in app.blank_hints["end"]
          and str(app.blank_msgs["end"].cget("foreground")) == "", "the message goes back to the hint once the number is fine")
    check(app.collect()["blank_pages_start"] == 3 and app.collect()["blank_pages_end"] == 2,
          "the blank-page settings are read")
    app.busy = False
    app.destroy()
    check(not errors, f"no window errors {errors[:1]}")

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
