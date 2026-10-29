"""Checks for 1.8.0 Phase 6 (plain Python - run: python tests/test_contents_merge_180.py).

1. Merging chapters keeps a page number typed in Edit contents. Before 1.8.0 the absorbed chapter's typed
   number was dropped with its entry (in Phase 5 the status line said so, but the number was still lost):
   - only the absorbed chapter had a typed number: it moves to the surviving chapter's entry;
   - both had different numbers: the user is asked which one stays, or cancels (nothing changes then);
   - the number stays with the surviving chapter after renaming and moving it, and after save / reopen;
   - an open Edit contents window and the contents page in Specific Text Edit show the kept number, so
     neither can put the old numbers back;
   - a typed number is only what the contents prints: the chapter still starts on its real page.
   Projects without typed numbers (and older projects without contents edits) merge exactly as before.
2. The labels say which size is which: "Book page size" (Layout step, each finished page of the book) and
   "Printer paper size" (Output step, the sheet that goes through the printer). The setting names in saved
   settings, presets and projects (page_size, sheet_size) are unchanged.
Window checks run only where a display is available. Nothing needs the internet.
"""
import copy
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="bf_merge_")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.environ["HOME"] = os.path.join(TMP, "home")
os.environ["BOOKFORGE_NO_UPDATE_CHECK"] = "1"
os.makedirs(os.environ["APPDATA"], exist_ok=True)
os.makedirs(os.path.join(os.environ["HOME"], "Documents"), exist_ok=True)

import pdfplumber                                                     # noqa: E402

import bf_edit                                                        # noqa: E402
import bf_impose                                                      # noqa: E402
from bf_build import run_build                                        # noqa: E402
from bf_core import DEFAULTS, PAGE_SIZES, Book, Chapter, Block, custom_page_inches   # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


# ============================================================================ 1. the contents edits after a merge
try:
    from bf_pdf import merged_contents_page, merge_contents_edits
    have_fn = True
except ImportError as e:
    have_fn = False
    check(False, f"bf_pdf has the merge rules for contents edits ({e})")

if have_fn:
    check(merged_contents_page("", "42") == "42" and merged_contents_page("12", "") is None and
          merged_contents_page("", "") is None and merged_contents_page("12", "12") is None and
          merged_contents_page("12", "57", "57") == "57" and merged_contents_page("12", "57", "12") == "12",
          "the kept page number: the absorbed one when only it had one, the chosen one when both differed")
    edits = [{"uid": "a", "title": None, "page": "", "show": True, "level": None},
             {"custom": True, "title": "Map", "page": "ix", "level": 0, "show": True},
             {"uid": "b", "title": None, "page": "", "show": True, "level": None},
             {"uid": "c", "title": "Typed text", "page": "42", "show": True, "level": None, "markup": "<b>T</b>"}]
    before = copy.deepcopy(edits)
    out = merge_contents_edits(edits, "b", "c", "42")
    check(edits == before, "the edits given are not changed (a new list is returned)")
    check([e.get("uid") for e in out] == ["a", None, "b"] and out[2]["page"] == "42" and out[2]["title"] is None
          and out[1] == before[1],
          "the absorbed entry goes, its number moves to the surviving entry (typed text stays behind), "
          "added entries are untouched")
    out = merge_contents_edits(edits, "b", "c", None)
    check([e.get("uid") for e in out] == ["a", None, "b"] and out[2]["page"] == "",
          "nothing to keep: only the absorbed entry goes")
    out = merge_contents_edits([e for e in edits if e.get("uid") != "b"], "b", "c", "42")
    check([e.get("uid") for e in out] == ["a", None, "b"] and out[2]["page"] == "42",
          "a surviving chapter without a saved entry gets one where the absorbed entry was")

# ============================================================================ 2. the window
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as e:                     # noqa: BLE001
    have_display = False
    print(f"SKIP  window checks (no display: {e})")


def contents_lines(pdf_path):
    """The lines of the contents page of a typeset book."""
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages[:8]:
            txt = pg.extract_text() or ""
            if txt.strip().upper().startswith("CONTENTS"):
                return [ln.strip() for ln in txt.splitlines()[1:]]
    return []


