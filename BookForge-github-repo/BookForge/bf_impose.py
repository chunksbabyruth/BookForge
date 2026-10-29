"""BookForge imposition: arranges finished book pages onto printer sheets for binding.

Imposition options:
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

from bf_core import safe_name, DEFAULTS, not_the_source

PT = 72.0


def _mm(w, h):
    """A size given in millimetres, as points (exact; 1 pt = 1/72 inch, 1 inch = 25.4 mm)."""
    return (w * PT / 25.4, h * PT / 25.4)


# Printer paper (sheets), width x height in points, the way round they are usually listed: the few landscape
# entries (Ledger, ID cards) lay out turned. US and architectural sizes are exact inches; ISO, JIS, ID-card and
# book sizes are exact millimetres (the names show them rounded and are never read back).
SHEETS = {
    "Letter": (612.0, 792.0), "Legal": (612.0, 1008.0), "Tabloid / 11x17": (792.0, 1224.0),
    "Half Letter": (396.0, 612.0), "Executive": (522.0, 756.0), "Note": (540.0, 720.0),
    "A3": _mm(297, 420), "A4": _mm(210, 297), "A5": _mm(148, 210), "A6": _mm(105, 148),
    "B4": _mm(250, 353), "B5": _mm(176, 250), "JIS B4": _mm(257, 364), "JIS B5": _mm(182, 257),
    "Postcard": (283.0, 416.0),
    "Ledger (17 x 11)": (1224.0, 792.0), "US Foolscap (8.5 x 13)": (612.0, 936.0), "Foolscap (9 x 13)": (648.0, 936.0),
    "ANSI C (17 x 22)": (1224.0, 1584.0), "ANSI D (22 x 34)": (1584.0, 2448.0), "ANSI E (34 x 44)": (2448.0, 3168.0),
    "Super B / A3+ (13 x 19)": (936.0, 1368.0), "SRA3": _mm(320, 450), "SRA4": _mm(225, 320),
    "A0": _mm(841, 1189), "A1": _mm(594, 841), "A2": _mm(420, 594), "A7": _mm(74, 105), "A8": _mm(52, 74),
    "A9": _mm(37, 52), "A10": _mm(26, 37), "B0": _mm(1000, 1414), "B1": _mm(707, 1000), "B2": _mm(500, 707), "B3": _mm(353, 500),
    "B6": _mm(125, 176), "B7": _mm(88, 125), "B8": _mm(62, 88), "B9": _mm(44, 62), "B10": _mm(31, 44),
    "JIS B0": _mm(1030, 1456), "JIS B1": _mm(728, 1030), "JIS B2": _mm(515, 728), "JIS B3": _mm(364, 515),
    "JIS B6": _mm(128, 182), "JIS B7": _mm(91, 128), "JIS B8": _mm(64, 91), "JIS B9": _mm(45, 64),
    "JIS B10": _mm(32, 45), "Arch A": (648.0, 864.0), "Arch B": (864.0, 1296.0),
    "Arch C": (1296.0, 1728.0), "Arch D": (1728.0, 2592.0), "Arch E": (2592.0, 3456.0),
    "Arch E1 (30 x 42)": (2160.0, 3024.0),
    "ID-1": _mm(85.6, 53.98), "ID-2": _mm(105, 74), "ID-3": _mm(125, 88),
    "Crown Quarto": _mm(189, 246), "Large Crown Quarto": _mm(201, 258),
    "Demy Quarto": _mm(219, 276), "Royal Quarto": _mm(237, 312), "Crown Octavo": _mm(123, 186),
    "Large Crown Octavo / Penguin Large Paperback": _mm(129, 198), "Demy Octavo": _mm(138, 216),
    "Royal Octavo": _mm(156, 234), "Small Paperback": _mm(111, 178), "Penguin Small Paperback": _mm(111, 181),
    "Custom": None,
}
# Names used by earlier BookForge versions (kept so their projects and settings still open the same paper).
SHEET_ALIASES = {"Tabloid": "Tabloid / 11x17", "11x17": "Tabloid / 11x17",
                 "Large Crown Octavo": "Large Crown Octavo / Penguin Large Paperback",
                 "Penguin Large Paperback": "Large Crown Octavo / Penguin Large Paperback"}
UNITS = {"in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4, "pt": 1.0}     # points per unit
# Display unit for paper selection: (code, menu name, word used after a size)
UNIT_CHOICES = [("in", "Inches", "inches"), ("mm", "Millimeters", "mm"), ("cm", "Centimeters", "cm"),
                ("pt", "Points", "points")]
UNIT_NAMES = {c: n for c, n, _w in UNIT_CHOICES}
UNIT_WORDS = {c: w for c, _n, w in UNIT_CHOICES}
# Custom paper: at least 1 pt and at most 14,400 pt (200 inches) a side - the largest page PDF readers open.
SHEET_MIN_PT, SHEET_MAX_PT = 1.0, 14400.0
FOLD_SIDES = ["Inside (recommended)", "Outside", "Both sides"]
FOLD_LAYOUTS = {  # name: (rows, cols, folds, landscape sheet)
    "Folio - 2 pages per side": (1, 2, "V", True),
    "Quarto - 4 pages per side": (2, 2, "HV", False),
    "Octavo - 8 pages per side": (2, 4, "vHV", True),   # first fold: right edge over to the left
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
    "imp_offset_x": 0.0, "imp_offset_y": 0.0,      # page offsets (pt): toward the fore-edge / toward the top
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
def sheet_name(s):
    name = s.get("sheet_size", "Letter")
    if name not in SHEETS:            # names used by earlier versions; anything unknown is Letter
        name = SHEET_ALIASES.get(name, "Letter")
    return name


def sheet_points(s):
    """The printer paper (sheet) as listed, in points: (width, height). Custom sizes are checked and a
    ValueError with a plain message is raised for an unusable one (never silently replaced)."""
    v = SHEETS[sheet_name(s)]
    if v is None:
        unit = s.get("sheet_unit", "in")
        v = custom_sheet_points(s.get("sheet_w"), s.get("sheet_h"), unit)
    return float(v[0]), float(v[1])


# --------------------------------------------------------------------------
# Paper sizes in other units (display only - sizes are kept in points or as the user typed them)
# --------------------------------------------------------------------------
def to_points(value, unit):
    return float(value) * UNITS[unit]


def from_points(pt, unit):
    return float(pt) / UNITS[unit]


_DECIMALS = {"in": 2, "mm": 1, "cm": 2, "pt": 2}


def fmt_length(pt, unit, edit=False):
    """A length for display: inches 8.5 / 11.0, mm 215.9, cm 21.59, points 612. edit=True keeps more
    digits (for the boxes where a custom size is typed). Display only - never used to compute a size."""
    v = from_points(pt, unit)
    d = _DECIMALS[unit] + (2 if edit else 0)
    t = f"{v:.{d}f}".rstrip("0").rstrip(".")
    if unit in ("in", "cm", "mm") and "." not in t and not edit:
        t += ".0"
    return t


def paper_dims_text(w_pt, h_pt, unit):
    return f"{fmt_length(w_pt, unit)} \u00d7 {fmt_length(h_pt, unit)} {UNIT_WORDS[unit]}"


def paper_label(s, unit=None):
    """'Letter (8.5 x 11.0 inches)' for the paper chosen in s, in the display unit (s["sheet_unit"])."""
    unit = unit or s.get("sheet_unit", "in")
    unit = unit if unit in UNITS else "in"
    name = sheet_name(s)
    w, h = sheet_points(s)
    return f"{name} ({paper_dims_text(w, h, unit)})"


def parse_length(text):
    """A typed number -> float. Raises ValueError with a plain message (empty, not a number, not finite)."""
    t = str(text if text is not None else "").strip().replace(",", ".")
    if not t:
        raise ValueError("type a number")
    try:
        v = float(t)
    except ValueError:
        raise ValueError(f"\u201c{text}\u201d isn't a number") from None
    if not math.isfinite(v):
        raise ValueError("the size must be an ordinary number")
    return v


def custom_sheet_points(w, h, unit):
    """Custom paper size -> (width, height) in points, checked. Raises ValueError with a plain message."""
    if unit not in UNITS:
        raise ValueError(f"Custom printer paper size: unknown unit \u201c{unit}\u201d.")
    out = []
    for name, v in (("width", w), ("height", h)):
        try:
            x = parse_length(v)
        except ValueError as e:
            raise ValueError(f"Custom printer paper {name}: {e}.") from None
        pt = x * UNITS[unit]
        shown = v.strip() if isinstance(v, str) else format(x, "g")
        if pt <= 0:
            raise ValueError(f"Custom printer paper {name} must be more than 0 (it is {shown}).")
        if pt < SHEET_MIN_PT:
            raise ValueError(f"Custom printer paper {name} is too small: at least 1 point "
                             f"({fmt_length(SHEET_MIN_PT, unit, True)} {UNIT_WORDS[unit]}).")
        if pt > SHEET_MAX_PT:
            raise ValueError(f"Custom printer paper {name} must be at most {fmt_length(SHEET_MAX_PT, unit)} "
                             f"{UNIT_WORDS[unit]} (it is {shown}).")
        out.append(pt)
    return tuple(out)


def parse_range(text, n):
    """'1-8, 10, 12-' -> sorted, de-duplicated zero-based page indexes.

    Reversed ranges ('6-4') are accepted and anything that selects no
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


