"""Checks for page-number numerals, number pictures and positions (1.8.1; plain Python - run:
python tests/test_page_numbers_181.py).

Layout -> Page numbers & headers: "Numerals" (setting pn_numerals: Arabic - the standard -, lowercase / uppercase
Roman, custom digit pictures, custom whole-number pictures) and "Position" (pn_position: the four positions of
earlier versions plus top / bottom left / right, top centre and the middle of the outside edge). These checks
read the made PDFs - every character and every picture with its position - and draw the pictures they need
themselves (no picture files are kept with the tests):

1. Roman numerals (subtractive forms, the 1-3999 range) and the setting's checks.
2. The standard (and settings / projects from before 1.8.1): the same pages as before, 1, 2, 3 bottom centre.
3. Roman numerals on the pages and on the contents page; the Roman front matter keeps i, ii, iii.
4. Digit pictures: 128 = the pictures of 1, 2 and 8, in that order, one scale, bottoms lined up, the spacing
   as set; transparent PNGs; missing, damaged and unusable pictures; the copies kept in a project.
5. Whole-number pictures (Cistercian numerals, drawn as the generator at codepo8.github.io/cistercian draws
   them): one glyph per page, the right glyph (checked on the rendered page), only the pictures needed are
   read, no number 0, missing / damaged pictures and folders, file-name patterns.
6. All positions, on left- and right-hand pages, as text and as pictures, inside the margins; the middle of the
   outside edge alternates by the page's place in the book.
7. Pages without numbers stay without (front matter, chapter openings, title page, blank pages, blank pages
   added before/after the book); signature padding gets none.
8. Preview = Print PDF = imposed sheets; on the imposed sheets every page's number is where the page's own
   number is (mapped through the imposition), never twice.
9. Long books and numbers near the limits (3999 Roman, 9999 pictures).
10. Projects: saved and reopened, moved with their picture folders, older projects; the Word document.
11. Window checks (Numerals box, picture settings shown only when used, folder checks, sample).
Window checks run only where a display is available. Nothing needs the internet.
"""
import copy
import math
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_folio_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
import pypdfium2 as pdfium                                            # noqa: E402
from PIL import Image, ImageDraw                                      # noqa: E402

import bf_edit                                                        # noqa: E402
import bf_folio                                                       # noqa: E402
import bf_impose                                                      # noqa: E402
from bf_build import build_preview, run_build                         # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, page_size_inches  # noqa: E402
from bf_pdf import build_pdf, contents_entries, contents_rows, rows_to_edits  # noqa: E402

FAILS = []
DIGEST = "Half Letter / Digest (5.5 x 8.5 in)"


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


# ---------------------------------------------------------------------------------------------- pictures
# Cistercian numerals as drawn by the codepo8 generator: 120 x 180, 4 px square-capped strokes, the stave from
# (60,20) to (60,160); units top right, tens top left, hundreds bottom right, thousands bottom left.
_P = [(10, 10), (30, 10), (50, 10), (10, 30), (30, 30), (50, 30), (10, 50), (30, 50), (50, 50), (10, 60), (30, 60),
      (50, 60), (10, 80), (30, 80), (50, 80)]
_G = {1: [(1, 2)], 2: [(4, 5)], 3: [(1, 5)], 4: [(4, 2)], 5: [(1, 2), (2, 4)], 6: [(2, 5)], 7: [(1, 2), (2, 5)],
      8: [(4, 5), (5, 2)], 9: [(1, 2), (2, 5), (5, 4)],
      10: [(0, 1)], 20: [(3, 4)], 30: [(1, 3)], 40: [(4, 0)], 50: [(0, 1), (0, 4)], 60: [(0, 3)],
      70: [(0, 1), (0, 3)], 80: [(4, 3), (3, 0)], 90: [(0, 1), (0, 3), (3, 4)],
      100: [(14, 13)], 200: [(10, 11)], 300: [(13, 11)], 400: [(10, 14)], 500: [(13, 14), (14, 10)],
      600: [(14, 11)], 700: [(13, 14), (14, 11)], 800: [(10, 11), (11, 14)], 900: [(13, 14), (14, 11), (11, 10)],
      1000: [(12, 13)], 2000: [(9, 10)], 3000: [(13, 9)], 4000: [(10, 12)], 5000: [(13, 12), (12, 10)],
      6000: [(12, 9)], 7000: [(13, 12), (12, 9)], 8000: [(12, 9), (9, 10)], 9000: [(13, 12), (12, 9), (9, 10)]}


