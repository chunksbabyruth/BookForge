"""BookForge PDF input. No window code here.

Two ways to use a PDF as the source of a book:

* "Keep the pages as they are": the PDF's own pages are printed and arranged for binding. copy_pages()
  makes a clean copy with every page the same size and the right way up (pages that are turned, cropped
  or a different size are fitted, never stretched), which the preview, imposition and cover all use.
* "Rebuild as an editable book": pdf_events() reads the text (with bold/italic, sizes, headings and
  pictures) into the same events the EPUB/Word readers produce, so the book can be edited, restyled and
  typeset like any other source. This is a best-effort reconstruction: PDFs store positioned lines, not
  paragraphs, so the result should be checked in the Chapters and Edit steps.
"""
import io
import os
import re
from collections import Counter

class PdfProblem(ValueError):
    pass


# --------------------------------------------------------------------------- opening
def _open(path):
    import pypdfium2 as pdfium
    try:
        return pdfium.PdfDocument(path)
    except Exception as e:                                   # pdfium's own messages are technical
        msg = str(e).lower()
        if "password" in msg:
            raise PdfProblem("This PDF is password-protected. Open it in a PDF reader, save a copy without "
                             "the password, and use that copy.") from e
        raise PdfProblem(f"This PDF can't be read - it may be damaged or not really a PDF ({str(e).rstrip('.')}).") from e


def pdf_meta(path):
    """{"title", "author", "pages"} from the PDF (title falls back to the file name)."""
    doc = _open(path)
    try:
        md = doc.get_metadata_dict(skip_empty=True)
        n = len(doc)
    finally:
        doc.close()
    title = (md.get("Title") or "").strip()
    if not title or title.lower() in ("untitled", "microsoft word") or title.lower().endswith((".doc", ".docx", ".pdf")):
        title = os.path.splitext(os.path.basename(path))[0]
    return {"title": title, "author": (md.get("Author") or "").strip(), "pages": n}


# --------------------------------------------------------------------------- keep the pages as they are
def _visible_box(page):
    """The part of the page a reader shows: the crop box inside the media box (in PDF units)."""
    mb, cb = page.mediabox, page.cropbox
    l, b = max(float(mb.left), float(cb.left)), max(float(mb.bottom), float(cb.bottom))
    r, t = min(float(mb.right), float(cb.right)), min(float(mb.top), float(cb.top))
    if r - l < 1 or t - b < 1:
        l, b, r, t = float(mb.left), float(mb.bottom), float(mb.right), float(mb.top)
    return l, b, r, t


def copy_pages(path, out_path, log=print):
    """Copy the PDF's pages into out_path, all one size and upright. Returns (pages, (width, height)) in
    points. The size is the one most pages have; other pages are scaled to fit it (keeping their shape)
    and centred. Nothing on the pages is changed."""
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import RectangleObject
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise PdfProblem("This PDF is password-protected. Open it in a PDF reader, save a copy "
                                     "without the password, and use that copy.")
            except PdfProblem:
                raise
            except Exception as e:
                raise PdfProblem("This PDF is encrypted in a way BookForge can't open. Save a copy without "
                                 "protection from a PDF reader and use that.") from e
        pages = list(reader.pages)
    except PdfProblem:
        raise
    except Exception as e:
        raise PdfProblem(f"This PDF can't be read - it may be damaged ({type(e).__name__}).") from e
    if not pages:
        raise PdfProblem("This PDF has no pages.")
    shapes = []
    for p in pages:
        l, b, r, t = _visible_box(p)
        w, h = r - l, t - b
        if (p.rotation or 0) % 180:
            w, h = h, w
        shapes.append((w, h))
    W, H = Counter((round(w), round(h)) for w, h in shapes).most_common(1)[0][0]
    W, H = float(W), float(H)
    plain = all(abs(w - W) < 1 and abs(h - H) < 1 for w, h in shapes) and \
        all(not (p.rotation or 0) % 360 for p in pages) and \
        all(abs(_visible_box(p)[0]) < 0.01 and abs(_visible_box(p)[1]) < 0.01 and
            [round(float(v), 2) for v in p.mediabox] == [round(float(v), 2) for v in p.cropbox] for p in pages)
    writer = PdfWriter()
    refit = 0
    for i, p in enumerate(pages):
        if plain:
            writer.add_page(p)
            continue
        if (p.rotation or 0) % 360:
            p.transfer_rotation_to_content()                  # the page's turn becomes part of its content
        l, b, r, t = _visible_box(p)
        p.trimbox = RectangleObject([l, b, r, t])              # merging clips to this, so cropped parts stay hidden
        w, h = r - l, t - b
        k = min(W / w, H / h)
        if abs(w - W) >= 1 or abs(h - H) >= 1:
            refit += 1
        new = writer.add_blank_page(W, H)
        tr = Transformation().translate(-l, -b).scale(k, k).translate((W - w * k) / 2, (H - h * k) / 2)
        new.merge_transformed_page(p, tr, expand=False)
        try:
            new.compress_content_streams()
        except Exception:
            pass
    with open(out_path, "wb") as f:
        writer.write(f)
    if refit:
        log(f"Note: {refit} page(s) were a different size or shape from the rest and were scaled to fit "
            f"{W / 72:.2f} x {H / 72:.2f} in (nothing was stretched).")
    return len(pages), (W, H)


