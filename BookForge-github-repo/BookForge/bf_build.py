"""One-click build pipeline used by the GUI."""
import os
import tempfile

from bf_core import safe_name, page_size_inches, blank_pages, plain, not_the_source
from bf_pdf import build_pdf, empty_pages_note
from bf_export import build_cover, build_epub, build_docx, build_html, build_txt
import bf_impose
import bf_matter


class NothingToPrint(ValueError):
    """The book has nothing to print (no chapters, all left out, or no text or pictures left)."""


def _has_content(b):
    if b.kind == "image":
        return bool(b.image)
    if b.kind == "verse":
        return any(plain(line).strip() for line in (b.lines or []))
    if b.kind == "scene":
        return False                        # a section break on its own isn't something to print
    return bool(plain(b.text or "").strip())


def book_problem(book, source=False):
    """Why this book can't be printed, as the end of a plain sentence ("there's nothing to print: ..."), or
    None when it can. Front matter, blank pages and empty parts are fine: the book needs some text or a
    picture in an included chapter (or the text before the first chapter), or a PDF kept as it is."""
    if book is None:
        return "no book has been read from the source yet."
    if getattr(book, "fixed_pdf", ""):
        if os.path.isfile(book.fixed_pdf):
            return None
        return f"the PDF it was made from can't be found any more ({book.fixed_pdf})."
    if any(_has_content(b) for b in book.front_blocks):
        return None
    if not book.chapters:
        return ("it has no chapters" + (" with any text in them" if source else " (they were all deleted)") + ".")
    active = book.active()
    if not active:
        return "every chapter is left out (select chapters on the Chapters tab and click Skip / include to bring them back)."
    if any(_has_content(b) for ch in active for b in ch.blocks):
        return None
    return ("its chapters have no text or pictures" + (" in them." if source else
            " left (their text was deleted or is empty)."))


def nothing_to_print(book):
    """The full message for book_problem, with what to do about it."""
    return ("There's nothing to print: " + book_problem(book) + "\n\nTo fix it, press Re-read source on the "
            "Source tab to make the book again from the source, bring left-out chapters back with Skip / include on the Chapters tab, "
            "or use Undo in Specific Text Edit.")


def empty_chapters_note(book):
    """A log line naming included chapters that have no text (they print as a title only), or ''."""
    if getattr(book, "fixed_pdf", ""):
        return ""
    empty = [c.display() or "(untitled)" for c in book.active() if c.level == 1 and
             not any(_has_content(b) for b in c.blocks)]
    if not empty:
        return ""
    names = ", ".join(f"\u201c{n}\u201d" for n in empty[:5]) + (f" and {len(empty) - 5} more" if len(empty) > 5 else "")
    return f"Note: {len(empty)} chapter(s) have no text, so only their title is printed: {names}."


def check_book(book, log=print):
    """Stop before anything is made when the book has nothing to print (NothingToPrint, a plain message)."""
    if book_problem(book):
        raise NothingToPrint(nothing_to_print(book))
    note = empty_chapters_note(book)
    if note:
        log(note)


def default_out_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "BookForge Books")


def cover_art_problems(book, s):
    """Plain messages about cover pictures that were chosen but can't be used."""
    from bf_pictures import cover_art
    out = []
    for which in ("front", "back"):
        path = (s.get(f"cover_{which}_image") or "").strip()
        if not path:
            continue
        try:
            if cover_art(book, s, which) is None:
                out.append(f"WARNING: the {which} cover picture wasn't found ({path}), so it was left out.")
        except ValueError as e:
            out.append(f"WARNING: {which} cover picture: {e}. It was left out.")
    return out


