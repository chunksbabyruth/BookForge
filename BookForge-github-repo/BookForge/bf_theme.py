"""BookForge look: tabs are book spines on a shelf, each in its own bookcloth colour.

Colours are muted (no neon, no pure black on pure white) and every text/background
pair meets WCAG AA contrast, so it stays colourful without being hard on the eyes.
"""
import tkinter as tk
from tkinter import ttk

LIGHT = dict(PAPER="#F2F4F7", CARD="#FFFFFF", INK="#2B3440", MUTED="#5E6976", LINE="#D3DAE2",
             TROUGH="#E6EAF0", FIELD_OFF="#F1F3F6", LOG="#E9EDF2", BASE="#FFFFFF", DEEP_MIX="#000000",
             DEEP_T=0.18, SCROLL="#CDD5DE", SCROLL_TROUGH="#EEF1F5", SCROLL_ACT="#B7C1CC", DISABLED="#9AA3AD")
# Dark: soft charcoal (not black), off-white text, the same bookcloth colours toned down
DARK = dict(PAPER="#15181E", CARD="#1F242C", INK="#E1E6EC", MUTED="#9AA5B1", LINE="#3A434E",
            TROUGH="#2A3039", FIELD_OFF="#191D23", LOG="#191D23", BASE="#1F242C", DEEP_MIX="#FFFFFF",
            DEEP_T=0.55, SCROLL="#3A434E", SCROLL_TROUGH="#191D23", SCROLL_ACT="#4B5562", DISABLED="#6B7480")
MODE = "light"
PAPER, CARD, INK, MUTED, LINE, TROUGH = (LIGHT[k] for k in ("PAPER", "CARD", "INK", "MUTED", "LINE", "TROUGH"))
P = dict(LIGHT)


def set_mode(dark):
    """Switch every colour this module hands out between the light and dark palettes."""
    global MODE, P, PAPER, CARD, INK, MUTED, LINE, TROUGH
    MODE = "dark" if dark else "light"
    P = dict(DARK if dark else LIGHT)
    PAPER, CARD, INK, MUTED, LINE, TROUGH = (P[k] for k in ("PAPER", "CARD", "INK", "MUTED", "LINE", "TROUGH"))
BUILD = "#227C79"      # build button (deep teal)
BUILD_HOVER = "#1C6866"
BUILD_DOWN = "#175553"

# (key, tab label, spine colour) -- one bookcloth colour per tab
TABS = [
    ("src", "Source", "#4A6FA5"),        # slate blue
    ("chap", "Chapters", "#3F7F86"),     # sea green
    ("info", "Book info", "#7D5A8E"),    # dusty plum
    ("lay", "Layout", "#5E7F3A"),        # moss green
    ("front", "Front & back", "#94691F"),  # ochre
    ("out", "Output", "#B0505C"),        # rose madder
]

UI = "Segoe UI"
UI_SEMI = ("Segoe UI Semibold", 10)


def mix(hex_color, other="#FFFFFF", t=0.85):
    """Blend hex_color toward `other` by t (0 = colour, 1 = other)."""
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def colors(key):
    spine = dict((k, c) for k, _l, c in TABS)[key]
    if MODE == "dark":
        return {"spine": spine, "page": mix(spine, PAPER, 0.88), "soft": mix(spine, CARD, 0.70),
                "mid": mix(spine, CARD, 0.45), "deep": mix(spine, "#FFFFFF", 0.55)}
    return {"spine": spine, "page": mix(spine, t=0.86), "soft": mix(spine, t=0.78),
            "mid": mix(spine, t=0.62), "deep": mix(spine, "#000000", 0.18)}


_IMAGES = []


