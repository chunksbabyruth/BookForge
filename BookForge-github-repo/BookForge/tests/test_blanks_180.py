"""Checks for blank pages in 1.8.0 (plain Python - run: python tests/test_blanks_180.py).

1. Typesetting: no page is left empty unless something asked for it. Each case below made an empty page in
   the print PDF (and so on the printed sheets) before 1.8.0:
   - a picture, a dedication-style line or the fanfic summary/notes ending at the bottom of a page: the space
     after it moved to a page of its own, and the next chapter / contents started on the page after that;
   - a chapter with no title that starts with a picture on a page of its own: an empty page before it;
   - a long author's note (kept with its label) right after a full page - a picture on a page of its own at
     the end of a chapter, or text ending at the bottom of a page: the small space before the note moved to a
     page of its own and the note was pushed past it;
   - "Drop chapter start down" with a long first paragraph (fixed in 1.8.0 Phase 3, checked again here with
     headings, untitled chapters, pictures, consecutive chapters, right-hand starts and Continuous).
   Blank pages that were asked for stay: "Blank pages at beginning/end", the left-hand page before a right-hand
   start, the back of the front cover picture. BookForge reports any other empty page it makes.
2. Imposition: "Custom signature sizes" no longer makes signatures of nothing but blank pages; each signature
   keeps its size; padding only completes the last signature; flyleafs at both ends; every page once and in
   order on the real printed sheets (rendered, every file: aggregated, per signature, duplex, single-sided);
   the printing notes count padding and flyleafs separately and correctly.
3. Preview = print PDF = imposed PDF with all of the above.
4. The window: the preview shows the empty-page warning; merging a chapter keeps its typed contents page number.
Window checks run only where a display is available. Nothing needs the internet.
"""
import copy
import io
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_blanks_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
import pypdfium2 as pdfium                                            # noqa: E402
from PIL import Image                                                 # noqa: E402
from reportlab.pdfgen import canvas                                   # noqa: E402

import bf_impose                                                      # noqa: E402
import bf_matter                                                      # noqa: E402
from bf_build import build_preview, run_build, padding_note           # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, page_size_inches  # noqa: E402
from bf_pdf import build_pdf                                          # noqa: E402

FAILS = []
MM = "Mass Market (4.25 x 6.87 in)"


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def settings(**kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP), page_size=MM, toc=False, title_page=False,
             bookplate="None")
    s.update(kw)
    return s


def png(w, h, color=(200, 40, 40)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


PIC = png(300, 200)


def kinds(path, s):
    """'T' (something in the text area: text, a picture or a line) or '_' (nothing at all) for every page.
    The page number and running head are outside the text area."""
    W, H = (v * 72 for v in page_size_inches(s))
    top, bot = float(s["margin_top"]) * 72, H - float(s["margin_bottom"]) * 72
    out = ""
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            inside = lambda o: o["bottom"] > top + 0.5 and o["top"] < bot - 0.5      # noqa: E731
            has = any(inside(c) and c["text"].strip() for c in pg.chars) or any(inside(i) for i in pg.images) \
                or any(inside(x) for x in pg.lines + pg.rects + pg.curves)
            out += "T" if has else "_"
    return out


def make(book, s, name):
    path = os.path.join(TMP, name + ".pdf")
    logs = []
    build_pdf(apply_info(book, s), s, path, log=logs.append)
    return path, kinds(path, s), logs


def starts(book):
    return [p for _id, p in book._chapter_pages]


def planned_versos_only(k):
    """Right-hand starts: every blank page is a left-hand (even) page between two pages with something on them."""
    return all(p % 2 == 0 and 1 < p < len(k) and k[p - 2] == "T" and k[p] == "T"
               for p in (i + 1 for i, x in enumerate(k) if x == "_"))


def chapter2(n=30):
    return Chapter("Chapter Two", blocks=[Block("para", text="Second chapter text. " * n)])


# ============================================================================ 1. typesetting
# 1a. a picture at the very end of a chapter, its bottom just above the bottom of the page
for start, want in (("New page", "TT"), ("Right-hand page", "T_T"), ("Continuous", "TT")):
    b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="word " * 72),
                                                                  Block("image", image=PIC, image_name="p.png",
                                                                        img_width=36)]),
                                  Chapter("Chapter Two", blocks=[Block("para", text="Two. " * 30)])])
    s = settings(chapter_start=start)
    _p, k, logs = make(b, s, f"pic_end_{start[:3]}")
    check(k == want and b._empty_pages == [] and not any("nothing printed" in m for m in logs),
          f"{start}: a picture ending a chapter at the bottom of a page leaves no empty page ({k}, want {want})")
    if start == "Right-hand page":
        check(starts(b) == [1, 3], "... and with right-hand starts chapter 2 still opens on page 3 (page 2 is the "
                                   "planned blank left-hand page)")

