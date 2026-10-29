"""Checks for "Fit contents on one page" (1.8.1; plain Python - run: python tests/test_contents_one_page_181.py).

Front & back -> Contents page -> "Fit contents on one page" (setting toc_one_page, off by default). These checks
read the contents page in the PDF itself (every word with its position):

1. Off (and in projects saved before the option existed): exactly the contents as before.
2. On, a short list that already fits: nothing changes.
3. On, longer lists: every entry on one page - none missing, clipped, overlapping, or with its page number over
   its words; page numbers on the right edge; long titles wrap; the type never below the readable limit; the
   chapters, their order, their text and their page numbers are unchanged apart from the shorter contents.
4. On, a list too long for one page at a readable size: the normal contents (complete, readable, as with the
   option off) and a warning in the log, the printing notes and the preview, from the real layout (not a
   chapter count).
5. Edited contents: renamed, reordered, hidden, added, typed page numbers (only the printed label), formatted
   entries, space above, parts and their chapters.
6. Preview = Print PDF = imposed sheets; right-hand chapter starts and blank pages; no empty pages.
7. Saved in projects and back; switching the option on and off; the estimate on the Front & back step agrees with
   the PDF; window checks.
Window checks run only where a display is available. Nothing needs the internet.
"""
import copy
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_toc1_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402
import pypdfium2 as pdfium                                            # noqa: E402

import bf_edit                                                        # noqa: E402
from bf_build import build_preview, run_build                         # noqa: E402
from bf_core import DEFAULTS, Book, Chapter, Block, apply_info, page_size_inches  # noqa: E402
from bf_pdf import (build_pdf, contents_entries, contents_rows, rows_to_edits, contents_fit_estimate,  # noqa: E402
                    TOC_FIT_MIN_SIZE, TOC_FIT_MIN_SCALE)

FAILS = []
DIGEST = "Half Letter / Digest (5.5 x 8.5 in)"


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def settings(**kw):
    s = copy.deepcopy(DEFAULTS)
    s.update(open_when_done=False, out_dir=tempfile.mkdtemp(dir=TMP), source_mode="paste", page_size=DIGEST,
             toc=True, title_page=True, fmt_pdf=True, fmt_impose=False, fmt_cover=False, fmt_epub=False,
             fmt_docx=False, fmt_html=False, fmt_txt=False, imp_files="Aggregated file only")
    s.update(kw)
    return s


def title(i, words=0):
    return f"Zt{i:03d}" + ("".join(f" word{k}" for k in range(words)) if words else "")


def book(n, words=0, parts=0):
    chs = []
    for i in range(1, n + 1):
        if parts and (i - 1) % parts == 0:
            chs.append(Chapter(f"Zp{(i - 1) // parts + 1:02d}", label=f"Part {(i - 1) // parts + 1}", level=0))
        chs.append(Chapter(title(i, words), blocks=[Block("para", text=f"Text of chapter {i}. " * 40)]))
    return Book(title="Contents Test", author="A. Writer", chapters=chs)


def make(b, s, name):
    """(PDF path, the book as typeset (its _contents_fit), log lines)."""
    b = apply_info(copy.deepcopy(b), dict(s))
    path = os.path.join(TMP, name + ".pdf")
    logs = []
    build_pdf(b, dict(s), path, log=logs.append)
    return path, b, logs


def pages(path):
    """Per page: (all words with positions, page height)."""
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            out.append((pg.extract_words(extra_attrs=["size"], keep_blank_chars=False), pg.height, pg.width))
    return out


def contents(path, s):
    """The contents pages: {page index: [lines]}, each line = (top, [words]); and the page numbers printed at the
    bottom (footers)."""
    pw_, ph_ = page_size_inches(s)
    mt, mb = float(s["margin_top"]) * 72, float(s["margin_bottom"]) * 72
    res = {}
    for i, (ws, H, W) in enumerate(pages(path)):
        body = [w for w in ws if mt - 2 < w["top"] and w["bottom"] < H - mb + 2]
        if any(w["text"] in ("Text", "Words") for w in body):          # a chapter page
            continue
        lines = {}
        for w in body:
            lines.setdefault(round(w["top"] / 2), []).append(w)
        lines = [(min(x["top"] for x in v), sorted(v, key=lambda x: x["x0"])) for _k, v in sorted(lines.items())]
        numbered = [ln for ln in lines if re.fullmatch(r"\d+|[ivxlc]+", ln[1][-1]["text"]) and len(ln[1]) > 1]
        if any(" ".join(w["text"] for w in ln[1]).upper() == "CONTENTS" for ln in lines) or len(numbered) >= 3:
            res[i] = lines                     # (the contents heading, or a page of numbered entries)
    return res


