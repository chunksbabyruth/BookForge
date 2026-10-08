"""One-click build pipeline used by the GUI."""
import os
import tempfile

from bf_core import safe_name, SHEET_SIZES, page_size_inches
from bf_pdf import build_pdf
from bf_export import impose, build_cover, build_epub, build_docx, build_html, build_txt


def default_out_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "BookForge Books")


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
        log("Imposing pages into signatures for binding...")
        out = base + " - Imposed for binding.pdf"
        info = impose(pdf_path, out, s, log)
        made.append(out)
        SW, SH = SHEET_SIZES[s["sheet_size"]]
        sig = "one single booklet" if int(s["sig_sheets"]) <= 0 else \
            f"{info['signatures']} signature(s) of up to {int(s['sig_sheets'])} sheets"
        notes.append(
            f"Imposed PDF: {info['sheets']} sheets of {s['sheet_size']} paper (landscape, {SW:g} x {SH:g} in), "
            f"printed double-sided; {sig}; {info['blanks']} blank page(s) added at the end to fill the last "
            "signature.\n  Print at Actual size / 100%, double-sided, FLIP ON SHORT EDGE (or tick "
            "'Rotate back sides' in BookForge if your printer only flips on the long edge). "
            "Print one test sheet first.")

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
