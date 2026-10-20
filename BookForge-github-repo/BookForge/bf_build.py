"""One-click build pipeline used by the GUI."""
import os
import tempfile

from bf_core import safe_name, page_size_inches, blank_pages
from bf_pdf import build_pdf
from bf_export import build_cover, build_epub, build_docx, build_html, build_txt
import bf_impose


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


def check_settings(s):
    """Stop before anything is written when a setting can't be used (a plain ValueError message):
    the number of blank pages, a custom page size, and - when the pages are imposed - a custom printer paper
    size and the page margins and offsets."""
    blank_pages(s, "start")
    blank_pages(s, "end")
    page_size_inches(s)
    if s.get("fmt_impose"):
        bf_impose.sheet_points(s)
        bf_impose.placement_settings(s)


def build_preview(book, s, log=print):
    """Typeset the book exactly as run_build does, but into a temporary folder.

    Uses the same build_pdf (and, when "Imposed PDF for binding" is ticked, the same imposition)
    so the preview IS the final layout. Nothing is written to the output folder."""
    s = dict(s)
    check_settings(s)
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
            "toc_labels": dict(getattr(book, "_toc_labels", {}))}


def run_build(book, s, log=print):
    check_settings(s)
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
    if s["fmt_pdf"] or s["fmt_impose"] or s["fmt_cover"]:
        if s["fmt_pdf"]:
            pdf_path = base + " - Print.pdf"
        else:
            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
        n_pages = typeset(book, s, pdf_path, log)
        pw, ph = page_size_inches(s)
        log(f"{'Copied' if fixed else 'Typeset'} {n_pages} pages at {pw:.3g} x {ph:.3g} in.")
        if s["fmt_pdf"]:
            made.append(pdf_path)
            notes.append(f"Print PDF: {n_pages} pages, {pw:.3g} x {ph:.3g} in, "
                         + ("the PDF's own pages, kept as they are." if fixed
                            else "page numbers and contents included."))
        if blank_pages_note(s):
            notes.append(blank_pages_note(s))

    if s["fmt_impose"]:
        log("Arranging pages on sheets for binding...")
        if int(s.get("sig_sheets") or 0) <= 0 and s.get("sig_format", "").startswith("Standard"):
            s["sig_format"] = "Booklet (one signature)"       # BookForge 1.0-1.2 setting
        info = bf_impose.impose(pdf_path, folder, safe_name(book.title), s, log)
        made += info["files"]
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
            f"Imposed for binding ({lay}): {info['sheets']} sheet(s) of {bf_impose.paper_label(s)} paper, "
            f"printed {SW:.4g} x {SH:.4g} in; {sig}; {info['blanks']} blank page(s) added to fill the last sheet.\n"
            f"  Print at Actual size / 100%, {how}. Print one test sheet first.\n  Folding: {info['instructions']}"
            + ("\n  Fold lines are printed on the inside of each fold (the side facing you as you fold)."
               if s.get("fold_marks") and s.get("fold_side", "Inside").startswith("Inside") else "")
            + (f"\n  {info['placement_note']}" if info.get("placement_note") else "")
            + (f"\n  WARNING: {info['warning']}" if info.get("warning") else "")
            + (f"\n  WARNING: {info['placement_warning']}" if info.get("placement_warning") else ""))

    if s["fmt_cover"]:
        log("Drawing cover template...")
        out = base + " - Cover.pdf"
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
            out = base + ext
            fn(book, s, out)
            made.append(out)
            if key == "fmt_docx":
                notes.append("Word document: when Word asks to update fields on opening, click Yes to "
                             "fill in the contents page numbers.")

    with open(os.path.join(folder, "READ ME - printing notes.txt"), "w", encoding="utf-8") as f:
        f.write(f"{book.title}\nMade with BookForge by ChunksBabyRuth\n\n")
        for n in notes:
            f.write("- " + n + "\n\n")
        f.write("Files:\n" + "\n".join("  " + os.path.basename(m) for m in made) + "\n")
    log("Done.")
    return folder, made, notes
