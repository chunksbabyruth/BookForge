"""BookForge "Keep the source's own fonts, sizes, colours and alignment". No window code here.

The book's normal text always follows the Layout settings. What this keeps is where the SOURCE made text
look different from its own normal text: words in another font, bigger or smaller words (kept as a
percentage, so they still follow the book's text size), coloured words, and centred, right-aligned or
indented paragraphs. The readers (Word, EPUB/HTML, rebuilt PDF) call these helpers when the option is on.
"""
import re
import threading

GENERIC = {"serif", "sans-serif", "sans serif", "monospace", "cursive", "fantasy", "system-ui", "inherit",
           "initial", "default"}
NAMED = {"red": "#ff0000", "darkred": "#8b0000", "maroon": "#800000", "blue": "#0000ff", "navy": "#000080",
         "darkblue": "#00008b", "green": "#008000", "darkgreen": "#006400", "purple": "#800080",
         "gray": "#808080", "grey": "#808080", "dimgray": "#696969", "silver": "#c0c0c0", "orange": "#ffa500",
         "brown": "#a52a2a", "teal": "#008080", "olive": "#808000", "crimson": "#dc143c", "magenta": "#ff00ff",
         "darkorange": "#ff8c00", "gold": "#ffd700", "indigo": "#4b0082", "firebrick": "#b22222"}
SIZE_WORDS = {"xx-small": 60, "x-small": 75, "small": 89, "smaller": 83, "medium": 100, "large": 120,
              "larger": 120, "x-large": 150, "xx-large": 200}


# --------------------------------------------------------------------------- small helpers
def pct(size, base):
    """A size relative to the source's normal text, as a whole percentage - or None if about the same."""
    try:
        p = round(float(size) / float(base) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if 90 <= p <= 111 or p <= 0:
        return None
    return max(40, min(p, 400))


def colour(c):
    """'#RRGGBB' for a colour worth keeping (not black, near-black or white), else ''."""
    if not c:
        return ""
    c = c.strip().lower()
    c = NAMED.get(c, c)
    m = re.fullmatch(r"#([0-9a-f]{3})", c)
    if m:
        c = "#" + "".join(x * 2 for x in m.group(1))
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", c)
    if m:
        c = "#%02x%02x%02x" % tuple(min(255, int(x)) for x in m.groups())
    if not re.fullmatch(r"#[0-9a-f]{6}", c):
        return ""
    rgb = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    if max(rgb) <= 60 or min(rgb) >= 235:
        return ""
    return c


def face(name):
    """A font family worth keeping (not a generic family), else ''."""
    if not name:
        return ""
    n = name.split(",")[0].strip().strip("'\"").strip()
    n = re.sub(r"^[A-Z]{6}\+", "", n)                     # PDF subset prefix
    return "" if not n or n.lower() in GENERIC else n


_ALIASES = {"times": "Times (built-in)", "timesnewroman": "Times (built-in)", "timesroman": "Times (built-in)",
            "arial": "Helvetica (built-in)", "helvetica": "Helvetica (built-in)", "courier": "Courier (built-in)",
            "couriernew": "Courier (built-in)"}
_fams = {}


def _key(n):
    n = re.sub(r"[-,_ ](regular|bold|italic|oblique|semibold|demibold|light|medium|black|heavy|condensed|book)\b.*$",
               "", n, flags=re.I)
    k = re.sub(r"[^a-z0-9]", "", n.lower())
    return re.sub(r"(psmt|mt|ps)$", "", k)


def usable_face(name):
    """The font family BookForge can use for a source's font name (installed, included or built in), or ''
    - fonts that aren't available are left out, so that text simply uses the book's font."""
    n = face(name)
    if not n:
        return ""
    if not _fams:
        try:
            import bf_fonts
            for f in bf_fonts.list_families(installed=True):
                _fams.setdefault(_key(f.replace(" (built-in)", "")), f)
        except Exception:
            pass
    k = _key(n)
    return _fams.get(k) or _ALIASES.get(k, "")


def font_open(face_name="", size_pct=None, color=""):
    """('<font ...>', '</font>') for the kept look, or ('', '')."""
    from bf_core import esc
    a = ""
    if face_name:
        a += f' face="{esc(face_name)}"'
    if size_pct:
        a += f' size="{int(size_pct)}%"'
    if color:
        a += f' color="{color}"'
    return (f"<font{a}>", "</font>") if a else ("", "")


def indent_steps(inches):
    """A left indent in inches -> the editor's indent steps (0.25 in each), 0 for small ones."""
    try:
        n = round(float(inches) / 0.25)
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, 8)) if float(inches) >= 0.2 else 0


