"""Chapter detection / text preservation tests (plain Python - run:  python tests/test_chapters.py).

Book files are NOT stored in the repo (they belong to their authors). Put your own copies in
tests/inputs/ - any that are missing are skipped:
  End_of_the_Line.epub            AO3 work 84070831 (28 chapters)
  Of_the_Tales_of_Ulmos.html      AO3 work 85682851, HTML download (22 chapters in the text)
  pg2591-images-3.epub            Grimms' Fairy Tales, Project Gutenberg (62)
  gregory-of-nyssa_on-the-making-of-man_william-moore-henry-austin-wilson.epub  Standard Ebooks (33)
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
INPUTS = os.environ.get("BOOKFORGE_TEST_INPUTS", os.path.join(HERE, "inputs"))

from bs4 import BeautifulSoup                           # noqa: E402
import bf_impose                                        # noqa: E402,F401  (registers binding defaults)
from bf_core import DEFAULTS, load_book, parse_text, plain, clean_chars   # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def chapters(book):
    return [c for c in book.chapters if c.include]


def from_file(name):
    s = dict(DEFAULTS)
    s["source_path"] = os.path.join(INPUTS, name)
    return load_book(s)


def browser_copy(html_bytes):
    """Plain text the way a browser copy looks: one block element per paragraph."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    tags = ["p", "h1", "h2", "h3", "dt", "dd", "li", "blockquote", "div"]
    out = [el.get_text().strip() for el in soup.body.find_all(tags) if not el.find(tags)]
    return "\n\n".join(t for t in out if t)


# ---------------------------------------------------------------- small pasted-text cases
S = dict(DEFAULTS)
b = parse_text("Prologue\n\nOnce.\n\nChapter 1\n\nA.\n\nChapter 2\n\nB.\n\nEpilogue\n\nEnd.", S)
check([(c.title, [x.text for x in c.blocks]) for c in b.chapters] ==
      [("Prologue", ["Once."]), ("Chapter 1", ["A."]), ("Chapter 2", ["B."]), ("Epilogue", ["End."])],
      "one-line chapters keep their text (no line swallowed as a title)")
b = parse_text("Chapter One\n\nThe Beginning\n\nIt was night.\n\nChapter Two\n\nThe Middle\n\nIt was day.", S)
check([(c.label, c.title) for c in b.chapters] == [("Chapter One", "The Beginning"), ("Chapter Two", "The Middle")],
      "'Chapter One' + title line become label + title")
b = parse_text("Chapter 1\n\nText one.\n\nChapter Notes\n\nA note.\n\nChapter 2\n\nText two.\n\n"
               "Chapter End Notes\n\nBye.", S)
check([c.title for c in b.chapters] == ["Chapter 1", "Chapter 2"],
      "AO3 labels (Chapter Notes / Chapter End Notes) are not chapters")
check(any(x.kind == "anote" and "Bye." in x.text for x in b.chapters[1].blocks),
      "pasted 'Chapter End Notes' text is kept as an author's note")
b = parse_text("Chapter 1: Start\n\nText.\n\nChapter triggers!\n\nMore text.\n\nChapter 2: Next\n\nEnd.", S)
check([c.title for c in b.chapters] == ["Chapter 1: Start", "Chapter 2: Next"],
      "un-numbered 'Chapter ...' line is text when chapters are numbered")
b = parse_text("# Chapter One\n\nText.\n\n# Chapter Two\n\nMore.", S, is_md=True)
check([c.title for c in b.chapters] == ["Chapter One", "Chapter Two"], "Markdown headings")

# ---------------------------------------------------------------- real books (skipped if absent)
CASES = [("End_of_the_Line.epub", 28), ("Of_the_Tales_of_Ulmos.html", 22), ("pg2591-images-3.epub", 62),
         ("gregory-of-nyssa_on-the-making-of-man_william-moore-henry-austin-wilson.epub", 33)]
for name, n in CASES:
    if not os.path.exists(os.path.join(INPUTS, name)):
        print(f"SKIP  {name} (not in {INPUTS})")
        continue
    bk = from_file(name)
    got = len(chapters(bk))
    check(got == n, f"{name}: {got} chapters (expected {n})")
    if name.startswith(("End_of", "Of_the")):
        check(len(bk.fic_meta) >= 3 and bk.fic_summary,
              f"{name}: work info ({len(bk.fic_meta)} lines) and summary found")
        check(not any(c.title.strip().lower() in ("preface", "afterword") for c in chapters(bk)),
              f"{name}: AO3 Preface/Afterword pages are not chapters")
        raw = open(os.path.join(INPUTS, name), "rb").read()
        if name.endswith(".html"):
            pasted = parse_text(browser_copy(raw), dict(DEFAULTS))
            check(len(chapters(pasted)) == n, f"{name} pasted as text: {len(chapters(pasted))} chapters")

ulmo = os.path.join(INPUTS, "Of_the_Tales_of_Ulmos.html")
if os.path.exists(ulmo):
    soup = BeautifulSoup(open(ulmo, "rb").read(), "html.parser")
    body = soup.find("div", id="chapters")
    for br in body.find_all("br"):
        br.replace_with(" ")
    src = []
    for el in body.find_all(["p", "h2"]):
        if not el.find(["p", "h2"]) and el.name != "h2":
            src += clean_chars(el.get_text("")).split()
    out = []
    for c in chapters(from_file("Of_the_Tales_of_Ulmos.html")):
        out += c.title.split()
        for x in c.blocks:
            if x.kind != "anote":
                out += plain(x.text).split()
    check(src == out, f"Ulmo story text word-for-word and in order ({len(src)} words)")

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
