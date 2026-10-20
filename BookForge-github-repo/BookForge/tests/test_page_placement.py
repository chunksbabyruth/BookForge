"""Checks for the finished page sizes, the printer paper sizes, page scaling and positioning, margins and offsets,
and the "Adjust page placement" window (plain Python - run: python tests/test_page_placement.py).

Every placement is checked three ways: against the formula written out here (independently of BookForge's own
code), against BookForge's shared placement (bf_impose.plan_imposition), and against the real imposed PDF -
both the transformation BookForge wrote into the PDF and where the drawn page content really lands
(pdfplumber), and for cut-off pages by rendering the sheet. The window part draws real sheets and compares
what is on screen with the PDF made from the same settings. Nothing needs the internet. All lengths are
points (1 pt = 1/72 inch); the sheet's origin is its bottom left corner.
"""
import copy
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="bf_placement_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")          # keep the user's real settings out of it
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
import pypdfium2 as pdfium                                            # noqa: E402
from pypdf import PdfReader                                           # noqa: E402
from pypdf.generic import ContentStream                               # noqa: E402
from reportlab.pdfgen import canvas                                   # noqa: E402

import bf_impose                                                      # noqa: E402
from bf_impose import (SHEETS, SHEET_ALIASES, FOLD_LAYOUTS, WACKY, SIG_FORMATS,  # noqa: E402
                       SOURCE_ROT, SCALINGS, POSITIONS, IMPOSE_DEFAULTS, impose, plan_imposition, place_page,
                       placement_settings)
from bf_core import (DEFAULTS, PAGE_SIZES, custom_page_inches, load_book,  # noqa: E402
                     apply_info, CUSTOM_PAGE_MIN_IN, CUSTOM_PAGE_MAX_IN)
from bf_pdf import build_pdf                                          # noqa: E402
import bf_build                                                       # noqa: E402
import bf_edit                                                        # noqa: E402
import bf_placement                                                   # noqa: E402

FAILS = []
COUNT = {"pdfs": 0}
QUIET = "-v" not in sys.argv


LAST = [""]                      # the last check made (to tell where a window error happened)


def check(cond, msg):
    LAST[0] = msg
    if not cond or not QUIET:
        print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def say(msg):
    print("PASS  " + msg)


def close(a, b, tol=0.005):
    return abs(float(a) - float(b)) <= tol


def boxes_close(a, b, tol=0.005):
    return all(close(x, y, tol) for x, y in zip(a, b))


MM = 72 / 25.4          # points per millimetre
PT_PER_IN = 72.0


# ------------------------------------------------------------------------------------------------ helpers
def frame_pdf(sizes, name):
    """A PDF whose page i (size sizes[i]) is filled edge to edge with its own colour, so the page can be
    found on a sheet (pdfplumber reports the filled rectangle where it really lands)."""
    path = os.path.join(TMP, name)
    c = canvas.Canvas(path, pagesize=sizes[0])
    for i, (w, h) in enumerate(sizes):
        c.setPageSize((w, h))
        r, g = page_colour(i)
        c.setFillColorRGB(r, g, 0.3)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", min(12, w / 6))
        c.drawString(w * 0.1, h * 0.5, f"P{i + 1}")
        c.showPage()
    c.save()
    return path