def typeset(book, s, pdf_path, log=print):
    """Make the book's pages (reading order) in pdf_path; returns the page count.
    A PDF kept as it is: its own pages, all one size and upright, and s gets that page size."""
    if getattr(book, "fixed_pdf", ""):
        import bf_pdfin
        if not os.path.isfile(book.fixed_pdf):
            raise ValueError(f"The PDF wasn't found: {book.fixed_pdf}")
        n_front, n_back = blank_pages(s, "start"), blank_pages(s, "end")
        log("Copying the PDF's pages (kept as they are)...")
        n, (w, h) = bf_pdfin.copy_pages(book.fixed_pdf, pdf_path, log)
        s["page_size"], s["custom_w"], s["custom_h"] = "Custom", w / 72, h / 72
        if n_front or n_back:
            add_blank_pages(pdf_path, n_front, n_back, w, h)
            n += n_front + n_back
        return n
    return build_pdf(book, s, pdf_path, log)


def add_blank_pages(pdf_path, n_front, n_back, w, h):
    """Put blank pages (w x h points) before and after the pages of a PDF, in place."""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for _ in range(n_front):
        writer.add_blank_page(w, h)
    for page in reader.pages:
        writer.add_page(page)
    for _ in range(n_back):
        writer.add_blank_page(w, h)
    tmp = pdf_path + ".tmp"
    with open(tmp, "wb") as f:
        writer.write(f)
    os.replace(tmp, pdf_path)


def blank_pages_note(s):
    """Printing-notes line about added blank pages ('' when there are none)."""
    a, b = blank_pages(s, "start"), blank_pages(s, "end")
    if not (a or b):
        return ""
    bits = [f"{a} at the beginning" if a else "", f"{b} at the end" if b else ""]
    return ("Blank pages you added: " + " and ".join(x for x in bits if x) +
            " (part of the book's pages, with no page number; signature padding is separate).")


def planned_blanks_note(book):
    """Printing-notes line about the pages the layout leaves blank on purpose ('' when there are none): the
    left-hand page before a chapter that starts on a right-hand page, and the back of the front cover picture.
    They are pages of the book (in the print PDF too) - not signature padding, not flyleafs."""
    pl = getattr(book, "_planned_blanks", None) or {}
    if not pl:
        return ""

    def pages(ps):
        shown = ", ".join(map(str, ps[:12])) + (f" and {len(ps) - 12} more" if len(ps) > 12 else "")
        return ("page " if len(ps) == 1 else "pages ") + shown
    bits = []
    cover = [p for p, why in pl.items() if why == "cover"]
    verso = [p for p, why in pl.items() if why == "verso"]
    if cover:
        bits.append(f"{pages(cover)} (the back of the front cover picture)")
    if verso:
        bits.append(f"{pages(verso)} (left-hand page{'s' if len(verso) > 1 else ''} left blank so the next "
                    "chapter starts on a right-hand page)")
    return ("Blank pages in the book on purpose (counting every page of the print PDF): " + "; ".join(bits) +
            ". They are part of the book's pages, not signature padding.")


def format_limits(book, s):
    """Edited front/back pages that a chosen file format can't hold, said in the printing notes (and the log)
    instead of being left out silently. Everything else edited on these pages is in every format that is made."""
    if getattr(book, "fixed_pdf", ""):
        return []
    named = lambda keys: [n for k, n in keys if s.get(k)]                         # noqa: E731
    reflow = named((("fmt_epub", "EPUB"), ("fmt_html", "web page"), ("fmt_txt", "text file")))
    others = named((("fmt_epub", "EPUB"), ("fmt_docx", "Word document"), ("fmt_html", "web page"),
                    ("fmt_txt", "text file")))
    word = lambda xs: (", ".join(xs[:-1]) + " and " + xs[-1]) if len(xs) > 1 else xs[0]   # noqa: E731
    out = []
    if reflow and s.get("bookplate", "None") != "None" and bf_matter.is_edited(book, "bookplate"):
        out.append(f"Not in the {word(reflow)}: the bookplate page you edited (a print page: it is in the print PDF"
                   + (" and the Word document)." if s.get("fmt_docx") else ")."))
    if others and int(s.get("notes_pages") or 0) > 0 and bf_matter.is_edited(book, "notes_page"):
        out.append(f"Not in the {word(others)}: the Notes pages you edited (lined pages for writing on, print "
                   "only).")
    toc = getattr(book, "toc", None) or []
    if reflow and s.get("toc") and toc:
        if any((e.get("page") or "").strip() and e.get("show", True) for e in toc):
            out.append(f"The {word(reflow)} {'has' if len(reflow) == 1 else 'have'} no page numbers (their text "
                       "reflows), so the page numbers typed in Edit contents are only in the print PDF"
                       + (" and the Word document." if s.get("fmt_docx") else "."))
        if any(e.get("markup") or e.get("space") for e in toc):
            out.append(f"The {word(reflow)} list{'s' if len(reflow) == 1 else ''} the contents entries' words; their "
                       "fonts, bold, colours and space above are in the print PDF"
                       + (" and the Word document." if s.get("fmt_docx") else "."))
    if s.get("fmt_txt") and any(b.kind == "image" and b.image for k in bf_matter.SECTIONS
                                if bf_matter.is_edited(book, k) for b in (bf_matter.override(book, k) or [])):
        out.append("The text file has no pictures: the pictures on the edited front/back pages are in the other "
                   "formats.")
    if bf_matter.is_edited(book, "blurb") and not s.get("fmt_cover") and (s.get("fmt_pdf") or s.get("fmt_impose")
                                                                         or others):
        out.append("The back-cover text you edited is printed on the cover only, and the cover PDF isn't being made "
                   "this time.")
    return out