def _indicator_images(spine, mid, radio):
    """Soft rounded checkbox / radio images, drawn at 4x and scaled down for smooth edges."""
    from PIL import Image, ImageDraw, ImageTk
    S, k = 18, 4
    out = {}
    for state in ("off", "on", "hover"):
        im = Image.new("RGBA", ((S + 7) * k, S * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        box = (1 * k, 1 * k, (S - 1) * k, (S - 1) * k)
        on = state == "on"
        fill = spine if on else (mix(spine, CARD, 0.80) if state == "hover" else CARD)
        edge = spine if on or state == "hover" else mid
        if radio:
            d.ellipse(box, fill=fill if not on else CARD, outline=edge, width=int(1.6 * k))
            if on:
                r = 4.2 * k
                c = S * k / 2
                d.ellipse((c - r, c - r, c + r, c + r), fill=spine)
        else:
            d.rounded_rectangle(box, radius=3.5 * k, fill=fill, outline=edge, width=int(1.6 * k))
            if on:
                d.line([(4.6 * k, 9.4 * k), (7.6 * k, 12.4 * k), (13.6 * k, 5.6 * k)], fill="#FFFFFF",
                       width=int(2.2 * k), joint="curve")
        im = im.resize((S + 7, S), Image.LANCZOS)
        out[state] = ImageTk.PhotoImage(im)
    _IMAGES.append(out)
    return out


def apply(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(background=PAPER)
    st.configure(".", background=PAPER, foreground=INK, font=(UI, 10), bordercolor=LINE,
                 lightcolor=CARD, darkcolor=LINE, troughcolor=TROUGH, focuscolor=PAPER,
                 selectbackground=mix(BUILD, t=0.8), selectforeground=INK)
    st.configure("Paper.TFrame", background=PAPER)
    st.configure("Paper.TLabel", background=PAPER, foreground=INK)
    st.configure("PaperHint.TLabel", background=PAPER, foreground=MUTED)
    st.configure("Brand.TLabel", background=PAPER, foreground=INK, font=("Georgia", 17, "bold"))
    st.configure("Maker.TLabel", background=PAPER, foreground=MUTED, font=(UI, 10, "italic"))
    st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, bordercolor=LINE,
                 lightcolor=CARD, darkcolor=CARD, rowheight=22)
    st.map("Treeview", background=[("selected", mix(BUILD, CARD, 0.35))], foreground=[("selected", INK)])
    st.configure("Treeview.Heading", background=TROUGH, foreground=INK, bordercolor=LINE, relief="flat",
                 lightcolor=TROUGH, darkcolor=TROUGH, font=UI_SEMI)
    st.map("Treeview.Heading", background=[("active", P["SCROLL"])])
    st.configure("Header.TButton", background=TROUGH, foreground=INK, bordercolor=LINE, lightcolor=TROUGH,
                 darkcolor=TROUGH, font=UI_SEMI, padding=(10, 4))
    st.map("Header.TButton", background=[("active", P["SCROLL"]), ("pressed", P["SCROLL_ACT"])])
    st.configure("Build.TButton", background=BUILD, foreground="#FFFFFF", bordercolor=BUILD,
                 lightcolor=BUILD, darkcolor=BUILD, font=(UI, 12, "bold"), padding=(22, 9))
    st.map("Build.TButton",
           background=[("disabled", "#A9C7C5"), ("pressed", BUILD_DOWN), ("active", BUILD_HOVER)],
           lightcolor=[("pressed", BUILD_DOWN), ("active", BUILD_HOVER)],
           darkcolor=[("pressed", BUILD_DOWN), ("active", BUILD_HOVER)],
           foreground=[("disabled", "#F4F8F8")])
    st.configure("Build.Horizontal.TProgressbar", background=BUILD, troughcolor=TROUGH,
                 bordercolor=TROUGH, lightcolor=BUILD, darkcolor=BUILD)
    st.configure("Vertical.TScrollbar", background=P["SCROLL"], troughcolor=P["SCROLL_TROUGH"],
                 bordercolor=P["SCROLL_TROUGH"], arrowcolor=MUTED, lightcolor=P["SCROLL"], darkcolor=P["SCROLL"])
    st.map("Vertical.TScrollbar", background=[("active", P["SCROLL_ACT"])])

    for key, _label, _c in TABS:
        c = colors(key)
        sp = c["spine"]
        st.configure(f"{key}.Page.TFrame", background=c["page"])
        st.configure(f"{key}.PageHint.TLabel", background=c["page"], foreground=MUTED)
        st.configure(f"{key}.TLabelframe", background=CARD, bordercolor=c["mid"], relief="solid",
                     lightcolor=CARD, darkcolor=CARD)
        st.configure(f"{key}.TLabelframe.Label", background=CARD, foreground=c["deep"], font=UI_SEMI)
        st.configure(f"{key}.Card.TFrame", background=CARD)
        st.configure(f"{key}.Card.TLabel", background=CARD, foreground=INK)
        st.configure(f"{key}.CardHint.TLabel", background=CARD, foreground=MUTED)
        for w, radio in (("TCheckbutton", False), ("TRadiobutton", True)):
            base = w[1:]
            name = f"{key}.Card.{w}"
            el = f"{key}.{base}.indicator.{MODE}"
            try:
                if el not in st.element_names():
                    imgs = _indicator_images(sp, c["mid"], radio)
                    st.element_create(el, "image", imgs["off"], ("selected", imgs["on"]),
                                      ("active", imgs["hover"]))
                st.layout(name, [(f"{base}.padding", {"sticky": "nswe", "children": [
                    (el, {"side": "left", "sticky": ""}),
                    (f"{base}.focus", {"side": "left", "sticky": "w", "children": [
                        (f"{base}.label", {"sticky": "nswe"})]})]})])
            except Exception:
                pass
            st.configure(name, background=CARD, foreground=INK, focuscolor=CARD, padding=(1, 2))
            st.map(name, background=[("active", CARD)], foreground=[("disabled", P["DISABLED"])])
        for w in ("TEntry", "TCombobox", "TSpinbox"):
            st.configure(f"{key}.{w}", fieldbackground=CARD, foreground=INK, bordercolor=LINE,
                         lightcolor=CARD, darkcolor=CARD, arrowcolor=sp, background=c["page"],
                         insertcolor=INK, padding=3)
            st.map(f"{key}.{w}", bordercolor=[("focus", sp)], lightcolor=[("focus", sp)],
                   fieldbackground=[("readonly", CARD), ("disabled", P["FIELD_OFF"])],
                   foreground=[("disabled", P["DISABLED"])],
                   selectbackground=[("readonly", "focus", c["soft"]), ("focus", c["soft"])],
                   selectforeground=[("readonly", "focus", INK), ("focus", INK)],
                   background=[("active", c["soft"])])
        st.configure(f"{key}.TButton", background=c["soft"], foreground=c["deep"], bordercolor=c["mid"],
                     lightcolor=c["soft"], darkcolor=c["soft"], font=UI_SEMI, padding=(10, 4))
        st.map(f"{key}.TButton", background=[("pressed", c["mid"]), ("active", mix(sp, t=0.70))],
               lightcolor=[("pressed", c["mid"]), ("active", mix(sp, t=0.70))],
               darkcolor=[("pressed", c["mid"]), ("active", mix(sp, t=0.70))],
               foreground=[("disabled", P["DISABLED"])])
    # dropdown lists of comboboxes
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", mix(BUILD, CARD, 0.65))
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.font", (UI, 10))
    return st


def style_text(widget, key):
    c = colors(key)
    widget.configure(background=CARD, foreground=INK, relief="flat",
                     highlightthickness=1, highlightbackground=LINE, highlightcolor=c["spine"],
                     selectbackground=c["soft"], selectforeground=INK)
    if isinstance(widget, tk.Text):
        widget.configure(insertbackground=INK)


class ScrollPage(tk.Frame):
    """A tab page that grows to fill the window and scrolls if the window is too small."""

    def __init__(self, master, key):
        c = colors(key)
        super().__init__(master, background=c["page"])
        self.canvas = tk.Canvas(self, background=c["page"], highlightthickness=0, borderwidth=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, padding=10, style=f"{key}.Page.TFrame")
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._fit())
        self.canvas.bind("<Configure>", lambda e: self._fit())

    def _fit(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        need = self.inner.winfo_reqheight()
        self.canvas.itemconfigure(self._win, width=cw, height=max(ch, need))
        self.canvas.configure(scrollregion=(0, 0, cw, max(ch, need)))
        if need > ch + 2:
            if not self.vsb.winfo_ismapped():
                self.vsb.pack(side="right", fill="y")
        elif self.vsb.winfo_ismapped():
            self.vsb.pack_forget()
            self.canvas.yview_moveto(0)

    def wheel(self, delta):
        if self.vsb.winfo_ismapped():
            self.canvas.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")


class Shelf(tk.Canvas):
    """The tab bar: a row of book spines. The open tab is the book pulled up off the shelf."""

    H = 50

    def __init__(self, master, on_select):
        super().__init__(master, height=self.H + 5, background=PAPER, highlightthickness=0,
                         borderwidth=0, cursor="hand2", takefocus=1)
        self.on_select = on_select
        self.current = 0
        self.hover = None
        self.boxes = []
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Left>", lambda e: self.select((self.current - 1) % len(TABS)))
        self.bind("<Right>", lambda e: self.select((self.current + 1) % len(TABS)))

    def select(self, i):
        self.current = i
        self.draw()
        self.on_select(i)

    def _hit(self, x):
        for i, (x0, x1) in enumerate(self.boxes):
            if x0 <= x <= x1:
                return i
        return None

    def _click(self, e):
        self.focus_set()
        i = self._hit(e.x)
        if i is not None:
            self.select(i)

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.draw()

    def _motion(self, e):
        self._set_hover(self._hit(e.x))

    def draw(self):
        self.delete("all")
        self.boxes = []
        w = max(self.winfo_width(), 400)
        gap, x = 6, 10
        font = ("Segoe UI Semibold", 10)
        for i, (key, label, spine) in enumerate(TABS):
            c = colors(key)
            text = f"{i + 1}  {label}"
            tw = max(110, len(text) * 8 + 34)
            active = i == self.current
            top = 0 if active else (6 if i == self.hover else 10)
            fill = spine if active else c["mid"] if i == self.hover else c["soft"]
            txt = "#FFFFFF" if active else c["deep"]
            band = mix(spine, t=0.45) if active else c["mid"]
            self.create_rectangle(x, top, x + tw, self.H, fill=fill, outline=fill)
            for y in (top + 6, self.H - 7):                       # two gilt lines, like a spine
                self.create_line(x + 6, y, x + tw - 6, y, fill=band)
            self.create_text(x + tw / 2, (top + self.H) / 2 + 1, text=text, fill=txt, font=font)
            if active and self.focus_get() is self:
                self.create_rectangle(x + 3, top + 3, x + tw - 3, self.H - 3, outline="#FFFFFF", dash=(2, 2))
            self.boxes.append((x, x + tw))
            x += tw + gap
        self.create_rectangle(0, self.H, w, self.H + 5, fill=TABS[self.current][2], outline="")
