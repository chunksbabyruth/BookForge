"""BookForge fonts: find installed font families, register them for PDF output.

* Every installed font is offered, grouped the way Windows groups them
  (family + Regular / Italic / Bold / Bold Italic), so e.g. "EB Garamond Medium"
  appears as its own family whose italic is Medium Italic.
* Users can define their own families from any four font files.
* OpenType fonts with PostScript (CFF) outlines and WOFF web fonts are converted
  to TrueType on the fly (cached), because the PDF engine only embeds TrueType.
"""
import hashlib
import json
import os
import re

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont

BUILTIN = {
    "Times (built-in)": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "Helvetica (built-in)": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "Courier (built-in)": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
}
BUILTIN_NAMES = {n for v in BUILTIN.values() for n in v}
SAME_BODY = "Same as body text"
SAME_HEAD = "Same as headings"
STYLES = ("R", "B", "I", "BI")
FONT_EXT = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")


# --------------------------------------------------------------------------
# Fonts that ship with BookForge (SIL Open Font License, original files from
# github.com/google/fonts, unmodified; licences in fonts/<folder>/OFL.txt).
# Most are variable fonts: genuine static Regular/Bold instances are made on the user's
# PC the first time they are used (cached), never faked. Missing styles stay missing.
# --------------------------------------------------------------------------
INCLUDED = {   # name: (folder, upright file, italic file or None, use)
    "EB Garamond": ("ebgaramond", "EBGaramond[wght].ttf", "EBGaramond-Italic[wght].ttf", "book"),
    "Crimson Pro": ("crimsonpro", "CrimsonPro[wght].ttf", "CrimsonPro-Italic[wght].ttf", "book"),
    "Source Serif 4": ("sourceserif4", "SourceSerif4[opsz,wght].ttf", "SourceSerif4-Italic[opsz,wght].ttf", "book"),
    "Libre Baskerville": ("librebaskerville", "LibreBaskerville[wght].ttf", "LibreBaskerville-Italic[wght].ttf",
                          "book"),
    "Libre Caslon Text": ("librecaslontext", "LibreCaslonText[wght].ttf", "LibreCaslonText-Italic[wght].ttf",
                          "book"),
    "Literata": ("literata", "Literata[opsz,wght].ttf", "Literata-Italic[opsz,wght].ttf", "book"),
    "Lora": ("lora", "Lora[wght].ttf", "Lora-Italic[wght].ttf", "book"),
    "Alegreya": ("alegreya", "Alegreya[wght].ttf", "Alegreya-Italic[wght].ttf", "book"),
    "Cormorant Garamond": ("cormorantgaramond", "CormorantGaramond[wght].ttf",
                           "CormorantGaramond-Italic[wght].ttf", "display"),
    "Cinzel": ("cinzel", "Cinzel[wght].ttf", None, "display"),
    "IM Fell English": ("imfellenglish", "IMFeENrm28P.ttf", "IMFeENit28P.ttf", "display"),
    "Playfair Display": ("playfairdisplay", "PlayfairDisplay[wght].ttf", "PlayfairDisplay-Italic[wght].ttf",
                         "display"),
}
# Requested fonts that are commercial / come with Windows or Office: they can't be shipped, but
# appear in the font lists automatically once installed on the PC (or added with "My fonts...").
NOT_INCLUDED = ["Garamond", "Palatino Linotype", "Book Antiqua", "Georgia", "Baskerville", "Caslon",
                "Minion Pro", "Bembo", "Sabon"]


def included_dir():
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "fonts")


def included_families():
    """Included families whose files are present (book fonts first, then title/display fonts)."""
    d = included_dir()
    names = [n for n, v in INCLUDED.items() if os.path.exists(os.path.join(d, v[0], v[1]))]
    return sorted(names, key=lambda n: (INCLUDED[n][3] != "book", n.lower()))


