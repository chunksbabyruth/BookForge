# BookForge

*Made by **ChunksBabyRuth***

**One-click book maker for Windows.** Turn an EPUB, a text file, Markdown, HTML, a Word document, or text you paste in into a print-ready book, ready to print at home and perfect-bind.

## Download

From the [Releases](../../releases) page, get **BookForge-Windows.zip** (recommended): unzip it anywhere and run `BookForge.exe` inside the folder. A single-file **BookForge.exe** is also there if you prefer, but antivirus programs are more suspicious of single-file Python apps.

No install needed. Until the program is code-signed, Windows may say "Windows protected your PC": click **More info → Run anyway**.

### About antivirus warnings

BookForge is built with PyInstaller, and some antivirus programs wrongly flag PyInstaller apps because other programs (including malware) use the same packaging. Each release is built automatically on GitHub from the public source code in this repository, with a custom-compiled launcher to reduce these false alarms. If Windows Defender still flags a release, please open an issue.

## What it does

- **Keeps the text word for word.** Italics, bold, poetry line breaks and footnote numbers are carried over; only invisible typesetting characters are tidied.
- **Finds chapters automatically** from EPUB headings, "Chapter 1" lines, Markdown `#` headings, ALL-CAPS lines or your own pattern. You can review, rename, skip or reorder them before building.
- **Builds the whole book:** title page, "This Book Belongs To" bookplate, dedication, an extra intro page, a contents page with real page numbers, chapter headings, "THE END" and lined notes pages.
- **Page layout:** 9 page sizes plus custom, mirrored margins with an extra spine margin, any installed font, drop caps, ornaments, running headers, and several page-numbering styles.
- **Never prints black boxes.** Characters missing from your font (accented Greek, Hebrew, symbols, CJK) are drawn with another installed font that has them.
- **Removes boilerplate** from Project Gutenberg and Standard Ebooks files (license, imprint, colophon).

### Output formats

- Print-ready PDF (pages in reading order, with clickable bookmarks)
- **Imposed PDF for binding:** 2 pages per landscape sheet, in signatures, with fold and signature-order marks
- Wraparound cover template with a spine width calculated from your paper
- EPUB, Word (.docx), HTML and plain text

Full printing and perfect-binding instructions are under **Help** in the program.

## Command line

```
BookForge.exe --cli "book.epub" "C:\output folder" [preset.json]
```

## Building from source

Requires Python 3.10+ on Windows.

```
pip install -r requirements.txt
python BookForge.py              # run it directly
build_exe.bat                    # or build the program folder (appears in dist\BookForge)
```

| File | Purpose |
|---|---|
| `BookForge.py` | the window and command-line mode |
| `bf_core.py` | reads source files, detects chapters, keeps text verbatim |
| `bf_pdf.py` | typesetting: fonts, margins, page numbers, contents, font fallback |
| `bf_export.py` | imposition, cover, EPUB, DOCX, HTML, TXT |
| `bf_build.py` | the one-click build pipeline |

## License

MIT © 2026 ChunksBabyRuth. See [LICENSE](LICENSE). Built with ReportLab, pypdf, Beautiful Soup, Pillow, python-docx and PyInstaller, each under its own license.

Please only print books you're free to reproduce, such as public-domain works, openly licensed works, or your own writing.