# --------------------------------------------------------------------------- CSS (EPUB / HTML)
def _decls(text):
    out = {}
    for part in (text or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip().replace("!important", "").strip()
    return out


def css_rules(css):
    """Simple class rules from a stylesheet: {'center': {'text-align': 'center'}, ...}. Only `.class` and
    `tag.class` selectors are used (that is how e-books mark styled text)."""
    rules = {}
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    css = re.sub(r"@media[^{]*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", r"\1", css)
    for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        d = _decls(body)
        for one in sel.split(","):
            one = one.strip()
            m = re.fullmatch(r"[a-zA-Z0-9]*\.([\w-]+)", one)
            if m:
                rules.setdefault(m.group(1), {}).update(d)
    return rules


def css_size(v):
    """A CSS font-size -> % of the surrounding text, or None."""
    v = (v or "").strip().lower()
    if v in SIZE_WORDS:
        return SIZE_WORDS[v]
    m = re.fullmatch(r"([\d.]+)\s*(em|rem|%|pt|px)", v)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return {"em": n * 100, "rem": n * 100, "%": n, "pt": n / 12 * 100, "px": n / 16 * 100}[unit]


def css_length_in(v):
    """A CSS length (em, pt, px, in, %) -> inches (roughly), or 0."""
    m = re.fullmatch(r"(-?[\d.]+)\s*(em|rem|pt|px|in|cm|mm|%)?", (v or "").strip().lower())
    if not m:
        return 0.0
    n, unit = float(m.group(1)), m.group(2) or "px"
    return {"em": n / 6, "rem": n / 6, "pt": n / 72, "px": n / 96, "in": n, "cm": n / 2.54, "mm": n / 25.4,
            "%": n / 100 * 4.5}[unit]


class Context:
    """The styles of one source file (or one EPUB): turns tags into kept fonts and paragraph formatting."""

    def __init__(self, rules=None):
        self.rules = rules or {}

    def _style(self, tag):
        d = {}
        for c in tag.get("class") or []:
            d.update(self.rules.get(c, {}))
        d.update(_decls(tag.get("style") or ""))
        return d

    def span_font(self, tag):
        """('<font ...>', '</font>') for an inline tag's own font, size and colour, or ('', '')."""
        d = self._style(tag)
        if not d:
            return "", ""
        size = css_size(d.get("font-size", ""))
        size = None if size is None or 90 <= size <= 111 else max(40, min(round(size), 400))
        return font_open(usable_face(d.get("font-family", "")), size, colour(d.get("color", "")))

    def block_fmt(self, tag):
        """{'align', 'indent'} for a paragraph-level tag, only what differs from normal text."""
        d = self._style(tag)
        out = {}
        al = (d.get("text-align") or "").lower()
        if al in ("center", "right"):
            out["align"] = al
        ind = indent_steps(css_length_in(d.get("margin-left") or d.get("padding-left") or ""))
        if ind:
            out["indent"] = ind
        return out


_local = threading.local()


def current():
    """The Context while a file is being read with "keep formatting" on, else None."""
    return getattr(_local, "ctx", None)


def set_current(ctx):
    _local.ctx = ctx
