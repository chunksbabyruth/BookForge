"""Regression tests for bf_impose (plain Python - run:  python tests/test_impose.py).

Fold-line rule checked here: each fold's guide line is printed on the face
that is on top when that fold is made, i.e. on the INSIDE of the fold, unless the user picks
Outside or Both.

Printing order (since 1.5.1): each signature's innermost sheet comes first, and
each sheet's inside face is printed before its outside face.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pdfplumber                                   # noqa: E402
from pypdf import PdfReader                         # noqa: E402
from reportlab.pdfgen import canvas                 # noqa: E402

import bf_impose                                    # noqa: E402
from bf_impose import (impose, IMPOSE_DEFAULTS, fold_plan, fold_guides, parse_range,  # noqa: E402
                       FOLD_LAYOUTS, LAYOUT_NAMES)

TMP = tempfile.mkdtemp(prefix="bf_test_")
FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def numbered_pdf(n=32, w=5.5 * 72, h=8.5 * 72):
    path = os.path.join(TMP, f"num{n}.pdf")
    c = canvas.Canvas(path, pagesize=(w, h))
    for i in range(1, n + 1):
        c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(w / 2, h / 2, f"P{i}")
        c.showPage()
    c.save()
    return path


def run(**kw):
    s = dict(IMPOSE_DEFAULTS)
    s.update(kw)
    out = tempfile.mkdtemp(dir=TMP)
    return impose(SRC, out, "t", s, log=lambda m: None)


def fold_lines(page):
    """Dashed fold guides = long axis-aligned lines that are not crop/edge marks."""
    out = []
    for l in page.lines:
        x0, x1, t, b = l["x0"], l["x1"], l["top"], l["bottom"]
        if abs(x0 - x1) < 0.5 and b - t > 60:
            out.append(("V", round(x0), round(t), round(b)))
        elif abs(t - b) < 0.5 and x1 - x0 > 60:
            out.append(("H", round(t), round(x0), round(x1)))
    return out


SRC = numbered_pdf(32)

# ---------------------------------------------------------------- page placement (unchanged)
for S in (1, 2, 8):
    n = 4 * S
    plan = fold_plan(1, 2, "V", S)
    ok = True
    for j in range(S):
        F = {c: p for r, c, p, rot, b, i in plan[j]["F"]}
        B = {c: p for r, c, p, rot, b, i in plan[j]["B"]}
        ok &= F == {0: n - 1 - 2 * j, 1: 2 * j} and B == {0: 2 * j + 1, 1: n - 2 - 2 * j}
    check(ok, f"folio page placement unchanged ({S} sheet signature)")
for name, (rows, cols, folds, _l) in FOLD_LAYOUTS.items():
    per = 2 * rows * cols
    pages = sorted(p for sh in fold_plan(rows, cols, folds, 3).values() for f in "FB" for _, _, p, _, _, _ in sh[f])
    check(pages == list(range(per * 3)), f"{name}: every page placed exactly once")

# ---------------------------------------------------------------- fold guides (the bug)
g = fold_guides(1, 2, "V")
check([x for x in g["B"] if x[5] == "in"] == [(1, 0, 1, 1, 0, "in")] and not [x for x in g["F"] if x[5] == "in"],
      "folio: inside fold line is on the inside face (printed first), centre, full height")

for kw, want_front, want_back, label in (
        ({}, 1, 0, "default = Inside"),                  # the inside face prints first
        ({"fold_side": "Outside"}, 0, 1, "Outside"),
        ({"fold_side": "Both sides"}, 1, 1, "Both sides")):
    info = run(sig_format="Perfect bound (every sheet separate)", imp_scaling="Stretch to fit", **kw)
    with pdfplumber.open(info["files"][0]) as pdf:
        fr = fold_lines(pdf.pages[0])
        bk = fold_lines(pdf.pages[1])
        W, H = pdf.pages[0].width, pdf.pages[0].height
    exp = [("V", round(W / 2), 0, round(H))]
    check((fr == exp) == bool(want_front) and (bk == exp) == bool(want_back) and
          (fr == [] or fr == exp) and (bk == [] or bk == exp),
          f"folio PDF fold lines, {label}: printed-first side {fr}, second side {bk}")

info = run(imp_layout="Quarto - 4 pages per side", sig_format="Perfect bound (every sheet separate)")
with pdfplumber.open(info["files"][0]) as pdf:
    W, H = pdf.pages[0].width, pdf.pages[0].height
    first, second = fold_lines(pdf.pages[0]), fold_lines(pdf.pages[1])
check(("H", round(H / 2), 0, round(W / 2)) in first and ("H", round(H / 2), round(W / 2), round(W)) in first,
      f"quarto: fold 1 runs full width on the side that is on top for fold 1, printed first ({first})")
check(second == [("V", round(W / 2), 0, round(H / 2))],
      f"quarto: fold 2 is half length, on the other side, on the half that shows ({second})")

for lay in ("Octavo - 8 pages per side", "Sextodecimo - 16 pages per side"):
    info = run(imp_layout=lay, sig_format="Perfect bound (every sheet separate)")
    with pdfplumber.open(info["files"][0]) as pdf:
        n_lines = len(fold_lines(pdf.pages[0])) + len(fold_lines(pdf.pages[1]))
    rows, cols, folds, _l = FOLD_LAYOUTS[lay]
    exp = sum(1 for f in "FB" for x in fold_guides(rows, cols, folds)[f] if x[5] == "in")
    check(n_lines == exp, f"{lay}: {n_lines} inside fold segments drawn (expected {exp})")

# ---------------------------------------------------------------- rotations / printers
info = run(rotate_back=True)
r = PdfReader(info["files"][0])
check(r.pages[0].get("/Rotate", 0) in (0, None) and r.pages[1].get("/Rotate") == 180,
      "rotate back sides: only the second side of each sheet is turned 180")
with pdfplumber.open(info["files"][0]) as pdf:
    check(len(fold_lines(pdf.pages[0])) == 1 and not fold_lines(pdf.pages[1]),
          "rotate back sides: fold line still on the inside face (printed first, not turned)")

info = run(rotate_paper=True)
r = PdfReader(info["files"][0])
p0 = r.pages[0]
check(float(p0.mediabox.width) < float(p0.mediabox.height) and p0.get("/Rotate", 0) in (0, None),
      "rotate paper 90: folio laid out on portrait paper (no /Rotate flag)")

info = run(printer_type="Single-sided (fronts and backs files)")
check(len(info["files"]) == 2, "single-sided: separate fronts and backs files")
with pdfplumber.open(info["files"][0]) as f_pdf, pdfplumber.open(info["files"][1]) as b_pdf:
    check(len(fold_lines(f_pdf.pages[0])) == 1 and not fold_lines(b_pdf.pages[0]),
          "single-sided: fold line is in the fronts file (inside face, printed first)")

# ---------------------------------------------------------------- page range rules
check(parse_range("", 5) == [0, 1, 2, 3, 4], "page range: empty = all pages")
check(parse_range("3, 1-2, 6-4", 8) == [0, 1, 2, 3, 4, 5], "page range: sorted, reversed range accepted")
check(parse_range("abc, 99-100", 5) == [0, 1, 2, 3, 4], "page range: nothing valid -> whole document")
check(parse_range("1-8, 10, 12-", 14) == [0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 12, 13],
      "page range: 1-8, 10, 12- (open-ended)")
check(parse_range("2, 2, 1-2", 5) == [0, 1], "page range: duplicates removed")

# ---------------------------------------------------------------- spine edge marks: outermost folio only
info = run(edge_marks=True, fold_marks=False, sig_sheets=2)
with pdfplumber.open(info["files"][0]) as pdf:
    def ticks(p):
        return [l for l in p.lines if abs(l["top"] - l["bottom"]) < 0.5 and 5 < l["x1"] - l["x0"] < 7]
    inner = len(ticks(pdf.pages[0])) + len(ticks(pdf.pages[1]))      # innermost sheet prints first
    outer = len(ticks(pdf.pages[2])) + len(ticks(pdf.pages[3]))
check(outer > 0 and inner == 0, f"spine edge marks only on the outermost folio (outer {outer}, inner {inner})")

# ---------------------------------------------------------------- every layout still builds
for lay in LAYOUT_NAMES:
    try:
        info = run(imp_layout=lay, cut_marks=True, edge_marks=True, sewing_marks=True)
        ok = all(os.path.getsize(f) > 0 for f in info["files"])
    except Exception as e:                           # pragma: no cover
        ok = False
        print("   ", e)
    check(ok, f"builds: {lay}")

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