CUSTOM_SIG_MAX = 200          # sheets in one custom signature (a sanity limit: 800+ pages folded together)
CUSTOM_SIG_HELP = ("Type the number of sheets in each signature, in order, separated by commas "
                   "(for example 4, 4, 6, 6).")


def custom_sizes(s):
    """The sheets per signature typed for "Custom signature sizes" ("4, 4, 6, 6" -> [4, 4, 6, 6]): whole
    numbers from 1 to CUSTOM_SIG_MAX, separated by commas (spaces and semicolons work too). Anything else is
    a ValueError with a plain message: a size is never guessed. (Before 1.8.0 "4.5" was read as two
    signatures of 4 and 5 sheets, "0" or a word was skipped, and a list without a number quietly used the
    standard signature size instead.)"""
    text = (s.get("sig_custom") or "").strip()
    tokens = [x for x in re.split(r"[,;\s]+", text) if x]
    if not tokens:
        raise ValueError("Custom signature sizes: no sizes typed. " + CUSTOM_SIG_HELP)
    out = []
    for x in tokens:
        if not re.fullmatch(r"[0-9]+", x) or not 1 <= int(x) <= CUSTOM_SIG_MAX:
            raise ValueError(f"Custom signature sizes: \u201c{x}\u201d isn't a whole number of sheets from 1 to "
                             f"{CUSTOM_SIG_MAX}. " + CUSTOM_SIG_HELP)
        out.append(int(x))
    return out


