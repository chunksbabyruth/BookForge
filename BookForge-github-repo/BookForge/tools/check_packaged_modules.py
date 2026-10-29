"""Check that a PyInstaller-built BookForge contains every Python module the app needs at run time.

usage: python tools/check_packaged_modules.py PATH_TO_PACKAGED_EXECUTABLE

The modules are looked up inside the executable's own archive (the same place the frozen app imports them
from), so this catches modules PyInstaller silently left out, such as PIL._tkinter_finder, without which
the preview window opens empty on macOS and Linux.
"""
import os
import sys
import tempfile

REQUIRED = [
    # BookForge itself
    "bf_build", "bf_core", "bf_edit", "bf_export", "bf_fonts", "bf_impose", "bf_pdf", "bf_theme",
    "bf_pictures", "bf_pdfin", "bf_keepfmt", "bf_update", "bf_placement", "bf_matter",
    # PDF reading and the update check (secure connections in the packaged app)
    "pypdfium2.raw", "certifi", "urllib.request", "ssl", "webbrowser",
    # window, preview and the link between Pillow and Tk
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "tkinter.colorchooser",
    "PIL.Image", "PIL.ImageTk", "PIL._tkinter_finder", "pypdfium2",
    # typesetting, imposition and exports
    "reportlab.platypus", "reportlab.pdfbase.ttfonts", "pypdf", "bs4", "docx", "pyphen",
    "fontTools.ttLib", "fontTools.varLib.instancer",
]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    exe = sys.argv[1]
    candidates = [exe]
    # some PyInstaller versions keep the archive next to the executable instead of inside it (.pkg)
    for root in (os.path.dirname(exe), os.path.join(os.path.dirname(exe), "..", "Frameworks"),
                 os.path.join(os.path.dirname(exe), "..", "Resources")):
        if os.path.isdir(root):
            candidates += [os.path.join(root, f) for f in os.listdir(root) if f.endswith(".pkg")]
    arch, pyz_name = None, None
    for c in candidates:
        try:
            a = CArchiveReader(c)
        except Exception:                 # noqa: BLE001 - not an archive, try the next place
            continue
        name = next((n for n in a.toc if n.endswith("PYZ.pyz") or n.endswith(".pyz")), None)
        if name:
            arch, pyz_name = a, name
            break
    if pyz_name is None:
        raise SystemExit(f"FAIL: no Python archive found inside {exe}")
    with tempfile.TemporaryDirectory() as tmp:
        pyz = os.path.join(tmp, "PYZ.pyz")
        with open(pyz, "wb") as f:
            f.write(arch.extract(pyz_name))
        modules = set(ZlibArchiveReader(pyz).toc)
    missing = [m for m in REQUIRED if m not in modules]
    if missing:
        raise SystemExit("FAIL: modules missing from the packaged app: " + ", ".join(missing))
    print(f"PASS: all {len(REQUIRED)} required modules are inside the packaged app ({len(modules)} modules in total)")


if __name__ == "__main__":
    main()