# 1b. a dedication-style line ending a chapter at the bottom of a page
b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Filler text of the first chapter. " * 4),
                                                              Block("para", text="word " * 154),
                                                              Block("ded", text="dedication style text")]), chapter2()])
_p, k, _l = make(b, settings(chapter_start="New page"), "ded_end")
check("_" not in k and len(starts(b)) == 2 and b._empty_pages == [],
      f"a dedication-style line ending a chapter at the bottom of a page leaves no empty page ({k})")


# 1c. the fanfic summary and notes ending at the bottom of a page (space after them, or a line's own space
# after already reaching below the bottom)
def fic_book(n):
    return Book(title="T", fic_meta=["<b>Rating:</b> G"] * 3,
                fic_summary=[Block("para", text="sum " * n, label="Summary")],
                fic_notes=[Block("para", text="note " * (n // 2), label="Notes")],
                chapters=[Chapter("One", blocks=[Block("para", text="One. " * 30)])])


for n in (55, 135):
    for toc in (True, False):
        b = fic_book(n)
        s = settings(chapter_start="New page", toc=toc, title_page=True, fic_info="Add a work info page")
        _p, k, _l = make(b, s, f"fic_{n}_{toc}")
        check("_" not in k and b._empty_pages == [],
              f"fanfic summary + notes ({n} words) ending at the bottom of a page, contents {'on' if toc else 'off'}: "
              f"no empty page before the {'contents' if toc else 'first chapter'} ({k})")

# 1d. chapters with no title that start with a picture on a page of its own (or edge to edge)
for place in ("page", "full"):
    for start in ("New page", "Right-hand page", "Continuous"):
        for sink in (0.0, 1.0):
            chs = [Chapter("", blocks=[Block("image", image=PIC, image_name="p.png", img_place=place),
                                       Block("para", text="After the picture. " * 40)]) for _ in range(3)]
            b = Book(title="T", chapters=chs)
            s = settings(chapter_start=start, chapter_sink=sink, chapter_label="None", toc=True, title_page=True)
            path, k, _l = make(b, s, f"pic_first_{place}_{start[:3]}_{sink}")
            with pdfplumber.open(path) as pdf:
                pic_pages = [i + 1 for i, pg in enumerate(pdf.pages) if pg.images]
            ok = pic_pages == starts(b) and b._empty_pages == []
            if start == "Right-hand page":
                ok = ok and all(p % 2 == 1 for p in pic_pages) and planned_versos_only(k)
            else:
                ok = ok and "_" not in k
            check(ok, f"{place} picture opening an untitled chapter, {start}, drop {sink:g} in: the picture is on "
                      f"the chapter's first page, no empty page before it {pic_pages} vs {starts(b)} ({k})")

# 1e. "Drop chapter start down" with long and short first paragraphs, headings, untitled chapters, pictures,
# consecutive chapters, parts, right-hand starts and Continuous
FIRST = {"long": [Block("para", text="Long opening words. " * 400)],
         "short": [Block("para", text="Short."), Block("para", text="More words. " * 300)],
         "heading": [Block("head", text="Inner Heading"), Block("para", text="After the heading. " * 300)],
         "picture": [Block("image", image=PIC, image_name="p.png", img_width=60),
                     Block("para", text="After the picture. " * 300)]}
bad = []
for start in ("New page", "Right-hand page", "Continuous"):
    for sink in (0.0, 1.0):
        for first in FIRST:
            for titled in (True, False):
                for part in (False, True):
                    chs = ([Chapter("A Part", label="Part One", level=0)] if part else []) + \
                        [Chapter(f"Title {i}" if titled else "", blocks=list(FIRST[first])) for i in range(3)]
                    b = Book(title="T", chapters=chs)
                    s = settings(chapter_start=start, chapter_sink=sink, toc=True, title_page=True,
                                 chapter_label="Chapter One" if titled else "None")
                    path, k, _l = make(b, s, "sink")
                    st = starts(b)
                    blanks_ok = planned_versos_only(k) if start == "Right-hand page" else "_" not in k
                    order_ok = st == sorted(st) and len(set(st)) == len(st)
                    if start == "Right-hand page":
                        order_ok = order_ok and all(p % 2 for p in st)
                    if not blanks_ok or b._empty_pages or not order_ok:
                        bad.append((start, sink, first, titled, part, k, st, b._empty_pages))
check(not bad, f"drop chapter start down 0 / 1 in x long, short, heading, picture first x titled / untitled x "
               f"with / without a part x every chapter start: no empty page, chapters in order "
               f"({len(FIRST) * 24} books) {bad[:2]}")
b = Book(title="T", chapters=[Chapter(f"Title {i}", blocks=list(FIRST["long"])) for i in range(3)])
s1 = settings(chapter_start="New page", chapter_sink=1.0, toc=False, title_page=False)
_p, k1, _l = make(b, s1, "sink_new")
st1 = starts(b)
b0 = Book(title="T", chapters=[Chapter(f"Title {i}", blocks=list(FIRST["long"])) for i in range(3)])
_p, k0, _l = make(b0, settings(chapter_start="New page", chapter_sink=0.0), "sink_none")
check(st1[0] == 1 and "_" not in k1 and len(st1) == 3 and k1.count("T") >= k0.count("T"),
      f"the Phase 1 case: drop 1 in + long first paragraphs, each chapter starts on its own first page {st1}")

# 1f. blank pages that were asked for stay where they belong
b = Book(title="T", cover_front=PIC, chapters=[Chapter(f"Chapter {i}", blocks=[Block("para", text="Words. " * (40 + 150 * i))])
                                               for i in range(4)])
s = settings(chapter_start="Right-hand page", blank_pages_start="2", blank_pages_end="3", cover_art_in_book=True,
             cover_front_image=os.path.join(TMP, "missing.png"), notes_pages=2, toc=True, title_page=True)
path, k, _l = make(b, s, "asked")
st = starts(b)
versos = [i + 1 for i, x in enumerate(k) if x == "_" and 4 < i + 1 <= len(k) - 3]
check(k[:2] == "__" and k[-3:] == "___" and k[2] == "T" and k[3] == "_",
      f"blank pages at the beginning (2) and end (3) and the back of the cover picture stay blank ({k})")
check(all(p % 2 for p in st) and versos and planned_versos_only("TTTT" + k[4:-3] + "T"),
      f"right-hand starts: chapters on odd pages {st}, the blank left-hand pages before them {versos} stay")
check(b._empty_pages == [], "... and none of these planned blank pages is reported as a problem")

# 1g. an empty page nobody asked for is reported (an empty, untitled chapter)
b = Book(title="T", chapters=[Chapter("One", blocks=[Block("para", text="Text. " * 30)]), Chapter("", blocks=[]),
                              Chapter("Three", blocks=[Block("para", text="Text. " * 30)])])
s = settings(chapter_start="New page", chapter_label="None")
_p, k, logs = make(b, s, "reported")
check(b._empty_pages == [2] and k[1] == "_" and any(m.startswith("WARNING: page 2 ") for m in logs),
      f"an empty page nobody asked for (an empty chapter) is reported in the log: {b._empty_pages}")
res = build_preview(b, dict(s), log=lambda m: None)
check(res.get("empty_pages") == [2], "... and in the preview's result")
s.update(fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False, fmt_docx=False, fmt_html=False,
         fmt_txt=False)
_f, _m, notes = run_build(b, dict(s), log=lambda m: None)
check(any(n.startswith("WARNING: page 2 ") and "nothing printed" in n for n in notes),
      "... and in the printing notes of the files made")


# 1h. a long author's note (kept with its label) right after a page that is already full: a picture on a page
# of its own / edge to edge at the end of a chapter, or the chapter's text ending at the bottom of a page
NOTE = Block("anote", text="End note. " * 60, label="Chapter End Notes")
bad = []
for place in ("page", "full"):
    for start in ("New page", "Continuous"):
        b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Words of the chapter. " * 260),
                                                                      Block("image", image=PIC, image_name="p.png",
                                                                            img_place=place), NOTE]), chapter2()])
        _p, k, _l = make(b, settings(chapter_start=start, toc=True, title_page=True), "pic_note")
        if "_" in k or b._empty_pages:
            bad.append((place, start, k))
