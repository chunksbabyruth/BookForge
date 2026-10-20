# BookForge

**Turn digital books and documents into books you can print and bind at home.**

BookForge is a free, open-source desktop application for turning ebooks, documents, and your own writing into print-ready books. Customize the layout, edit chapters, choose your fonts, preview every page, and generate files for printing and binding.

Whether you're preparing a novel, printing a fanfiction, making a personal collection, or creating a book from your own writing, BookForge gives you control over the process.

- Edit and organize chapters before building your book.
- Customize fonts, typography, page layouts, and margins.
- Add front matter, contents pages, chapter headings, and more.
- Preview your book before generating the final files.
- Create print-ready PDFs, binding layouts, and cover templates.
- Save your work as a project and return to it later.

**Free and open source. Available for Windows, with experimental macOS and Linux builds.**

## Download BookForge

**[Download the latest release](../../releases)**

### Windows (recommended)

1. Open the [Releases page](../../releases).
2. Download `BookForge-Windows.zip`.
3. Extract the ZIP file into a folder of your choice.
4. Open the extracted folder and run `BookForge.exe`.

No installation is required. Keep the extracted folder together so the application can access its bundled files.

A standalone `BookForge.exe` is also available in releases, but the folder version is recommended.

**Windows security warnings:** Windows may display a warning because the application is not code-signed. Only run software you trust and have downloaded from the official repository. If you choose to proceed, Windows may provide a **More info** option followed by **Run anyway**.

### macOS (experimental)

BookForge provides separate downloads for both Mac processor types:

- `BookForge-macOS-arm64.dmg` — Apple Silicon Macs, including M1, M2, M3, and M4.
- `BookForge-macOS-x86_64.dmg` — Intel Macs.

Open the downloaded DMG and drag BookForge into your Applications folder.

Because the application is not yet signed and notarized with an Apple Developer ID, macOS may block its first launch. If you trust the download, follow the security instructions included with the DMG to allow the application to open.

If you encounter an installation or launch problem, please report it through [GitHub Issues](../../issues).

### Linux (experimental)

Linux downloads are available for x86-64 systems:

- `BookForge-Linux-x86_64.zip` — folder-based application.
- `BookForge-Linux-x86_64-single-file.tar.gz` — single-file application.

For the folder version, extract the ZIP archive and run the `BookForge` executable inside the extracted `BookForge` directory.

The current Linux builds are produced on Ubuntu 24.04 and require glibc 2.39 or newer. Other distributions may need additional dependencies or may not be compatible.

Linux and macOS builds need more real-world testing. If you try either version, feedback about installation, importing documents, editing, previewing, and generating printing files is especially welcome.

## Help improve BookForge

BookForge is actively being developed, and feedback from real users helps make it better.

Try the available features, experiment with different books and layouts, and let me know what works well or what needs improvement.

- **Report a bug:** [Open an issue](../../issues).
- **Suggest a feature:** [Share an idea](../../issues).
- **Review the source code:** Browse this repository.

When reporting a bug, please include your operating system, the steps you took, what happened, and what you expected to happen. Screenshots and error messages are helpful.

If you have an idea for a feature that would make BookForge more useful, I'd love to hear it.

## Features

### Import and organize your books

BookForge can work with supported ebook and document formats, as well as text you paste directly into the application.

- Import EPUB, TXT, Markdown, HTML, and Word documents (`.docx`).
- Automatically identify chapters from EPUB headings, common chapter titles, Markdown headings, all-caps headings, or a custom pattern.
- Review detected chapters and their word counts before building.
- Rename, skip, reorder, or merge chapters when automatic detection gets something wrong.
- Preserve text formatting such as bold, italics, underline, strikethrough, lists, poetry line breaks, and footnote numbers where supported by the source and conversion process.
- Clean up common boilerplate from Project Gutenberg, Standard Ebooks, and AO3 files.

Your original source file is not modified by the editing process.

### Edit your book

The Edit step provides a chapter list alongside a word-processor-style editor.

You can:

- Add, rename, delete, and reorder chapters.
- Edit text and format selected content.
- Apply bold, italic, underline, strikethrough, superscript, and subscript.
- Change fonts, font sizes, and text colours.
- Use paragraph styles for headings, quotations, lists, poetry, section breaks, and author's notes.
- Adjust alignment, indentation, and spacing.
- Undo and redo changes.
- Find and replace text.
- Preview an individual chapter and return to editing it.