def padding_note(info):
    """What the printing notes say about the blank pages the imposition adds (signature-completion padding, kept
    apart from flyleafs and from the blank pages that are part of the book)."""
    fly = info.get("flyleaf_pages", 0)
    bits = []
    if info.get("signatures"):
        pad, per_sheet = info["blanks"], info.get("per_sheet") or 1
        bits.append((f"{pad} blank page(s) added after the book's last page to complete the last "
                     + ("sheet" if pad < per_sheet else "signature")) if pad else "no blank pages needed to fill "
                    "the sheets")
        custom, plan = info.get("custom") or [], info.get("plan") or []
        if custom and len(plan) < len(custom):
            bits.append(f"the book needs {len(plan)} of the {len(custom)} custom signature sizes, so only those "
                        "are made")
        elif custom and len(plan) > len(custom):
            bits.append(f"the custom sizes are used in order, the last one ({custom[-1]} sheets) again for the "
                        "rest")
    elif info.get("empty_spaces"):
        bits.append(f"{info['empty_spaces']} page space(s) on the sheets left empty after the book's last page")
    if fly:
        bits.append(f"flyleafs: {fly} blank page(s) at the beginning and {fly} at the end")
    only = info.get("flyleaf_only") or []
    if only:
        bits.append("signature " + ", ".join(map(str, only)) + (" has" if len(only) == 1 else " have") +
                    " no book pages, only flyleaf" + (" or padding" if info.get("blanks") else "") +
                    " pages (blank on purpose)")
    return "; ".join(bits)


def check_settings(s):
    """Stop before anything is written when a setting can't be used (a plain ValueError message):
    the number of blank pages, a custom page size, and - when the pages are imposed - a custom printer paper
    size, the page margins and offsets, and custom signature sizes."""
    blank_pages(s, "start")
    blank_pages(s, "end")
    page_size_inches(s)
    if s.get("fmt_impose"):
        bf_impose.sheet_points(s)
        bf_impose.placement_settings(s)
        if s.get("sig_format", "").startswith("Custom") and s.get("imp_layout") not in bf_impose.WACKY:
            bf_impose.custom_sizes(s)