# --------------------------------------------------------------------------- rebuild as an editable book
_TERMINAL = tuple(".!?:;”’\"')]…*")
_ROMAN = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)
_DOTS = "\u2022\u25cf\u25aa\u25a0\u2023\u25e6\u2043\uf0b7\uf0a7\uf076\uf0d8\u00b7"
_BULLET = re.compile(r"^([" + _DOTS + r"\-\u2013*]|\d{1,3}[.)]|[a-z][.)]|[ivx]{1,4}[.)])\s+\S")
_LEADER = re.compile(r"(\.{3,}|…|\s{2,}|\t)\s*(\d+|[ivxlcdm]+)\s*$", re.I)


def _read_lines(doc, log):
    """Every text line on every page: dicts with text runs, position and size (PDF points, y up)."""
    import ctypes
    import pypdfium2.raw as raw
    pages = []
    buf = ctypes.create_string_buffer(256)
    r_, g_, b_, a_ = (ctypes.c_uint() for _ in range(4))
    fl = ctypes.c_int()
    l, rr, bb, t = (ctypes.c_double() for _ in range(4))
    for pi in range(len(doc)):
        page = doc[pi]
        pw, ph = page.get_size()
        tp = page.get_textpage()
        n = tp.count_chars()
        lines, cur = [], None
        last_font_key, last_style = None, (False, False, "")
        for i in range(n):
            u = raw.FPDFText_GetUnicode(tp, i)
            if u in (13, 10):
                if u == 10 and cur is not None:
                    lines.append(cur)
                    cur = None
                continue
            ch = chr(u) if u else ""
            if not ch:
                continue
            if u in (0xFFFE, 0x02) or raw.FPDFText_IsHyphen(tp, i):
                # a word broken over two lines: pdfium joins the lines and marks the break; keep the lines
                # apart (so page numbers and headers next to it stay separate) and join the word later
                if cur is not None:
                    cur["hyph"] = True
                    lines.append(cur)
                    cur = None
                continue
            raw.FPDFText_GetCharBox(tp, i, l, rr, bb, t)
            size = raw.FPDFText_GetFontSize(tp, i)
            fkey = raw.FPDFText_GetTextObject(tp, i)
            fkey = ctypes.cast(fkey, ctypes.c_void_p).value if fkey else None
            if fkey != last_font_key:
                k = raw.FPDFText_GetFontInfo(tp, i, buf, len(buf), ctypes.byref(fl))
                name = buf.raw[:max(0, min(k, len(buf)) - 1)].decode("utf-8", "ignore") if k else ""
                weight = raw.FPDFText_GetFontWeight(tp, i)
                low = name.lower()
                bold = weight >= 600 or "bold" in low or "black" in low or "heavy" in low or "semibold" in low
                italic = "italic" in low or "oblique" in low or bool(fl.value & 64)
                color = ""
                if raw.FPDFText_GetFillColor(tp, i, r_, g_, b_, a_):
                    rgb = (r_.value, g_.value, b_.value)
                    if max(rgb) > 60 and min(rgb) < 230:       # not black/near-black, not white
                        color = "#%02x%02x%02x" % rgb
                fam = re.sub(r"^[A-Z]{6}\+", "", name)
                last_style = (bold, italic, color, fam, round(size * 2) / 2)
                last_font_key = fkey
            gen = bool(raw.FPDFText_IsGenerated(tp, i))
            if cur is None:
                cur = {"runs": [], "x0": 1e9, "x1": -1e9, "top": -1e9, "bot": 1e9, "sizes": Counter(),
                       "page": pi, "pw": pw, "ph": ph, "hyph": False}
            if ch.strip() and not gen:
                cur["x0"], cur["x1"] = min(cur["x0"], l.value), max(cur["x1"], rr.value)
                cur["top"], cur["bot"] = max(cur["top"], t.value), min(cur["bot"], bb.value)
                cur["sizes"][round(size * 2) / 2] += 1
            style = last_style if ch.strip() else None
            if cur["runs"] and (style is None or cur["runs"][-1][1] == style or cur["runs"][-1][1] is None):
                txt, st = cur["runs"][-1]
                cur["runs"][-1] = (txt + ch, st if st is not None else style)
            else:
                cur["runs"].append((ch, style))
        if cur is not None:
            lines.append(cur)
        out = []
        for ln in lines:
            text = "".join(t for t, _s in ln["runs"])
            if not text.strip() or ln["x0"] > 1e8:
                continue
            ln["text"] = text.strip()
            ln["size"] = ln["sizes"].most_common(1)[0][0] if ln["sizes"] else 10
            out.append(ln)
        imgs = []
        for obj in page.get_objects(max_depth=2):
            if obj.type == 3:                                   # an image
                try:
                    x0, y0, x1, y1 = obj.get_bounds() if hasattr(obj, "get_bounds") else obj.get_pos()
                except Exception:
                    continue
                imgs.append({"obj": obj, "box": (x0, y0, x1, y1)})
        pages.append({"lines": out, "images": imgs, "w": pw, "h": ph, "page": page, "tp": tp})
    return pages


