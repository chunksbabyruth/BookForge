# BookForge

*Made by **ChunksBabyRuth***

**One-click book maker for Windows, with experimental macOS and Linux builds in development.** Turn an EPUB, a PDF, a Word document, a text file, Markdown, HTML, or text you paste in into a print-ready book, ready to print at home and perfect-bind.

## Download

From the [Releases](../../releases) page, get **BookForge-Windows.zip** (recommended): unzip it anywhere and run `BookForge.exe` inside the folder. A single-file **BookForge.exe** is also there if you prefer, but antivirus programs are more suspicious of single-file Python apps.

No install needed. Until the program is code-signed, Windows may say "Windows protected your PC": click **More info → Run anyway**.

### macOS and Linux (experimental)

Each release also has macOS and Linux downloads, built and checked automatically on GitHub (the same tests as Windows, plus the packaged app's own preview window and a full book made by the packaged app). They still need wider testing on real computers, so please report problems through GitHub Issues.

**macOS:** download `BookForge-macOS-arm64.dmg` for Apple Silicon Macs (M1, M2, M3, M4…) or `BookForge-macOS-x86_64.dmg` for Intel Macs, open it and drag BookForge to Applications. Until the app is signed with a paid Apple Developer ID and notarized, macOS asks you to allow it the first time: open it once, then go to **System Settings → Privacy & Security** and click **Open Anyway**. If macOS says the app is "damaged" and offers only *Move to Trash*, open Terminal and run `xattr -dr com.apple.quarantine /Applications/BookForge.app` once. The DMG includes these steps.

**Linux (x86_64):** `BookForge-Linux-x86_64.zip` is the folder version (extract it and run `BookForge/BookForge`); `BookForge-Linux-x86_64-single-file.tar.gz` holds a single `BookForge` program. Built on Ubuntu 24.04, so it needs a Linux with glibc 2.39 or newer.

**Signing the Mac app properly (for the maintainer):** with an Apple Developer Program membership, add these repository secrets and every build is signed with the hardened runtime, notarized and stapled automatically, so macOS opens it without any warning: `MACOS_CERTIFICATE_P12_BASE64` (your *Developer ID Application* certificate exported as .p12, base64-encoded), `MACOS_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_SPECIFIC_PASSWORD` (made at appleid.apple.com), and optionally `MACOS_SIGNING_IDENTITY`. Without them the app is ad-hoc signed.

### About antivirus warnings

BookForge is built with PyInstaller, and some antivirus programs wrongly flag PyInstaller apps because other programs (including malware) use the same packaging. Each release is built automatically on GitHub from the public source code in this repository. If Windows Defender still flags a release, please open an issue.

## What it does

- **Keeps the text word for word.** Italics, bold, strikethrough, underline, lists, poetry line breaks and footnote numbers carry over; only invisible typesetting characters are tidied.
- **PDF files, two ways:** *Keep the pages as they are* prints the PDF's own pages and arranges them for binding (any PDF, scanned ones too; pages of different sizes or turned sideways are fitted, never stretched). *Rebuild as an editable book* reads the text out of the PDF (with bold, italics, headings, lists and pictures, leaving out page numbers and running heads) so you can edit it and change its fonts and layout like any other book. Scanned PDFs have no text to read; run them through an OCR program first.
- **Keep the source's look (optional):** words the source set in another font, size or colour, and centred, right-aligned or indented paragraphs, look that way in the book too, for Word, EPUB/HTML and rebuilt PDF files. Normal text follows your own layout settings.
- **Finds chapters automatically** from EPUB headings (checked against the book's own contents list), "Chapter 1" lines, Markdown `#` headings, ALL-CAPS lines or your own pattern. The **Chapters** step shows every chapter, how it starts and its word count. You can rename, skip, reorder or merge wrongly split chapters before building, and your edits are never thrown away without asking: merging keeps a page number typed for the merged chapter's contents entry (it moves to the chapter it joins), and when both chapters have a different typed number you choose which one stays or cancel the merge.
- **Edit your book like a word processor:** the **Specific Text Edit** step lists your chapters (add, rename, delete, reorder) next to a Word-style editor: type and delete text, bold, italic, underline, strikethrough, superscript/subscript, any font (included, installed or your own), size, colour, paragraph styles (heading, quotation, list, poetry, section break, author's note), alignment, indent and spacing, undo/redo, find & replace. **Preview this chapter** shows it on the page; the preview's **Edit this chapter** jumps back. Your source file is never changed: not by editing, saving a project or making the book (if a file BookForge makes would have the source's own name, it is saved with " (BookForge)" added).
- **Pictures:** **Insert picture…** puts a picture (PNG, JPEG, GIF, BMP, TIFF or WebP) where the cursor is, shown as a small copy in the text. Double-click it to choose its size (it keeps its shape), alignment, and whether it sits in the text, on a page of its own, or fills the whole page edge to edge. The picture window tells you how sharp it will print.
- **Edit the front and back pages too:** the Specific Text Edit list also has the **front pages** (title page, bookplate, dedication, extra front page, work info, summary, author's notes, contents, text before chapter 1) and the **back pages** ("THE END", end pages such as an afterword or acknowledgements, the Notes pages and the back-cover text). Edit them like a chapter: words, fonts, sizes, bold, italic, underline, colours, alignment, indents and space above, plus pictures on the extra front page, the text before chapter 1 and the end pages. A page you haven't changed is made from your settings exactly as before, and **Back to automatic** undoes your changes to a page. The title page's words are the Book info fields, so changing a line in either place changes both, and the title page still follows Layout → *Titles*. The contents show one line per entry: rename or format a line, add a line for a new entry, remove a line to hide an entry, **Move up / Move down** to reorder, **Indent +** for a sub-entry, and click a page number to type your own (the chapter itself never moves). Edited pages are saved in projects and reach the preview, the print PDF, the printing sheets, the cover (back-cover text) and the EPUB, Word, web page and text files, in the same order as the print PDF. What a format can't hold is said in the printing notes instead of being left out quietly: the bookplate is a print page (print PDF and Word), the Notes pages are lined pages for printing only, the EPUB, web page and text file have no page numbers (page numbers typed for the contents are in the print PDF and Word; Word fills in the real ones when it updates its fields) and the text file has no pictures. Pages read from the source (work info, summary, notes, contents) go back to the source's version only when you read the source again (BookForge asks first); your own pages stay.
- **Edit the contents page:** **Edit contents…** (Front & back) renames, reorders, hides or adds entries and lets you type a page number. Page numbers you don't type are worked out from the real layout every time, numbers you type are never replaced (the log tells you if one doesn't match), and every contents page has its page number. Automatic spacing keeps the last few entries from sitting alone on a page.
- **Save your work:** **File → Save project** keeps the book with every edit, picture and setting in a `.bookforge` file; **Open project** brings it all back. BookForge asks before closing with unsaved edits.
- **Preview before printing:** **Preview book** shows every page exactly as it will print, typeset by the same code as the final files, plus the folded printing sheets when imposition is on. Nothing is saved until you click **Generate printing files**.
- **Builds the whole book:** title page, "This Book Belongs To" bookplate, dedication, an extra intro page, a contents page with real page numbers, chapter headings, "THE END" and lined notes pages.
- **Title and heading placement** (Layout → *Titles: alignment & position*): the title page block (title, subtitle, author, credit) left, centred or right, how far down the page it starts, and the book title's size; chapter titles (number line, title, subtitle, ornament, and the headings BookForge adds such as Contents) left, centred or right, and how far down the page a chapter starts; part titles' alignment, position and size. The standard values print exactly as before. Headings inside your text keep their own alignment. The same settings reach every format: the Word document puts the titles in the same places on its pages as the PDF; the EPUB and web page use the same alignment and sizes, with each position turned into space above the title (a screen has no fixed page height); the plain text file has no layout. The front cover has its own **Cover title alignment** (standard: the same as the title page) and **Cover title position** (Output → *Cover*), because its title, subtitle and author are laid out differently from the title page.
- **Blank pages at the beginning and end** (Front & back step): any number from 0 to 500 of truly blank pages before and after the book. They are real pages of the book, folded into the signatures like any other page, with no page number or running head; the book's own page numbers are not shifted by them. Signature padding and flyleafs are separate and still added as before. They are in the print PDF, the printing sheets and the preview; the EPUB, Word, web page and text files leave them out.
- **Typography:** 14 free book and title fonts included (see *Fonts* below), any installed font, or your own font files (**My fonts…**: choose one file and BookForge finds the family's Regular, Italic, Bold and Bold Italic in the same folder) (Regular / Italic / Bold / Bold Italic, OpenType included), with separate fonts for body text, headings and drop caps. Hyphenation in 20 languages with your own dictionary for invented words, and no widows, orphans or one-word last lines.
- **Book page size and layout:** the **Book page size** (Layout step) is the size of each finished page of the book: 34 sizes plus custom (US trade sizes such as 5 x 8, 5.5 x 8.5, 6 x 9 and 6.14 x 9.21 in; A4, A5, A6; ISO B4, B5 and B6; JIS B5 and B6; the traditional British octavo and quarto sizes and A- and B-format paperbacks), mirrored margins, drop caps 2–5 lines tall with rules for opening quotation marks, ornaments, running headers, and several page-numbering styles.
- **Section breaks:** recognises the markers your text uses (`***`, `~`, `o0o`…) and centres them.
- **Fanfiction downloads (AO3, FanFicFare):** optional work-info and summary pages, and author's notes set apart, kept as written, or left out.
- **Never prints black boxes.** Characters missing from your font (accented Greek, Hebrew, symbols, CJK) are drawn with another installed font that has them.
- **Removes boilerplate** from Project Gutenberg, Standard Ebooks and AO3 files.
- **Easy on the eyes:** dark mode (the default) or light mode, switched with the button at the top right. **Settings & storage** (same place) shows where BookForge keeps its files, lets you clear them, and lets you choose your own fonts folder.
- **Update check:** **Check for updates** (top right) asks GitHub for the newest published release and shows what's new with a link to its download page. BookForge also checks quietly when it starts (you can turn this off in Settings & storage). It only reads the version number and notes: nothing is downloaded or installed.

### Binding (imposition)

Everything needed to print a book for hand binding, built in:

- **Layouts:** folio, quarto, octavo, sextodecimo, small multi-signature layouts and the one-sheet zine
- **Signatures:** booklet, perfect bound, standard, or custom sizes, plus flyleafs. Custom sizes (for example `4, 4, 6, 6` sheets) are used in that order and only as many as the book needs (the last size repeats when the list runs out); each signature keeps its size, so only the last one is completed with blank pages. Sizes are whole numbers of sheets separated by commas; anything else (such as `4.5`) is pointed out before a preview or build instead of being guessed. The printing notes say how many blank pages complete the last sheet or signature, count flyleafs separately, list the blank pages you added and the pages the layout leaves blank on purpose (left-hand pages before right-hand chapter starts, the back of the cover picture) apart from the padding, and name any signature that holds only flyleaf pages
- **Checked for empty pages:** every book BookForge makes is checked for pages with nothing printed on them that no setting asked for (asked for: blank pages at the beginning or end, the left-hand page before a right-hand start, the back of a front cover picture). If one turns up, the preview, the log and the printing notes name the page, so you can check it before printing
- **Pages:** page range and page rotation
- **Page placement:** scaling (*Keep proportional* fits the page inside the margins without changing its shape, *Stretch to fit* fills the space inside the margins, *Original size* never scales), position (*Centered* or *Snug against binding edge*), fore-edge, binding, top and bottom margins, and offsets that move every page toward the fore-edge or the top (negative: toward the spine or the bottom). Everything is in points (72 pt = 1 inch). A page bigger than its space is cut off at the edge of its space, never printed over its neighbours, and the printing notes say so
- **Adjust page placement…:** a live view of a printing sheet drawn to scale, with the book's real pages, the margins and the spine, and the measurements of the page you click (sizes, scale, position and the white space on every side, in points). It changes as you change any setting; drag a page, or use the arrow keys, to set the offsets. The printing files use exactly the same placement
- **Marks:** fold lines, cut lines, spine edge marks, signature order marks and sewing marks
- **Printing:** duplex or single-sided printing, and aggregated and/or per-signature files
- **Printer paper size:** the **Printer paper size** (Output step) is the sheet of paper that goes through your printer, with the book pages arranged on it: 68 paper sizes, at their exact standard sizes (US Letter, Legal, Tabloid, Ledger, ANSI C to E; ISO A0 to A10 and B0 to B10; JIS B0 to B10; SRA3, SRA4 and Super B / A3+; Arch A to E1; foolscap, ID card, book and paperback sizes) or a size of your own: tick **Use a custom printer paper size** (Printer paper size then says Custom; untick it to go back to the paper you had). The chosen paper's size is shown next to it in the **display unit for paper selection** (inches, millimetres, centimetres or points); a custom size is typed in that unit (decimals allowed), keeps its real size when you change the unit, and is checked (more than 0, at most 200 inches a side) before anything is made

### Output formats

- Print-ready PDF (pages in reading order, with clickable bookmarks)
- Imposed PDF for binding
- Wraparound cover with your own front and back pictures (fill or fit the panel, title over the picture if you like), a spine width estimated from your paper weight or typed in after you measure, and a cover view in the preview
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

- **Settings and font caches:** `%APPDATA%\BookForge` (on macOS and Linux: a `BookForge` folder in your home folder). You can open it, or clear it, from **Settings & storage**. Deleting this folder is safe.
- **Books you make:** `Documents\BookForge Books`, unless you choose another folder on the Output tab.
- **Your extra fonts:** `Documents\BookForge Fonts`, unless you choose another folder in Settings & storage.

## Versions and releases

Versions go up by 0.1 for each minor update (1.5.0, 1.6.0, 1.7.0, 1.8.0 ...) and by 0.0.1 for a bug-fix update (1.5.1). To publish one, set `APP_VERSION` in `bf_core.py` (and the numbers in `version_info.txt`), commit, then push a matching tag:

```
git tag v1.8.0
git push origin v1.8.0
```

GitHub then runs the tests, builds the program, checks that the fonts, their licences and the preview engine are inside it, and attaches `BookForge-Windows.zip` and `BookForge.exe` to the v1.8.0 release; the macOS and Linux workflow attaches its packages and the release notes to the same release. Check that the tag matches `APP_VERSION` before pushing it (the workflows don't check). **Run workflow** on the Actions tab also works: the Windows build asks for a release tag and attaches the files to that release (making the release if it doesn't exist yet), and the macOS and Linux build only attaches to a release when you type a tag; otherwise its packages stay downloadable from that run.

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
| `bf_impose.py` | imposition: layouts, signatures, marks, paper sizes, page placement (one function places the pages for both the PDF and the placement window) |
| `bf_placement.py` | the Adjust page placement window |
| `bf_pdfin.py` | PDF files as sources: pages kept as they are, or text rebuilt into an editable book |
| `bf_pictures.py` | pictures: reading, converting, sizes, cover pictures |
| `bf_keepfmt.py` | keeping the source's own fonts, sizes, colours and alignment |
| `bf_update.py` | the update check (reads GitHub's newest release; downloads nothing) |
| `bf_fonts.py` | font discovery, custom families, OpenType conversion |
| `bf_theme.py` | the colour theme |
| `tests/` | regression tests: `python tests/test_impose.py`, `test_preview.py`, `test_editor.py`, `test_chapters.py`, `test_build.py`, `test_page_placement.py` and the others in the folder. Tests that need real books look for your own copies in `tests/inputs/` (never committed) named `ao3_story.epub`, `ao3_oneshot.html`, `gutenberg.epub` and `standard_ebooks.epub`, and skip themselves when they're missing |

## License

MIT © 2026 ChunksBabyRuth. See [LICENSE](LICENSE). Built with ReportLab, pypdf, Beautiful Soup, Pillow, python-docx, pyphen, fontTools, pypdfium2 (preview; BSD-3-Clause / Apache-2.0) and PyInstaller, each under its own license.

Please only print books you're free to reproduce, such as public-domain works, openly licensed works, or your own writing.