def entry_lines(cp):
    """The contents page's lines that are entries (not the heading), as (text, words, top, bottom)."""
    out = []
    for top, ws in cp:
        txt = " ".join(w["text"] for w in ws)
        if txt.strip().upper() == "CONTENTS":
            continue
        out.append((txt, ws, top, max(w["bottom"] for w in ws)))
    return out


def tidy(path, s, cp, expect_titles):
    """Every expected title complete on the contents page; page numbers at the right edge, after their words;
    no overlapping lines; nothing below the text area. Returns (ok, why)."""
    pw_, ph_ = page_size_inches(s)
    rights = [(pw_ - float(s["margin_outer"])) * 72, (pw_ - float(s["margin_inner"])) * 72]   # (odd / even page)
    H = ph_ * 72
    mb = float(s["margin_bottom"]) * 72
    lines = entry_lines(cp)
    text = " ".join(t for t, _w, _a, _b in lines)
    words_all = re.sub(r"\s+\d+(?= |$)", "", text).lower()          # (Title Case contents)
    missing = [t for t in expect_titles if t.lower() not in words_all]
    if missing:
        return False, f"missing or cut {missing[:3]}"
    prev_bottom = 0
    for t, ws, top, bottom in lines:
        if top < prev_bottom - 0.5:
            return False, f"overlapping lines at {t[:30]}"
        prev_bottom = bottom
        if bottom > H - mb + 1:
            return False, f"below the text area: {t[:30]}"
        num = ws[-1]
        if re.fullmatch(r"\d+|[ivxlc]+", num["text"]) and len(ws) > 1:
            if not any(r - 8 < num["x1"] < r + 1 for r in rights):
                return False, f"page number not at the right edge: {t[:30]} ({num['x1']:.1f} vs {rights})"
            if ws[-2]["x1"] > num["x0"] - 2:
                return False, f"page number over the words: {t[:30]}"
    return True, ""


def chars(path):
    with pdfplumber.open(path) as pdf:
        return [[(c["text"], round(c["x0"], 2), round(c["top"], 2), c["fontname"].split("+")[-1], round(c["size"], 2))
                 for c in pg.chars] for pg in pdf.pages]


def body_pages(path):
    """The text of the pages after the contents (chapter pages), without the page number lines."""
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if "Text of chapter" in t:
                out.append(re.sub(r"(?m)^\s*[-—]?\s*\d+\s*[-—]?\s*$", "", t).strip())
    return out


def starts(path):
    """chapter number -> printed page number of the page it starts on; and the contents' numbers for them."""
    st, listed = {}, {}
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            foot = (t.strip().split("\n") or [""])[-1].strip()
            if "Text of chapter" in t:
                m = re.search(r"Text of chapter (\d+)\.", t)
                for mm in re.finditer(r"^Zt(\d{3})\b", t, re.M):
                    st.setdefault(int(mm.group(1)), foot)
                if m and int(m.group(1)) not in st and re.search(rf"^Zt{int(m.group(1)):03d}", t, re.M):
                    st[int(m.group(1))] = foot
            else:
                for mm in re.finditer(r"Zt(\d{3})\b.*?(\d+)\s*$", t, re.M):
                    listed[int(mm.group(1))] = mm.group(2)
    return st, listed


# ============================================================================ 1./2. off; short lists
S_OFF, S_ON = settings(), settings(toc_one_page=True)
check(DEFAULTS["toc_one_page"] is False, "the option is off by default")
b10 = book(10)
p_off, _b, _l = make(b10, S_OFF, "short_off")
p_on, bk, logs = make(b10, S_ON, "short_on")
check(chars(p_on) == chars(p_off) and bk._contents_fit["fits"] and bk._contents_fit["step"] == 0,
      "a short contents list that already fits on one page: exactly the same pages with the option on")
