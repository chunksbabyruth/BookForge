"""BookForge exporters: imposition, cover, EPUB, DOCX, HTML, TXT."""
import html
import io
import math
import re
import uuid
import zipfile
from datetime import datetime, timezone

from bf_core import SHEET_SIZES, PAPERS, page_size_inches, plain, esc
from bf_pdf import font_roles, apply_case, auto_label, LABELISH


# --------------------------------------------------------------------------
# Imposition: 2-up folio signatures on landscape sheets (perfect binding)
# --------------------------------------------------------------------------
def impose(pdf_in, out_path, s, log=print):
    from pypdf import PdfReader, PdfWriter, Transformation
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black

    r = PdfReader(pdf_in)
    pages = list(r.pages)
    n = len(pages)
    SW, SH = (v * 72 for v in SHEET_SIZES[s["sheet_size"]])
    half = SW / 2
    sheets = int(s["sig_sheets"])
    sig_pages = (math.ceil(n / 4) * 4) if sheets <= 0 else sheets * 4
    sigs, i = [], 0
    while i < n:
        chunk = list(range(i, min(i + sig_pages, n)))
        while len(chunk) % 4:
            chunk.append(None)
        sigs.append(chunk)
        i += sig_pages
    sides = []
    for si, sig in enumerate(sigs):
        m = len(sig)
        for j in range(m // 4):
            sides.append((sig[m - 1 - 2 * j], sig[2 * j], si, j, True))
            sides.append((sig[2 * j + 1], sig[m - 2 - 2 * j], si, j, False))
    blanks = sum(1 for sig in sigs for x in sig if x is None)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(SW, SH))
    step = 16
    usable = max(1, int((SH - 72) // step))
    for (_, _, si, j, front) in sides:
        if front and s["fold_marks"]:
            c.setLineWidth(0.4)
            c.line(half, SH, half, SH - 14)
            c.line(half, 0, half, 14)
        if front and j == 0 and s["sig_marks"]:
            y = SH - 36 - (si % usable) * step
            c.setFillColor(black)
            c.rect(half - 3, y - 6, 6, 12, fill=1, stroke=0)
            c.setFont("Helvetica", 6)
            c.drawString(half + 5, y - 2, str(si + 1))
        c.showPage()
    c.save()
    ov = PdfReader(io.BytesIO(buf.getvalue()))

    w = PdfWriter()
    for k, side in enumerate(sides):
        pg = w.add_blank_page(SW, SH)
        for slot, pi in enumerate(side[:2]):
            if pi is None:
                continue
            src = pages[pi]
            sw_, sh_ = float(src.mediabox.width), float(src.mediabox.height)
            kk = min(half / sw_, SH / sh_)
            tx = slot * half + (half - sw_ * kk) / 2
            ty = (SH - sh_ * kk) / 2
            pg.merge_transformed_page(src, Transformation().scale(kk).translate(tx, ty))
        pg.merge_page(ov.pages[k])
        if not side[4] and s["rotate_back"]:
            pg.rotate(180)
    with open(out_path, "wb") as f:
        w.write(f)
    return {"sheets": len(sides) // 2, "signatures": len(sigs), "blanks": blanks}


def trim_size(s):
    pw, ph = page_size_inches(s)
    if s.get("_trim"):
        return s["_trim"]
    if s.get("fmt_impose"):
        # Estimate only (the build uses the size the imposition really gives): a folio on the sheet turned
        # landscape. Any paper preset works here, not just the four oldest ones.
        from bf_impose import sheet_points
        W0, H0 = sheet_points(s)
        SW, SH = max(W0, H0) / 72, min(W0, H0) / 72
        k = min((SW / 2) / pw, SH / ph)
        return pw * k, ph * k
    return pw, ph


# --------------------------------------------------------------------------
# Wraparound cover template
# --------------------------------------------------------------------------
def build_cover(book, s, out_path, n_pages):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor, black
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.platypus import Paragraph, Frame
    from reportlab.pdfbase.pdfmetrics import stringWidth

    (R, B, I, BI), (HR, HB, _hi, _hbi), _d = font_roles(s, lambda m: None)
    if s.get("heading_bold", True):
        B = HB
    else:
        B = HR
    from reportlab.lib.utils import ImageReader
    from bf_pictures import cover_art, fit_box, COVER_FITS
    tw, th = trim_size(s)
    spine = estimated_spine(s, n_pages)
    if float(s.get("spine_width") or 0) > 0:
        spine = float(s["spine_width"])                   # measured by the user
    W, H = (2 * tw + spine) * 72, th * 72
    c = canvas.Canvas(out_path, pagesize=(W, H))
    c.setTitle(f"{book.title} - cover")
    fill = s.get("cover_image_fit", COVER_FITS[0]) == COVER_FITS[0]
    arts = {}
    for which, x0 in (("back", 0), ("front", (tw + spine) * 72)):
        try:
            data = cover_art(book, s, which)
        except ValueError:
            data = None
        if not data:
            continue
        try:
            img = ImageReader(io.BytesIO(data))
            iw, ih = img.getSize()
            bx, by, bw, bh = fit_box(iw, ih, x0, 0, tw * 72, H, fill)
            c.saveState()
            path = c.beginPath()
            path.rect(x0, 0, tw * 72, H)
            c.clipPath(path, stroke=0, fill=0)
            c.drawImage(img, bx, by, bw, bh, mask="auto")
            c.restoreState()
            arts[which] = True
        except Exception:
            pass
    c.setStrokeColor(HexColor("#bbbbbb"))
    c.setDash(3, 3)
    c.setLineWidth(0.5)
    for x in (tw * 72, (tw + spine) * 72):
        if arts:                                          # short marks only, so the pictures stay clean
            c.line(x, 0, x, 0.25 * 72)
            c.line(x, H - 0.25 * 72, x, H)
        else:
            c.line(x, 0, x, H)
    c.setDash()

    def fit(text, font, maxsize, maxw):
        sz = maxsize
        while sz > 8 and stringWidth(text, font, sz) > maxw:
            sz -= 1
        return sz

    fx0 = (tw + spine) * 72
    cx = fx0 + tw * 72 / 2
    pad = 0.6 * 72
    y = H * 0.68
    t = book.title
    sz = fit(t, B, 40, tw * 72 - 2 * pad)
    c.setFillColor(black)
    if not arts.get("front") or s.get("cover_text_over_art"):
        c.setFont(B, sz)
        c.drawCentredString(cx, y, t)
        if book.subtitle:
            s2 = fit(book.subtitle, I, 16, tw * 72 - 2 * pad)
            c.setFont(I, s2)
            c.drawCentredString(cx, y - sz * 1.3, book.subtitle)
        if book.author:
            s3 = fit(book.author, R, 18, tw * 72 - 2 * pad)
            c.setFont(R, s3)
            c.drawCentredString(cx, H * 0.18, book.author)
    if spine * 72 >= 14:
        label = book.title + (f"    {book.author}" if book.author else "")
        ssz = min(spine * 72 * 0.55, 14)
        ssz = fit(label, B, ssz, H - 72)
        c.saveState()
        c.translate((tw + spine / 2) * 72, H / 2)
        c.rotate(-90)
        c.setFont(B, ssz)
        c.drawCentredString(0, -ssz * 0.35, label)
        c.restoreState()
    if (s.get("blurb") or "").strip():
        sty = ParagraphStyle("blurb", fontName=R, fontSize=11, leading=15, alignment=TA_JUSTIFY,
                             spaceAfter=8)
        paras = [Paragraph(esc(" ".join(p.split())), sty)
                 for p in re.split(r"\n\s*\n", s["blurb"].strip()) if p.strip()]
        Frame(pad, pad, tw * 72 - 2 * pad, H * 0.75 - pad, showBoundary=0).addFromList(paras, c)
    c.showPage()
    c.save()
    return {"trim": (tw, th), "spine": spine, "width": W / 72, "height": H / 72,
            "measured": float(s.get("spine_width") or 0) > 0, "art": sorted(arts)}


def estimated_spine(s, n_pages):
    """Spine width in inches worked out from the page count and the paper's thickness."""
    return math.ceil(n_pages / 2) * PAPERS.get(s["paper"], 0.004)


# --------------------------------------------------------------------------
# Shared helpers for text exports
# --------------------------------------------------------------------------
def chapter_heads(book, s):
    """Yield (chapter, label, title) with the same labelling rules as the PDF."""
    n = 0
    for ch in book.active():
        title = apply_case(ch.title, s["title_case"])
        if ch.level == 0:
            yield ch, ch.label, title
            continue
        n += 1
        lbl = ch.label
        if not lbl and s["chapter_label"] not in ("None", "") and not LABELISH.match(ch.title + " "):
            lbl = auto_label(s["chapter_label"], n)
        yield ch, lbl, title


def contents_list(book, s, heads, sep=" \u2014 "):
    """The contents list for EPUB, HTML and plain text: [(chapter number in heads or None, text)].
    Follows "Edit contents" (renamed, hidden, moved and added entries). Page numbers are left out
    because these formats reflow. With no edits this is the plain list of chapter headings."""
    items = [(i, f"{lbl}{sep}{title}" if lbl and title else (title or lbl))
             for i, (_ch, lbl, title) in enumerate(heads, 1)]
    if not getattr(book, "toc", None):
        return items
    from bf_pdf import contents_entries, apply_contents_edits
    by_uid = {ch.uid: n for n, (ch, _l, _t) in enumerate(heads, 1)}
    out = []
    for e in apply_contents_edits(contents_entries(book, s), book.toc):
        if e.get("custom"):
            out.append((None, e["text"]))
        elif e["uid"] in by_uid:
            n = by_uid[e["uid"]]
            out.append((n, e["text"] if e.get("edited") else items[n - 1][1]))
    return out


def an_mode(s):
    return s.get("an_mode", "Set apart (smaller, indented)")


def scene_text(b, s):
    sb = s.get("scene_break", "* * *")
    if sb == "Blank space":
        return ""
    if sb == "Keep the source's own":
        return plain(b.text) or "* * *"
    return sb


def _font_span(m):
    a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))
    css = []
    if a.get("face"):
        css.append(f"font-family:'{a['face']}'")
    if a.get("size"):
        css.append(f"font-size:{a['size']}" + ("" if a["size"].endswith("%") else "pt"))
    if a.get("color"):
        css.append(f"color:{a['color']}")
    return f'<span style="{";".join(css)}">' if css else "<span>"


def para_style(b):
    """CSS for formatting set in the editor (alignment, indent, space above)."""
    css = []
    if getattr(b, "align", ""):
        css.append(f"text-align:{b.align}")
    if getattr(b, "indent", 0):
        css.append(f"margin-left:{0.25 * int(b.indent):g}in")
    if getattr(b, "space", 0):
        css.append(f"margin-top:{int(b.space)}pt")
    return f' style="{";".join(css)}"' if css else ""


def front_art(book, s):
    """The front cover picture's bytes (see bf_pictures.cover_art), or None if there isn't a usable one."""
    from bf_pictures import cover_art
    try:
        return cover_art(book, s, "front")
    except ValueError:
        return None


def picture_html(b, src):
    """A picture for EPUB / web pages, with the size, alignment and placement chosen in the editor."""
    pcss, icss = [], []
    if b.align in ("left", "center", "right"):
        pcss.append(f"text-align:{b.align}")
    if b.img_place == "full":
        icss.append("width:100%")
    elif b.img_width:
        icss.append(f"width:{min(100, max(5, int(b.img_width)))}%")
    if b.img_place in ("page", "full"):
        pcss += ["page-break-before:always", "page-break-after:always"]
        icss.append("max-height:95vh")
    ps = f' style="{";".join(pcss)}"' if pcss else ""
    ims = f' style="{";".join(icss)}"' if icss else ""
    return f'<p class="img"{ps}><img src="{src}" alt=""{ims} /></p>'


def to_xhtml(markup):
    m = markup.replace("<super>", "<sup>").replace("</super>", "</sup>").replace("<br/>", "<br />")
    m = m.replace("<strike>", "<s>").replace("</strike>", "</s>")
    m = re.sub(r"<font\b[^>]*>", _font_span, m).replace("</font>", "</span>")
    return m.replace("&nbsp;", "&#160;")


def img_type(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"GIF8":
        return "gif", "image/gif"
    if b"<svg" in data[:300]:
        return "svg", "image/svg+xml"
    return None, None


CSS = """body{font-family:Georgia,'Times New Roman',serif;line-height:1.55;margin:0 6%;}
p{text-indent:1.5em;margin:0 0 .45em;text-align:justify;}
.label{text-align:center;margin:3em 0 .3em;font-size:1.1em;letter-spacing:.05em;}
h1,h2{text-align:center;margin:.3em 0 1.2em;}
h3{text-align:center;margin:1.5em 0 .8em;}
.part{margin-top:30%;}
.verse{text-align:center;font-style:italic;margin:1em 0;text-indent:0;}
.quote{margin:1em 2em;text-indent:0;}
.subtitle{text-align:center;font-style:italic;margin:0 2em 1.5em;text-indent:0;}
.scene{text-align:center;margin:1em 0;text-indent:0;}
.item{text-indent:-1.2em;text-align:left;}
.anote{font-size:.88em;margin:0 2em .3em;text-indent:0;text-align:left;}
.anlabel{font-size:.82em;font-weight:bold;margin:1em 2em .2em;text-indent:0;}
.meta{text-indent:-1em;margin:0 0 .3em 1em;text-align:left;}
.titlepage{text-align:center;margin-top:25%;}
.titlepage .t{font-size:2.2em;font-weight:bold;text-indent:0;text-align:center;}
.titlepage p{text-align:center;text-indent:0;}
.ded{text-align:center;font-style:italic;margin-top:25%;text-indent:0;}
.end{text-align:center;margin-top:2em;text-indent:0;}
img{max-width:100%;}
.img{text-align:center;text-indent:0;}
nav ol{list-style:none;} a{color:inherit;}
"""


def blocks_html(blocks, imgmap, s=None):
    s = s or {}
    out = []
    prev_label = None
    for b in blocks:
        if b.kind != "anote":
            prev_label = None
        if b.kind == "anote":
            if an_mode(s).startswith("Leave"):
                continue
            keep = an_mode(s).startswith("Keep")
            if b.label and b.label != prev_label:
                out.append(f'<p class="{"quote" if keep else "anlabel"}">{esc(b.label)}</p>')
            out.append(f'<p class="{"quote" if keep else "anote"}"{para_style(b)}>{to_xhtml(b.text)}</p>')
            prev_label = b.label
        elif b.kind == "item":
            ind = 1.5 * (b.depth + 1)
            bullet = esc(b.bullet) + "&#160;" if b.bullet else ""
            out.append(f'<p class="item" style="margin-left:{ind}em">{bullet}{to_xhtml(b.text)}</p>')
        elif b.kind == "para":
            out.append(f"<p{para_style(b)}>{to_xhtml(b.text)}</p>")
        elif b.kind == "quote":
            out.append(f'<p class="quote"{para_style(b)}>{to_xhtml(b.text)}</p>')
        elif b.kind == "subtitle":
            out.append(f'<p class="subtitle"{para_style(b)}>{to_xhtml(b.text)}</p>')
        elif b.kind == "verse":
            out.append('<p class="verse">' + "<br />".join(to_xhtml(l) if l else "&#160;"
                                                          for l in b.lines) + "</p>")
        elif b.kind == "head":
            out.append(f"<h3{para_style(b)}>{to_xhtml(b.text)}</h3>")
        elif b.kind == "scene":
            out.append(f'<p class="scene">{esc(scene_text(b, s)) or "&#160;"}</p>')
        elif b.kind == "image" and id(b) in imgmap:
            out.append(picture_html(b, imgmap[id(b)]))
    return "\n".join(out)





def fic_sections(book, s):
    """[(heading, [(css_class, markup)])] for the fanfic info / summary / notes pages."""
    out = []
    if book.fic_meta and s.get("fic_info", "Leave out") != "Leave out":
        out.append(("Work Info", [("meta", m) for m in book.fic_meta]))
    if book.fic_summary and s.get("fic_summary", "Add a summary page") != "Leave out":
        out.append((book.fic_summary[0].label or "Summary", [("flush", b.text) for b in book.fic_summary]))
    if book.fic_notes and not an_mode(s).startswith("Leave"):
        out.append((book.fic_notes[0].label or "Notes", [("flush", b.text) for b in book.fic_notes]))
    return out


# --------------------------------------------------------------------------
# EPUB 3
# --------------------------------------------------------------------------
def build_epub(book, s, out_path):
    uid = "urn:uuid:" + str(uuid.uuid4())
    lang = book.language or "en"
    heads = list(chapter_heads(book, s))

    def page(title, body):
        return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
                f'xml:lang="{lang}" lang="{lang}"><head><meta charset="utf-8" /><title>{esc(title)}</title>'
                '<link rel="stylesheet" type="text/css" href="style.css" /></head>'
                f"<body>\n{body}\n</body></html>")

    files, manifest, spine, navitems = {}, [], [], []
    imgmap, n_img = {}, 0
    for ch in book.active():
        for b in ch.blocks:
            if b.kind == "image" and b.image:
                ext, mt = img_type(b.image)
                if ext:
                    n_img += 1
                    name = f"images/img{n_img:04d}.{ext}"
                    files["OEBPS/" + name] = b.image
                    manifest.append(f'<item id="img{n_img}" href="{name}" media-type="{mt}"/>')
                    imgmap[id(b)] = name
    cover_meta = ""
    art = front_art(book, s)
    if art and img_type(art)[0]:
        ext, mt = img_type(art)          # e-book readers show this picture as the book's cover
        files[f"OEBPS/images/cover.{ext}"] = art
        manifest.append(f'<item id="cover-image" href="images/cover.{ext}" media-type="{mt}" '
                        'properties="cover-image"/>')
        files["OEBPS/cover.xhtml"] = page(book.title, '<div style="text-align:center;margin:0;padding:0">'
                                          f'<img src="images/cover.{ext}" alt="{esc(book.title)}" '
                                          'style="max-width:100%;max-height:100vh" /></div>')
        manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append("cover")
        cover_meta = '<meta name="cover" content="cover-image"/>'
    tp = ['<div class="titlepage">', f'<p class="t">{esc(book.title)}</p>']
    if book.subtitle:
        tp.append(f"<p><i>{esc(book.subtitle)}</i></p>")
    if book.author:
        tp.append(f"<p>{esc(book.author)}</p>")
    if book.credit:
        tp.append(f"<p>{esc(book.credit)}</p>")
    tp.append("</div>")
    if (s.get("dedication") or "").strip():
        tp.append('<p class="ded">' + esc(s["dedication"].strip()).replace("\n", "<br />") + "</p>")
    files["OEBPS/title.xhtml"] = page(book.title, "\n".join(tp))
    manifest.append('<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>')
    spine.append("title")
    fic = fic_sections(book, s)
    if fic:
        body = "".join(f"<h2>{esc(h)}</h2>" + "".join(
            f'<p class="{"meta" if c == "meta" else "quote"}">{to_xhtml(m)}</p>' for c, m in items)
            for h, items in fic)
        files["OEBPS/info.xhtml"] = page("About this work", body)
        manifest.append('<item id="info" href="info.xhtml" media-type="application/xhtml+xml"/>')
        spine.append("info")
    if (s.get("note_text") or "").strip():
        body = (f"<h2>{esc(s.get('note_title') or '')}</h2>" if s.get("note_title") else "") + \
            "".join(f"<p>{esc(' '.join(p.split()))}</p>" for p in re.split(r"\n\s*\n", s["note_text"].strip()))
        files["OEBPS/note.xhtml"] = page(s.get("note_title") or "Note", body)
        manifest.append('<item id="note" href="note.xhtml" media-type="application/xhtml+xml"/>')
        spine.append("note")
    for i, (ch, lbl, title) in enumerate(heads, 1):
        fn = f"ch{i:03d}.xhtml"
        parts = []
        if ch.level == 0:
            parts.append('<div class="part">')
        if lbl:
            parts.append(f'<p class="label">{esc(lbl)}</p>')
        if title:
            parts.append(f'<h{1 if ch.level == 0 else 2}>{esc(title)}</h{1 if ch.level == 0 else 2}>')
        if ch.level == 0:
            parts.append("</div>")
        parts.append(blocks_html(ch.blocks, imgmap, s))
        if i == len(heads) and s.get("the_end"):
            parts.append('<p class="end">THE END</p>')
        files["OEBPS/" + fn] = page(title or lbl, "\n".join(parts))
        manifest.append(f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f"c{i}")
        disp = f"{lbl} \u2014 {title}" if lbl and title else (title or lbl)
        navitems.append((fn, disp))
    nav = ("<nav epub:type=\"toc\" id=\"toc\"><h2>" + esc(s.get("toc_title") or "Contents") + "</h2><ol>" +
           "".join(f'<li><a href="{navitems[n - 1][0]}">{esc(t)}</a></li>' if n else f"<li><span>{esc(t)}</span></li>"
                   for n, t in contents_list(book, s, heads)) + "</ol></nav>")
    files["OEBPS/nav.xhtml"] = page("Contents", nav)
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    if s.get("toc"):
        spine.insert(1 + ("cover" in spine) + ("note" in spine) + ("info" in spine), "nav")
    ncx = ('<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" '
           f'version="2005-1"><head><meta name="dtb:uid" content="{uid}"/></head>'
           f"<docTitle><text>{esc(book.title)}</text></docTitle><navMap>" +
           "".join(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{esc(t)}</text></navLabel>'
                   f'<content src="{fn}"/></navPoint>' for i, (fn, t) in enumerate(navitems, 1)) +
           "</navMap></ncx>")
    files["OEBPS/toc.ncx"] = ncx
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    files["OEBPS/style.css"] = CSS
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')
    mod = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
           'version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{esc(book.title)}</dc:title>'
           f'<dc:language>{esc(lang)}</dc:language>' +
           (f"<dc:creator>{esc(book.author)}</dc:creator>" if book.author else "") +
           f'{cover_meta}<meta property="dcterms:modified">{mod}</meta></metadata><manifest>' + "".join(manifest) +
           '</manifest><spine toc="ncx">' + "".join(f'<itemref idref="{x}"/>' for x in spine) +
           "</spine></package>")
    files["OEBPS/content.opf"] = opf
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>", compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