check(not bad, f"a long author's note after a picture on a page of its own / edge to edge leaves no empty page {bad}")
# (line spacing 1.5: the last line of a full page leaves less than the paragraph's space after + 4 pt; the
# chapter's text then ends on every line of a page in turn)
bad = []
for words in range(150, 300, 3):
    b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Lots of words here. " * words),
                                                                  NOTE]), chapter2()])
    _p, k, _l = make(b, settings(chapter_start="New page", line_spacing=1.5), "text_note")
    if "_" in k or b._empty_pages:
        bad.append((words, k))
check(not bad, f"a long author's note after text ending anywhere on a page (50 lengths) leaves no empty page {bad[:3]}")
b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Lots of words here. " * 318),
                                                              Block("anote", text="End note. " * 400,
                                                                    label="Chapter End Notes")]), chapter2()])
_p, k, _l = make(b, settings(chapter_start="New page", page_size="Letter (8.5 x 11 in)"), "text_note_letter")
check("_" not in k and b._empty_pages == [],
      f"... and with the default page size (Letter), text ending on a page's last line, a page-long note ({k})")


# 1i. THE END emptied in Specific Text Edit (and "Print THE END" still on): nothing is printed, as in the other
# formats - its space alone used to move to a last page of its own when the book's text ended at the bottom
bad = []
for words in range(60, 150, 2):
    b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Lots of words here. " * words)])])
    for ov in ([], [Block("endline", text="")]):
        bf_matter.set_override(b, "the_end", ov)
        _p, k, _l = make(b, settings(chapter_start="New page", the_end=True), "end_empty")
        if "_" in k or b._empty_pages:
            bad.append((words, len(ov), k))
