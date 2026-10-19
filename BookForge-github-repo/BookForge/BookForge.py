"""BookForge - one-click book maker (Windows GUI)."""
import copy
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from bf_core import (DEFAULTS, PAGE_SIZES, PAPERS, APP_NAME, APP_VERSION, APP_AUTHOR, BUILD_DATE,
                     load_book, apply_info, plain, esc, Block, Chapter)
import bf_fonts
from bf_fonts import SAME_BODY, SAME_HEAD
from bf_pdf import HYPH_LANGS
from bf_impose import LAYOUT_NAMES, SHEETS, SIG_FORMATS, SOURCE_ROT, SEWING_WHERE, FOLD_SIDES, UNITS
from bf_build import run_build, default_out_dir, build_preview
import bf_edit
import bf_theme as th

TEXT_KEYS = ("paste_text", "dedication", "note_text", "blurb", "hyph_words")
# Fields that belong to one particular book. They are NOT remembered between sessions, so a new
# session never starts with the previous book's file, text, title or author.
BOOK_KEYS = ("source_path", "paste_text", "title", "subtitle", "author", "credit", "dedication",
             "note_title", "note_text", "blurb")
PARSE_KEYS = ("source_mode", "source_path", "split_mode", "custom_regex", "strip_gutenberg",
              "skip_contents", "skip_cover", "include_images", "keep_front_text", "drop_empty",
              "line_paragraphs", "preserve_breaks")

HELP = """HOW TO USE BOOKFORGE

1. SOURCE: pick an EPUB, TXT, Markdown, HTML or Word (.docx) file, or choose
   "Paste text" and paste your writing. Click "Scan chapters" to check that the
   chapters were found correctly. You can rename or skip chapters in the list.
2. BOOK INFO: title, subtitle and author for the title page (left blank, the
   EPUB's own details are used).
3. LAYOUT / FRONT & BACK: page size, fonts, margins, chapter style, page
   numbers, contents page, bookplate, dedication and so on.
4. PREVIEW BOOK shows the book exactly as it will print (and, with imposition on,
   the printing sheets). Nothing is saved. Change settings and click Update
   preview as often as you like.
5. OUTPUT: tick the formats you want and click GENERATE PRINTING FILES. Everything is saved
   in one folder, together with a "READ ME - printing notes.txt" file.

TEXT IS KEPT WORD FOR WORD. Only spacing used for line-wrapping in the source
file is tidied; italics, bold and line breaks in poems are carried over.

PRINTING THE "IMPOSED FOR BINDING" PDF
- The Output tab has every binding option: folio, quarto, octavo or
  sextodecimo layouts, small "wacky" layouts and a one-sheet zine, booklet /
  perfect bound / standard / custom signatures, flyleafs, page range, page
  rotation, scaling, margins, fold/cut/spine/signature/sewing marks, and
  duplex or single-sided printing.
- Print at Actual size / 100% (never "Fit"). The printing notes file says
  which edge to flip on for your layout. If your printer can only flip on the
  other edge, tick "Rotate back sides 180" and rebuild.
- Print ONE test sheet first and fold it: page numbers should run in order.
- The notes file also has the folding steps for your layout. As in
  bookbinder-js, each signature's innermost sheet prints first. For folio:
  fold every sheet in half, then nest sheet 1 inside sheet 2, those inside
  sheet 3, and so on. "Perfect bound" signatures are single sheets: just
  fold and stack them in order.
- Stack the signatures in order. The small black marks on the folds make a
  staircase when they're in the right order.

PERFECT BINDING
- Clamp each signature and shave/cut off the folded edge so every page is a
  loose leaf (skip this if you plan to sew the signatures instead).
- Jog the whole stack square, clamp it with the spine edge sticking out 1/8".
- Rough up the spine lightly, brush on flexible PVA glue in two thin coats.
  A strip of mull/cloth pressed into the glue makes it much stronger.
- Wrap the cover (Cover PDF, printed on cardstock, folded on the dashed lines)
  around the glued spine, clamp, and leave overnight.
- Trim the three open edges with a guillotine or a sharp blade + straightedge.

TIPS
- Half-letter (5.5 x 8.5) pages fill a landscape letter sheet exactly. Letter
  pages are shrunk to fit, so pick a bigger font size if you use them.
- Characters your chosen font doesn't have (Greek with accents, Hebrew,
  symbols, Chinese...) are drawn automatically with another installed font
  that has them. The status log says which font was borrowed, and warns if
  something isn't in any font on your PC.
- Invisible typesetting characters (word joiners, hair spaces) and the little
  return-arrows after e-book footnotes are left out; note numbers are printed
  as superscripts. The words themselves are never changed.
"""