def _set_style_names(ft, italic, weight):
    """Give a generated instance its own style names; fonts that share a PostScript name get merged
    into one in a PDF, which would silently turn Bold back into Regular."""
    name = ft["name"]
    fam = name.getDebugName(16) or name.getDebugName(1) or "Font"
    sub = {(False, 400): "Regular", (False, 700): "Bold", (True, 400): "Italic", (True, 700): "Bold Italic"}[
        (italic, weight)]
    ps_base = re.sub(r"[^A-Za-z0-9]", "", fam)
    for rec in list(name.names):
        if rec.nameID in (1, 16):
            rec.string = fam
        elif rec.nameID in (2, 17):
            rec.string = sub
        elif rec.nameID == 4:
            rec.string = f"{fam} {sub}"
        elif rec.nameID == 6:
            rec.string = f"{ps_base}-{sub.replace(' ', '')}"


def _static(path, weight, italic=False):
    """A genuine static instance of a variable font at `weight` (None if out of range / not variable)."""
    from fontTools.ttLib import TTFont as FT
    ft = FT(path, lazy=True)
    if "fvar" not in ft:
        return path if weight == 400 else None
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in ft["fvar"].axes}
    lo, _d, hi = axes.get("wght", (weight, weight, weight))
    if not lo <= weight <= hi:
        return None
    st = os.stat(path)
    # keyed on the font file itself (name + size), not its location: the single-file program
    # unpacks to a new temporary folder every time it starts
    key = hashlib.sha1(f"v3|{os.path.basename(path)}|{weight}|{italic}|{st.st_size}".encode()).hexdigest()[:12]
    cdir = os.path.join(appdata_dir(), "fontcache")
    os.makedirs(cdir, exist_ok=True)
    out = os.path.join(cdir, f"inc_{key}.ttf")
    if not os.path.exists(out):
        from fontTools.varLib import instancer
        loc = {tag: (weight if tag == "wght" else dflt) for tag, (_mn, dflt, _mx) in axes.items()}
        inst = instancer.instantiateVariableFont(FT(path), loc)
        _set_style_names(inst, italic, weight)
        inst.save(out)
    return out


def included_files(name):
    """{"R": (path, 0), ...} with only the styles this family genuinely has."""
    folder, up, it, _use = INCLUDED[name]
    d = os.path.join(included_dir(), folder)
    files = {}
    for sty, fname, w in (("R", up, 400), ("B", up, 700), ("I", it, 400), ("BI", it, 700)):
        if fname and os.path.exists(os.path.join(d, fname)):
            p = _static(os.path.join(d, fname), w, italic=sty in ("I", "BI"))
            if p:
                files[sty] = (p, 0)
    return files


def appdata_dir():
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "BookForge")
    os.makedirs(d, exist_ok=True)
    return d


def font_dirs():
    dirs = []
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs.append(os.path.join(win, "Fonts"))
    la = os.environ.get("LOCALAPPDATA")
    if la:
        dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    if os.name != "nt":
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
    return [d for d in dirs if os.path.isdir(d)]


def font_files():
    out = []
    for d in font_dirs():
        for root, _sub, files in os.walk(d):
            for f in files:
                if f.lower().endswith(FONT_EXT):
                    out.append(os.path.join(root, f))
    return out


# --------------------------------------------------------------------------
# Reading font names
# --------------------------------------------------------------------------
def _style_of(sub):
    s = sub.lower().replace("-", " ").strip()
    if s in ("regular", "normal", "roman", "book", "plain", "standard"):
        return "R"
    if s in ("italic", "oblique", "regular italic", "book italic"):
        return "I"
    if s == "bold":
        return "B"
    if s in ("bold italic", "bold oblique", "bolditalic"):
        return "BI"
    return None


def _name(ft, nid):
    t = ft["name"]
    rec = t.getName(nid, 3, 1, 0x409) or t.getName(nid, 1, 0, 0) or t.getName(nid, 3, 1)
    if rec is None:
        for r in t.names:
            if r.nameID == nid:
                rec = r
                break
    try:
        return rec.toUnicode().strip() if rec else ""
    except Exception:
        return ""


