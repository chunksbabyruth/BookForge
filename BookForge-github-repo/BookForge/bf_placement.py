"""Page placement preview ("Adjust page placement..." on the Output step).

Shows one side of a printing sheet with every page where the printing files will put it, and updates as the
settings change. The page positions come from bf_impose.plan_imposition - the very function the imposed PDF is
made from - so the preview and the PDF can't disagree; this module only converts sheet points to screen pixels.

Dragging a page changes the page offsets (in points), and the numbers beside the sheet are worked out from the
same placement. All lengths are points (1 pt = 1/72 inch); the sheet's origin is its bottom left corner.
"""
import copy
import os
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk

import bf_impose
from bf_core import DEFAULTS, PAGE_SIZES, page_size_inches, load_book, apply_info

PLACEMENT_KEYS = ("imp_fore", "imp_binding", "imp_top", "imp_bottom", "imp_offset_x", "imp_offset_y")
# Settings that only change how pages are put on the sheets (not the pages themselves).
SHEET_ONLY_KEYS = set(bf_impose.IMPOSE_DEFAULTS) | {"sheet_size", "sheet_unit", "sheet_w", "sheet_h",
                                                    "fmt_pdf", "fmt_impose", "fmt_cover", "fmt_epub", "fmt_docx",
                                                    "fmt_html", "fmt_txt", "out_dir", "open_when_done",
                                                    "dark_mode", "check_updates", "paper", "spine_width",
                                                    "cover_front_image", "cover_back_image", "cover_image_fit",
                                                    "cover_text_over_art", "blurb"}
PLACEHOLDER_PAGES = 16


# --------------------------------------------------------------------------
# Plain helpers (no window) - also used by the tests
# --------------------------------------------------------------------------
def fit_view(W, H, view_w, view_h, pad=24):
    """Scale and origin that fit a W x H pt sheet in a view_w x view_h pixel area, proportions kept."""
    k = max(1e-9, min((view_w - 2 * pad) / W, (view_h - 2 * pad) / H))
    ox = (view_w - W * k) / 2
    oy = (view_h - H * k) / 2
    return k, ox, oy


def to_screen(view, H, x, y):
    """Sheet point (origin bottom left, y up) -> canvas pixel (origin top left, y down)."""
    k, ox, oy = view
    return ox + x * k, oy + (H - y) * k


def rect_to_screen(view, H, x, y, w, h):
    x1, y1 = to_screen(view, H, x, y + h)
    x2, y2 = to_screen(view, H, x + w, y)
    return x1, y1, x2, y2


def offsets_after_drag(g, start, dx_px, dy_px, k):
    """New (offset toward fore-edge, offset toward top) in points after dragging page g by dx_px, dy_px
    screen pixels (y down) on a view scaled k px per pt. Mirrors the rule in bf_impose.place_page."""
    dx_pt, dy_pt = dx_px / k, -dy_px / k
    ox = start[0] + (dx_pt if g.bind == "L" else -dx_pt)
    oy = start[1] + (dy_pt if g.rot == 0 else -dy_pt)
    return round(ox, 2), round(oy, 2)


def nudge(g, start, right=0.0, up=0.0):
    """Offsets after moving page g right/up on the sheet by the given points (keyboard arrows)."""
    ox = start[0] + (right if g.bind == "L" else -right)
    oy = start[1] + (up if g.rot == 0 else -up)
    return round(ox, 2), round(oy, 2)


def _pt(v):
    return f"{v:.2f}"


def finished_page_text(s, fixed=False, src=None):
    if fixed and src:
        return f"the PDF's own pages, {_pt(src[0])} × {_pt(src[1])} pt"
    if "page_size" not in s:
        return f"{_pt(src[0])} × {_pt(src[1])} pt" if src else "-"
    try:
        w, h = page_size_inches(s)
    except ValueError as e:
        return str(e)
    name = s.get("page_size") if s.get("page_size") in PAGE_SIZES else "Custom"
    return f"{name} – {_pt(w * 72)} × {_pt(h * 72)} pt"