### Save projects and continue later

BookForge supports its own `.bookforge` project files.

Use **File → Save project** to preserve your edits, pictures, and project settings. Use **Open project** to continue working later.

BookForge also warns you about unsaved changes when you attempt to close the application.

### Preview before generating

Use **Preview book** to inspect your book before creating the final printing files.

The preview lets you review the typeset pages and, when imposition is enabled, the arranged printing sheets.

The preview uses the same typesetting code as the generated files, helping you catch layout problems before printing.

### Build a complete book

BookForge can generate common book sections, including:

- Title pages.
- A "This Book Belongs To" bookplate.
- Dedication pages.
- An additional introductory page.
- A contents page with page numbers.
- Chapter headings.
- An ending page marked "THE END".
- Lined notes pages.

Available sections and their settings can be customized through the application.

### Typography and fonts

Choose from included fonts, fonts already installed on your computer, or your own font files.

BookForge supports separate fonts for body text, headings, and drop caps. Where available, Regular, Italic, Bold, and Bold Italic styles can be used.

Additional typography features include:

- Drop caps from two to five lines tall.
- Hyphenation in 20 languages.
- Custom hyphenation dictionaries for unusual or invented words.
- Font fallback for characters missing from the selected font.
- Controls for paragraph spacing, alignment, indentation, and line layout.
- Running headers, ornaments, and multiple page-numbering styles.

### Page layout and formatting

Customize the appearance of your finished book with:

- Nine built-in page sizes and custom dimensions.
- Mirrored margins.
- Chapter-opening layouts.
- Section breaks and centered separators.
- Running headers and page numbers.
- Opening quotation mark handling for drop caps.
- Adjustable typography and paragraph spacing.

### Fanfiction support

BookForge includes options for supported AO3 and FanFicFare downloads.

Depending on the source document and selected options, you can include work information and summaries, and choose how author's notes are presented.

### Dark and light themes

Use the theme button in the top-right corner to switch between dark mode and light mode.

The **Settings & storage** area also lets you manage your application storage and choose a custom fonts folder.

## Printing and binding

BookForge includes tools for arranging pages for different book formats and printing methods.

### Layouts

Available layouts include:

- Folio.
- Quarto.
- Octavo.
- Sextodecimo.
- Small multi-signature layouts.
- One-sheet, eight-page zine.

### Binding and signatures

Choose from booklet, perfect-bound, standard, or custom signature arrangements. Flyleaf pages are also supported.

### Printing controls

Configure options such as:

- Page ranges.
- Page rotation.
- Scaling and positioning.
- Margins.
- Duplex or single-sided printing.
- Fold lines and cut lines.
- Spine-edge marks.
- Signature-order and sewing marks.
- Combined printing files or individual signature files.

Available options depend on the selected layout and output settings.

**Printing instructions:** Open the Help section inside BookForge for guidance on printing, folding, and perfect binding.

## Output formats

BookForge can generate the following output files:

| Output | Purpose |
|---|---|
| Print-ready PDF | A typeset book in reading order, with clickable bookmarks. |
| Imposed PDF | Pages arranged for supported printing and binding layouts. |
| Wraparound cover template | A cover template with spine width calculated from your paper settings. |
| EPUB | An ebook version of your book. |
| Word (`.docx`) | An editable Word document. |
| HTML | A web-readable document. |
| TXT | Plain text. |

## Included fonts and licensing