class BookEditor:
    """The Edit step: chapters on the left, a Word-style editor on the right.

    The text box holds one chapter. Paragraph styles, alignment etc. are tags on whole lines; bold, italic,
    fonts, sizes and colours are tags on characters. bf_edit converts to and from the book model, which the
    preview and every output are made from, so edits always appear exactly as they will print."""

    SIZES = ["(default)"] + [str(n) for n in (8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 36, 48, 60)]
    SPACES = ["0", "6", "12", "18", "24", "36"]
    STYLE_SIZE = {"head": 16, "subtitle": 13, "anote": 10, "image": 11}

    def __init__(self, app, parent):
        self.app, self.cur, self.cur_obj = app, None, None
        self.loading, self.dirty, self.title_dirty = False, False, False
        self.images, self.fontcache, self.undo_stack, self.redo_stack = {}, {}, [], []
        self.last_snap = 0.0
        S = app.S
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        left = ttk.LabelFrame(parent, text="Chapters", padding=8, style=S("TLabelframe"))
        left.grid(row=0, column=0, sticky="nsw", padx=6, pady=5)
        left.rowconfigure(0, weight=1)
        self.lst = tk.Listbox(left, width=30, exportselection=False, activestyle="none", font=("Segoe UI", 10))
        th.style_text(self.lst, app.k)
        self.lst.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.lst.bind("<<ListboxSelect>>", lambda e: self._picked())
        ttk.Label(left, text="Chapter title", style=S("Card.TLabel")).grid(row=1, column=0, columnspan=2,
                                                                          sticky="w", pady=(8, 0))
        self.title_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.title_var, style=S("TEntry")).grid(row=2, column=0, columnspan=2,
                                                                            sticky="we")
        self.title_var.trace_add("write", lambda *a: self._title_changed())
        for n, (txt, fn) in enumerate((("Add chapter", self.add_chapter), ("Delete chapter", self.delete_chapter),
                                       ("Move up", lambda: self.move_chapter(-1)),
                                       ("Move down", lambda: self.move_chapter(1)))):
            ttk.Button(left, text=txt, style=S("TButton"), command=fn).grid(row=3 + n // 2, column=n % 2,
                                                                          sticky="we", padx=1, pady=(6 if n < 2 else 2, 0))
        right = ttk.Frame(parent, style=S("Page.TFrame"))
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)
        bar1 = ttk.Frame(right, style=S("Page.TFrame"))
        bar1.grid(row=0, column=0, sticky="we")
        self.style_var, self.font_var, self.size_var, self.space_var = (tk.StringVar() for _ in range(4))
        names = [lab for _k, lab in bf_edit.STYLES]
        cb = ttk.Combobox(bar1, textvariable=self.style_var, values=names, state="readonly", width=15, style=S("TCombobox"))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_style(dict((v, k) for k, v in bf_edit.STYLES)[self.style_var.get()]))
        self.font_cb = ttk.Combobox(bar1, textvariable=self.font_var, state="readonly", width=22, style=S("TCombobox"))
        self.font_cb.pack(side="left", padx=(6, 0))
        self.font_cb.bind("<<ComboboxSelected>>", lambda e: self.set_value("ff|", "" if self.font_var.get().startswith("(") else self.font_var.get()))
        sz = ttk.Combobox(bar1, textvariable=self.size_var, values=self.SIZES, state="readonly", width=8, style=S("TCombobox"))
        sz.pack(side="left", padx=(6, 0))
        sz.bind("<<ComboboxSelected>>", lambda e: self.set_value("fs|", "" if self.size_var.get().startswith("(") else self.size_var.get()))
        ttk.Label(bar1, text="  paragraph style, font, size", style=S("PageHint.TLabel")).pack(side="left", padx=(6, 0))
        barf = ttk.Frame(right, style=S("Page.TFrame"))
        barf.grid(row=1, column=0, sticky="we", pady=(4, 0))
        for txt, tip, fn in (("B", "Bold (Ctrl+B)", lambda: self.toggle("b")), ("I", "Italic (Ctrl+I)", lambda: self.toggle("i")),
                             ("U", "Underline (Ctrl+U)", lambda: self.toggle("u")), ("S", "Strikethrough", lambda: self.toggle("s")),
                             ("x\u00b2", "Superscript", lambda: self.toggle("sup")), ("x\u2082", "Subscript", lambda: self.toggle("sub")),
                             ("Colour", "Text colour", self.pick_color), ("Clear", "Clear character formatting", self.clear_format)):
            b = ttk.Button(barf, text=txt, style="Tool.TButton", command=fn)
            b.pack(side="left", padx=(0 if txt == "B" else 1, 0))
        ttk.Label(barf, text="  Align", style=S("PageHint.TLabel")).pack(side="left", padx=(8, 2))
        for txt, al in (("Left", "left"), ("Centre", "center"), ("Right", "right"), ("Justify", "justify"), ("Auto", "")):
            ttk.Button(barf, text=txt, style="Tool.TButton",
                       command=lambda a=al: self.set_line("al|", a)).pack(side="left", padx=1)
        bar2 = ttk.Frame(right, style=S("Page.TFrame"))
        bar2.grid(row=2, column=0, sticky="we", pady=(4, 4))
        ttk.Button(bar2, text="Indent \u2212", style="Tool.TButton", command=lambda: self.indent(-1)).pack(side="left", padx=(0, 1))
        ttk.Button(bar2, text="Indent +", style="Tool.TButton", command=lambda: self.indent(1)).pack(side="left", padx=1)
        ttk.Label(bar2, text="Space above", style=S("PageHint.TLabel")).pack(side="left", padx=(8, 2))
        sp = ttk.Combobox(bar2, textvariable=self.space_var, values=self.SPACES, state="readonly", width=4, style=S("TCombobox"))
        sp.pack(side="left")
        sp.bind("<<ComboboxSelected>>", lambda e: self.set_line("sp|", "" if self.space_var.get() == "0" else self.space_var.get()))
        for txt, fn in (("Undo", self.undo), ("Redo", self.redo), ("Find & replace", self.find_window),
                        ("Section break", self.insert_break), ("Line break", self.insert_linebreak)):
            ttk.Button(bar2, text=txt, style="Tool.TButton", command=fn).pack(side="left", padx=(8 if txt == "Undo" else 1, 0))
        box = ttk.Frame(right, style=S("Card.TFrame"))
        box.grid(row=3, column=0, sticky="nsew")
        self.txt = tk.Text(box, wrap="word", undo=False, padx=16, pady=12, spacing3=6, height=20)
        th.style_text(self.txt, app.k)
        vs = ttk.Scrollbar(box, command=self.txt.yview)
        self.txt.configure(yscrollcommand=vs.set)
        self.txt.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.status = ttk.Label(right, style=S("PageHint.TLabel"), text="Pick a source on the Source tab, then edit its chapters here.")
        self.status.grid(row=4, column=0, sticky="w", pady=(4, 0))
        bot = ttk.Frame(right, style=S("Page.TFrame"))
        bot.grid(row=5, column=0, sticky="we", pady=(6, 0))
        ttk.Button(bot, text="Preview this chapter", style=S("TButton"), command=self.preview_here).pack(side="left")
        ttk.Button(bot, text="Save project...", style=S("TButton"), command=app.save_project_dialog).pack(side="left", padx=6)
        ttk.Button(bot, text="Open project...", style=S("TButton"), command=app.open_project_dialog).pack(side="left")
        t = self.txt
        for seq, fn in (("<Control-b>", lambda: self.toggle("b")), ("<Control-i>", lambda: self.toggle("i")),
                        ("<Control-u>", lambda: self.toggle("u")), ("<Control-z>", self.undo), ("<Control-y>", self.redo),
                        ("<Control-f>", self.find_window), ("<Control-h>", self.find_window)):
            t.bind(seq, lambda e, fn=fn: (fn(), "break")[1])
        t.bind("<KeyPress>", self._keypress, add="+")
        t.bind("<KeyRelease>", lambda e: self._update_toolbar(), add="+")
        t.bind("<ButtonRelease-1>", lambda e: self._update_toolbar(), add="+")
        t.bind("<<Paste>>", lambda e: self._snap(force=True), add="+")
        muted = th.MUTED
        t.tag_configure("f_u", underline=True)
        t.tag_configure("f_s", overstrike=True)
        t.tag_configure("f_sup", offset=5)
        t.tag_configure("f_sub", offset=-3)
        t.tag_configure("st|quote", lmargin1=36, lmargin2=36, rmargin=36)
        t.tag_configure("st|item", lmargin1=18, lmargin2=34)
        t.tag_configure("st|verse", lmargin1=30, lmargin2=30)
        t.tag_configure("st|head", spacing1=12)
        t.tag_configure("st|subtitle", justify="center")
        t.tag_configure("st|anote", lmargin1=24, lmargin2=24, foreground=muted)
        t.tag_configure("st|scene", justify="center", foreground=muted)
        t.tag_configure("st|image", justify="center", foreground=muted)
        t.tag_configure("al|left", justify="left")
        t.tag_configure("al|center", justify="center")
        t.tag_configure("al|right", justify="right")
        t.tag_configure("al|justify", justify="left")
        for n in range(1, 9):
            t.tag_configure(f"in|{n}", lmargin1=24 * n, lmargin2=24 * n)
        for v in self.SPACES[1:]:
            t.tag_configure(f"sp|{v}", spacing1=int(v))
        for tg in ("al|left", "al|center", "al|right", "al|justify"):
            t.tag_raise(tg)
        import tkinter.font as tkfont
        self.families = {f.lower() for f in tkfont.families()}
        self.fallback = next((f for f in ("Georgia", "Times New Roman", "DejaVu Serif", "Liberation Serif")
                              if f.lower() in self.families), "TkDefaultFont")
        self.update_fonts(app.fonts if hasattr(app, "fonts") else [])

    # ------------------------------------------------------------ chapters
    def chapters(self):
        return self.app.book.chapters if self.app.book is not None else []

    def refresh_list(self):
        self.lst.delete(0, "end")
        for ch in self.chapters():
            self.lst.insert("end", ch.display() + ("" if ch.include else "   (left out)"))
        if self.cur is not None and self.cur < self.lst.size():
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(self.cur)
            self.lst.see(self.cur)

    def on_show(self):
        """The Edit tab was opened: show the book (it may have changed on other tabs)."""
        paths = []
        for root, _d, files in os.walk(bf_fonts.included_dir()):
            paths += [os.path.join(root, f) for f in files if f.lower().endswith((".ttf", ".otf"))]
        for c in self.app.custom_fonts:
            paths += [c[k] for k in ("R", "I", "B", "BI") if c.get(k)]
        if bf_edit.load_fonts_for_editor(paths):
            import tkinter.font as tkfont
            self.families = {f.lower() for f in tkfont.families()}
        chs = self.chapters()
        self.refresh_list()
        if not chs:
            return
        idx = next((i for i, c in enumerate(chs) if c is self.cur_obj), None)
        if idx is None:
            self.cur = None
            self.select(0)
        elif idx != self.cur:
            self.cur = idx
            self.refresh_list()

    def reset(self):
        """The book was replaced (scanned again, new book, project opened)."""
        self.cur, self.cur_obj = None, None
        self.undo_stack, self.redo_stack = [], []
        self.txt.delete("1.0", "end")
        self.refresh_list()
        if self.app.book is not None and th.TABS[self.app.cur_page][0] == "edit":
            self.select(0)

    def _picked(self):
        sel = self.lst.curselection()
        if sel and sel[0] != self.cur:
            self.select(sel[0])

    def select(self, i):
        if not self.chapters():
            return
        self.commit()
        i = max(0, min(i, len(self.chapters()) - 1))
        self.cur, self.cur_obj = i, self.chapters()[i]
        self.undo_stack, self.redo_stack = [], []
        self._load(bf_edit.blocks_to_paras(self.cur_obj.blocks))
        self.loading = True
        self.title_var.set(self.cur_obj.title)
        self.loading = False
        self.title_dirty = False
        self.refresh_list()
        self.txt.mark_set("insert", "1.0")
        self.txt.see("1.0")
        self._status()
        self._update_toolbar()

    def _title_changed(self):
        if self.loading or self.cur_obj is None:
            return
        self.cur_obj.title = self.title_var.get()
        self.title_dirty = True
        self.app.unsaved = True
        self.lst.delete(self.cur)
        self.lst.insert(self.cur, self.cur_obj.display() + ("" if self.cur_obj.include else "   (left out)"))
        self.lst.selection_set(self.cur)

    def add_chapter(self):
        if self.app.book is None:
            return
        self.commit()
        ch = Chapter(title="New chapter", blocks=[Block("para", text="Type the new chapter here.")])
        at = (self.cur + 1) if self.cur is not None else len(self.chapters())
        self.chapters().insert(at, ch)
        self._structure_changed()
        self.cur = None
        self.select(at)

    def delete_chapter(self):
        if self.cur_obj is None:
            return
        if not messagebox.askyesno("Delete chapter", f"Delete \u201c{self.cur_obj.display()}\u201d and all its text from "
                                                     "this book?\n\n(Your source file is not changed.)"):
            return
        i = self.cur
        del self.chapters()[i]
        self.cur, self.cur_obj = None, None
        self._structure_changed()
        if self.chapters():
            self.select(min(i, len(self.chapters()) - 1))
        else:
            self.txt.delete("1.0", "end")
            self.refresh_list()

    def move_chapter(self, d):
        if self.cur is None:
            return
        self.commit()
        chs, i, j = self.chapters(), self.cur, self.cur + d
        if 0 <= j < len(chs):
            chs[i], chs[j] = chs[j], chs[i]
            self.cur = j
            self._structure_changed()
            self.refresh_list()

    def _structure_changed(self):
        self.app.edited = True
        self.app.unsaved = True
        self.app.fill_list()

    # ------------------------------------------------------------ text box <-> paragraphs
    def _line_tags(self, p, n):
        tags = [f"st|{p.style}"]
        if p.align:
            tags.append(f"al|{p.align}")
        if p.indent:
            tags.append(f"in|{max(1, min(int(p.indent), 8))}")
        if p.space:
            tags.append(f"sp|{p.space}")
        if p.label:
            tags.append(f"lb|{p.label}")
        if p.style == "item":
            tags.append(f"bl|{p.bullet}|{p.depth}")
        if p.style == "verse":
            tags.append(f"vg|{p.group}")
        if p.style in ("image", "scene") and p.block is not None:
            self.images[n] = p.block
            tags.append(f"ob|{n}")
        return tags

    def _color_tag(self, color):
        tag = f"fc|{color}"
        try:
            self.txt.tag_configure(tag, foreground=color)
        except tk.TclError:
            pass
        return tag

    def _load(self, paras):
        self.loading = True
        t = self.txt
        t.delete("1.0", "end")
        self.images = {}
        for n, p in enumerate(paras):
            start = t.index("end-1c")
            for text, f in p.runs:
                tags = [f"f_{k}" for k in bf_edit.FLAGS if f.get(k)]
                if f.get("font"):
                    tags.append("ff|" + f["font"])
                if f.get("size"):
                    tags.append("fs|" + str(f["size"]))
                if f.get("color"):
                    tags.append(self._color_tag(f["color"]))
                t.insert("end", text, tuple(tags))
            t.insert("end", "\n")
            for tg in self._line_tags(p, n):
                t.tag_add(tg, start, "end-1c")
        self.refresh()
        t.edit_modified(False)
        self.dirty = False
        self.loading = False

    def _runs(self, s, e):
        t = self.txt
        cuts = {t.index(s), t.index(e)}
        for _kind, _val, idx in t.dump(s, e, tag=True):
            cuts.add(t.index(idx))
        cuts = sorted(cuts, key=lambda x: tuple(int(v) for v in x.split(".")))
        runs = []
        for a, b in zip(cuts, cuts[1:]):
            text = t.get(a, b)
            if not text:
                continue
            f = {}
            for tg in t.tag_names(a):
                if tg.startswith("f_") and tg[2:] in bf_edit.FLAGS:
                    f[tg[2:]] = True
                elif tg.startswith("ff|"):
                    f["font"] = tg[3:]
                elif tg.startswith("fs|"):
                    f["size"] = tg[3:]
                elif tg.startswith("fc|"):
                    f["color"] = tg[3:]
            runs.append((text, f))
        return bf_edit.merge(runs)

    def read(self):
        """The text box as editor paragraphs."""
        t, paras, used = self.txt, [], set()
        last = int(t.index("end-1c").split(".")[0])
        for ln in range(1, last + 1):
            s, e = f"{ln}.0", f"{ln}.end"
            text = t.get(s, e)
            tags = set(t.tag_names(e) if t.compare(e, "<", "end-1c") else t.tag_names(s))
            val = {tg.split("|", 1)[0]: tg.split("|", 1)[1] for tg in tags if "|" in tg and not tg.startswith(("ff|", "fs|", "fc|", "df|"))}
            style = val.get("st", "para")
            ob = val.get("ob")
            block = self.images.get(int(ob)) if ob is not None and ob.isdigit() else None
            if style in ("image", "scene"):
                if block is None or ob in used or (style == "image" and not text.startswith("[picture")):
                    style, block = "para", None             # a copy made by pressing Enter: ordinary text
                else:
                    used.add(ob)
            if not text and style not in ("scene",):
                continue
            bullet, depth = "", 0
            if "bl" in val:
                bullet, _, d = val["bl"].rpartition("|")
                depth = int(d) if d.isdigit() else 0
            paras.append(bf_edit.Para(style, self._runs(s, e), align=val.get("al", ""),
                                      indent=int(val.get("in", 0) or 0), space=int(val.get("sp", 0) or 0),
                                      label=val.get("lb", ""), bullet=bullet, depth=depth,
                                      group=val.get("vg"), block=block))
        return paras

    def commit(self):
        """Write the text box back into the book (only if something changed)."""
        if self.cur_obj is None or self.loading:
            return True
        changed = self.dirty or self.txt.edit_modified()
        if changed:
            try:
                self.cur_obj.blocks = bf_edit.paras_to_blocks(self.read())
            except Exception as e:
                messagebox.showerror("Edit", f"Your edits to this chapter couldn't be applied ({e}).\n\n"
                                             "They are still in the editor - nothing has been lost.")
                return False
            self.txt.edit_modified(False)
            self.dirty = False
        if changed or self.title_dirty:
            self.title_dirty = False
            self.app.edited = True
            self.app.unsaved = True
            self.app.fill_list()
        return True

    # ------------------------------------------------------------ display
    def update_fonts(self, names):
        vals = ["(default font)"] + [n for n in names if n not in (SAME_BODY, SAME_HEAD)]
        self.font_cb.configure(values=vals)

    def _tk_family(self, fam):
        fam = fam or self.app.var("font_family").get()
        fam = {"Times (built-in)": "Times New Roman", "Helvetica (built-in)": "Arial",
               "Courier (built-in)": "Courier New"}.get(fam, fam)
        return fam if fam.lower() in self.families else self.fallback

    def refresh(self, start="1.0", end="end"):
        t = self.txt
        for name in self.fontcache.values():
            t.tag_remove(name, start, end)
        cuts = {t.index(start), t.index(end)}
        for _k, _v, idx in t.dump(start, end, tag=True):
            cuts.add(t.index(idx))
        cuts = sorted(cuts, key=lambda x: tuple(int(v) for v in x.split(".")))
        for a, b in zip(cuts, cuts[1:]):
            tags = set(t.tag_names(a))
            style = next((x[3:] for x in tags if x.startswith("st|")), "para")
            fam = next((x[3:] for x in tags if x.startswith("ff|")), "")
            size = next((x[3:] for x in tags if x.startswith("fs|")), "")
            try:
                size = float(size) if size else self.STYLE_SIZE.get(style, 12)
            except ValueError:
                size = 12
            if "f_sup" in tags or "f_sub" in tags:
                size *= 0.7
            bold = "f_b" in tags or style == "head"
            italic = "f_i" in tags or style in ("subtitle", "anote", "image")
            key = (self._tk_family(fam), int(round(size)), bold, italic)
            if key not in self.fontcache:
                name = "df|%s|%d|%d|%d" % key
                t.tag_configure(name, font=(key[0], key[1], ("bold " if bold else "") + ("italic" if italic else "")))
                self.fontcache[key] = name
                t.tag_lower(name)
            t.tag_add(self.fontcache[key], a, b)

    def _status(self, msg=None):
        if msg:
            self.status.configure(text=msg)
            return
        if self.cur_obj is None:
            return
        words = len(self.txt.get("1.0", "end").split())
        self.status.configure(text=f"Chapter {self.cur + 1} of {len(self.chapters())}  \u00b7  {words:,} words  \u00b7  "
                                   "Fonts show in their printed shape in the preview")

    def _update_toolbar(self):
        t = self.txt
        tags = set(t.tag_names("insert-1c" if t.compare("insert", ">", "insert linestart") else "insert"))
        line = set(t.tag_names("insert lineend"))
        style = next((x[3:] for x in line if x.startswith("st|")), "para")
        self.style_var.set(bf_edit.STYLE_NAMES.get(style, "Normal text"))
        self.font_var.set(next((x[3:] for x in tags if x.startswith("ff|")), "(default font)"))
        self.size_var.set(next((x[3:] for x in tags if x.startswith("fs|")), "(default)"))
        self.space_var.set(next((x[3:] for x in line if x.startswith("sp|")), "0"))

    # ------------------------------------------------------------ undo / redo (covers formatting too)
    def _state(self):
        return (self.read(), self.txt.index("insert"))

    def _snap(self, force=False):
        import time
        now = time.time()
        if not force and now - self.last_snap < 1.2:
            self.last_snap = now
            return
        self.last_snap = now
        self.undo_stack.append(self._state())
        del self.undo_stack[:-100]
        self.redo_stack.clear()

    def _keypress(self, e):
        if e.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Left", "Right", "Up",
                        "Down", "Home", "End", "Prior", "Next"):
            return
        self._snap()

    def _restore(self, state):
        paras, ins = state
        self._load(paras)
        self.dirty = True
        self.txt.mark_set("insert", ins)
        self.txt.see(ins)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self._state())
            self._restore(self.undo_stack.pop())
            self.last_snap = 0

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self._state())
            self._restore(self.redo_stack.pop())
            self.last_snap = 0

    # ------------------------------------------------------------ formatting
    def _sel(self):
        try:
            return self.txt.index("sel.first"), self.txt.index("sel.last")
        except tk.TclError:
            self._status("Select some text first, then choose the formatting.")
            return None

    def _lines(self):
        try:
            a, b = self.txt.index("sel.first"), self.txt.index("sel.last")
        except tk.TclError:
            a = b = self.txt.index("insert")
        return range(int(a.split(".")[0]), int(b.split(".")[0]) + 1)

    def _after_format(self, a, b):
        self.dirty = True
        self.refresh(a, b)
        self.app.unsaved = True
        self._update_toolbar()

    def toggle(self, flag):
        r = self._sel()
        if not r:
            return
        self._snap(force=True)
        tag = f"f_{flag}"
        on = all(f.get(flag) for _t, f in self._runs(*r))
        (self.txt.tag_remove if on else self.txt.tag_add)(tag, *r)
        if flag in ("sup", "sub") and not on:
            self.txt.tag_remove("f_sub" if flag == "sup" else "f_sup", *r)
        self._after_format(*r)

    def set_value(self, prefix, value):
        r = self._sel()
        if not r:
            return
        self._snap(force=True)
        for tg in self.txt.tag_names():
            if tg.startswith(prefix):
                self.txt.tag_remove(tg, *r)
        if value:
            tag = self._color_tag(value) if prefix == "fc|" else prefix + value
            self.txt.tag_add(tag, *r)
        self._after_format(*r)

    def pick_color(self):
        from tkinter import colorchooser
        if not self._sel():
            return
        c = colorchooser.askcolor(title="Text colour", parent=self.txt)
        if c and c[1]:
            self.set_value("fc|", c[1].lower())

    def clear_format(self):
        r = self._sel()
        if not r:
            return
        self._snap(force=True)
        for tg in self.txt.tag_names():
            if tg.startswith(("f_", "ff|", "fs|", "fc|")):
                self.txt.tag_remove(tg, *r)
        self._after_format(*r)

    def set_line(self, prefix, value):
        lines = self._lines()
        self._snap(force=True)
        for ln in lines:
            a, b = f"{ln}.0", f"{ln}.end+1c"
            for tg in self.txt.tag_names():
                if tg.startswith(prefix):
                    self.txt.tag_remove(tg, a, b)
            if value:
                self.txt.tag_add(prefix + value, a, b)
        self._after_format(f"{lines[0]}.0", f"{lines[-1]}.end+1c")

    def set_style(self, style):
        if style == "image":
            self._status("Pictures come from your source file; they can be moved or deleted but not added here.")
            self._update_toolbar()
            return
        self.set_line("st|", style)
        if style == "item":
            for ln in self._lines():
                if not any(tg.startswith("bl|") for tg in self.txt.tag_names(f"{ln}.end")):
                    self.txt.tag_add("bl|\u2022|0", f"{ln}.0", f"{ln}.end+1c")

    def indent(self, d):
        cur = next((int(x[3:]) for x in self.txt.tag_names("insert lineend") if x.startswith("in|")), 0)
        n = max(0, min(cur + d, 8))
        self.set_line("in|", str(n) if n else "")

    def insert_break(self):
        self._snap(force=True)
        ln = int(self.txt.index("insert").split(".")[0])
        self.txt.insert(f"{ln}.end", "\n* * *")
        a, b = f"{ln + 1}.0", f"{ln + 1}.end+1c"
        for tg in self.txt.tag_names(a):
            self.txt.tag_remove(tg, a, b)
        self.txt.tag_add("st|scene", a, b)
        self._after_format(f"{ln}.0", b)

    def insert_linebreak(self):
        self._snap(force=True)
        self.txt.insert("insert", bf_edit.BR, self.txt.tag_names("insert-1c"))
        self._after_format("insert linestart", "insert lineend")

    # ------------------------------------------------------------ find & replace
    def find_window(self):
        w = tk.Toplevel(self.txt)
        w.title("Find & replace")
        w.configure(background=th.CARD)
        w.transient(self.txt.winfo_toplevel())
        fr = ttk.Frame(w, padding=12, style=self.app.S("Card.TFrame"))
        fr.pack(fill="both", expand=True)
        fv, rv, case = tk.StringVar(), tk.StringVar(), tk.BooleanVar(value=False)
        for r, (lab, var) in enumerate((("Find", fv), ("Replace with", rv))):
            ttk.Label(fr, text=lab, style=self.app.S("Card.TLabel")).grid(row=r, column=0, sticky="w", pady=2)
            e = ttk.Entry(fr, textvariable=var, width=36, style=self.app.S("TEntry"))
            e.grid(row=r, column=1, columnspan=3, sticky="we", pady=2)
            if r == 0:
                e.focus_set()
        ttk.Checkbutton(fr, text="Match capitals", variable=case, style=self.app.S("Card.TCheckbutton")).grid(
            row=2, column=1, sticky="w")
        msg = ttk.Label(fr, style=self.app.S("CardHint.TLabel"))
        msg.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        t = self.txt

        def find(start=None):
            pat = fv.get()
            if not pat:
                return None
            pos = t.search(pat, start or "insert", stopindex="end", nocase=not case.get())
            if not pos:
                pos = t.search(pat, "1.0", stopindex="end", nocase=not case.get())
            if not pos:
                msg.configure(text="Not found in this chapter.")
                return None
            end = f"{pos}+{len(pat)}c"
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", pos, end)
            t.mark_set("insert", end)
            t.see(pos)
            msg.configure(text="")
            return pos

        def replace():
            try:
                a, b = t.index("sel.first"), t.index("sel.last")
            except tk.TclError:
                find()
                return
            if t.get(a, b).lower() != fv.get().lower() and fv.get():
                find()
                return
            self._snap(force=True)
            tags = tuple(x for x in t.tag_names(a) if x != "sel")
            t.delete(a, b)
            t.insert(a, rv.get(), tags)
            self._after_format(f"{a} linestart", f"{a} lineend+1c")
            find()

        def replace_all():
            if not fv.get():
                return
            self._snap(force=True)
            n, pos = 0, "1.0"
            while True:
                pos = t.search(fv.get(), pos, stopindex="end", nocase=not case.get())
                if not pos:
                    break
                tags = tuple(x for x in t.tag_names(pos) if x != "sel")
                t.delete(pos, f"{pos}+{len(fv.get())}c")
                t.insert(pos, rv.get(), tags)
                pos = f"{pos}+{len(rv.get())}c"
                n += 1
            self._after_format("1.0", "end")
            msg.configure(text=f"Replaced {n} time(s) in this chapter.")
        for c, (lab, fn) in enumerate((("Find next", find), ("Replace", replace), ("Replace all", replace_all))):
            ttk.Button(fr, text=lab, style=self.app.S("TButton"), command=fn).grid(row=3, column=c + 1, sticky="we",
                                                                                  padx=1, pady=(8, 0))
        self.find_win = w
        self.find_funcs = (fv, rv, find, replace, replace_all)

    # ------------------------------------------------------------ preview link
    def preview_here(self):
        if self.cur_obj is None:
            return
        if not self.commit():
            return
        self.app._preview_target = id(self.cur_obj)
        self.app.preview_book()


