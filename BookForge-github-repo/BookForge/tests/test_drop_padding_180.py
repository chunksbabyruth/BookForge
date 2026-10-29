"""Checks for 1.8.0 Phase 7 (plain Python - run: python tests/test_drop_padding_180.py).

1. "Drop chapter start down": no empty page before a chapter, wherever its first paragraph ends.
   - The reported case (long first paragraph, drop 1 in): fixed in Phase 3, checked again with the chapter's real
     start page, the title on it and the drop applied.
   - Found in Phase 7: a drop bigger than the page has room for (small pages, or a chapter that opens with a
     tall picture). The title block (or the picture) couldn't follow the drop on the page: the page was left
     with nothing on it but the drop space, or the number line stayed alone at the bottom with the title on the
     next page. Now the drop is never so low that the title block and what the chapter starts with can't
     follow it (as for title and part pages); where it fits, it is exactly as before.
   - Found in Phase 7: in Continuous, a titled chapter whose first paragraph doesn't fit in the rest of the page
     moves to the next page with its title, but its contents page number stayed behind (the page before). It
     now goes with the title; the text layout is unchanged.
   - Short and long first paragraphs, headings, untitled chapters, pictures, drop caps, consecutive chapters,
     right-hand starts (their blank left-hand pages stay), Continuous (unchanged: the drop isn't used there),
     several page sizes and body sizes; preview = print PDF = imposed sheets.
2. Custom signature sizes.
   - Read exactly as typed: whole numbers of sheets ("4, 4, 6, 6", "4 4 6 6"...). Before Phase 7 "4.5, 6" was
     read as three signatures of 4, 5 and 6 sheets, "0" or a word was skipped, and a list without a number quietly
     used the standard signature size. Now such a list stops the preview / build with a plain message.
   - Every signature has exactly its size; only the last one is completed; flyleafs are counted once; the real
     files (aggregated and per signature) have exactly those pages; nothing is carried over from an earlier build.
   - The printing notes keep signature padding apart from flyleafs, from the blank pages you added, and (new)
     from the pages the layout leaves blank on purpose (left-hand pages before right-hand chapter starts, the back
     of the cover picture) - with their page numbers.
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
TMP = tempfile.mkdtemp(prefix="bf_drop_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
import pypdfium2 as pdfium                                            # noqa: E402
from PIL import Image                                                 # noqa: E402

import bf_impose                                                      # noqa: E402
from bf_build import build_preview, run_build                         # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, page_size_inches   # noqa: E402
from bf_pdf import build_pdf                                          # noqa: E402

FAILS = []
FOLIO, QUARTO = "Folio - 2 pages per side", "Quarto - 4 pages per side"
MM, POCKET, A6 = "Mass Market (4.25 x 6.87 in)", "Pocket (4 x 6 in)", "A6 (105 x 148 mm)"
LETTER, DIGEST, TRADE = "Letter (8.5 x 11 in)", "Half Letter / Digest (5.5 x 8.5 in)", "Trade Paperback (6 x 9 in)"


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def settings(**kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP), page_size=MM, toc=False, title_page=False,
             bookplate="None", fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False, fmt_docx=False,
             fmt_html=False, fmt_txt=False)
    s.update(kw)
    return s


def png(w, h, color=(200, 40, 40)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


PIC, TALL = png(300, 200), png(200, 340, (30, 90, 200))


def pages_of(path, s):
    """Per page: (text inside the text area, number of pictures, top of every text line {text: top})."""
    W, H = (v * 72 for v in page_size_inches(s))
    top, bot = float(s["margin_top"]) * 72, H - float(s["margin_bottom"]) * 72
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            inside = [c for c in pg.chars if c["bottom"] > top + 0.5 and c["top"] < bot - 0.5]
            lines = {}
            for c in inside:
                lines.setdefault(round(c["top"], 1), []).append(c["text"])
            imgs = [i for i in pg.images if i["bottom"] > top + 0.5 and i["top"] < bot - 0.5]
            out.append(("".join(c["text"] for c in inside),
                        len(imgs) + sum(1 for i in pg.images if i["width"] >= W - 1),
                        {"".join(v).strip(): t for t, v in sorted(lines.items())}))
    return out


def blank(p):
    return not p[0].strip() and not p[1]


def make(book, s, name):
    path = os.path.join(TMP, name + ".pdf")
    build_pdf(apply_info(book, s), s, path, log=lambda m: None)
    return path, pages_of(path, s)


def starts(book):
    return [p for _id, p in book._chapter_pages]


def title_top(pages, page, text):
    return next((t for line, t in pages[page - 1][2].items() if line.startswith(text)), None)


def planned_only(pages, right_hand):
    """Every empty page is a planned one: none at all, or (right-hand starts) a left-hand page between two pages
    with something on them."""
    for i, p in enumerate(pages, 1):
        if blank(p) and not (right_hand and i % 2 == 0 and 1 < i < len(pages) and not blank(pages[i - 2]) and
                             not blank(pages[i])):
            return False
    return True


def book_of(first, n=3, titled=True):
    return Book(title="T", chapters=[Chapter(f"Title {i}" if titled else "", blocks=first(i)) for i in range(1, n + 1)])


# ============================================================================ 1. drop chapter start down
# 1a. the reported case: a long first paragraph after the drop
LONG = lambda i: [Block("para", text=f"Long opening words {i}. " * 260)]   # noqa: E731
for size in (DIGEST, MM):
    for start in ("New page", "Right-hand page"):
        b0 = book_of(LONG)
        _p, pg0 = make(b0, settings(page_size=size, chapter_start=start, chapter_sink=0.0), "drop0")
        b1 = book_of(LONG)
        _p, pg1 = make(b1, settings(page_size=size, chapter_start=start, chapter_sink=1.0), "drop1")
        st = starts(b1)
        ok = planned_only(pg1, start.startswith("Right")) and b1._empty_pages == [] and len(st) == 3
        for i, p in enumerate(st, 1):
            txt = pg1[p - 1][0]
            t0, t1 = title_top(pg0, starts(b0)[i - 1], f"Title {i}"), title_top(pg1, p, f"Title {i}")
            ok = ok and f"Title {i}" in txt and f"Long opening words {i}." in txt and \
                t0 is not None and t1 is not None and 71 < t1 - t0 < 79   # the drop + the title's own space above
        check(ok and (not start.startswith("Right") or all(x % 2 for x in st)),
              f"{size[:11]}, {start}, drop 1 in, long first paragraphs: no empty page; each chapter starts on the "
              f"page with its title and first words, the title dropped 1 in {st}")

# 1b. first paragraph short / long, headings, no headings, pictures; consecutive chapters; every chapter start;
# two page sizes and two body sizes; the drop on and off
FIRST = {"long": LONG,
         "short": lambda i: [Block("para", text=f"Short {i}."), Block("para", text="More words. " * 200)],
         "heading": lambda i: [Block("head", text=f"Inner Heading {i}"), Block("para", text="After it. " * 200)],
         "picture": lambda i: [Block("image", image=PIC, image_name="p.png", img_width=70),
                               Block("para", text=f"After picture {i}. " * 200)]}
bad, n_books = [], 0
for size in (MM, LETTER):
    for body in (10, 16):
        for start in ("New page", "Right-hand page", "Continuous"):
            for first, mk in FIRST.items():
                for titled in (True, False):
                    if first == "heading" and not titled:
                        continue
                    kinds = {}
                    for sink in (0.0, 1.0):
                        b = book_of(mk, titled=titled)
                        s = settings(page_size=size, body_size=body, chapter_start=start, chapter_sink=sink,
                                     toc=True, title_page=True, chapter_label="Chapter One" if titled else "None")
                        path, pg = make(b, s, "matrix")
                        n_books += 1
                        st = starts(b)
                        cont = start == "Continuous"     # (short chapters can share a page there)
                        ok = planned_only(pg, start.startswith("Right")) and b._empty_pages == [] and \
                            st == sorted(st) and len(st) == 3 and (cont or len(set(st)) == 3)
                        if start.startswith("Right"):
                            ok = ok and all(x % 2 for x in st)
                        if titled:
                            ok = ok and all(f"Title {i}" in pg[p - 1][0] for i, p in enumerate(st, 1))
                        if first == "picture" and not cont:     # (Continuous: it may go on the next page)
                            ok = ok and all(pg[p - 1][1] for p in st)
                        kinds[sink] = [p[0] for p in pg]
                        if not ok:
                            bad.append((size[:6], body, start, first, titled, sink, st))
                    if start == "Continuous" and kinds[0.0] != kinds[1.0]:
                        bad.append((size[:6], body, start, first, titled, "continuous changed"))
check(not bad, f"{n_books} books (2 page sizes x 2 body sizes x every chapter start x long / short / heading / "
               f"picture first x titled / untitled x drop 0 / 1 in): no unexpected empty page, chapters in order, "
               f"each title (and on new pages the opening picture) on its chapter's first page - in Continuous too, "
               f"where the contents used to give the page before; Continuous is unchanged by the drop "
               f"{bad[:3]}")

# 1c. drops bigger than the page has room for (found in Phase 7): small pages, a typed drop above the 4 in the
# spinner allows, a tall opening picture, a big drop cap
TALL_FIRST = lambda i: [Block("image", image=TALL, image_name="t.png", img_width=100),   # noqa: E731
                        Block("para", text=f"After the tall picture {i}. " * 300)]
OPEN_LONG = lambda i: [f"Long opening words {i}."]                                     # noqa: E731
CASES = [("Pocket, drop 4 in, number line + title + ornament", POCKET, 4.0, True, True, LONG, False, OPEN_LONG),
         ("A6, drop 4 in, number line + title", A6, 4.0, True, False, LONG, False, OPEN_LONG),
         ("A6, drop 4 in, no title", A6, 4.0, False, False, LONG, False, OPEN_LONG),
         ("Mass Market, drop 4 in, heading first", MM, 4.0, True, False, FIRST["heading"], False,
          lambda i: [f"Inner Heading {i}", "After it."]),
         ("Mass Market, typed drop 6 in", MM, 6.0, True, True, LONG, False, OPEN_LONG),
         ("Letter, drop 2 in, no title, tall opening picture", LETTER, 2.0, False, False, TALL_FIRST, False, None),
         ("Trade, drop 2 in, title + opening picture (fits under the title, not under title + drop)", TRADE, 2.0,
          True, False, lambda i: [Block("image", image=TALL, image_name="t.png", img_width=75),
                                  Block("para", text=f"After the picture {i}. " * 300)], False, None),
         ("Pocket, drop 3 in, 4-line drop cap", POCKET, 3.0, True, False,
          lambda i: [Block("para", text=f"Dropped capital opening {i}. " * 300)], True,
          lambda i: ["ropped capital", f"opening {i}."])]
for name, size, sink, titled, orn, mk, cap, opening in CASES:
    for start in ("New page", "Right-hand page"):
        b = book_of(mk, titled=titled)
        s = settings(page_size=size, chapter_start=start, chapter_sink=sink, chapter_label="Chapter One" if titled
                     else "None", ornament=orn, drop_cap=cap, drop_cap_lines=4)
        try:
            path, pg = make(b, s, "bigdrop")
        except Exception as e:                 # noqa: BLE001 - (before Phase 7 a typed 6 in drop stopped the book)
            check(False, f"{name}, {start}: the book is made ({type(e).__name__}: {str(e)[:90]})")
            continue
        st = starts(b)
        ok = planned_only(pg, start.startswith("Right")) and b._empty_pages == [] and len(st) == 3
        for i, p in enumerate(st, 1):
            txt = pg[p - 1][0]
            if titled:
                ok = ok and f"Title {i}" in txt and "Chapter" in txt
            if opening is None:                                    # the opening picture, on the same page
                ok = ok and pg[p - 1][1] >= 1
            else:                                                  # the opening lines, on the same page
                ok = ok and all(w in txt for w in opening(i))
        b0 = book_of(mk, titled=titled)
        _p, pg0 = make(b0, settings(page_size=size, chapter_start=start, chapter_sink=0.0,
                                    chapter_label="Chapter One" if titled else "None", ornament=orn, drop_cap=cap,
                                    drop_cap_lines=4), "bigdrop0")
        if titled and "picture" not in name:                   # still dropped, as far as the page allows
            t0, t1 = title_top(pg0, starts(b0)[0], "Title 1"), title_top(pg, st[0], "Title 1")
            ok = ok and t0 is not None and t1 is not None and t1 > t0 + 36
        check(ok, f"{name}, {start}: no empty page; the chapter's title block and what it starts with are on its "
                  f"first page {st}")
# where the drop fits, it is exactly as asked (Letter, 2 in)
b0, b1 = book_of(LONG), book_of(LONG)
_p, pg0 = make(b0, settings(page_size=LETTER, chapter_sink=0.0, chapter_label="Chapter One", ornament=True), "fit0")
_p, pg1 = make(b1, settings(page_size=LETTER, chapter_sink=2.0, chapter_label="Chapter One", ornament=True), "fit2")
t0, t1 = title_top(pg0, starts(b0)[0], "Title 1"), title_top(pg1, starts(b1)[0], "Title 1")
check(t0 is not None and t1 is not None and abs(t1 - t0 - 144) < 1,
      f"Letter, drop 2 in: the title is exactly 2 in lower ({t0} -> {t1})")


# 1d. preview = print PDF = imposed sheets, with a big drop, right-hand starts and custom signatures
def chars(path):
    with pdfplumber.open(path) as pdf:
        return [[(c["text"], round(c["x0"], 2), round(c["top"], 2), c["fontname"].split("+")[-1]) for c in p.chars] +
                [("img", round(i["x0"], 1), round(i["top"], 1)) for i in p.images] for p in pdf.pages]


def renders(path):
    doc = pdfium.PdfDocument(path)
    out = [doc[i].render(scale=0.3).to_pil().tobytes() for i in range(len(doc))]
    doc.close()
    return out


b = book_of(LONG)
s = settings(page_size=POCKET, chapter_start="Right-hand page", chapter_sink=4.0, chapter_label="Chapter One",
             ornament=True, toc=True, title_page=True, fmt_impose=True, imp_layout=QUARTO,
             sig_format="Custom signature sizes", sig_custom="2, 3", flyleafs=1)
res = build_preview(apply_info(copy.deepcopy(b), dict(s)), dict(s), log=lambda m: None)
_f, made, _n = run_build(apply_info(copy.deepcopy(b), dict(s)), dict(s), log=lambda m: None)
prn = next(m for m in made if m.endswith("Print.pdf"))
imposed = next(m for m in made if m.endswith("Imposed for binding.pdf"))
check(chars(prn) == chars(res["pdf"]) and res["empty_pages"] == [] and
      len(res["sheets"]) == 1 and renders(res["sheets"][0]) == renders(imposed),
      "preview = Make the book with a big drop: the same pages, and the same imposed sheets rendered side by side")

# ============================================================================ 2. custom signature sizes
# 2a. read exactly as typed
for text, want in (("4, 4, 6, 6", [4, 4, 6, 6]), ("4,4,6,6", [4, 4, 6, 6]), ("4 4 6 6", [4, 4, 6, 6]),
                   ("4; 6", [4, 6]), (" 3 ", [3]), ("2,\n3", [2, 3])):
    try:
        got = bf_impose.custom_sizes({"sig_custom": text})
    except ValueError as e:
        got = str(e)
    check(got == want, f"custom sizes {text!r} are read as {want} ({got})")
for text in ("4.5, 6", "0, 4", "-4, 6", "4, x, 6", "", "four", "4, 4, 6, 6 sheets", "201"):
    try:
        got = bf_impose.custom_sizes({"sig_custom": text})
        msg = ""
    except ValueError as e:
        got, msg = None, str(e)
    check(got is None and msg.startswith("Custom signature sizes:") and "for example 4, 4, 6, 6" in msg,
          f"custom sizes {text!r} aren't guessed: a plain message ({msg or got})")
book = Book(title="Stop", chapters=[Chapter("One", blocks=[Block("para", text="Words. " * 300)])])
s = settings(fmt_impose=True, imp_layout=FOLIO, sig_format="Custom signature sizes", sig_custom="4.5, 6")
stopped = []
for fn in (lambda: build_preview(apply_info(copy.deepcopy(book), dict(s)), dict(s), log=lambda m: None),
           lambda: run_build(apply_info(copy.deepcopy(book), dict(s)), dict(s), log=lambda m: None)):
    try:
        fn()
        stopped.append(False)
    except ValueError as e:
        stopped.append("4.5" in str(e))
check(stopped == [True, True] and not os.listdir(s["out_dir"]),
      "the preview and Make the book stop with that message before anything is written")
s.update(imp_layout="8 pages on one sheet (zine)" if "8 pages on one sheet (zine)" in bf_impose.WACKY else
         next(iter(bf_impose.WACKY)))
try:
    run_build(apply_info(copy.deepcopy(book), dict(s)), dict(s), log=lambda m: None)
    ok = True
except ValueError:
    ok = False
check(ok, "small layouts (no signatures) don't use the custom sizes, so they aren't checked there")


# 2b. real files for several sequences: every signature exactly its size, padding only in the last one
def expected(n_pages, per, fly, sizes):
    sheets = -(-(n_pages + 4 * fly) // per)
    plan = []
    while sum(plan) < sheets:
        plan.append(sizes[min(len(plan), len(sizes) - 1)])
    return plan, sum(plan) * per - n_pages - 4 * fly


rows = []
for li, (layout, per) in enumerate(((FOLIO, 4), (QUARTO, 8))):
    for ci, custom in enumerate(("4, 4, 6, 6", "6, 2, 5", "1, 2", "3")):
        for fly in (0, 1, 2):
            words = 120 + 260 * ((li * 12 + ci * 3 + fly) % 9)          # books of different lengths
            book = Book(title=f"Sig {li}{ci}{fly}", chapters=[Chapter(f"Part {k}", blocks=[
                Block("para", text="Words of the book. " * words)]) for k in range(1, 3)])
            s = settings(fmt_impose=True, imp_layout=layout, sig_format="Custom signature sizes", sig_custom=custom,
                         flyleafs=fly, imp_files="Both aggregated & per-signature files")
            folder, made, notes = run_build(apply_info(book, s), dict(s), log=lambda m: None)
            prn = next(m for m in made if m.endswith("Print.pdf"))
            n = len(pdfium.PdfDocument(prn))
            plan, pad = expected(n, per, fly, [int(x) for x in custom.replace(",", " ").split()])
            sig_files = sorted(m for m in made if os.sep + "Signatures" + os.sep in m)
            sig_sides = [len(pdfium.PdfDocument(f)) for f in sig_files]
            agg = next(m for m in made if m.endswith("Imposed for binding.pdf"))
            note = next(x for x in notes if x.startswith("Imposed"))
            info, sides = bf_impose.plan_imposition([(306.0, 495.0)] * n, dict(s), log=lambda m: None)
            seq = {}
            for side in sides:
                for it in side["items"]:
                    seq.setdefault(side["sig"], {})[it["sigpage"]] = it["ref"]
            flat = [seq[g][p] for g in sorted(seq) for p in sorted(seq[g])]
            pages = [r[1] for r in flat if r[0] == "p"]
            only = [g + 1 for g in sorted(seq) if not any(r[0] == "p" for r in seq[g].values())]
            ok = (info["plan"] == plan and sig_sides == [2 * x for x in plan] and len(pdfium.PdfDocument(agg)) ==
                  2 * sum(plan) and info["blanks"] == pad and pages == list(range(n)) and
                  flat[:2 * fly] == [("b", None)] * (2 * fly) and len(flat) == sum(plan) * per and
                  (f"{pad} blank page(s) added after the book's last page" in note if pad else
                   "no blank pages needed" in note) and
                  ((f"flyleafs: {2 * fly} blank page(s) at the beginning and {2 * fly} at the end" in note) == bool(fly))
                  and info["flyleaf_only"] == only and (("no book pages" in note) == bool(only)))
            rows.append((layout[:5], custom, fly, n, plan, pad, ok))
bad = [r for r in rows if not r[-1]]
check(not bad, f"{len(rows)} real builds (folio and quarto x 4, 4, 6, 6 / 6, 2, 5 / 1, 2 / 3 x 0-2 flyleafs, books "
               f"of different lengths): every signature file has exactly its size, the aggregated file all of them, "
               f"the book's pages once and in order, flyleafs first and last, padding only to complete the last "
               f"signature, the notes give the same numbers {bad[:2]}")

# 2c. the printing notes keep every kind of blank page apart
b = Book(title="Blanks", cover_front=PIC, chapters=[Chapter(f"Chapter {i}", blocks=[
    Block("para", text="Words. " * (60 + 170 * i))]) for i in range(1, 5)])
s = settings(chapter_start="Right-hand page", blank_pages_start="1", blank_pages_end="2", cover_art_in_book=True,
             cover_front_image=os.path.join(TMP, "missing.png"), toc=True, title_page=True, fmt_impose=True,
             imp_layout=QUARTO, sig_format="Custom signature sizes", sig_custom="2, 3", flyleafs=1)
folder, made, notes = run_build(apply_info(b, dict(s)), dict(s), log=lambda m: None)
prn = next(m for m in made if m.endswith("Print.pdf"))
pg = pages_of(prn, s)
empty = [i for i, p in enumerate(pg, 1) if blank(p)]
n = len(pg)
user = [1] + [n - 1, n]
planned = sorted(set(empty) - set(user))
cover_back = [p for p in planned if p == 3]                     # page 1 blank (added), 2 the picture, 3 its back
versos = [p for p in planned if p != 3]
txt = "\n".join(notes)
plan, pad = expected(n, 8, 1, [2, 3])
check(set(user) <= set(empty) and cover_back == [3] and versos and all(p % 2 == 0 for p in versos),
      f"the print PDF: blank pages added (1 at the beginning, 2 at the end), the back of the cover picture (3) and "
      f"left-hand pages before right-hand starts {versos}")
check("Blank pages you added: 1 at the beginning and 2 at the end" in txt and
      "page 3 (the back of the front cover picture)" in txt and
      ("pages " + ", ".join(map(str, versos)) if len(versos) > 1 else f"page {versos[0]}") +
      " (left-hand page" in txt and "not signature padding" in txt and
      (f"{pad} blank page(s) added after the book's last page" in txt if pad else "no blank pages needed" in txt)
      and "flyleafs: 2 blank page(s) at the beginning and 2 at the end" in txt,
      f"the printing notes name each kind apart: added {user}, cover back 3, left-hand {versos}, padding {pad}, "
      "flyleafs 2 + 2")
res = build_preview(apply_info(copy.deepcopy(b), dict(s)), dict(s), log=lambda m: None)
check(res.get("planned_blanks") == {3: "cover", **{p: "verso" for p in versos}},
      f"the preview knows the same planned blank pages ({res.get('planned_blanks')})")

# 2d. nothing carried over from an earlier build: the same settings, a longer and then a shorter book
s = settings(fmt_impose=True, imp_layout=FOLIO, sig_format="Custom signature sizes", sig_custom="4, 4, 6, 6")
counts = []
for words in (3000, 300, 3000):
    book = Book(title=f"Again {words}", chapters=[Chapter("One", blocks=[Block("para", text="Word here. " * words)])])
    folder, made, notes = run_build(apply_info(book, s), s, log=lambda m: None)   # (the same settings dict)
    n = len(pdfium.PdfDocument(next(m for m in made if m.endswith("Print.pdf"))))
    plan, pad = expected(n, 4, 0, [4, 4, 6, 6])
    note = next(x for x in notes if x.startswith("Imposed"))
    counts.append((n, pad, f"{pad} blank page(s)" in note if pad else "no blank pages needed" in note,
                   len(pdfium.PdfDocument(next(m for m in made if m.endswith("Imposed for binding.pdf")))) ==
                   2 * sum(plan)))
check(all(c[2] and c[3] for c in counts) and counts[0][:2] == counts[2][:2] and counts[0][0] != counts[1][0],
      f"three builds in a row with the same settings: each one's padding and sheets come from its own pages {counts}")

# ============================================================================ 3. the window
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
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + "Words of the chapter. " * 500 + "\n\n"
                                                  for i in range(1, 4)))
    outdir = tempfile.mkdtemp(dir=TMP)
    for key, val in dict(out_dir=outdir, open_when_done=False, fmt_pdf=True, fmt_impose=True, fmt_cover=False,
                         fmt_epub=False, fmt_docx=False, fmt_html=False, fmt_txt=False, imp_layout=FOLIO,
                         sig_format="Custom signature sizes", sig_custom="4.5, 6", chapter_sink=1.0,
                         page_size=MM, imp_files="Both aggregated & per-signature files").items():
        app.var(key).set(val)
    app.scan(force=True)
    idle(60)
    n = len(SAID)
    app.preview_book()
    idle()
    pump(0.2)
    said = SAID[n:]
    check(len(said) == 1 and "“4.5”" in said[0][2] and "(Output step, Binding layout.)" in said[0][2] and
          not getattr(app, "preview_win", None),
          "the window: Preview with “4.5, 6” says what to type, on which step, and makes nothing")
    app.var("sig_custom").set("4, 4, 6, 6")
    idle()
    app.preview_book()
    idle()
    pump(0.2)
    pw = getattr(app, "preview_win", None)
    prev_sides = len(pw.sheets) if pw is not None and pw.alive() else None
    app.var("sig_custom").set("2, 3")                         # changed after the preview: Make the book uses it
    idle()
    app.build()
    idle()
    pump(0.2)
    prn = [os.path.join(r, f) for r, _d, fs in os.walk(outdir) for f in fs if f.endswith("Print.pdf")]
    sig = [f for r, _d, fs in os.walk(outdir) for f in fs if r.endswith("Signatures")]
    if prn:
        n = len(pdfium.PdfDocument(prn[0]))
        plan, pad = expected(n, 4, 0, [2, 3])
        plan0, _pad0 = expected(n, 4, 0, [4, 4, 6, 6])
        notes_txt = open(os.path.join(os.path.dirname(prn[0]), "READ ME - printing notes.txt"), encoding="utf-8").read()
        check(prev_sides == 2 * sum(plan0) and len(sig) == len(plan) and
              (f"{pad} blank page(s) added after the book's last page" in notes_txt if pad else True),
              f"the window: the preview showed the 4, 4, 6, 6 sheets ({prev_sides} sides); after changing to 2, 3 "
              f"Make the book made {len(sig)} signature files for {plan}, padding {pad} in the notes")
    else:
        check(False, "the window: Make the book made the files")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