# --------------------------------------------------------------------------
# Word DOCX
# --------------------------------------------------------------------------
WORD_FONT = {"Times (built-in)": "Times New Roman", "Helvetica (built-in)": "Arial",
             "Courier (built-in)": "Courier New"}


def add_docx_picture(d, b, s, pw, ph):
    """A picture in the Word file, with the size, alignment and placement chosen in the editor.
    Word can't print to the paper's edge, so a full-page picture fills the text area of its own page."""
    from docx.shared import Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from bf_pictures import size
    tw = pw - float(s["margin_inner"]) - float(s["margin_outer"])
    th = ph - float(s["margin_top"]) - float(s["margin_bottom"])
    own = b.img_place in ("page", "full")
    if b.img_place == "full":
        w = tw
    elif b.img_width:
        w = tw * min(100, max(5, int(b.img_width))) / 100
    else:
        w = min(tw, 5)
    px = size(b.image)
    if px and px[0] and w * px[1] / px[0] > th * (0.95 if own else 0.9):
        w = th * (0.95 if own else 0.9) * px[0] / px[1]          # keep it on one page, same shape
    if own and d.paragraphs and d.paragraphs[-1].text.strip():
        d.add_page_break()
    d.add_picture(io.BytesIO(b.image), width=Inches(w))
    d.paragraphs[-1].alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "right": WD_ALIGN_PARAGRAPH.RIGHT}.get(
        b.align, WD_ALIGN_PARAGRAPH.CENTER)
    if own:
        d.add_page_break()