b21 = book(21)                                  # "Automatic" spacing already gets these onto one page
p21_off, _b, logs21 = make(b21, S_OFF, "auto_off")
p21_on, bk21, _l = make(b21, S_ON, "auto_on")
check(any("spacing tightened" in m for m in logs21) and len(contents(p21_off, S_OFF)) == 1 and
      chars(p21_on) == chars(p21_off) and bk21._contents_fit["fits"] and bk21._contents_fit["step"] == 0,
      "a list that Automatic spacing already puts on one page: exactly the same pages with the option on")
old = {k: v for k, v in S_OFF.items() if k != "toc_one_page"}           # settings from before the option
p_old, _b, _l = make(b10, old, "short_old")
b30 = book(30)
p30_off, _b, _l = make(b30, S_OFF, "medium_off")
p30_old, _b, _l = make(b30, old, "medium_old")
check(chars(p_old) == chars(p_off) and chars(p30_old) == chars(p30_off),
      "older projects / settings without the option: the contents as before")

# ============================================================================ 3. lists that need fitting
c_off = contents(p30_off, S_OFF)
p30_on, b30_on, logs30 = make(b30, S_ON, "medium_on")
c_on = contents(p30_on, S_ON)
fit = b30_on._contents_fit
ok, why = tidy(p30_on, S_ON, c_on[min(c_on)], [title(i) for i in range(1, 31)]) if len(c_on) == 1 else (False, "")
check(len(c_off) == 2 and len(c_on) == 1 and fit["fits"] and fit["step"] in (1, 2) and ok,
      f"30 chapters: 2 contents pages off; on, all 30 on one page by tighter spacing (step {fit['step']}), "
      f"none missing, cut or overlapping {why}")
check(any("Contents: fitted on one page" in m for m in logs30), "the log says how the contents were fitted")
check(body_pages(p30_on) == body_pages(p30_off), "the chapters' pages are exactly the same (only the contents "
                                                 "page changed)")
st, listed = starts(p30_on)
st0, listed0 = starts(p30_off)
check(len(st) == 30 and all(listed.get(k) == st.get(k) for k in st) and
      all(int(st[k]) == int(st0[k]) - 1 for k in st),
      "the contents numbers are the chapters' real pages, one less than with two contents pages")
size_on = {round(w["size"], 2) for _t, ws in c_on[min(c_on)] for w in ws if w["text"].startswith("Zt")}
check(size_on and min(size_on) >= max(TOC_FIT_MIN_SIZE, TOC_FIT_MIN_SCALE * float(S_ON["body_size"])) - 0.01,
      f"readable type ({sorted(size_on)} pt; limit {max(TOC_FIT_MIN_SIZE, TOC_FIT_MIN_SCALE * 13):.2f})")

# many short entries on a bigger page: needs smaller type
b46 = book(46)
SL = settings(toc_one_page=True, page_size="Letter (8.5 x 11 in)")
p46, b46_on, _l = make(b46, SL, "many_on")
c46 = contents(p46, SL)
ok, why = tidy(p46, SL, c46[min(c46)], [title(i) for i in range(1, 47)]) if len(c46) == 1 else (False, "")
check(len(c46) == 1 and b46_on._contents_fit["fits"] and b46_on._contents_fit["step"] >= 3 and ok,
      f"46 chapters on Letter: one page with smaller type ({b46_on._contents_fit['size']:.2f} pt) {why}")

# long titles that wrap
bl = book(16, words=14)
pl_off, _b, _l = make(bl, S_OFF, "long_off")
pl, bl_on, _l = make(bl, S_ON, "long_on")
cl = contents(pl, S_ON)
wrapped = len(entry_lines(cl[min(cl)])) > 16 if cl else False
ok, why = tidy(pl, S_ON, cl[min(cl)], [title(i, 14) for i in range(1, 17)]) if len(cl) == 1 else (False, "")
check(len(contents(pl_off, S_OFF)) == 2 and len(cl) == 1 and wrapped and ok,
      f"16 long titles (14 words each): one page, titles wrapped onto more lines, every word kept {why}")