def _markup(runs, base_size, keep, base_fam=""):
    from bf_core import esc
    import bf_keepfmt
    out = []
    for text, st in runs:
        if st is None:
            out.append(esc(text))
            continue
        bold, italic, color, fam, size = st
        m = esc(text)
        if keep:
            kf = bf_keepfmt.usable_face(fam) if bf_keepfmt._key(fam) != bf_keepfmt._key(base_fam) else ""
            o, c = bf_keepfmt.font_open(kf, bf_keepfmt.pct(size, base_size), color)
            m = o + m + c
        if italic:
            m = f"<i>{m}</i>"
        if bold:
            m = f"<b>{m}</b>"
        out.append(m)
    m = "".join(out)
    for tag in ("b", "i"):                                       # <b>a</b> <b>b</b> -> <b>a b</b>
        m = re.sub(rf"</{tag}>(\s*)<{tag}>", r"\1", m)
    return m


def esc_(t):
    from bf_core import esc
    return esc(t)


def _norm(t):
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", t.strip().lower()))


def _edge_lines(pg):
    """Lines that sit apart at the very top or bottom of a page (where running heads, page numbers and
    footers go): the first/last line, when a clear gap separates it from the text block."""
    h = pg["h"]
    lines = sorted(pg["lines"], key=lambda ln: -ln["top"])
    if len(lines) <= 3:
        return [ln for ln in lines if ln["top"] > h * 0.88 or ln["bot"] < h * 0.12]
    gaps = sorted(a["bot"] - b["top"] for a, b in zip(lines, lines[1:]) if a["bot"] - b["top"] > 0)
    med = gaps[len(gaps) // 2] if gaps else 0
    out = []
    first, second = lines[0], lines[1]
    if first["top"] > h * 0.85 and first["bot"] - second["top"] > max(med * 1.6, 3):
        out.append(first)
    last, before = lines[-1], lines[-2]
    if last["bot"] < h * 0.15 and before["bot"] - last["top"] > max(med * 1.6, 3):
        out.append(last)
    return out


def _strip_furniture(pages):
    """Drop running heads, page numbers and repeated footers: lines set apart at the top or bottom of the
    page that are page numbers, or that repeat on many pages."""
    n = len(pages)
    sizes = Counter()
    for pg in pages:
        for ln in pg["lines"]:
            sizes[ln["size"]] += len(ln["text"])
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    edges = [[ln for ln in _edge_lines(pg) if ln["size"] <= body * 1.15] for pg in pages]   # headings are bigger
    counts = Counter()
    for e in edges:
        counts.update({_norm(ln["text"]) for ln in e})
    need = max(3, int(n * 0.25))
    removed = 0
    for pg, e in zip(pages, edges):
        drop = set()
        for ln in e:
            t = ln["text"].strip()
            if re.fullmatch(r"[\u2014\u2013\-\s]*(\d{1,4}|[ivxlcdm]{1,7})[\u2014\u2013\-\s]*", t, re.I) or \
                    (n >= 3 and counts[_norm(t)] >= need):
                drop.add(id(ln))
        if n >= 3:                  # the same header/footer on a page where it isn't set apart as clearly
            h = pg["h"]
            for ln in pg["lines"]:
                if (ln["top"] > h * 0.88 or ln["bot"] < h * 0.12) and ln["size"] <= body * 1.15 and \
                        counts[_norm(ln["text"])] >= need:
                    drop.add(id(ln))
        removed += len(drop)
        pg["lines"] = [ln for ln in pg["lines"] if id(ln) not in drop]
    return removed


def _is_contents_page(pg):
    lines = pg["lines"]
    if len(lines) < 4:
        return False
    hits = sum(1 for ln in lines if _LEADER.search(ln["text"]) or re.search(r"\s\d{1,4}$", ln["text"]))
    has_title = any(re.fullmatch(r"(table of )?contents", ln["text"].strip(), re.I) for ln in lines[:3])
    return hits >= 0.6 * len(lines) or (has_title and hits >= 0.4 * len(lines))


def _page_picture(pg, dpi=150):
    """Render a page (one with no text: a scan or a drawing) as a JPEG."""
    bm = pg["page"].render(scale=dpi / 72)
    im = bm.to_pil().convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def _image_bytes(obj):
    """An image object's picture as PNG/JPEG bytes, or None."""
    try:
        im = obj.get_bitmap(render=True).to_pil()
    except Exception:
        try:
            im = obj.get_bitmap(render=False).to_pil()
        except Exception:
            return None
    if im.width < 24 or im.height < 24:
        return None
    out = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P"):
        im.convert("RGBA").save(out, "PNG")
    else:
        im.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def pdf_events(path, s, log=print):
    """Read a PDF's text into events (see bf_core events_to_book). Returns (events, meta, images)."""
    keep = bool(s.get("keep_format"))
    doc = _open(path)
    try:
        meta = pdf_meta(path)
        pages = _read_lines(doc, log)
        n = len(pages)
        total = sum(len(ln["text"]) for pg in pages for ln in pg["lines"])
        if n and total / n < 25:
            raise PdfProblem("This PDF looks like scanned pictures of pages, so there is no text in it to edit. "
                             "Choose “Keep the pages as they are” to print it as it is, or run it through "
                             "an OCR program first (many PDF readers have “Recognize text”) and open the "
                             "result.")
        removed = _strip_furniture(pages)
        if removed:
            log(f"PDF: left out {removed} running head / page number line(s).")
        events, images = [], {}
        outline = {}
        try:
            for item in doc.get_toc(max_depth=4):
                t = re.sub(r"\s+", " ", (item.title or "")).strip()
                if t:
                    outline.setdefault(_norm(t), item.level + 1)
        except Exception:
            outline = {}
        sizes = Counter()
        for pg in pages:
            for ln in pg["lines"]:
                sizes[ln["size"]] += len(ln["text"])
        body = sizes.most_common(1)[0][0] if sizes else 10.0
        fams = Counter()
        for pg in pages:
            for ln in pg["lines"]:
                for t, st in ln["runs"]:
                    if st is not None:
                        fams[st[3]] += len(t)
        base_fam = fams.most_common(1)[0][0] if fams else ""
        head_sizes = sorted({sz for sz in sizes if sz >= body * 1.25}, reverse=True)
        level_of = {sz: i + 1 for i, sz in enumerate(head_sizes)}
        # running heads that repeat a heading (a chapter's title at the top of its pages)
        titles = {_norm(ln["text"]) for pg in pages for ln in pg["lines"] if ln["size"] in level_of}
        titles |= set(outline) | {_norm(meta["title"])}
        dropped = 0
        for pg in pages:
            keep_lines = []
            for ln in pg["lines"]:
                if ln["top"] > pg["h"] * 0.90 and ln["size"] <= body * 1.15 and _norm(ln["text"]) in titles:
                    dropped += 1
                    continue
                keep_lines.append(ln)
            pg["lines"] = keep_lines
        if dropped:
            log(f"PDF: left out {dropped} running head(s) repeating a chapter title.")
        skip_contents = bool(s.get("skip_contents"))
        para, para_fmt, pending_notes = None, {}, []
        pic_n = 0
        left_now = [0.0]                     # the text's left edge on the page being read (for flush)
        scanned_pages = 0
        book_started = False
        prev = None                          # the line before (it may be on the page before)

        def flush():
            nonlocal para
            if para is not None:
                text = para["text"]
                xs = para.get("x0s") or []
                if keep and not para.get("item") and "align" not in para_fmt and xs:
                    # the whole paragraph sits in from the margin (a letter, a block quote): keep that
                    shift = min(xs) - left_now[0]
                    if (len(xs) >= 2 and shift >= 18) or shift >= 43:
                        steps = __import__("bf_keepfmt").indent_steps(shift / 72)
                        if steps:
                            para_fmt["indent"] = steps
                if text.strip() and para.get("item"):
                    events.append(("item", text) + para["item"])
                elif text.strip():
                    events.append(("para", text, para_fmt) if keep and para_fmt else ("para", text))
                para = None
            while pending_notes:
                events.append(pending_notes.pop(0))

        for pi, pg in enumerate(pages):
            lines = pg["lines"]
            if skip_contents and pi < max(3, n // 6) and _is_contents_page(pg):
                log(f"PDF: page {pi + 1} looks like a contents page and was left out.")
                continue
            if not lines:
                if pg["images"] and s.get("include_images"):
                    flush()
                    pic_n += 1
                    name = f"page{pi + 1:03d}.jpg"
                    images[name] = _page_picture(pg)
                    events.append(("image", name))
                    scanned_pages += 1
                continue
            body_lines = [ln for ln in lines if abs(ln["size"] - body) < 0.6]
            left = Counter(round(ln["x0"]) for ln in body_lines).most_common(1)[0][0] if body_lines else \
                min(ln["x0"] for ln in lines)
            right = max((ln["x1"] for ln in body_lines), default=max(ln["x1"] for ln in lines))
            left_now[0] = left
            width = max(1.0, right - left)
            gaps = [a["bot"] - b["top"] for a, b in zip(body_lines, body_lines[1:]) if 0 < a["bot"] - b["top"] < body * 3]
            gap = sorted(gaps)[len(gaps) // 2] if gaps else body * 0.3
            pics = []
            if s.get("include_images"):
                for im in pg["images"]:
                    x0, y0, x1, y1 = im["box"]
                    if (x1 - x0) < 20 or (y1 - y0) < 20:
                        continue
                    pics.append((y1, im))
            pics.sort(key=lambda p: -p[0])
            for ln in lines:
                while pics and pics[0][0] > ln["top"]:
                    _y, im = pics.pop(0)
                    data = _image_bytes(im["obj"])
                    if data:
                        flush()
                        pic_n += 1
                        name = f"picture{pic_n:03d}.{'png' if data[:4] == b'\x89PNG' else 'jpg'}"
                        images[name] = data
                        events.append(("image", name))
                text = ln["text"]
                size = ln["size"]
                markup = _markup(ln["runs"], body, keep, base_fam).strip()
                is_head = size in level_of or _norm(text) in outline
                note = size <= body * 0.85 and ln["bot"] < pg["h"] * 0.3 and len(text) > 2
                centred = abs((ln["x0"] - left) - (right - ln["x1"])) < body * 1.2 and (ln["x1"] - ln["x0"]) < width * 0.8
                if is_head and pi < 3 and not book_started and _norm(text) == _norm(meta["title"]):
                    flush()                        # the book's own title on its title page: front text
                    events.append(("para", markup))
                    prev = ln
                    continue
                if is_head:
                    lvl = level_of.get(size) or outline.get(_norm(text), 1)
                    if events and events[-1][0] == "head" and events[-1][1] == lvl and para is None and \
                            prev is not None and prev.get("head") and prev["page"] == ln["page"] and \
                            prev["bot"] - ln["top"] < size * 1.2:
                        events[-1] = ("head", lvl, events[-1][2] + " " + text)
                    else:
                        flush()
                        events.append(("head", lvl, text))
                    ln["head"] = True
                    prev = ln
                    book_started = True
                    continue
                if note:
                    pending_notes.append(("para", markup))
                    continue
                bullet = _BULLET.match(text) if not re.fullmatch(r"[\s*\u2022\u00b7~#=\-\u2013\u2014]+", text) else None
                new = para is None or bool(bullet)
                if not new and para.get("item") and ln["x0"] - left > body * 0.5 and prev is not None and \
                        prev["page"] == ln["page"] and prev["bot"] - ln["top"] < gap + body * 0.6:
                    pass                                       # the next line of a list item
                elif not new and prev is not None:
                    gap_here = prev["bot"] - ln["top"] if prev["page"] == ln["page"] else None
                    indent = ln["x0"] - left > body * 0.8 and not centred
                    short_prev = prev["x1"] < right - width * 0.15 and prev["text"].rstrip().endswith(_TERMINAL)
                    if gap_here is not None and gap_here > gap + body * 0.6:
                        new = True
                    elif indent or short_prev or abs(size - prev["size"]) > 0.6:
                        new = True
                    elif prev.get("centred") != centred and not (prev["text"] and not prev.get("centred") and
                                                                  prev["x1"] >= right - body):
                        new = True                     # a centred line after normal text, or the other way round
                    elif prev.get("centred") and centred:
                        new = True
                    elif gap_here is None and prev["text"].rstrip().endswith(_TERMINAL) and \
                            ln["x0"] - left > body * 0.8:
                        new = True
                if new:
                    flush()
                    para = {"text": markup, "x0s": [ln["x0"]]}
                    para_fmt = {}
                    if bullet:
                        mark = bullet.group(1)
                        mark = "\u2022" if mark in _DOTS else mark
                        depth = max(0, min(3, int((ln["x0"] - left) // (body * 1.8))))
                        para = {"text": re.sub(r"^((?:<[^>]+>)*)\s*" + re.escape(esc_(bullet.group(1))) + r"\s*", r"\1",
                                               markup, count=1), "item": (mark, depth)}
                    if keep:
                        if centred:
                            para_fmt["align"] = "center"
                        elif ln["x0"] - left > width * 0.3:
                            para_fmt["align"] = "right" if ln["x1"] > right - body else ""
                        if not para_fmt.get("align"):
                            para_fmt.pop("align", None)
                else:
                    t = para["text"]
                    para.setdefault("x0s", []).append(ln["x0"])
                    if prev is not None and prev.get("hyph"):
                        para["text"] = re.sub(r"[-­‐\x02]$", "", t) + markup
                    elif re.search(r"[A-Za-zÀ-ɏ]-$", t) and re.match(r"[a-zß-ÿ]", text):
                        para["text"] = t[:-1] + markup
                    else:
                        para["text"] = t + " " + markup
                ln["centred"] = centred
                prev = ln
            while pics:
                _y, im = pics.pop(0)
                data = _image_bytes(im["obj"])
                if data:
                    flush()
                    pic_n += 1
                    name = f"picture{pic_n:03d}.{'png' if data[:4] == b'\x89PNG' else 'jpg'}"
                    images[name] = data
                    events.append(("image", name))
        flush()
        if scanned_pages:
            log(f"PDF: {scanned_pages} page(s) had no text (scans or drawings) and were kept as pictures.")
        log(f"PDF: read {n} pages{f', {pic_n} picture(s)' if pic_n else ''}. Check the chapters and text - "
            "PDFs don't store paragraphs, so BookForge rebuilt them from the line positions.")
        return events, meta, images
    finally:
        doc.close()