def build_docx(book, s, out_path):
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Inches, RGBColor

    d = docx.Document()
    pw, ph = page_size_inches(s)
    sec = d.sections[0]
    sec.page_width, sec.page_height = Inches(pw), Inches(ph)
    sec.top_margin, sec.bottom_margin = Inches(float(s["margin_top"])), Inches(float(s["margin_bottom"]))
    sec.left_margin, sec.right_margin = Inches(float(s["margin_inner"])), Inches(float(s["margin_outer"]))
    st_el = d.settings.element
    st_el.append(OxmlElement("w:mirrorMargins"))
    uf = OxmlElement("w:updateFields")
    uf.set(qn("w:val"), "true")
    st_el.append(uf)

    font = WORD_FONT.get(s["font_family"], s["font_family"])
    hfam = s.get("heading_font") or "Same as body text"
    hfont = font if hfam == "Same as body text" else WORD_FONT.get(hfam, hfam)
    size = float(s["body_size"])
    normal = d.styles["Normal"]
    normal.font.name = font
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), font)
    normal.font.size = Pt(size)
    pf = normal.paragraph_format
    pf.first_line_indent = Inches(float(s["indent"]))
    pf.space_after = Pt(float(s["para_space"]))
    pf.line_spacing = float(s["line_spacing"])
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if s["align"] == "Justified" else WD_ALIGN_PARAGRAPH.LEFT
    pf.widow_control = True
    for hn, hs in (("Heading 1", float(s["title_size"])), ("Heading 2", float(s["title_size"]))):
        h = d.styles[hn]
        h.font.name, h.font.size, h.font.bold = hfont, Pt(hs), bool(s.get("heading_bold", True))
        h.font.color.rgb = RGBColor(0, 0, 0)
        h.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.paragraph_format.space_after = Pt(16)
        h.paragraph_format.first_line_indent = Inches(0)

    def center(text, sz=None, bold=False, italic=False, before=0, after=6, brk=False):
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Inches(0)
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
        p.paragraph_format.page_break_before = brk
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        if sz:
            r.font.size = Pt(sz)
        return p

    def fmt_para(p, b):
        """Alignment / indent / space above set in the editor."""
        al = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
              "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
        if getattr(b, "align", "") in al:
            p.alignment = al[b.align]
        if getattr(b, "indent", 0):
            p.paragraph_format.left_indent = Inches(0.25 * int(b.indent))
        if getattr(b, "space", 0):
            p.paragraph_format.space_before = Pt(int(b.space))

    def add_markup(p, markup, base_italic=False):
        fl = {"i": 0, "b": 0, "super": 0, "sub": 0, "strike": 0, "u": 0}
        fonts = []                                    # editor fonts: (face, size, colour) stack
        for tok in re.split(r"(<[^>]+>)", markup):
            if not tok:
                continue
            if tok.startswith("<"):
                name = re.sub(r"[</>]", " ", tok).split()
                name = name[0].lower() if name else ""
                if name == "br":
                    p.add_run().add_break()
                elif name in fl:
                    fl[name] += -1 if tok.startswith("</") else 1
                elif name == "font":
                    if tok.startswith("</"):
                        if fonts:
                            fonts.pop()
                    else:
                        fonts.append(dict(re.findall(r'(\w+)="([^"]*)"', tok)))
                continue
            r = p.add_run(html.unescape(tok))
            for f in fonts:
                if f.get("face"):
                    r.font.name = html.unescape(f["face"]).replace(" (built-in)", "")
                if f.get("size"):
                    try:
                        v = f["size"]
                        r.font.size = Pt(float(s["body_size"]) * float(v[:-1]) / 100 if v.endswith("%")
                                         else float(v))
                    except ValueError:
                        pass
                if f.get("color", "").startswith("#") and len(f["color"]) == 7:
                    r.font.color.rgb = RGBColor.from_string(f["color"][1:].upper())
            r.italic = bool(fl["i"]) != base_italic
            r.bold = bool(fl["b"])
            if fl["strike"]:
                r.font.strike = True
            if fl["u"]:
                r.underline = True
            if fl["super"]:
                r.font.superscript = True
            if fl["sub"]:
                r.font.subscript = True

    ts = float(s["title_size"])
    art = front_art(book, s) if s.get("cover_art_in_book") else None
    if art:
        from bf_core import Block
        try:
            add_docx_picture(d, Block("image", image=art, img_place="full"), s, pw, ph)
        except Exception:
            pass
    if s["title_page"]:
        center(book.title, max(30, ts * 1.5), bold=True, before=140, after=12)
        if book.subtitle:
            center(book.subtitle, float(s["sub_size"]) + 1, italic=True)
        if book.author:
            center(book.author, float(s["sub_size"]), before=30)
        if book.credit:
            center(book.credit, size * 0.9)
        if s["bookplate"] == "On title page":
            center(s["bookplate_text"], float(s["sub_size"]), italic=True, before=60)
            center("_" * 40, after=0)
    if s["bookplate"] == "Separate page":
        center(s["bookplate_text"], float(s["sub_size"]), italic=True, before=220, brk=True)
        center("_" * 40)
    if (s.get("dedication") or "").strip():
        center(s["dedication"].strip(), italic=True, before=180, brk=True)
    if s["toc"]:
        center(s["toc_title"], ts, bold=True, after=18, brk=True)
        p = d.add_paragraph()
        p.paragraph_format.first_line_indent = Inches(0)
        r = p.add_run()
        for kind, txt in (("begin", None), ("instr", 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None),
                          ("text", "Press F9 (or right-click > Update Field) to build the contents."),
                          ("end", None)):
            if kind == "instr":
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = txt
                r._r.append(el)
            elif kind == "text":
                r = p.add_run(txt)
                r = p.add_run()
            else:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
                r._r.append(el)
    for heading, items in fic_sections(book, s):
        center(heading, float(s["sub_size"]), bold=True, brk=True, after=12)
        for cls, m in items:
            p = d.add_paragraph()
            p.paragraph_format.first_line_indent = Inches(-0.25 if cls == "meta" else 0)
            p.paragraph_format.left_indent = Inches(0.25 if cls == "meta" else 0)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            add_markup(p, m)
    if (s.get("note_text") or "").strip():
        first = True
        if s.get("note_title"):
            center(s["note_title"], float(s["sub_size"]), bold=True, brk=True, after=12)
            first = False
        for para in re.split(r"\n\s*\n", s["note_text"].strip()):
            p = d.add_paragraph(" ".join(para.split()))
            if first:
                p.paragraph_format.page_break_before = True
                first = False

    has_parts = any(c.level == 0 for c in book.active())
    heads = list(chapter_heads(book, s))
    for i, (ch, lbl, title) in enumerate(heads):
        hstyle = "Heading 1" if (ch.level == 0 or not has_parts) else "Heading 2"
        h = d.add_paragraph(style=hstyle)
        h.paragraph_format.page_break_before = True
        if lbl:
            rl = h.add_run(lbl)
            rl.bold = False
            rl.font.size = Pt(float(s["sub_size"]))
            if title:
                rl.add_break()
        if title:
            h.add_run(title)
        prev_label = None
        for b in ch.blocks:
            if b.kind != "anote":
                prev_label = None
            if b.kind == "anote":
                if an_mode(s).startswith("Leave"):
                    continue
                keep = an_mode(s).startswith("Keep")
                if b.label and b.label != prev_label:
                    p = d.add_paragraph()
                    p.paragraph_format.first_line_indent = Inches(0)
                    p.paragraph_format.left_indent = Inches(0 if keep else 0.35)
                    add_markup(p, esc(b.label) if keep else f"<b>{esc(b.label)}</b>")
                p = d.add_paragraph()
                p.paragraph_format.first_line_indent = Inches(0)
                p.paragraph_format.left_indent = p.paragraph_format.right_indent = Inches(0.35 if not keep else 0.4)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                add_markup(p, b.text)
                fmt_para(p, b)
                if not keep:
                    for r in p.runs:
                        r.font.size = Pt(size * 0.88)
                prev_label = b.label
            elif b.kind == "item":
                p = d.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.3 * (b.depth + 1))
                p.paragraph_format.first_line_indent = Inches(-0.25 if b.bullet else 0)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                add_markup(p, (esc(b.bullet) + "\t" if b.bullet else "") + b.text)
                fmt_para(p, b)
            elif b.kind == "para":
                p = d.add_paragraph()
                add_markup(p, b.text)
                fmt_para(p, b)
            elif b.kind == "subtitle":
                p = center("", after=14)
                add_markup(p, b.text, base_italic=True)
                fmt_para(p, b)
            elif b.kind == "quote":
                p = d.add_paragraph()
                p.paragraph_format.left_indent = p.paragraph_format.right_indent = Inches(0.4)
                p.paragraph_format.first_line_indent = Inches(0)
                add_markup(p, b.text)
                fmt_para(p, b)
            elif b.kind == "verse":
                p = d.add_paragraph()
                p.paragraph_format.first_line_indent = Inches(0)
                if s["verse_style"] == "Centered italic":
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    add_markup(p, "<br/>".join(b.lines), base_italic=True)
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p.paragraph_format.left_indent = Inches(0.5)
                    add_markup(p, "<br/>".join(b.lines))
            elif b.kind == "head":
                p = center("", bold=True, before=12, after=8)
                add_markup(p, f"<b>{b.text}</b>")
                fmt_para(p, b)
            elif b.kind == "scene":
                center(scene_text(b, s))
            elif b.kind == "image" and b.image:
                try:
                    add_docx_picture(d, b, s, pw, ph)
                except Exception:
                    pass
        if i == len(heads) - 1 and s.get("the_end"):
            center("THE END", before=24)

    if s["pn_position"] != "None":
        fp = sec.footer.paragraphs[0] if not s["pn_position"].startswith("Top") else sec.header.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run()
        for kind in ("begin", "instr", "end"):
            if kind == "instr":
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = "PAGE"
            else:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            r._r.append(el)
    d.core_properties.title = book.title
    d.core_properties.author = book.author
    d.save(out_path)


