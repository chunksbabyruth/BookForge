"""Checks for fixes made after the first 1.7.0 upload (plain Python - run: python tests/test_regressions_170.py).

1. "Continuous" chapters: a part with its own text followed by another part printed an empty page between them.
2. Scrolling while a dropdown list is open moved the settings page (and the dropdown) under the list.
Nothing needs the internet.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_170_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info          # noqa: E402
from bf_pdf import build_pdf                                          # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def para(n):
    return [Block("para", "Words in a line of text, set as an ordinary paragraph. " * 6) for _ in range(n)]


# ---------------------------------------------------------------- 1. no empty page between parts
def book():
    return Book(title="Parts", author="Test", chapters=[
        Chapter("Introduction", level=0, blocks=para(3)),            # a part with its own text
        Chapter("Part One", level=0),                                 # a part with no text
        Chapter("Chapter 1", blocks=para(4)),
        Chapter("Part Two", level=0, blocks=para(2)),                 # part with text, then a chapter
        Chapter("Chapter 2", blocks=para(4)),
        Chapter("Part Three", level=0),                               # empty part right after a chapter
        Chapter("Part Four", level=0, blocks=para(1)),                # two parts in a row
        Chapter("Chapter 3", blocks=para(3))])


for start in ("Continuous", "New page", "Right-hand page"):
    s = dict(DEFAULTS, source_mode="paste", chapter_start=start, toc=False)
    out = os.path.join(TMP, f"parts_{start[:4]}.pdf")
    build_pdf(apply_info(book(), s), s, out, log=lambda m: None)
    with pdfplumber.open(out) as pdf:
        empty = [i + 1 for i, p in enumerate(pdf.pages) if not p.chars]
        n = len(pdf.pages)
    if start == "Right-hand page":       # its blank backs are on purpose: never two empty pages in a row
        check(all(b + 1 not in empty for b in empty), f"{start}: blank backs only, never two in a row ({empty} of {n})")
    else:
        check(not empty, f"{start}: no empty pages between parts and chapters ({n} pages, empty: {empty})")

# ---------------------------------------------------------------- 2. no page scrolling under an open dropdown
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as e:                     # noqa: BLE001
    have_display = False
    print(f"SKIP  window checks (no display: {e})")

if have_display:
    import BookForge as BF
    app = BF.App()
    app._no_save = True
    app.geometry("1000x560")
    errors = []
    app.report_callback_exception = lambda *a: errors.append(a[1])

    def pump(sec=0.3):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    def first_combobox(w):
        for c in w.winfo_children():
            if c.winfo_class() == "TCombobox":
                return c
            r = first_combobox(c)
            if r is not None:
                return r
        return None

    class Wheel:
        def __init__(self, widget):
            self.widget, self.delta = widget, -120

    pump(0.5)
    app.shelf.select(BF.th.tab_index("out"))
    pump(0.5)
    page = app.pages[BF.th.tab_index("out")]
    combo = first_combobox(page.inner)
    y0 = page.canvas.yview()[0]
    app.tk.call("ttk::combobox::Post", combo)
    pump(0.3)
    check(app._dropdown_open(), "an open dropdown list is noticed")
    for _ in range(3):
        app._wheel(Wheel(page.canvas))
        pump(0.05)
    check(page.canvas.yview()[0] == y0, "scrolling while the list is open doesn't move the page under it")
    app.tk.call("ttk::combobox::Unpost", combo)
    pump(0.3)
    app._wheel(Wheel(page.canvas))
    pump(0.1)
    check(not app._dropdown_open() and page.canvas.yview()[0] != y0, "once it is closed the page scrolls as before")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