class PreviewWindow:
    """Shows the preview: the book's pages and, when imposition is on, the printing sheets."""

    ZOOMS = ["Fit page", "Fit width", "Actual size"]

    def __init__(self, app, result):
        self.app, self.result, self.docs, self.i, self.mode = app, None, {}, 0, "pages"
        self.w = w = tk.Toplevel(app)
        w.title("Preview")
        w.geometry("1000x920")
        w.configure(background=th.PAPER)
        w.protocol("WM_DELETE_WINDOW", self.close)
        top = ttk.Frame(w, padding=(10, 8, 10, 2), style="Paper.TFrame")
        top.pack(fill="x")
        self.modes = ttk.Frame(top, style="Paper.TFrame")
        self.modes.pack(side="left")
        self.zoom = tk.StringVar(value=self.ZOOMS[0])
        z = ttk.Combobox(top, textvariable=self.zoom, values=self.ZOOMS, state="readonly", width=11,
                         style=app.S("TCombobox"))
        z.pack(side="right")
        z.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(top, text="Zoom", style="Paper.TLabel").pack(side="right", padx=(0, 6))
        navrow = ttk.Frame(w, padding=(10, 2, 10, 8), style="Paper.TFrame")
        navrow.pack(fill="x")
        nav = ttk.Frame(navrow, style="Paper.TFrame")
        nav.pack()
        for txt, fn in (("\u23EE", lambda: self.go(0)), ("\u25C0  Previous", lambda: self.go(self.i - 1))):
            ttk.Button(nav, text=txt, style="Header.TButton", command=fn).pack(side="left", padx=2)
        self.page_var = tk.StringVar()
        ent = ttk.Entry(nav, textvariable=self.page_var, width=5, justify="center", style=app.S("TEntry"))
        ent.pack(side="left", padx=(8, 4))
        ent.bind("<Return>", lambda e: self._jump())
        self.of = ttk.Label(nav, style="Paper.TLabel")
        self.of.pack(side="left", padx=(0, 8))
        for txt, fn in (("Next  \u25B6", lambda: self.go(self.i + 1)), ("\u23ED", lambda: self.go(len(self.items) - 1))):
            ttk.Button(nav, text=txt, style="Header.TButton", command=fn).pack(side="left", padx=2)
        bot = ttk.Frame(w, padding=(10, 8), style="Paper.TFrame")
        bot.pack(side="bottom", fill="x")
        self.info = ttk.Label(bot, style="PaperHint.TLabel", wraplength=520, justify="left")
        self.info.pack(side="left", fill="x", expand=True)
        ttk.Button(bot, text="Generate printing files  \u25B6", style="Build.TButton",
                   command=self.generate).pack(side="right")
        ttk.Button(bot, text="\u21BB  Update preview", style="Header.TButton",
                   command=app.preview_book).pack(side="right", padx=8, ipady=5)
        ttk.Button(bot, text="\u25C0  Back to settings", style="Header.TButton",
                   command=self.close).pack(side="right", ipady=5)
        ttk.Button(bot, text="\u270E  Edit this chapter", style="Header.TButton",
                   command=self.edit_here).pack(side="right", padx=(0, 8), ipady=5)
        body = tk.Frame(w, background=th.PAPER)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background=th.TROUGH, highlightthickness=0)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())
        # Windows sends wheel steps of 120, macOS small steps (1, 2, 3...); Linux (X11) sends Button-4/5 instead.
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            int(-e.delta / 120) or (-1 if e.delta > 0 else 1 if e.delta < 0 else 0), "units"))
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        for key, d in (("<Left>", -1), ("<Right>", 1), ("<Prior>", -1), ("<Next>", 1)):
            w.bind(key, lambda e, d=d: self.go(self.i + d))
        w.bind("<Home>", lambda e: self.go(0))
        w.bind("<End>", lambda e: self.go(len(self.items) - 1))
        self.load(result)

    # ---- data
    def alive(self):
        try:
            return bool(self.w.winfo_exists())
        except tk.TclError:
            return False

    def _doc(self, path):
        import pypdfium2 as pdfium
        if path not in self.docs:
            self.docs[path] = pdfium.PdfDocument(path)
        return self.docs[path]

    def _release(self):
        for d in self.docs.values():
            try:
                d.close()
            except Exception:
                pass
        self.docs = {}
        if self.result:
            shutil.rmtree(self.result["dir"], ignore_errors=True)

    def load(self, result):
        keep = self.i
        self._release()
        self.result = result
        self.pages = [(result["pdf"], k, f"page {k + 1} of the book") for k in range(len(self._doc(result["pdf"])))]
        self.sheets = []
        for f in result["sheets"]:
            n = len(self._doc(f))
            for k in range(n):
                if result["duplex"]:
                    lab = f"sheet {k // 2 + 1}, {'first' if k % 2 == 0 else 'second'} side"
                else:
                    lab = f"sheet {k + 1}, {'front (print first)' if 'fronts' in f else 'back (print second)'}"
                self.sheets.append((f, k, lab))
        if not self.sheets:
            self.mode = "pages"
        self._mode_buttons()
        import time
        self.info.configure(text=f"\u201c{result['title']}\u201d typeset with your current settings at "
                                 f"{time.strftime('%H:%M')} \u2014 exactly as the printing files will be. "
                                 "Nothing has been saved yet." +
                                 (" Printing sheets show how pages are arranged and folded." if self.sheets else ""))
        self.i = min(keep, len(self.items) - 1)
        self.w.title(f"Preview \u2014 {result['title']}")
        self.w.lift()
        self.render()

    @property
    def items(self):
        return self.sheets if self.mode == "sheets" else self.pages

    def _mode_buttons(self):
        for c in self.modes.winfo_children():
            c.destroy()
        if not self.sheets:
            ttk.Label(self.modes, text=f"Book pages ({len(self.pages)})", style="Paper.TLabel",
                      font=("Segoe UI Semibold", 11)).pack(side="left")
            return
        for key, txt in (("pages", f"Book pages ({len(self.pages)})"),
                         ("sheets", f"Printing sheets ({len(self.sheets)} sides)")):
            ttk.Button(self.modes, text=("\u25CF  " if self.mode == key else "") + txt, style="Header.TButton",
                       command=lambda k=key: self.set_mode(k)).pack(side="left", padx=(0, 6))

    def set_mode(self, m):
        self.mode, self.i = m, 0
        self._mode_buttons()
        self.render()

    # ---- drawing
    def go(self, i):
        if self.items:
            self.i = max(0, min(i, len(self.items) - 1))
            self.render()

    def _jump(self):
        try:
            self.go(int(self.page_var.get()) - 1)
        except ValueError:
            self.render()

    def render(self):
        if not self.alive() or not self.items:
            return
        from PIL import ImageTk
        try:
            # Pillow finds Tk through this module on macOS and Linux. Importing it here also makes
            # PyInstaller bundle it; without it the packaged app's preview window stays empty.
            from PIL import _tkinter_finder  # noqa: F401
        except ImportError:
            pass
        path, idx, label = self.items[self.i]
        c = self.canvas
        try:
            page = self._doc(path)[idx]
            pw, ph = page.get_size()
            rotation = page.get_rotation()
            if rotation in (90, 270):
                pw, ph = ph, pw
            cw, ch = max(200, self.canvas.winfo_width() - 30), max(200, self.canvas.winfo_height() - 30)
            z = self.zoom.get()
            k = min(cw / pw, ch / ph) if z == "Fit page" else (cw / pw if z == "Fit width" else 96 / 72)
            img = page.render(scale=k, may_draw_forms=False).to_pil()
            self.photo = ImageTk.PhotoImage(img)
        except Exception as e:
            # Say so in the window instead of leaving it blank (details go to last_error.txt).
            try:
                with open(os.path.join(app_dir(), "last_error.txt"), "w", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
            except Exception:
                pass
            c.delete("all")
            c.create_text(20, 20, anchor="nw", width=max(300, c.winfo_width() - 40), fill=th.INK,
                          font=("Segoe UI", 11),
                          text=f"This page couldn't be drawn in the preview ({type(e).__name__}: {e}).\n\n"
                               "The printing files are not affected. Details were saved to last_error.txt in "
                               + app_dir())
            self.page_var.set(str(self.i + 1))
            self.of.configure(text=f"of {len(self.items)}   —   {label}")
            return
        c.delete("all")
        x = max(15, (c.winfo_width() - img.width) // 2)
        c.create_rectangle(x + 4, 19, x + img.width + 4, 19 + img.height, fill="#000000", outline="", stipple="gray25")
        c.create_image(x, 15, anchor="nw", image=self.photo)
        c.configure(scrollregion=(0, 0, max(c.winfo_width(), img.width + 30), img.height + 30))
        self.page_var.set(str(self.i + 1))
        self.of.configure(text=f"of {len(self.items)}   \u2014   {label}")

    # ---- buttons
    def chapter_at_page(self):
        """Id of the chapter shown on the current page (the last chapter starting on or before it)."""
        page = self.i + 1 if self.mode == "pages" else 1
        starts = sorted((pg, cid) for cid, pg in self.result.get("chapter_pages", []) if pg)
        cid = None
        for pg, c in starts:
            if pg <= page:
                cid = c
        return cid if cid is not None else (starts[0][1] if starts else None)

    def edit_here(self):
        cid = self.chapter_at_page()
        self.close()
        self.app.edit_chapter(cid)

    def generate(self):
        self.close()
        self.app.build()

    def close(self):
        self._release()
        try:
            self.w.destroy()
        except tk.TclError:
            pass
        if getattr(self.app, "preview_win", None) is self:
            self.app.preview_win = None


def app_dir():
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION} (build {BUILD_DATE}) \u2014 one-click book maker by {APP_AUTHOR}")
        self.geometry("1100x800")
        self.minsize(900, 560)
        try:
            self.iconbitmap(resource("bookforge.ico"))
        except Exception:
            try:                      # macOS / Linux: Tk can't use .ico files directly
                from PIL import Image, ImageTk
                self._icon = ImageTk.PhotoImage(Image.open(resource("bookforge.ico")))
                self.iconphoto(True, self._icon)
            except Exception:
                pass
        if sys.platform == "darwin":
            # Quit from the macOS menu / Cmd+Q / Dock goes through the same "save your edits?" check
            self.createcommand("tk::mac::Quit", self.on_close)
        self.dark = self._saved_dark()
        th.set_mode(self.dark)
        th.apply(self)
        self.k = "src"
        self.vars, self.texts = {}, {}
        self.book, self.book_sig, self.busy, self.mode = None, None, False, ""
        self.edited = False
        self.unsaved = False          # edits not yet saved in a project file
        self._preview_target = None   # chapter to show when the next preview opens
        self.autofilled = {}          # title/author values BookForge filled in itself from a source
        self.q = queue.Queue()
        self.custom_fonts = []
        self.font_combos = []
        self.fonts = bf_fonts.list_families(installed=False)
        self._menu()
        self._ui()
        self.load_settings(os.path.join(app_dir(), "settings.json"), quiet=True, skip_book=True)
        bf_fonts.set_user_fonts_dir(self.var("fonts_dir").get())
        self.var("dark_mode").set(self.dark)
        self._mode_changed()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll_id = self.after(120, self.poll)
        threading.Thread(target=lambda: self.q.put(("fonts", bf_fonts.scan_installed())), daemon=True).start()

    # ------------------------------------------------------------ helpers
    def var(self, key):
        if key not in self.vars:
            d = DEFAULTS[key]
            if isinstance(d, bool):
                v = tk.BooleanVar(value=d)
            elif isinstance(d, int):
                v = tk.IntVar(value=d)
            elif isinstance(d, float):
                v = tk.DoubleVar(value=d)
            else:
                v = tk.StringVar(value=d)
            self.vars[key] = v
        return self.vars[key]

    def S(self, name):
        return f"{self.k}.{name}"

    def lab(self, p, r, text, c=0):
        ttk.Label(p, text=text, style=self.S("Card.TLabel")).grid(row=r, column=c, sticky="w",
                                                                 padx=6, pady=3)

    def combo(self, p, r, text, key, values, width=30, cmd=None):
        self.lab(p, r, text)
        cb = ttk.Combobox(p, textvariable=self.var(key), values=list(values), state="readonly",
                          width=width, style=self.S("TCombobox"))
        cb.grid(row=r, column=1, sticky="we", padx=6, pady=3)
        if cmd:
            cb.bind("<<ComboboxSelected>>", cmd)
        return cb

    def spin(self, p, r, text, key, lo, hi, inc, hint=""):
        self.lab(p, r, text)
        f = ttk.Frame(p, style=self.S("Card.TFrame"))
        f.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        ttk.Spinbox(f, textvariable=self.var(key), from_=lo, to=hi, increment=inc,
                    width=8, style=self.S("TSpinbox")).pack(side="left")
        if hint:
            ttk.Label(f, text=hint, style=self.S("CardHint.TLabel")).pack(side="left", padx=6)

    def entry(self, p, r, text, key, width=40):
        self.lab(p, r, text)
        e = ttk.Entry(p, textvariable=self.var(key), width=width, style=self.S("TEntry"))
        e.grid(row=r, column=1, sticky="we", padx=6, pady=3)
        return e

    def check(self, p, r, text, key, c=0, span=2):
        ttk.Checkbutton(p, text=text, variable=self.var(key), style=self.S("Card.TCheckbutton")).grid(
            row=r, column=c, columnspan=span, sticky="w", padx=6, pady=2)

    def textbox(self, p, key, height=4, width=50):
        f = ttk.Frame(p, style=self.S("Card.TFrame"))
        t = tk.Text(f, height=height, width=width, wrap="word", font=("Segoe UI", 10),
                    undo=True, padx=6, pady=4)
        th.style_text(t, self.k)
        sb = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.texts[key] = t
        return f

    def group(self, parent, text, **grid):
        g = ttk.LabelFrame(parent, text=text, padding=10, style=self.S("TLabelframe"))
        g.grid(**grid, sticky="nsew", padx=6, pady=5)
        g.columnconfigure(1, weight=1)
        return g

    # ------------------------------------------------------------ layout
    def _menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="New book", command=self.new_book)
        f.add_command(label="Open project...", command=self.open_project_dialog)
        f.add_command(label="Save project...", command=self.save_project_dialog, accelerator="Ctrl+S")
        self.bind_all("<Control-s>", lambda e: self.save_project_dialog())
        f.add_command(label="Open source file...", command=self.browse_source)
        f.add_separator()
        f.add_command(label="Save settings as preset...", command=self.save_preset)
        f.add_command(label="Load preset...", command=self.load_preset)
        f.add_command(label="Reset all settings to defaults", command=self.reset)
        f.add_command(label="Settings & storage...", command=self.settings_window)
        f.add_separator()
        f.add_command(label="Exit", command=self.on_close)
        m.add_cascade(label="File", menu=f)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="How to use, print and bind", command=self.show_help)
        h.add_command(label="Fonts & licences", command=self.licences_window)
        h.add_command(label="About", command=self.about_window)
        m.add_cascade(label="Help", menu=h)
        self.config(menu=m)

    def _saved_dark(self):
        try:
            with open(os.path.join(app_dir(), "settings.json"), encoding="utf-8") as f:
                return bool(json.load(f).get("dark_mode", DEFAULTS["dark_mode"]))
        except Exception:
            return bool(DEFAULTS["dark_mode"])

    def _ui(self):
        bar = ttk.Frame(self, padding=(14, 6, 14, 12), style="Paper.TFrame")
        bar.pack(side="bottom", fill="x")
        head = ttk.Frame(self, padding=(14, 10, 14, 4), style="Paper.TFrame")
        head.pack(side="top", fill="x")
        ttk.Label(head, text=APP_NAME, style="Brand.TLabel").pack(side="left")
        ttk.Label(head, text=f"by {APP_AUTHOR}", style="Maker.TLabel").pack(side="left", padx=(10, 0),
                                                                          pady=(7, 0))
        ttk.Button(head, text="\u2699  Settings & storage", style="Header.TButton",
                   command=self.settings_window).pack(side="right")
        self.dark_btn = ttk.Button(head, style="Header.TButton", command=self.toggle_dark,
                                   text="\u2600  Light mode" if self.dark else "\u263E  Dark mode")
        self.dark_btn.pack(side="right", padx=(0, 8))
        self.shelf = th.Shelf(self, self.show_tab)
        self.shelf.pack(side="top", fill="x", padx=14)
        holder = tk.Frame(self, background=th.PAPER)
        holder.pack(side="top", fill="both", expand=True, padx=14)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.pages = []
        builders = (self._tab_source, self._tab_chapters, self._tab_edit, self._tab_info, self._tab_layout, self._tab_front,
                    self._tab_output)
        for (key, _label, _c), build in zip(th.TABS, builders):
            self.k = key
            page = th.ScrollPage(holder, key)
            page.grid(row=0, column=0, sticky="nsew")
            fr = page.inner
            fr.columnconfigure(0, weight=1)
            fr.columnconfigure(1, weight=1)
            build(fr)
            self.pages.append(page)
        self.bind_all("<MouseWheel>", self._wheel)
        # Linux (X11) reports the mouse wheel as buttons 4 and 5
        self.bind_all("<Button-4>", lambda e: self._wheel(e, 120))
        self.bind_all("<Button-5>", lambda e: self._wheel(e, -120))
        self.k = "src"
        for i in range(len(th.TABS)):
            self.bind_all(f"<Control-Key-{i + 1}>", lambda e, i=i: self.shelf.select(i))
        self.bind_all("<Control-Tab>", lambda e: self.shelf.select((self.shelf.current + 1) % len(th.TABS)))
        self.show_tab(0)

        self.preview_btn = ttk.Button(bar, text="Preview book", style="Header.TButton",
                                      command=self.preview_book)
        self.preview_btn.pack(side="left", pady=(8, 0), padx=(0, 8), ipady=5)
        self.build_btn = ttk.Button(bar, text="\u25B6  Generate printing files", style="Build.TButton",
                                    command=self.build)
        self.build_btn.pack(side="left", pady=(8, 0))
        right = ttk.Frame(bar, style="Paper.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(8, 0))
        self.status = ttk.Label(right, text="Ready. Pick a source, check the chapters, then click Preview book.",
                                style="Paper.TLabel")
        self.status.pack(anchor="w")
        self.prog = ttk.Progressbar(right, mode="indeterminate", style="Build.Horizontal.TProgressbar")
        self.prog.pack(fill="x", pady=(4, 4))
        self.logbox = tk.Text(right, height=3, font=("Consolas", 9), state="disabled", relief="flat",
                              background=th.P["LOG"], foreground=th.MUTED, highlightthickness=0,
                              padx=6, pady=3)
        self.logbox.pack(fill="x")

    def show_tab(self, i):
        prev = getattr(self, "cur_page", None)
        if prev is not None and prev != i and th.TABS[prev][0] == "edit":
            self._commit_editor()
        self.cur_page = i
        self.pages[i].tkraise()
        if th.TABS[i][0] in ("chap", "edit") and not self.busy:
            self.after(50, self.auto_scan)
        if th.TABS[i][0] == "edit" and getattr(self, "editor", None) is not None:
            self.editor.on_show()

    def _wheel(self, e, delta=None):
        w = e.widget
        if isinstance(w, (tk.Text, tk.Listbox, ttk.Treeview)) or str(w).endswith("popdown.f.l"):
            return
        try:
            if w.winfo_toplevel() is not self:
                return            # wheel over another window (e.g. the preview), not over the settings pages
        except (AttributeError, tk.TclError):
            pass
        self.pages[getattr(self, "cur_page", 0)].wheel(e.delta if delta is None else delta)

    def _tab_source(self, t):
        t.rowconfigure(1, weight=1)
        g = self.group(t, "Make a book from...", row=0, column=0, columnspan=2)
        ttk.Radiobutton(g, text="A file (EPUB, TXT, Markdown, HTML, Word .docx)", value="file",
                        variable=self.var("source_mode"), command=self._mode_changed,
                        style=self.S("Card.TRadiobutton")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=6)
        self.src_entry = ttk.Entry(g, textvariable=self.var("source_path"), style=self.S("TEntry"))
        self.src_entry.grid(row=1, column=0, columnspan=2, sticky="we", padx=6, pady=3)
        self.src_btn = ttk.Button(g, text="Browse...", command=self.browse_source, style=self.S("TButton"))
        self.src_btn.grid(row=1, column=2, padx=6)
        g.columnconfigure(0, weight=1)
        ttk.Radiobutton(g, text="Text I paste or type below", value="paste",
                        variable=self.var("source_mode"), command=self._mode_changed,
                        style=self.S("Card.TRadiobutton")).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))

        t.rowconfigure(1, weight=1)
        pg = ttk.LabelFrame(t, text="Paste or type text  (mark chapters with \"Chapter 1\" lines "
                                    "or # headings)", padding=8, style=self.S("TLabelframe"))
        pg.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=5)
        self.paste_frame = self.textbox(pg, "paste_text", height=8)
        self.paste_frame.pack(fill="both", expand=True)

        d = self.group(t, "Cleaning up the source", row=2, column=0, columnspan=2)
        d.columnconfigure(1, weight=1)
        checks = [("Remove Gutenberg / Standard Ebooks / AO3 boilerplate", "strip_gutenberg"),
                  ("Skip the source's own contents list", "skip_contents"),
                  ("Skip cover-image page", "skip_cover"),
                  ("Include pictures from the source", "include_images"),
                  ("Keep text before the first chapter", "keep_front_text"),
                  ("Drop empty chapters", "drop_empty"),
                  ("Keep line breaks inside paragraphs (poetry)", "preserve_breaks")]
        for i, (txt, key) in enumerate(checks):
            self.check(d, i % 4, txt, key, c=i // 4, span=1)

        sb = self.group(t, "Section breaks", row=3, column=0, columnspan=2)
        self.entry(sb, 0, "Markers this text uses", "scene_markers", 50)
        ttk.Label(sb, text="Comma-separated. Any paragraph that is just one of these becomes a centred "
                           "section break.", style=self.S("CardHint.TLabel")).grid(row=1, column=1, sticky="w",
                                                                                 padx=6)
        self.check(sb, 2, "Also treat lines made only of symbols (~~~, ***, \u2022\u2022\u2022) as section breaks",
                   "scene_symbols")
        nxt = ttk.Frame(t, style=self.S("Page.TFrame"))
        nxt.grid(row=4, column=0, columnspan=2, sticky="e", padx=6, pady=(4, 8))
        ttk.Button(nxt, text="Next: check the chapters  \u2192", style=self.S("TButton"),
                   command=lambda: self.shelf.select(1)).pack(side="right")

    # ------------------------------------------------------------ Chapters step
    SPLIT_LABELS = [
        ("Auto", "Find them automatically (recommended)"),
        ("Chapter / Part lines", "Lines that start with Chapter, Part, Prologue..."),
        ("Markdown # headings", "Lines that start with # (Markdown)"),
        ("ALL-CAPS lines", "Short lines written in CAPITAL LETTERS"),
        ("Heading level 1", "Headings in the file - biggest size (level 1)"),
        ("Heading level 2", "Headings in the file - level 2"),
        ("Heading level 3", "Headings in the file - level 3"),
        ("Custom pattern", "My own pattern (advanced)"),
        ("No chapters", "Don't split - the whole text is one chapter"),
    ]

    def _tab_chapters(self, t):
        t.rowconfigure(2, weight=1)
        t.columnconfigure(0, weight=3)
        t.columnconfigure(1, weight=2)
        how = self.group(t, "How are chapters marked in your text?", row=0, column=0, columnspan=2)
        how.columnconfigure(1, weight=1)
        labels = [lab for _v, lab in self.SPLIT_LABELS]
        self.split_disp = tk.StringVar()
        cb = ttk.Combobox(how, textvariable=self.split_disp, values=labels, state="readonly", width=46,
                          style=self.S("TCombobox"))
        cb.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        cb.bind("<<ComboboxSelected>>", self._split_chosen)
        self.var("split_mode").trace_add("write", lambda *a: self._show_split())
        self._show_split()
        ttk.Button(how, text="Find chapters again", command=self.scan,
                   style=self.S("TButton")).grid(row=0, column=1, sticky="w", padx=6)
        self.entry(how, 1, "My own pattern", "custom_regex", 30)
        ttk.Label(how, text="only used with \"My own pattern\"  (e.g.  ^Part \\d+)",
                  style=self.S("CardHint.TLabel")).grid(row=2, column=1, sticky="w", padx=6)
        self.combo(how, 3, "In text files, a new paragraph starts at", "line_paragraphs",
                   ["Auto", "Blank line between paragraphs", "Each line is a paragraph"], width=30)

        self.chap_summary = ttk.Label(t, text="No chapters yet - pick a source on the Source tab.",
                                      style=self.S("PageHint.TLabel"), font=("Segoe UI Semibold", 11),
                                      wraplength=900, justify="left")
        self.chap_summary.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2))

        lst = ttk.LabelFrame(t, text="Chapters in the order they will be printed", padding=8,
                             style=self.S("TLabelframe"))
        lst.grid(row=2, column=0, sticky="nsew", padx=6, pady=5)
        lst.rowconfigure(1, weight=1)
        lst.columnconfigure(0, weight=1)
        ttk.Label(lst, text="Click a chapter to see how it starts. Double-click a title to rename it. "
                            "Click the tick to leave a chapter out.", style=self.S("CardHint.TLabel"),
                  wraplength=520).grid(row=0, column=0, sticky="w", pady=(0, 4))
        tf = ttk.Frame(lst, style=self.S("Card.TFrame"))
        tf.grid(row=1, column=0, sticky="nsew")
        cols = ("print", "num", "title", "starts", "words")
        self.ctree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended", height=14)
        for c, head, w, anchor, stretch in (("print", "Print", 52, "center", False), ("num", "#", 46, "center", False),
                                            ("title", "Chapter title", 260, "w", True),
                                            ("starts", "Starts with...", 230, "w", True),
                                            ("words", "Words", 70, "e", False)):
            self.ctree.heading(c, text=head)
            self.ctree.column(c, width=w, anchor=anchor, stretch=stretch)
        self.ctree.tag_configure("skipped", foreground="#9AA3AD")
        vs = ttk.Scrollbar(tf, command=self.ctree.yview)
        self.ctree.configure(yscrollcommand=vs.set)
        self.ctree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.ctree.bind("<<TreeviewSelect>>", lambda e: self.show_preview())
        self.ctree.bind("<Double-Button-1>", self._tree_double)
        self.ctree.bind("<Button-1>", self._tree_click, add="+")
        bot = ttk.Frame(lst, style=self.S("Card.TFrame"))
        bot.grid(row=2, column=0, sticky="we", pady=(6, 0))
        for n, (txt, fn) in enumerate((("Rename", self.rename_ch), ("Skip / include", self.toggle_ch),
                                       ("Move up", lambda: self.move_ch(-1)), ("Move down", lambda: self.move_ch(1)),
                                       ("Merge into previous", self.merge_ch),
                                       ("Undo all changes", self.reset_chapters))):
            ttk.Button(bot, text=txt, command=fn, style=self.S("TButton")).grid(row=n // 3, column=n % 3,
                                                                              sticky="we", padx=2, pady=2)
        for c in range(3):
            bot.columnconfigure(c, weight=1)

        pv = ttk.LabelFrame(t, text="How the selected chapter starts", padding=8, style=self.S("TLabelframe"))
        pv.grid(row=2, column=1, sticky="nsew", padx=6, pady=5)
        pv.rowconfigure(0, weight=1)
        pv.columnconfigure(0, weight=1)
        self.preview = tk.Text(pv, wrap="word", height=14, width=40, font=("Georgia", 10), padx=8, pady=6)
        th.style_text(self.preview, self.k)
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.tag_configure("found", font=("Segoe UI Semibold", 10),
                                   foreground="#7CC4C9" if self.dark else "#2F6B71")
        self.preview.tag_configure("note", foreground=th.MUTED, font=("Georgia", 9, "italic"))
        self.preview.configure(state="disabled")
        ttk.Label(pv, text="Wrong split? Select the chapter that shouldn't exist and click \"Merge into "
                           "previous\". Missing chapters? Change \"How are chapters marked\" above.",
                  style=self.S("CardHint.TLabel"), wraplength=280).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _tab_edit(self, t):
        t.rowconfigure(0, weight=1)
        t.columnconfigure(0, weight=1)
        holder = ttk.Frame(t, style=self.S("Page.TFrame"))
        holder.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.editor = BookEditor(self, holder)

    def edit_tab(self):
        return [k for k, _l, _c in th.TABS].index("edit")

    def _commit_editor(self):
        ed = getattr(self, "editor", None)
        return ed.commit() if ed is not None else True

    def edit_chapter(self, cid):
        """Open the Edit step at the chapter with this id (from the preview's Edit this chapter)."""
        if self.book is None:
            return
        idx = next((i for i, c in enumerate(self.book.chapters) if id(c) == cid), 0)
        self.shelf.select(self.edit_tab())
        self.editor.select(idx)

    def save_project_dialog(self):
        if not self._commit_editor():
            return False
        if self.book is None:
            messagebox.showinfo("Save project", "There's no book to save yet - pick a source first.")
            return False
        base = re.sub(r'[\\/:*?"<>|]+', " ", self.book.title or "My book").strip() or "My book"
        p = filedialog.asksaveasfilename(title="Save project", defaultextension=".bookforge", initialfile=base + ".bookforge",
                                         filetypes=[("BookForge project", "*.bookforge")])
        if not p:
            return False
        try:
            bf_edit.save_project(p, self.book, self.collect(), APP_VERSION)
        except Exception as e:
            messagebox.showerror("Save project", f"The project couldn't be saved ({e}).\n\nYour edits are still open "
                                                 "in BookForge - try saving somewhere else.")
            return False
        self.unsaved = False
        self.status.configure(text=f"Project saved: {os.path.basename(p)}")
        return True

    def open_project_dialog(self):
        if self.busy:
            return
        self._commit_editor()
        if getattr(self, "unsaved", False) and not messagebox.askyesno(
                "Open project", "Open another project? Unsaved edits to the current book will be lost."):
            return
        p = filedialog.askopenfilename(title="Open project", filetypes=[("BookForge project", "*.bookforge"),
                                                                        ("All files", "*.*")])
        if not p:
            return
        try:
            book, settings = bf_edit.load_project(p)
        except ValueError as e:
            messagebox.showerror("Open project", f"That project can't be opened: {e}.")
            return
        settings.pop("dark_mode", None)
        self.apply(settings)
        self._mode_changed()
        self.book, self.edited, self.unsaved = book, True, False
        self.book_sig = self.source_sig(self.collect())
        self.fill_list()
        self.editor.reset()
        self.shelf.select(self.edit_tab())
        self.status.configure(text=f"Opened project {os.path.basename(p)} - {len(book.chapters)} chapters.")

    def _tab_info(self, t):
        g = self.group(t, "Title page details (leave blank to use the source's own)", row=0, column=0,
                       columnspan=2)
        self.entry(g, 0, "Title", "title", 60)
        self.entry(g, 1, "Subtitle", "subtitle", 60)
        self.entry(g, 2, "Author line", "author", 60)
        self.entry(g, 3, "Extra credit line", "credit", 60)
        ttk.Label(g, text='e.g. "Translated by Edgar Taylor"  or  "Illustrated by ..."',
                  style=self.S("CardHint.TLabel")).grid(row=4, column=1, sticky="w", padx=6)
        d = self.group(t, "Dedication page (optional)", row=1, column=0, columnspan=2)
        self.textbox(d, "dedication", height=3).grid(row=0, column=0, columnspan=2, sticky="nsew")
        d.columnconfigure(0, weight=1)
        n = self.group(t, "Extra front page: introduction, about the author, notes... (optional)",
                       row=2, column=0, columnspan=2)
        self.entry(n, 0, "Heading", "note_title", 50)
        self.combo(n, 1, "Place it", "note_place", ["After contents", "Before contents"])
        self.textbox(n, "note_text", height=7).grid(row=2, column=0, columnspan=2, sticky="nsew", pady=4)
        t.rowconfigure(2, weight=1)

    def _tab_layout(self, t):
        g = self.group(t, "Page & margins (inches)", row=0, column=0)
        self.combo(g, 0, "Page size", "page_size", list(PAGE_SIZES))
        self.spin(g, 1, "Custom width", "custom_w", 2, 17, 0.25, "used when size = Custom")
        self.spin(g, 2, "Custom height", "custom_h", 2, 17, 0.25)
        self.spin(g, 3, "Top margin", "margin_top", 0.2, 3, 0.05)
        self.spin(g, 4, "Bottom margin", "margin_bottom", 0.2, 3, 0.05)
        self.spin(g, 5, "Inside (spine) margin", "margin_inner", 0.2, 3, 0.05, "extra room for glue")
        self.spin(g, 6, "Outside margin", "margin_outer", 0.2, 3, 0.05)

        f = self.group(t, "Text", row=1, column=0)
        self.font_combos = [
            (self.combo(f, 0, "Body text font", "font_family", self.fonts), "body"),
            (self.combo(f, 1, "Titles & headings font", "heading_font", [SAME_BODY] + self.fonts), "head"),
            (self.combo(f, 2, "Drop cap font", "dropcap_font", [SAME_HEAD, SAME_BODY] + self.fonts), "drop")]
        fb = ttk.Frame(f, style=self.S("Card.TFrame"))
        fb.grid(row=3, column=1, sticky="w", padx=6, pady=(0, 4))
        ttk.Button(fb, text="My fonts...", command=self.font_manager, style=self.S("TButton")).pack(side="left")
        self.font_count = ttk.Label(f, text="Looking for fonts...", style=self.S("CardHint.TLabel"))
        self.font_count.grid(row=12, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(fb, text="use any font files, e.g. Medium + Medium Italic", style=self.S("CardHint.TLabel")).pack(
            side="left", padx=6)
        self.check(f, 4, "Bold titles and headings", "heading_bold")
        self.spin(f, 5, "Body size (pt)", "body_size", 6, 30, 0.5)
        self.spin(f, 6, "Line spacing", "line_spacing", 1.0, 2.5, 0.05, "x font size")
        self.combo(f, 7, "Alignment", "align", ["Justified", "Left"])
        self.spin(f, 8, "Paragraph indent (in)", "indent", 0, 1.5, 0.05)
        self.spin(f, 9, "Space between paragraphs (pt)", "para_space", 0, 24, 1)
        self.check(f, 10, "Indent the first paragraph of each chapter", "first_para_indent")
        self.combo(f, 11, "Poems / verse", "verse_style", ["Centered italic", "Indented"])

        h = self.group(t, "Hyphenation & line breaks", row=2, column=0)
        self.combo(h, 0, "Hyphenate words", "hyph_lang", list(HYPH_LANGS))
        self.spin(h, 1, "Shortest word to hyphenate", "hyph_min", 3, 15, 1, "letters")
        self.check(h, 2, "Avoid a single short word alone on a paragraph's last line", "avoid_runts")
        ttk.Label(h, text="Your hyphenation dictionary  (one word per line; hyphens show where it may break, "
                          "e.g. Ka-la-din.  A word with no hyphens is never split.)",
                  style=self.S("CardHint.TLabel"), wraplength=420).grid(row=3, column=0, columnspan=2, sticky="w",
                                                                         padx=6, pady=(6, 2))
        self.textbox(h, "hyph_words", height=4, width=40).grid(row=4, column=0, columnspan=2, sticky="nsew",
                                                                padx=6)

        c = self.group(t, "Chapters", row=0, column=1)
        self.combo(c, 0, "Each chapter starts on", "chapter_start",
                   ["New page", "Right-hand page", "Continuous"])
        self.combo(c, 1, "Chapter number line", "chapter_label",
                   ["None", "Chapter 1", "Chapter One", "CHAPTER I", "1", "I"])
        self.combo(c, 2, "Chapter title case", "title_case", ["As written", "Title Case", "UPPERCASE"])
        self.spin(c, 3, "Chapter title size (pt)", "title_size", 10, 60, 1)
        self.spin(c, 4, "Sub-heading size (pt)", "sub_size", 8, 40, 0.5)
        self.spin(c, 5, "Drop chapter start down (in)", "chapter_sink", 0, 4, 0.25)
        self.check(c, 6, "Ornament under chapter titles", "ornament")
        self.check(c, 7, "Drop cap (large first letter) in each chapter", "drop_cap")
        self.spin(c, 8, "Drop cap height (lines)", "drop_cap_lines", 2, 5, 1)
        self.combo(c, 9, "Chapter opens with a quote", "drop_cap_quote",
                   ["Hang the quote in the margin", "Quote at text size before the letter",
                    "Make the quote big too", "No drop cap when a chapter opens with a quote"])
        self.combo(c, 10, "Section breaks print as", "scene_break",
                   ["Keep the source's own", "* * *", "*", "~ ~ ~", "# # #", "Blank space"])

        n = self.group(t, "Page numbers & headers", row=1, column=1)
        self.combo(n, 0, "Position", "pn_position",
                   ["Bottom center", "Bottom outside", "Top outside", "None"])
        self.combo(n, 1, "Style", "pn_style", ["Rule above", "Plain", "Dashes"])
        self.combo(n, 2, "Numbering", "pn_mode",
                   ["Every page (title page = 1)", "Start at 1 on first chapter",
                    "Roman front matter, 1 on first chapter"])
        self.check(n, 3, "Hide number on chapter opening pages", "pn_hide_openers")
        self.check(n, 4, "Hide number on blank pages", "pn_hide_blank")
        self.check(n, 5, "Hide number on the title page", "pn_hide_title")
        self.check(n, 6, "Running headers (book title / chapter title)", "running_heads")

    def _tab_front(self, t):
        g = self.group(t, "Front of the book", row=0, column=0)
        self.check(g, 0, "Title page", "title_page")
        self.combo(g, 1, "\"Belongs to\" bookplate", "bookplate", ["On title page", "Separate page", "None"])
        self.entry(g, 2, "Bookplate wording", "bookplate_text", 34)
        c = self.group(t, "Contents page", row=1, column=0)
        self.check(c, 0, "Make a contents page with page numbers", "toc")
        self.entry(c, 1, "Contents heading", "toc_title", 34)
        self.combo(c, 2, "Numbers in front of titles", "toc_numbers", ["None", "Number (1.)", "Chapter N:"])
        self.combo(c, 3, "Contents title case", "toc_case", ["As written", "Title Case", "UPPERCASE"])
        self.check(c, 4, "Dot leaders ( ........ 12 )", "toc_dots")
        ff = self.group(t, "Fanfiction downloads (AO3, FanFicFare)", row=2, column=0, columnspan=2)
        self.combo(ff, 0, "Work info (rating, fandom, tags...)", "fic_info", ["Leave out", "Add a work info page"])
        self.combo(ff, 1, "Story summary", "fic_summary", ["Add a summary page", "Leave out"])
        self.combo(ff, 2, "Author's notes", "an_mode",
                   ["Set apart (smaller, indented)", "Keep as written", "Leave out"])
        ttk.Label(ff, text="Also removes AO3's \"Please drop by the Archive and comment\" line. "
                           "Ordinary books aren't affected.", style=self.S("CardHint.TLabel")).grid(
            row=3, column=1, sticky="w", padx=6)
        b = self.group(t, "Back of the book", row=0, column=1)
        self.check(b, 0, "Print \"THE END\" after the last chapter", "the_end")
        self.spin(b, 1, "Lined \"Notes\" pages at the end", "notes_pages", 0, 20, 1)
        ttk.Label(t, text="Dedication and the extra front page are on the Book info tab.",
                  style=self.S("PageHint.TLabel")).grid(row=1, column=1, sticky="nw", padx=12, pady=12)

    def _tab_output(self, t):
        g = self.group(t, "Save to", row=0, column=0, columnspan=2)
        e = ttk.Entry(g, textvariable=self.var("out_dir"), style=self.S("TEntry"))
        e.grid(row=0, column=0, sticky="we", padx=6)
        g.columnconfigure(0, weight=1)
        ttk.Button(g, text="Browse...", command=self.browse_out, style=self.S("TButton")).grid(
            row=0, column=1, padx=6)
        ttk.Label(g, text=f"Blank = {default_out_dir()}  (a folder per book is made inside)",
                  style=self.S("CardHint.TLabel")).grid(row=1, column=0, sticky="w", padx=6)
        self.check(g, 2, "Open the folder when finished", "open_when_done")
        f = self.group(t, "Formats to make", row=1, column=0)
        self.check(f, 0, "Print-ready PDF (pages in reading order)", "fmt_pdf")
        self.check(f, 1, "Imposed PDF for binding (pages arranged on sheets to fold)", "fmt_impose")
        self.check(f, 2, "Wraparound cover template PDF (front, spine, back)", "fmt_cover")
        self.check(f, 3, "EPUB e-book", "fmt_epub")
        self.check(f, 4, "Word document (.docx, editable)", "fmt_docx")
        self.check(f, 5, "Web page (.html)", "fmt_html")
        self.check(f, 6, "Plain text (.txt)", "fmt_txt")
        b = self.group(t, "Binding layout", row=2, column=0)
        self.combo(b, 0, "Page layout", "imp_layout", LAYOUT_NAMES, width=34)
        self.combo(b, 1, "Signature format", "sig_format", SIG_FORMATS, width=34)
        self.spin(b, 2, "Sheets per signature", "sig_sheets", 1, 40, 1, "standard signatures")
        self.entry(b, 3, "Custom signature sizes", "sig_custom", 24)
        ttk.Label(b, text="sheets per signature, e.g. 4, 4, 6, 6", style=self.S("CardHint.TLabel")).grid(
            row=4, column=1, sticky="w", padx=6)
        self.spin(b, 5, "Flyleafs (blank leaves each end)", "flyleafs", 0, 10, 1)
        self.entry(b, 6, "Page range", "imp_range", 24)
        ttk.Label(b, text="blank = all pages; e.g. 1-8, 10, 12-", style=self.S("CardHint.TLabel")).grid(
            row=7, column=1, sticky="w", padx=6)
        self.combo(b, 8, "Rotate source pages", "imp_source_rot", list(SOURCE_ROT), width=34)
        self.combo(b, 9, "Files to make", "imp_files", ["Aggregated file only",
                                                         "Both aggregated & per-signature files",
                                                         "Signature files only"], width=34)
        pr = self.group(t, "Printer & paper", row=2, column=1)
        self.combo(pr, 0, "Paper size", "sheet_size", list(SHEETS))
        self.spin(pr, 1, "Custom width", "sheet_w", 1, 2000, 0.25)
        self.spin(pr, 2, "Custom height", "sheet_h", 1, 2000, 0.25)
        self.combo(pr, 3, "Custom size unit", "sheet_unit", list(UNITS))
        self.combo(pr, 4, "Printer", "printer_type", ["Duplex (two-sided printer)",
                                                       "Single-sided (fronts and backs files)",
                                                       "Single-sided, backs in reverse order"])
        self.check(pr, 5, "Rotate paper 90\u00b0", "rotate_paper")
        self.check(pr, 6, "Rotate back sides 180\u00b0 (flip on the other edge)", "rotate_back")
        pl = self.group(t, "Page placement", row=3, column=0)
        self.combo(pl, 0, "Page scaling", "imp_scaling", ["Keep proportional", "Stretch to fit", "Original size"])
        self.combo(pl, 1, "Page position", "imp_position", ["Centered", "Snug against binding edge"])
        self.spin(pl, 2, "Fore-edge margin (pt)", "imp_fore", 0, 200, 1, "72 pt = 1 inch")
        self.spin(pl, 3, "Binding margin (pt)", "imp_binding", 0, 200, 1)
        self.spin(pl, 4, "Top margin (pt)", "imp_top", 0, 200, 1)
        self.spin(pl, 5, "Bottom margin (pt)", "imp_bottom", 0, 200, 1)
        self.combo(pl, 6, "Small layouts: spacing", "wacky_spacing", ["Packed", "Distributed space"])
        self.spin(pl, 7, "Small layouts: fore-edge padding (pt)", "wacky_fore", 0, 72, 1)
        mk = self.group(t, "Marks", row=3, column=1)
        self.check(mk, 0, "Fold lines", "fold_marks")
        self.combo(mk, 9, "Fold lines printed on", "fold_side", FOLD_SIDES, width=30)
        ttk.Label(mk, text="Inside = the side you see while folding (as bookbinder-js does)",
                  style=self.S("CardHint.TLabel")).grid(row=10, column=0, columnspan=2, sticky="w", padx=6)
        self.check(mk, 1, "Cut lines / crop marks", "cut_marks")
        self.check(mk, 2, "Page edge marks at the spine", "edge_marks")
        self.check(mk, 3, "Signature order marks on the spine", "sig_marks")
        self.check(mk, 4, "Sewing marks", "sewing_marks")
        self.combo(mk, 5, "Sewing marks on", "sewing_where", SEWING_WHERE, width=30)
        self.spin(mk, 6, "Distance from ends (pt)", "sewing_margin", 0, 300, 1, "kettle stitch")
        self.spin(mk, 7, "Sewing stations", "sewing_count", 0, 12, 1)
        self.spin(mk, 8, "Tape width (pt)", "sewing_tape", 0, 144, 1, "0 = single holes")
        c = self.group(t, "Cover", row=1, column=1)
        self.combo(c, 0, "Paper (sets spine width)", "paper", list(PAPERS))
        ttk.Label(c, text="Back cover text (optional):", style=self.S("Card.TLabel")).grid(row=1, column=0, columnspan=2,
                                                             sticky="w", padx=6)
        self.textbox(c, "blurb", height=8, width=40).grid(row=2, column=0, columnspan=2,
                                                          sticky="nsew", padx=6)
        c.rowconfigure(2, weight=1)

    # ------------------------------------------------------------ settings
    def collect(self):
        s = {}
        for k, d in DEFAULTS.items():
            if isinstance(d, list):
                continue
            try:
                v = self.var(k).get()
                s[k] = type(d)(v) if not isinstance(d, bool) else bool(v)
            except (tk.TclError, ValueError):
                s[k] = d
        for k in TEXT_KEYS:
            if k in self.texts:
                s[k] = self.texts[k].get("1.0", "end-1c")
        s["custom_fonts"] = [dict(c) for c in self.custom_fonts]
        return s

    def apply(self, data):
        data = bf_fonts.migrate(dict(data))
        if "custom_fonts" in data:
            self.custom_fonts = [dict(c) for c in data.get("custom_fonts") or []]
            self.refresh_fonts()
        for k, v in data.items():
            if k in self.texts:
                self.texts[k].delete("1.0", "end")
                self.texts[k].insert("1.0", v or "")
            elif k in DEFAULTS and not isinstance(DEFAULTS[k], list):
                try:
                    self.var(k).set(v)
                except tk.TclError:
                    pass

    def save_settings(self, path, keep_book=False):
        data = self.collect()
        if not keep_book:
            for k in BOOK_KEYS:
                data.pop(k, None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)

    def load_settings(self, path, quiet=False, skip_book=False):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if skip_book:                     # settings files from v1.4 and older still contain them
                for k in BOOK_KEYS:
                    data.pop(k, None)
            self.apply(data)
        except Exception as e:
            if not quiet:
                messagebox.showerror("Couldn't load", str(e))

    def save_preset(self):
        p = filedialog.asksaveasfilename(title="Save preset", defaultextension=".json",
                                         initialdir=app_dir(), filetypes=[("BookForge preset", "*.json")])
        if p:
            data = self.collect()
            for k in ("source_path", "paste_text", "title", "subtitle", "author", "credit"):
                data.pop(k, None)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)

    def load_preset(self):
        p = filedialog.askopenfilename(title="Load preset", initialdir=app_dir(),
                                       filetypes=[("BookForge preset", "*.json")])
        if p:
            self.load_settings(p)

    def reset(self):
        if messagebox.askyesno("Reset", "Put every setting back to its default?"):
            self.apply(DEFAULTS)
            for k in ("dedication", "note_text", "blurb", "hyph_words"):
                self.texts[k].delete("1.0", "end")

    # ------------------------------------------------------------ light / dark
    def toggle_dark(self):
        """Rebuild the window in the other palette, keeping everything the user has entered."""
        if self.busy:
            return
        if getattr(self, "preview_win", None) is not None:
            self.preview_win.close()
        self._commit_editor()
        editing = getattr(getattr(self, "editor", None), "cur_obj", None)
        state = self.collect()
        tab = self.shelf.current
        sel = self._sel()
        self.dark = not self.dark
        self.var("dark_mode").set(self.dark)
        th.set_mode(self.dark)
        for w in list(self.children.values()):
            w.destroy()
        th.apply(self)
        self.font_combos = []
        self._menu()
        self._ui()
        self.apply(state)
        self._mode_changed()
        self.refresh_fonts()
        if self.book:
            self.fill_list()
            for i in sel:
                if self.ctree.exists(str(i)):
                    self.ctree.selection_add(str(i))
        self.editor.cur_obj = editing
        self.shelf.select(tab)
        try:
            self.save_settings(os.path.join(app_dir(), "settings.json"))
        except Exception:
            pass

    # ------------------------------------------------------------ settings & storage
    def _open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)
        except Exception:
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                messagebox.showinfo("Folder", path)

    def settings_window(self):
        w = tk.Toplevel(self)
        w.title("Settings & storage")
        w.configure(background=th.CARD)
        w.transient(self)
        fr = ttk.Frame(w, padding=16, style=self.S("Card.TFrame"))
        fr.pack(fill="both", expand=True)
        fr.columnconfigure(1, weight=1)

        def head(r, text):
            ttk.Label(fr, text=text, style=self.S("Card.TLabel"), font=("Segoe UI Semibold", 11)).grid(
                row=r, column=0, columnspan=3, sticky="w", pady=(12 if r else 0, 4))

        def hint(r, text):
            ttk.Label(fr, text=text, style=self.S("CardHint.TLabel"), wraplength=560, justify="left").grid(
                row=r, column=0, columnspan=3, sticky="w")

        head(0, "Appearance")
        ttk.Button(fr, text="Switch to light mode" if self.dark else "Switch to dark mode",
                   style=self.S("TButton"), command=lambda: (w.destroy(), self.toggle_dark())).grid(
            row=1, column=0, sticky="w")

        head(2, "Where BookForge keeps its own files")
        ad = app_dir()
        ttk.Entry(fr, width=60, style=self.S("TEntry")).grid(row=3, column=0, columnspan=2, sticky="we")
        fr.grid_slaves(row=3, column=0)[0].insert(0, ad)
        ttk.Button(fr, text="Open", style=self.S("TButton"), command=lambda: self._open_folder(ad)).grid(
            row=3, column=2, padx=(6, 0))
        hint(4, "Your remembered settings (settings.json), the font list cache, fonts prepared for printing "
                "(fontcache) and the last error report. Deleting this folder is safe: BookForge starts fresh "
                "with default settings.")

        def clear(what):
            if not messagebox.askyesno("Clear", f"Delete BookForge's {what}?", parent=w):
                return
            import shutil
            if what == "remembered settings":
                try:
                    os.remove(os.path.join(ad, "settings.json"))
                except OSError:
                    pass
                self._no_save = True
            else:
                shutil.rmtree(os.path.join(ad, "fontcache"), ignore_errors=True)
                try:
                    os.remove(os.path.join(ad, "font_cache.json"))
                except OSError:
                    pass
            messagebox.showinfo("Clear", f"Done. The {what} were deleted.", parent=w)
        b = ttk.Frame(fr, style=self.S("Card.TFrame"))
        b.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(b, text="Clear remembered settings", style=self.S("TButton"),
                   command=lambda: clear("remembered settings")).pack(side="left")
        ttk.Button(b, text="Clear prepared fonts", style=self.S("TButton"),
                   command=lambda: clear("prepared fonts")).pack(side="left", padx=6)

        head(6, "Your fonts folder")
        fv = tk.StringVar(value=self.var("fonts_dir").get() or bf_fonts.default_user_fonts_dir())
        ttk.Entry(fr, textvariable=fv, width=60, style=self.S("TEntry")).grid(row=7, column=0, columnspan=2,
                                                                             sticky="we")

        def choose():
            p = filedialog.askdirectory(parent=w, title="Choose a folder for your fonts",
                                        initialdir=fv.get() if os.path.isdir(fv.get()) else os.path.expanduser("~"))
            if p:
                fv.set(p)
                self.var("fonts_dir").set(p)
                bf_fonts.set_user_fonts_dir(p)
                threading.Thread(target=lambda: self.q.put(("fonts", bf_fonts.scan_installed(force=True))),
                                 daemon=True).start()
        ttk.Button(fr, text="Change...", style=self.S("TButton"), command=choose).grid(row=7, column=2, padx=(6, 0))
        ttk.Button(fr, text="Open fonts folder", style=self.S("TButton"),
                   command=lambda: self._open_folder(fv.get())).grid(row=8, column=0, sticky="w", pady=(4, 0))
        hint(9, "Put any .ttf / .otf / .ttc font files in this folder and they appear in every font list "
                "(after restarting BookForge, or after choosing the folder here). Fonts installed in Windows "
                "work too, and \"My fonts...\" on the Layout tab builds a family from any font files.")

        head(10, "Fonts")
        counts = ttk.Label(fr, style=self.S("CardHint.TLabel"), wraplength=560, justify="left")
        counts.grid(row=11, column=0, columnspan=3, sticky="w")

        def show_counts():
            inst = bf_fonts._FAMILIES
            counts.configure(text=f"Included with BookForge (SIL Open Font License 1.1, licences ship with the "
                                  f"program): {len(bf_fonts.included_families())} families.   Installed on this PC "
                                  f"or in your fonts folder: " +
                                  (f"{len(inst)} families." if inst is not None else "still looking..."))
        show_counts()

        def rescan():
            counts.configure(text="Looking for fonts...")

            def work():
                self.q.put(("fonts", bf_fonts.scan_installed(force=True)))
            threading.Thread(target=work, daemon=True).start()
            w.after(1500, show_counts)

        def report():
            r = tk.Toplevel(w)
            r.title("Font report")
            txt = tk.Text(r, wrap="word", width=100, height=22, font=("Consolas", 9), padx=10, pady=8)
            th.style_text(txt, self.k)
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", f"{APP_NAME} {APP_VERSION} (build {BUILD_DATE})\n" + bf_fonts.font_report())
        b2 = ttk.Frame(fr, style=self.S("Card.TFrame"))
        b2.grid(row=12, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(b2, text="Rescan fonts", style=self.S("TButton"), command=rescan).pack(side="left")
        ttk.Button(b2, text="Font report...", style=self.S("TButton"), command=report).pack(side="left", padx=6)
        ttk.Button(b2, text="Fonts & licences...", style=self.S("TButton"), command=self.licences_window).pack(
            side="left")
        ttk.Button(fr, text="Close", style=self.S("TButton"), command=w.destroy).grid(row=13, column=2, sticky="e",
                                                                                     pady=(14, 0))

    def licences_window(self):
        w = tk.Toplevel(self)
        w.title("Fonts & licences")
        w.geometry("860x600")
        w.configure(background=th.PAPER)
        w.transient(self)
        left = ttk.Frame(w, padding=10, style="Paper.TFrame")
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Included fonts", style="Paper.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        lb = tk.Listbox(left, width=24, font=("Segoe UI", 10), activestyle="none", exportselection=False)
        th.style_text(lb, self.k)
        lb.pack(fill="y", expand=True, pady=6)
        names = bf_fonts.included_families()
        for n in names:
            lb.insert("end", n)
        lb.insert("end", "\u2014 not included \u2014")
        txt = tk.Text(w, wrap="word", font=("Consolas", 9), padx=12, pady=10)
        th.style_text(txt, self.k)
        txt.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)

        def show(_e=None):
            sel = lb.curselection()
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            if sel and sel[0] < len(names):
                n = names[sel[0]]
                lic = bf_fonts.licence_text(n)
                folder = bf_fonts.INCLUDED[n][0]
                txt.insert("end", f"{n}  -  fonts/{folder}/OFL.txt\n\n")
                txt.insert("end", lic if lic else "Licence file missing from this copy of BookForge.")
            else:
                txt.insert("end", "These fonts are commercial or come with Windows / Microsoft Office, so they can't "
                                  "be shipped with BookForge:\n\n  " + "\n  ".join(bf_fonts.NOT_INCLUDED) +
                                  "\n\nIf they are installed on your PC (or put in your fonts folder) they appear in "
                                  "the font lists automatically.")
            txt.configure(state="disabled")
        lb.bind("<<ListboxSelect>>", show)
        lb.selection_set(0)
        show()

    def about_window(self):
        w = tk.Toplevel(self)
        w.title(f"About {APP_NAME}")
        w.configure(background=th.CARD)
        w.transient(self)
        fr = ttk.Frame(w, padding=18, style=self.S("Card.TFrame"))
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=f"{APP_NAME} {APP_VERSION}  (build {BUILD_DATE})", style=self.S("Card.TLabel"),
                  font=("Georgia", 15, "bold")).pack(anchor="w")
        ttk.Label(fr, text=f"Made by {APP_AUTHOR}.  Free and open source (MIT License).\n\n"
                           "Turns EPUBs, text and Word files into print-ready books with page numbers, contents, "
                           "imposition and covers.\n\n"
                           f"Includes {len(bf_fonts.included_families())} font families licensed under the SIL "
                           "Open Font License 1.1 (original files from Google Fonts). Each font's licence ships "
                           "with the program.\n\nBookForge's own files are kept in:\n" + app_dir(),
                  style=self.S("Card.TLabel"), wraplength=460, justify="left").pack(anchor="w", pady=(8, 12))
        b = ttk.Frame(fr, style=self.S("Card.TFrame"))
        b.pack(fill="x")
        ttk.Button(b, text="Fonts & licences...", style=self.S("TButton"), command=self.licences_window).pack(side="left")
        ttk.Button(b, text="Open that folder", style=self.S("TButton"),
                   command=lambda: self._open_folder(app_dir())).pack(side="left", padx=6)
        ttk.Button(b, text="Close", style=self.S("TButton"), command=w.destroy).pack(side="right")

    def new_book(self):
        """Clear everything that belongs to the current book; keep layout, fonts and output settings."""
        if self.busy:
            return
        if self.edited and not messagebox.askyesno(
                "New book", "Start a new book? Your chapter changes for the current book will be lost."):
            return
        for k in BOOK_KEYS:
            if k in self.texts:
                was = str(self.texts[k].cget("state"))
                self.texts[k].configure(state="normal")
                self.texts[k].delete("1.0", "end")
                self.texts[k].configure(state=was)
            else:
                self.var(k).set("")
        self.book, self.book_sig, self.edited, self.autofilled = None, None, False, {}
        self.unsaved = False
        self.editor.reset()
        self.ctree.delete(*self.ctree.get_children())
        self.show_preview()
        self.chap_summary.configure(text="No chapters yet - pick a source on the Source tab.")
        self.var("source_mode").set("file")
        self._mode_changed()
        self.shelf.select(0)
        self.status.configure(text="New book. Pick a source, check the chapters, then click Preview book.")

    def on_close(self):
        if getattr(self, "unsaved", False) and self.book is not None and not getattr(self, "_closing", False):
            self._commit_editor()
            ans = messagebox.askyesnocancel(
                "Save your edits?", "You've edited this book. Save your edits as a BookForge project before closing?\n\n"
                                    "Yes = save   No = close without saving   Cancel = keep working")
            if ans is None or (ans and not self.save_project_dialog()):
                return
        if getattr(self, "preview_win", None) is not None:
            self.preview_win.close()
        try:
            if not getattr(self, "_no_save", False):
                self.save_settings(os.path.join(app_dir(), "settings.json"))
        except Exception:
            pass
        try:
            self.after_cancel(self._poll_id)
        except Exception:
            pass
        self.destroy()

    # ------------------------------------------------------------ actions
    def _mode_changed(self):
        paste = self.var("source_mode").get() == "paste"
        self.src_entry.configure(state="disabled" if paste else "normal")
        self.src_btn.configure(state="disabled" if paste else "normal")
        self.texts["paste_text"].configure(state="normal" if paste else "disabled",
                                           background=th.CARD if paste else th.P["FIELD_OFF"])

    def refresh_fonts(self, installed=None):
        names = bf_fonts.list_families(self.custom_fonts, installed=False)
        inst = installed if installed is not None else (bf_fonts._FAMILIES or {})
        n_inc = len(bf_fonts.included_families())
        try:
            if n_inc == 0:
                self.font_count.configure(text="No included fonts were found in this copy of BookForge - see "
                                               "Settings & storage > Font report.", foreground="#E07A6F")
            else:
                scanned = installed is not None or bf_fonts._FAMILIES is not None
                self.font_count.configure(
                    text=f"{n_inc} fonts included with BookForge + " +
                         (f"{len(inst)} installed on this PC" if scanned else "looking for installed fonts..."),
                    foreground=th.MUTED)
        except (AttributeError, tk.TclError):
            pass
        seen = set(names)
        names += sorted((f for f in inst if f not in seen), key=str.lower)
        self.fonts = names
        display = [n for n in bf_fonts.included_families() if bf_fonts.INCLUDED[n][3] == "display"]
        for cb, role in self.font_combos:
            extra = {"body": [], "head": [SAME_BODY] + display, "drop": [SAME_HEAD, SAME_BODY] + display}[role]
            cb.configure(values=extra + [n for n in names if n not in extra])
        if getattr(self, "editor", None) is not None:
            self.editor.update_fonts(names)

    def add_custom_family(self, entry):
        """Check and add a "My fonts" family. Returns a plain error message, or None when it worked."""
        for k in ("R", "I", "B", "BI"):
            if entry.get(k):
                _fam, _sty, problem = bf_fonts.font_file_info(entry[k])
                if problem:
                    return f"The {dict(R='Regular', I='Italic', B='Bold', BI='Bold Italic')[k]} file can't be used: {problem}."
        try:
            bf_fonts.register_family(entry["name"], {k: (entry[k], 0) for k in ("R", "I", "B", "BI") if entry.get(k)})
        except Exception as e:
            return f"That font can't be used ({type(e).__name__}: {e})."
        self.custom_fonts = [c for c in self.custom_fonts if c["name"] != entry["name"]] + [dict(entry)]
        self.refresh_fonts()
        return None

    def font_manager(self):
        w = tk.Toplevel(self)
        w.title("My fonts")
        w.configure(background=th.CARD)
        w.transient(self)
        w.grab_set()
        fr = ttk.Frame(w, padding=14, style=self.S("Card.TFrame"))
        fr.pack(fill="both", expand=True)
        fr.columnconfigure(1, weight=1)
        ttk.Label(fr, text="Make a font family from any font files (.ttf, .otf, .ttc, .woff). Choose one file and "
                           "BookForge fills in the family's other styles from the same folder. Only Regular is "
                           "required.\nTip: to use Medium weights, pick Medium as Regular and Medium Italic as "
                           "Italic.\n\nIncluded with BookForge (free licence): " +
                           ", ".join(bf_fonts.included_families()) + ".\nCommercial fonts can't be included: " +
                           ", ".join(bf_fonts.NOT_INCLUDED) + " appear in the font lists automatically once "
                           "installed on this PC (several come with Windows or Microsoft Office).",
                  style=self.S("Card.TLabel"), justify="left", wraplength=560).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        lb = tk.Listbox(fr, height=5, font=("Segoe UI", 10), activestyle="none")
        th.style_text(lb, self.k)
        lb.grid(row=1, column=0, columnspan=3, sticky="nsew")
        vals = {k: tk.StringVar() for k in ("name", "R", "I", "B", "BI")}

        def fill():
            lb.delete(0, "end")
            for c in self.custom_fonts:
                n = sum(1 for k in ("R", "I", "B", "BI") if c.get(k))
                lb.insert("end", f"{c['name']}   ({n} style{'s' if n != 1 else ''})")

        def pick(key):
            p = filedialog.askopenfilename(parent=w, title="Choose a font file", filetypes=[
                ("Font files", "*.ttf *.otf *.ttc *.otc *.woff *.woff2"), ("All files", "*.*")])
            if not p:
                return
            fam, sty, problem = bf_fonts.font_file_info(p)
            if problem:
                messagebox.showerror("My fonts", f"That file can't be used: {problem}.", parent=w)
                return
            names = {"R": "Regular", "I": "Italic", "B": "Bold", "BI": "Bold Italic"}
            if sty != key and not messagebox.askyesno(
                    "My fonts", f"This file is the {names.get(sty, sty)} style of \"{fam}\", but you chose it "
                                f"for {names[key]}. Use it for {names[key]} anyway?", parent=w):
                return
            vals[key].set(p)
            if not vals["name"].get().strip():
                vals["name"].set(fam)
            try:                                  # fill in the family's other styles from the same folder
                _f, found = bf_fonts.family_from_file(p)
            except ValueError:
                found = {}
            for k, fp in found.items():
                if k != key and not vals[k].get().strip():
                    vals[k].set(fp)

        def on_select(_e=None):
            sel = lb.curselection()
            if sel:
                c = self.custom_fonts[sel[0]]
                for k in vals:
                    vals[k].set(c.get(k, ""))

        lb.bind("<<ListboxSelect>>", on_select)
        rows = (("name", "Family name"), ("R", "Regular"), ("I", "Italic"), ("B", "Bold"), ("BI", "Bold italic"))
        for r, (key, label) in enumerate(rows, start=2):
            ttk.Label(fr, text=label, style=self.S("Card.TLabel")).grid(row=r, column=0, sticky="w", padx=(0, 8),
                                                                       pady=3)
            ttk.Entry(fr, textvariable=vals[key], width=52, style=self.S("TEntry")).grid(row=r, column=1, sticky="we",
                                                                                       pady=3)
            if key != "name":
                ttk.Button(fr, text="Browse...", command=lambda k=key: pick(k), style=self.S("TButton")).grid(
                    row=r, column=2, padx=(6, 0))

        def save():
            name = vals["name"].get().strip()
            if not name or not vals["R"].get().strip():
                messagebox.showwarning("My fonts", "Give the family a name and choose at least the Regular file.",
                                       parent=w)
                return
            entry = {"name": name}
            for k in ("R", "I", "B", "BI"):
                if vals[k].get().strip():
                    entry[k] = vals[k].get().strip()
            err = self.add_custom_family(entry)
            if err:
                messagebox.showerror("My fonts", err, parent=w)
                return
            fill()

        def remove():
            sel = lb.curselection()
            if sel:
                name = self.custom_fonts[sel[0]]["name"]
                self.custom_fonts.pop(sel[0])
                for key in ("font_family", "heading_font", "dropcap_font"):
                    if self.var(key).get() == name:
                        self.var(key).set(DEFAULTS[key])
                self.refresh_fonts()
                fill()

        bar = ttk.Frame(fr, style=self.S("Card.TFrame"))
        bar.grid(row=8, column=0, columnspan=3, sticky="we", pady=(12, 0))
        ttk.Button(bar, text="Add / update family", command=save, style=self.S("TButton")).pack(side="left")
        ttk.Button(bar, text="Remove selected", command=remove, style=self.S("TButton")).pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=w.destroy, style=self.S("TButton")).pack(side="right")
        fill()

    def browse_source(self):
        p = filedialog.askopenfilename(title="Choose a book or text file", filetypes=[
            ("Books and text", "*.epub *.txt *.md *.markdown *.html *.htm *.xhtml *.docx"),
            ("All files", "*.*")])
        if p:
            self.var("source_mode").set("file")
            self.var("source_path").set(p)
            self._mode_changed()
            self.scan()

    def browse_out(self):
        p = filedialog.askdirectory(title="Where should books be saved?")
        if p:
            self.var("out_dir").set(p)

    def source_sig(self, s):
        h = hashlib.sha1()
        for k in PARSE_KEYS:
            h.update(repr(s.get(k)).encode())
        if s["source_mode"] == "paste":
            h.update(s.get("paste_text", "").encode("utf-8", "ignore"))
        elif os.path.exists(s.get("source_path", "")):
            h.update(str(os.path.getmtime(s["source_path"])).encode())
        return h.hexdigest()

    def log(self, msg):
        self.q.put(("log", msg))

    def _start(self, label, mode="build"):
        self.busy, self.mode = True, mode
        self.build_btn.configure(state="disabled")
        self.preview_btn.configure(state="disabled")
        self.status.configure(text=label)
        self.prog.start(12)

    def _stop(self, label):
        self.busy = False
        self.build_btn.configure(state="normal")
        self.preview_btn.configure(state="normal")
        self.status.configure(text=label)
        self.prog.stop()

    def scan(self, force=False):
        if self.busy:
            return
        if self.edited and not force and not messagebox.askyesno(
                "Find chapters again?", "You've renamed, skipped, moved or merged chapters. Finding the "
                                        "chapters again will undo those changes. Continue?"):
            self._show_split()
            return
        self.edited = False
        s = self.collect()
        self._start("Reading the source...", "scan")

        def work():
            try:
                book = load_book(s, s.get("paste_text", ""))
                self.q.put(("scanned", book, self.source_sig(s)))
            except Exception as e:
                self.q.put(("error", str(e), traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ chapters: table helpers
    def _split_chosen(self, _e=None):
        lab = self.split_disp.get()
        for v, l in self.SPLIT_LABELS:
            if l == lab:
                self.var("split_mode").set(v)
        self.scan()

    def _show_split(self):
        v = self.var("split_mode").get()
        self.split_disp.set(dict(self.SPLIT_LABELS).get(v, self.SPLIT_LABELS[0][1]))

    def auto_scan(self):
        """Opening the Chapters step reads the source if it hasn't been read (or has changed)."""
        s = self.collect()
        src_ok = (s["source_mode"] == "paste" and s.get("paste_text", "").strip()) or \
            (s["source_mode"] == "file" and os.path.exists(s.get("source_path", "")))
        if src_ok and (self.book is None or (self.source_sig(s) != self.book_sig and not self.edited)):
            self.scan()

    def fill_list(self):
        sel = self._sel()
        self.ctree.delete(*self.ctree.get_children())
        if not self.book:
            return
        n = 0
        for i, ch in enumerate(self.book.chapters):
            if ch.level == 1 and ch.include:
                n += 1
            words = sum(len(plain(b.text).split()) + sum(len(plain(l).split()) for l in b.lines) for b in ch.blocks)
            first = next((plain(b.text) for b in ch.blocks if b.kind in ("para", "quote", "verse", "item")
                          and plain(b.text).strip()), "")
            if not first:
                first = next((plain(l) for b in ch.blocks for l in b.lines if plain(l).strip()), "")
            num = "PART" if ch.level == 0 else (str(n) if ch.include else "-")
            self.ctree.insert("", "end", iid=str(i), values=("\u2714" if ch.include else "\u2014", num,
                                                            ch.display(), " ".join(first.split())[:70],
                                                            f"{words:,}"),
                              tags=() if ch.include else ("skipped",))
        for i in sel:
            if self.ctree.exists(str(i)):
                self.ctree.selection_add(str(i))
        act = [c for c in self.book.chapters if c.include]
        n_ch = len([c for c in act if c.level == 1])
        skipped = len(self.book.chapters) - len(act)
        s = self.collect()
        start = {"New page": "starts on a new page", "Right-hand page": "starts on a right-hand page",
                 "Continuous": "follows straight on"}.get(s.get("chapter_start"), "starts on a new page")
        msg = f"{n_ch} chapter{'s' if n_ch != 1 else ''} will be printed"
        if skipped:
            msg += f", {skipped} left out"
        msg += f". Each {start}" + (" and is listed in the Contents." if s.get("toc") else ".")
        if self.edited:
            msg += "  (You've made changes - they'll be used when you build.)"
        self.chap_summary.configure(text=msg)

    def _sel(self):
        return sorted(int(x) for x in self.ctree.selection()) if hasattr(self, "ctree") else []

    def show_preview(self):
        sel = self._sel()
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        if self.book and len(sel) == 1:
            ch = self.book.chapters[sel[0]]
            found = (ch.label + " / " if ch.label else "") + ch.title
            self.preview.insert("end", f"Heading found in your text:\n\u201c{found}\u201d\n\n", "found")
            shown = 0
            for b in ch.blocks:
                if shown >= 12:
                    self.preview.insert("end", "...")
                    break
                if b.kind == "anote":
                    self.preview.insert("end", f"[{b.label or 'Note'}] {plain(b.text)}\n\n", "note")
                elif b.kind == "scene":
                    self.preview.insert("end", "* * *\n\n")
                elif b.kind == "verse":
                    self.preview.insert("end", "\n".join(plain(l) for l in b.lines) + "\n\n")
                elif b.kind == "image":
                    self.preview.insert("end", "[picture]\n\n")
                else:
                    self.preview.insert("end", plain(b.text) + "\n\n")
                shown += 1
        self.preview.configure(state="disabled")

    def _tree_click(self, e):
        if self.ctree.identify_region(e.x, e.y) == "cell" and self.ctree.identify_column(e.x) == "#1":
            row = self.ctree.identify_row(e.y)
            if row:
                self.ctree.selection_set(row)
                self.toggle_ch()
                return "break"

    def _tree_double(self, e):
        if self.ctree.identify_region(e.x, e.y) == "cell" and self.ctree.identify_column(e.x) != "#1":
            row = self.ctree.identify_row(e.y)
            if row:
                self.ctree.selection_set(row)
                self.rename_ch()
                return "break"

    def _changed(self):
        self.edited = True
        self.unsaved = True
        self.fill_list()
        self.show_preview()

    def rename_ch(self):
        sel = self._sel()
        if not self.book or len(sel) != 1:
            return
        ch = self.book.chapters[sel[0]]
        x, y, w, h = self.ctree.bbox(str(sel[0]), "title") or (0, 0, 0, 0)
        if not w:
            return
        ent = ttk.Entry(self.ctree)
        ent.insert(0, ch.title)
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()

        def done(save):
            if save and ent.get().strip() != ch.title:
                ch.title = ent.get().strip()
                ent.destroy()
                self._changed()
            else:
                ent.destroy()
        ent.bind("<Return>", lambda e: done(True))
        ent.bind("<Escape>", lambda e: done(False))
        ent.bind("<FocusOut>", lambda e: done(True))

    def toggle_ch(self):
        if not self.book:
            return
        for i in self._sel():
            self.book.chapters[i].include = not self.book.chapters[i].include
        self._changed()

    def move_ch(self, d):
        sel = self._sel()
        if not self.book or len(sel) != 1:
            return
        i, j = sel[0], sel[0] + d
        chs = self.book.chapters
        if 0 <= j < len(chs):
            chs[i], chs[j] = chs[j], chs[i]
            self.ctree.selection_set(str(j))
            self._changed()
            self.ctree.see(str(j))

    def merge_ch(self):
        """Undo a wrong split: the chapter's heading goes back into the text where it was."""
        sel = self._sel()
        if not self.book or len(sel) != 1 or sel[0] == 0:
            return
        i = sel[0]
        prev, ch = self.book.chapters[i - 1], self.book.chapters[i]
        heading = ch.title if not ch.label else f"{ch.label} {ch.title}".strip()
        prev.blocks.append(Block("head" if ch.heading_kind == "head" else "para", esc(heading)))
        prev.blocks.extend(ch.blocks)
        del self.book.chapters[i]
        self.ctree.selection_set(str(i - 1))
        self._changed()

    def reset_chapters(self):
        if self.book and (not self.edited or messagebox.askyesno(
                "Undo all changes", "Find the chapters again from the source? Your renames, skips, moves "
                                    "and merges will be lost.")):
            self.edited = False
            self.book = None
            self.scan(force=True)

    def _choose_book(self, s):
        """The book to typeset: the scanned (and possibly edited) chapters, or None to read the source again."""
        sig = self.source_sig(s)
        cached = self.book if (self.book is not None and sig == self.book_sig) else None
        if cached is None and self.book is not None and self.edited:
            if messagebox.askyesno("Keep your chapter changes?",
                                   "The source or chapter settings changed after you edited the chapters.\n\n"
                                   "Yes = use your edited chapters\nNo = find the chapters again "
                                   "(your edits will be lost)"):
                cached = self.book
        return cached, sig

    def preview_book(self):
        """Typeset the book with the current settings and show it - nothing is saved to the output folder."""
        if self.busy or not self._commit_editor():
            return
        s = self.collect()
        cached, sig = self._choose_book(s)
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self._start("Making the preview...", mode="preview")

        def work():
            try:
                if cached is not None:
                    book = copy.copy(cached)
                else:
                    self.log("Reading the source...")
                    book = load_book(s, s.get("paste_text", ""))
                    self.q.put(("scanned", book, sig))
                    book = copy.copy(book)
                apply_info(book, s)
                self.q.put(("preview", build_preview(book, s, self.log)))
            except Exception as e:
                self.q.put(("error", str(e), traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def build(self):
        if self.busy or not self._commit_editor():
            return
        s = self.collect()
        if not any(s[k] for k in ("fmt_pdf", "fmt_impose", "fmt_cover", "fmt_epub", "fmt_docx",
                                  "fmt_html", "fmt_txt")):
            messagebox.showwarning("Nothing to make", "Tick at least one format on the Output tab.")
            return
        try:
            self.save_settings(os.path.join(app_dir(), "settings.json"))
        except Exception:
            pass
        cached, sig = self._choose_book(s)
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self._start("Building your book...")

        def work():
            try:
                if cached is not None:
                    book = copy.copy(cached)
                else:
                    self.log("Reading the source...")
                    book = load_book(s, s.get("paste_text", ""))
                    self.q.put(("scanned", book, sig))
                    book = copy.copy(book)
                apply_info(book, s)
                folder, made, notes = run_build(book, s, self.log)
                self.q.put(("done", folder, made))
            except Exception as e:
                self.q.put(("error", str(e), traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", item[1] + "\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                    self.status.configure(text=item[1])
                elif kind == "fonts":
                    self.refresh_fonts(item[1])
                elif kind == "scanned":
                    self.book, self.book_sig = item[1], item[2]
                    self.edited = False
                    self.unsaved = False
                    if getattr(self, "editor", None) is not None:
                        self.editor.reset()
                    for k in ("title", "author"):
                        cur = self.var(k).get().strip()
                        new = (getattr(self.book, k) or "").strip()
                        if not cur or cur == self.autofilled.get(k):
                            self.var(k).set(new)
                            self.autofilled[k] = new
                    self.fill_list()
                    if self.mode == "scan":
                        self._stop(f"Found {len(self.book.chapters)} chapters. Check the list, then click Preview book.")
                elif kind == "preview":
                    res = item[1]
                    self._stop(f"Preview ready: {res['pages']} pages. Nothing has been saved yet.")
                    if getattr(self, "preview_win", None) is not None and self.preview_win.alive():
                        self.preview_win.load(res)
                    else:
                        self.preview_win = PreviewWindow(self, res)
                    target, self._preview_target = self._preview_target, None
                    page = dict(res.get("chapter_pages", [])).get(target) if target else None
                    if page:
                        self.preview_win.mode = "pages"
                        self.preview_win._mode_buttons()
                        self.preview_win.go(page - 1)
                elif kind == "done":
                    folder, made = item[1], item[2]
                    self._stop(f"Finished! {len(made)} file(s) saved in {folder}")
                    if self.var("open_when_done").get():
                        try:
                            os.startfile(folder)
                        except Exception:
                            try:
                                if sys.platform == "darwin":
                                    subprocess.Popen(["open", folder])
                                else:
                                    subprocess.Popen(["xdg-open", folder])
                            except Exception:
                                pass
                    messagebox.showinfo("Book finished", "Saved to:\n" + folder + "\n\n" +
                                        "\n".join(os.path.basename(m) for m in made) +
                                        "\n\nPrinting tips are in 'READ ME - printing notes.txt'.")
                elif kind == "error":
                    self._stop("Something went wrong \u2014 see the message.")
                    try:
                        with open(os.path.join(app_dir(), "last_error.txt"), "w", encoding="utf-8") as f:
                            f.write(item[2])
                    except Exception:
                        pass
                    messagebox.showerror("Problem", item[1] + "\n\n(Details saved to last_error.txt in "
                                         + app_dir() + ")")
        except queue.Empty:
            pass
        finally:
            # keep listening even if handling one message failed - otherwise later builds never finish
            self._poll_id = self.after(120, self.poll)

    def show_help(self):
        w = tk.Toplevel(self)
        w.title("How to use, print and bind")
        w.geometry("760x620")
        w.configure(background=th.PAPER)
        t = tk.Text(w, wrap="word", font=("Segoe UI", 10), padx=16, pady=12, background=th.CARD,
                    foreground=th.INK, relief="flat", highlightthickness=0, spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(w, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        t.insert("1.0", HELP)
        t.configure(state="disabled")


def cli(argv):
    """Headless mode: BookForge.exe --cli SOURCE OUTPUT_FOLDER [preset.json]"""
    src, out = argv[0], argv[1]
    s = dict(DEFAULTS)
    if len(argv) > 2:
        with open(argv[2], encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    s.update(source_mode="file", source_path=src, out_dir=out)
    os.makedirs(out, exist_ok=True)
    logf = open(os.path.join(out, "BookForge log.txt"), "w", encoding="utf-8")

    def log(m):
        logf.write(m + "\n")
        logf.flush()
    try:
        book = apply_info(load_book(s), s)
        run_build(book, s, log)
    except Exception:
        log(traceback.format_exc())
        return 1
    finally:
        logf.close()
    return 0


def preview_window_check(source, report=None):
    """Self-test for packaged builds: typeset SOURCE, open the real preview window and check that the book
    pages and printing sheets are actually drawn in it. Returns 0 when they are."""
    s = dict(DEFAULTS)
    s.update(source_mode="file", source_path=source, fmt_impose=True)
    res = build_preview(apply_info(load_book(s), s), s, log=lambda m: None)
    app = App()
    errors = []
    app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
    lines, ok = [], True
    try:
        win = PreviewWindow(app, res)
        for mode in ("pages", "sheets"):
            if mode == "sheets":
                if not win.sheets:
                    lines.append("FAIL: no printing sheets in the preview")
                    ok = False
                    break
                win.set_mode("sheets")
            for _ in range(10):
                app.update()
            ph = getattr(win, "photo", None)
            drawn = ph is not None and ph.width() > 100 and ph.height() > 100 and bool(win.canvas.find_all())
            if drawn:
                lines.append(f"PASS: preview window shows {mode} ({ph.width()}x{ph.height()} image)")
            else:
                texts = [win.canvas.itemcget(i, "text") for i in win.canvas.find_all()
                         if win.canvas.type(i) == "text"]
                lines.append(f"FAIL: preview window shows no {mode} image {texts[:1]}")
                ok = False
            win.photo = None
        win.close()
    except Exception:
        lines.append("FAIL: " + traceback.format_exc())
        ok = False
    finally:
        try:
            app.destroy()
        except tk.TclError:
            pass
    if errors:
        lines += ["FAIL: window error: " + e for e in errors]
        ok = False
    msg = "\n".join(lines) + "\n"
    if report:
        with open(report, "w", encoding="utf-8") as f:
            f.write(msg)
    else:
        sys.stdout.write(msg)
    return 0 if ok else 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--preview-window-check":
        # BookForge --preview-window-check SOURCE [REPORT.txt] : opens the real preview window (self-test)
        sys.exit(preview_window_check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    if len(sys.argv) >= 3 and sys.argv[1] == "--font-report":
        bf_fonts.set_user_fonts_dir(None)
        bf_fonts.scan_installed(force=True)
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(bf_fonts.font_report() + "\n")
        sys.exit(0)
    if len(sys.argv) >= 4 and sys.argv[1] == "--preview-check":
        # BookForge.exe --preview-check SOURCE OUT.png : makes a preview and draws its first page
        s = dict(DEFAULTS)
        s.update(source_mode="file", source_path=sys.argv[2])
        res = build_preview(apply_info(load_book(s), s), s, log=lambda m: None)
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(res["pdf"])
        doc[0].render(scale=1).to_pil().save(sys.argv[3])
        doc.close()
        shutil.rmtree(res["dir"], ignore_errors=True)
        sys.exit(0)
    if len(sys.argv) >= 4 and sys.argv[1] == "--cli":
        sys.exit(cli(sys.argv[2:]))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