# ============================================================================ 4. too long for one page
b120 = book(120)
p120_off, _b, _l = make(b120, S_OFF, "huge_off")
p120, b120_on, logs120 = make(b120, S_ON, "huge_on")
f120 = b120_on._contents_fit
c120 = contents(p120, S_ON)
all_lines = " ".join(t for i in sorted(c120) for t, _w, _a, _b2 in entry_lines(c120[i]))
check(not f120["fits"] and chars(p120) == chars(p120_off) and len(c120) > 1 and
      all(title(i) in all_lines for i in range(1, 121)),
      f"120 chapters: can't fit at a readable size -> the normal contents ({len(c120)} pages, all 120 entries, "
      "same as with the option off)")
check(any(m.startswith("WARNING: Fit contents on one page") and "shorten" in m and "untick" in m
          for m in logs120), "a clear warning in the log, with what to do")
b14 = book(14, words=40)                    # few chapters, very long titles: the layout decides, not the count
p14, b14_on, logs14 = make(b14, S_ON, "fewlong_on")
check(not b14_on._contents_fit["fits"] and any("Fit contents on one page" in m for m in logs14),
      "only 14 chapters but very long titles: also too long (decided by the real layout, not a chapter count)")
folder, made, notes = run_build(apply_info(copy.deepcopy(b120), dict(S_ON)), dict(S_ON), log=lambda m: None)
readme = open(os.path.join(folder, "READ ME - printing notes.txt"), encoding="utf-8").read()
check(any("Fit contents on one page" in n for n in notes) and "Fit contents on one page" in readme,
      "the printing notes have the warning")
res = build_preview(apply_info(copy.deepcopy(b120), dict(S_ON)), dict(S_ON), log=lambda m: None)
check(res.get("contents_fit") and not res["contents_fit"]["fits"], "the preview knows it didn't fit")

# ============================================================================ 5. edited contents, parts
bp = book(24, parts=8)
s5 = settings(toc_one_page=True)
auto = contents_entries(apply_info(copy.deepcopy(bp), dict(s5)), s5)
rows = contents_rows(auto, [])
idx = {r["uid"]: n for n, r in enumerate(rows)}
ch = [c for c in bp.chapters if c.level != 0]
rows[idx[ch[0].uid]]["title"] = "Zr renamed first chapter"
rows[idx[ch[1].uid]]["markup"] = "<b>Zr bold second</b>"
rows[idx[ch[1].uid]]["title"] = "Zr bold second"
rows[idx[ch[2].uid]]["show"] = False
rows[idx[ch[3].uid]]["page"] = "99"
rows[idx[ch[4].uid]]["space"] = 12
a, b_ = idx[ch[5].uid], idx[ch[6].uid]
rows[a], rows[b_] = rows[b_], rows[a]
rows.append({"uid": None, "custom": True, "auto": "", "title": "Zc added map", "page": "x", "show": True,
             "level": 0, "auto_level": 0, "markup": None, "space": 0})
bp.toc = rows_to_edits(rows, auto)
p5_off, _b, _l = make(bp, settings(), "edited_off")
p5, bp_on, _l = make(bp, s5, "edited_on")
c5 = contents(p5, s5)
lines5 = entry_lines(c5[min(c5)]) if c5 else []
txt5 = "\n".join(t for t, _w, _a, _b2 in lines5)
expect = ["Zr renamed first chapter", "Zr bold second", "Zc added map"] + \
    [c.title for c in bp.chapters if c.level == 0] + [title(i) for i in range(4, 25)]
ok, why = tidy(p5, s5, c5[min(c5)], expect) if len(c5) == 1 else (False, "")
order = [m.group(0) for m in re.finditer(r"Zt00[67]", txt5)]
check(len(contents(p5_off, settings())) >= 2 and len(c5) == 1 and ok and title(3) not in txt5 and
      re.search(r"Zt004.*\b99\s*$", txt5, re.M) and order == ["Zt007", "Zt006"],
      f"edited contents with parts: one page with the renamed, formatted, added, moved, spaced and typed-number "
      f"entries, the hidden one left out {why}")
