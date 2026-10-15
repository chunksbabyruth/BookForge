"""BookForge imposition: arranges finished book pages onto printer sheets for binding.

Covers the same options as the bookbinder-js imposer:
  * folio / quarto / octavo / sextodecimo (worked out by simulating the folds, so the
    folded sheet always reads in order) and the small "wacky" layouts
  * booklet / perfect bound / standard signatures / custom signature sizes, flyleafs
  * page range, source page rotation, page scaling, positioning and margins
  * fold lines, cut lines, spine edge marks, signature order marks, sewing marks
  * duplex or single-sided output, aggregated and/or per-signature files
"""
import io
import math
import os
import re

from bf_core import safe_name, DEFAULTS

PT = 72.0
SHEETS = {  # portrait width, height in points
    "Letter": (612, 792), "Legal": (612, 1008), "Tabloid / 11x17": (792, 1224),
    "Half Letter": (396, 612), "Executive": (522, 756), "Note": (540, 720),
    "A3": (842, 1191), "A4": (595, 842), "A5": (420, 595), "A6": (297, 420),
    "B4": (708, 1000), "B5": (498, 708), "JIS B4": (729, 1032), "JIS B5": (516, 729),
    "Postcard": (283, 416),
    "Ledger (17 x 11)": (792, 1224), "US Foolscap (8.5 x 13)": (612, 936), "Foolscap (9 x 13)": (648, 936),
    "A0": (2384, 3370), "A1": (1684, 2384), "A2": (1191, 1684), "A7": (210, 297), "A8": (148, 210),
    "A9": (105, 148), "B0": (2834, 4008), "B1": (2004, 2834), "B2": (1417, 2004), "B3": (1000, 1417),
    "B6": (354, 498), "B7": (249, 354), "B8": (175, 249), "B9": (124, 175), "B10": (87, 124),
    "JIS B0": (2920, 4127), "JIS B1": (2064, 2920), "JIS B2": (1460, 2064), "JIS B3": (1032, 1460),
    "JIS B6": (363, 516), "JIS B7": (258, 363), "Arch A": (648, 864), "Arch B": (864, 1296),
    "Arch C": (1296, 1728), "Arch E": (2592, 3456), "ID-1": (153, 242.65), "ID-2": (210, 297),
    "ID-3": (249, 354), "Crown Quarto": (535, 697), "Large Crown Quarto": (569, 731),
    "Demy Quarto": (620, 782), "Royal Quarto": (671, 884), "Crown Octavo": (348, 527),
    "Large Crown Octavo": (365, 561), "Demy Octavo": (391, 612), "Royal Octavo": (442, 663),
    "Small Paperback": (314, 504), "Penguin Small Paperback": (314, 513),
    "Penguin Large Paperback": (365, 561),
    "Custom": None,
}
UNITS = {"in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4, "pt": 1.0}
FOLD_SIDES = ["Inside (recommended)", "Outside", "Both sides"]
FOLD_LAYOUTS = {  # name: (rows, cols, folds, landscape sheet)
    "Folio - 2 pages per side": (1, 2, "V", True),
    "Quarto - 4 pages per side": (2, 2, "HV", False),
    "Octavo - 8 pages per side": (2, 4, "VHV", True),
    "Sextodecimo - 16 pages per side": (4, 4, "HVHV", False),
}
WACKY = {
    "Small book: 6 per side (3-folio signature)": "1_3rd",
    "Petite: 16 per side (4-folio signatures x 2)": "2_16s",
    "Single-sheet zine: 8 pages, one side": "8_zine",
    "Small: 18 per side (3-folio strips x 3)": "3_6s",
    "Little: 20 per side (3/3/4-folio signatures)": "3_3_4",
    "Tiny: 32 per side (4-folio strips x 4)": "4_8s",
    "Mini: 60 per side (folio strips x 6)": "6_10s",
}
LAYOUT_NAMES = list(FOLD_LAYOUTS) + list(WACKY)
SIG_FORMATS = ["Standard signatures", "Perfect bound (every sheet separate)", "Booklet (one signature)",
               "Custom signature sizes"]
SOURCE_ROT = {"No rotation": (0, 0), "Rotate 90\u00b0 clockwise": (-90, -90),
              "Rotate 90\u00b0 counter-clockwise": (90, 90),
              "Odd 90\u00b0 clockwise, even counter-clockwise (bound at bottom)": (-90, 90),
              "Odd 90\u00b0 counter-clockwise, even clockwise (bound at top)": (90, -90)}
SEWING_WHERE = ["Center of every folio", "Only on the spine (outside)", "Only in the center of each signature",
                "Spine and center of each signature"]

IMPOSE_DEFAULTS = {
    "imp_layout": "Folio - 2 pages per side", "sig_format": "Standard signatures", "sig_sheets": 8,
    "sig_custom": "", "flyleafs": 0, "imp_range": "", "imp_source_rot": "No rotation",
    "sheet_size": "Letter", "sheet_w": 8.5, "sheet_h": 11.0, "sheet_unit": "in",
    "printer_type": "Duplex (two-sided printer)", "rotate_paper": False, "rotate_back": False,
    "imp_scaling": "Keep proportional", "imp_position": "Centered",
    "imp_fore": 0.0, "imp_binding": 0.0, "imp_top": 0.0, "imp_bottom": 0.0,
    "fold_marks": True, "fold_side": "Inside (recommended)", "cut_marks": False, "edge_marks": False, "sig_marks": True,
    "sewing_marks": False, "sewing_where": "Center of every folio", "sewing_margin": 72.0,
    "sewing_count": 3, "sewing_tape": 36.0, "imp_files": "Aggregated file only",
    "wacky_spacing": "Packed", "wacky_fore": 0.0,
}


DEFAULTS.update(IMPOSE_DEFAULTS)
DEFAULTS["sig_sheets"] = 8


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def sheet_points(s):
    name = s.get("sheet_size", "Letter")
    if name not in SHEETS:            # names used by BookForge 1.0-1.2
        name = {"Tabloid": "Tabloid / 11x17"}.get(name, "Letter")
    v = SHEETS[name]
    if v is None:
        u = UNITS.get(s.get("sheet_unit", "in"), 72.0)
        v = (float(s.get("sheet_w") or 8.5) * u, float(s.get("sheet_h") or 11) * u)
    return float(v[0]), float(v[1])


def parse_range(text, n):
    """'1-8, 10, 12-' -> sorted, de-duplicated zero-based page indexes.

    Like bookbinder-js: reversed ranges ('6-4') are accepted and anything that selects no
    valid page falls back to the whole document. Open-ended ranges ('12-', '-5') also work.
    """
    text = (text or "").strip()
    if not text:
        return list(range(n))
    picked = set()
    for part in re.split(r"[,;\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1) or 1)
            b = int(m.group(2) or n)
            if a > b:
                a, b = b, a
            picked.update(p for p in range(a, b + 1) if 1 <= p <= n)
        elif part.isdigit() and 1 <= int(part) <= n:
            picked.add(int(part))
    return [p - 1 for p in sorted(picked)] if picked else list(range(n))


def signature_plan(sheets, s):
    fmt = s.get("sig_format", "Standard signatures")
    if fmt.startswith("Perfect"):
        return [1] * sheets
    if fmt.startswith("Booklet"):
        return [sheets]
    if fmt.startswith("Custom"):
        sizes = [int(x) for x in re.findall(r"\d+", s.get("sig_custom") or "") if int(x) > 0]
        if sizes:
            plan = list(sizes)
            while sum(plan) < sheets:
                plan.append(sizes[-1])
            return plan
    size = max(1, int(s.get("sig_sheets") or 8))
    n = math.ceil(sheets / size)
    base, extra = divmod(sheets, n)
    return [base + 1] * extra + [base] * (n - extra)


# --------------------------------------------------------------------------
# Fold simulation: where every page of a signature lands on its sheets
# --------------------------------------------------------------------------
_PLANS = {}


def fold_plan(rows, cols, folds, nsheets):
    """Returns {sheet: {"F": [...], "B": [...]}} with entries (row, col, page, rot, bind, inside).

    Sheets are folded one at a time (each laid printed-front-side DOWN, folds made in
    order: V = left half over onto the right half, H = top half down onto the bottom half)
    and then nested, sheet 0 outermost. Pages are 0-based within the signature.
    """
    key = (rows, cols, folds, nsheets)
    if key in _PLANS:
        return _PLANS[key]
    if nsheets > 1:                       # each sheet folded on its own, then nested in the centre
        one = fold_plan(rows, cols, folds, 1)[0]
        per = 2 * rows * cols
        n = per * nsheets
        plan = {}
        for j in range(nsheets):
            plan[j] = {face: [(r, c, (j * per // 2 + p) if p < per // 2 else n - (j + 1) * per // 2 + (p - per // 2),
                               rot, b, ins) for (r, c, p, rot, b, ins) in one[face]] for face in "FB"}
        _PLANS[key] = plan
        return plan
    state = {}
    layers = []
    for sh in reversed(range(nsheets)):           # sheet 0 ends up at the bottom = outermost
        layer = {}
        for r in range(rows):
            for c in range(cols):
                k = (sh, r, c)
                layer[(r, c)] = k
                state[k] = {"up": "B", "rot": 0, "nv": 0, "inside": "B"}
        layers.append(layer)
    h, w = rows, cols
    guides = {"F": [], "B": []}           # (x1, y1, x2, y2, fold_no, "in"/"out") in cell units

    def crease(a, b):
        """Shared edge of two neighbouring cells, in the simulation's (back-view) grid units."""
        ra, ca = a[1], a[2]
        rb, cb = b[1], b[2]
        if ra == rb and abs(ca - cb) == 1:
            x = max(ca, cb)
            return (x, ra, x, ra + 1)
        if ca == cb and abs(ra - rb) == 1:
            y = max(ra, rb)
            return (ca, y, ca + 1, y)
        return None
    for fi, f in enumerate(folds):
        # The fold is a valley as seen from above, so its guide belongs on the face that is
        # showing on top of the packet right now - only across the top layer.
        top_layer = layers[0]
        face = state[next(iter(top_layer.values()))]["up"]
        other = "F" if face == "B" else "B"
        pairs = ([(top_layer.get((r, w // 2 - 1)), top_layer.get((r, w // 2))) for r in range(h)]
                 if f == "V" else
                 [(top_layer.get((h // 2 - 1, c)), top_layer.get((h // 2, c))) for c in range(w)])
        for a, b in pairs:
            seg = crease(a, b) if a and b else None
            if not seg:
                continue
            x1, y1, x2, y2 = seg
            mirrored = (cols - x1, y1, cols - x2, y2)       # same spot seen from the other face
            on_back, on_front = (seg, mirrored)
            guides[face].append((on_back if face == "B" else on_front) + (fi, "in"))
            guides[other].append((on_back if other == "B" else on_front) + (fi, "out"))
        last = fi == len(folds) - 1
        if last:
            for st in state.values():
                st["inside"] = st["up"]
        top, bottom = [], []
        if f == "V":
            half = w // 2
            for layer in reversed(layers):
                moved = {(r, (w - 1 - c) - half): k for (r, c), k in layer.items() if c < half}
                if moved:
                    top.append(moved)
            for layer in layers:
                rem = {(r, c - half): k for (r, c), k in layer.items() if c >= half}
                if rem:
                    bottom.append(rem)
            for layer in top:
                for k in layer.values():
                    st = state[k]
                    st["up"] = "F" if st["up"] == "B" else "B"
                    st["nv"] += 1
            w = half
        else:
            half = h // 2
            for layer in reversed(layers):
                moved = {((h - 1 - r) - half, c): k for (r, c), k in layer.items() if r < half}
                if moved:
                    top.append(moved)
            for layer in layers:
                rem = {(r - half, c): k for (r, c), k in layer.items() if r >= half}
                if rem:
                    bottom.append(rem)
            for layer in top:
                for k in layer.values():
                    st = state[k]
                    st["up"] = "F" if st["up"] == "B" else "B"
                    st["rot"] = (st["rot"] + 180) % 360
            h = half
        layers = top + bottom
    plan = {sh: {"F": [], "B": []} for sh in range(nsheets)}
    for i, layer in enumerate(layers):
        (k,) = layer.values()
        st = state[k]
        sh, r, c = k
        up_page, down_page = 2 * i, 2 * i + 1
        front_page = up_page if st["up"] == "F" else down_page
        back_page = down_page if st["up"] == "F" else up_page
        # The sheets lie face DOWN, so the simulation's columns are as seen from the back.
        bind = "R" if st["nv"] % 2 else "L"            # binding side, seen from the back
        plan[sh]["B"].append((r, c, back_page, st["rot"], bind, st["inside"] == "B"))
        plan[sh]["F"].append((r, cols - 1 - c, front_page, st["rot"], "L" if bind == "R" else "R",
                              st["inside"] == "F"))
    _PLANS[key] = plan
    _GUIDES[(rows, cols, folds)] = guides
    return plan


_GUIDES = {}


def fold_guides(rows, cols, folds):
    """Fold-line segments per sheet face ("F" = side printed first, "B" = other side)."""
    fold_plan(rows, cols, folds, 1)
    return _GUIDES[(rows, cols, folds)]


def fold_instructions(layout, nested=True):
    rows, cols, folds, _ = FOLD_LAYOUTS[layout]
    steps = ["bring the LEFT edge over to the RIGHT edge" if f == "V" else
             "bring the TOP edge down to the BOTTOM edge" for f in folds]
    txt = ("Fold every sheet on its own: lay it with the side that printed FIRST facing DOWN (page numbers "
           "the right way up), then " + "; ".join(f"fold {i + 1}: {x}" for i, x in enumerate(steps)) +
           (". Then nest the folded sheets of each signature: sheet 2 goes into the centre of sheet 1, sheet 3 "
            "into the centre of sheet 2, and so on." if nested else
            ". Each folded sheet is its own signature: stack them in printed order (don't nest them)."))
    if len(folds) > 1:
        txt += " Crease each fold firmly; the folded edges at the top and outside are cut open after binding."
    return txt


# --------------------------------------------------------------------------
# Small "wacky" layouts (one or more little signatures per printed side)
# --------------------------------------------------------------------------
F, T = False, True


def _tbl(rows):
    return [[(k, fl) for k, fl in row] for row in rows]


WACKY_TABLES = {
    "1_3rd": (12, False, _tbl([[(8, F), (5, F)], [(9, T), (4, T)], [(12, F), (1, F)]]),
              _tbl([[(6, F), (7, F)], [(3, T), (10, T)], [(2, F), (11, F)]])),
    "3_3_4": (40, False,
              _tbl([[(36, F), (29, F), (28, F), (37, F)], [(33, T), (32, T), (25, T), (40, T)],
                    [(5, T), (8, T), (17, T), (20, T)], [(4, F), (9, F), (16, F), (21, F)],
                    [(1, T), (12, T), (13, T), (24, T)]]),
              _tbl([[(38, F), (27, F), (30, F), (35, F)], [(39, T), (26, T), (31, T), (34, T)],
                    [(19, T), (18, T), (7, T), (6, T)], [(22, F), (15, F), (10, F), (3, F)],
                    [(23, T), (14, T), (11, T), (2, T)]])),
    "2_16s": (32, False,
              _tbl([[(8, F), (9, F), (24, F), (25, F)], [(1, T), (16, T), (17, T), (32, T)],
                    [(4, F), (13, F), (20, F), (29, F)], [(5, T), (12, T), (21, T), (28, T)]]),
              _tbl([[(26, F), (23, F), (10, F), (7, F)], [(31, T), (18, T), (15, T), (2, T)],
                    [(30, F), (19, F), (14, F), (3, F)], [(27, T), (22, T), (11, T), (6, T)]])),
}
STRIPS = {  # rows per sheet, folios per strip, front order, back order (1-based within strip)
    "3_6s": (3, 3, [2, 11, 10, 3, 6, 7], [8, 5, 4, 9, 12, 1]),
    "4_8s": (4, 4, [2, 15, 14, 3, 6, 11, 10, 7], [8, 9, 12, 5, 4, 13, 16, 1]),
    "6_10s": (6, 5, [6, 3, 2, 7, 10, 19, 18, 11, 14, 15], [16, 13, 12, 17, 20, 9, 8, 1, 4, 5]),
}
WACKY_LANDSCAPE = {"8_zine": False, "1_3rd": False, "3_3_4": False, "2_16s": False,
                   "3_6s": True, "4_8s": True, "6_10s": True}
WACKY_HELP = {
    "8_zine": "One sheet, printed on one side only: the classic no-cut 8-page zine. Fold in half both ways, "
              "cut the centre slit, and fold up. Pages after 8 are left out.",
    "1_3rd": "Cut along the cut line (or just trim the top), then fold up along the dotted lines.",
    "2_16s": "Cut the vertical centre line (and the horizontal lines if you like), then fold up each folio "
             "signature.",
    "3_3_4": "Cut along the cut lines. Fold up the two 3-folio signatures, then the 4-folio one.",
    "3_6s": "Landscape layout: print flipped on the SHORT edge. Cut out the rows, fold each row's folios in a "
            "zig-zag (two pages per face), then fold the centre so matching page numbers meet.",
    "4_8s": "Landscape layout: print flipped on the SHORT edge. Cut out the rows, fold each row's folios in a "
            "zig-zag, then fold the centre so matching page numbers meet.",
    "6_10s": "Landscape layout: print flipped on the SHORT edge. Cut out the rows, zig-zag fold the folios, "
             "then make the first 2 folios one signature and the last 3 another.",
}


def wacky_sides(fmt, npages, duplex):
    """List of sides; each side is a list of rows of (page_index or None, upside_down)."""
    def pg(base, k, fl):
        idx = base + k - 1
        return (idx if idx < npages else None, fl)

    if fmt == "8_zine":
        return [[[pg(0, k, F) for k in (8, 1, 2, 3)], [pg(0, k, T) for k in (7, 6, 5, 4)]]]
    if fmt in WACKY_TABLES:
        per, _x, front, back = WACKY_TABLES[fmt]
        sides = []
        for sh in range(max(1, math.ceil(npages / per))):
            base = sh * per
            sides.append([[pg(base, k, fl) for k, fl in row] for row in front])
            sides.append([[pg(base, k, fl) for k, fl in row] for row in back])
        return sides
    rows, folios, forder, border = STRIPS[fmt]
    per_row = folios * 4
    nrows = max(1, math.ceil(npages / per_row))
    fronts, backs = [], []
    for r in range(nrows):
        base = r * per_row
        fr = [pg(base, k, F) for k in forder]
        bk = [pg(base, k, F) for k in border]
        if not duplex:
            bk.reverse()
        fronts.append(fr)
        backs.append(bk)
    sheets = []
    for r in range(nrows):
        if r % rows == 0:
            sheets.append(([], []))
        sheets[-1][0].insert(0, fronts[r])
        sheets[-1][1].insert(0, backs[r])
    blank = [(None, F)] * (folios * 2)
    filler = 0
    while len(sheets[-1][0]) < rows:
        if filler % 2 == 0:
            sheets[-1][0].insert(0, blank)
            sheets[-1][1].insert(0, blank)
        else:
            sheets[-1][0].append(blank)
            sheets[-1][1].append(blank)
        filler += 1
    out = []
    for fr, bk in sheets:
        out.append(fr)
        if not duplex:
            bk = [[(p, not fl) for p, fl in row] for row in reversed(bk)]
        out.append(bk)
    return out


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def _transform(src, angle, x, y, w, h, sx, sy):
    from pypdf import Transformation
    mb = src.mediabox
    cx = float(mb.left) + float(mb.width) / 2
    cy = float(mb.bottom) + float(mb.height) / 2
    return Transformation().translate(-cx, -cy).rotate(angle).scale(sx, sy).translate(x + w / 2, y + h / 2)


def _dashed(c, x1, y1, x2, y2):
    from reportlab.lib.colors import HexColor
    c.saveState()
    c.setStrokeColor(HexColor("#888888"))
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    c.line(x1, y1, x2, y2)
    c.restoreState()


FOLD_STYLES = [((10, 5), 0.8), ((5, 5), 0.65), ((3, 5), 0.5), ((1, 5), 0.45)]   # fold 1 boldest


def _fold_line(c, x1, y1, x2, y2, fold_no):
    from reportlab.lib.colors import HexColor
    dash, width = FOLD_STYLES[min(fold_no, len(FOLD_STYLES) - 1)]
    c.saveState()
    c.setStrokeColor(HexColor("#666666"))
    c.setLineWidth(width)
    c.setDash(*dash)
    c.line(x1, y1, x2, y2)
    c.restoreState()


def _cut(c, x1, y1, x2, y2, width=0.35):
    from reportlab.lib.colors import HexColor
    c.saveState()
    c.setStrokeColor(HexColor("#555555"))
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    c.restoreState()


def _crop_marks(c, x, y, w, h, off=3, ln=9):
    for cx, sx in ((x, -1), (x + w, 1)):
        for cy, sy in ((y, -1), (y + h, 1)):
            _cut(c, cx + sx * off, cy, cx + sx * (off + ln), cy)
            _cut(c, cx, cy + sy * off, cx, cy + sy * (off + ln))


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------
def impose(pdf_in, out_dir, base_name, s, log=print):
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black

    for k, v in IMPOSE_DEFAULTS.items():
        s.setdefault(k, v)
    reader = PdfReader(pdf_in)
    src = list(reader.pages)
    chosen = parse_range(s.get("imp_range"), len(src))
    if not chosen:
        raise ValueError("The page range doesn't include any pages.")
    order = [("b", None)] * (2 * int(s.get("flyleafs") or 0)) + [("p", i) for i in chosen] + \
        [("b", None)] * (2 * int(s.get("flyleafs") or 0))
    duplex = not s["printer_type"].startswith("Single")
    layout = s.get("imp_layout") if s.get("imp_layout") in LAYOUT_NAMES else LAYOUT_NAMES[0]
    rot_odd, rot_even = SOURCE_ROT.get(s.get("imp_source_rot"), (0, 0))
    W0, H0 = sheet_points(s)
    sides = []          # each: dict(front, sig, sheet, items=[...], lines=callable)
    info = {"layout": layout}

    sp = src[chosen[0]]
    pw0, ph0 = float(sp.mediabox.width), float(sp.mediabox.height)

    if layout in FOLD_LAYOUTS:
        rows, cols, folds, landscape = FOLD_LAYOUTS[layout]
        W, H = (max(W0, H0), min(W0, H0)) if landscape else (min(W0, H0), max(W0, H0))
        if s.get("rotate_paper"):
            W, H = H, W
        per_sheet = 2 * rows * cols
        filled = len(order)
        while len(order) % per_sheet:
            order.append(("b", None))
        plan_sizes = signature_plan(len(order) // per_sheet, s)
        need = sum(plan_sizes) * per_sheet
        blanks = need - filled
        order += [("b", None)] * (need - len(order))
        cw, ch = W / cols, H / rows
        pos = 0
        for si, nsh in enumerate(plan_sizes):
            chunk = order[pos:pos + nsh * per_sheet]
            pos += nsh * per_sheet
            plan = fold_plan(rows, cols, folds, nsh)
            for sh in range(nsh):
                for face in ("F", "B"):
                    items = []
                    for (r, c, p, rot, bind, inside) in plan[sh][face]:
                        items.append({"ref": chunk[p], "r": r, "c": c, "rot": rot, "bind": bind,
                                      "sigpage": p, "sigpages": len(chunk), "outer": sh == 0})
                    sides.append({"front": face == "F", "sig": si, "sheet": sh, "items": items})
        info.update(sheets=sum(plan_sizes), signatures=len(plan_sizes), plan=plan_sizes, blanks=blanks,
                    sheet=(W, H), cell=(cw, ch), instructions=fold_instructions(layout, max(plan_sizes) > 1))
    else:
        fmt = WACKY[layout]
        land = WACKY_LANDSCAPE[fmt]
        W, H = (max(W0, H0), min(W0, H0)) if land else (min(W0, H0), max(W0, H0))
        if s.get("rotate_paper"):
            W, H = H, W
        refs = [o for o in order]
        wsides = wacky_sides(fmt, len(refs), duplex)
        for i, side in enumerate(wsides):
            sides.append({"front": i % 2 == 0, "sig": i // 2, "sheet": 0, "rows": side, "items": []})
        info.update(sheets=math.ceil(len(wsides) / 2), signatures=0, plan=[], blanks=0, sheet=(W, H),
                    instructions=WACKY_HELP.get(fmt, ""), refs=refs)

    scaling = s.get("imp_scaling", "Keep proportional")
    snug = s.get("imp_position", "Centered").startswith("Snug")
    m_fore, m_bind = float(s.get("imp_fore") or 0), float(s.get("imp_binding") or 0)
    m_top, m_bot = float(s.get("imp_top") or 0), float(s.get("imp_bottom") or 0)

    def src_angle(ref):
        if ref[0] != "p":
            return 0
        return rot_odd if (ref[1] + 1) % 2 else rot_even

    # ---- lay out every side: placements + marks
    rendered = []           # (side, [(src_index, transform)], marks_draw_fn)
    trim = None
    for side in sides:
        places = []
        rects = []
        if "rows" not in side:
            rows, cols, folds, _l = FOLD_LAYOUTS[layout]
            cw, ch = info["cell"]
            for it in side["items"]:
                x0 = it["c"] * cw
                y0 = H - (it["r"] + 1) * ch
                rot, bind = it["rot"], it["bind"]
                ml = m_bind if bind == "L" else m_fore
                mr = m_fore if bind == "L" else m_bind
                mt, mb = (m_top, m_bot) if rot == 0 else (m_bot, m_top)
                ax, ay, aw, ah = x0 + ml, y0 + mb, max(1, cw - ml - mr), max(1, ch - mt - mb)
                ang = (src_angle(it["ref"]) + rot) % 360
                rw, rh = (ph0, pw0) if ang in (90, 270) else (pw0, ph0)
                if scaling.startswith("Original"):
                    sx = sy = 1.0
                elif scaling.startswith("Stretch"):
                    sx, sy = aw / rw, ah / rh
                else:
                    sx = sy = min(aw / rw, ah / rh)
                w_, h_ = rw * sx, rh * sy
                x = (ax if bind == "L" else ax + aw - w_) if snug else ax + (aw - w_) / 2
                y = ay + (ah - h_) / 2
                trim = trim or (w_ / PT, h_ / PT)
                rect = (x, y, w_, h_, bind, it)
                rects.append(rect)
                if it["ref"][0] == "p":
                    places.append((it["ref"][1], _transform(src[it["ref"][1]], ang, x, y, w_, h_, sx, sy)))
        else:
            grid = side["rows"]
            nrows = len(grid)
            ncols = max(len(r) for r in grid)
            fore = float(s.get("wacky_fore") or 0)
            scale = min(W / (ncols * (pw0 + fore)), H / (nrows * ph0))
            pw, ph, fg = pw0 * scale, ph0 * scale, fore * scale
            packed = s.get("wacky_spacing", "Packed").startswith("Packed")
            left = (W - ncols * (pw + fg)) / (2 if packed else ncols)
            top = (H - nrows * ph) / (2 if packed else 2 * nrows)
            trim = trim or (pw / PT, ph / PT)
            for r, row in enumerate(grid):
                for i, (idx, flip) in enumerate(row):
                    hoff = left if packed else (1 + i - (i % 2)) * left
                    voff = top if packed else top + 2 * top * r
                    x = (pw + fg) * i + hoff + fg * ((i + 1) % 2)
                    y_top = ph * r + voff
                    y = H - y_top - ph
                    rects.append((x, y, pw, ph, "L" if i % 2 else "R", None))
                    if idx is None:
                        continue
                    ref = info["refs"][idx]
                    if ref[0] != "p":
                        continue
                    ang = 180 if flip else 0
                    places.append((ref[1], _transform(src[ref[1]], ang, x, y, pw, ph, pw / pw0, ph / ph0)))
            side["geom"] = (nrows, ncols, pw, ph, fg, left, top, packed)
        rendered.append((side, places, rects))
    info["trim"] = trim or (pw0 / PT, ph0 / PT)

    # ---- marks overlay (one reportlab page per side)
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=(W, H))
    step = 14
    for side, places, rects in rendered:
        if "rows" not in side:
            rows, cols, folds, _l = FOLD_LAYOUTS[layout]
            cw, ch = info["cell"]
            if s["fold_marks"]:
                where = s.get("fold_side", FOLD_SIDES[0])
                show = {"in": not where.startswith("Outside"), "out": not where.startswith("Inside")}
                for (x1, y1, x2, y2, fno, pos) in fold_guides(rows, cols, folds)["F" if side["front"] else "B"]:
                    if show[pos]:
                        _fold_line(cv, x1 * cw, H - y1 * ch, x2 * cw, H - y2 * ch, fno)
            for (x, y, w_, h_, bind, it) in rects:
                if s["cut_marks"] and side["front"]:
                    _crop_marks(cv, x, y, w_, h_)
                ex = x if bind == "L" else x + w_
                d = -1 if bind == "L" else 1
                if s["edge_marks"] and it["outer"]:
                    _cut(cv, ex, y + h_, ex + d * 6, y + h_, 0.6)
                    _cut(cv, ex, y, ex + d * 6, y, 0.6)
                if s["sig_marks"] and it["outer"] and it["sigpage"] == 0 and len(info.get("plan") or []) > 1:
                    usable = max(1, int((h_ - 24) // step))
                    my = y + h_ - 18 - (side["sig"] % usable) * step
                    cv.setFillColor(black)
                    cv.rect(ex - 3, my - 6, 6, 12, fill=1, stroke=0)
                    cv.setFont("Helvetica", 6)
                    cv.drawString(ex + (4 if bind == "R" else -9), my - 2, str(side["sig"] + 1))
                if s["sewing_marks"] and bind == "L":
                    where = s.get("sewing_where", SEWING_WHERE[0])
                    first = it["sigpage"] == 0
                    middle = it["sigpage"] == it["sigpages"] // 2
                    ok = (where.startswith("Center of every") or (where.startswith("Only on") and first)
                          or (where.startswith("Only in") and middle)
                          or (where.startswith("Spine and") and (first or middle)))
                    if ok:
                        margin = float(s.get("sewing_margin") or 0)
                        n = int(s.get("sewing_count") or 0)
                        tape = float(s.get("sewing_tape") or 0)
                        work = h_ - 2 * margin
                        gap = work / (n + 1) if n >= 0 else 0
                        pts = [margin, h_ - margin]
                        for i in range(1, n + 1):
                            pts += [margin + gap * i + tape / 2, margin + gap * i - tape / 2]
                        cv.setFillColor(black)
                        for p in pts:
                            if 0 <= p <= h_:
                                cv.circle(ex, y + p, 1.1, stroke=0, fill=1)
        else:
            nrows, ncols, pw, ph, fg, left, top, packed = side["geom"]
            if s["fold_marks"] or s["cut_marks"]:
                for (x, y, w_, h_, _b, _i) in rects:
                    for cx in (x, x + w_):
                        for cy in (y, y + h_):
                            _cut(cv, cx - 3, cy, cx + 3, cy, 0.3)
                            _cut(cv, cx, cy - 3, cx, cy + 3, 0.3)
            if s["fold_marks"]:
                for (x, y, w_, h_, b, _i) in rects:
                    if b == "R":          # fold between the two pages of each folio
                        _dashed(cv, x + w_, y, x + w_, y + h_)
            if s["cut_marks"] and side["front"]:
                ys = sorted({round(r[1], 2) for r in rects} | {round(r[1] + r[3], 2) for r in rects})
                for yy in ys:
                    _cut(cv, 0, yy, W, yy, 0.25)
        cv.showPage()
    cv.save()
    overlay = PdfReader(io.BytesIO(buf.getvalue()))

    # ---- assemble output files
    rot_paper = 0          # "Rotate paper 90" now changes the layout itself (see above)

    def build(side_list, back_rotate):
        wr = PdfWriter()
        for idx in side_list:
            side, places, _r = rendered[idx]
            pg = wr.add_blank_page(W, H)
            for si, tf in places:
                pg.merge_transformed_page(src[si], tf)
            pg.merge_page(overlay.pages[idx])
            r = rot_paper + (180 if (back_rotate and not side["front"]) else 0)
            if r:
                pg.rotate(r % 360)
        return wr

    files = []
    mode = s.get("imp_files", "Aggregated file only")
    all_idx = list(range(len(rendered)))
    os.makedirs(out_dir, exist_ok=True)

    def write(wr, path):
        with open(path, "wb") as f:
            wr.write(f)
        files.append(path)

    def emit(indices, base):
        if duplex:
            write(build(indices, bool(s.get("rotate_back"))), base + ".pdf")
        else:
            fr = [i for i in indices if rendered[i][0]["front"]]
            bk = [i for i in indices if not rendered[i][0]["front"]]
            if "reverse" in s["printer_type"].lower():
                bk.reverse()
            write(build(fr, False), base + " - fronts (print first).pdf")
            if bk:
                write(build(bk, False), base + " - backs (print second).pdf")

    if not mode.startswith("Signature files") or layout not in FOLD_LAYOUTS:
        emit(all_idx, os.path.join(out_dir, base_name + " - Imposed for binding"))
    if not mode.startswith("Aggregated") and layout in FOLD_LAYOUTS:
        sdir = os.path.join(out_dir, "Signatures")
        os.makedirs(sdir, exist_ok=True)
        for sig in range(info["signatures"]):
            emit([i for i in all_idx if rendered[i][0]["sig"] == sig],
                 os.path.join(sdir, f"{safe_name(base_name)} - signature {sig + 1:02d}"))
    info["files"] = files
    info["duplex"] = duplex
    info["sheet_in"] = (W / PT, H / PT)
    return info