def read_faces(path):
    """[(family, subfamily, index, restricted)] for one font file."""
    from fontTools.ttLib import TTFont as FT, TTCollection
    faces = []
    low = path.lower()
    if low.endswith((".ttc", ".otc")):
        coll = TTCollection(path, lazy=True)
        fonts = list(enumerate(coll.fonts))
    else:
        fonts = [(0, FT(path, lazy=True))]
    for idx, ft in fonts:
        try:
            fam, sub = _name(ft, 1), _name(ft, 2)
            fs = ft["OS/2"].fsType if "OS/2" in ft else 0
            restricted = bool(fs & 0x0002) and not (fs & 0x000C)
            if fam:
                faces.append((fam, sub, idx, restricted))
        except Exception:
            continue
    return faces


_FAMILIES = None


def scan_installed(force=False):
    """{family: {"R": [path, index], "I": ..., "B": ..., "BI": ...}} for installed fonts (cached)."""
    global _FAMILIES
    if _FAMILIES is not None and not force:
        return _FAMILIES
    cache_path = os.path.join(appdata_dir(), "font_cache.json")
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    new_cache, fams = {}, {}
    for p in font_files():
        try:
            st = os.stat(p)
            sig = [st.st_mtime, st.st_size]
        except OSError:
            continue
        ent = cache.get(p)
        if ent and ent[0] == sig:
            faces = ent[1]
        else:
            try:
                faces = read_faces(p)
            except Exception:
                faces = []
        new_cache[p] = [sig, faces]
        for fam, sub, idx, restricted in faces:
            sty = _style_of(sub)
            if not sty or restricted:
                continue
            fams.setdefault(fam, {}).setdefault(sty, [p, idx])
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(new_cache, f)
    except Exception:
        pass
    _FAMILIES = {k: v for k, v in fams.items() if "R" in v}
    return _FAMILIES


def list_families(custom=(), installed=True):
    names = list(BUILTIN)
    names += [n for n in included_families() if n not in names]
    names += [c["name"] for c in custom if c.get("name") and c["name"] not in names]
    if installed:
        seen = set(names)
        names += sorted((f for f in scan_installed() if f not in seen), key=str.lower)
    return names


# --------------------------------------------------------------------------
# Converting fonts the PDF engine can't embed directly
# --------------------------------------------------------------------------
def _otf_to_ttf(ft):
    """Convert a CFF-flavoured OpenType font (in memory) to TrueType outlines."""
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable
    order = ft.getGlyphOrder()
    gs = ft.getGlyphSet()
    glyphs = {}
    for g in order:
        pen = TTGlyphPen(gs)
        gs[g].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyphs[g] = pen.glyph()
    ft["loca"] = newTable("loca")
    ft["glyf"] = glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    del ft["CFF "]
    if "VORG" in ft:
        del ft["VORG"]
    glyf.compile(ft)
    hmtx = ft["hmtx"]
    for name, g in glyf.glyphs.items():
        if hasattr(g, "xMin"):
            hmtx[name] = (hmtx[name][0], g.xMin)
    ft["maxp"] = maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for a in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
              "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions"):
        setattr(maxp, a, 1 if a == "maxZones" else 0)
    maxp.maxComponentElements = max([len(getattr(g, "components", []) or []) for g in glyphs.values()] + [0])
    maxp.compile(ft)
    post = ft["post"]
    post.formatType = 2.0
    post.extraNames, post.mapping, post.glyphOrder = [], {}, order
    try:
        post.compile(ft)
    except OverflowError:
        post.formatType = 3.0
    ft.sfntVersion = "\000\001\000\000"