bold = [w for t, ws, _a, _b2 in lines5 for w in ws if w["text"] == "bold"]
with pdfplumber.open(p5) as pdf:
    bold_font = [c["fontname"] for pg in pdf.pages for c in pg.chars if c["text"] == "b" and
                 any(abs(c["top"] - w["top"]) < 1 and w["x0"] - 1 <= c["x0"] <= w["x1"] for w in bold)]
check(bold_font and all("Bold" in f for f in bold_font), "a formatted (bold) entry keeps its look")
st5, _l5 = starts(p5)
st5o, _l5o = starts(p5_off)
check([c.uid for c in bp_on.chapters] == [c.uid for c in bp.chapters] and body_pages(p5) == body_pages(p5_off) and
      st5.get(4) != "99", "chapters, their order and text unchanged; the typed 99 is only a label (chapter 4 starts "
                          f"on page {st5.get(4)})")

# ============================================================================ 6. preview / print / imposed
s6 = settings(toc_one_page=True, fmt_impose=True, chapter_start="Right-hand page", blank_pages_start="1")
folder, made, notes = run_build(apply_info(copy.deepcopy(b30), dict(s6)), dict(s6), log=lambda m: None)
prn = next(m for m in made if m.endswith("Print.pdf"))
imp = next(m for m in made if m.endswith("Imposed for binding.pdf"))
res6 = build_preview(apply_info(copy.deepcopy(b30), dict(s6)), dict(s6), log=lambda m: None)


def renders(path):
    doc = pdfium.PdfDocument(path)
    out = [doc[i].render(scale=0.25).to_pil().tobytes() for i in range(len(doc))]
    doc.close()
    return out


c6 = contents(prn, s6)
check(chars(res6["pdf"]) == chars(prn) and renders(res6["sheets"][0]) == renders(imp) and len(c6) == 1 and
      res6["empty_pages"] == [], "preview = Print PDF = imposed sheets (rendered); the contents on one page; no "
                                 "unexpected empty pages")
st6, _l6 = starts(prn)
with pdfplumber.open(prn) as pdf:
    first = [n for n, pg in enumerate(pdf.pages, 1) if "Text of chapter" in (pg.extract_text() or "")]
    n_pages = len(pdf.pages)
check(first and first[0] % 2 == 1 and len(pdfium.PdfDocument(imp)) * 2 >= n_pages,
      f"right-hand chapter starts kept (chapter 1 on page {first[0] if first else None}) and the imposed file "
      "holds every page")

# ============================================================================ 7. projects, on/off, estimate
proj = os.path.join(TMP, "one.bookforge")
bf_edit.save_project(proj, bp, s5, "1.8.1")
b7, s7 = bf_edit.load_project(proj)
p7, _b, _l = make(b7, s7, "reopened")
check(s7.get("toc_one_page") is True and chars(p7) == chars(p5), "saved in a project and the same after reopening")
p_again, _b, _l = make(b30, S_OFF, "medium_off_again")
check(chars(p_again) == chars(p30_off), "switched off again: exactly the contents as before")
est_ok = []
for name, b_, s_ in (("short", b10, S_ON), ("medium", b30, S_ON), ("many", b46, SL), ("long", bl, S_ON),
                     ("huge", b120, S_ON), ("edited", bp, s5), ("tightened", book(61), S_ON)):
    e = contents_fit_estimate(apply_info(copy.deepcopy(b_), dict(s_)), s_)
    _p, bb, _l = make(b_, s_, "est_" + name)
    real = bb._contents_fit
    est_ok.append(e is not None and e["fits"] == real["fits"] and e["step"] == real["step"] and
                  abs(e["size"] - real["size"]) < 0.01 and (real["fits"] or e["pages"] == real["pages"] ==
                                                             len(contents(_p, s_))))
