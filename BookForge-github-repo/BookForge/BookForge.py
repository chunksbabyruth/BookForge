"""BookForge - one-click book maker (Windows GUI)."""
import copy
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from bf_core import (DEFAULTS, PAGE_SIZES, SHEET_SIZES, PAPERS, APP_NAME, APP_VERSION, APP_AUTHOR,
                     load_book, apply_info, plain)
from bf_pdf import available_fonts, CUSTOM_LABEL
from bf_build import run_build, default_out_dir

TEXT_KEYS = ("paste_text", "dedication", "note_text", "blurb")
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
4. OUTPUT: tick the formats you want and click BUILD BOOK. Everything is saved
   in one folder, together with a "READ ME - printing notes.txt" file.

TEXT IS KEPT WORD FOR WORD. Only spacing used for line-wrapping in the source
file is tidied; italics, bold and line breaks in poems are carried over.

PRINTING THE "IMPOSED FOR BINDING" PDF
- Print at Actual size / 100% (never "Fit"), double-sided,
  FLIP ON SHORT EDGE. If your printer can only flip on the long edge, tick
  "Rotate back sides 180" on the Output tab and rebuild.
- Print ONE test sheet first and fold it: page numbers should run in order.
- Sheets come out in order. For each signature, fold every sheet in half and
  nest each new folded sheet INSIDE the previous one (sheet 1 is outermost).
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
        self.title(f"{APP_NAME} {APP_VERSION} \u2014 one-click book maker by {APP_AUTHOR}")
        self.geometry("1040x760")
        self.minsize(940, 660)
        try:
            self.iconbitmap(resource("bookforge.ico"))
        except Exception:
            pass
        st = ttk.Style(self)
        for th in ("vista", "winnative", "clam"):
            if th in st.theme_names():
                st.theme_use(th)
                break
        st.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=(18, 8))
        st.configure("Hint.TLabel", foreground="#555555")
        self.vars, self.texts = {}, {}
        self.book, self.book_sig, self.busy, self.mode = None, None, False, ""
        self.q = queue.Queue()
        self.fonts = available_fonts()
        self._menu()
        self._ui()
        self.load_settings(os.path.join(app_dir(), "settings.json"), quiet=True)
        self._mode_changed()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(120, self.poll)

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

    def lab(self, p, r, text, c=0):
        ttk.Label(p, text=text).grid(row=r, column=c, sticky="w", padx=6, pady=3)

    def combo(self, p, r, text, key, values, width=30, cmd=None):
        self.lab(p, r, text)
        cb = ttk.Combobox(p, textvariable=self.var(key), values=list(values), state="readonly",
                          width=width)
        cb.grid(row=r, column=1, sticky="we", padx=6, pady=3)
        if cmd:
            cb.bind("<<ComboboxSelected>>", cmd)
        return cb

    def spin(self, p, r, text, key, lo, hi, inc, hint=""):
        self.lab(p, r, text)
        f = ttk.Frame(p)
        f.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        ttk.Spinbox(f, textvariable=self.var(key), from_=lo, to=hi, increment=inc,
                    width=8).pack(side="left")
        if hint:
            ttk.Label(f, text=hint, style="Hint.TLabel").pack(side="left", padx=6)

    def entry(self, p, r, text, key, width=40):
        self.lab(p, r, text)
        e = ttk.Entry(p, textvariable=self.var(key), width=width)
        e.grid(row=r, column=1, sticky="we", padx=6, pady=3)
        return e

    def check(self, p, r, text, key, c=0, span=2):
        ttk.Checkbutton(p, text=text, variable=self.var(key)).grid(
            row=r, column=c, columnspan=span, sticky="w", padx=6, pady=2)

    def textbox(self, p, key, height=4, width=50):
        f = ttk.Frame(p)
        t = tk.Text(f, height=height, width=width, wrap="word", font=("Segoe UI", 10),
                    undo=True, relief="solid", borderwidth=1)
        sb = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.texts[key] = t
        return f

    def group(self, parent, text, **grid):
        g = ttk.LabelFrame(parent, text=text, padding=8)
        g.grid(**grid, sticky="nsew", padx=6, pady=5)
        g.columnconfigure(1, weight=1)
        return g

    # ------------------------------------------------------------ layout
    def _menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Open source file...", command=self.browse_source)
        f.add_separator()
        f.add_command(label="Save settings as preset...", command=self.save_preset)
        f.add_command(label="Load preset...", command=self.load_preset)
        f.add_command(label="Reset all settings to defaults", command=self.reset)
        f.add_separator()
        f.add_command(label="Exit", command=self.on_close)
        m.add_cascade(label="File", menu=f)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="How to use, print and bind", command=self.show_help)
        h.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", f"{APP_NAME} {APP_VERSION}\nMade by {APP_AUTHOR}\n\nTurns EPUBs, text and Word "
                     "files into print-ready books with page numbers, contents, imposition and "
                     "covers.\n\nFree and open source (MIT License)."))
        m.add_cascade(label="Help", menu=h)
        self.config(menu=m)

    def _ui(self):
        bar = ttk.Frame(self, padding=(8, 2, 8, 8))
        bar.pack(side="bottom", fill="x")
        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 4))
        tabs = {}
        for name in ("1. Source", "2. Book info", "3. Layout", "4. Front & back", "5. Output"):
            fr = ttk.Frame(nb, padding=6)
            nb.add(fr, text=name)
            fr.columnconfigure(0, weight=1)
            fr.columnconfigure(1, weight=1)
            tabs[name[0]] = fr
        self._tab_source(tabs["1"])
        self._tab_info(tabs["2"])
        self._tab_layout(tabs["3"])
        self._tab_front(tabs["4"])
        self._tab_output(tabs["5"])

        self.build_btn = ttk.Button(bar, text="\u25B6  BUILD BOOK", style="Big.TButton",
                                    command=self.build)
        self.build_btn.pack(side="left")
        right = ttk.Frame(bar)
        right.pack(side="left", fill="both", expand=True, padx=12)
        self.status = ttk.Label(right, text="Ready. Pick a source on the Source tab, then click BUILD BOOK.")
        self.status.pack(anchor="w")
        self.prog = ttk.Progressbar(right, mode="indeterminate")
        self.prog.pack(fill="x", pady=(4, 2))
        self.logbox = tk.Text(right, height=4, font=("Consolas", 9), state="disabled",
                              relief="flat", background="#f4f4f4")
        self.logbox.pack(fill="x")

    def _tab_source(self, t):
        t.rowconfigure(1, weight=1)
        g = self.group(t, "Make a book from...", row=0, column=0, columnspan=2)
        ttk.Radiobutton(g, text="A file (EPUB, TXT, Markdown, HTML, Word .docx)", value="file",
                        variable=self.var("source_mode"), command=self._mode_changed).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=6)
        self.src_entry = ttk.Entry(g, textvariable=self.var("source_path"))
        self.src_entry.grid(row=1, column=0, columnspan=2, sticky="we", padx=6, pady=3)
        self.src_btn = ttk.Button(g, text="Browse...", command=self.browse_source)
        self.src_btn.grid(row=1, column=2, padx=6)
        g.columnconfigure(0, weight=1)
        ttk.Radiobutton(g, text="Text I paste or type below", value="paste",
                        variable=self.var("source_mode"), command=self._mode_changed).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))

        left = ttk.Frame(t)
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pg = ttk.LabelFrame(left, text="Paste / type text  (use \"Chapter 1\" lines or # headings "
                                       "to mark chapters)", padding=6)
        pg.grid(row=0, column=0, sticky="nsew", padx=6, pady=5)
        self.paste_frame = self.textbox(pg, "paste_text", height=6)
        self.paste_frame.pack(fill="both", expand=True)

        d = self.group(left, "Chapters & cleanup", row=1, column=0)
        self.combo(d, 0, "Find chapters by", "split_mode",
                   ["Auto", "Heading level 1", "Heading level 2", "Heading level 3",
                    "Markdown # headings", "Chapter / Part lines", "ALL-CAPS lines",
                    "Custom pattern", "No chapters"])
        self.entry(d, 1, "Custom pattern (regex)", "custom_regex")
        self.combo(d, 2, "Paragraphs in text files", "line_paragraphs",
                   ["Auto", "Blank line between paragraphs", "Each line is a paragraph"])
        self.check(d, 3, "Remove Gutenberg / Standard Ebooks boilerplate (license, imprint, colophon)", "strip_gutenberg")
        self.check(d, 4, "Skip the source's own contents list (a new one is made)", "skip_contents")
        self.check(d, 5, "Skip cover-image page", "skip_cover")
        self.check(d, 6, "Include pictures from the source", "include_images")
        self.check(d, 7, "Keep text that comes before the first chapter", "keep_front_text")
        self.check(d, 8, "Drop empty chapters", "drop_empty")
        self.check(d, 9, "Keep line breaks inside paragraphs (poetry / text files)", "preserve_breaks")

        r = ttk.LabelFrame(t, text="Chapters found", padding=6)
        r.grid(row=1, column=1, sticky="nsew", padx=6, pady=5)
        r.rowconfigure(1, weight=1)
        r.columnconfigure(0, weight=1)
        top = ttk.Frame(r)
        top.grid(row=0, column=0, sticky="we")
        ttk.Button(top, text="Scan chapters", command=self.scan).pack(side="left")
        self.scan_lbl = ttk.Label(top, text="Not scanned yet.", style="Hint.TLabel")
        self.scan_lbl.pack(side="left", padx=8)
        lf = ttk.Frame(r)
        lf.grid(row=1, column=0, sticky="nsew", pady=4)
        self.chlist = tk.Listbox(lf, font=("Segoe UI", 10), activestyle="none", selectmode="extended")
        sb = ttk.Scrollbar(lf, command=self.chlist.yview)
        self.chlist.configure(yscrollcommand=sb.set)
        self.chlist.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.chlist.bind("<Double-Button-1>", lambda e: self.rename_ch())
        bot = ttk.Frame(r)
        bot.grid(row=2, column=0, sticky="we")
        for txt, fn in (("Rename", self.rename_ch), ("Skip / include", self.toggle_ch),
                        ("Move up", lambda: self.move_ch(-1)), ("Move down", lambda: self.move_ch(1))):
            ttk.Button(bot, text=txt, command=fn).pack(side="left", padx=2, expand=True, fill="x")

    def _tab_info(self, t):
        g = self.group(t, "Title page details (leave blank to use the source's own)", row=0, column=0,
                       columnspan=2)
        self.entry(g, 0, "Title", "title", 60)
        self.entry(g, 1, "Subtitle", "subtitle", 60)
        self.entry(g, 2, "Author line", "author", 60)
        self.entry(g, 3, "Extra credit line", "credit", 60)
        ttk.Label(g, text='e.g. "Translated by Edgar Taylor"  or  "Illustrated by ..."',
                  style="Hint.TLabel").grid(row=4, column=1, sticky="w", padx=6)
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
        self.font_cb = self.combo(f, 0, "Font", "font_family", self.fonts, cmd=self._font_pick)
        self.spin(f, 1, "Body size (pt)", "body_size", 6, 30, 0.5)
        self.spin(f, 2, "Line spacing", "line_spacing", 1.0, 2.5, 0.05, "x font size")
        self.combo(f, 3, "Alignment", "align", ["Justified", "Left"])
        self.spin(f, 4, "Paragraph indent (in)", "indent", 0, 1.5, 0.05)
        self.spin(f, 5, "Space between paragraphs (pt)", "para_space", 0, 24, 1)
        self.check(f, 6, "Indent the first paragraph of each chapter", "first_para_indent")
        self.combo(f, 7, "Poems / verse", "verse_style", ["Centered italic", "Indented"])

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
        self.check(c, 7, "Large first letter in each chapter", "drop_cap")
        self.combo(c, 8, "Scene break", "scene_break", ["* * *", "*", "~ ~ ~", "# # #", "Blank space"])

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
        b = self.group(t, "Back of the book", row=0, column=1)
        self.check(b, 0, "Print \"THE END\" after the last chapter", "the_end")
        self.spin(b, 1, "Lined \"Notes\" pages at the end", "notes_pages", 0, 20, 1)
        ttk.Label(t, text="Dedication and the extra front page are on the Book info tab.",
                  style="Hint.TLabel").grid(row=1, column=1, sticky="nw", padx=12, pady=12)

    def _tab_output(self, t):
        g = self.group(t, "Save to", row=0, column=0, columnspan=2)
        e = ttk.Entry(g, textvariable=self.var("out_dir"))
        e.grid(row=0, column=0, sticky="we", padx=6)
        g.columnconfigure(0, weight=1)
        ttk.Button(g, text="Browse...", command=self.browse_out).grid(row=0, column=1, padx=6)
        ttk.Label(g, text=f"Blank = {default_out_dir()}  (a folder per book is made inside)",
                  style="Hint.TLabel").grid(row=1, column=0, sticky="w", padx=6)
        self.check(g, 2, "Open the folder when finished", "open_when_done")
        f = self.group(t, "Formats to make", row=1, column=0)
        self.check(f, 0, "Print-ready PDF (pages in reading order)", "fmt_pdf")
        self.check(f, 1, "Imposed PDF for binding (2 pages per sheet, in signatures)", "fmt_impose")
        self.check(f, 2, "Wraparound cover template PDF (front, spine, back)", "fmt_cover")
        self.check(f, 3, "EPUB e-book", "fmt_epub")
        self.check(f, 4, "Word document (.docx, editable)", "fmt_docx")
        self.check(f, 5, "Web page (.html)", "fmt_html")
        self.check(f, 6, "Plain text (.txt)", "fmt_txt")
        i = self.group(t, "Binding / imposition", row=2, column=0)
        self.combo(i, 0, "Sheet size (landscape)", "sheet_size", list(SHEET_SIZES))
        self.spin(i, 1, "Sheets per signature", "sig_sheets", 0, 20, 1, "0 = one booklet (saddle stitch)")
        self.check(i, 2, "Fold marks", "fold_marks")
        self.check(i, 3, "Signature order marks on the spine", "sig_marks")
        self.check(i, 4, "Rotate back sides 180\u00b0 (printer only flips on long edge)", "rotate_back")
        c = self.group(t, "Cover", row=1, column=1, rowspan=2)
        self.combo(c, 0, "Paper (sets spine width)", "paper", list(PAPERS))
        ttk.Label(c, text="Back cover text (optional):").grid(row=1, column=0, columnspan=2,
                                                             sticky="w", padx=6)
        self.textbox(c, "blurb", height=8, width=40).grid(row=2, column=0, columnspan=2,
                                                          sticky="nsew", padx=6)
        c.rowconfigure(2, weight=1)

    # ------------------------------------------------------------ settings
    def collect(self):
        s = {}
        for k, d in DEFAULTS.items():
            try:
                v = self.var(k).get()
                s[k] = type(d)(v) if not isinstance(d, bool) else bool(v)
            except (tk.TclError, ValueError):
                s[k] = d
        for k in TEXT_KEYS:
            if k in self.texts:
                s[k] = self.texts[k].get("1.0", "end-1c")
        return s

    def apply(self, data):
        for k, v in data.items():
            if k in DEFAULTS:
                try:
                    self.var(k).set(v)
                except tk.TclError:
                    pass
            elif k in self.texts:
                self.texts[k].delete("1.0", "end")
                self.texts[k].insert("1.0", v or "")
        if self.var("font_family").get() not in self.fonts:
            self.var("font_family").set(DEFAULTS["font_family"])

    def save_settings(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.collect(), f, indent=1)

    def load_settings(self, path, quiet=False):
        try:
            with open(path, encoding="utf-8") as f:
                self.apply(json.load(f))
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
            for k in ("dedication", "note_text", "blurb"):
                self.texts[k].delete("1.0", "end")

    def on_close(self):
        try:
            self.save_settings(os.path.join(app_dir(), "settings.json"))
        except Exception:
            pass
        self.destroy()

    # ------------------------------------------------------------ actions
    def _mode_changed(self):
        paste = self.var("source_mode").get() == "paste"
        self.src_entry.configure(state="disabled" if paste else "normal")
        self.src_btn.configure(state="disabled" if paste else "normal")
        self.texts["paste_text"].configure(state="normal" if paste else "disabled",
                                           background="white" if paste else "#eeeeee")

    def _font_pick(self, _e=None):
        if self.var("font_family").get() == CUSTOM_LABEL:
            p = filedialog.askopenfilename(title="Choose the REGULAR style of a font",
                                           filetypes=[("Fonts", "*.ttf *.otf *.ttc")])
            if p:
                self.var("custom_font_path").set(p)
            elif not self.var("custom_font_path").get():
                self.var("font_family").set(DEFAULTS["font_family"])

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
        self.status.configure(text=label)
        self.prog.start(12)

    def _stop(self, label):
        self.busy = False
        self.build_btn.configure(state="normal")
        self.status.configure(text=label)
        self.prog.stop()

    def scan(self):
        if self.busy:
            return
        s = self.collect()
        self._start("Reading the source...", "scan")

        def work():
            try:
                book = load_book(s, s.get("paste_text", ""))
                self.q.put(("scanned", book, self.source_sig(s)))
            except Exception as e:
                self.q.put(("error", str(e), traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def fill_list(self):
        self.chlist.delete(0, "end")
        if not self.book:
            return
        n = 0
        for ch in self.book.chapters:
            if ch.level == 1:
                n += 1
            words = sum(len(plain(b.text).split()) + sum(len(plain(l).split()) for l in b.lines) for b in ch.blocks)
            tag = "PART  " if ch.level == 0 else f"{n:>3}.  "
            line = f"{tag}{ch.display()}   ({words:,} words)"
            if not ch.include:
                line = "   [skipped]  " + ch.display()
            self.chlist.insert("end", line)
            if not ch.include:
                self.chlist.itemconfig("end", foreground="#999999")
        act = self.book.active()
        self.scan_lbl.configure(text=f"{len([c for c in act if c.level == 1])} chapters will be printed."
                                     "  Double-click to rename.")

    def _sel(self):
        return list(self.chlist.curselection())

    def rename_ch(self):
        sel = self._sel()
        if not self.book or len(sel) != 1:
            return
        ch = self.book.chapters[sel[0]]
        new = simpledialog.askstring("Rename chapter", "Chapter title:", initialvalue=ch.title, parent=self)
        if new is not None:
            ch.title = new.strip()
            self.fill_list()
            self.chlist.selection_set(sel[0])

    def toggle_ch(self):
        if not self.book:
            return
        for i in self._sel():
            self.book.chapters[i].include = not self.book.chapters[i].include
        sel = self._sel()
        self.fill_list()
        for i in sel:
            self.chlist.selection_set(i)

    def move_ch(self, d):
        sel = self._sel()
        if not self.book or len(sel) != 1:
            return
        i, j = sel[0], sel[0] + d
        chs = self.book.chapters
        if 0 <= j < len(chs):
            chs[i], chs[j] = chs[j], chs[i]
            self.fill_list()
            self.chlist.selection_set(j)
            self.chlist.see(j)

    def build(self):
        if self.busy:
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
        sig = self.source_sig(s)
        cached = self.book if (self.book is not None and sig == self.book_sig) else None
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
                elif kind == "scanned":
                    self.book, self.book_sig = item[1], item[2]
                    for k in ("title", "author"):
                        if not self.var(k).get().strip() and getattr(self.book, k):
                            self.var(k).set(getattr(self.book, k))
                    self.fill_list()
                    if self.mode == "scan":
                        self._stop(f"Found {len(self.book.chapters)} chapters. Check the list, then BUILD BOOK.")
                elif kind == "done":
                    folder, made = item[1], item[2]
                    self._stop(f"Finished! {len(made)} file(s) saved in {folder}")
                    if self.var("open_when_done").get():
                        try:
                            os.startfile(folder)
                        except Exception:
                            try:
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
        self.after(120, self.poll)

    def show_help(self):
        w = tk.Toplevel(self)
        w.title("How to use, print and bind")
        w.geometry("760x620")
        t = tk.Text(w, wrap="word", font=("Consolas", 10), padx=12, pady=10)
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


def main():
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
