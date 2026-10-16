"""Preview regression tests (plain Python - run:  python tests/test_preview.py).

Uses a made-up book, so it needs no test files. Checks that the preview is typeset by the same code as
the final printing files (identical pages, fonts and printing sheets) and writes nothing to the output folder.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pdfplumber                                        # noqa: E402
from pypdf import PdfReader                              # noqa: E402
import bf_impose                                         # noqa: E402,F401
from bf_core import DEFAULTS, parse_text, apply_info     # noqa: E402
from bf_build import build_preview, run_build            # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


TEXT = "\n\n".join(
    [f"# Chapter {n}\n\nIt was a *quiet* morning in the **old** town, caf\u00e9 lights still on \u2014 "
     f"\u201cnaïve\u201d visitors everywhere. " + "The story went on. " * 60 + "\n\n* * *\n\n" +
     "Later that day the rain began. " * 40 for n in range(1, 4)])


def pages_text(p):
    with pdfplumber.open(p) as d:
        return [x.extract_text() or "" for x in d.pages]


def fonts(p):
    out = set()
    for pg in PdfReader(p).pages:
        for v in (pg.get("/Resources", {}).get("/Font", {}) or {}).values():
            out.add(str(v.get_object()["/BaseFont"]).split("+")[-1])
    return out


for font, extra in (("Times (built-in)", {}), ("EB Garamond", {"page_size": "Half Letter / Digest (5.5 x 8.5 in)"})):
    out_dir = tempfile.mkdtemp(prefix="bf_prev_out_")
    shutil.rmtree(out_dir)                                     # must not exist until Generate
    s = dict(DEFAULTS)
    s.update(source_mode="paste", title="Preview Test", author="Tester", font_family=font, drop_cap=True,
             running_heads=True, ornament=True, fmt_impose=True, fmt_cover=False, out_dir=out_dir, **extra)
    book = apply_info(parse_text(TEXT, s, is_md=True), dict(s))
    res = build_preview(book, dict(s), log=lambda m: None)
    check(not os.path.exists(out_dir), f"[{font}] preview wrote nothing to the output folder")
    check(os.path.dirname(res["pdf"]) == res["dir"] and res["dir"].startswith(tempfile.gettempdir()),
          f"[{font}] preview lives in a temporary folder")
    book2 = apply_info(parse_text(TEXT, s, is_md=True), dict(s))
    folder, made, notes = run_build(book2, dict(s), log=lambda m: None)
    final = [m for m in made if m.endswith("Print.pdf")][0]
    imposed = [m for m in made if m.endswith("Imposed for binding.pdf")][0]
    a, b = pages_text(res["pdf"]), pages_text(final)
    check(len(a) == len(b) == res["pages"] and a == b,
          f"[{font}] final Print PDF = preview, page for page ({len(b)} pages)")
    check(fonts(res["pdf"]) == fonts(final), f"[{font}] same fonts in preview and final {sorted(fonts(final))}")
    check([p.mediabox for p in PdfReader(res["pdf"]).pages] == [p.mediabox for p in PdfReader(final).pages],
          f"[{font}] same page sizes")
    c, d = pages_text(res["sheets"][0]), pages_text(imposed)
    check(len(c) == len(d) and c == d, f"[{font}] imposed PDF = printing-sheet preview ({len(d)} sides)")
    shutil.rmtree(res["dir"], ignore_errors=True)
    shutil.rmtree(out_dir, ignore_errors=True)

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