def embeddable(path, index=0):
    """Return (path, index) of a TrueType file reportlab can embed, converting if needed."""
    from fontTools.ttLib import TTFont as FT
    low = path.lower()
    needs = low.endswith((".otf", ".otc", ".woff", ".woff2"))
    if low.endswith((".ttc", ".ttf")) and not needs:
        with open(path, "rb") as f:
            head = f.read(4) if low.endswith(".ttf") else b""
        needs = head == b"OTTO"
        if low.endswith(".ttc"):
            ft = FT(path, fontNumber=index, lazy=True)
            needs = "CFF " in ft or "CFF2" in ft
    if not needs:
        return path, index
    st = os.stat(path)
    key = hashlib.sha1(f"{path}|{index}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()[:16]
    cdir = os.path.join(appdata_dir(), "fontcache")
    os.makedirs(cdir, exist_ok=True)
    out = os.path.join(cdir, key + ".ttf")
    if os.path.exists(out):
        return out, 0
    ft = FT(path, fontNumber=index)
    ft.flavor = None
    if "CFF2" in ft:
        raise ValueError("variable OpenType (CFF2) fonts aren't supported; use a static font file")
    if "CFF " in ft:
        _otf_to_ttf(ft)
    ft.save(out)
    return out, 0


# --------------------------------------------------------------------------
# Registering families with the PDF engine
# --------------------------------------------------------------------------
def _register_one(name, path, index):
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    p, i = embeddable(path, index)
    kw = {"subfontIndex": i} if p.lower().endswith((".ttc", ".otc")) else {}
    pdfmetrics.registerFont(TTFont(name, p, **kw))
    return name


def register_family(display, files):
    """files: {"R": (path, index), ...}. Returns (regular, bold, italic, bolditalic) names."""
    tag = "BF_" + re.sub(r"\W", "", display)[:40] + "_" + hashlib.sha1(
        repr(sorted(files.items())).encode()).hexdigest()[:6]
    names = {}
    for sty in STYLES:
        if files.get(sty):
            path, idx = files[sty][0], int(files[sty][1]) if len(files[sty]) > 1 else 0
            names[sty] = _register_one(f"{tag}-{sty}", path, idx)
    r = names["R"]
    b = names.get("B", r)
    i = names.get("I", r)
    bi = names.get("BI") or (b if "B" in names else i)
    registerFontFamily(r, normal=r, bold=b, italic=i, boldItalic=bi)
    return r, b, i, bi


def migrate(s):
    """Settings from BookForge 1.0-1.2 used one 'custom font file' path; turn it into a family."""
    if s.get("font_family") == "Custom font file (.ttf)..." and s.get("custom_font_path"):
        fams = list(s.get("custom_fonts") or [])
        if not any(c.get("name") == "My font" for c in fams):
            fams.append({"name": "My font", "R": s["custom_font_path"]})
        s["custom_fonts"] = fams
        s["font_family"] = "My font"
    return s


def resolve(display, s, log=print):
    """Turn a family name from the dropdown into reportlab font names."""
    if display in BUILTIN:
        return BUILTIN[display]
    custom = {c.get("name"): c for c in s.get("custom_fonts") or []}
    if display in INCLUDED and display not in custom:
        try:
            import time
            t0 = time.time()
            files = included_files(display)
            if time.time() - t0 > 1:
                log(f'Prepared the included font "{display}" (first use only - it is saved for next time).')
        except Exception as e:
            files = {}
            log(f'WARNING: couldn\'t prepare the included font "{display}" ({e}).')
        if "R" not in files:
            log(f'WARNING: the included font "{display}" is missing from this copy of BookForge, so Times was used.')
            return BUILTIN["Times (built-in)"]
        missing = [lab for k, lab in (("B", "bold"), ("I", "italic"), ("BI", "bold italic")) if k not in files]
        if missing:
            log(f'Note: "{display}" has no {", ".join(missing)} style; the nearest real style is used '
                f'(nothing is faked).')
        try:
            return register_family(display, files)
        except Exception as e:
            log(f'WARNING: couldn\'t use the font "{display}" ({e}), so Times was used.')
            return BUILTIN["Times (built-in)"]
    if display in custom:
        c = custom[display]
        files = {k: (c[k], 0) for k in STYLES if c.get(k) and os.path.exists(c[k])}
        if "R" not in files:
            log(f'WARNING: the regular file for your font "{display}" is missing, so Times was used.')
            return BUILTIN["Times (built-in)"]
    else:
        files = scan_installed().get(display)
        if not files:
            log(f'WARNING: font "{display}" isn\'t installed on this PC, so Times was used.')
            return BUILTIN["Times (built-in)"]
        files = {k: tuple(v) for k, v in files.items()}
    try:
        return register_family(display, files)
    except Exception as e:
        msg = str(e)
        if "embed" in msg.lower():
            msg = "its license doesn't allow it to be embedded in PDFs"
        log(f'WARNING: couldn\'t use the font "{display}" ({msg}), so Times was used.')
        return BUILTIN["Times (built-in)"]
