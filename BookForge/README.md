# BookForge

*Made by **ChunksBabyRuth***

**One-click book maker for Windows.** Turn an EPUB, a text file, Markdown, HTML, a Word document, or text you paste in into a print-ready book, ready to print at home and perfect-bind.

## Download

From the [Releases](../../releases) page, get **BookForge-Windows.zip** (recommended): unzip it anywhere and run `BookForge.exe` inside the folder. A single-file **BookForge.exe** is also there if you prefer, but antivirus programs are more suspicious of single-file Python apps.

No install needed. Until the program is code-signed, Windows may say "Windows protected your PC": click **More info → Run anyway**.

### About antivirus warnings

BookForge is built with PyInstaller, and some antivirus programs wrongly flag PyInstaller apps because other programs (including malware) use the same packaging. Each release is built automatically on GitHub from the public source code in this repository, with a custom-compiled launcher to reduce these false alarms. If Windows Defender still flags a release, please open an issue.

## What it does

- **Keeps the text word for word.** Italics, bold, strikethrough, underline, lists, poetry line breaks and footnote numbers carry over; only invisible typesetting characters are tidied.
- **Finds chapters automatically** from EPUB headings, "Chapter 1" lines, Markdown `#` headings, ALL-CAPS lines or your own pattern. You can review, rename, skip or reorder them before building.
- **Builds the whole book:** title page, "This Book Belongs To" bookplate, dedication, an extra intro page, a contents page with real page numbers, chapter headings, "THE END" and lined notes pages.
- **Typography:** any installed font, or your own font files (Regular / Italic / Bold / Bold Italic, OpenType included), with separate fonts for body text, headings and drop caps. Hyphenation in 20 languages with your own dictionary for invented words, and no widows, orphans or one-word last lines.
- **Page layout:** 9 page sizes plus custom, mirrored margins, drop caps 2–5 lines tall with rules for opening quotation marks, ornaments, running headers, and several page-numbering styles.
- **Section breaks:** recognises the markers your text uses (`***`, `~`, `o0o`…) and centres them.
- **Fanfiction downloads (AO3, FanFicFare):** optional work-info and summary pages, and author's notes set apart, kept as written, or left out.
- **Never prints black boxes.** Characters missing from your font (accented Greek, Hebrew, symbols, CJK) are drawn with another installed font that has them.
- **Removes boilerplate** from Project Gutenberg, Standard Ebooks and AO3 files.

### Binding (imposition)

Everything the [bookbinder-js](https://github.com/momijizukamori/bookbinder-js) imposer offers, built in:

- **Layouts:** folio, quarto, octavo, sextodecimo, small multi-signature layouts and the one-sheet zine
- **Signatures:** booklet, perfect bound, standard, or custom sizes, plus flyleafs
- **Pages:** page range, page rotation, scaling, positioning and margins
- **Marks:** fold lines, cut lines, spine edge marks, signature order marks and sewing marks
- **Printing:** duplex or single-sided printing, and aggregated and/or per-signature files

### Output formats

- Print-ready PDF (pages in reading order, with clickable bookmarks)
- Imposed PDF for binding
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
| `bf_export.py` | cover, EPUB, DOCX, HTML, TXT |
| `bf_build.py` | the one-click build pipeline |
| `bf_impose.py` | imposition: layouts, signatures, marks |
| `bf_fonts.py` | font discovery, custom families, OpenType conversion |
| `bf_theme.py` | the colour theme |

## License

MIT © 2026 ChunksBabyRuth. See [LICENSE](LICENSE). Built with ReportLab, pypdf, Beautiful Soup, Pillow, python-docx and PyInstaller, each under its own license.

Please only print books you're free to reproduce, such as public-domain works, openly licensed works, or your own writing.