def diagnostics(info, s, side, g, page_no, fixed=False):
    """Lines (label, value, kind) describing the paper, the layout and one placed page. kind: '' / 'head' /
    'ok' / 'warn'. Everything comes from the same placement the PDF uses."""
    W, H = info["sheet"]
    W0, H0 = bf_impose.sheet_points(s)
    lines = [("PAPER AND LAYOUT", "", "head"),
             ("Printer paper", f"{bf_impose.sheet_name(s)} – {_pt(W0)} × {_pt(H0)} pt", ""),
             ("Sheet as printed", f"{_pt(W)} × {_pt(H)} pt ({'landscape' if W > H else 'portrait'})", ""),
             ("Finished book page", finished_page_text(s, fixed, info.get("page")), "")]
    layout = info["layout"]
    if layout in bf_impose.FOLD_LAYOUTS:
        rows, cols, _f, _l = bf_impose.FOLD_LAYOUTS[layout]
        lines.append(("Layout", f"{layout.split(' - ')[0]} – {rows} row{'s' * (rows != 1)} × "
                                f"{cols} column{'s' * (cols != 1)} per side", ""))
    else:
        lines.append(("Layout", layout, ""))
    if g is None:
        lines.append(("", "Click a page to see its numbers.", ""))
        return lines
    x0, y0, cw, ch = g.cell
    ax, ay, aw, ah = g.area
    lines += [("Page's space (cell)", f"{_pt(cw)} × {_pt(ch)} pt", ""),
              ("Usable after margins", f"{_pt(aw)} × {_pt(ah)} pt", "")]
    where = f"page {page_no}" if page_no else "a blank page"
    lines.append((f"PAGE ({where.upper()})", "", "head"))
    if g.kind == "small":
        lines += [("Source page", f"{_pt(g.src[0])} × {_pt(g.src[1])} pt", ""),
                  ("On the sheet", f"{_pt(g.w)} × {_pt(g.h)} pt", ""),
                  ("Scaling", f"{g.sx:.6f} × {g.sy:.6f} (small layouts keep the proportions)", ""),
                  ("Rotated", "Yes (180°, upside down)" if g.ang else "No", ""),
                  ("Position", f"x {_pt(g.x)}, y {_pt(g.y)} pt (bottom left corner)", ""),
                  ("", "Page scaling, position, margins and offsets don't apply to small layouts.", "")]
        return lines
    turn = {0: "No", 90: "Yes, 90° counter-clockwise", 180: "Yes, 180° (upside down)",
            270: "Yes, 90° clockwise"}.get(g.ang, f"Yes, {g.ang}°")
    lines += [("Spine side", "left of the page" if g.bind == "L" else "right of the page", ""),
              ("Head (top) of the space", "up" if g.rot == 0 else "down (the page is upside down on the sheet)", ""),
              ("Source page", f"{_pt(g.src[0])} × {_pt(g.src[1])} pt", ""),
              ("Rotated", turn, ""),
              ("Scaling mode", f"{g.mode}, {'snug against the binding edge' if g.snug else 'centered'}", ""),
              ("Scale (across × down)", f"{g.sx:.6f} × {g.sy:.6f}", ""),
              ("On the sheet", f"{_pt(g.w)} × {_pt(g.h)} pt", ""),
              ("Position", f"x {_pt(g.x)}, y {_pt(g.y)} pt (bottom left corner of the page)", ""),
              ("Margins", f"fore-edge {_pt(g.margins['fore'])}, binding {_pt(g.margins['spine'])}, "
                          f"top {_pt(g.margins['top'])}, bottom {_pt(g.margins['bottom'])} pt", ""),
              ("Offsets", f"{_pt(g.offset[0])} pt toward the fore-edge, {_pt(g.offset[1])} pt toward the top", ""),
              ("White space: spine", f"{_pt(g.gaps['spine'])} pt", ""),
              ("White space: top", f"{_pt(g.gaps['top'])} pt", ""),
              ("White space: fore-edge", f"{_pt(g.gaps['fore'])} pt", ""),
              ("White space: bottom", f"{_pt(g.gaps['bottom'])} pt", "")]
    if not g.fits_cell:
        over = -min(g.gaps.values())
        lines.append(("", f"The page sticks out of its space by up to {_pt(over)} pt: that part is cut off "
                          "in the PDF.", "warn"))
    elif not g.fits_area:
        over = max(g.margins[k] - g.gaps[k] for k in g.gaps)
        lines.append(("", f"The page runs into the margins by up to {_pt(over)} pt.", "warn"))
    else:
        lines.append(("", "The page fits inside its margins.", "ok"))
    return lines


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------
class PlacementWindow:
    def __init__(self, app):
        import bf_theme as th
        self.app, self.th = app, th
        self.w = w = tk.Toplevel(app)
        w.title("Adjust page placement")
        w.geometry("1240x820")
        w.minsize(860, 560)
        w.configure(background=th.PAPER)
        w.protocol("WM_DELETE_WINDOW", self.close)
        w.bind("<Escape>", lambda e: self.close())
        self.side_i, self.sel = 0, None          # side shown; selected (side, place index)
        self.info, self.sides, self.error = None, [], ""
        self.src_pdf, self.src_sizes, self.src_sig, self.src_dir, self.doc = None, None, None, None, None
        self.busy_typeset, self.want_typeset, self.gen = False, False, 0
        self.imgs, self.cache = [], {}
        self.real_pages, self.drawn, self.hit = False, [], []
        self.drag = None
        self._pending = None
        self._traces = []
        self._timers = set()
        self._closed = False
        self.fail_sig = None

        top = ttk.Frame(w, padding=(10, 8, 10, 4), style="Paper.TFrame")
        top.pack(fill="x")
        ttk.Button(top, text="◀  Previous side", style="Header.TButton",
                   command=lambda: self.go(self.side_i - 1)).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="Next side  ▶", style="Header.TButton",
                   command=lambda: self.go(self.side_i + 1)).pack(side="left")
        self.side_lbl = ttk.Label(top, style="Paper.TLabel")
        self.side_lbl.pack(side="left", padx=12)
        srow = ttk.Frame(w, padding=(10, 0, 10, 4), style="Paper.TFrame")
        srow.pack(fill="x")
        self.status = ttk.Label(srow, style="PaperHint.TLabel", wraplength=1000, justify="left")
        self.status.pack(side="left", fill="x", expand=True)
        self.status.bind("<Configure>", lambda e: self.status.configure(wraplength=max(200, e.width - 4)))

        body = tk.Frame(w, background=th.PAPER)
        body.pack(fill="both", expand=True)
        right = ttk.Frame(body, padding=(8, 4, 10, 8), style="Paper.TFrame", width=430)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.canvas = tk.Canvas(body, background=th.TROUGH, highlightthickness=0, takefocus=1)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 8))
        self.canvas.bind("<Configure>", lambda e: self.schedule(redraw_only=True))
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        for key, dx, dy in (("<Left>", -1, 0), ("<Right>", 1, 0), ("<Up>", 0, 1), ("<Down>", 0, -1)):
            self.canvas.bind(key, lambda e, dx=dx, dy=dy: self._nudge(dx, dy, 10 if e.state & 1 else 1))

        # controls: the same settings as the Output step (same variables, so both stay in step)
        S = app.S
        ctl = ttk.Frame(right, style="Paper.TFrame")
        ctl.pack(fill="x")
        r = 0

        def label(text, row, col=0):
            ttk.Label(ctl, text=text, style="Paper.TLabel").grid(row=row, column=col, sticky="w", pady=2)
        label("Page scaling", r)
        ttk.Combobox(ctl, textvariable=app.var("imp_scaling"), values=bf_impose.SCALINGS, state="readonly",
                     width=24, style=S("TCombobox")).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        label("Page position", r)
        ttk.Combobox(ctl, textvariable=app.var("imp_position"), values=bf_impose.POSITIONS, state="readonly",
                     width=24, style=S("TCombobox")).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        for key, text, lo in (("imp_fore", "Fore-edge margin (pt)", 0), ("imp_binding", "Binding margin (pt)", 0),
                              ("imp_top", "Top margin (pt)", 0), ("imp_bottom", "Bottom margin (pt)", 0),
                              ("imp_offset_x", "Offset toward fore-edge (pt)", -1),
                              ("imp_offset_y", "Offset toward top (pt)", -1)):
            label(text, r)
            hi = bf_impose.OFFSET_MAX_PT if lo < 0 else bf_impose.MARGIN_MAX_PT
            ttk.Spinbox(ctl, textvariable=app.var(key), from_=-hi if lo < 0 else 0, to=hi, increment=1,
                        width=10, style=S("TSpinbox")).grid(row=r, column=1, sticky="w", padx=6)
            r += 1
        btns = ttk.Frame(ctl, style="Paper.TFrame")
        btns.grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Button(btns, text="Reset offsets", style="Header.TButton", command=self.reset_offsets).pack(side="left")
        ttk.Button(btns, text="Refresh pages", style="Header.TButton",
                   command=lambda: self.refresh_source(force=True)).pack(side="left", padx=6)
        r += 1
        ttk.Label(ctl, text="Offsets move every page: positive = toward the fore-edge / toward the top, "
                            "negative = toward the spine / toward the bottom. Drag a page, or click it and use "
                            "the arrow keys (Shift = 10 pt).", style="PaperHint.TLabel", wraplength=400,
                  justify="left").grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 6))
        df = ttk.Frame(right, style="Paper.TFrame")
        df.pack(fill="both", expand=True)
        self.diag = tk.Text(df, wrap="word", height=30, relief="flat", borderwidth=0, padx=4, pady=4,
                            background=th.PAPER, foreground=th.INK, font=("TkDefaultFont", 9),
                            highlightthickness=0, cursor="arrow")
        dsb = ttk.Scrollbar(df, command=self.diag.yview)
        self.diag.configure(yscrollcommand=dsb.set)
        dsb.pack(side="right", fill="y")
        self.diag.pack(side="left", fill="both", expand=True)
        dark = th.MODE == "dark"
        self.diag.tag_configure("head", font=("TkDefaultFont", 9, "bold"), spacing1=6)
        self.diag.tag_configure("warn", foreground="#F08A84" if dark else "#B83B36")
        self.diag.tag_configure("ok", foreground="#6CC08B" if dark else "#2F7A4B")
        self.diag.tag_configure("label", foreground=th.MUTED)
        bot = ttk.Frame(w, padding=(10, 0, 10, 8), style="Paper.TFrame")
        bot.pack(fill="x")
        ttk.Label(bot, text="All sizes and positions are in points (72 pt = 1 inch). The sheet is drawn to scale; "
                            "shaded strips are the margins, the red line is the spine (the fold).",
                  style="PaperHint.TLabel").pack(side="left")
        ttk.Button(bot, text="Close", style="Header.TButton", command=self.close).pack(side="right")

        for key in DEFAULTS:
            if isinstance(DEFAULTS[key], list):
                continue
            var = app.var(key)
            self._traces.append((var, var.trace_add("write", lambda *a, key=key: self._changed(key))))
        self.refresh_source(force=True)
        self.schedule()
        self._after(1500, self._watch)

    # ---- life
    def _after(self, ms, fn):
        """A timer on this window. Every timer still waiting is cancelled when the window closes: Tk would
        otherwise run it later, after its callback is gone (or replaced by another one of the same name)."""
        box = []

        def run():
            self._timers.discard(box[0] if box else None)
            fn()
        try:
            tid = self.w.after(ms, run)
        except tk.TclError:
            return None
        box.append(tid)
        self._timers.add(tid)
        return tid

    def alive(self):
        try:
            return bool(self.w.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        self._closed = True
        for tid in list(self._timers) + ([self._pending] if self._pending else []):
            try:
                self.w.after_cancel(tid)
            except (tk.TclError, ValueError):
                pass
        self._timers, self._pending = set(), None
        for var, tid in self._traces:
            try:
                var.trace_remove("write", tid)
            except tk.TclError:
                pass
        self._traces = []
        self._close_doc()
        if self.src_dir:
            shutil.rmtree(self.src_dir, ignore_errors=True)
        try:
            self.w.destroy()
        except tk.TclError:
            pass
        if getattr(self.app, "placement_win", None) is self:
            self.app.placement_win = None

    def _close_doc(self):
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None
        self.cache = {}

    # ---- settings -> placement
    def settings(self):
        """The current settings, with the margin and offset boxes as typed (so typing mistakes are reported
        instead of silently replaced)."""
        s = self.app.collect()
        for key in PLACEMENT_KEYS:
            s[key] = self.app._raw(key)
        return s

    def _changed(self, key):
        if not self.alive():
            return
        self.schedule()
        if key not in SHEET_ONLY_KEYS:
            self.want_typeset = True
            self._after(900, lambda g=self.gen: self._maybe_typeset(g))
        self.gen += 1

    def _maybe_typeset(self, gen):
        if self.alive() and self.want_typeset and gen == self.gen - 1:
            self.refresh_source()

    def _watch(self):
        """Every 1.5 s: set the pages again when something that isn't a setting box changed them (text boxes
        such as the dedication, edits to the chapters, a newly read source), so old pages are never shown as
        current."""
        if not self.alive():
            return
        try:
            sig = self.typeset_sig(self.app.collect())
            if not self.busy_typeset and not self.drag and sig != self.fail_sig and (
                    self.src_sizes is None or self.src_sig != sig):
                self.refresh_source()
        finally:
            if self.alive():
                self._after(1500, self._watch)

    def book_changed(self):
        """The app read a new source or opened a project: set the pages again."""
        if self.alive():
            self.src_sig = None
            self.refresh_source(force=True)
            self.schedule()

    def schedule(self, redraw_only=False):
        if self._pending is not None:
            try:
                self.w.after_cancel(self._pending)
            except tk.TclError:
                pass
        try:
            self._pending = self.w.after(40, self.update)
        except tk.TclError:
            self._pending = None

    def page_source(self, s):
        """(sizes of the source pages, whether they show the book's real pages). Before the pages are typeset
        (or while they're being typeset again) the finished page size from the settings is used."""
        if self.src_sizes and self.src_sig == self.typeset_sig(s):
            return self.src_sizes, True
        try:
            w, h = page_size_inches(s)
        except ValueError:
            w, h = 6.0, 9.0
        n = len(self.src_sizes) if self.src_sizes else PLACEHOLDER_PAGES
        return [(w * 72, h * 72)] * n, False

    def typeset_sig(self, s):
        """What the source pages depend on: the book (and its edits) and every setting except the ones that
        only change how pages go on the sheets."""
        if getattr(self.app.book, "fixed_pdf", ""):         # a PDF kept as it is: only blank pages change it
            keep = {k: s.get(k) for k in ("blank_pages_start", "blank_pages_end")}
        else:
            keep = {k: v for k, v in s.items() if k not in SHEET_ONLY_KEYS and k not in PLACEMENT_KEYS}
        return (id(self.app.book), getattr(self.app, "book_rev", 0), repr(sorted(keep.items(), key=str)))

    def update(self):
        self._pending = None
        if not self.alive():
            return
        s = self.settings()
        sizes, real = self.page_source(s)
        self.real_pages = real
        try:
            info, sides = bf_impose.plan_imposition(sizes, s, log=lambda m: None)
            self.info, self.sides, self.error = info, sides, ""
        except ValueError as e:
            self.error = str(e)
        if self.sides:
            self.side_i = max(0, min(self.side_i, len(self.sides) - 1))
        self.draw()

    # ---- the source pages (typeset in the background, exactly as the printing files are)
    def refresh_source(self, force=False):
        if self.busy_typeset:
            self.want_typeset = True
            return
        app = self.app
        if force and not app._commit_editor():          # only when asked: never interrupts typing
            return
        s = app.collect()
        if not force and self.src_sizes and self.src_sig == self.typeset_sig(s):
            self.want_typeset = False
            return
        src_ok = (s["source_mode"] == "paste" and s.get("paste_text", "").strip()) or \
                 (s["source_mode"] == "file" and os.path.exists(s.get("source_path", "")))
        if app.book is None and not src_ok:
            self.status.configure(text="No source yet: the pages are shown as plain pages of the chosen size.")
            self.src_sizes, self.src_sig, self.src_pdf = [], self.typeset_sig(s), None
            return
        self.busy_typeset, self.want_typeset = True, False
        self.status.configure(text="Setting the pages…")
        sig = self.typeset_sig(s)
        book = app.book
        result = {}

        def work():
            d = None
            try:
                import bf_build
                b = copy.copy(book) if book is not None else load_book(s, s.get("paste_text", ""), log=lambda m: None)
                ss = dict(s)
                apply_info(b, ss)
                d = tempfile.mkdtemp(prefix="BookForge placement ")
                pdf = os.path.join(d, "pages.pdf")
                bf_build.typeset(b, ss, pdf, log=lambda m: None)
                from pypdf import PdfReader
                result["sizes"] = [(float(p.mediabox.width), float(p.mediabox.height)) for p in PdfReader(pdf).pages]
                result["pdf"], result["dir"] = pdf, d
                if self._closed:                       # the window was closed meanwhile: tidy up here
                    shutil.rmtree(d, ignore_errors=True)
            except Exception as e:                     # shown in the window; the build reports it too
                result["error"] = str(e)
                if d:
                    shutil.rmtree(d, ignore_errors=True)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if not self.alive():
                if result.get("dir"):
                    shutil.rmtree(result["dir"], ignore_errors=True)
                return
            if t.is_alive():
                self._after(120, poll)
                return
            self.busy_typeset = False
            if "error" in result:
                self.fail_sig = sig                         # not tried again until something changes
                self.status.configure(text=f"The pages couldn't be set: {result['error']}")
            else:
                self._close_doc()
                if self.src_dir:
                    shutil.rmtree(self.src_dir, ignore_errors=True)
                self.src_pdf, self.src_sizes, self.src_dir, self.src_sig = (result["pdf"], result["sizes"],
                                                                           result["dir"], sig)
                self.status.configure(text=f"Showing the book's {len(self.src_sizes)} pages as they will print.")
            if self.want_typeset:
                self.refresh_source()
            self.schedule()
        self._after(120, poll)

    # ---- drawing
    def go(self, i):
        if self.sides:
            self.side_i = max(0, min(i, len(self.sides) - 1))
            self.sel = None
            self.draw()

    def view(self):
        cw, ch = max(50, self.canvas.winfo_width()), max(50, self.canvas.winfo_height())
        W, H = self.info["sheet"]
        return fit_view(W, H, cw, ch)

    def page_image(self, si, g, wpx, hpx):
        from PIL import Image
        key = (si, g.ang, wpx, hpx)
        if key in self.cache:
            return self.cache[key]
        if self.doc is None:
            import pypdfium2 as pdfium
            self.doc = pdfium.PdfDocument(self.src_pdf)
        page = self.doc[si]
        pw, ph = page.get_size()
        rw, rh = (ph, pw) if g.ang in (90, 270) else (pw, ph)
        scale = max(wpx / rw, hpx / rh, 0.05) * 1.3
        im = page.render(scale=min(scale, 4)).to_pil().convert("RGB")
        if g.ang:
            im = im.rotate(g.ang, expand=True)               # PIL turns counter-clockwise, like the PDF
        im = im.resize((max(1, wpx), max(1, hpx)), Image.LANCZOS)
        if len(self.cache) > 600:
            self.cache = {}
        self.cache[key] = im
        return im

    def draw(self):
        from PIL import ImageTk
        try:
            from PIL import _tkinter_finder  # noqa: F401  (Pillow finds Tk through it; PyInstaller bundles it)
        except ImportError:
            pass
        c = self.canvas
        c.delete("all")
        self.imgs = []
        self.hit = []
        self.drawn = []          # (source page, place index, page rectangle, visible part) in canvas pixels
        if self.error or not self.info or not self.sides:
            c.create_text(20, 20, anchor="nw", text=self.error or "Nothing to show yet.", fill="#D9534F",
                          width=max(200, c.winfo_width() - 40))
            self.show_diag([("", self.error, "warn")] if self.error else [])
            return
        info, side = self.info, self.sides[self.side_i]
        W, H = info["sheet"]
        view = self.view()
        k = view[0]
        x1, y1, x2, y2 = rect_to_screen(view, H, 0, 0, W, H)
        c.create_rectangle(x1 + 4, y1 + 4, x2 + 4, y2 + 4, fill="#9A968E", outline="")             # shadow
        c.create_rectangle(x1, y1, x2, y2, fill="white", outline="#777777", tags=("sheet",))
        n = len(self.sides)
        if side.get("face"):
            what = f"sheet {side['sheet'] + 1} of signature {side['sig'] + 1}" if info.get("plan") else "sheet"
        else:
            what = "sheet"
        self.side_lbl.configure(text=f"Side {self.side_i + 1} of {n} — {what}, "
                                     f"{'first' if side['front'] else 'second'} side — "
                                     f"{_pt(W)} × {_pt(H)} pt — shown at {k * 72:.1f} pixels per inch")
        cells = []
        if "rows" not in side:
            for it in side["items"]:
                cells.append(it["geo"])
        else:
            for _si, g in side["places"]:
                cells.append(g)
        # cells, margins, spine
        for g in cells:
            cx1, cy1, cx2, cy2 = rect_to_screen(view, H, *g.cell)
            c.create_rectangle(cx1, cy1, cx2, cy2, fill="#F3E3D3" if g.kind == "fold" else "white",
                               outline="#B8B0A4", dash=(3, 3))
            if g.kind == "fold":
                ax1, ay1, ax2, ay2 = rect_to_screen(view, H, *g.area)
                c.create_rectangle(ax1, ay1, ax2, ay2, fill="white", outline="")
                sx_ = cx1 if g.bind == "L" else cx2
                c.create_line(sx_, cy1, sx_, cy2, fill="#C0392B", width=2)
                hy = cy1 + 9 if g.rot == 0 else cy2 - 9
                c.create_text((cx1 + cx2) / 2, hy, text="top", fill="#8A8278", font=("TkDefaultFont", 7),
                              angle=0 if g.rot == 0 else 180)
        # pages
        for idx, (si, g) in enumerate(side["places"]):
            px1, py1, px2, py2 = rect_to_screen(view, H, g.x, g.y, g.w, g.h)
            cx1, cy1, cx2, cy2 = rect_to_screen(view, H, *g.cell)
            vx1, vy1, vx2, vy2 = max(px1, cx1), max(py1, cy1), min(px2, cx2), min(py2, cy2)   # clipped like the PDF
            wpx, hpx = int(round(px2 - px1)), int(round(py2 - py1))
            drawn = False
            if self.real_pages and self.src_pdf and wpx >= 2 and hpx >= 2 and vx2 > vx1 and vy2 > vy1:
                try:
                    im = self.page_image(si, g, wpx, hpx)
                    crop = im.crop((int(round(vx1 - px1)), int(round(vy1 - py1)),
                                    max(int(round(vx1 - px1)) + 1, int(round(vx2 - px1))),
                                    max(int(round(vy1 - py1)) + 1, int(round(vy2 - py1)))))
                    ph = ImageTk.PhotoImage(crop)
                    self.imgs.append(ph)
                    c.create_image(vx1, vy1, image=ph, anchor="nw")
                    drawn = True
                except Exception:
                    drawn = False
            if not drawn and vx2 > vx1 and vy2 > vy1:
                c.create_rectangle(vx1, vy1, vx2, vy2, fill="#DCE8F5", outline="")
                c.create_text((vx1 + vx2) / 2, (vy1 + vy2) / 2, text=str(si + 1), fill="#4A6FA5",
                              font=("TkDefaultFont", max(7, min(20, int(hpx / 6)))), angle=g.ang if g.ang in (0, 180) else 0)
            sel = self.sel == (self.side_i, idx)
            if not g.fits_cell:
                c.create_rectangle(px1, py1, px2, py2, outline="#D9534F", dash=(4, 3), width=1)
            c.create_rectangle(vx1, vy1, vx2, vy2, outline="#2E6FD8" if sel else "#666666", width=2 if sel else 1,
                               tags=(f"page{idx}",))
            self.hit.append(((vx1, vy1, vx2, vy2), idx))
            self.drawn.append((si, idx, (px1, py1, px2, py2), (vx1, vy1, vx2, vy2)))
        if self.sel is None and side["places"]:
            self.sel = (self.side_i, 0)
            return self.draw()
        g, page_no = None, None
        if self.sel and self.sel[0] == self.side_i and self.sel[1] < len(side["places"]):
            si, g = side["places"][self.sel[1]]
            page_no = si + 1
        lines = diagnostics(info, self.app.collect(), side, g, page_no,
                            fixed=bool(getattr(self.app.book, "fixed_pdf", "")))
        if info.get("placement_warning"):
            lines.insert(0, ("", info["placement_warning"], "warn"))
        if info.get("warning"):
            lines.insert(0, ("", info["warning"], "warn"))
        if not self.app.var("fmt_impose").get():
            lines.insert(0, ("", "\u201cImposed PDF for binding\u201d isn't ticked on the Output step, so no printing "
                                 "sheets are made. Tick it to print the pages like this.", "warn"))
        if not self.real_pages:
            lines.insert(0, ("", "The pages are being set with your current settings; until then they are shown "
                                 "as plain pages of the finished size." if self.busy_typeset else
                             "Showing plain pages of the finished size (numbered).", "warn" if self.busy_typeset else ""))
        self.show_diag(lines)

    def show_diag(self, lines):
        t = self.diag
        top = t.yview()[0]
        t.configure(state="normal")
        t.delete("1.0", "end")
        for label, value, kind in lines:
            if kind == "head":
                t.insert("end", label + "\n", "head")
            elif label:
                t.insert("end", label + ": ", "label")
                t.insert("end", value + "\n", kind or ())
            else:
                t.insert("end", value + "\n", kind or ())
        t.configure(state="disabled")
        t.yview_moveto(top)

    # ---- mouse and keyboard
    def _at(self, x, y):
        for (x1, y1, x2, y2), idx in reversed(getattr(self, "hit", [])):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx
        return None

    def _offsets(self):
        try:
            return (float(self.app.var("imp_offset_x").get()), float(self.app.var("imp_offset_y").get()))
        except (tk.TclError, ValueError):
            return (0.0, 0.0)

    def _press(self, e):
        self.canvas.focus_set()
        idx = self._at(e.x, e.y)
        if idx is None:
            self.drag = None
            return
        self.sel = (self.side_i, idx)
        _si, g = self.sides[self.side_i]["places"][idx]
        self.drag = {"x": e.x, "y": e.y, "start": self._offsets(), "g": g, "k": self.view()[0]}
        self.draw()

    def _motion(self, e):
        d = self.drag
        if not d or d["g"].kind != "fold":
            return
        ox, oy = offsets_after_drag(d["g"], d["start"], e.x - d["x"], e.y - d["y"], d["k"])
        self.app.var("imp_offset_x").set(ox)
        self.app.var("imp_offset_y").set(oy)

    def _release(self, _e):
        self.drag = None

    def _nudge(self, dx, dy, step):
        if not self.sel or not self.sides:
            return
        _si, g = self.sides[self.side_i]["places"][self.sel[1]]
        if g.kind != "fold":
            return
        ox, oy = nudge(g, self._offsets(), dx * step, dy * step)
        self.app.var("imp_offset_x").set(ox)
        self.app.var("imp_offset_y").set(oy)

    def reset_offsets(self):
        self.app.var("imp_offset_x").set(0.0)
        self.app.var("imp_offset_y").set(0.0)