# --------------------------------------------------------------------------
# HTML and TXT
# --------------------------------------------------------------------------
def build_html(book, s, out_path):
    import base64
    heads = list(chapter_heads(book, s))
    imgmap = {}
    for ch in book.active():
        for b in ch.blocks:
            if b.kind == "image" and b.image:
                ext, mt = img_type(b.image)
                if ext:
                    imgmap[id(b)] = f"data:{mt};base64," + base64.b64encode(b.image).decode()
    out = [f'<!DOCTYPE html><html lang="{book.language or "en"}"><head><meta charset="utf-8">'
           f"<title>{esc(book.title)}</title><style>{CSS} body{{max-width:40em;margin:0 auto;padding:2em}}"
           "</style></head><body>"]
    art = front_art(book, s) if s.get("cover_art_in_book") else None
    if art and img_type(art)[0]:
        out.append(f'<p class="img"><img src="data:{img_type(art)[1]};base64,{base64.b64encode(art).decode()}" '
                   f'alt="{esc(book.title)}" style="max-width:100%" /></p>')
    out += ['<div class="titlepage">', f'<p class="t">{esc(book.title)}</p>']
    for v, tag in ((book.subtitle, "i"), (book.author, "span"), (book.credit, "span")):
        if v:
            out.append(f"<p><{tag}>{esc(v)}</{tag}></p>")
    out.append("</div>")
    for heading, items in fic_sections(book, s):
        out.append(f"<h2>{esc(heading)}</h2>")
        out += [f'<p class="{"meta" if c == "meta" else "quote"}">{to_xhtml(m)}</p>' for c, m in items]
    if s["toc"]:
        out.append(f"<h2>{esc(s['toc_title'])}</h2><ol>")
        for i, disp in contents_list(book, s, heads):
            out.append(f'<li><a href="#c{i}">{esc(disp)}</a></li>' if i else f"<li>{esc(disp)}</li>")
        out.append("</ol>")
    for i, (ch, lbl, title) in enumerate(heads, 1):
        out.append(f'<hr id="c{i}">')
        if lbl:
            out.append(f'<p class="label">{esc(lbl)}</p>')
        if title:
            out.append(f"<h2>{esc(title)}</h2>")
        out.append(blocks_html(ch.blocks, imgmap, s))
    if s.get("the_end"):
        out.append('<p class="end">THE END</p>')
    out.append("</body></html>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def build_txt(book, s, out_path):
    out = [book.title]
    for v in (book.subtitle, book.author, book.credit):
        if v:
            out.append(v)
    out.append("")
    heads = list(chapter_heads(book, s))
    for heading, items in fic_sections(book, s):
        out += [heading] + [plain(m) for _c, m in items] + [""]
    if s["toc"]:
        out.append(s["toc_title"])
        for _i, disp in contents_list(book, s, heads, sep=" - "):
            out.append("  " + disp)
        out.append("")
    for ch, lbl, title in heads:
        out += ["", ""]
        if lbl:
            out.append(lbl)
        if title:
            out.append(title)
        out.append("")
        for b in ch.blocks:
            if b.kind in ("para", "quote", "head", "subtitle"):
                out.append(plain(b.text))
                out.append("")
            elif b.kind == "anote" and not an_mode(s).startswith("Leave"):
                out += [("[" + b.label + "] " if b.label else "") + plain(b.text), ""]
            elif b.kind == "item":
                out.append("  " * b.depth + (b.bullet + " " if b.bullet else "  ") + plain(b.text))
            elif b.kind == "verse":
                out += [plain(l) for l in b.lines] + [""]
            elif b.kind == "scene":
                out += [scene_text(b, s), ""]
    if s.get("the_end"):
        out.append("THE END")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