check(not bad, f"THE END emptied: no empty last page, whatever line the book's text ends on (45 lengths) {bad[:3]}")
b = Book(title="T", chapters=[Chapter("Chapter One", blocks=[Block("para", text="Lots of words here. " * 86)])])
texts = []
for ov in (None, [Block("endline", text="<b>FIN</b>")]):
    if ov:
        bf_matter.set_override(b, "the_end", ov)
    path, k, _l = make(b, settings(chapter_start="New page", the_end=True), "end_kept")
    with pdfplumber.open(path) as pdf:
        texts.append(pdf.pages[-1].extract_text() or "")
check("THE END" in texts[0] and "FIN" in texts[1],
      f"... and THE END as it is, or edited to other words, is still printed ({[t[-12:] for t in texts]})")


# ============================================================================ 2. imposition
def colour(i):
    return (40 + (i % 6) * 40, 40 + ((i // 6) % 6) * 40, 40 + ((i // 36) % 6) * 40)


def coloured(n, w=306, h=396):
    """A book PDF whose page i is filled with its own colour (so it is recognised on the rendered sheets)."""
    p = os.path.join(TMP, f"coloured_{n}.pdf")
    if not os.path.exists(p):
        c = canvas.Canvas(p, pagesize=(w, h))
        for i in range(n):
            c.setFillColorRGB(*(v / 255 for v in colour(i)))
            c.rect(0, 0, w, h, stroke=0, fill=1)
            c.showPage()
        c.save()
    return p


def decode(px):
    r, g, b = px[:3]
    if r > 245 and g > 245 and b > 245:
        return None
    k = [round((v - 40) / 40) for v in (r, g, b)]
    return k[0] + 6 * k[1] + 36 * k[2] if all(0 <= x <= 5 for x in k) else "?"


def imp(n, **kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(fmt_impose=True)
    s.update(kw)
    out = tempfile.mkdtemp(dir=TMP)
    info = bf_impose.impose(coloured(n), out, "b", copy.deepcopy(s), log=lambda m: None)
    _i, sides = bf_impose.plan_imposition([(306.0, 396.0)] * n, copy.deepcopy(s), log=lambda m: None)
    return s, out, info, sides


def rendered(path, sides_in_file, W, H):
    """What each page space of each printed side shows: book page index, None (blank) or '?'."""
    doc = pdfium.PdfDocument(path)
    got = []
    for k, side in enumerate(sides_in_file):
        pg = doc[k]
        rot = pg.get_rotation()
        img = pg.render(scale=0.4).to_pil()
        row = []
        for it in side["items"]:
            g = it["geo"]
            x, y = g.x + g.w / 2, g.y + g.h / 2
            if rot == 180:
                x, y = W - x, H - y
            row.append(decode(img.getpixel((min(img.width - 1, int(x * 0.4)), min(img.height - 1, int((H - y) * 0.4))))))
        got.append(row)
    doc.close()
    return got


def sequence(sides):
    """The pages of every signature in folding order: [(signature, [ref, ...])]."""
    by = {}
    for side in sides:
        for it in side["items"]:
            by.setdefault(side["sig"], {})[it["sigpage"]] = it["ref"]
    return [(sig, [by[sig][p] for p in sorted(by[sig])]) for sig in sorted(by)]


FOLIO, QUARTO = "Folio - 2 pages per side", "Quarto - 4 pages per side"
# 2a. "4, 4, 6, 6" (sheets per signature) for books of different lengths: only the signatures the book needs,
# each its own size, padding only in the last one, after the book's last page (and before the back flyleafs)
for layout, per_sheet in ((FOLIO, 4), (QUARTO, 8)):
    for n, fly in ((12, 0), (12, 1), (20, 0), (40, 1), (100, 0), (130, 2)):
        need = -(-(n + 4 * fly) // per_sheet)                          # sheets the pages fill
        want, sizes = [], [4, 4, 6, 6]
        while sum(want) < need:
            want.append(sizes[min(len(want), 3)])
        s, out, info, sides = imp(n, imp_layout=layout, sig_format="Custom signature sizes", sig_custom="4, 4, 6, 6",
                                  flyleafs=fly, imp_files="Both aggregated & per-signature files")
        pad = sum(want) * per_sheet - n - 4 * fly
        seq = sequence(sides)
        flat = [r for _s, refs in seq for r in refs]
        pages = [r[1] for r in flat if r[0] == "p"]
        first_p = next(i for i, r in enumerate(flat) if r[0] == "p")
        last_p = max(i for i, r in enumerate(flat) if r[0] == "p")
        check(info["plan"] == want and info["blanks"] == pad and pages == list(range(n)) and first_p == 2 * fly and
              len(flat) - 1 - last_p == pad + 2 * fly and pad < want[-1] * per_sheet and
              all(any(r[0] == "p" for r in refs) for _s, refs in seq),
              f"{layout[:6]}, {n} pages, {fly} flyleaf, custom 4, 4, 6, 6: signatures {info['plan']} (want {want}), "
              f"{info['blanks']} padding pages, flyleafs first and last, every signature holds book pages")
        files = sorted(os.listdir(os.path.join(out, "Signatures")))
        W, H = info["sheet"]
        per_file_ok = len(files) == len(want)
        seen = []
        for si, f in enumerate(files):
            idx = [i for i, sd in enumerate(sides) if sd["sig"] == si]
            path = os.path.join(out, "Signatures", f)
            with pdfplumber.open(path) as pdf:
                per_file_ok = per_file_ok and len(pdf.pages) == 2 * want[si]
            got = rendered(path, [sides[i] for i in idx], W, H)
            exp = [[it["ref"][1] if it["ref"][0] == "p" else None for it in sides[i]["items"]] for i in idx]
            per_file_ok = per_file_ok and got == exp and any(x is not None for r in got for x in r)
            seen += [x for r in got for x in r if x is not None]
        agg = os.path.join(out, "b - Imposed for binding.pdf")
        with pdfplumber.open(agg) as pdf:
            agg_pages = len(pdf.pages)
        check(per_file_ok and sorted(seen) == list(range(n)) and agg_pages == 2 * sum(want),
              f"... each of the {len(files)} signature files has its own size ({[2 * x for x in want]} sides), "
              f"shows its own pages on the rendered sheets and every book page once; the aggregated file has "
              f"{agg_pages} sides")

# 2b. other custom sequences, and the formats that were already right stay the same
for custom, n, want in (("6, 2, 5", 70, [6, 2, 5, 5]), ("6, 2, 5", 30, [6, 2]), ("2, 3", 13, [2, 3]), ("1", 1, [1]),
                        ("3, 3, 3, 3, 3, 3, 3, 3", 40, [3, 3, 3, 3]), ("4", 1, [4])):
    _s, _o, info, _sides = imp(n, imp_layout=FOLIO, sig_format="Custom signature sizes", sig_custom=custom)
    check(info["plan"] == want and info["blanks"] == sum(want) * 4 - n,
          f"custom \"{custom}\", {n} pages (folio): signatures {info['plan']} (want {want}), {info['blanks']} padding")


def old_standard(sheets, size):
    k = -(-sheets // size)
    base, extra = divmod(sheets, k)
    return [base + 1] * extra + [base] * (k - extra)


std_ok = True
for n in range(1, 120, 7):
    for fmt, kw in (("Standard signatures", {"sig_sheets": 3}), ("Standard signatures", {"sig_sheets": 8}),
                    ("Perfect bound (every sheet separate)", {}), ("Booklet (one signature)", {})):
        s = copy.deepcopy(DEFAULTS)
        s.update(imp_layout=FOLIO, sig_format=fmt, **kw)
        info, _sides = bf_impose.plan_imposition([(306.0, 396.0)] * n, s, log=lambda m: None)
        sheets = -(-n // 4)
        want = {"Standard signatures": old_standard(sheets, kw.get("sig_sheets", 8)),
                "Perfect bound (every sheet separate)": [1] * sheets, "Booklet (one signature)": [sheets]}[fmt]
        std_ok = std_ok and info["plan"] == want and info["blanks"] == sheets * 4 - n and info["blanks"] < 4
check(std_ok, "standard, perfect bound and booklet signatures are unchanged (padding always less than one sheet)")

# 2c. single-sided printing, reversed backs, rotated backs, page ranges: the real files show the plan
bad = []
for layout in (FOLIO, QUARTO, "Octavo - 8 pages per side"):
    for printer in ("Duplex (two-sided printer)", "Single-sided (fronts and backs files)",
                    "Single-sided, backs in reverse order"):
        for rng, fly, rotb in (("", 1, False), ("2-9, 15", 0, True)):
            s, out, info, sides = imp(23, imp_layout=layout, sig_format="Custom signature sizes", sig_custom="1, 2",
                                      flyleafs=fly, imp_range=rng, printer_type=printer, rotate_back=rotb,
                                      imp_files="Both aggregated & per-signature files")
            W, H = info["sheet"]
            duplex = not printer.startswith("Single")

            def groups(indices, base):
                if duplex:
                    return [(base + ".pdf", indices)]
                fr = [i for i in indices if sides[i]["front"]]
                bk = [i for i in indices if not sides[i]["front"]]
                if "reverse" in printer:
                    bk.reverse()
                return [(base + " - fronts (print first).pdf", fr), (base + " - backs (print second).pdf", bk)]
            gl = groups(list(range(len(sides))), os.path.join(out, "b - Imposed for binding"))
            for sig in range(info["signatures"]):
                gl += groups([i for i in range(len(sides)) if sides[i]["sig"] == sig],
                             os.path.join(out, "Signatures", f"b - signature {sig + 1:02d}"))
            agg_seen = []
            for path, idx in gl:
                got = rendered(path, [sides[i] for i in idx], W, H)
                exp = [[it["ref"][1] if it["ref"][0] == "p" else None for it in sides[i]["items"]] for i in idx]
                if got != exp:
                    bad.append((layout, printer, rng, os.path.basename(path)))
                if "Imposed" in path:
                    agg_seen += [x for r in got for x in r if x is not None]
            if sorted(agg_seen) != bf_impose.parse_range(rng, 23):
                bad.append((layout, printer, rng, "pages"))
check(not bad, f"duplex, single-sided and reversed backs, rotated backs and page ranges: every printed side of "
               f"every file (aggregated and per signature) shows exactly the planned pages {bad[:2]}")

# 2d. the printing notes count padding and flyleafs separately and correctly
book = Book(title="Notes Book", chapters=[Chapter(f"Chapter {i}", blocks=[Block("para", text="Words. " * 60)])
                                          for i in range(3)])
s = settings(fmt_pdf=True, fmt_impose=True, fmt_cover=False, fmt_epub=False, fmt_docx=False, fmt_html=False,
             fmt_txt=False, imp_layout=FOLIO, sig_format="Custom signature sizes", sig_custom="4, 4, 6, 6", flyleafs=1,
             imp_files="Both aggregated & per-signature files")
logs = []
_f, made, notes = run_build(book, dict(s), log=logs.append)
pages = len(pdfplumber.open(next(m for m in made if m.endswith("Print.pdf"))).pages)
need = -(-(pages + 4) // 4)
plan = []
while sum(plan) < need:
    plan.append([4, 4, 6, 6][min(len(plan), 3)])
pad = sum(plan) * 4 - pages - 4
note = next(n for n in notes if n.startswith("Imposed for binding"))
unit = "sheet" if pad < 4 else "signature"
check((f"{pad} blank page(s) added after the book's last page to complete the last {unit}" in note if pad else
       "no blank pages needed" in note) and "flyleafs: 2 blank page(s) at the beginning and 2 at the end" in note and
      f"{len(plan)} signature(s)" in note and "to fill the last sheet" not in note,
      f"printing notes, custom sizes: {len(plan)} signatures, {pad} padding pages, flyleafs counted apart ({pages} "
      f"book pages)")
check((f"the book needs {len(plan)} of the 4 custom signature sizes" in note) == (len(plan) < 4),
      "... and they say when the book needs fewer signatures than the sizes typed")
sigs = sorted(os.listdir(os.path.join(os.path.dirname(made[0]), "Signatures")))
check(len(sigs) == len(plan), f"... and exactly that many signature files are made ({len(sigs)})")
info = {"signatures": 6, "plan": [1] * 6, "blanks": 1, "per_sheet": 4, "flyleaf_pages": 4, "flyleaf_only": [1, 6],
        "custom": []}
txt = padding_note(info)
check("1 blank page(s) added after the book's last page to complete the last sheet" in txt and
      "signature 1, 6 have no book pages, only flyleaf or padding pages (blank on purpose)" in txt,
      "perfect bound with 2 flyleafs: signatures holding only flyleaf pages are named as blank on purpose")
_s, _o, info, _sd = imp(10, imp_layout=FOLIO, sig_format="Perfect bound (every sheet separate)", flyleafs=2)
check(info["flyleaf_only"] == [1, info["signatures"]] and info["flyleaf_pages"] == 4,
      f"... and the imposition finds them ({info['flyleaf_only']})")

# 2e. a page count from an earlier build is never reused
s2 = dict(s, out_dir=tempfile.mkdtemp(dir=TMP))
book2 = Book(title="Notes Book", chapters=[Chapter(f"Chapter {i}", blocks=[Block("para", text="Words. " * 60)])
                                           for i in range(9)])
_f, made2, notes2 = run_build(book2, dict(s2), log=lambda m: None)
pages2 = len(pdfplumber.open(next(m for m in made2 if m.endswith("Print.pdf"))).pages)
need2 = -(-(pages2 + 4) // 4)
plan2 = []
while sum(plan2) < need2:
    plan2.append([4, 4, 6, 6][min(len(plan2), 3)])
pad2 = sum(plan2) * 4 - pages2 - 4
note2 = next(n for n in notes2 if n.startswith("Imposed for binding"))
check(pages2 != pages and (f"{pad2} blank page(s)" in note2 or (pad2 == 0 and "no blank pages" in note2)) and
      f"{len(plan2)} signature(s)" in note2, f"a second, longer book gets its own counts ({pages2} pages, {plan2})")

# ============================================================================ 3. preview = print = imposed
b = Book(title="Same", fic_meta=["<b>Rating:</b> G"] * 3, fic_summary=[Block("para", text="sum " * 55, label="Summary")],
         fic_notes=[Block("para", text="note " * 27, label="Notes")],
         chapters=[Chapter("", blocks=[Block("image", image=PIC, image_name="p.png", img_place="page"),
                                       Block("para", text="After. " * 200)]),
                   Chapter("Two", blocks=[Block("para", text="word " * 72), Block("image", image=PIC, image_name="p.png",
                                                                                   img_width=36)]),
                   Chapter("Three", blocks=[Block("para", text="Long. " * 600)])])
bf_matter.set_override(b, "dedication", [Block("ded", text="For you")])
s = settings(chapter_start="Right-hand page", chapter_sink=1.0, toc=True, title_page=True, fic_info="Add a work info page",
             fmt_pdf=True, fmt_impose=True, fmt_cover=False, fmt_epub=False, fmt_docx=False, fmt_html=False,
             fmt_txt=False, imp_layout=QUARTO, sig_format="Custom signature sizes", sig_custom="2, 3", flyleafs=1)
res = build_preview(b, dict(s), log=lambda m: None)
_f, made, _n = run_build(b, dict(s), log=lambda m: None)
prn = next(m for m in made if m.endswith("Print.pdf"))
imposed = next(m for m in made if m.endswith("Imposed for binding.pdf"))


def chars(path):
    with pdfplumber.open(path) as pdf:
        return [[(c["text"], round(c["x0"], 2), round(c["top"], 2), c["fontname"].split("+")[-1]) for c in p.chars] +
                [("img", round(i["x0"], 1), round(i["top"], 1)) for i in p.images] for p in pdf.pages]


def renders(path):
    doc = pdfium.PdfDocument(path)
    out = [doc[i].render(scale=0.3).to_pil().tobytes() for i in range(len(doc))]
    doc.close()
    return out


k = kinds(prn, s)
check(chars(prn) == chars(res["pdf"]) and res["empty_pages"] == [] and "__" not in k,
      f"preview = Make the book: same pages, text, fonts and pictures; no empty page ({k})")
check(len(res["sheets"]) == 1 and renders(res["sheets"][0]) == renders(imposed),
      "the imposed sheets of the preview and of Make the book are the same, rendered side by side")

# ============================================================================ 4. the window
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as e:                     # noqa: BLE001
    have_display = False
    print(f"SKIP  window checks (no display: {e})")

if have_display:
    from tkinter import messagebox
    SAID = []
    for kk in ("askyesno", "askyesnocancel", "showinfo", "showerror", "showwarning", "askokcancel"):
        setattr(messagebox, kk, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, title, message))
                                               or True))(kk))
    import BookForge as BF

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

    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + "Words of the chapter. " * 400 + "\n\n"
                                                  for i in range(1, 5)))
    app.scan(force=True)
    idle(60)
    app.book.chapters.insert(1, Chapter("", blocks=[]))        # an empty, untitled chapter: an empty page
    app.var("chapter_label").set("None")
    app.var("toc").set(False)
    idle()
    app.preview_book()
    idle()
    pump(0.3)
    pw = getattr(app, "preview_win", None)
    info_text = str(pw.info.cget("text")) if pw is not None and pw.alive() else ""
    check("WARNING" in info_text and "nothing printed" in info_text,
          "the preview window says when a page of the book has nothing printed on it")
    del app.book.chapters[1]
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    cw.rows[1]["page"] = "42"
    cw.ok()
    pump(0.1)
    app.fill_list()
    app.ctree.selection_set("1")
    app.merge_ch()
    pump(0.1)
    kept = next((e.get("page") for e in app.book.toc or [] if e.get("uid") == app.book.chapters[0].uid), "")
    check("(42) is kept" in str(app.status.cget("text")) and kept == "42",
          "merging a chapter whose contents entry had a typed page number keeps it (on the surviving entry, "
          "1.8.0 Phase 6) and says so")
    # Make the book from the window with custom signature sizes: only the signatures the book needs, and the
    # printing notes count the padding and the flyleafs apart
    outdir = tempfile.mkdtemp(dir=TMP)
    for key, val in dict(out_dir=outdir, open_when_done=False, fmt_pdf=True, fmt_impose=True, fmt_cover=False,
                         fmt_epub=False, fmt_docx=False, fmt_html=False, fmt_txt=False,
                         imp_layout=FOLIO, sig_format="Custom signature sizes", sig_custom="4, 4, 6, 6", flyleafs=1,
                         imp_files="Both aggregated & per-signature files").items():
        app.var(key).set(val)
    idle()
    app.build()
    idle()
    pump(0.2)
    folder = next((os.path.join(r) for r, ds, _fs in os.walk(outdir) if "Signatures" in ds), None)
    prn = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")]
    if folder and prn:
        n_pages = len(pdfplumber.open(prn[0]).pages)
        need = -(-(n_pages + 4) // 4)
        plan = []
        while sum(plan) < need:
            plan.append([4, 4, 6, 6][min(len(plan), 3)])
        files = sorted(os.listdir(os.path.join(folder, "Signatures")))
        notes_txt = open(os.path.join(folder, "READ ME - printing notes.txt"), encoding="utf-8").read()
        pad = sum(plan) * 4 - n_pages - 4
        check(len(files) == len(plan) and "flyleafs: 2 blank page(s) at the beginning and 2 at the end" in notes_txt
              and (f"{pad} blank page(s) added after the book's last page" in notes_txt if pad else True),
              f"Make the book (window), custom 4, 4, 6, 6: {len(files)} signature files for {n_pages} pages "
              f"(want {len(plan)}), padding {pad} and flyleafs in the notes")
    else:
        check(False, "Make the book (window) made the signature files")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