def build_preview(book, s, log=print):
    """Typeset the book exactly as run_build does, but into a temporary folder.

    Uses the same build_pdf (and, when "Imposed PDF for binding" is ticked, the same imposition)
    so the preview IS the final layout. Nothing is written to the output folder."""
    s = dict(s)
    check_settings(s)
    check_book(book, log)
    tmp = tempfile.mkdtemp(prefix="BookForge preview ")
    pdf = os.path.join(tmp, "preview.pdf")
    n = typeset(book, s, pdf, log)
    sheets, duplex = [], True
    if s.get("fmt_impose"):
        if int(s.get("sig_sheets") or 0) <= 0 and s.get("sig_format", "").startswith("Standard"):
            s["sig_format"] = "Booklet (one signature)"       # same rule as run_build
        s["imp_files"] = "Aggregated file only"                # same sheets; just one file to show
        info = bf_impose.impose(pdf, tmp, "preview", s, log)
        sheets, duplex = info["files"], info["duplex"]
        s["_trim"] = info["trim"]                               # same as run_build, for the cover
    cover = None
    if s.get("fmt_cover"):
        for problem in cover_art_problems(book, s):
            log(problem)
        cover = os.path.join(tmp, "cover.pdf")
        build_cover(book, s, cover, n)
    return {"dir": tmp, "pdf": pdf, "pages": n, "sheets": sheets, "duplex": duplex, "title": book.title,
            "cover": cover,
            "chapter_pages": list(getattr(book, "_chapter_pages", [])),
            "toc_labels": dict(getattr(book, "_toc_labels", {})),
            "empty_pages": list(getattr(book, "_empty_pages", [])),
            "planned_blanks": dict(getattr(book, "_planned_blanks", None) or {})}