def page_colour(i):
    return ((i + 1) % 40) / 40, ((i + 1) // 40) / 40


def colour_page(col):
    if not col or len(col) < 3 or abs(col[2] - 0.3) > 0.01:
        return None
    return int(round(col[0] * 40)) + 40 * int(round(col[1] * 40)) - 1


def merged(pdf_path):
    """Per sheet page: [(matrix, clip)] for every source page BookForge merged onto it, read from the PDF's own
    content stream (pypdf writes 'q <matrix> cm <clip> re W n ... Q' for each)."""
    r = PdfReader(pdf_path)
    out = []
    for pg in r.pages:
        ops = ContentStream(pg.get_contents(), r).operations
        items = []
        depth, inside = 0, None          # inside: depth of the merged page being read (its own content is skipped)
        for i in range(len(ops)):
            op = ops[i][1]
            if op == b"q":
                depth += 1
            elif op == b"Q":
                depth -= 1
                if inside is not None and depth < inside:
                    inside = None
            elif inside is None and op == b"cm" and i + 3 < len(ops) and ops[i + 1][1] == b"re" and \
                    ops[i + 2][1] == b"W":
                m = [float(v) for v in ops[i][0]]
                x, y, w, h = (float(v) for v in ops[i + 1][0])
                items.append((m, (x, y, x + w, y + h)))
                inside = depth
        out.append(items)
    return out


def apply_m(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def m_box(m, box):
    """Bounding box (x, y, w, h) on the sheet of a source rectangle (x0, y0, x1, y1) under matrix m."""
    pts = [apply_m(m, x, y) for x in (box[0], box[2]) for y in (box[1], box[3])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def plumber_pages(pdf_path):
    """Per sheet page: {source page index: (x, y, w, h)} where its filled rectangle really is."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            found = {}
            H = float(pg.mediabox[3]) - float(pg.mediabox[1])
            for r in list(pg.rects) + list(pg.curves):        # a turned page's rectangle may come as a path
                i = colour_page(r.get("non_stroking_color"))
                if i is None or not r.get("fill", True):
                    continue
                x0, x1 = r["x0"], r["x1"]
                y0, y1 = H - r["bottom"], H - r["top"]
                found[i] = (x0, y0, x1 - x0, y1 - y0)
            out.append(found)
    return out


def oracle(cell, bind, rot, pw, ph, ang, mode, snug, m, off):
    """Where a page should go, written out from the rules (not BookForge's code):
    margins are measured from the page's own spine / fore-edge / head / foot; Keep proportional = one scale,
    the smaller of usable width / page width and usable height / page height; Stretch = each direction on
    its own; Original = 1. Snug = against the spine-side margin. Offsets: + toward fore-edge, + toward head."""
    x0, y0, cw, ch = cell
    spine_m, fore_m, head_m, foot_m = m["binding"], m["fore"], m["top"], m["bottom"]
    left = spine_m if bind == "L" else fore_m
    right = fore_m if bind == "L" else spine_m
    bottom = foot_m if rot == 0 else head_m
    top = head_m if rot == 0 else foot_m
    uw, uh = cw - left - right, ch - bottom - top
    rw, rh = (ph, pw) if ang % 180 == 90 else (pw, ph)
    if mode == "Original size":
        sx = sy = 1.0
    elif mode == "Stretch to fit":
        sx, sy = uw / rw, uh / rh
    else:
        sx = sy = min(uw / rw, uh / rh)
    w, h = rw * sx, rh * sy
    if snug:
        x = x0 + left if bind == "L" else x0 + cw - right - w
    else:
        x = x0 + left + (uw - w) / 2
    y = y0 + bottom + (uh - h) / 2
    x += off[0] if bind == "L" else -off[0]
    y += off[1] if rot == 0 else -off[1]
    return x, y, w, h, sx, sy


def settings(**kw):
    s = dict(IMPOSE_DEFAULTS)
    s.update(kw)
    return s


def do_impose(src, **kw):
    s = settings(**kw)
    info = impose(src, tempfile.mkdtemp(dir=TMP), "t", s, log=lambda m: None)
    COUNT["pdfs"] += len(info["files"])
    return info, s


def side_order(info, s, sides):
    """Index into `sides` of every printed page, in file order (the same rule impose() uses)."""
    idx = list(range(len(sides)))
    if info["duplex"]:
        return idx
    fr = [i for i in idx if sides[i]["front"]]
    bk = [i for i in idx if not sides[i]["front"]]
    if "reverse" in s["printer_type"].lower():
        bk.reverse()
    return fr + bk


def verify_pdf(info, s, sizes, label, plumber=True, use_oracle=True):
    """Every page on every printed side: PDF matrix box == shared placement (== formula); drawn content ==
    the same box (pages that fit) or the visible part clipped to the cell (pages that don't). Returns a list
    of problems."""
    probs = []
    _info, sides = plan_imposition(sizes, dict(s), log=lambda m: None)
    order = side_order(info, s, sides)
    pages = []
    for f in info["files"]:
        mm = merged(f)
        pl = plumber_pages(f) if plumber else [None] * len(mm)
        rdr = PdfReader(f)
        for k in range(len(mm)):
            pages.append((mm[k], pl[k], rdr.pages[k]))
    if len(pages) != len(order):
        return [f"{label}: {len(pages)} printed sides, the plan has {len(order)}"]
    W, H = info["sheet"]
    seen = []
    ps = placement_settings(s)
    for (mm, pl, pg), si in zip(pages, order):
        side = sides[si]
        if not (close(pg.mediabox.width, W, 0.01) and close(pg.mediabox.height, H, 0.01)):
            probs.append(f"{label}: sheet {float(pg.mediabox.width)} x {float(pg.mediabox.height)} != {W} x {H}")
        if len(mm) != len(side["places"]):
            probs.append(f"{label}: side {si}: {len(mm)} pages in the PDF, {len(side['places'])} planned")
            continue
        for (m, clip), (src_i, g) in zip(mm, side["places"]):
            seen.append(src_i)
            pw, ph = sizes[src_i]
            box = m_box(m, (0, 0, pw, ph))
            if not boxes_close(box, (g.x, g.y, g.w, g.h)):
                probs.append(f"{label}: page {src_i + 1}: PDF {tuple(round(v, 3) for v in box)} != placement "
                             f"{(round(g.x, 3), round(g.y, 3), round(g.w, 3), round(g.h, 3))}")
            if use_oracle and g.kind == "fold":
                o = oracle(g.cell, g.bind, g.rot, pw, ph, g.ang, ps["scaling"], ps["snug"], ps,
                           (ps["offset_x"], ps["offset_y"]))
                if not boxes_close(o[:4], (g.x, g.y, g.w, g.h), 1e-6) or not (close(o[4], g.sx, 1e-9)
                                                                              and close(o[5], g.sy, 1e-9)):
                    probs.append(f"{label}: page {src_i + 1}: placement differs from the formula {o}")
            vis = m_box(m, clip)
            cx, cy, cw, ch = g.cell
            want_vis = (max(g.x, cx), max(g.y, cy), min(g.x + g.w, cx + cw) - max(g.x, cx),
                        min(g.y + g.h, cy + ch) - max(g.y, cy))
            if g.fits_cell:
                if not boxes_close(vis, box, 0.01) and not (vis[2] >= box[2] - 0.01 and vis[3] >= box[3] - 0.01):
                    probs.append(f"{label}: page {src_i + 1} fits but is clipped {vis} vs {box}")
            elif want_vis[2] > 0.01 and want_vis[3] > 0.01 and not boxes_close(vis, want_vis, 0.02):
                probs.append(f"{label}: page {src_i + 1} sticks out; visible part {vis} != {want_vis}")
            if pl is not None and g.fits_cell:
                got = pl.get(src_i)
                if got is None or not boxes_close(got, box, 0.02):
                    probs.append(f"{label}: page {src_i + 1} drawn at {got}, expected {box}")
    want = sorted(i for i in range(len(sizes)) if i in set(seen))
    if sorted(seen) != want:
        probs.append(f"{label}: some pages appear twice")
    return probs


ZERO = {"imp_fore": 0, "imp_binding": 0, "imp_top": 0, "imp_bottom": 0, "imp_offset_x": 0, "imp_offset_y": 0}
MARGINS = {"imp_fore": 18, "imp_binding": 36, "imp_top": 24, "imp_bottom": 30, "imp_offset_x": 0, "imp_offset_y": 0}
MARG_OFF = dict(MARGINS, imp_offset_x=12.5, imp_offset_y=-7.25)

# ======================================================================================== 1. finished page sizes
_PAGE_IN = {"Letter (8.5 x 11 in)": (8.5, 11), "Half Letter / Digest (5.5 x 8.5 in)": (5.5, 8.5),
            "Trade Paperback (6 x 9 in)": (6, 9), "Paperback (5 x 8 in)": (5, 8),
            "Mass Market (4.25 x 6.87 in)": (4.25, 6.87), "Legal (8.5 x 14 in)": (8.5, 14),
            "Pocket (4 x 6 in)": (4, 6), "Trade (5.25 x 8 in)": (5.25, 8), "Textbook (7 x 10 in)": (7, 10),
            "Large (8 x 10 in)": (8, 10), "Square (8 x 8 in)": (8, 8), "Square (8.5 x 8.5 in)": (8.5, 8.5),
            "5.06 x 7.81 in": (5.06, 7.81), "6.69 x 9.61 in": (6.69, 9.61), "7.5 x 9.25 in": (7.5, 9.25),
            "8.25 x 11 in": (8.25, 11)}
_PAGE_MM = {"A4 (8.27 x 11.69 in)": (210, 297), "A5 (5.83 x 8.27 in)": (148, 210), "A6 (105 x 148 mm)": (105, 148),
            "B4 (250 x 353 mm)": (250, 353), "B5 (176 x 250 mm)": (176, 250), "B6 (125 x 176 mm)": (125, 176),
"JIS B5 (182 x 257 mm)": (182, 257), "JIS B6 (128 x 182 mm)": (128, 182),
            "A-format Paperback (111 x 178 mm)": (111, 178), "Penguin Small Paperback (111 x 181 mm)": (111, 181),
            "Crown Octavo (123 x 186 mm)": (123, 186), "Large Crown Octavo / B-format (129 x 198 mm)": (129, 198),
            "Demy Octavo (138 x 216 mm)": (138, 216), "Royal Octavo (156 x 234 mm, 6.14 x 9.21 in)": (156, 234),
            "Crown Quarto (189 x 246 mm, 7.44 x 9.69 in)": (189, 246),
            "Large Crown Quarto (201 x 258 mm)": (201, 258), "Demy Quarto (219 x 276 mm)": (219, 276),
            "Royal Quarto (237 x 312 mm)": (237, 312)}
PAGE_EXPECTED = {k: (w, h) for k, (w, h) in _PAGE_IN.items()}
PAGE_EXPECTED.update({k: (w / 25.4, h / 25.4) for k, (w, h) in _PAGE_MM.items()})
page_presets = {k: v for k, v in PAGE_SIZES.items() if v is not None}
check(set(page_presets) == set(PAGE_EXPECTED) and PAGE_SIZES.get("Custom", 1) is None,
      f"finished page sizes: all {len(PAGE_EXPECTED)} presets plus Custom {sorted(set(page_presets) ^ set(PAGE_EXPECTED))}")
check(all(close(page_presets[k][0], v[0], 1e-12) and close(page_presets[k][1], v[1], 1e-12)
          for k, v in PAGE_EXPECTED.items() if k in page_presets), "every finished page size is exact")
for k in ("Letter (8.5 x 11 in)", "Half Letter / Digest (5.5 x 8.5 in)", "Trade Paperback (6 x 9 in)",
          "Paperback (5 x 8 in)", "Mass Market (4.25 x 6.87 in)", "A4 (8.27 x 11.69 in)", "A5 (5.83 x 8.27 in)",
          "Legal (8.5 x 14 in)"):
    check(k in PAGE_SIZES, f"earlier versions' page size {k!r} is still offered")
check(all(v[0] <= v[1] for v in page_presets.values()), "finished pages are listed upright (width <= height)")
vals = [tuple(round(x, 4) for x in v) for v in page_presets.values()]
check(len(set(vals)) == len(vals), "no finished page size is listed twice")
bad_names = []
for k, (w, h) in page_presets.items():
    for a, b, unit in re.findall(r"(\d+(?:\.\d+)?) x (\d+(?:\.\d+)?) (in|mm)", k):
        f = 1 if unit == "in" else 25.4
        dec = len(a.split(".")[1]) if "." in a else 0
        if round(w * f, dec) != float(a) or round(h * f, len(b.split(".")[1]) if "." in b else 0) != float(b):
            bad_names.append(k)
check(not bad_names, f"every page size's name shows its real size, rounded {bad_names}")
for bad, word in (((0, 9), "between"), ((-1, 9), "between"), (("abc", 9), "isn't a number"),
                  ((float("nan"), 9), "between"), ((float("inf"), 9), "between"), ((6, 300), "between"),
                  ((None, 9), "isn't a number")):
    try:
        custom_page_inches(*bad)
        check(False, f"custom page size {bad} is refused")
    except ValueError as e:
        check(word in str(e), f"custom page size {bad} is refused: {e}")
check(custom_page_inches("6.14", 9.21) == (6.14, 9.21) and
      custom_page_inches(CUSTOM_PAGE_MIN_IN, CUSTOM_PAGE_MAX_IN) == (CUSTOM_PAGE_MIN_IN, CUSTOM_PAGE_MAX_IN),
      "custom page sizes inside the limits are used exactly")
try:
    bf_build.check_settings(dict(DEFAULTS, page_size="Custom", custom_w=float("nan"), custom_h=9))
    check(False, "an unusable custom page size stops the build")
except ValueError as e:
    check("Custom page width" in str(e), f"an unusable custom page size stops the build ({e})")

# every finished preset: the typeset pages have exactly that size, and imposed on A3 they sit as the rules say
BOOK_TEXT = "Chapter 1\n\n" + "Some words here. " * 120 + "\n\nChapter 2\n\n" + "More words. " * 120
page_bad, page_place_bad = [], []
for name, (w_in, h_in) in PAGE_EXPECTED.items():
    s = dict(DEFAULTS, source_mode="paste", toc=False, page_size=name)     # every preset works with the default margins
    out = os.path.join(TMP, f"fin_{len(os.listdir(TMP))}.pdf")
    build_pdf(apply_info(load_book(s, BOOK_TEXT), s), s, out, log=lambda m: None)
    sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in PdfReader(out).pages]
    COUNT["pdfs"] += 1
    if any(not (close(a, w_in * 72, 0.01) and close(b, h_in * 72, 0.01)) for a, b in sizes):
        page_bad.append((name, sizes[0]))
    info, si = do_impose(out, sheet_size="A3", imp_layout="Folio - 2 pages per side")
    page_place_bad += verify_pdf(info, si, sizes, f"{name} on A3", plumber=False)
check(not page_bad, f"every finished page size typesets pages of exactly that size ({len(PAGE_EXPECTED)} PDFs) "
                    f"{page_bad[:3]}")
check(not page_place_bad, f"every finished page size is placed on the sheet as the rules say "
                          f"({len(PAGE_EXPECTED)} imposed PDFs) {page_place_bad[:3]}")

# ======================================================================================== 2. printer paper sizes
sheet_presets = {k: v for k, v in SHEETS.items() if v is not None}
landscape = {k for k, (w, h) in sheet_presets.items() if w > h}
check(landscape == {"Ledger (17 x 11)", "ID-1", "ID-2", "ID-3"},
      f"printer papers are listed upright except Ledger and the ID cards {sorted(landscape)}")
svals = [tuple(round(x, 3) for x in v) for v in sheet_presets.values()]
check(len(set(svals)) == len(svals), "no printer paper size is listed twice")
check(len(sheet_presets) == 68 and all(n in SHEETS for n in SHEET_ALIASES.values()),
      f"{len(sheet_presets)} printer paper presets plus Custom; old names lead to listed papers")
check(set(PAGE_SIZES).isdisjoint(SHEETS.keys() - {"Custom"}), "the finished page and printer paper lists are separate")
sheet_bad = []
SRC4 = frame_pdf([(612, 792)] * 4, "letter4.pdf")
for name in sheet_presets:
    for layout, mode, pos, mg in (("Folio - 2 pages per side", "Keep proportional", "Centered", ZERO),
                                  ("Quarto - 4 pages per side", "Stretch to fit", "Snug against binding edge", ZERO)):
        info, s = do_impose(SRC4, sheet_size=name, imp_layout=layout, imp_scaling=mode, imp_position=pos, **mg)
        sheet_bad += verify_pdf(info, s, [(612, 792)] * 4, f"{name} {layout}")
check(not sheet_bad, f"every printer paper preset: sheet size, and every page's place in the PDF (matrix and "
                     f"drawn content) = the shared placement = the formula ({len(sheet_presets) * 2} imposed PDFs) "
                     f"{sheet_bad[:3]}")

# ======================================================================================== 3. the worked example
# Source page 612 x 792 pt; each page's space 2004 x 2834 pt (folio on paper 2834 x 4008 pt: two 2004-pt halves
# side by side once it is laid landscape); no margins, offsets or rotation.
CELL = (0.0, 0.0, 2004.0, 2834.0)
ps0 = placement_settings(settings())
S8 = {}
for mode in SCALINGS:
    S8[mode] = place_page(CELL, "L", 0, 612, 792, 0, dict(ps0, scaling=mode))
g = S8["Original size"]
check(g.sx == 1 and g.sy == 1 and (g.w, g.h) == (612, 792) and close(g.gaps["spine"], g.gaps["fore"], 1e-9) and
      close(g.gaps["top"], g.gaps["bottom"], 1e-9) and close(g.gaps["spine"], 696, 1e-9) and
      close(g.gaps["top"], 1021, 1e-9), f"Original size: scale 1 x 1, 612 x 792 pt, equal white space "
                                         f"({g.gaps['spine']:.2f} pt each side, {g.gaps['top']:.2f} top and bottom)")
g = S8["Keep proportional"]
check(close(g.sx, 2004 / 612, 1e-12) and close(g.sx, 3.27451, 1e-5) and g.sx == g.sy and close(g.w, 2004, 1e-9)
      and close(g.h, 792 * 2004 / 612, 1e-9) and close(g.h, 2593.41, 0.005) and close(g.gaps["top"], 120.29, 0.005)
      and close(g.gaps["bottom"], 120.29, 0.005) and close(g.gaps["spine"], 0, 1e-9) and close(g.gaps["fore"], 0, 1e-9),
      f"Keep proportional: scale {g.sx:.5f}, placed {g.w:.2f} x {g.h:.2f} pt, top and bottom white space "
      f"{g.gaps['top']:.2f} pt, none at the sides")
g = S8["Stretch to fit"]
check(close(g.sx, 3.27451, 1e-5) and close(g.sy, 2834 / 792, 1e-12) and close(g.sy, 3.57828, 1e-5) and
      close(g.w, 2004, 1e-9) and close(g.h, 2834, 1e-9) and all(close(v, 0, 1e-9) for v in g.gaps.values()),
      f"Stretch to fit: scale {g.sx:.5f} x {g.sy:.5f}, placed {g.w:.2f} x {g.h:.2f} pt")
# the same three in a real PDF
SRC_LETTER = frame_pdf([(612, 792)] * 2, "letter2.pdf")
ex_bad = []
for mode in SCALINGS:
    info, s = do_impose(SRC_LETTER, sheet_size="Custom", sheet_w=2834, sheet_h=4008, sheet_unit="pt",
                        imp_scaling=mode, imp_layout="Folio - 2 pages per side")
    if info["sheet"] != (4008.0, 2834.0) or info["cell"] != (2004.0, 2834.0):
        ex_bad.append(("sheet", info["sheet"], info["cell"]))
    ex_bad += verify_pdf(info, s, [(612, 792)] * 2, f"worked example {mode}")
    pl = plumber_pages(info["files"][0])
    _i, sides = plan_imposition([(612, 792)] * 2, dict(s), log=lambda m: None)
    for k, side in enumerate(sides):
        for si, gg in side["places"]:
            got = pl[k][si]
            want = S8[mode]
            rel = (got[0] - gg.cell[0], got[1] - gg.cell[1], got[2], got[3])
            ref = (want.x, want.y, want.w, want.h) if gg.bind == "L" else (2004 - want.x - want.w, want.y,
                                                                          want.w, want.h)
            if not boxes_close(rel, ref, 0.02):
                ex_bad.append((mode, si, rel, ref))
    lines = bf_placement.diagnostics(info, s, sides[0], sides[0]["places"][0][1], 1)
    text = "\n".join(f"{a}: {b}" for a, b, _k in lines)
    gg = sides[0]["places"][0][1]
    want_scale = f"{gg.sx:.6f} × {gg.sy:.6f}"
    if want_scale not in text or f"{gg.w:.2f} × {gg.h:.2f} pt" not in text or \
            f"White space: top: {gg.gaps['top']:.2f} pt" not in text:
        ex_bad.append(("diagnostics", mode, text))
check(not ex_bad, f"the worked example: the PDF and the numbers shown agree for all three scalings {ex_bad[:2]}")
say("worked example in the PDF: Keep proportional 3.27451 -> 2004.00 x 2593.41 pt with 120.29 pt above and below; "
    "Stretch 3.27451 x 3.57828 -> 2004 x 2834; Original 612 x 792 centred")

# a different shape with margins: a landscape page 900 x 500 pt in the same space, fore-edge 30, binding 50,
# top 40, bottom 60
psm = dict(ps0, fore=30.0, binding=50.0, top=40.0, bottom=60.0)
g = place_page(CELL, "L", 0, 900, 500, 0, dict(psm, scaling="Keep proportional"))
k = min((2004 - 80) / 900, (2834 - 100) / 500)
check(close(k, 2.137778, 1e-6) and close(g.sx, k, 1e-12) and close(g.w, 1924, 1e-9) and close(g.h, 1068.89, 0.005) and
      close(g.x, 50, 1e-9) and close(g.y, 60 + (2734 - 500 * k) / 2, 1e-9) and close(g.gaps["top"], 40 + 832.56, 0.01),
      f"a landscape page with margins: scale {g.sx:.6f}, {g.w:.2f} x {g.h:.2f} pt at x {g.x:.2f}, y {g.y:.2f}")
g = place_page(CELL, "R", 0, 900, 500, 0, dict(psm, scaling="Stretch to fit", snug=True))
check(close(g.sx, 1924 / 900, 1e-12) and close(g.sy, 2734 / 500, 1e-12) and close(g.x, 30, 1e-9) and
      close(g.y, 60, 1e-9) and close(g.gaps["spine"], 50, 1e-9) and close(g.gaps["fore"], 30, 1e-9),
      "the same, stretched, spine on the right: fills the space inside the margins exactly")
g = place_page(CELL, "R", 180, 900, 500, 180, dict(psm, scaling="Keep proportional", snug=True, offset_x=10,
                                                   offset_y=5))
check(close(g.x, 2004 - 50 - 1924 - 10, 1e-9) and close(g.gaps["spine"], 50 - (-10), 1e-9) and
      close(g.gaps["fore"], 30 - 10, 1e-9) and close(g.gaps["top"], 40 - 5 + (2734 - 500 * k) / 2, 1e-9),
      "upside down, spine on the right, snug, offsets 10 toward the fore-edge and 5 toward the top: every "
      "white space as expected")
SRC_LAND = frame_pdf([(900, 500)] * 2, "land2.pdf")
ex2 = []
for mode in SCALINGS:
    for pos in POSITIONS:
        info, s = do_impose(SRC_LAND, sheet_size="Custom", sheet_w=2834, sheet_h=4008, sheet_unit="pt",
                            imp_scaling=mode, imp_position=pos, imp_fore=30, imp_binding=50, imp_top=40, imp_bottom=60)
        ex2 += verify_pdf(info, s, [(900, 500)] * 2, f"landscape {mode} {pos}")
check(not ex2, f"a landscape page with margins, every scaling and position, in the PDF {ex2[:2]}")

# ======================================================================================== 4. every combination
SOURCES = {"portrait": (396, 612), "landscape": (612, 396), "square": (500, 500), "small": (100, 150),
           "large": (2000, 3000)}
combo_bad, n_combo = [], 0
for layout in FOLD_LAYOUTS:
    for sname, (sw, sh) in SOURCES.items():
        src = frame_pdf([(sw, sh)] * 8, f"src_{sname}.pdf")
        for mode in SCALINGS:
            for pos in POSITIONS:
                for vname, var in (("no margins", ZERO), ("margins", MARGINS), ("margins+offsets", MARG_OFF)):
                    info, s = do_impose(src, sheet_size="Letter", imp_layout=layout, imp_scaling=mode,
                                        imp_position=pos, **var)
                    combo_bad += verify_pdf(info, s, [(sw, sh)] * 8, f"{layout[:6]} {sname} {mode} {pos} {vname}")
                    n_combo += 1
check(not combo_bad, f"{n_combo} combinations (4 fold layouts x 5 page shapes and sizes x 3 scalings x 2 positions "
                     f"x margins/offsets), both sides of every sheet {combo_bad[:3]}")

# source rotation and rotated paper
rot_bad, n_rot = [], 0
src = frame_pdf([(396, 612)] * 8, "rot8.pdf")
for layout in FOLD_LAYOUTS:
    for rot in SOURCE_ROT:
        for rp in (False, True):
            for mode in SCALINGS:
                info, s = do_impose(src, sheet_size="A4", imp_layout=layout, imp_source_rot=rot, rotate_paper=rp,
                                    imp_scaling=mode, imp_position="Snug against binding edge", **MARG_OFF)
                rot_bad += verify_pdf(info, s, [(396, 612)] * 8, f"{layout[:6]} {rot} paper turned {rp} {mode}")
                n_rot += 1
check(not rot_bad, f"{n_rot} combinations with every source page rotation and with the paper turned "
                   f"{rot_bad[:3]}")
_i, sides = plan_imposition([(396, 612)] * 8, settings(imp_source_rot="Rotate 90° clockwise"), log=lambda m: None)
gs = [g for side in sides for _si, g in side["places"]]
check(all(g.ang in (90, 270) and (g.rsize == (612, 396)) for g in gs),
      "a page turned 90 degrees is fitted with its width and height swapped")

# large B formats (and the largest sheets) with a custom page
big_bad = []
for name in ("B0", "B1", "JIS B0", "A0", "Arch E1 (30 x 42)", "ANSI E (34 x 44)", "SRA3"):
    src = frame_pdf([(6.14 * 72, 9.21 * 72)] * 16, "royal16.pdf")
    for layout in ("Folio - 2 pages per side", "Sextodecimo - 16 pages per side"):
        info, s = do_impose(src, sheet_size=name, imp_layout=layout, imp_scaling="Keep proportional", **MARG_OFF)
        big_bad += verify_pdf(info, s, [(6.14 * 72, 9.21 * 72)] * 16, f"{name} {layout}")
check(not big_bad, f"large sheets (ISO and JIS B0, B1, A0, Arch E1, ANSI E, SRA3) {big_bad[:2]}")

# ======================================================================================== 5. pages bigger than their space
# Original size with pages larger than the space: nothing may be printed outside each page's own space.
src = frame_pdf([(2000, 3000)] * 4, "huge4.pdf")
clip_bad = []
for off in ((0, 0), (150, -80)):
    info, s = do_impose(src, sheet_size="Letter", imp_scaling="Original size", imp_offset_x=off[0], imp_offset_y=off[1])
    _i, sides = plan_imposition([(2000, 3000)] * 4, dict(s), log=lambda m: None)
    doc = pdfium.PdfDocument(info["files"][0])
    for k, side in enumerate(sides):
        img = doc[k].render(scale=1).to_pil().convert("RGB")
        W, H = info["sheet"]
        for si, g in side["places"]:
            r_, g_ = page_colour(si)
            cx, cy, cw, ch = g.cell
            for px in range(int(cx) + 3, int(cx + cw) - 3, 17):
                for py in range(int(H - cy - ch) + 3, int(H - cy) - 3, 17):
                    pix = img.getpixel((px, py))
                    if abs(pix[0] - r_ * 255) > 3 or abs(pix[2] - 0.3 * 255) > 3:
                        if not (pix[0] < 60 and pix[1] < 60):      # the page's own label is black
                            clip_bad.append((off, k, si, (px, py), pix))
                            break
    doc.close()
    check(not clip_bad and "cut off" in info.get("placement_warning", "") and "Original size" in
          info.get("placement_warning", ""), f"Original size pages larger than their space (offsets {off}) stay inside "
                                             f"their own space and the notes say they're cut off {clip_bad[:2]}")
g = place_page((0, 0, 396, 612), "L", 0, 2000, 3000, 0, dict(ps0, scaling="Original size"))
check(g.sx == 1 and not g.fits_cell and not g.fits_area, "Original size never shrinks a page")
check(bf_impose.placement_problems([{"places": [(0, g)]}]).startswith("Pages don't fit their space"),
      "a page that doesn't fit is reported")
g2 = place_page((0, 0, 396, 612), "L", 0, 300, 500, 0, dict(ps0, scaling="Original size", fore=60, offset_x=30))
check(g2.fits_cell and not g2.fits_area and "run into the margins" in bf_impose.placement_problems([{"places": [(0, g2)]}]),
      "a page that fits its space but not its margins is reported as running into the margins")

# mixed page sizes in one PDF: each page is fitted by its own size
sizes = [(396, 612), (612, 396), (500, 500), (300, 700), (396, 612), (612, 792), (200, 200), (396, 612)]
src = frame_pdf(sizes, "mixed8.pdf")
mix_bad = []
for layout in ("Folio - 2 pages per side", "Quarto - 4 pages per side"):
    for mode in SCALINGS:
        info, s = do_impose(src, sheet_size="Letter", imp_layout=layout, imp_scaling=mode, **MARGINS)
        mix_bad += verify_pdf(info, s, sizes, f"mixed {layout} {mode}")
check(not mix_bad, f"pages of different sizes in one PDF are each fitted by their own size {mix_bad[:2]}")

# ======================================================================================== 6. imposition regression
reg_bad, n_reg = [], 0
src16 = frame_pdf([(396, 612)] * 22, "num22.pdf")
for layout in FOLD_LAYOUTS:
    for fmt in SIG_FORMATS:
        for printer in ("Duplex (two-sided printer)", "Single-sided (fronts and backs files)",
                        "Single-sided, backs in reverse order"):
            for rb, rng in ((False, ""), (True, "3-17")):
                info, s = do_impose(src16, sheet_size="Letter", imp_layout=layout, sig_format=fmt, sig_sheets=2,
                                    sig_custom="1, 2", printer_type=printer, rotate_back=rb, imp_range=rng,
                                    flyleafs=1, fold_marks=True, cut_marks=True, edge_marks=True, sig_marks=True,
                                    sewing_marks=True, imp_position="Snug against binding edge", **MARG_OFF)
                reg_bad += verify_pdf(info, s, [(396, 612)] * 22, f"{layout[:6]} {fmt[:8]} {printer[:12]} {rb} {rng!r}",
                                      plumber=False)
                chosen = bf_impose.parse_range(rng, 22)
                seen = set()
                for f in info["files"]:
                    for pg in plumber_pages(f):
                        seen |= set(pg)
                if seen != set(chosen):
                    reg_bad.append((layout, fmt, printer, rng, "pages", sorted(set(chosen) ^ seen)))
                n_reg += 1
check(not reg_bad, f"{n_reg} imposition paths (4 fold layouts x 4 signature formats x 3 printer modes x rotated "
                   f"backs / page range, flyleafs, all marks): every chosen page printed once, where the placement "
                   f"says {reg_bad[:3]}")

# marks on the spine follow the fold (the edge of the page's space), not the page edge
mark_bad = []
src = frame_pdf([(396, 612)] * 32, "num32.pdf")
for layout in FOLD_LAYOUTS:
    info, s = do_impose(src, sheet_size="Letter", imp_layout=layout, sig_format="Standard signatures", sig_sheets=1,
                        sig_marks=True, sewing_marks=True, sewing_where="Center of every folio",
                        imp_binding=30, imp_fore=5)
    _i, sides = plan_imposition([(396, 612)] * 32, dict(s), log=lambda m: None)
    with pdfplumber.open(info["files"][0]) as pdf:
        for k, (pg, side) in enumerate(zip(pdf.pages, sides)):
            folds = {round(g.cell[0] if g.bind == "L" else g.cell[0] + g.cell[2], 2) for _si, g in side["places"]}
            folds |= {round(it["geo"].cell[0] if it["bind"] == "L" else it["geo"].cell[0] + it["geo"].cell[2], 2)
                      for it in side["items"]}
            for r in pg.rects:
                if r.get("non_stroking_color") in ((0,), [0], (0, 0, 0), [0, 0, 0], 0) and close(r["width"], 6, 0.01) \
                        and close(r["height"], 12, 0.01):
                    if round((r["x0"] + r["x1"]) / 2, 2) not in folds:
                        mark_bad.append((layout, k, "signature mark", r["x0"]))
            for cv in pg.curves:
                if close(cv["x1"] - cv["x0"], 2.2, 0.05):
                    if round((cv["x0"] + cv["x1"]) / 2, 2) not in folds:
                        mark_bad.append((layout, k, "sewing mark", cv["x0"]))
check(not mark_bad, f"signature and sewing marks sit on the fold even with a 30 pt binding margin {mark_bad[:3]}")

# small layouts: their own spacing; page scaling, position, margins and offsets don't move them
small_bad = []
src = frame_pdf([(396, 612)] * 20, "num20.pdf")
for layout in WACKY:
    ref = None
    for var in (dict(ZERO), dict(MARG_OFF, imp_scaling="Stretch to fit", imp_position="Snug against binding edge")):
        info, s = do_impose(src, sheet_size="Letter", imp_layout=layout, **var)
        small_bad += verify_pdf(info, s, [(396, 612)] * 20, f"{layout}", use_oracle=False)
        boxes = [m_box(m, (0, 0, 396, 612)) for f in info["files"] for pg in merged(f) for m, _c in pg]
        if ref is None:
            ref = boxes
        elif ref != boxes:
            small_bad.append((layout, "moved by page placement settings"))
check(not small_bad, f"the {len(WACKY)} small layouts keep their own spacing and every page is where the plan says "
                     f"{small_bad[:2]}")

# ======================================================================================== 7. checks of typed values
for key, val, word in (("imp_fore", "abc", "isn't a number"), ("imp_top", float("nan"), "ordinary number"),
                       ("imp_bottom", float("inf"), "ordinary number"), ("imp_binding", -1, "between 0"),
                       ("imp_fore", 20000, "between 0"), ("imp_offset_x", 10001, "between -10000"),
                       ("imp_offset_y", "", "type a number"), ("imp_offset_y", "1e400", "ordinary number")):
    try:
        placement_settings(settings(**{key: val}))
        check(False, f"{key} = {val!r} is refused")
    except ValueError as e:
        check(word in str(e), f"{key} = {val!r} is refused: {e}")
check(placement_settings(settings(imp_offset_x="-12,5", imp_fore="7"))["offset_x"] == -12.5,
      "offsets can be negative and typed with a decimal comma")
check(placement_settings({k: v for k, v in IMPOSE_DEFAULTS.items() if not k.startswith("imp_offset")})["offset_x"] == 0,
      "settings from before offsets existed mean no offset")
try:
    plan_imposition([(396, 612)] * 4, settings(imp_fore=200, imp_binding=200), log=lambda m: None)
    check(False, "margins wider than the page's space are refused")
except ValueError as e:
    check("no room" in str(e), f"margins wider than the page's space are refused: {e}")
out_dir = os.path.join(TMP, "refused")
s = dict(DEFAULTS, source_mode="paste", fmt_impose=True, imp_top=float("nan"), out_dir=out_dir)
try:
    bf_build.run_build(apply_info(load_book(s, BOOK_TEXT), s), s, log=lambda m: None)
    check(False, "an unusable margin stops the build")
except ValueError as e:
    check("Top margin" in str(e) and not os.path.exists(out_dir), f"an unusable margin stops the build before "
                                                                  f"anything is written ({e})")
s = dict(DEFAULTS, source_mode="paste", fmt_impose=True, imp_offset_x=15, imp_scaling="Original size",
         out_dir=os.path.join(TMP, "notes"), open_when_done=False)
folder, made, notes = bf_build.run_build(apply_info(load_book(s, BOOK_TEXT), s), s, log=lambda m: None)
txt = open(os.path.join(folder, "READ ME - printing notes.txt"), encoding="utf-8").read()
check("Page placement: Original size, centered" in txt and "offsets 15 pt toward the fore-edge" in txt,
      "the printing notes say how the pages are placed")

# ======================================================================================== 8. projects keep it all
proj = os.path.join(TMP, "p.bookforge")
s = dict(DEFAULTS, source_mode="paste", paste_text=BOOK_TEXT, sheet_size="ANSI C (17 x 22)", imp_scaling="Stretch to fit",
         imp_position="Snug against binding edge", imp_fore=12.25, imp_binding=30, imp_top=7, imp_bottom=9.5,
         imp_offset_x=-4.75, imp_offset_y=3.5, page_size="B6 (125 x 176 mm)")
book = apply_info(load_book(s, BOOK_TEXT), s)
bf_edit.save_project(proj, book, s, "test")
_b, back = bf_edit.load_project(proj)
check(all(back.get(k) == s[k] for k in ("sheet_size", "imp_scaling", "imp_position", "imp_fore", "imp_binding",
                                        "imp_top", "imp_bottom", "imp_offset_x", "imp_offset_y", "page_size")),
      "a project keeps the paper, page size, scaling, position, margins and offsets")

# ======================================================================================== 9. PDFs used as the source
def odd_pdf(path):
    """Pages of different sizes, one turned, one with a crop box (as PDFs from other programs can be)."""
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    raw = frame_pdf([(396, 612), (396, 612), (612, 396), (396, 612), (500, 700), (396, 612)], "odd_raw.pdf")
    r = PdfReader(raw)
    w = PdfWriter()
    for i, p in enumerate(r.pages):
        if i == 2:
            p.rotate(90)
        if i == 3:
            p.cropbox = RectangleObject((20, 20, 376, 592))
        w.add_page(p)
    with open(path, "wb") as f:
        w.write(f)
    return path


ODD = odd_pdf(os.path.join(TMP, "odd.pdf"))
s = dict(DEFAULTS, source_mode="file", source_path=ODD, pdf_mode="Keep the pages as they are", fmt_impose=True,
         imp_scaling="Keep proportional", **MARGINS)
book = load_book(s, "")
check(bool(getattr(book, "fixed_pdf", "")), "a PDF kept as it is is read as its own pages")
pages_pdf = os.path.join(TMP, "kept.pdf")
ss = dict(s)
n = bf_build.typeset(book, ss, pages_pdf, log=lambda m: None)
kept_sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in PdfReader(pages_pdf).pages]
check(n == 6 and len(set(kept_sizes)) == 1 and ss["page_size"] == "Custom" and
      close(ss["custom_w"] * 72, kept_sizes[0][0], 1e-6), f"kept PDF pages come out one size, upright {kept_sizes[0]}")
info, si = do_impose(pages_pdf, **{k: ss[k] for k in IMPOSE_DEFAULTS})
kept_bad = verify_pdf(info, si, kept_sizes, "kept PDF", plumber=False)   # (their drawings don't fill the pages)
first = plan_imposition(kept_sizes, dict(si), log=lambda m: None)[1][0]["places"][0][1]
lines = bf_placement.diagnostics(info, ss, None, first, 1, fixed=True)
check(not kept_bad and any("the PDF's own pages" in b for _a, b, _k in lines),
      f"kept PDF pages are placed by the same rules, and the numbers say they are the PDF's own pages {kept_bad[:2]}")
s2 = dict(s, pdf_mode="Rebuild as an editable book", page_size="A5 (5.83 x 8.27 in)")
try:
    book2 = load_book(s2, "")
    out = os.path.join(TMP, "rebuilt.pdf")
    bf_build.typeset(apply_info(book2, dict(s2)), dict(s2), out, log=lambda m: None)
    rs = {(round(float(p.mediabox.width), 2), round(float(p.mediabox.height), 2)) for p in PdfReader(out).pages}
    check(rs == {(round(148 * MM, 2), round(210 * MM, 2))}, f"a rebuilt PDF is typeset at the chosen page size {rs}")
except ValueError as e:            # a PDF with hardly any text can't be rebuilt; that is reported, not guessed
    check("text" in str(e).lower(), f"a PDF with almost no text is refused for rebuilding with a message ({e})")

print(f"({COUNT['pdfs']} PDFs made and measured so far)")

# ======================================================================================== 10. the placement window
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
        setattr(messagebox, k, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, message)) or True))(k))
    import BookForge as BF
    app = BF.App()
    app._no_save = True
    errors = []
    app.report_callback_exception = lambda *a: errors.append(f"after the check {LAST[0]!r}: " +
                                                             "".join(__import__("traceback").format_exception(*a)))

    def pump(sec=0.3):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    def wait(cond, sec=90.0):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def idle(sec=240):
        """Wait until BookForge isn't busy making a preview or a book. Open project, New book and the light/dark
        switch are ignored while it is (as in every version), and a slow computer (or CI runner) takes longer."""
        return wait(lambda: not app.busy, sec)

    def settle(win, sec=30):
        """Wait until the placement window has redrawn for the settings just changed (not a fixed time)."""
        pump(0.05)
        if win is None or not win.alive():
            return True
        return wait(lambda: win._pending is None, sec)

    def window_ready(w):
        return (w.alive() and not w.busy_typeset and w.real_pages and w.src_sizes and
                w.src_sig == w.typeset_sig(w.settings()) and w._pending is None)

    def to_points(w, rect):
        k, ox, oy = w.view()
        H = w.info["sheet"][1]
        x1, y1, x2, y2 = rect
        return (x1 - ox) / k, H - (y2 - oy) / k, (x2 - x1) / k, (y2 - y1) / k

    def diag_numbers(w):
        text = w.diag.get("1.0", "end")
        out = {}
        m = re.search(r"Scale \(across × down\): ([\d.]+) × ([\d.]+)", text)
        if m:
            out["scale"] = (float(m.group(1)), float(m.group(2)))
        m = re.search(r"On the sheet: ([\d.]+) × ([\d.]+) pt", text)
        if m:
            out["size"] = (float(m.group(1)), float(m.group(2)))
        m = re.search(r"Position: x (-?[\d.]+), y (-?[\d.]+) pt", text)
        if m:
            out["pos"] = (float(m.group(1)), float(m.group(2)))
        for name in ("spine", "top", "fore-edge", "bottom"):
            m = re.search(rf"White space: {name}: (-?[\d.]+) pt", text)
            if m:
                out[name] = float(m.group(1))
        return out, text

    def compare_window(w, label):
        """Every side: the window's drawing == the shared placement == the PDF that 'Preview book' and
        'Generate' make from the same settings; and the numbers beside the sheet == the PDF."""
        probs = []
        s = w.settings()
        b = copy.copy(app.book)
        ss = dict(s)
        apply_info(b, ss)
        res = bf_build.build_preview(b, ss, log=lambda m: None)
        COUNT["pdfs"] += 1 + len(res["sheets"])
        sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in PdfReader(res["pdf"]).pages]
        if [tuple(round(v, 3) for v in x) for x in sizes] != [tuple(round(v, 3) for v in x) for x in w.src_sizes]:
            probs.append(f"{label}: the window shows {len(w.src_sizes)} pages of {w.src_sizes[0]}, the book has "
                         f"{len(sizes)} of {sizes[0]}")
        info_pdf = {"sheet": w.info["sheet"], "duplex": res["duplex"], "files": res["sheets"]}
        pdf_pages = [mm for f in res["sheets"] for mm in merged(f)]
        rdr = [p for f in res["sheets"] for p in PdfReader(f).pages]
        order = side_order(info_pdf, s, w.sides)
        if len(pdf_pages) != len(w.sides):
            return probs + [f"{label}: {len(pdf_pages)} printed sides, the window has {len(w.sides)}"]
        W, H = w.info["sheet"]
        for pos, si in enumerate(order):
            w.go(si)
            pump(0.02)
            sx1, sy1, sx2, sy2 = w.canvas.coords("sheet")
            if not close((sx2 - sx1) / (sy2 - sy1), W / H, 1e-6):
                probs.append(f"{label}: the sheet is drawn {sx2 - sx1:.1f} x {sy2 - sy1:.1f} px for {W} x {H} pt")
            if not (close(rdr[pos].mediabox.width, W, 0.01) and close(rdr[pos].mediabox.height, H, 0.01)):
                probs.append(f"{label}: PDF sheet {rdr[pos].mediabox} != window {W} x {H}")
            drawn = {d[1]: d for d in w.drawn}
            mm = pdf_pages[pos]
            places = w.sides[si]["places"]
            if len(mm) != len(places) or len(drawn) != len(places):
                probs.append(f"{label}: side {si}: PDF {len(mm)}, plan {len(places)}, drawn {len(drawn)} pages")
                continue
            for idx, ((m, _clip), (src_i, g)) in enumerate(zip(mm, places)):
                pbox = m_box(m, (0, 0) + tuple(sizes[src_i]))
                on_screen = to_points(w, drawn[idx][2])
                if drawn[idx][0] != src_i:
                    probs.append(f"{label}: side {si}: window shows page {drawn[idx][0] + 1}, PDF has {src_i + 1}")
                if not boxes_close(pbox, (g.x, g.y, g.w, g.h), 0.01):
                    probs.append(f"{label}: page {src_i + 1}: PDF {pbox} != plan {(g.x, g.y, g.w, g.h)}")
                if not boxes_close(on_screen, pbox, 0.01):
                    probs.append(f"{label}: page {src_i + 1}: window {on_screen} != PDF {pbox}")
        # the numbers beside the sheet, for the first page of the first printed side
        w.go(order[0])
        pump(0.05)
        w.sel = (order[0], 0)
        w.draw()
        nums, text = diag_numbers(w)
        m, _clip = pdf_pages[0][0]
        src_i, g = w.sides[order[0]]["places"][0]
        x, y, bw, bh = m_box(m, (0, 0) + tuple(sizes[src_i]))
        cx, cy, cw, ch = g.cell
        left, right, bottom, top = x - cx, cx + cw - x - bw, y - cy, cy + ch - y - bh
        spine, fore = (left, right) if g.bind == "L" else (right, left)
        head, foot = (top, bottom) if g.rot == 0 else (bottom, top)
        want = {"size": (bw, bh), "pos": (x, y), "spine": spine, "fore-edge": fore, "top": head, "bottom": foot}
        if g.kind == "small":                 # small layouts show their size and position only
            want = {"size": (bw, bh), "pos": (x, y)}
        for key, v in want.items():
            got = nums.get(key)
            if got is None or (isinstance(v, tuple) and not boxes_close(got, v, 0.006)) or \
                    (not isinstance(v, tuple) and not close(got, v, 0.006)):
                probs.append(f"{label}: numbers beside the sheet: {key} {got} != PDF {v}")
        if g.kind == "fold" and "scale" in nums and not (close(nums["scale"][0], bw / g.rsize[0], 2e-6) and
                                                         close(nums["scale"][1], bh / g.rsize[1], 2e-6)):
            probs.append(f"{label}: scale shown {nums['scale']} != PDF {bw / g.rsize[0]} x {bh / g.rsize[1]}")
        import shutil
        shutil.rmtree(res["dir"], ignore_errors=True)
        return probs

    def set_vars(**kw):
        for k, v in kw.items():
            app.var(k).set(v)
        settle(getattr(app, "placement_win", None))

    pump()
    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].configure(state="normal")
    long_text = "".join(f"Chapter {i}\n\n" + ("Words in a line of text. " * 90 + "\n\n") * 3 for i in range(1, 4))
    app.texts["paste_text"].insert("1.0", long_text)
    set_vars(fmt_impose=True, toc=False, page_size="Half Letter / Digest (5.5 x 8.5 in)")
    app.scan(force=True) if hasattr(app, "scan") else None
    check(wait(lambda: app.book is not None and not app.busy, 60), "the pasted book is read")
    app.open_placement()
    w = app.placement_win
    check(w is not None and w.alive(), "Adjust page placement opens its window")
    app.open_placement()
    check(app.placement_win is w and len([c for c in app.winfo_children() if isinstance(c, tk.Toplevel)]) >= 1,
          "opening it again brings the same window to the front")
    check(wait(lambda: window_ready(w), 120), f"the window shows the book's real pages ({w.status.cget('text')})")
    app.var("fmt_impose").set(False)
    settle(w)
    check("isn't ticked" in w.diag.get("1.0", "end"), "the window says when no printing sheets will be made")
    app.var("fmt_impose").set(True)
    settle(w)
    check("isn't ticked" not in w.diag.get("1.0", "end"), "and stops saying it once they will")

    CONFIGS = [
        ("Letter, folio, keep proportional, centred",
         dict(sheet_size="Letter", imp_layout="Folio - 2 pages per side", imp_scaling="Keep proportional",
              imp_position="Centered", **ZERO)),
        ("A4, quarto, stretch, snug, margins and offsets",
         dict(sheet_size="A4", imp_layout="Quarto - 4 pages per side", imp_scaling="Stretch to fit",
              imp_position="Snug against binding edge", page_size="A5 (5.83 x 8.27 in)", **MARG_OFF)),
        ("Tabloid, octavo, original size, offsets",
         dict(sheet_size="Tabloid / 11x17", imp_layout="Octavo - 8 pages per side", imp_scaling="Original size",
              imp_position="Centered", page_size="Pocket (4 x 6 in)", **dict(ZERO, imp_offset_x=5, imp_offset_y=-3))),
        ("B1, sextodecimo, keep proportional, snug, margins",
         dict(sheet_size="B1", imp_layout="Sextodecimo - 16 pages per side", imp_scaling="Keep proportional",
              imp_position="Snug against binding edge", page_size="Royal Octavo (156 x 234 mm, 6.14 x 9.21 in)",
              **MARGINS)),
        ("Letter turned, source pages turned 90 degrees",
         dict(sheet_size="Letter", rotate_paper=True, imp_layout="Folio - 2 pages per side",
              imp_source_rot="Rotate 90° clockwise", imp_scaling="Keep proportional", **MARG_OFF)),
        ("JIS B0, quarto, stretch",
         dict(sheet_size="JIS B0", rotate_paper=False, imp_source_rot="No rotation", imp_layout="Quarto - 4 pages per side",
              imp_scaling="Stretch to fit", imp_position="Centered", page_size="B5 (176 x 250 mm)", **ZERO)),
        ("single-sided printer, backs reversed and rotated",
         dict(sheet_size="Legal", imp_layout="Folio - 2 pages per side", printer_type="Single-sided, backs in reverse order",
              rotate_back=True, imp_scaling="Keep proportional", page_size="Half Letter / Digest (5.5 x 8.5 in)",
              **MARG_OFF)),
        ("small layout",
         dict(sheet_size="Letter", printer_type="Duplex (two-sided printer)", rotate_back=False,
              imp_layout="Small book: 6 per side (3-folio signature)", **ZERO)),
    ]
    for label, conf in CONFIGS:
        set_vars(**conf)
        if not check(wait(lambda: window_ready(w), 120), f"[{label}] the window catches up with the settings"):
            continue
        probs = compare_window(w, label)
        check(not probs, f"[{label}] window drawing = shared placement = imposed PDF on every side; the numbers "
                         f"beside the sheet = the PDF {probs[:3]}")

    # the worked example in the window: custom paper 2834 x 4008 pt, a custom 8.5 x 11 in page
    set_vars(sheet_size="Custom", sheet_unit="pt", imp_layout="Folio - 2 pages per side", imp_scaling="Keep proportional",
             imp_position="Centered", page_size="Custom", custom_w=8.5, custom_h=11, **ZERO)
    app.custom_paper_on.set(True)
    app._custom_paper_toggled()
    app.sheet_w_text.set("2834")
    app.sheet_h_text.set("4008")
    pump(0.3)
    if check(wait(lambda: window_ready(w), 120), "the window shows the worked example"):
        w.sel = (0, 0)
        w.draw()
        nums, text = diag_numbers(w)
        check(w.info["cell"] == (2004.0, 2834.0) and nums.get("scale") == (3.27451, 3.27451) and
              nums.get("size") == (2004.0, 2593.41) and nums.get("top") == 120.29 and nums.get("bottom") == 120.29,
              f"the window shows scale 3.274510, 2004.00 x 2593.41 pt and 120.29 pt above and below {nums}")
        probs = compare_window(w, "worked example")
        check(not probs, f"[worked example] window = PDF {probs[:2]}")
        set_vars(imp_scaling="Stretch to fit")
        nums, _t = diag_numbers(w)
        check(nums.get("scale") == (3.27451, 3.578283) and nums.get("size") == (2004.0, 2834.0),
              f"Stretch to fit: 3.274510 x 3.578283, 2004 x 2834 pt, shown at once (no new typesetting) {nums}")
        set_vars(imp_scaling="Original size")
        nums, _t = diag_numbers(w)
        check(nums.get("scale") == (1.0, 1.0) and nums.get("size") == (612.0, 792.0) and nums.get("spine") == 696.0
              and nums.get("fore-edge") == 696.0 and nums.get("top") == 1021.0 and nums.get("bottom") == 1021.0,
              f"Original size: 612 x 792 pt with equal white space {nums}")

    # live: changing anything redraws at once; pages that have to be set again are never shown out of date
    set_vars(sheet_size="Letter", imp_scaling="Keep proportional", page_size="Half Letter / Digest (5.5 x 8.5 in)")
    app.custom_paper_on.set(False)
    app._custom_paper_toggled()
    check(wait(lambda: window_ready(w), 120), "back to Letter paper and a 5.5 x 8.5 in page")
    before = [(g.x, g.y, g.w, g.h) for _si, g in w.sides[0]["places"]]
    app.var("imp_top").set(50)
    settle(w)
    after = [(g.x, g.y, g.w, g.h) for _si, g in w.sides[0]["places"]]
    check(before != after and w.real_pages, "a margin change moves the pages in the window straight away")
    app.var("imp_top").set(0)
    app.var("page_size").set("Pocket (4 x 6 in)")
    settle(w)
    stale = w.real_pages and w.src_sizes and close(w.src_sizes[0][0], 5.5 * 72)
    check(not stale and all(close(g.src[0], 288) for _si, g in w.sides[0]["places"]),
          "right after the page size changes the window shows plain 4 x 6 in pages, never the old ones")
    check(wait(lambda: window_ready(w), 120) and close(w.src_sizes[0][0], 288) and close(w.src_sizes[0][1], 432),
          "then the book's real 4 x 6 in pages")
    app.var("imp_fore").set("abc")
    settle(w)
    check("isn't a number" in w.error and w.drawn == [] and "isn't a number" in app.placement_msg.cget("text") and
          str(app.placement_msg.cget("foreground")) == "#D9534F",
          "a margin that isn't a number: the window says so and draws no out-of-date sheet; the Output step too")
    check("Fore-edge margin" in (app.settings_problem(app.collect()) or ""),
          "and Preview book / Generate are stopped with the same message")
    app.var("imp_fore").set(0)
    settle(w)
    check(not w.error and w.drawn and app.placement_msg.cget("text") == BF.PLACEMENT_HINT, "fixing it brings it back")
    keep_size = app.var("page_size").get()
    app.var("page_size").set("Custom")
    app.var("custom_w").set("abc")
    settle(w)
    check("Custom page width" in (app.settings_problem(app.collect()) or ""),
          "a custom page width that isn't a number stops Preview book / Generate (never silently replaced)")
    app.var("custom_w").set(6)
    app.var("page_size").set(keep_size)
    settle(w)
    app.var("imp_offset_x").set("-12,5")
    settle(w)
    check(app.collect()["imp_offset_x"] == -12.5 and w.settings()["imp_offset_x"] == "-12,5" and
          w.sides[0]["places"][0][1].offset[0] == -12.5, "an offset typed with a decimal comma is used as typed")
    app.var("imp_offset_x").set(0)
    settle(w)

    # dragging a page and the arrow keys set the offsets; the PDF follows
    check(wait(lambda: window_ready(w), 120), "the window has the real pages again")
    w.go(0)
    w.sel = (0, 0)
    w.draw()
    si0, g0 = w.sides[0]["places"][0]
    x1, y1, x2, y2 = w.drawn[0][3]
    cx_, cy_ = (x1 + x2) / 2, (y1 + y2) / 2
    k_ = w.view()[0]
    w.canvas.event_generate("<ButtonPress-1>", x=int(cx_), y=int(cy_))
    w.canvas.event_generate("<B1-Motion>", x=int(cx_) + 30, y=int(cy_) - 20)
    w.canvas.event_generate("<ButtonRelease-1>", x=int(cx_) + 30, y=int(cy_) - 20)
    settle(w)
    want = bf_placement.offsets_after_drag(g0, (0.0, 0.0), 30, -20, k_)
    got = (app.var("imp_offset_x").get(), app.var("imp_offset_y").get())
    g1 = w.sides[0]["places"][0][1]
    check(close(got[0], want[0], 1e-9) and close(got[1], want[1], 1e-9) and close(g1.x - g0.x, 30 / k_, 0.006) and
          close(g1.y - g0.y, 20 / k_, 0.006),
          f"dragging a page 30 px right and 20 px up moves it {30 / k_:.2f} x {20 / k_:.2f} pt; offsets {got} in the "
          f"boxes")
    probs = compare_window(w, "after dragging")
    check(not probs, f"after dragging, the PDF puts every page where the window shows it {probs[:2]}")
    w.canvas.focus_force()
    pump(0.05)
    start = (app.var("imp_offset_x").get(), app.var("imp_offset_y").get())
    w.canvas.event_generate("<Right>")
    w.canvas.event_generate("<Up>", state=1)
    settle(w)
    want = bf_placement.nudge(g1, start, 1, 10)
    check((app.var("imp_offset_x").get(), app.var("imp_offset_y").get()) == want,
          f"arrow keys move the page 1 pt, with Shift 10 pt {want}")
    w.reset_offsets()
    settle(w)
    check((app.var("imp_offset_x").get(), app.var("imp_offset_y").get()) == (0.0, 0.0) and
          close(w.sides[0]["places"][0][1].x, g0.x, 1e-9), "Reset offsets puts the pages back")

    # another project: the window sets that book's pages; an open preview is never left showing the old book
    projA = os.path.join(TMP, "A.bookforge")
    projB = os.path.join(TMP, "B.bookforge")
    app.var("title").set("Book A")
    bf_edit.save_project(projA, app.book, app.collect(), "test")
    sB = dict(app.collect(), page_size="A6 (105 x 148 mm)", title="Book B", imp_offset_x=7, sheet_size="A4",
              margin_top=0.5, margin_bottom=0.5, margin_inner=0.6, margin_outer=0.5)
    bookB = apply_info(load_book(dict(sB, paste_text=BOOK_TEXT), BOOK_TEXT), dict(sB))
    bf_edit.save_project(projB, bookB, sB, "test")
    import json
    with open(projB, encoding="utf-8") as f:
        data = json.load(f)
    for key in ("imp_offset_x", "imp_offset_y"):
        data["settings"].pop(key, None)
    data["settings"]["sheet_size"] = "Large Crown Octavo"
    projOld = os.path.join(TMP, "old.bookforge")
    with open(projOld, "w", encoding="utf-8") as f:
        json.dump(data, f)
    idle()
    app.preview_book()
    check(wait(lambda: getattr(app, "preview_win", None) is not None and app.preview_win.alive() and not app.busy
               and app.preview_win.result is not None, 120), "Preview book shows the book")
    pw = app.preview_win
    filedialog.askopenfilename = lambda **kw: projB
    app.unsaved = False
    idle()
    app.open_project_dialog()
    check(pw.result is None and "out of date" in pw.w.title(), "opening another project marks the open preview out "
                                                               "of date at once")
    check(wait(lambda: pw.result is not None and pw.result["title"] == "Book B" and not app.busy, 120),
          "and the preview is made again for the new project")
    check(wait(lambda: window_ready(w) and close(w.src_sizes[0][0], 105 * MM, 0.01), 120) and
          app.var("imp_offset_x").get() == 7 and w.sides[0]["places"][0][1].offset[0] == 7,
          "the placement window shows the new project's pages (A6) and its offsets")
    probs = compare_window(w, "project B")
    check(not probs, f"[project B] window = PDF {probs[:2]}")
    filedialog.askopenfilename = lambda **kw: projOld
    idle()
    app.open_project_dialog()
    pump(0.2)
    check(app.var("sheet_size").get() == "Large Crown Octavo / Penguin Large Paperback" and
          app.var("imp_offset_x").get() == 0 and app.var("imp_offset_y").get() == 0,
          "a project from before offsets (with an old paper name) opens with no offsets and the same paper")
    check(wait(lambda: window_ready(w), 120), "and the window catches up")
    check(wait(lambda: pw.result is not None and not app.busy, 240),
          "and the open preview is made again for it too (BookForge is busy until then)")
    app.unsaved = False
    app.edited = False
    idle()
    app.new_book()
    pump(0.3)
    check(pw.result is None and app.book is None, "New book: the open preview is marked out of date, not left showing "
                                                  "the old book")
    check(wait(lambda: not w.real_pages and w.status.cget("text").startswith("No source"), 30),
          "and the placement window shows plain pages until there is a new source")
    pw.close()

    # dark/light switch closes the window cleanly; it opens again in the new look
    idle()
    app.toggle_dark()
    pump(0.5)
    check(app.placement_win is None and not w.alive(), "switching light/dark closes the placement window")
    app.open_placement()
    pump(0.5)
    w2 = app.placement_win
    check(w2 is not None and w2.alive() and w2.drawn, "and it opens again")
    w2.close()
    pump(0.2)
    app.var("imp_fore").set(3)
    app.var("page_size").set("Letter (8.5 x 11 in)")
    pump(0.3)
    check(app.placement_win is None, "closing it leaves nothing behind")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{COUNT['pdfs']} PDFs made and measured.")
print(f"{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