check(all(est_ok), f"the estimate shown on Front & back agrees with the PDF {est_ok}")
pages_ok = []                              # option off: "The contents take about N pages" = the PDF's pages
for name, b_, s_ in (("medium", b30, S_OFF), ("huge", b120, S_OFF), ("long", bl, S_OFF),
                     ("compact", b120, settings(toc_spacing="Compact")), ("normal", b46, settings(toc_spacing="Normal")),
                     ("edited", bp, settings()), ("tightened", book(61), S_OFF)):   # (61: Automatic tightens)
    e = contents_fit_estimate(apply_info(copy.deepcopy(b_), dict(s_)), s_)
    _p, _bb, _l = make(b_, s_, "pages_" + name)
    pages_ok.append((e["pages"], len(contents(_p, s_))))
check(all(a == b_ for a, b_ in pages_ok), f"the estimate's page count with the option off = the PDF's {pages_ok}")

# ============================================================================ window
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

    def label():
        app.update_toc_fit()
        return str(app.toc_fit_label.cget("text"))

    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + "Words of the chapter. " * 30 + "\n\n"
                                                  for i in range(1, 31)))
    app.var("page_size").set(DIGEST)
    app.scan(force=True)
    idle(60)
    app.shelf.select(th.tab_index("front"))
    pump(0.6)
    boxes = []
    todo = [app.pages[th.tab_index("front")]]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == "TCheckbutton" and str(w.cget("text")) == "Fit contents on one page":
            boxes.append(w)
    check(boxes and app.var("toc_one_page").get() is False and "Tick to fit them on one page" in label(),
          f"Front & back: the “Fit contents on one page” box (off) and the estimate ({label()[:60]}...)")
    boxes[0].invoke() if boxes else app.var("toc_one_page").set(True)
    pump(0.6)
    check(app.var("toc_one_page").get() is True and label().startswith("The contents fit on one page"),
          "ticked: it says the contents fit on one page, and how")
    idle()
    app.preview_book()
    idle()
    pump(0.3)
    pw = getattr(app, "preview_win", None)
    res = pw.result if pw is not None and pw.alive() else None
    cp = contents(res["pdf"], app.collect()) if res else {}
    check(res and len(cp) == 1 and "Fit contents on one page" not in str(pw.info.cget("text")),
          "the preview shows the contents on one page")
    app.edit_contents()
    pump(0.2)
    cw = app.contents_win
    cw.rows[0]["title"] = "Chapter 1 with a much longer title that wraps onto a second line of the contents"
    cw.rows[4]["show"] = False
    cw.ok()
    pump(0.2)
    idle()
    app.preview_book()
    idle()
    pump(0.3)
    res = app.preview_win.result
    txt = "\n".join(page.extract_text() or "" for page in pdfplumber.open(res["pdf"]).pages[:4])
    check(len(contents(res["pdf"], app.collect())) == 1 and "much longer title" in txt,
          "after Edit contents (renamed, hidden): still one page, with the edits")
    app.var("body_size").set(13.0)
    app.texts["paste_text"].delete("1.0", "end")
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + "Words of the chapter. " * 10 + "\n\n"
                                                  for i in range(1, 121)))
    SAID.clear()
    app.scan(force=True)
    idle(60)
    pump(0.3)
    lab = label()
    check(lab.startswith("⚠") and "too long for one page" in lab and "untick" in lab,
          "120 chapters: the estimate warns before anything is made, and says what to do")
    idle()
    app.preview_book()
    idle()
    pump(0.3)
    check("Fit contents on one page" in str(app.preview_win.info.cget("text")),
          "the preview window shows the warning")
    proj = os.path.join(TMP, "window.bookforge")
    PICK.append(proj)
    idle()
    app.save_project_dialog()
    app.var("toc_one_page").set(False)
    PICK.append(proj)
    idle()
    app.open_project_dialog()
    pump(0.3)
    check(app.var("toc_one_page").get() is True, "the window: saved in the project and ticked again on reopening")
    book9, sett = bf_edit.load_project(proj)
    sett.pop("toc_one_page", None)
    old = os.path.join(TMP, "old.bookforge")
    bf_edit.save_project(old, book9, sett, "1.8.0")
    PICK.append(old)
    idle()                                       # (the preview made for the reopened project first)
    app.open_project_dialog()
    pump(0.3)
    check(app.var("toc_one_page").get() is False, "the window: an older project opens with the option off")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