def signature_plan(sheets, s):
    fmt = s.get("sig_format", "Standard signatures")
    if fmt.startswith("Perfect"):
        return [1] * sheets
    if fmt.startswith("Booklet"):
        return [sheets]
    if fmt.startswith("Custom"):
        sizes = custom_sizes(s)                # (a ValueError if the sizes can't be read: never guessed)
        # The sizes in the order given (the last one again when the list runs out), only as many as the book
        # needs: each signature keeps its own size, and only the last one is completed with blank pages.
        # (Before 1.8.0 every size in the list was used, so a list longer than the book made whole
        # signatures of nothing but blank pages.)
        plan = []
        while sum(plan) < sheets:
            plan.append(sizes[min(len(plan), len(sizes) - 1)])
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

    Sheets are folded one at a time (each laid face "F" DOWN, folds made in order: V = left half
    over onto the right half, v = right half over onto the left half, H = top half down onto the
    bottom half) and then nested, sheet 0 outermost. Pages are 0-based within the signature.
    Face "F" is the outside of the folded sheet (it has the signature's first page); "B" is the inside.
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
                 if f in "Vv" else
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
        if f in "Vv":
            half = w // 2
            left_over = f == "V"              # V: the left half moves; v: the right half moves
            for layer in reversed(layers):
                moved = {(r, (w - 1 - c) - (half if left_over else 0)): k for (r, c), k in layer.items()
                         if (c < half) == left_over}
                if moved:
                    top.append(moved)
            for layer in layers:
                rem = {(r, c - (half if left_over else 0)): k for (r, c), k in layer.items()
                       if (c < half) != left_over}
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
    """Fold-line segments per sheet face ("F" = outside face, "B" = inside face, printed first)."""
    fold_plan(rows, cols, folds, 1)
    return _GUIDES[(rows, cols, folds)]


def fold_instructions(layout, nested=True):
    rows, cols, folds, _ = FOLD_LAYOUTS[layout]
    steps = [{"V": "bring the LEFT edge over to the RIGHT edge", "v": "bring the RIGHT edge over to the LEFT edge",
              "H": "bring the TOP edge down to the BOTTOM edge"}[f] for f in folds]
    txt = ("Fold every sheet on its own: lay it with the side that printed FIRST facing UP (page numbers "
           "the right way up), then " + "; ".join(f"fold {i + 1}: {x}" for i, x in enumerate(steps)) +
           (". Then nest the folded sheets of each signature. Each signature's innermost "
            "sheet prints first: put sheet 1 into the centre of sheet 2, those two into the centre of sheet 3, "
            "and so on, so the signature's last sheet is on the outside." if nested else
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


def drop_blank_rows(sides, fmt, duplex):
    """Leave out the empty rows of the first sheet so a short book
    prints its pages larger.  A row is only left out when its strip of paper is empty on both
    sides of the sheet, so the fronts and backs keep the same page size and still line up."""
    def empty(row):
        return all(idx is None for idx, _fl in row)

    if len(sides) == 1:                       # one-sided layout (the zine)
        kept = [row for row in sides[0] if not empty(row)]
        if kept:
            sides[0] = kept
        return sides
    fr, bk = sides[0], sides[1]
    n = len(fr)
    if len(bk) != n:
        return sides
    turned = fmt in STRIPS and not duplex     # single-sided strip backs are printed upside down

    def partner(j):
        return n - 1 - j if turned else j
    keep = [not (empty(fr[j]) and empty(bk[partner(j)])) for j in range(n)]
    if any(keep) and not all(keep):
        sides[0] = [fr[j] for j in range(n) if keep[j]]
        sides[1] = [bk[k] for k in range(n) if keep[partner(k)]]
    return sides


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
# --------------------------------------------------------------------------
# Page placement: where one page goes in its space on the sheet. The PDF (impose) and the page placement
# preview both use place_page / wacky_place through plan_imposition, so they can never disagree.
# All lengths are in points (1 pt = 1/72 inch), origin at the bottom left of the sheet.
# --------------------------------------------------------------------------
SCALINGS = ["Keep proportional", "Stretch to fit", "Original size"]
POSITIONS = ["Centered", "Snug against binding edge"]
MARGIN_MAX_PT = 10000.0          # margins: 0 .. 10,000 pt (139 inches) - more than the largest sheet's half
OFFSET_MAX_PT = 10000.0          # offsets: -10,000 .. 10,000 pt
_EPS = 1e-6
_MARGIN_LABELS = (("imp_fore", "Fore-edge margin"), ("imp_binding", "Binding margin"),
                  ("imp_top", "Top margin"), ("imp_bottom", "Bottom margin"))
_OFFSET_LABELS = (("imp_offset_x", "Offset toward the fore-edge"), ("imp_offset_y", "Offset toward the top"))


def parse_points(value, label, lo, hi):
    """A margin or offset in points -> float, checked (a number, finite, within lo..hi). ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError(f"{label}: type a number of points.")
    if isinstance(value, (int, float)):
        v = float(value)
        shown = format(v, "g")
    else:
        shown = str(value if value is not None else "").strip()
        if not shown:
            raise ValueError(f"{label}: type a number of points (0 for none).")
        try:
            v = float(shown.replace(",", ".").replace("\u2212", "-"))
        except ValueError:
            raise ValueError(f"{label}: \u201c{shown}\u201d isn't a number of points.") from None
    if not math.isfinite(v):
        raise ValueError(f"{label}: \u201c{shown}\u201d isn't an ordinary number of points.")
    if v < lo or v > hi:
        raise ValueError(f"{label} must be between {lo:g} and {hi:g} points (it is {shown}).")
    return v


def placement_settings(s):
    """The page scaling, position, margins and offsets from the settings, checked (ValueError with a plain
    message for a margin or offset that isn't an ordinary number in range)."""
    vals = {}
    for key, label in _MARGIN_LABELS:
        vals[key] = parse_points(s.get(key, 0.0) if s.get(key) is not None else 0.0, label, 0.0, MARGIN_MAX_PT)
    for key, label in _OFFSET_LABELS:
        vals[key] = parse_points(s.get(key, 0.0) if s.get(key) is not None else 0.0, label,
                                 -OFFSET_MAX_PT, OFFSET_MAX_PT)
    scaling = s.get("imp_scaling") or SCALINGS[0]
    if not any(scaling.startswith(x.split()[0]) for x in SCALINGS):
        scaling = SCALINGS[0]
    return {"scaling": scaling, "snug": (s.get("imp_position") or "Centered").startswith("Snug"),
            "position": "Snug against binding edge" if (s.get("imp_position") or "").startswith("Snug") else "Centered",
            "fore": vals["imp_fore"], "binding": vals["imp_binding"], "top": vals["imp_top"],
            "bottom": vals["imp_bottom"], "offset_x": vals["imp_offset_x"], "offset_y": vals["imp_offset_y"]}


class Placement:
    """One page in its space ("cell") on the sheet. Lengths in points, sheet origin at the bottom left.

    cell: (x0, y0, width, height) - the page's share of the sheet; area: the cell less the margins;
    bind: the side of the cell where the spine is, "L" or "R" (as seen on the printed sheet);
    rot: 0 = the page's head is up, 180 = upside down; ang: how far the source page is turned (degrees,
    counter-clockwise: the cell's 180 plus any source rotation); src: source page size; sx, sy: scale;
    x, y, w, h: where the page lands. gaps: white space between the page and its cell edges, named from
    the page's point of view (spine, fore-edge, top, bottom); a negative gap means the page sticks out."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def rotated(self):
        return self.ang % 360 != 0

    def clip_box(self, page):
        """None when the page stays inside its cell; otherwise the part of the source page (source page
        coordinates) that lies inside the cell, so nothing is printed over the neighbouring pages."""
        if self.fits_cell:
            return None
        mb = page.mediabox
        cx = float(mb.left) + float(mb.width) / 2
        cy = float(mb.bottom) + float(mb.height) / 2
        tx, ty = self.x + self.w / 2, self.y + self.h / 2
        a = math.radians(-self.ang)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        x0, y0, cw, ch = self.cell
        for px, py in ((x0, y0), (x0 + cw, y0), (x0, y0 + ch), (x0 + cw, y0 + ch)):
            qx, qy = (px - tx) / self.sx, (py - ty) / self.sy           # undo translate + scale
            pts.append((qx * ca - qy * sa + cx, qx * sa + qy * ca + cy))    # undo the turn
        cb = page.cropbox
        left = max(min(p[0] for p in pts), float(cb.left))
        right = min(max(p[0] for p in pts), float(cb.right))
        bottom = max(min(p[1] for p in pts), float(cb.bottom))
        top = min(max(p[1] for p in pts), float(cb.top))
        if right <= left or top <= bottom:
            return (float(cb.left), float(cb.bottom), float(cb.left), float(cb.bottom))   # nothing visible
        return (left, bottom, right, top)


def _clip_source(page, box):
    from pypdf.generic import RectangleObject
    page.cropbox = RectangleObject(box)
    page.trimbox = RectangleObject(box)


def _gaps(x, y, w, h, cell, bind, rot):
    x0, y0, cw, ch = cell
    left, right = x - x0, (x0 + cw) - (x + w)
    bottom, top = y - y0, (y0 + ch) - (y + h)
    spine, fore = (left, right) if bind == "L" else (right, left)
    head, foot = (top, bottom) if rot == 0 else (bottom, top)
    return {"spine": spine, "fore": fore, "top": head, "bottom": foot}


def place_page(cell, bind, rot, pw, ph, ang, ps):
    """Scale and position a pw x ph source page (turned by ang degrees) in its cell, following the page
    scaling, position, margins and offsets in ps (see placement_settings).

    Margins: whitespace kept free inside the cell at the spine (binding), fore-edge, top and bottom,
    measured from the page's point of view (the spine side is `bind`, the top is down when rot == 180).
    Keep proportional: one scale, min(usable width / page width, usable height / page height).
    Stretch to fit: usable width / page width across, usable height / page height down.
    Original size: scale 1. Centered: the page sits in the middle of the usable area; Snug: against the
    usable area's spine side, centered up and down. Offsets then move the page: offset_x toward the
    fore-edge (negative: toward the spine), offset_y toward the top (negative: toward the bottom)."""
    x0, y0, cw, ch = cell
    m_fore, m_bind, m_top, m_bot = ps["fore"], ps["binding"], ps["top"], ps["bottom"]
    ml = m_bind if bind == "L" else m_fore
    mr = m_fore if bind == "L" else m_bind
    mt, mb = (m_top, m_bot) if rot == 0 else (m_bot, m_top)
    aw, ah = cw - ml - mr, ch - mt - mb
    if aw <= 0 or ah <= 0:
        raise ValueError(f"The margins leave no room for the pages: each page has {cw:.2f} × {ch:.2f} pt "
                         f"on the sheet, and the margins take {ml + mr:.2f} pt across and {mt + mb:.2f} pt "
                         "down. Make the margins smaller.")
    ax, ay = x0 + ml, y0 + mb
    rw, rh = (ph, pw) if ang in (90, 270) else (pw, ph)
    mode = ps["scaling"]
    if mode.startswith("Original"):
        sx = sy = 1.0
    elif mode.startswith("Stretch"):
        sx, sy = aw / rw, ah / rh
    else:
        sx = sy = min(aw / rw, ah / rh)
    w, h = rw * sx, rh * sy
    x = (ax if bind == "L" else ax + aw - w) if ps["snug"] else ax + (aw - w) / 2
    y = ay + (ah - h) / 2
    x += ps["offset_x"] if bind == "L" else -ps["offset_x"]
    y += ps["offset_y"] if rot == 0 else -ps["offset_y"]
    gaps = _gaps(x, y, w, h, cell, bind, rot)
    need = {"spine": m_bind, "fore": m_fore, "top": m_top, "bottom": m_bot}
    return Placement(kind="fold", cell=cell, area=(ax, ay, aw, ah), bind=bind, rot=rot, ang=ang % 360,
                     src=(pw, ph), rsize=(rw, rh), sx=sx, sy=sy, x=x, y=y, w=w, h=h, mode=mode,
                     snug=ps["snug"], margins=need, offset=(ps["offset_x"], ps["offset_y"]), gaps=gaps,
                     fits_area=all(gaps[k] >= need[k] - _EPS for k in gaps),
                     fits_cell=all(v >= -_EPS for v in gaps.values()))


def wacky_geometry(W, H, nrows, ncols, pw0, ph0, s):
    """The small layouts' own spacing: every page the same size, as large as the grid allows (keep
    proportional), with the fore-edge padding between folios; page scaling, position, margins and offsets
    don't apply to them."""
    fore = float(s.get("wacky_fore") or 0)
    scale = min(W / (ncols * (pw0 + fore)), H / (nrows * ph0))
    pw, ph, fg = pw0 * scale, ph0 * scale, fore * scale
    packed = (s.get("wacky_spacing") or "Packed").startswith("Packed")
    left = (W - ncols * (pw + fg)) / (2 if packed else ncols)
    top = (H - nrows * ph) / (2 if packed else 2 * nrows)
    return {"nrows": nrows, "ncols": ncols, "pw0": pw0, "ph0": ph0, "pw": pw, "ph": ph, "fg": fg,
            "left": left, "top": top, "packed": packed, "fore": fore}


def wacky_cell_xy(g, r, i):
    hoff = g["left"] if g["packed"] else (1 + i - (i % 2)) * g["left"]
    voff = g["top"] if g["packed"] else g["top"] + 2 * g["top"] * r
    x = (g["pw"] + g["fg"]) * i + hoff + g["fg"] * ((i + 1) % 2)
    y = g["ph"] * r + voff         # row 0 at the bottom of the sheet
    return x, y


def wacky_place(g, x, y, ang, bind, size=None):
    """A page in its small-layout space. Pages of the first page's size fill the space exactly; a page of
    another size (only possible in a PDF that wasn't made by BookForge) keeps its proportions, centered."""
    pw, ph = g["pw"], g["ph"]
    cell = (x, y, pw, ph)
    sw, sh = (float(v) for v in size) if size else (g["pw0"], g["ph0"])
    if (sw, sh) == (g["pw0"], g["ph0"]):
        sx, sy, w, h, px, py = pw / sw, ph / sh, pw, ph, x, y
    else:
        sx = sy = min(pw / sw, ph / sh)
        w, h = sw * sx, sh * sy
        px, py = x + (pw - w) / 2, y + (ph - h) / 2
    return Placement(kind="small", cell=cell, area=cell, bind=bind, rot=ang, ang=ang, src=(sw, sh),
                     rsize=(sw, sh), sx=sx, sy=sy, x=px, y=py, w=w, h=h,
                     mode="Keep proportional (small layouts)", snug=False,
                     margins={"spine": 0.0, "fore": 0.0, "top": 0.0, "bottom": 0.0}, offset=(0.0, 0.0),
                     gaps=_gaps(px, py, w, h, cell, bind, ang), fits_area=True, fits_cell=True)


def first_placement(sides):
    for side in sides:
        for _si, g in side.get("places", []):
            return g
    return None


def placement_summary(sides):
    """One line for the printing notes: how the pages are scaled and placed (points)."""
    g = first_placement(sides)
    if g is None:
        return ""
    if g.kind == "small":
        return (f"Page placement: small layout, every page {g.w:.2f} \u00d7 {g.h:.2f} pt (scale {g.sx:.4f}); "
                "page scaling, position, margins and offsets don't apply to small layouts.")
    m = g.margins
    return (f"Page placement: {g.mode}, {'snug against the binding edge' if g.snug else 'centered'}; source page "
            f"{g.src[0]:.2f} \u00d7 {g.src[1]:.2f} pt, on the sheet {g.w:.2f} \u00d7 {g.h:.2f} pt (scale "
            f"{g.sx:.4f} \u00d7 {g.sy:.4f}) in a {g.cell[2]:.2f} \u00d7 {g.cell[3]:.2f} pt space; margins fore-edge "
            f"{m['fore']:g}, binding {m['spine']:g}, top {m['top']:g}, bottom {m['bottom']:g} pt; offsets "
            f"{g.offset[0]:g} pt toward the fore-edge, {g.offset[1]:g} pt toward the top.")


def placement_problems(sides):
    """A plain warning when pages don't fit their space (or their margins), else ''."""
    worst_cell, worst_area, original, offsets = 0.0, 0.0, False, False
    for side in sides:
        for _si, g in side.get("places", []):
            if g.kind != "fold":
                continue
            over_cell = -min(g.gaps.values())
            over_area = max(g.margins[k] - g.gaps[k] for k in g.gaps)
            worst_cell, worst_area = max(worst_cell, over_cell), max(worst_area, over_area)
            if over_area > _EPS:
                original = original or g.mode.startswith("Original")
                offsets = offsets or any(abs(v) > _EPS for v in g.offset)
    fixes = []
    if original:
        fixes.append("choose Keep proportional or Stretch to fit (Original size never shrinks pages)")
    if offsets:
        fixes.append("make the offsets smaller")
    fix = (" To fix it, " + " or ".join(fixes) + ".") if fixes else ""
    if worst_cell > _EPS:
        return (f"Pages don't fit their space on the sheet: they stick out by up to {worst_cell:.2f} pt, so "
                f"that part is cut off (nothing is printed over the neighbouring pages).{fix or ' Use a larger paper size.'}")
    if worst_area > _EPS:
        return (f"Pages run into the margins by up to {worst_area:.2f} pt (they still fit their space on "
                f"the sheet).{fix}")
    return ""


def plan_imposition(sizes, s, log=print):
    """Where every page goes - shared by impose() (the PDF) and the page placement preview, so both
    always agree. Reads and writes no PDF. sizes: (width, height) in points of every source page.

    Returns (info, sides). Each side has "rects" [(x, y, w, h, bind, item)] (used for the marks) and
    "places" [(source page index, Placement)] in sheet points (origin at the bottom left)."""
    for k, v in IMPOSE_DEFAULTS.items():
        s.setdefault(k, v)
    if not sizes:
        raise ValueError("There are no pages to arrange.")
    chosen = parse_range(s.get("imp_range"), len(sizes))
    if not chosen:
        raise ValueError("The page range doesn't include any pages.")
    order = [("b", None)] * (2 * int(s.get("flyleafs") or 0)) + [("p", i) for i in chosen] + \
        [("b", None)] * (2 * int(s.get("flyleafs") or 0))
    duplex = not s["printer_type"].startswith("Single")
    layout = s.get("imp_layout") if s.get("imp_layout") in LAYOUT_NAMES else LAYOUT_NAMES[0]
    rot_odd, rot_even = SOURCE_ROT.get(s.get("imp_source_rot"), (0, 0))
    W0, H0 = sheet_points(s)
    # The paper keeps the way round it is listed: a landscape entry (Ledger,
    # ID-1/2/3, or a custom size wider than it is tall) lays out like the upright size turned 90 degrees.
    turn = bool(s.get("rotate_paper")) != (W0 > H0)
    sides = []          # each: dict(front, sig, sheet, items=[...], lines=callable)
    info = {"layout": layout}

    pw0, ph0 = (float(v) for v in sizes[chosen[0]])

    if layout in FOLD_LAYOUTS:
        rows, cols, folds, landscape = FOLD_LAYOUTS[layout]
        W, H = (max(W0, H0), min(W0, H0)) if landscape else (min(W0, H0), max(W0, H0))
        if turn:
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
            # Printing order: each signature's innermost sheet first, and each sheet's
            # inside face ("B") before its outside face ("F").
            for sh in reversed(range(nsh)):
                for face in ("B", "F"):
                    items = []
                    for (r, c, p, rot, bind, inside) in plan[sh][face]:
                        items.append({"ref": chunk[p], "r": r, "c": c, "rot": rot, "bind": bind,
                                      "sigpage": p, "sigpages": len(chunk), "outer": sh == 0})
                    sides.append({"front": face == "B", "face": face, "sig": si, "sheet": sh, "items": items})
        firsts, pos = [], 0                 # signatures holding no book page (only flyleafs: blank on purpose)
        for nsh in plan_sizes:
            firsts.append(any(r[0] == "p" for r in order[pos:pos + nsh * per_sheet]))
            pos += nsh * per_sheet
        info.update(sheets=sum(plan_sizes), signatures=len(plan_sizes), plan=plan_sizes, blanks=blanks,
                    sheet=(W, H), cell=(cw, ch), instructions=fold_instructions(layout, max(plan_sizes) > 1),
                    per_sheet=per_sheet, flyleaf_pages=2 * int(s.get("flyleafs") or 0),
                    flyleaf_only=[i + 1 for i, has in enumerate(firsts) if not has],
                    custom=custom_sizes(s) if s.get("sig_format", "").startswith("Custom") else [])
    else:
        fmt = WACKY[layout]
        land = WACKY_LANDSCAPE[fmt]
        W, H = (max(W0, H0), min(W0, H0)) if land else (min(W0, H0), max(W0, H0))
        if turn:
            W, H = H, W
        refs = [o for o in order]
        wsides = drop_blank_rows(wacky_sides(fmt, len(refs), duplex), fmt, duplex)
        if fmt == "8_zine":
            book_pages = [r[1] for r in refs if r[0] == "p"]
            on_sheet = [r[1] for r in refs[:8] if r[0] == "p"]
            if len(on_sheet) < len(book_pages):
                left = len(book_pages) - len(on_sheet)
                info["warning"] = (f"The one-sheet zine holds 8 pages (flyleafs included), so {left} of the "
                                   f"{len(book_pages)} pages are left out: it ends at page {on_sheet[-1] + 1 if on_sheet else 0}. "
                                   "Use another layout, or a page range, for a longer book.")
                log("Note: " + info["warning"])
        for i, side in enumerate(wsides):
            sides.append({"front": i % 2 == 0, "sig": i // 2, "sheet": 0, "rows": side, "items": []})
        empty = sum(1 for side in wsides for row in side for idx, _fl in row if idx is None)
        info.update(sheets=math.ceil(len(wsides) / 2), signatures=0, plan=[], blanks=0, sheet=(W, H),
                    instructions=WACKY_HELP.get(fmt, ""), refs=refs, empty_spaces=empty,
                    flyleaf_pages=2 * int(s.get("flyleafs") or 0), flyleaf_only=[], custom=[])

    ps = placement_settings(s)

    def src_angle(ref):
        if ref[0] != "p":
            return 0
        return rot_odd if (ref[1] + 1) % 2 else rot_even

    # ---- lay out every side: where each page goes (the same numbers drive the PDF and the preview)
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
                ang = (src_angle(it["ref"]) + it["rot"]) % 360
                ref = it["ref"]
                pw, ph = (float(v) for v in sizes[ref[1]]) if ref[0] == "p" else (pw0, ph0)
                g = place_page((x0, y0, cw, ch), it["bind"], it["rot"], pw, ph, ang, ps)
                it["geo"] = g
                trim = trim or (g.w / PT, g.h / PT)
                rects.append((g.x, g.y, g.w, g.h, it["bind"], it))
                if it["ref"][0] == "p":
                    places.append((it["ref"][1], g))
        else:
            grid = side["rows"]
            wg = wacky_geometry(W, H, len(grid), max(len(r) for r in grid), pw0, ph0, s)
            trim = trim or (wg["pw"] / PT, wg["ph"] / PT)
            for r, row in enumerate(grid):
                for i, (idx, flip) in enumerate(row):
                    x, y = wacky_cell_xy(wg, r, i)
                    rects.append((x, y, wg["pw"], wg["ph"], "L" if i % 2 else "R", None))
                    if idx is None:
                        continue
                    ref = info["refs"][idx]
                    if ref[0] != "p":
                        continue
                    places.append((ref[1], wacky_place(wg, x, y, 180 if flip else 0, "L" if i % 2 else "R",
                                                       sizes[ref[1]])))
            side["geom"] = (wg["nrows"], wg["ncols"], wg["pw"], wg["ph"], wg["fg"], wg["left"], wg["top"],
                            wg["packed"])
        side["places"], side["rects"] = places, rects
    info["trim"] = trim or (pw0 / PT, ph0 / PT)
    info.update(layout=layout, page=(pw0, ph0), sheet=(W, H), placement=ps, duplex=duplex,
                fold=layout in FOLD_LAYOUTS)
    problems = placement_problems(sides)
    if problems:
        info["placement_warning"] = problems
        log("Note: " + problems)
    info["placement_note"] = placement_summary(sides)
    return info, sides


def impose(pdf_in, out_dir, base_name, s, log=print):
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black

    reader = PdfReader(pdf_in)
    src = list(reader.pages)
    info, sides = plan_imposition([(float(p.mediabox.width), float(p.mediabox.height)) for p in src], s, log)
    layout = info["layout"]
    W, H = info["sheet"]
    duplex = info["duplex"]
    rendered = [(side, [(si, _transform(src[si], g.ang, g.x, g.y, g.w, g.h, g.sx, g.sy), g.clip_box(src[si]))
                        for si, g in side["places"]], side["rects"]) for side in sides]

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
                for (x1, y1, x2, y2, fno, pos) in fold_guides(rows, cols, folds)[side["face"]]:
                    if show[pos]:
                        _fold_line(cv, x1 * cw, H - y1 * ch, x2 * cw, H - y2 * ch, fno)
            for (x, y, w_, h_, bind, it) in rects:
                if s["cut_marks"] and side["face"] == "F":         # crop marks on the outside face
                    _crop_marks(cv, x, y, w_, h_)
                ex = x if bind == "L" else x + w_                  # the page's spine-side edge
                cx0, _cy0, ccw, _cch = it["geo"].cell
                fx = cx0 if bind == "L" else cx0 + ccw              # the fold (the cell's spine edge)
                d = -1 if bind == "L" else 1
                if s["edge_marks"] and it["outer"]:
                    _cut(cv, ex, y + h_, ex + d * 6, y + h_, 0.6)
                    _cut(cv, ex, y, ex + d * 6, y, 0.6)
                if s["sig_marks"] and it["outer"] and it["sigpage"] == 0 and len(info.get("plan") or []) > 1:
                    usable = max(1, int((h_ - 24) // step))
                    my = y + h_ - 18 - (side["sig"] % usable) * step
                    cv.setFillColor(black)
                    cv.rect(fx - 3, my - 6, 6, 12, fill=1, stroke=0)      # on the fold, where the spine is
                    cv.setFont("Helvetica", 6)
                    cv.drawString(fx + (4 if bind == "R" else -9), my - 2, str(side["sig"] + 1))
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
                                cv.circle(fx, y + p, 1.1, stroke=0, fill=1)   # sewn through the fold
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
            for si, tf, clip in places:
                if clip is not None:            # a page bigger than its space: keep it inside its own space
                    _clip_source(src[si], clip)
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
        new = not_the_source(path, s)              # never the book's own source file
        if new != path:
            info.setdefault("renamed", []).append((path, new))
            log(f"\u201c{os.path.basename(path)}\u201d is the book's source file, so this file was saved as "
                f"\u201c{os.path.basename(new)}\u201d instead.")
        with open(new, "wb") as f:
            wr.write(f)
        files.append(new)

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
                write(build(bk, bool(s.get("rotate_back"))), base + " - backs (print second).pdf")

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
