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
- **Finds chapters automatically** from EPUB headings (checked against the book's own contents list), "Chapter 1" lines, Markdown `#` headings, ALL-CAPS lines or your own pattern. The **Chapters** step shows every chapter, how it starts and its word count. You can rename, skip, reorder or merge wrongly split chapters before building, and your edits are never thrown away without asking.
- **Edit your book like a word processor:** the **Edit** step lists your chapters (add, rename, delete, reorder) next to a Word-style editor: type and delete text, bold, italic, underline, strikethrough, superscript/subscript, any font (included, installed or your own), size, colour, paragraph styles (heading, quotation, list, poetry, section break, author's note), alignment, indent and spacing, undo/redo, find & replace. **Preview this chapter** shows it on the page; the preview's **Edit this chapter** jumps back. Your source file is never changed.
- **Save your work:** **File → Save project** keeps the book with every edit, picture and setting in a `.bookforge` file; **Open project** brings it all back. BookForge asks before closing with unsaved edits.
- **Preview before printing:** **Preview book** shows every page exactly as it will print, typeset by the same code as the final files, plus the folded printing sheets when imposition is on. Nothing is saved until you click **Generate printing files**.
- **Builds the whole book:** title page, "This Book Belongs To" bookplate, dedication, an extra intro page, a contents page with real page numbers, chapter headings, "THE END" and lined notes pages.
- **Typography:** 14 free book and title fonts included (see *Fonts* below), any installed font, or your own font files (**My fonts…**: choose one file and BookForge finds the family's Regular, Italic, Bold and Bold Italic in the same folder) (Regular / Italic / Bold / Bold Italic, OpenType included), with separate fonts for body text, headings and drop caps. Hyphenation in 20 languages with your own dictionary for invented words, and no widows, orphans or one-word last lines.
- **Page layout:** 9 page sizes plus custom, mirrored margins, drop caps 2–5 lines tall with rules for opening quotation marks, ornaments, running headers, and several page-numbering styles.
- **Section breaks:** recognises the markers your text uses (`***`, `~`, `o0o`…) and centres them.
- **Fanfiction downloads (AO3, FanFicFare):** optional work-info and summary pages, and author's notes set apart, kept as written, or left out.
- **Never prints black boxes.** Characters missing from your font (accented Greek, Hebrew, symbols, CJK) are drawn with another installed font that has them.
- **Removes boilerplate** from Project Gutenberg, Standard Ebooks and AO3 files.
- **Easy on the eyes:** dark mode (the default) or light mode, switched with the button at the top right. **Settings & storage** (same place) shows where BookForge keeps its files, lets you clear them, and lets you choose your own fonts folder.

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

## Fonts

**Included** (SIL Open Font License 1.1, original files from [Google Fonts](https://github.com/google/fonts)):
Alegreya, Baskervville, Crimson Pro, EB Garamond, Gelasio, Libre Baskerville, Libre Caslon Text, Literata, Lora and Source Serif 4. For titles: Cinzel, Cormorant Garamond, IM Fell English and Playfair Display.

**Licences:**
- **In the repository:** each font's own licence is in `fonts/<font>/OFL.txt`, unchanged from Google Fonts.
- **In the program:** the licences ship inside it (`_internal\fonts\<font>\OFL.txt`) and can be read under **Help → Fonts & licences**.

**Reserved font names:** Libre Baskerville, Lora and Playfair Display declare one.

**Original static files:** every family ships with its original static Regular, Italic, Bold and Bold Italic files, as published on Google Fonts, used unchanged. Where those came with a licence worded differently from the repository copy, it ships verbatim as `fonts/<font>/OFL-static-files.txt` next to `OFL.txt`. Both appear under Help → Fonts & licences. The Source Serif 4 static files carry their copyright notice inside the font files themselves ("© 2014 - 2021 Adobe Systems Incorporated … with Reserved Font Name 'Source'"); the `OFL.txt` beside them also has a copyright line.

**How bold is made:** most included fonts are also variable fonts. When a font folder has no static file for a style, BookForge makes a static Bold or Regular instance on your PC the first time you use it. Each instance gets a neutral internal name ("BFInst…"), never a reserved font name. If original static files (for example `Lora-Bold.ttf` from a Google Fonts download) are in `fonts/<font>/`, they are used exactly as they are. Missing styles are never faked: Cinzel has no italic, and IM Fell English has no bold.

**Commercial fonts can't be included:** Garamond, Palatino Linotype, Book Antiqua, Georgia, Baskerville, Caslon, Minion Pro, Bembo and Sabon. Several come with Windows or Microsoft Office. They appear in the font lists automatically once installed. You can also put font files in your fonts folder (Settings & storage) or add them with **My fonts…**.

## Where BookForge keeps its files

- **Settings and font caches:** `%APPDATA%\BookForge`. You can open it, or clear it, from **Settings & storage**. Deleting this folder is safe.
- **Books you make:** `Documents\BookForge Books`, unless you choose another folder on the Output tab.
- **Your extra fonts:** `Documents\BookForge Fonts`, unless you choose another folder in Settings & storage.

## Versions and releases

Versions go up by 0.1 for each minor update (1.5.0, 1.6.0, 1.7.0 ...). To publish one, set `APP_VERSION` in `bf_core.py` (and the numbers in `version_info.txt`), commit, then push a matching tag:

```
git tag v1.5.0
git push origin v1.5.0
```

GitHub then runs the tests, builds the program, checks that the fonts, their licences and the preview engine are inside it, and attaches `BookForge-Windows.zip` and `BookForge.exe` to the v1.5.0 release. The build stops if the tag and `APP_VERSION` don't match. **Run workflow** on the Actions tab makes a test build you can download from that run, without touching any release.

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
| `bf_edit.py` | the editing model: paragraphs ⇄ formatted text, project files |
| `bf_build.py` | the one-click build pipeline |
| `bf_impose.py` | imposition: layouts, signatures, marks |
| `bf_fonts.py` | font discovery, custom families, OpenType conversion |
| `bf_theme.py` | the colour theme |
| `tests/` | regression tests: `python tests/test_impose.py`, `test_preview.py`, `test_editor.py`, `test_chapters.py`, `test_build.py`. Tests that need real books look for your own copies in `tests/inputs/` (never committed) named `ao3_story.epub`, `ao3_oneshot.html`, `gutenberg.epub` and `standard_ebooks.epub`, and skip themselves when they're missing |

## License

MIT © 2026 ChunksBabyRuth. See [LICENSE](LICENSE). Built with ReportLab, pypdf, Beautiful Soup, Pillow, python-docx, pyphen, fontTools, pypdfium2 (preview; BSD-3-Clause / Apache-2.0) and PyInstaller, each under its own license.

Please only print books you're free to reproduce, such as public-domain works, openly licensed works, or your own writing.
