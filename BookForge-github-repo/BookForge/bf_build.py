"""One-click build pipeline used by the GUI."""
import os
import tempfile

from bf_core import safe_name, page_size_inches
from bf_pdf import build_pdf
from bf_export import build_cover, build_epub, build_docx, build_html, build_txt
import bf_impose


def default_out_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "BookForge Books")


def build_preview(book, s, log=print):
    """Typeset the book exactly as run_build does, but into a temporary folder.

    Uses the same build_pdf (and, when "Imposed PDF for binding" is ticked, the same imposition)
    so the preview IS the final layout. Nothing is written to the output folder."""
    s = dict(s)
    tmp = tempfile.mkdtemp(prefix="BookForge preview ")
    pdf = os.path.join(tmp, "preview.pdf")
    n = build_pdf(book, s, pdf, log)
    sheets, duplex = [], True
    if s.get("fmt_impose"):
        if int(s.get("sig_sheets") or 0) <= 0 and s.get("sig_format", "").startswith("Standard"):
            s["sig_format"] = "Booklet (one signature)"       # same rule as run_build
        s["imp_files"] = "Aggregated file only"                # same sheets; just one file to show
        info = bf_impose.impose(pdf, tmp, "preview", s, log)
        sheets, duplex = info["files"], info["duplex"]
    return {"dir": tmp, "pdf": pdf, "pages": n, "sheets": sheets, "duplex": duplex, "title": book.title}


def run_build(book, s, log=print):
    root = s.get("out_dir") or default_out_dir()
    folder = os.path.join(root, safe_name(book.title))
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, safe_name(book.title))
    made, notes = [], []
    n_chap = len([c for c in book.active() if c.level == 1])
    log(f"Book: {book.title}  ({n_chap} chapters)")

    pdf_path = None
    n_pages = 0
    if s["fmt_pdf"] or s["fmt_impose"] or s["fmt_cover"]:
        if s["fmt_pdf"]:
            pdf_path = base + " - Print.pdf"
        else:
            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
        n_pages = build_pdf(book, s, pdf_path, log)
        pw, ph = page_size_inches(s)
        log(f"Typeset {n_pages} pages at {pw:g} x {ph:g} in.")
        if s["fmt_pdf"]:
            made.append(pdf_path)
            notes.append(f"Print PDF: {n_pages} pages, {pw:g} x {ph:g} in, page numbers and contents included.")

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
            "(turned over so the blank sides print), then print the 'backs' file")
        notes.append(
            f"Imposed for binding ({lay}): {info['sheets']} sheet(s) of {s['sheet_size']} paper "
            f"({SW:g} x {SH:g} in); {sig}; {info['blanks']} blank page(s) added to fill the last sheet.\n"
            f"  Print at Actual size / 100%, {how}. Print one test sheet first.\n  Folding: {info['instructions']}"
            + ("\n  Fold lines are printed on the inside of each fold (the side facing you as you fold)."
               if s.get("fold_marks") and s.get("fold_side", "Inside").startswith("Inside") else ""))

    if s["fmt_cover"]:
        log("Drawing cover template...")
        out = base + " - Cover.pdf"
        ci = build_cover(book, s, out, n_pages)
        made.append(out)
        tw, th = ci["trim"]
        notes.append(f"Cover: {ci['width']:.2f} x {ci['height']:.2f} in total (back + spine + front). "
                     f"Trim size {tw:.2f} x {th:.2f} in, spine {ci['spine']:.3f} in "
                     f"(estimated from {s['paper']}). Dashed lines mark the spine folds. "
                     "Print on cardstock large enough to hold it (e.g. legal or 11x17) and trim.")

    if pdf_path and not s["fmt_pdf"]:
        try:
            os.remove(pdf_path)
        except OSError:
            pass

    for key, ext, fn, label in (("fmt_epub", ".epub", build_epub, "EPUB e-book"),
                                ("fmt_docx", ".docx", build_docx, "Word document"),
                                ("fmt_html", ".html", build_html, "Web page"),
                                ("fmt_txt", ".txt", build_txt, "Plain text")):
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