BookForge includes 14 free font families sourced from [Google Fonts](https://github.com/google/fonts).

### Included families

**Book and body fonts:**

- Alegreya
- Baskervville
- Crimson Pro
- EB Garamond
- Gelasio
- Libre Baskerville
- Libre Caslon Text
- Literata
- Lora
- Source Serif 4

**Additional title fonts:**

- Cinzel
- Cormorant Garamond
- IM Fell English
- Playfair Display

The included fonts are distributed under the SIL Open Font License (OFL), subject to each font's own license terms.

### Font licenses

Font license files are included in the repository under `fonts/<font>/OFL.txt`, along with any applicable additional license notices.

The bundled application also includes the font licenses. Open **Help → Fonts & licences** to review them.

Some fonts declare reserved font names. BookForge respects those restrictions when creating font instances.

### Font styles

Original static font files are used where provided. For supported variable fonts, BookForge can generate static font instances locally when needed.

Missing styles are not necessarily available for every family. For example, Cinzel does not include an italic style, and IM Fell English does not include a bold style in the included files.

### Using other fonts

Commercial fonts such as Palatino Linotype, Book Antiqua, Georgia, Baskerville, Caslon, Minion Pro, Bembo, and Sabon are not bundled with BookForge.

If you have a valid license for a font, you can use it by installing it on your computer, selecting it through **My fonts…**, or placing supported font files in your chosen fonts folder.

Please respect the license terms of any fonts you use.

## Where BookForge stores files

BookForge stores application settings, font caches, and generated books separately.

### Application settings and font caches

On Windows, the default location is:

```text
%APPDATA%\BookForge
```

On macOS and Linux, BookForge uses a `BookForge` folder in your home directory.

You can open or clear the application storage through **Settings & storage**.

Clearing this data removes application settings and cached files. Save any important work and back up project files before clearing storage.

### Generated books

By default, generated books are stored in:

```text
Documents\BookForge Books
```

You can choose a different output folder on the Output tab.

### Custom fonts

The default folder for additional fonts is:

```text
Documents\BookForge Fonts
```

You can choose a different fonts folder in **Settings & storage**.

## Troubleshooting

### The application will not open

- Make sure you extracted the Windows ZIP before launching the application.
- Keep the extracted application files together.
- On macOS, follow the included first-launch security instructions if Gatekeeper blocks the app.
- On Linux, confirm that your distribution meets the glibc requirement and that the executable has permission to run.

### The preview is blank or does not display correctly

Please report the issue through [GitHub Issues](../../issues).

Include your operating system, BookForge version, the steps required to reproduce the problem, and a screenshot if possible.

### Antivirus software flags the application

BookForge is packaged with PyInstaller, a tool used to distribute Python applications. Some security products flag packaged applications incorrectly.

Releases are built through GitHub Actions from the source code in this repository. However, this does not guarantee that every security product will consider every build safe.

Only download BookForge from the official repository, review the source if you have concerns, and report suspected false positives through GitHub Issues.

### Something else is not working

If a feature produces unexpected results, please report it. Include the source format, relevant settings, and a description of the problem. Remove private or copyrighted content from screenshots and attachments when possible.

## Building BookForge from source

BookForge is a Python desktop application.

### Requirements

- Python 3.10 or newer for the Windows source workflow.
- The dependencies listed in `requirements.txt`.
- Additional platform-specific dependencies may be required when running or packaging on macOS and Linux.

### Run from source

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python BookForge.py
```

### Build the Windows application

On Windows, run:

```bat
build_exe.bat
```

The packaged application folder is created under `dist\BookForge`.

### Command-line mode

BookForge also supports a command-line mode for compatible inputs and output settings:

```bat
BookForge.exe --cli "book.epub" "C:\output folder" [preset.json]
```

The optional preset file supplies configuration for the command-line build.

### Tests

The repository includes regression tests for the editor, chapter detection, preview, book generation, and page imposition.

Examples include:

```bash
python tests/test_impose.py
python tests/test_preview.py
python tests/test_editor.py
python tests/test_chapters.py
python tests/test_build.py
```

Some tests require sample books that are not included in the repository. Where applicable, those tests skip themselves when the required files are unavailable.

## Contributing and development

Bug reports, feature suggestions, and contributions are welcome.

Before submitting a code change, please consider how it affects the Windows application and its existing build process. Changes intended to add macOS or Linux support should avoid breaking the established Windows workflow.

When submitting a bug report, include the BookForge version, operating system, steps to reproduce the problem, and relevant error messages.

## License

BookForge is distributed under the MIT License.

Copyright (c) 2026 ChunksBabyRuth.

See [LICENSE](LICENSE) for the full license text.

BookForge uses third-party libraries and fonts, each subject to its own license. The bundled font license files are available under **Help → Fonts & licences**.

Please only reproduce or distribute books that you have the right to copy, such as your own writing, public-domain works, or appropriately licensed material.

---

**Thank you for trying BookForge!** If you find a bug, have a suggestion, or simply want to share what you've made, I'd love to hear from you.