def run_build(book, s, log=print):
    check_settings(s)
    check_book(book, log)
    root = s.get("out_dir") or default_out_dir()
    folder = os.path.join(root, safe_name(book.title))
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, safe_name(book.title))
    made, notes = [], []
    n_chap = len([c for c in book.active() if c.level == 1])
    fixed = bool(getattr(book, "fixed_pdf", ""))
    log(f"Book: {book.title}  " + (f"(a PDF of {book.fixed_pages} pages, kept as they are)" if fixed
                                   else f"({n_chap} chapters)"))

    pdf_path = None
    n_pages = 0

    def out_file(path):
        """The file to write: never the book's own source file (see not_the_source)."""
        new = not_the_source(path, s)
        if new != path:
            msg = (f"\u201c{os.path.basename(path)}\u201d is the book's source file, so this file was saved as "
                   f"\u201c{os.path.basename(new)}\u201d instead: making the book never overwrites its source.")
            log(msg)
            notes.append(msg)
        return new
    if s["fmt_pdf"] or s["fmt_impose"] or s["fmt_cover"]:
        if s["fmt_pdf"]:
            pdf_path = out_file(base + " - Print.pdf")
        else:
            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
        n_pages = typeset(book, s, pdf_path, log)
        pw, ph = page_size_inches(s)
        log(f"{'Copied' if fixed else 'Typeset'} {n_pages} pages at {pw:.3g} x {ph:.3g} in.")
        if s["fmt_pdf"]:
            made.append(pdf_path)
            notes.append(f"Print PDF: {n_pages} pages, book page size {pw:.3g} x {ph:.3g} in, "
                         + ("the PDF's own pages, kept as they are." if fixed
                            else "page numbers and contents included."))
        if blank_pages_note(s):
            notes.append(blank_pages_note(s))
        if planned_blanks_note(book):
            notes.append(planned_blanks_note(book))
        if getattr(book, "_empty_pages", None):
            notes.append("WARNING: " + empty_pages_note(book._empty_pages))

    if s["fmt_impose"]:
        log("Arranging pages on sheets for binding...")
        if int(s.get("sig_sheets") or 0) <= 0 and s.get("sig_format", "").startswith("Standard"):
            s["sig_format"] = "Booklet (one signature)"       # BookForge 1.0-1.2 setting
        info = bf_impose.impose(pdf_path, folder, safe_name(book.title), s, log)
        made += info["files"]
        for old, new in info.get("renamed", []):
            notes.append(f"\u201c{os.path.basename(old)}\u201d is the book's source file, so this file was saved "
                         f"as \u201c{os.path.basename(new)}\u201d instead: making the book never overwrites its source.")
        s["_trim"] = info["trim"]
        SW, SH = info["sheet_in"]
        lay = info["layout"]
        if info["signatures"]:
            plan = info["plan"]
            sig = f"{info['signatures']} signature(s) " + (
                f"of {plan[0]} sheet(s) each" if len(set(plan)) == 1 else "of " + ", ".join(map(str, plan)) + " sheets")
        else:
            sig = "small-format layout"
        flip = "SHORT" if SW > SH else "LONG"            # sheet size already reflects "Rotate paper 90"
        how = (f"double-sided, FLIP ON {flip} EDGE (or tick 'Rotate back sides' if your printer only offers the "
               "other flip)") if info["duplex"] else (
            "on a single-sided printer: print the 'fronts' file, put the printed stack back in the tray "
            "(turned over so the blank sides print), then print the 'backs' file (if the backs come out "
            "upside down, tick 'Rotate back sides 180' and make the files again)")
        notes.append(
            f"Imposed for binding ({lay}): {info['sheets']} sheet(s) of {bf_impose.paper_label(s)} printer paper, "
            f"printed {SW:.4g} x {SH:.4g} in; {sig}; {padding_note(info)}.\n"
            f"  Print at Actual size / 100%, {how}. Print one test sheet first.\n  Folding: {info['instructions']}"
            + ("\n  Fold lines are printed on the inside of each fold (the side facing you as you fold)."
               if s.get("fold_marks") and s.get("fold_side", "Inside").startswith("Inside") else "")
            + (f"\n  {info['placement_note']}" if info.get("placement_note") else "")
            + (f"\n  WARNING: {info['warning']}" if info.get("warning") else "")
            + (f"\n  WARNING: {info['placement_warning']}" if info.get("placement_warning") else ""))

    if s["fmt_cover"]:
        log("Drawing cover template...")
        out = out_file(base + " - Cover.pdf")
        for problem in cover_art_problems(book, s):
            log(problem)
        ci = build_cover(book, s, out, n_pages)
        made.append(out)
        tw, th = ci["trim"]
        how = "as you measured it" if ci.get("measured") else \
            f"estimated from {s['paper']} - measure your printed pages and type the real width on the Output tab"
        notes.append(f"Cover: {ci['width']:.2f} x {ci['height']:.2f} in total (back + spine + front). "
                     f"Trim size {tw:.2f} x {th:.2f} in, spine {ci['spine']:.3f} in ({how}). "
                     + ("Dashed lines mark the spine folds. " if not ci.get("art") else
                        "Short dashed marks at the top and bottom edges show the spine folds. ")
                     + "Print on cardstock large enough to hold it (e.g. legal or 11x17) and trim.")

    if pdf_path and not s["fmt_pdf"]:
        try:
            os.remove(pdf_path)
        except OSError:
            pass

    for key, ext, fn, label in (("fmt_epub", ".epub", build_epub, "EPUB e-book"),
                                ("fmt_docx", ".docx", build_docx, "Word document"),
                                ("fmt_html", ".html", build_html, "Web page"),
                                ("fmt_txt", ".txt", build_txt, "Plain text")):
        if s[key] and fixed:
            log(f"{label}: skipped - a PDF kept as it is has no editable text. Choose \u201cRebuild as an "
                "editable book\u201d for PDFs on the Source tab to make one.")
            notes.append(f"{label}: not made, because the PDF's pages were kept as they are.")
            continue
        if s[key]:
            log(f"Writing {label}...")
            out = out_file(base + ext)
            fn(book, s, out)
            made.append(out)
            if key == "fmt_docx":
                notes.append("Word document: when Word asks to update fields on opening, click Yes to "
                             "fill in the contents page numbers.")

    for line in format_limits(book, s):
        log(line)
        notes.append(line)
    with open(out_file(os.path.join(folder, "READ ME - printing notes.txt")), "w", encoding="utf-8") as f:
        f.write(f"{book.title}\nMade with BookForge by ChunksBabyRuth\n\n")
        for n in notes:
            f.write("- " + n + "\n\n")
        f.write("Files:\n" + "\n".join("  " + os.path.basename(m) for m in made) + "\n")
    log("Done.")
    return folder, made, notes