def cistercian(n, scale=1):
    """The Cistercian numeral for n (1..9999) as an RGBA picture: black strokes on a transparent background."""
    im = Image.new("RGBA", (120 * scale, 180 * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    segs = [(1, 13)]
    for i, ch in enumerate(reversed(str(n))):
        segs += _G.get(int(ch) * 10 ** i, [])
    w = 2 * scale
    for a, b in segs:
        (x1, y1), (x2, y2) = [(_P[k][0] * 2 * scale, _P[k][1] * 2 * scale) for k in (a, b)]
        if x1 == x2 or y1 == y2:
            d.rectangle([min(x1, x2) - w, min(y1, y2) - w, max(x1, x2) + w - 1, max(y1, y2) + w - 1], fill=(0, 0, 0, 255))
        else:
            dx, dy = x2 - x1, y2 - y1
            ln = math.hypot(dx, dy)
            ux, uy = dx / ln, dy / ln
            nx, ny = -uy, ux
            ax, ay, bx, by = x1 - ux * w, y1 - uy * w, x2 + ux * w, y2 + uy * w
            d.polygon([(ax + nx * w, ay + ny * w), (bx + nx * w, by + ny * w), (bx - nx * w, by - ny * w),
                       (ax - nx * w, ay - ny * w)], fill=(0, 0, 0, 255))
    return im


def glyph_pack(folder, numbers, pattern="cistercian_{number}.png"):
    os.makedirs(folder, exist_ok=True)
    for n in numbers:
        cistercian(n).save(os.path.join(folder, bf_folio.pattern_name(pattern, n)), compress_level=1)
    return folder


def digit_pack(folder, skip=(), bad=()):
    """Digit pictures 0-9, each a different width (30 + 2 x digit pixels) so the PDF shows which was drawn; the
    1 is shorter (50 px, the others 60) to check that all digits share one scale and stand on one line."""
    os.makedirs(folder, exist_ok=True)
    for d in range(10):
        name = os.path.join(folder, f"{d}.png")
        if d in skip:
            continue
        if d in bad:
            with open(name, "wb") as f:
                f.write(b"this is not a picture")
            continue
        h = 50 if d == 1 else 60
        im = Image.new("RGBA", (30 + 2 * d, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([3, 3, 26 + 2 * d, h - 4], fill=(20, 20, 120, 255))
        im.save(name)
    return folder


GLYPHS = glyph_pack(os.path.join(TMP, "cistercian"), range(1, 401))
DIGITS = digit_pack(os.path.join(TMP, "digits"))


# ---------------------------------------------------------------------------------------------- books
def settings(**kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP), source_mode="paste", page_size=DIGEST,
             toc=True, title_page=True, fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False,
             fmt_docx=False, fmt_html=False, fmt_txt=False, imp_files="Aggregated file only", pn_style="Plain",
             pn_digits_dir=DIGITS, pn_glyphs_dir=GLYPHS, pn_glyph_pattern="cistercian_{number}.png")
    s.update(kw)
    return s


def book(n=6, words=120):
    return Book(title="Numbers Test", author="A. Writer",
                chapters=[Chapter(f"Zt{i:03d}", blocks=[Block("para", text=f"Text of chapter {i}. " * words)])
                          for i in range(1, n + 1)])


def make(b, s, name):
    b = apply_info(copy.deepcopy(b), dict(s))
    path = os.path.join(TMP, name + ".pdf")
    logs = []
    build_pdf(b, dict(s), path, log=logs.append)
    return path, b, logs


def geo(s):
    pw, ph = page_size_inches(s)
    W, H = pw * 72, ph * 72
    mt, mb, mi, mo = (float(s[k]) * 72 for k in ("margin_top", "margin_bottom", "margin_inner", "margin_outer"))
    return W, H, mt, mb, mi, mo, W - mi - mo, H - mt - mb


def furniture(path, s):
    """Per page (index 0 = page 1): what is printed outside the text area: {"text", "box" (x0, top, x1, bottom)
    or None, "images": [pdfplumber images]} (the page number; nothing else is outside it in these books)."""
    W, H, mt, mb, mi, mo, fw, fh = geo(s)
    out = []
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages, 1):
            fx0 = mi if i % 2 else mo

            def outside(o, fx0=fx0):
                return (o["bottom"] <= mt + 0.5 or o["top"] >= H - mb - 0.5 or o["x1"] <= fx0 + 0.5 or
                        o["x0"] >= fx0 + fw - 0.5)
            cs = sorted([c for c in pg.chars if outside(c) and c["text"].strip()], key=lambda c: c["x0"])
            ims = sorted([im for im in pg.images if outside(im)], key=lambda m: m["x0"])
            objs = cs + ims
            box = (min(o["x0"] for o in objs), min(o["top"] for o in objs), max(o["x1"] for o in objs),
                   max(o["bottom"] for o in objs)) if objs else None
            out.append({"text": "".join(c["text"] for c in cs), "box": box, "images": ims, "chars": cs})
    return out


def numbered(path, s):
    return {i + 1: f["text"] for i, f in enumerate(furniture(path, s)) if f["text"] or f["images"]}


def chars(path):
    with pdfplumber.open(path) as pdf:
        return [[(c["text"], round(c["x0"], 2), round(c["top"], 2), c["fontname"].split("+")[-1], round(c["size"], 2))
                 for c in pg.chars] + [("IMG", round(m["x0"], 2), round(m["top"], 2), round(m["x1"], 2),
                                        round(m["bottom"], 2)) for m in pg.images] for pg in pdf.pages]


def renders(path, scale=0.3):
    doc = pdfium.PdfDocument(path)
    out = [doc[i].render(scale=scale).to_pil().tobytes() for i in range(len(doc))]
    doc.close()
    return out


def glyph_on_page(path, page_no, box, n):
    """How well the picture drawn at box on the rendered page matches the Cistercian numeral n (and the best
    other number nearby): (IoU with n, best IoU with another number)."""
    doc = pdfium.PdfDocument(path)
    k = 8
    im = doc[page_no - 1].render(scale=k).to_pil().convert("L")
    doc.close()
    x0, top, x1, bottom = box
    crop = im.crop((int(x0 * k), int(top * k), int(math.ceil(x1 * k)), int(math.ceil(bottom * k))))
    mine = crop.point(lambda v: 255 if v < 128 else 0)

    def iou(m):
        exp = cistercian(m).getchannel("A").resize(crop.size).point(lambda v: 255 if v > 127 else 0)
        a, b = mine.tobytes(), exp.tobytes()
        inter = sum(1 for p, q in zip(a, b) if p and q)
        uni = sum(1 for p, q in zip(a, b) if p or q)
        return inter / max(1, uni)
    others = [m for m in {n - 1, n + 1, n + 10, n - 10, n + 100} if 1 <= m <= 9999 and m != n]
    return iou(n), max(iou(m) for m in others)


# ============================================================================ 1. numerals
R = bf_folio.roman_numeral
known = {1: "i", 4: "iv", 9: "ix", 14: "xiv", 40: "xl", 44: "xliv", 49: "xlix", 90: "xc", 99: "xcix", 400: "cd",
         444: "cdxliv", 900: "cm", 1994: "mcmxciv", 2026: "mmxxvi", 3888: "mmmdccclxxxviii", 3999: "mmmcmxcix"}
check(all(R(n) == r and R(n, True) == r.upper() for n, r in known.items()),
      "Roman numerals use the usual subtractive forms (IV, IX, XL, XC, CD, CM)")


def unroman(r):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    t = 0
    for a, b in zip(r, r[1:] + " "):
        t += -v[a] if b != " " and v[a] < v[b] else v[a]
    return t


allr = [R(n, True) for n in range(1, 4000)]
check(all(unroman(r) == n for n, r in enumerate(allr, 1)) and len(set(allr)) == 3999 and
      not any(re.search(r"IIII|XXXX|CCCC|VV|LL|DD|IL|IC|ID|IM|VX|XD|XM", r) for r in allr),
      "every number 1-3999 has one correct, conventional Roman numeral")
check(R(0) is None and R(-3) is None and R(4000) is None and R(True) is None and R(2.5) is None,
      "0, negative numbers, 4000 and up have no Roman numeral (handled explicitly)")
f4000 = bf_folio.Folio({"pn_numerals": bf_folio.ROMAN_UPPER})
check(f4000.text(3999) == "MMMCMXCIX" and f4000.text(4000) == "4000" and f4000.text(4001) == "4001" and
      "go up to 3999" in " ".join(f4000.report()) and "4000" in " ".join(f4000.report()),
      "beyond 3999: printed as 1, 2, 3 and said in the notes")
check(bf_folio.numerals({}) == bf_folio.ARABIC and bf_folio.numerals({"pn_numerals": "Klingon"}) == bf_folio.ARABIC
      and DEFAULTS["pn_numerals"] == bf_folio.ARABIC and DEFAULTS["pn_position"] == "Bottom center",
      "the standard is Arabic numerals, bottom centre (unknown values = the standard)")
check(bf_folio.pattern_problem("{number}.png") is None and bf_folio.pattern_problem("c_{number:4}.jpg") is None and
      all(bf_folio.pattern_problem(p) for p in ("", "number.png", "{number}{number}.png", "{number}", "a/{number}.png",
                                                "{num}.png", "{number:9}.png", "{number}.txt", "{x}{number}.png")),
      "file-name patterns are checked ({number} once, zero-padding 1-6, a picture file type, no folders)")
check(bf_folio.pattern_name("{number:4}.png", 12) == "0012.png" and bf_folio.pattern_name("{number}.png", 128) ==
      "128.png" and bf_folio.pattern_name("cistercian_{number}.png", 7) == "cistercian_7.png" and
      bf_folio.pattern_name("{number:3}.png", 1234) == "1234.png", "pattern -> file names (with zero-padding)")
pad = os.path.join(TMP, "padded")
os.makedirs(pad)
for n in (1, 2, 30, 128, 999):
    open(os.path.join(pad, f"{n:04d}.png"), "wb").close()
check(bf_folio.detect_pattern(GLYPHS) == "cistercian_{number}.png" and bf_folio.detect_pattern(pad) ==
      "{number:4}.png" and bf_folio.detect_pattern(DIGITS) == "{number}.png" and
      bf_folio.pack_numbers(pad, "{number:4}.png") == {1, 2, 30, 128, 999} and
      bf_folio.pack_numbers(GLYPHS, "cistercian_{number}.png") == set(range(1, 401)) and
      bf_folio.describe_numbers(set(range(1, 401))).startswith("1–400 (400 pictures)") and
      "first missing number is 3" in bf_folio.describe_numbers({1, 2, 30}),
      "the file-name pattern is worked out from the files, and the numbers a folder has (by name only)")

# ============================================================================ 2. the standard
b6 = book(6)
S0 = settings()
p_std, _b, _l = make(b6, S0, "std")
old = {k: v for k, v in S0.items() if not k.startswith("pn_") or k in ("pn_position", "pn_style", "pn_mode",
                                                                         "pn_hide_openers", "pn_hide_blank",
                                                                         "pn_hide_title")}
p_old, _b, _l = make(b6, old, "old")
check(chars(p_std) == chars(p_old), "settings from before 1.8.1 (no numerals setting): exactly the same pages")
nums = numbered(p_std, S0)
W, H, MT, MB, MI, MO, FW, FH = geo(S0)
fur = furniture(p_std, S0)
check(nums and all(t == str(p) for p, t in nums.items()) and
      all(abs((f["box"][0] + f["box"][2]) / 2 - ((MI if i % 2 == 0 else MO) + FW / 2)) < 0.6 and f["box"][1] > H - MB
          for i, f in enumerate(fur) if f["box"]),
      f"the standard: 1, 2, 3 at the bottom centre of every numbered page ({len(nums)} pages)")
s_rule = settings(pn_style="Rule above")
p_rule, _b, _l = make(b6, s_rule, "rule")
p_rule_old, _b, _l = make(b6, {k: v for k, v in s_rule.items() if k in old}, "rule_old")
check(chars(p_rule) == chars(p_rule_old), "the standard look (Rule above) is unchanged as well")

# ============================================================================ 3. Roman
b40 = book(40, words=60)
s_up = settings(pn_numerals=bf_folio.ROMAN_UPPER)
p_up, _b, logs_up = make(b40, s_up, "roman_upper")
n_up = numbered(p_up, s_up)
s_lo = settings(pn_numerals=bf_folio.ROMAN_LOWER)
p_lo, _b, _l = make(b40, s_lo, "roman_lower")
n_lo = numbered(p_lo, s_lo)
check(n_up and all(t == R(p, True) for p, t in n_up.items()) and n_lo.keys() == n_up.keys() and
      all(t == R(p) for p, t in n_lo.items()) and {"IV", "IX", "XIV", "XL"} <= set(n_up.values()),
      f"Roman numerals on the pages (upper: {', '.join(list(n_up.values())[:5])}...; lower; IV, IX, XIV, XL appear)")
with pdfplumber.open(p_up) as pdf:
    toc_txt = pdf.pages[1].extract_text()
check(re.search(r"Zt001\s+[IVXLC]+\s*$", toc_txt, re.M) and not re.search(r"Zt0\d\d\s+\d+\s*$", toc_txt, re.M),
      "the contents page lists the pages in the same Roman numerals")
s_fm = settings(pn_numerals=bf_folio.ROMAN_UPPER, pn_mode="Roman front matter, 1 on first chapter")
p_fm, _b, _l = make(book(6), s_fm, "roman_fm")
n_fm = numbered(p_fm, s_fm)
front = [t for p, t in sorted(n_fm.items()) if t == t.lower()]
body = [t for p, t in sorted(n_fm.items()) if t != t.lower()]
check(front and all(re.fullmatch(r"[ivx]+", t) for t in front) and body and body[0] == "I" and
      all(R(i + 1, True) == t for i, t in enumerate(body)),
      f"Roman front matter keeps i, ii, iii ({front}); the chosen numerals start at I on chapter 1")
p_fm_ar, _b, _l = make(book(6), settings(pn_mode="Roman front matter, 1 on first chapter"), "fm_arabic")
check(numbered(p_fm_ar, settings()).keys() == n_fm.keys(), "the same pages are numbered as with Arabic numerals")

# ============================================================================ 4. digit pictures
b130 = book(70, words=70)
s_dg = settings(pn_numerals=bf_folio.DIGIT_IMAGES, pn_img_gap=1.5)
p_dg, _b, logs_dg = make(b130, s_dg, "digits")
fd = furniture(p_dg, s_dg)
p_ar, _b, _l = make(b130, settings(), "digits_arabic")
fa = furniture(p_ar, settings())
ok_digits, why = True, ""
for i, (f, a) in enumerate(zip(fd, fa), 1):
    if not a["text"]:
        if f["images"] or f["text"]:
            ok_digits, why = False, f"page {i} numbered with pictures only"
        continue
    ims = f["images"]
    got = "".join(str((m["srcsize"][0] - 30) // 2) for m in ims)
    bottoms = {round(m["bottom"], 2) for m in ims}
    scales = {round(m["height"] / m["srcsize"][1], 4) for m in ims}
    gaps = [round(b2["x0"] - b1["x1"], 2) for b1, b2 in zip(ims, ims[1:])]
    asp = all(abs(m["width"] / m["height"] - m["srcsize"][0] / m["srcsize"][1]) < 0.01 for m in ims)
    if got != str(i) or len(bottoms) != 1 or len(scales) != 1 or any(abs(g - 1.5) > 0.02 for g in gaps) or not asp:
        ok_digits, why = False, f"page {i}: {got} bottoms {bottoms} scales {scales} gaps {gaps}"
        break
check(ok_digits and len(fd) >= 128, f"digit pictures: every page's number is its digits' pictures in order (128 = "
                                    f"1, 2, 8), one scale, bottoms lined up, 1.5 pt apart, shapes kept {why}")
p128 = fd[127]["images"]
check([(m["srcsize"][0] - 30) // 2 for m in p128] == [1, 2, 8] and p128[0]["height"] < p128[1]["height"],
      "page 128: the pictures of 1, 2 and 8 (the shorter 1 keeps its size next to the others)")
with pdfplumber.open(p_dg) as pdf:
    smask = all("SMask" in m["stream"].attrs for m in pdf.pages[127].images)
check(smask, "transparent PNGs keep their transparency in the PDF")
check(not [m for m in logs_dg if m.startswith("WARNING")], "no warnings when the pictures are fine")
s_dgh = settings(pn_numerals=bf_folio.DIGIT_IMAGES, pn_img_height=14.0, pn_img_gap=0)
p_dgh, _b, _l = make(book(6), s_dgh, "digits_h14")
fh_ = furniture(p_dgh, s_dgh)
check(any(f["images"] for f in fh_) and
      all(abs(m["height"] / m["srcsize"][1] - 14.0 / 60) < 0.0005 for f in fh_ for m in f["images"]) and
      all(abs(b2["x0"] - b1["x1"]) < 0.01 for f in fh_ for b1, b2 in zip(f["images"], f["images"][1:])),
      "picture height and spacing as set (the tallest digit 14 pt, 0 pt apart)")
# problems with the pictures
miss = digit_pack(os.path.join(TMP, "digits_missing"), skip=(7,))
broken = digit_pack(os.path.join(TMP, "digits_broken"), bad=(3,))
_i, prob_m = bf_folio.check_digits(miss)
_i, prob_b = bf_folio.check_digits(broken)
_i, prob_n = bf_folio.check_digits(os.path.join(TMP, "no such folder"))
huge = digit_pack(os.path.join(TMP, "digits_huge"))
Image.new("RGBA", (5000, 60)).save(os.path.join(huge, "4.png"))
_i, prob_h = bf_folio.check_digits(huge)
check(prob_m and "7" in prob_m[0] and prob_b and "3.png" in prob_b[0] and prob_n and "isn't there" in prob_n[0] and
      prob_h and "too big" in prob_h[0] and bf_folio.check_digits(DIGITS)[1] == [],
      f"digit folders are checked: a missing digit, a damaged file, no folder, a huge picture ({prob_b[0][:60]}...)")
s_bad = settings(pn_numerals=bf_folio.DIGIT_IMAGES, pn_digits_dir=broken)
p_bad, bk_bad, logs_bad = make(book(6), s_bad, "digits_bad")
check(numbered(p_bad, s_bad) == numbered(p_std, S0) and not any(f["images"] for f in furniture(p_bad, s_bad)) and
      any("3.png" in m and "Arabic" in m for m in logs_bad if m.startswith("WARNING")),
      "unusable digit pictures: the book is still made, numbered 1, 2, 3, with a warning that says why")
b_cp = book(6)
b_cp.pn_digits = bf_folio.digit_copies(DIGITS)
s_gone = settings(pn_numerals=bf_folio.DIGIT_IMAGES, pn_digits_dir=os.path.join(TMP, "moved away"))
p_cp, _b, logs_cp = make(b_cp, s_gone, "digits_copies")
check(len(b_cp.pn_digits) == 10 and any(f["images"] for f in furniture(p_cp, s_gone)) and
      chars(p_cp) == chars(make(book(6), settings(pn_numerals=bf_folio.DIGIT_IMAGES), "digits_6")[0]) and
      any("copies saved in the project" in m for m in logs_cp),
      "folder gone, copies kept in the project: the same pictures, and the log says so")

# ============================================================================ 5. whole-number pictures
s_gl = settings(pn_numerals=bf_folio.WHOLE_IMAGES)
loaded = []
_real_load = bf_folio.load_picture


def counting_load(src, name):
    loaded.append(name)
    return _real_load(src, name)


bf_folio.load_picture = counting_load
p_gl, _b, logs_gl = make(b130, s_gl, "glyphs")
bf_folio.load_picture = _real_load
fg = furniture(p_gl, s_gl)
n_pages = len(fg)
one_each = all(len(f["images"]) == 1 and not f["text"] for f, a in zip(fg, fa) if a["text"]) and \
    all(not f["images"] for f, a in zip(fg, fa) if not a["text"])
need = {f"cistercian_{p}.png" for p, a in enumerate(fa, 1) if a["text"]}
check(one_each and len(set(loaded)) == len(loaded) and need <= set(loaded) and
      set(loaded) <= {f"cistercian_{p}.png" for p in range(1, n_pages + 1)} and
      not [m for m in logs_gl if m.startswith("WARNING")],
      f"whole-number pictures: one glyph on each numbered page; only those {len(set(loaded))} of the 400 pictures "
      "were read, each once")
glyph_ok = []
for pno in (3, 19, 45, 99, 128):
    if pno <= n_pages and fg[pno - 1]["images"]:
        m = fg[pno - 1]["images"][0]
        mine, other = glyph_on_page(p_gl, pno, (m["x0"], m["top"], m["x1"], m["bottom"]), pno)
        glyph_ok.append((pno, round(mine, 2), round(other, 2)))
check(len(glyph_ok) == 5 and all(a >= 0.95 and a >= b + 0.05 for _p, a, b in glyph_ok),
      f"the rendered pages show the right Cistercian numeral (page, match, best other number): {glyph_ok}")
m = fg[127]["images"][0]
check(abs(m["width"] / m["height"] - 120 / 180) < 0.01 and abs(m["height"] - max(9.0, 13 * 0.8) * 2) < 0.01,
      "glyphs keep their shape; automatic height = twice the number text size")
# missing, damaged, zero, folder problems
part = glyph_pack(os.path.join(TMP, "glyphs_partial"), [n for n in range(0, 61) if n not in (5, 17)])
cistercian(1).save(os.path.join(part, "cistercian_0.png"))           # a "0" picture must never be used
with open(os.path.join(part, "cistercian_23.png"), "wb") as f:
    f.write(b"\x89PNG broken")
s_part = settings(pn_numerals=bf_folio.WHOLE_IMAGES, pn_glyphs_dir=part)
loaded.clear()
bf_folio.load_picture = counting_load
p_part, bk_part, logs_part = make(book(20, words=60), s_part, "glyphs_partial")
bf_folio.load_picture = _real_load
fp = furniture(p_part, s_part)
text_pages = {i for i, f in enumerate(fp, 1) if f["text"]}
warn = " ".join(m for m in logs_part if m.startswith("WARNING"))
check({5, 17, 23} <= text_pages and all(fp[p - 1]["text"] == str(p) for p in (5, 17, 23)) and
      all(fp[p - 1]["images"] for p in range(1, 61) if p <= len(fp) and p not in text_pages and
          numbered(p_ar, settings()).get(p)) and "cistercian_0.png" not in loaded and
      "5, 17, 23" in warn and "Arabic" in warn,
      f"missing (5, 17) and damaged (23) pictures: those pages get 1, 2, 3 and the warning names them; 0 is "
      f"never looked up ({sorted(text_pages)[:6]})")
f0 = bf_folio.Folio(s_part)
check(f0.parts(0) is None and f0.parts(10000) is None and f0.parts(-1) is None,
      "no picture for 0, negative numbers or numbers past 9999 (handled explicitly)")
for label, kw in (("no folder", dict(pn_glyphs_dir=os.path.join(TMP, "gone"))),
                  ("bad pattern", dict(pn_glyph_pattern="number.png")),
                  ("empty folder setting", dict(pn_glyphs_dir=""))):
    sx = settings(pn_numerals=bf_folio.WHOLE_IMAGES, **kw)
    px, bx, lx = make(book(4), sx, "glyph_" + label.replace(" ", "_"))
    check(numbered(px, sx) == numbered(make(book(4), settings(), "ar4")[0], settings()) and
          any("Arabic" in m for m in lx if m.startswith("WARNING")),
          f"{label}: numbered 1, 2, 3 instead, with a warning")
res_w = build_preview(apply_info(copy.deepcopy(book(20, 60)), dict(s_part)), dict(s_part), log=lambda m: None)
folder_w, made_w, notes_w = run_build(apply_info(copy.deepcopy(book(20, 60)), dict(s_part)), dict(s_part),
                                      log=lambda m: None)
readme = open(os.path.join(folder_w, "READ ME - printing notes.txt"), encoding="utf-8").read()
check(any("5, 17, 23" in n for n in res_w["folio_notes"]) and "5, 17, 23" in readme,
      "the preview and the printing notes have the warning too")

# contents page: the same pictures; a number typed in Edit contents stays as typed (only a label)
b_t = book(8, 60)
s_t = settings(pn_numerals=bf_folio.DIGIT_IMAGES)
auto = contents_entries(apply_info(copy.deepcopy(b_t), dict(s_t)), s_t)
rows = contents_rows(auto, [])
rows[2]["page"] = "99"
b_t.toc = rows_to_edits(rows, auto)
p_t, _b, _l = make(b_t, s_t, "typed_digits")
W, H, MT, MB, MI, MO, FW, FH = geo(s_t)
with pdfplumber.open(p_t) as pdf:
    cp = pdf.pages[1]
    col = [m for m in cp.images if m["top"] < H - MB and m["x1"] > MO + FW - 0.45 * 72 - 1]
    entries = [w for w in cp.extract_words() if w["text"].startswith("Zt")]
    typed = [w for w in cp.extract_words() if w["text"] == "99"]
check(len(entries) == 8 and typed and len({round(m["bottom"]) for m in col}) == 7 and
      abs(typed[0]["x1"] - (MO + FW)) < 0.6,
      "contents page: the entries' page numbers are the same digit pictures, right-aligned; the number typed in "
      "Edit contents (99) is printed as typed text")

# ============================================================================ 6. positions
EXPECT = {"Bottom center": "c", "Bottom left": "l", "Bottom right": "r", "Bottom outside": "o", "Top center": "c",
          "Top left": "l", "Top right": "r", "Top outside": "o", "Middle outside edge": "m"}


def placed_ok(f, page, s, pictures):
    W, H, mt, mb, mi, mo, fw, fh = geo(s)
    if not f["box"]:
        return False
    x0, top, x1, bottom = f["box"]
    odd = page % 2 == 1
    fx0 = mi if odd else mo
    fx1 = fx0 + fw
    pos = s["pn_position"]
    kind = EXPECT[pos]
    tol = 0.6
    if kind == "m":
        cx, cy = (x0 + x1) / 2, (top + bottom) / 2
        want = W - mo / 2 if odd else mo / 2
        inside = (x1 <= fx0 - 1 or x0 >= fx1 + 1) and x0 >= 0 and x1 <= W
        return abs(cx - want) < tol and abs(cy - (mt + fh / 2)) < 6 and inside
    if pos.startswith("Top"):
        if not (bottom <= mt - 1 and top >= 0):
            return False
    elif not (top >= H - mb + 1 and bottom <= H):
        return False
    if kind == "c":
        return abs((x0 + x1) / 2 - (fx0 + fx1) / 2) < tol
    if kind == "l":
        return abs(x0 - fx0) < tol
    if kind == "r":
        return abs(x1 - fx1) < tol
    return abs(x1 - (W - mo)) < tol if odd else abs(x0 - mo) < tol      # outside: as in every earlier version


pos_ok = []
for pos in EXPECT:
    for mode in (bf_folio.ARABIC, bf_folio.WHOLE_IMAGES, bf_folio.DIGIT_IMAGES):
        sp = settings(pn_position=pos, pn_numerals=mode, page_size=DIGEST)
        pp, _b, lp = make(book(5, 80), sp, f"pos_{pos}_{mode[:6]}".replace(" ", "_"))
        fps = furniture(pp, sp)
        pages_ = [i for i, f in enumerate(fps, 1) if f["box"]]
        good = [placed_ok(fps[i - 1], i, sp, mode != bf_folio.ARABIC) for i in pages_]
        pos_ok.append((pos, mode[:6], len(pages_), all(good) and len(pages_) >= 8 and
                       {i % 2 for i in pages_} == {0, 1} and not [m for m in lp if m.startswith("WARNING")]))
bad = [p for p in pos_ok if not p[3]]
check(not bad, f"all 9 positions, as text, digit pictures and whole-number pictures, on left- and right-hand pages, "
               f"in the margins where they belong ({len(pos_ok)} books) {bad}")
sm = settings(pn_position="Middle outside edge", blank_pages_start=1)
pm, _b, _l = make(book(5, 80), sm, "middle_blank1")
side = [(i, "R" if (f["box"][0] + f["box"][2]) / 2 > geo(sm)[0] / 2 else "L")
        for i, f in enumerate(furniture(pm, sm), 1) if f["box"]]
check(side and all(s_ == ("R" if i % 2 else "L") for i, s_ in side),
      "Middle outside edge: right on right-hand (odd) pages, left on left-hand pages - also after a blank page "
      "added before the book (the page's place in the book decides)")
sw = settings(pn_position="Middle outside edge", margin_outer=0.2, pn_style="Dashes", body_size=18)
pw_, _b, lw = make(book(3, 40), sw, "middle_narrow")
check(any("wider than the outside margin" in m for m in lw), "a number wider than the outside margin is pointed out")
sg = settings(pn_numerals=bf_folio.WHOLE_IMAGES, pn_img_height=60.0, margin_bottom=0.5)
pg_, _b, lg = make(book(3, 40), sg, "glyph_too_tall")
W, H, MT, MB, MI, MO, FW, FH = geo(sg)
check(all(f["box"][1] >= H - MB for f in furniture(pg_, sg) if f["box"]) and any("smaller" in m for m in lg),
      "pictures taller than the margin are made to fit inside it (and that is said)")

# ============================================================================ 7. pages without numbers
b_m = Book(title="Front", author="A", fic_summary=[Block("para", text="A summary. " * 40, label="Summary")],
           chapters=[Chapter("Book One", label="Part One", level=0)] +
                    [Chapter(f"Zt{i:03d}", blocks=[Block("para", text=f"Text of chapter {i}. " * 90)])
                     for i in range(1, 5)])
same_pages = []
for mode_pn in ("Every page (title page = 1)", "Start at 1 on first chapter", "Roman front matter, 1 on first chapter"):
    for extra in (dict(), dict(pn_hide_openers=True, pn_hide_title=True, chapter_start="Right-hand page",
                               blank_pages_start=2, blank_pages_end=3)):
        base_s = settings(pn_mode=mode_pn, **extra)
        ref = numbered(make(b_m, base_s, "unnum_ref")[0], base_s)
        for mode in (bf_folio.ROMAN_UPPER, bf_folio.DIGIT_IMAGES, bf_folio.WHOLE_IMAGES):
            sx = settings(pn_mode=mode_pn, pn_numerals=mode, **extra)
            same_pages.append(numbered(make(b_m, sx, "unnum")[0], sx).keys() == ref.keys())
check(all(same_pages) and len(same_pages) == 18, "the pages that have a number are the same with every numerals "
                                                 "choice (front matter, chapter openings, title page, blank pages "
                                                 "and the blank pages added before/after the book)")
sb = settings(pn_numerals=bf_folio.WHOLE_IMAGES, blank_pages_start=2, blank_pages_end=2)
pb, _b, _l = make(book(4, 80), sb, "blanks")
fb = furniture(pb, sb)
check(not fb[0]["box"] and not fb[1]["box"] and not fb[-1]["box"] and not fb[-2]["box"] and fb[2]["images"],
      "blank pages added before and after the book have no number; numbering starts after them")

# ============================================================================ 8. preview / print / imposed


def to_sheet(g, sw, sh, px, py):
    """A point of a source page (pt, origin bottom left) -> the sheet (pt, origin bottom left), as bf_impose
    places the page (centre, turn, scale, move)."""
    dx, dy = px - sw / 2, py - sh / 2
    a = math.radians(g.ang)
    rx, ry = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    return g.x + g.w / 2 + rx * g.sx, g.y + g.h / 2 + ry * g.sy


imp_ok = []
for layout in ("Folio - 2 pages per side", "Quarto - 4 pages per side", "Octavo - 8 pages per side"):
    for mode in (bf_folio.ARABIC, bf_folio.WHOLE_IMAGES):
        si = settings(fmt_impose=True, imp_layout=layout, pn_numerals=mode, pn_position="Middle outside edge",
                      blank_pages_start=1, sig_marks=False, chapter_start="Right-hand page")
        bb = book(9, 70)
        folder_i, made_i, _n = run_build(apply_info(copy.deepcopy(bb), dict(si)), dict(si), log=lambda m: None)
        prn = next(x for x in made_i if x.endswith("Print.pdf"))
        imp = next(x for x in made_i if "Imposed" in x)
        resp = build_preview(apply_info(copy.deepcopy(bb), dict(si)), dict(si), log=lambda m: None)
        same = chars(resp["pdf"]) == chars(prn) and renders(resp["sheets"][0]) == renders(imp)
        fsrc = furniture(prn, si)
        with pdfplumber.open(prn) as pdf:
            sizes = [(float(p.width), float(p.height)) for p in pdf.pages]
            src_counts = [sum(1 for c in p.chars if c["text"].strip()) + len(p.images) for p in pdf.pages]
        info, sides = bf_impose.plan_imposition(sizes, dict(si), log=lambda m: None)
        found = missing = extra = 0
        with pdfplumber.open(imp) as pdf:
            for sheet, sd in zip(pdf.pages, sides):
                SH = float(sheet.height)
                objs = [("t", c["text"], (c["x0"] + c["x1"]) / 2, SH - (c["top"] + c["bottom"]) / 2) for c in sheet.chars
                        if c["text"].strip()] + \
                       [("i", "", (m["x0"] + m["x1"]) / 2, SH - (m["top"] + m["bottom"]) / 2) for m in sheet.images]
                used = set()
                for idx, g in sd.get("places", []):
                    f = fsrc[idx]
                    sw, sh = sizes[idx]
                    for o in f["chars"] + f["images"]:
                        kind = "t" if "text" in o else "i"
                        X, Y = to_sheet(g, sw, sh, (o["x0"] + o["x1"]) / 2, sh - (o["top"] + o["bottom"]) / 2)
                        hit = [k for k, ob in enumerate(objs) if ob[0] == kind and k not in used and
                               abs(ob[2] - X) < 1.5 and abs(ob[3] - Y) < 1.5 and (kind == "i" or ob[1] == o["text"])]
                        if hit:
                            used.add(hit[0])
                            found += 1
                        else:
                            missing += 1
                # every page's space holds exactly what the page holds (no second number), and nothing is
                # printed in a blank (padding) space
                cells = [(g.x, g.y, g.w, g.h) for _i, g in sd.get("places", [])]
                for (idx, g), (x, y, w, h) in zip(sd.get("places", []), cells):
                    inside = sum(1 for ob in objs if x <= ob[2] <= x + w and y <= ob[3] <= y + h)
                    if inside != src_counts[idx]:
                        extra += abs(inside - src_counts[idx])
                for k, ob in enumerate(objs):
                    if k in used:
                        continue
                    if not any(x <= ob[2] <= x + w and y <= ob[3] <= y + h for x, y, w, h in cells):
                        extra += 1
        n_src = sum(len(f["chars"]) + len(f["images"]) for f in fsrc)
        imp_ok.append((layout.split(" ")[0], mode[:6], same, found, n_src, missing, extra))
check(all(same and found == n_src and n_src > 0 and not missing and not extra for _l, _m, same, found, n_src, missing,
          extra in imp_ok),
      "preview = Print PDF = imposed sheets; on the folio, quarto and octavo sheets every page number (text or "
      f"picture) is exactly where its page puts it, none missing, none twice, nothing in padding spaces {imp_ok}")

# ============================================================================ 9. long books, near the limits
big = os.path.join(TMP, "cistercian_all")
glyph_pack(big, range(1, 10000), "{number:4}.png")
s_long = settings(pn_numerals=bf_folio.WHOLE_IMAGES, pn_glyphs_dir=big, pn_glyph_pattern="{number:4}.png", toc=False,
                  title_page=False, pn_position="Bottom outside")
b_long = Book(title="Long", author="A", chapters=[Chapter("Zt001", blocks=[Block("para", text=f"Words {k} of a "
                                                                                    "long book. " * 30)
                                                                              for k in range(1000)])])
loaded.clear()
bf_folio.load_picture = counting_load
t0 = time.time()
p_long, _b, logs_long = make(b_long, s_long, "long")
secs = time.time() - t0
bf_folio.load_picture = _real_load
fl = furniture(p_long, s_long)
check(len(fl) > 500 and all(len(f["images"]) == 1 for f in fl) and len(loaded) == len(set(loaded)) <= len(fl) and
      not [m for m in logs_long if m.startswith("WARNING")],
      f"a long book ({len(fl)} pages, {secs:.0f} s) with a 9,999-picture folder: one glyph per page, only "
      f"{len(set(loaded))} pictures read")
last = len(fl)
mm = fl[last - 1]["images"][0]
mine, other = glyph_on_page(p_long, last, (mm["x0"], mm["top"], mm["x1"], mm["bottom"]), last)
check(mine >= 0.95 and mine >= other + 0.05, f"its last page ({last}) shows the right glyph ({mine:.2f} vs {other:.2f})")
# numbers near the limits, drawn by the same code on a page of their own
from reportlab.pdfgen import canvas as rl_canvas                      # noqa: E402
lim = os.path.join(TMP, "limits.pdf")
cv = rl_canvas.Canvas(lim, pagesize=(300, 300))
fol = bf_folio.Folio(dict(pn_numerals=bf_folio.WHOLE_IMAGES, pn_glyphs_dir=big, pn_glyph_pattern="{number:4}.png"))
drawn = []
for n in (2999, 3000, 3001, 3999, 9998, 9999, 10000):
    pts = fol.parts(n)
    drawn.append((n, bool(pts)))
    if pts:
        fol.draw(cv, pts, 150, 100, 60, "center")
    cv.showPage()
cv.save()
with pdfplumber.open(lim) as pdf:
    boxes = [(pg.images[0]["x0"], pg.images[0]["top"], pg.images[0]["x1"], pg.images[0]["bottom"]) if pg.images
             else None for pg in pdf.pages]
lim_ok = [(n, round(glyph_on_page(lim, i + 1, boxes[i], n)[0], 2)) for i, (n, d) in enumerate(drawn) if d]
check(dict(drawn) == {2999: True, 3000: True, 3001: True, 3999: True, 9998: True, 9999: True, 10000: False} and
      all(v >= 0.95 for _n, v in lim_ok) and "10000" in " ".join(fol.report()) and "9999" in " ".join(fol.report()),
      f"3000, 3999 and 9999 are drawn with the right glyphs {lim_ok}; 10000 has none (said, printed as text)")
fr = bf_folio.Folio({"pn_numerals": bf_folio.ROMAN_LOWER})
check(fr.text(3000) == "mmm" and fr.text(3999) == "mmmcmxcix" and fr.text(4000) == "4000",
      "Roman numerals near the limit (3000 = mmm, 3999 = mmmcmxcix, 4000 -> 4000)")

# ============================================================================ 10. projects, Word
proj = os.path.join(TMP, "proj", "numbers.bookforge")
os.makedirs(os.path.dirname(proj))
pack_near = glyph_pack(os.path.join(TMP, "proj", "my glyphs"), range(1, 60))
digits_near = digit_pack(os.path.join(TMP, "proj", "my digits"))
s10 = settings(pn_numerals=bf_folio.WHOLE_IMAGES, pn_glyphs_dir=pack_near, pn_digits_dir=digits_near,
               pn_position="Top right", pn_img_height=18.0, pn_img_gap=2.0)
b10 = book(6)
b10.pn_digits = bf_folio.digit_copies(digits_near)
bf_edit.save_project(proj, b10, s10, "1.8.1")
b10r, s10r = bf_edit.load_project(proj)
p10, _b, _l = make(b10, s10, "proj_a")
p10r, _b, _l = make(b10r, s10r, "proj_b")
check(all(s10r[k] == s10[k] for k in ("pn_numerals", "pn_glyphs_dir", "pn_digits_dir", "pn_glyph_pattern",
                                      "pn_position", "pn_img_height", "pn_img_gap")) and
      chars(p10) == chars(p10r) and len(b10r.pn_digits) == 10, "saved in a project and the same after reopening")
moved = os.path.join(TMP, "moved")
shutil.move(os.path.dirname(proj), moved)            # the project folder moved, with its picture folders
b10m, s10m = bf_edit.load_project(os.path.join(moved, "numbers.bookforge"))
p10m, _b, l10m = make(b10m, s10m, "proj_moved")
check(s10m["pn_glyphs_dir"] == os.path.join(moved, "my glyphs") and s10m["pn_digits_dir"] ==
      os.path.join(moved, "my digits") and chars(p10m) == chars(p10) and "pn_glyphs_dir_rel" not in s10m,
      "a project moved together with its picture folders finds them in the new place")
shutil.rmtree(os.path.join(moved, "my glyphs"))
b10x, s10x = bf_edit.load_project(os.path.join(moved, "numbers.bookforge"))
p10x, _b, l10x = make(b10x, s10x, "proj_gone")
check(any("isn't there" in m and "Arabic" in m for m in l10x) and not any(f["images"] for f in furniture(p10x, s10x)),
      "a picture folder that isn't there any more: said clearly, numbered 1, 2, 3")
old_proj = os.path.join(TMP, "old.bookforge")
bf_edit.save_project(old_proj, book(4), {k: v for k, v in settings().items() if not k.startswith("pn_") or k in old},
                     "1.8.0")
b_o, s_o = bf_edit.load_project(old_proj)
check("pn_numerals" not in s_o and b_o.pn_digits == {} and
      chars(make(b_o, dict(settings(), **s_o), "oldproj")[0]) == chars(make(book(4), settings(), "oldproj_ref")[0]),
      "a project from before 1.8.1 opens with Arabic numerals and prints as before")


def docx_xml(s, name):
    sx = dict(s, fmt_docx=True, fmt_pdf=False, out_dir=tempfile.mkdtemp(dir=TMP))
    folder, made, notes = run_build(apply_info(copy.deepcopy(book(3, 30)), dict(sx)), dict(sx), log=lambda m: None)
    path = next(x for x in made if x.endswith(".docx"))
    with zipfile.ZipFile(path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        foot = " ".join(z.read(n).decode("utf-8") for n in z.namelist() if re.match(r"word/(footer|header)\d*\.xml", n))
    return doc, foot, notes


d_up, f_up, n_up_w = docx_xml(settings(pn_numerals=bf_folio.ROMAN_UPPER, pn_position="Bottom right"), "w1")
d_lo, f_lo, _n = docx_xml(settings(pn_numerals=bf_folio.ROMAN_LOWER, pn_position="Top left"), "w2")
d_ar, f_ar, n_ar = docx_xml(settings(), "w3")
d_pic, f_pic, n_pic = docx_xml(settings(pn_numerals=bf_folio.WHOLE_IMAGES, pn_position="Middle outside edge"), "w4")
sect = re.search(r"<w:sectPr.*?</w:sectPr>", d_up, re.S).group(0)
order = re.findall(r"<w:(pgSz|pgMar|pgNumType|cols|docGrid)\b", sect)
check('w:fmt="upperRoman"' in d_up and 'w:fmt="lowerRoman"' in d_lo and "pgNumType" not in d_ar and
      'w:val="right"' in f_up and 'w:val="left"' in f_lo and 'w:val="center"' in f_ar and
      order.index("pgNumType") > order.index("pgMar") and (("cols" not in order) or
                                                          order.index("pgNumType") < order.index("cols")),
      "Word: Roman numerals as Word's own page-number format, left / centre / right as chosen")
check(any("Word document" in n and "Arabic" in n and "halfway" in n for n in n_pic) and
      not any("Word document: its page" in n or "Word document: they" in n for n in n_ar),
      "Word: what it can't do (pictures, the middle of the edge) is said in the printing notes, only when chosen")

# ============================================================================ 11. window
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
        setattr(messagebox, k, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, title, message))
                                              or True))(k))
    PICK = []
    filedialog.askdirectory = lambda **kw: PICK.pop(0) if PICK else ""
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

    app.shelf.select(th.tab_index("lay"))
    pump(0.5)
    combos = []
    todo = [app.pages[th.tab_index("lay")]]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == "TCombobox" and str(w.cget("textvariable")) == str(app.var("pn_numerals")):
            combos.append(w)
    check(combos and list(combos[0].cget("values")) == bf_folio.NUMERALS and
          app.var("pn_numerals").get() == bf_folio.ARABIC and not app.pn_box.winfo_ismapped(),
          "Layout: the Numerals box (standard Arabic); no picture settings shown for it")
    app.var("pn_numerals").set(bf_folio.DIGIT_IMAGES)
    pump(0.5)
    app.update_number_pictures(force=True)
    pump(0.2)
    check(app.pn_box.winfo_ismapped() and all(w.winfo_ismapped() for w in app.pn_rows["digits"]) and
          not any(w.winfo_ismapped() for w in app.pn_rows["whole"]),
          "digit pictures chosen: the digit folder and spacing appear (not the whole-number ones)")
    app.var("pn_digits_dir").set("")
    PICK.append(miss)
    SAID.clear()
    app.choose_digit_folder()
    pump(0.2)
    check(app.var("pn_digits_dir").get() == "" and SAID and "7" in SAID[-1][2],
          "a folder with a digit missing is refused, saying which")
    PICK.append(DIGITS)
    app.choose_digit_folder()
    pump(0.3)
    check(app.var("pn_digits_dir").get() == DIGITS and "can be used" in str(app.pn_status.cget("text")) and
          app.pn_sample.image is not None, "a good folder is taken, with a sample of the composed numbers")
    app.var("pn_numerals").set(bf_folio.WHOLE_IMAGES)
    PICK.append(pad)
    app.choose_number_folder()
    pump(0.3)
    PICK.append(GLYPHS)
    app.choose_number_folder()
    pump(0.3)
    st = str(app.pn_status.cget("text"))
    check(app.var("pn_glyphs_dir").get() == GLYPHS and app.var("pn_glyph_pattern").get() == "cistercian_{number}.png"
          and "1–400" in st and "cistercian_128.png" in st and app.pn_sample.image is not None and
          all(w.winfo_ismapped() for w in app.pn_rows["whole"]),
          "whole-number folder: its file-name pattern is found, the numbers it covers and a sample glyph shown")
    app.var("pn_glyph_pattern").set("{number}.png")
    pump(0.6)
    check(str(app.pn_status.cget("text")).startswith("⚠"), "a pattern that matches no files is pointed out")
    app.var("pn_glyph_pattern").set("cistercian_{number}.png")
    app.var("pn_position").set("Middle outside edge")
    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + "Words of the chapter. " * 120 + "\n\n"
                                                  for i in range(1, 7)))
    app.scan(force=True)
    idle(60)
    app.preview_book()
    idle()
    pump(0.3)
    pw = getattr(app, "preview_win", None)
    res = pw.result if pw is not None and pw.alive() else None
    sr = app.collect()
    fprev = furniture(res["pdf"], sr) if res else []
    check(res and sum(1 for f in fprev if f["images"]) >= 5 and
          all(placed_ok(f, i, sr, True) for i, f in enumerate(fprev, 1) if f["box"]),
          "the preview window's book has the glyphs in the middle of the outside edge")
    proj_w = os.path.join(TMP, "window.bookforge")
    PICK.append(proj_w)
    idle()
    app.save_project_dialog()
    app.var("pn_numerals").set(bf_folio.ARABIC)
    PICK.append(proj_w)
    idle()
    app.open_project_dialog()
    pump(0.3)
    check(app.var("pn_numerals").get() == bf_folio.WHOLE_IMAGES and app.var("pn_glyphs_dir").get() == GLYPHS and
          app.var("pn_position").get() == "Middle outside edge", "the window: saved in the project and back on "
                                                                  "reopening")
    PICK.append(old_proj)
    idle()
    app.open_project_dialog()
    pump(0.3)
    check(app.var("pn_numerals").get() == bf_folio.ARABIC, "the window: an older project opens with Arabic numerals")
    # (1.8.0: at 1400 x 1000, switching light/dark on the Output tab kept two hint labels rewrapping each other
    # forever and the window froze; a freeze here ends the test with a stack dump instead of hanging)
    import faulthandler
    idle()
    app.geometry("1400x1000+0+0")
    pump(0.5)
    app.shelf.select(th.tab_index("out"))
    pump(0.5)
    faulthandler.dump_traceback_later(120, exit=True)
    app.toggle_dark()
    pump(1.5)
    app.toggle_dark()
    pump(1.5)
    faulthandler.cancel_dump_traceback_later()
    check(app.var("pn_numerals").get() == bf_folio.ARABIC,
          "switching light/dark twice at 1400 x 1000 on the Output tab doesn't freeze the window and keeps the settings")
    check(not errors, f"no window errors {errors[:1]}")
    idle()
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