def number_for(lines, entry):
    """The page number the contents prints beside an entry (None if the entry isn't there)."""
    for ln in lines:
        if ln.rsplit(" ", 1)[0] == entry:
            return ln.rsplit(" ", 1)[1]
    return None


def widgets(w):
    yield w
    for c in w.winfo_children():
        yield from widgets(c)


if have_display:
    from tkinter import messagebox, filedialog
    SAID, ANSWER = [], {}
    for kk in ("askyesno", "askyesnocancel", "showinfo", "showerror", "showwarning", "askokcancel"):
        setattr(messagebox, kk, (lambda kind: (lambda title="", message="", **kw: SAID.append((kind, title, message))
                                               or ANSWER.get(kind, True)))(kk))
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

    def preview():
        idle()
        app.preview_book()
        idle()
        pump(0.2)
        pw = getattr(app, "preview_win", None)
        return pw.result if pw is not None and pw.alive() else None

    def uid_of(title):
        return next((c.uid for c in app.book.chapters if c.title == title), None)

    def typed(uid):
        e = next((e for e in app.book.toc or [] if not e.get("custom") and e.get("uid") == uid), None)
        return (e.get("page") or "") if e else ""

    def type_page(title, page):
        """Edit contents > Page number for one chapter's entry, then OK."""
        app.edit_contents()
        pump(0.1)
        cw = app.contents_win
        r = next(r for r in cw.rows if r["uid"] == uid_of(title))
        r["page"] = page
        cw.ok()
        pump(0.1)

    def merge(title):
        """Chapters step: select the chapter and Merge into previous."""
        idle()
        app.fill_list()
        i = next((i for i, c in enumerate(app.book.chapters) if c.title == title), None)
        if i is None:
            check(False, f"{title} is still there to merge")
            return []
        app.ctree.selection_set(str(i))
        n = len(SAID)
        app.merge_ch()
        pump(0.1)
        return [s for s in SAID[n:] if s[0] == "askyesnocancel"]

    app.var("source_mode").set("paste")
    app._mode_changed()
    app.texts["paste_text"].insert("1.0", "".join(f"Chapter {i}\n\n" + f"Words of chapter {i}. " * 300 + "\n\n"
                                                  for i in range(1, 8)))
    app.var("toc").set(True)
    app.scan(force=True)
    idle(60)
    res = preview()
    real_before = dict(app.toc_labels)                  # uid -> the page each chapter really starts on
    u2 = uid_of("Chapter 2")

    # ---- 2a. only the absorbed chapter has a typed number: it is kept, on the surviving entry
    type_page("Chapter 3", "42")
    u3 = uid_of("Chapter 3")
    asked = merge("Chapter 3")
    check(not asked and uid_of("Chapter 3") is None and typed(u2) == "42" and
          not any(e.get("uid") == u3 for e in app.book.toc),
          "merging a chapter with a typed contents page number into one without: the number is kept on the "
          f"surviving entry, nothing asked ({typed(u2)!r})")
    check("(42) is kept" in str(app.status.cget("text")) and "Chapter 2" in str(app.status.cget("text")),
          f"... and the status line says so ({app.status.cget('text')})")
    res = preview()
    lines = contents_lines(res["pdf"]) if res else []
    check(number_for(lines, "Chapter 2") == "42" and number_for(lines, "Chapter 3") is None and
          number_for(lines, "Chapter 4") == app.toc_labels.get(uid_of("Chapter 4")),
          f"the contents page prints 42 beside Chapter 2, no Chapter 3 entry, real numbers for the others {lines}")
    check(app.toc_labels.get(u2) == real_before[u2] and app.toc_labels.get(u2) != "42",
          f"the typed number doesn't move the chapter: Chapter 2 still starts on page {app.toc_labels.get(u2)}")

    # ---- 2b. both have different typed numbers: asked; Cancel changes nothing
    type_page("Chapter 2", "12")
    type_page("Chapter 4", "57")
    u4 = uid_of("Chapter 4")
    snap = (copy.deepcopy(app.book.toc), [(c.uid, c.title, len(c.blocks)) for c in app.book.chapters],
            [b.text for b in app.book.chapters[1].blocks])
    ANSWER["askyesnocancel"] = None
    asked = merge("Chapter 4")
    check(len(asked) == 1 and "12" in asked[0][2] and "57" in asked[0][2] and "Cancel" in asked[0][2],
          "both chapters have different typed numbers: the user is asked which to keep (or to cancel)")
    check((app.book.toc, [(c.uid, c.title, len(c.blocks)) for c in app.book.chapters],
           [b.text for b in app.book.chapters[1].blocks]) == snap and "cancelled" in str(app.status.cget("text")),
          "Cancel: no merge - the chapters, their text and the contents numbers are exactly as before")

    # ---- 2c. No = keep the absorbed chapter's number
    ANSWER["askyesnocancel"] = False
    asked = merge("Chapter 4")
    check(len(asked) == 1 and uid_of("Chapter 4") is None and typed(u2) == "57" and
          not any(e.get("uid") == u4 for e in app.book.toc),
          f"choosing the absorbed chapter's number (57): it is the surviving entry's number ({typed(u2)!r})")

    # ---- 2d. Yes = keep the surviving chapter's number
    type_page("Chapter 5", "88")
    ANSWER["askyesnocancel"] = True
    asked = merge("Chapter 5")
    check(len(asked) == 1 and uid_of("Chapter 5") is None and typed(u2) == "57",
          f"choosing the surviving chapter's number (57 over 88): it stays ({typed(u2)!r})")
    ANSWER.pop("askyesnocancel")

    # ---- 2e. save and reopen the project: the kept number comes back with the chapter
    proj = os.path.join(TMP, "merged.bookforge")
    idle()
    PICK.append(proj)
    app.save_project_dialog()
    with open(proj, encoding="utf-8") as f:
        saved = json.load(f)
    PICK.append(proj)
    idle()
    app.open_project_dialog()
    pump(0.3)
    check(not app.unsaved and saved["settings"].get("page_size") == app.var("page_size").get() and
          uid_of("Chapter 2") == u2 and typed(u2) == "57" and len(app.book.chapters) == 4,
          "save and reopen the project: the surviving chapter (same id) still has the kept number 57")
    res = preview()
    lines = contents_lines(res["pdf"]) if res else []
    check(number_for(lines, "Chapter 2") == "57", f"... and the reopened book prints it {lines}")

    # ---- 2f. rename and move the surviving chapter: the number stays with it
    ch2 = next(c for c in app.book.chapters if c.uid == u2)
    ch2.title = "Renamed Two"
    app._changed()
    app.fill_list()
    app.ctree.selection_set("1")
    app.move_ch(-1)                                         # Renamed Two is now the first chapter
    res = preview()
    lines = contents_lines(res["pdf"]) if res else []
    first = app.book.chapters[0]
    u1 = uid_of("Chapter 1")
    check(first.uid == u2 and typed(u2) == "57" and number_for(lines, "Renamed Two") == "57" and
          number_for(lines, "Chapter 1") == app.toc_labels.get(u1) and app.toc_labels.get(u2) != "57",
          f"renamed and moved: the typed number stays with the surviving chapter, the others are real {lines}")

    # ---- 2g. an open Edit contents window: a number typed there (not yet OK'd) is kept too, and Cancel goes
    # back to the contents as they were before the window was opened (merged)
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    u6 = uid_of("Chapter 6")
    next(r for r in cw.rows if r["uid"] == u6)["page"] = "33"
    asked = merge("Chapter 6")
    u7 = uid_of("Chapter 7")
    prev6 = app.book.chapters[[c.uid for c in app.book.chapters].index(u7) - 1]
    check(not asked and uid_of("Chapter 6") is None and typed(prev6.uid) == "33" and
          not any(r["uid"] == u6 for r in cw.rows) and
          next(r for r in cw.rows if r["uid"] == prev6.uid)["page"] == "33",
          "a number typed in the open Edit contents window is kept, and the window shows it on the surviving entry")
    cw.cancel()
    pump(0.1)
    check(typed(prev6.uid) == "" and typed(u2) == "57" and not any(e.get("uid") == u6 for e in app.book.toc or []),
          "... and Cancel in that window goes back to the contents before it was opened (the merge stays)")

    # ---- 2h. the contents page open in Specific Text Edit: after a merge on the Chapters step it shows the kept
    # number, so saving that page can't bring the old one back (the absorbed entry was hidden: same lines)
    app.edit_contents()
    pump(0.1)
    cw = app.contents_win
    r7 = next(r for r in cw.rows if r["uid"] == u7)
    r7["page"], r7["show"] = "71", False
    cw.ok()
    pump(0.1)
    ed = app.editor
    app.shelf.select(th.tab_index("edit"))
    pump(0.3)
    ed.select_section("contents")
    pump(0.3)
    app.shelf.select(th.tab_index("chap"))
    pump(0.3)
    asked = merge("Chapter 7")
    app.shelf.select(th.tab_index("edit"))
    pump(0.3)
    surv = app.book.chapters[-1]
    rows_ed = {r["uid"]: r["page"] for r in getattr(ed, "toc_rows", [])}
    check(not asked and typed(surv.uid) == "71" and rows_ed.get(surv.uid) == "71" and u7 not in rows_ed,
          "Specific Text Edit's contents page shows the kept number after the merge (it is loaded again)")
    ed.txt.insert("end-1c", " ")                         # a change on that page, then leave the step: saved
    ed.dirty = True
    app.shelf.select(th.tab_index("chap"))
    pump(0.3)
    check(typed(surv.uid) == "71" and typed(u2) == "57",
          f"... and saving that page keeps the numbers ({typed(surv.uid)!r}, {typed(u2)!r})")

    # ---- 2i. a project without any typed numbers, saved by an older BookForge (no contents edits stored):
    # merging is exactly as before, nothing asked
    old = Book(title="Old Project", chapters=[Chapter(f"Old {i}", blocks=[Block("para", text=f"Old words {i}. " * 80)])
                                              for i in range(1, 4)])
    oldp = os.path.join(TMP, "old.bookforge")
    bf_edit.save_project(oldp, old, dict(DEFAULTS, page_size="Trade Paperback (6 x 9 in)", sheet_size="Tabloid"),
                         "1.6.0")
    with open(oldp, encoding="utf-8") as f:
        data = json.load(f)
    for k in ("toc", "matter"):
        data["book"].pop(k, None)
    for c in data["book"]["chapters"]:
        c.pop("uid", None)                                # older projects had no chapter ids either
    with open(oldp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    app.unsaved = False
    PICK.append(oldp)
    idle()
    app.open_project_dialog()
    pump(0.3)
    blocks_want = [b.text for b in app.book.chapters[0].blocks] + ["Old 2"] + \
        [b.text for b in app.book.chapters[1].blocks]
    asked = merge("Old 2")
    check(not asked and app.book.toc == [] and [c.title for c in app.book.chapters] == ["Old 1", "Old 3"] and
          [b.text for b in app.book.chapters[0].blocks] == blocks_want and
          app.var("page_size").get() == "Trade Paperback (6 x 9 in)" and app.var("sheet_size").get() == "Tabloid / 11x17",
          "an older project without typed numbers: opens with its sizes (old paper name Tabloid), merges as before (heading back in the "
          "text), the contents stay automatic, nothing asked")
    res = preview()
    lines = contents_lines(res["pdf"]) if res else []
    check(number_for(lines, "Old 1") == app.toc_labels.get(app.book.chapters[0].uid) and
          number_for(lines, "Old 3") == app.toc_labels.get(app.book.chapters[1].uid) and
          number_for(lines, "Old 2") is None, f"... and its contents shows the real page numbers {lines}")

    # ============================================================================ 3. the page size labels
    texts = {}
    for w in widgets(app):
        try:
            texts.setdefault(str(w.cget("text")), []).append(w)
        except (tk.TclError, AttributeError):
            pass

    def beside(label):
        """The variable name of the control on the same row as a label (combo boxes: their textvariable)."""
        out = []
        for lw in texts.get(label, []):
            gi = lw.grid_info()
            for c in lw.master.grid_slaves(row=int(gi["row"]), column=1):
                try:
                    out.append(str(c.cget("textvariable")))
                except tk.TclError:
                    pass
        return out

    check(beside("Book page size") == [str(app.var("page_size"))] and
          beside("Printer paper size") == [str(app.var("sheet_size"))],
          "Layout: “Book page size” is the page_size setting; Output: “Printer paper size” is "
          "the sheet_size setting")
    check(all(t in texts for t in ("Book page & margins (inches)", "Use a custom printer paper size",
                                   "Custom printer paper size", "Paper weight (sets spine width)")) and
          not any(t in texts for t in ("Page size", "Paper size", "Use a custom paper size", "Custom paper size",
                                       "Paper (sets spine width)")),
          "the other labels follow (custom printer paper, paper weight for the spine); the old ones are gone")
    app.var("sheet_size").set("Letter")
    app._paper_changed()
    check(str(app.paper_lbl.cget("text")).startswith("Printer paper size: Letter"),
          f"the line under it names the printer paper size ({app.paper_lbl.cget('text')})")
    check("book page size" in BF.HELP and "printer paper size" in BF.HELP and
          "Use a custom printer paper size" in BF.HELP and "Use a custom paper size" not in BF.HELP,
          "the help uses the same names")

    # settings compatibility: the same keys everywhere; older names still read
    keys = set(app.collect())
    check({"page_size", "sheet_size", "custom_w", "custom_h", "sheet_w", "sheet_h", "paper"} <= keys and
          not any("book_page" in k or "printer_paper" in k for k in keys) and set(DEFAULTS) <= keys,
          "the settings keep their names (page_size, sheet_size...): saved settings, presets and projects")
    preset = os.path.join(TMP, "p.json")
    PICK.append(preset)
    app.save_preset()
    with open(preset, encoding="utf-8") as f:
        pdata = json.load(f)
    old_preset = os.path.join(TMP, "old.json")
    with open(old_preset, "w", encoding="utf-8") as f:
        json.dump({"page_size": "Paperback (5 x 8 in)", "sheet_size": "11x17"}, f)
    app.load_settings(old_preset)
    pump(0.1)
    check("page_size" in pdata and "sheet_size" in pdata and "Paperback (5 x 8 in)" in PAGE_SIZES and
          app.var("page_size").get() == "Paperback (5 x 8 in)" and app.var("sheet_size").get() == "Tabloid / 11x17"
          and bf_impose.SHEET_ALIASES.get("11x17") == "Tabloid / 11x17",
          "a preset is saved with the same keys, and an older settings file (page_size, sheet_size \u201c11x17\u201d) "
          f"still loads ({app.var('page_size').get()!r}, {app.var('sheet_size').get()!r})")
    check(not errors, f"no window errors {errors[:1]}")
    app.destroy()

# ---- the messages and the printing notes use the same names
try:
    custom_page_inches("x", 9)
    msg = ""
except ValueError as e:
    msg = str(e)
try:
    bf_impose.custom_sheet_points("0", "11", "in")
    msg2 = ""
except ValueError as e:
    msg2 = str(e)
check(msg.startswith("Custom book page width") and msg2.startswith("Custom printer paper width"),
      f"unusable custom sizes name the book page / the printer paper ({msg} / {msg2})")
s = dict(DEFAULTS, out_dir=tempfile.mkdtemp(dir=TMP), open_when_done=False, fmt_pdf=True, fmt_impose=True,
         fmt_cover=False, fmt_epub=False, fmt_docx=False, fmt_html=False, fmt_txt=False,
         page_size="Mass Market (4.25 x 6.87 in)", sheet_size="Letter")
book = Book(title="Notes", chapters=[Chapter("One", blocks=[Block("para", text="Words. " * 200)])])
_f, _m, notes = run_build(book, s, log=lambda m: None)
check(any(n.startswith("Print PDF:") and "book page size 4.25 x 6.87 in" in n for n in notes) and
      any("sheet(s) of Letter (8.5 × 11.0 inches) printer paper" in n for n in notes),
      "the printing notes say book page size and printer paper")

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
