# BookForge — task tracker & resume notes

Spec: "BookForge — Fold-Line Bug, Feature Parity Audit, Chapter UI, Fonts, and Full Regression Testing"
(user-supplied, 7 sections + non-negotiable rules). Follow phases IN ORDER. Ask before any substantial
chapter-UI redesign.

Status legend: [ ] todo  [~] in progress  [x] done  [!] blocked / needs user

## Resume instructions (for Claude, if a session ends mid-way)
- Source of truth for code: latest repo zip delivered = BookForge-github-repo.zip (v1.3).
  Sandbox copies (may be lost between sessions): /home/claude/bookforge (dev), /tmp/repo/BookForge (repo copy).
  If lost: unzip BookForge-github-repo.zip from the user (ask them to re-upload) into /home/claude/bookforge.
- Windows build: Wine + standalone CPython 3.12 at /opt/winpy (python-build-standalone), PyInstaller.
  Recreate: apt install wine64; download cpython-3.12.x-x86_64-pc-windows-msvc-install_only from
  github.com/astral-sh/python-build-standalone releases; pip install pyinstaller reportlab pypdf
  beautifulsoup4 pillow python-docx pyphen fonttools. Build flags: see build_exe.bat / workflow.
- Test inputs uploaded by user: End_of_the_Line.epub (AO3), a reference imposed PDF,
  On_the_Making_of_Man_-_Imposed_for_binding.pdf (BookForge output).

## Phase 1 — Inspection
- [x] T1.1 Repo state: sandbox code == delivered v1.3 zip (all 8 .py identical). User's LOCAL git status is not visible from here -> ask user to run `git status` before applying changes.
- [x] T1.2 Fold lines: ROOT CAUSE found (see findings log F1)
- [x] T1.3 Imposition parity audit: see F2 (live app UI + its source)
- [x] T1.4 Chapter workflow: bugs B1-B3 (EPUB) and P1-P3 (pasted text) found, see F3. [!] AO3 85682851 unreachable (HTTP 525) -> need user's local copy
- [x] T1.5 Fonts: see F4
- [x] T1.6 No automated test suite exists (only ad-hoc scripts); packaging = PyInstaller (build_exe.bat, GitHub Actions workflow, Wine locally)

## Phase 2 — Report findings, ask approval for chapter UI
- [x] T2.1 Findings report delivered. User reply: repo re-uploaded (IDENTICAL to v1.3, no local changes); AO3 85682851 supplied as HTML; UI change approved IN PRINCIPLE but user wants options presented if there are several -> present options before building UI (T3.4).

## Phase 3 — Implementation (after approval where needed)
- [x] T3.1 Fold-line fix DONE: bf_impose.fold_plan records per-fold guides (face on top before each fold), _fold_line draws them; new setting fold_side (Inside default/Outside/Both) in Output > Marks. Verified: tests/test_impose.py (37/37 PASS) + visual compare with reference sheet 1.
- [x] T3.2 Parity fixes DONE: D2 rotate paper = re-layout on turned paper; D3 edge marks outermost folio only; D4 page range sorted/dedup/reversed/fallback; D5 57 reference paper sizes (+A2) and cm unit. (bf_build flip note adjusted.)
- [x] T3.3 Chapter-detection fixes DONE (bf_core.py), all verified:
      EotL EPUB 35->28, Ulmo HTML 1->22, Ulmo paste 24->22, EotL paste 81->28; Grimms 62 / Gregory 33 unchanged.
      Fixes: AO3 labels not chapters (AO3_LABEL_RE); number-words-only chapter labels; "Chapter N." paragraphs
      when headings give <=1 chapter (PARA_CHAPTER_RE); EPUB toc.ncx/nav check demotes in-story headings;
      see-end-notes line (+label) -> note; AO3 Preface/title pages -> work info/summary/notes; long tag lists
      kept as work info; "Rating:"+value lines joined in pasted text; pasted note labels open notes (front:
      until next label/heading; chapter-start: 1 paragraph unless a "Chapter Text" line exists; end notes:
      to next chapter); un-numbered "Chapter ..." lines ignored when most chapters are numbered;
      text-loss edge case fixed (one-line chapter swallowed as a title - pre-existing in v1.3).
      Text preservation: Ulmo story 23,166 words identical & in order; EotL: no duplicated words (only AO3
      chrome/labels removed or turned into note headings).
- [x] T3.4 Chapter UI = option B (user chose): new "2 Chapters" tab (bf_theme TABS + BookForge._tab_chapters).
      Plain-language "How are chapters marked?" (same internal split_mode values), table (Print tick, #, title,
      Starts with..., Words), inline rename, skip, move, NEW Merge into previous (heading goes back into the text
      as heading or line, Chapter.heading_kind), Undo all changes, preview pane, summary line. Edits protected:
      re-detect asks; build asks when source/settings changed after edits (was: silently discarded).
      Source tab now = input + cleanup + section breaks + "Next" button. Verified gui_test5 (xvfb): auto-detect,
      edits reach the PDF Contents.
- [x] T3.5 Fonts DONE: 12 OFL families bundled UNMODIFIED in fonts/<folder>/ with OFL.txt (EB Garamond, Crimson Pro,
      Source Serif 4, Libre Baskerville, Libre Caslon Text*, Literata, Lora, Alegreya | display: Cormorant Garamond,
      Cinzel, IM Fell English, Playfair Display). Static Regular/Bold instances generated locally on first use
      (bf_fonts._static, cached in %APPDATA%/BookForge/fontcache) with proper style names. BUG FOUND+FIXED during
      verification: instances kept the Regular PostScript name -> PDF merged them -> bold printed as regular.
      Genuine gaps reported, not faked: Cinzel no italic, IM Fell English no bold. RFN fonts (Lora, Libre
      Baskerville, Playfair Display): originals shipped unmodified; instances only made locally.
      Not includable (commercial/system): Garamond, Palatino Linotype, Book Antiqua, Georgia, Baskerville, Caslon,
      Minion Pro, Bembo, Sabon -> selectable when installed (existing scan) or via My fonts. *Libre Caslon Text
      offered as a free Caslon alternative, labelled as itself.
      Packaging: --add-data "fonts;fonts" added to build_exe.bat + workflow.

## Phase 4 — Verification
- [x] T4.1 tests/test_impose.py 37/37, tests/test_chapters.py 16/16, tests/test_build.py 21/21 (final code)
- [x] T4.2 Word-for-word: Grimms 100,836 + Gregory 39,644 words, 0 differences; Ulmo story 23,166 words in order
- [x] T4.3 GUI (xvfb): Chapters step auto-detect, edit/merge/skip/rename, edit protection, edits reach PDF contents
- [x] T4.4 Windows build (Wine): folder + single-file v1.4; CLI build of Ulmo with included fonts -> genuine
       bold embedded, fold lines on inside faces; window opens with 6 steps
- [x] T4.5 Found+fixed during verification: bold instances printed as regular (font naming); single-file app
       re-prepared fonts every run (cache key); AO3 HTML title had author/fandom appended

## Phase 5 — Final report
- [x] T5.1 delivered with v1.4 (BookForge-github-repo.zip, BookForge-Windows.zip, BookForge.exe)

## Findings log
(appended as work proceeds)

F1 Fold lines (verified by measuring both PDFs with pdfplumber):
- Reference (portrait 612x792, content rotated): fold line y=396 drawn on PDF pages 1,3,... = the
  INSIDE face of each folio (pages that meet at the fold, e.g. contents 2|3). Outside faces have none.
- BookForge v1.3 (landscape 792x612): fold line x=396 on PDF pages 1,3,... = BookForge's "front" side, which is
  the OUTSIDE face (title page + last page of the signature).
- Code: bf_impose.py marks loop: `if s["fold_marks"] and side["front"]:` draws EVERY internal cell boundary on the
  front side. fold_plan() lays sheets printed-first-side DOWN, so "front" = outside of every fold.
- So root cause is not a left/right coordinate slip: fold lines are tied to the wrong FACE, and for multi-fold
  layouts all folds are drawn full-length on one face although each fold is made with a different face on top.
- Reference rule: 1st fold on inside face full length; later folds on the
  other face, only over the half that is showing, distinct dash patterns per fold.
- Planned fix: derive fold-guide segments from the fold simulation (for fold k: crease segment on the face that is
  on top of the packet just before fold k, only across the top layer's cells), convert to each face's print
  coordinates; add setting "Fold lines on: Inside (recommended) / Outside / Both". Rotations (/Rotate) are applied
  after the overlay merge, so lines follow rotate_back / rotate_paper automatically (verify in testing).


F2 Imposition parity (against a reference imposer; BookForge v1.3):
 OK (implemented; verify output in Phase 4): folio/quarto/octavo/sextodecimo; 7 small layouts incl. 8-page zine;
   booklet/perfect/standard/custom signatures; flyleafs; 5 source-rotation styles; duplex/single-sided split files;
   alternate page rotation (= BookForge "rotate back sides"); keep proportional/stretch/original; centered/binding-
   aligned; fore/binding/top/bottom margins; packed/distributed + small-layout fore-edge padding; cut lines;
   signature order marks; sewing marks (4 placements, margin A, stations B, tape C); aggregated/signatures/both.
 DIFFERENT / INCORRECT:
   D1 fold lines on wrong face (F1) + all folds drawn full length on one face (reference: per fold, per face).
   D2 "Rotate paper 90" - reference swaps paper orientation and re-lays out (proportions change);
      BookForge only sets /Rotate 90 on output pages.
   D3 PDF bounds indicators - reference: only on the OUTERMOST folio of each signature; BookForge: every page.
   D4 Page range - reference sorts + de-duplicates, accepts reversed ranges (6-4), falls back to ALL pages on
      invalid input; BookForge keeps typed order, duplicates allowed, reversed range = empty, invalid = error.
   D5 Paper sizes - reference has 65 named sizes; BookForge 15 + custom. Custom units: reference display units
      in/cm/mm/pt (custom entered in pt); BookForge in/mm/pt (no cm).
 INTENTIONALLY DIFFERENT (keep): landscape sheets instead of portrait-with-rotated-pages (prints identically);
   BookForge prints the outside face first, reference the inside face first (duplex pairs either way); extra
   "backs in reverse order" option; marks also on small layouts (reference: not supported there).
 MISSING: reference "Preview" button (BookForge opens the output folder instead) - propose: not needed / optional.

F3 Chapter detection (End_of_the_Line.epub = AO3 work 84070831 by Ally_Kats, Calibre-processed; NOT 85682851):
 EPUB: 35 "chapters" detected vs 28 real.
   B1 AO3 preface becomes 2 chapters ("Preface", and work title "End of the Line" holding summary/notes);
      summary not moved to the summary page; meta (8 lines) was harvested correctly.
   B2 "Chapter Notes" label + "See the end of the chapter for notes" (no parentheses, no blockquote after it)
      are printed as story paragraphs.
   B3 5 false chapters: the author used <h2 class="heading"> inside story text (e.g. "Chase's eyes were wide...",
      "anditsacitywithnoone..."). Real chapters are the ones listed in the EPUB's own table of contents
      (toc.ncx). Proposed fix: when an EPUB TOC exists and matches most chapter-level headings, headings missing
      from the TOC become in-chapter sub-headings (guarded; Grimms/Gregory regression must stay 62/33).
 Pasted text (stand-in: same story converted to plain text; real AO3 85682851 not reachable):
   81 "chapters" vs 28.
   P1 KEYWORD_RE treats any line starting with "Chapter" as a heading -> "Chapter Summary", "Chapter Notes",
      "Chapter End Notes" (and AO3's "Chapter Text") become chapters.
   P2 LABEL_RE accepts any word after "Chapter" ([a-z-]+), so "Chapter Notes" is taken as a chapter LABEL and
      merged with the next line as a title.
   P3 Author's notes in plain text have no blockquote, so label lines can't delimit notes; needs the real AO3
      paste to design boundaries (AO3 page may contain a "Chapter Text" line usable as delimiter).
 UI problems (Source tab): see report; awaiting approval of the proposed design (D-UI).

F4 Fonts (official Google Fonts repo, ofl/<name>/OFL.txt = HTTP 200 => SIL OFL, redistributable):
   EB Garamond, Crimson Pro, Source Serif 4, Libre Baskerville, Literata, Lora, Alegreya, Cormorant Garamond,
   Cinzel, IM Fell English, Playfair Display (+ Libre Caslon Text as a free Caslon alternative).
   TODO before bundling: read each OFL.txt for Reserved Font Names; many are VARIABLE fonts -> need static
   Regular/Italic/Bold/BoldItalic files (prefer upstream static TTFs; instancing = modified version, RFN rules).
   Genuine-style gaps to report, never fake: IM Fell English (no Bold), Cinzel (no Italic).
 Commercial / not redistributable -> selectable only when installed (existing installed-font scan + My fonts):
   Garamond (Monotype; ships with MS Office), Palatino Linotype (Windows), Baskerville (commercial; Office has
   "Baskerville Old Face"), Caslon (commercial), Minion Pro (Adobe), Bembo (Monotype), Sabon (Linotype),
   Book Antiqua (Office), Georgia (Windows).

F5 AO3 work 85682851 = "Of the Tales of Ulmo's Daughter" by Nyeni (AO3 HTML download, Of_the_Tales_of_Ulmos.html).
   AO3 treats it as ONE chapter; the 22 chapters are plain <p>Chapter N.</p> paragraphs inside #chapters.
   Baseline v1.3: HTML import -> 1 chapter (H1 bug: paragraph chapter markers ignored when headings give <=1
   chapter); meta 7 / summary 2 / notes 1 harvested OK. Simulated paste (browser-style text from the same HTML,
   /tmp/ulmo_paste.txt) -> 24 = Preface + 22 + Afterword (P4: AO3 Preface/Afterword pages become chapters;
   meta lines split "Rating:" / value on separate lines). Real AO3 web-page paste may differ (not available).

CHANGED FILES so far (sandbox /home/claude/bookforge): bf_impose.py, BookForge.py (fold_side combo, units), bf_build.py
  (flip note), NEW tests/test_impose.py. Backup of v1.3 bf_impose: /tmp/bf_impose_v13.py.

TESTS (no new framework; plain python):  python tests/test_impose.py  (37 checks)  /  python tests/test_chapters.py (16)
  test books go in tests/inputs/ (gitignored, not redistributed). Last run: 0 failures both.
WIP SNAPSHOT for the user: BookForge-WIP-repo.zip (NOT a release; version still 1.3).
DONE (v1.4). Was remaining: T3.4, T3.5, Phase 4 (full regression incl. PDFs w/ an_mode x3, fic pages, TOC/page
  numbers, all exports, GUI screenshots, EXE rebuild under Wine + CLI test), Phase 5 final report.

OPEN / NOT VERIFIED (carry forward):
- Real printer test of the new fold-line placement (only PDFs inspected).
- Real Windows (not Wine) run; first-use font preparation time on real PC.
- Pasted text taken from AO3's WEB PAGE (tested with text derived from the HTML download only).
- Small layouts: marks drawn by BookForge (reference doesn't support marks there) - not compared.
- Reference "Preview" button: not implemented (BookForge opens the output folder instead).

## v1.5 batch (requested after v1.4)
- [x] T6.1 Don't restore book-specific fields at startup (source, pasted text, title, subtitle, author, credit,
       dedication, extra page, back-cover text); keep layout/font/binding/output settings
- [x] T6.2 Auto-fill fix: a new source replaces an auto-filled title/author, never one the user typed
- [x] T6.3 File > New book (clears the book-specific fields, chapters and preview)
- [x] T6.4 Full regression PASS: test_chapters 16/16, test_impose 37/37, test_build 21/21, gui_test6 14/14 (new
       behaviour), gui_test5 chapters workflow unchanged, Grimms+Gregory 0 word differences. (BookForge.py only changed.)
- [!] T6.5 App icon: 5 options drawn (generator /home/claude/icons/make_icons.py; A Midnight Grimoire, B Teal
       Bookcloth, C Spines on a Shelf, D Ember Forge, E Binder's Needle). WAITING for user's pick -> then replace
       bookforge.ico (+ window icon uses it), bump to v1.5, rebuild repo zip.

## v1.4 (final) batch — user: "this is just going to be v1.4 again"
- [x] T7.1 Version back to 1.4 (APP_VERSION + version_info); icon A kept
- [x] T7.2 All 14 OFL.txt fetched (HTTP 200) from the exact URLs; 12 byte-identical to bundled; Baskervville +
       Gelasio added (fonts + OFL). RFN declared by: Libre Baskerville, Lora, Playfair Display (NOT Source Serif 4).
- [x] T7.3 Help > Fonts & licences viewer (each OFL.txt verbatim), About window + Settings & storage link to it
- [x] T7.4 Static files preferred; generated instances get neutral names 'BFInst<hash>' (never an RFN)
- [x] T7.5 Settings & storage: app data path (open, clear settings, clear prepared fonts); fonts folder
       (default Documents/BookForge Fonts, Change..., Open) scanned like Windows Fonts; setting 'fonts_dir'
- [x] T7.6 Dark mode (default ON), header button 'Light mode'/'Dark mode' + Settings window; switch rebuilds
       the window keeping all input, chapters, edits and tab; remembered in settings ('dark_mode'). gui_test7 12/12
- [x] T7.7 'Fonts not in the app': in every build I tested they are in the font lists; likely the user ran an
       older .exe or the fonts/ folder wasn't uploaded/committed. Now also visible in Help > Fonts & licences.
- [x] T7.8 Full regression PASS: test_chapters 16/16, test_impose 37/37, test_build 22/22 (font check now verifies
       the exact prepared fonts + no Reserved Font Name), gui_test5 OK, gui_test6 14/14, gui_test7 12/12,
       Grimms/Gregory 0 word differences. Packaging check (Wine, not delivered): 14 OFL.txt inside the program,
       byte-identical to official; Gelasio/Baskervville/Playfair embedded by the built program. Repo zip built.

## User's Google Drive fonts (folder 1yIdCAM3pyPnAZknCo41KztqYLOLXNkh0) — checked, NOT copied
- 14 family folders (Google Fonts website downloads): variable files + static/ folder + OFL.txt + README.txt each.
- All 14 have an OFL.txt. Same text as bundled (CRLF): Lora, Cormorant Garamond, Baskervville, EB Garamond,
  Gelasio, Libre Baskerville, Playfair Display. Differ: IM Fell English, Libre Caslon Text, Source Serif 4
  (website copy has NO copyright line - fails OFL condition 2; bundled GitHub copy is correct), others unmatched.
- Their variable files are a different release (e.g. Lora 210,884 vs bundled 212,196 bytes).
- Binary fonts cannot be pulled through the Drive connector (content passes through the chat as text; ~50 files
  of 100-700 KB is far too large). Static files can be added on the user's PC with add_static_fonts.ps1
  (-Fonts = local copy of that folder) or in a Claude Code / Cowork session with folder access.
- No repo files changed this session -> previous full regression + BookForge-github-repo.zip remain current.

## User's font zip added (Alegreya_..._etc.zip)
- [x] 49 original static files (Regular/Italic/Bold/Bold Italic) for 13 families copied unchanged into fonts/<font>/;
      all verified genuine (weight 400/700, italic flags, not variable). Literata + Source Serif 4: default text size.
      IM Fell English: user's files are a different release -> kept the bundled originals. Libre Caslon Text has no
      Bold Italic static -> still generated (neutral name). Cinzel: no italic (none exists).
- [x] Licences: 10 download licences differ from the repo copies -> shipped verbatim as OFL-static-files.txt beside
      OFL.txt (viewer shows both); 3 identical apart from line endings. Source Serif 4 download licence lacks a copyright
      line; notice is embedded in the font files (Adobe, RFN 'Source') and the bundled OFL.txt has one.
- [x] Full regression PASS: chapters 16/16, impose 37/37, build 22/22 (reserved-name test now checks only fonts
      BookForge generates), gui_test5 OK, gui_test6 14/14, gui_test7 12/12, classics 0 word differences.
      Packaging check: program contains 76 font files + 14 OFL.txt + 10 OFL-static-files.txt, identical to repo;
      built program embeds original Lora / Playfair / Cinzel with no font preparation.

## "Font lists only show the same 4" (user report)
- Diagnosis: a 4-entry headings list = no included AND no installed fonts found by the copy the user runs.
  Current code, frozen with PyInstaller (Wine), finds all 14 included + installed fonts (--font-report).
  Likely causes: user runs an older .exe (all builds said "1.4"), or the GitHub copy lacks fonts/ (100-file upload
  limit) so GitHub's build fails / has no fonts. NOT reproducible with the current code.
- Added: BUILD_DATE shown in title + About; live font count under the Layout font lists (red warning if no
  included fonts); Settings & storage > Fonts: counts, Rescan fonts, Font report; CLI: BookForge.exe
  --font-report out.txt; bf_fonts.font_report()/SCAN_REPORT records folders, files, errors.
- Regression PASS (chapters 16/16, impose 37/37, build 22/22, gui5 OK, gui6 14/14, gui7 12/12, gui8 5/5).
- Delivered: BookForge-Windows.zip (verification build, folder version) + BookForge-github-repo.zip.

## 2026-10-19 — macOS/Linux builds + full 1.5.0 bug check (Cowork session)
Rules: user's "BookForge — Mandatory Development Rules for Claude" (saved in the Book Forge folder and the Project).
Source of truth: GitHub main @ 682481c (= uploaded BookForge-1.5.0-complete-source.zip + cross-platform commits).
Reference copy of the 1.5.0 source: Book Forge\Source backups\BookForge-1.5.0-complete-source.zip.

The "SKIP gutenberg.epub / ao3_story.epub / ao3_oneshot.html / standard_ebooks.epub" lines in CI are the optional
real-book tests: tests/inputs/ is gitignored (books can't be redistributed), so on GitHub those checks skip. Not
needed for the build. tests/test_regressions.py (new) makes its own books so it always runs.

Bug check done (Linux, Python 3.12 + Tk 8.6 like the runners): 2,396 real builds of every option value on EPUB/TXT/
HTML(AO3)/DOCX (all 7 outputs + preview each); ~75,000 imposition checks (every layout x signature format x printer
x rotate back/paper x page counts, flyleafs, ranges, sheet sizes, source rotations: every page printed once, every
recto backs onto its verso the right way up); option-by-option output checks (page sizes, margins, fonts, sizes,
spacing, alignment, indents, page numbers x4 positions x3 styles x3 modes, hide options, running heads, chapter
starts/labels/case, drop caps x quote modes, section breaks, THE END, notes pages, front matter order, bookplate,
contents x18 variants with real page numbers, hyphenation, runts, verse, AO3 options x18, cover widths, every word
kept in PDF/TXT/HTML/EPUB/DOCX); a GUI walkthrough of every tab/control/window/editor tool (83 checks, xvfb).

CONFIRMED BUGS FIXED (each has a regression test in tests/test_regressions.py or a CI packaged-app check):
- B1 Linux/macOS packaged preview window empty: PIL._tkinter_finder not bundled (confirmed in the user's own Linux
  download). BookForge.py imports it in PreviewWindow.render; workflow adds --hidden-import; preview shows a message
  instead of a blank window if a page can't be drawn.
- B2 BookForge.py poll(): if handling one queued message raised, polling stopped for good (later builds never
  "finished"). Now always reschedules (finally).
- B3 bf_pdf: mirrored margins swapped on every other pair of pages (ReportLab autoNextPageTemplate kept each template
  for 2 pages). BookDoc.handle_pageBegin picks odd/even frame from the page number. Invisible with the default equal
  inside/outside margins; output pixel-identical when margins are equal (66 builds compared).
- B4 bf_pdf: text under a Part heading (epigraph/intro) was dropped from the print PDF (other formats had it).
- B5 bf_pdf DropLetter: missing _unRestrictSize -> build crashed when a drop-cap paragraph was laid out again
  (~10% of drop-cap builds in a sweep: small pages, big text, Continuous chapters, AO3 notes).
- B6 bf_core parse_docx: words inside Word hyperlinks were dropped (python-docx p.runs skips links).
- B7 Packaged Linux/macOS Word export failed (python-docx opens docx/parts/../templates/...; folder missing in the
  bundle; POSIX needs it, Windows doesn't). Workflow adds docx/parts to the bundle. Found by the new packaged
  full-book CI check; also present in the user's Oct 18 Linux download.
- B8 Linux mouse wheel did nothing (X11 sends Button-4/5); macOS preview wheel did nothing (small deltas). Wheel over
  another window no longer scrolls the hidden settings page.
- B9 macOS: Cmd+Q / app-menu Quit skipped the "Save your edits?" prompt -> tk::mac::Quit -> on_close. (NOT testable
  here: no Mac.) Linux/macOS window icon via iconphoto (Tk can't use .ico there).
BUILD_DATE -> 2026-10-19 (version still 1.5.0 - ask user if this should be 1.5.1).

NOT CHANGED (reported, need the user's decision):
- "Rotate back sides 180" has no effect with the two single-sided printer types (backs file never rotated).
- One-sheet zine silently uses only the first 8 pages of a longer book (no warning).
- Word import ignores tables, pictures and tracked insertions (text in tables is lost).
- Contents "Chapter N:" prefix isn't uppercased with Contents case = UPPERCASE.
- Running heads on lined Notes pages show the last chapter's title.
- A book-title <h1> at the same level as Part headings becomes a Part page; pasted text with Parts that have
  fewer than 2 chapters each makes Parts the chapters (heuristic counts >= 2x).
- A single "Chapter 1" line in pasted text isn't a chapter (needs 2+).
- AO3 HTML author isn't auto-filled (seen with a synthetic AO3 file only - check with a real one).

WORKFLOW (.github/workflows/build-cross-platform.yml) rewritten to mirror main.yml step for step; main.yml untouched.
macOS: inside-out signing (tools/macos_sign_and_package.sh): Developer ID + hardened runtime + notarytool + staple when
secrets exist (MACOS_CERTIFICATE_P12_BASE64, MACOS_CERTIFICATE_PASSWORD, [MACOS_SIGNING_IDENTITY], APPLE_ID,
APPLE_TEAM_ID, APPLE_APP_SPECIFIC_PASSWORD), otherwise correct ad-hoc signing; DMG (with "How to open" note) + ZIP;
Info.plist version; icon. "Damaged"/"Open Anyway" can only be removed with a paid Apple Developer ID ($99/yr).
Linux: folder zip (top folder BookForge/, like Windows) + single-file tar.gz (like BookForge.exe).
New CI gates: tools/check_packaged_modules.py, BookForge --preview-window-check (real preview window inside the
packaged app), full book with every format + included fonts made by the packaged app.
Verified here: Linux steps of the workflow run locally exactly as written (all pass); negative control (bug
reintroduced) makes both new gates fail. Windows: folder + single-file exe rebuilt under Wine with main.yml's exact
command from the fixed code: full book (7 outputs, EB Garamond/Cinzel embedded, margins mirrored correctly),
--preview-check and --preview-window-check pass. NOT verified: real macOS run, real Windows (only Wine), printer.

## 2026-10-19 (later) — 1.5.1: the five reported items + imposition parity (Cowork session)
User asked: make the binding settings work like the reference imposer (reference URL: aggregated, LETTER, fold lines,
stretch, perfect, flyleafs 0), check every other option against it, fix the five "NOT CHANGED" items above, and
bump the version to 1.5.1. For the convention questions the user asked for my recommendations ("ease of use and
results comparable to the reference imposer"): match print order + octavo, keep the even signature split, keep the extras.
The reference imposer was only run for comparison; none of its code is in BookForge.

FIXED / CHANGED
- bf_impose emit(): "Rotate back sides 180" now also turns the backs file for both single-sided printer types.
- bf_impose 8_zine: warning in the log, info["warning"] and the READ ME notes when book pages don't fit (counts
  flyleafs). Layout unchanged (the reference imposer also drops pages after 8).
- bf_core parse_docx: body read in document order (paragraphs AND tables; each table row -> one paragraph, cells
  joined by an em space like the HTML/EPUB importer; merged cells once; nested tables go with their cell); runs
  read through w:ins / w:moveTo / smartTag / customXml / fldSimple / sdt (tracked deletions and moveFrom left
  out); pictures (a:blip, VML imagedata) imported when Include pictures is on, in place (text before / picture /
  text after). Documents without these import exactly as before (corpus + round-tripped exports compared).
- bf_pdf contents: "Chapter N:" prefix and a chapter's own label follow UPPERCASE (Title Case leaves them, so
  roman numerals in labels survive).
- bf_pdf Notes pages: a Marker sets the running head to "Notes".
- Version 1.5.1: APP_VERSION, version_info.txt (1.5.1.0), README (tag example + corrected release text: the
  active workflows don't check tag vs APP_VERSION, Run workflow on Windows publishes to the tag you type, no
  custom-compiled launcher), root main.yml dispatch default v1.5.1, cross-platform example tag + v1.5.1 notes.
PARITY CHANGES
- Folio/quarto/octavo/16mo printing order: each signature's innermost sheet first, inside face ("B") first.
  Sides carry side["face"]; fold guides use the face, crop marks stay on the outside face. Folding notes: "lay it
  with the side that printed FIRST facing UP", "put sheet 1 into the centre of sheet 2 ...". GUI help text too.
- Octavo folds "vHV": fold 1 right edge over to the left (fold_plan supports "v"); layout now = the reference imposer.
- Paper: Ledger/ID-1/ID-2/ID-3 stored landscape like the reference imposer; a landscape entry (or custom w > h) lays out
  like the upright size with Rotate paper 90 (turn = rotate_paper XOR w > h).
- Small layouts: drop_blank_rows() leaves out first-sheet rows that are blank on BOTH sides (the reference imposer drops
  per side, which misaligns fronts/backs when a row is blank on one side only - BookForge keeps that row).
KEPT ON PURPOSE (differences from the reference imposer; the reference imposer drops pages or ignores the setting)
- Standard signature split: identical whenever the reference imposer's own plan adds up (all sizes 2-12 x 1-40 sheets);
  differs only where its formula plans more sheets than exist (e.g. 9 sheets at 8 -> 7+2; BookForge 5+4).
- Custom signature list repeats its last size (the reference imposer drops the remaining pages); open-ended ranges "12-";
  flyleafs also on small layouts; one-sided zine writes no empty backs file; rotate back also on small layouts.
- Mark styles: BookForge "Cut lines / crop marks" = trim marks around each page on the outside face; the reference imposer
  "Cutlines" = short marks at the sheet's cut folds on every face. Not changed (ask the user if wanted).
TESTS (all on this code): parity.py 184/193 SAME (9 = the kept differences above; 0 order/face notes);
impose_check 84,199 checks, 145 = 144 by-design (alternating source rotation turns versos 180, identical before
the change) + zine-flyleaf checker artifact; repo tests 0 failures incl. new tests/test_regressions_151.py (32
checks, 20 fail on the old code); test_impose.py: 5 order checks updated to the new convention; matrix 2396 builds,
12 intended "margins too large" errors, 0 output problems; semantic 2 failures (same as before, checker
heuristics; the 2 contents-UPPERCASE failures are fixed); GUI 83/83; old vs new renders: print PDFs and covers
identical in 66 builds, imposed folio/quarto = same sheets reordered; local Linux workflow run all green;
Windows (Wine): all test_*.py pass with Windows Python, folder + single-file exe rebuilt with main.yml's command,
version resource 1.5.1.0, CLI books from a Word file (tables/pictures/insertions, EB Garamond/Cinzel), octavo
single-sided rotate back, Ledger folio, zine warning, preview + preview-window checks pass.
NOT VERIFIED: real Windows/macOS hardware, a real printer and hand folding of the new octavo steps.

## 2026-10-19 (evening) — 1.6.0: PDFs, pictures, contents editing, update check (Cowork session)
User asked for (spec followed as written): no mention of the reference imposer anywhere (UI, help, docs,
changelogs, release notes; functionality kept); PDF import in two modes (default "Keep the pages as they are",
or "Rebuild as an editable book"), plus keeping the source's own formatting for all formats where possible;
pictures and cover art; an editable contents page with page numbers on every page and no stranded last
entries; the dark-mode dropdown turning white; a "Check for updates" button with a quiet startup check
(GitHub releases of chunksbabyruth/BookForge, latest published only, never download or run anything).

DONE
- Mentions removed everywhere (BookForge.py help + marks hint, bf_impose docstring/comments/fold notes,
  README, tests, this tracker, release notes). Behaviour unchanged (same imposition results as 1.5.1).
- Contents (bf_pdf): continuation pages are Table flowables, which were treated as blank pages, so their
  page numbers were hidden -> now counted as content. "Contents spacing": Automatic (default) tightens the
  spacing step by step, never below 8 pt type, when the last page would hold only a few entries; Normal;
  Compact. Contents numbers are the printed labels (1, 2... / i, ii...). Chapters have stable ids (Chapter.uid)
  so "Edit contents..." changes (Book.toc) survive renames/moves and are saved in projects. Typed page numbers
  are never replaced; the log says when one doesn't match the real page. EPUB/HTML/TXT contents follow edits.
- Pictures (bf_pictures, bf_edit, BookForge editor, bf_pdf, bf_export): Insert picture..., thumbnail in the
  text, double-click dialog (size % of text width, alignment, in text / own page / full page edge to edge,
  replace, remove, print size + dpi). Other formats converted to PNG/JPEG; EXIF rotation applied. Block fields
  img_width / img_place. Full-page pictures: no folio or running head; own-page pictures: no running head.
- Cover: front/back pictures (fill or fit), title over art optional, measured spine width (0 = estimate),
  optional front picture as page 1 (back left blank), EPUB cover image, Cover view in the preview, Preview
  cover button. Picture copies saved in projects (Book.cover_front/back) for when the files move.
- PDF input (bf_pdfin): keep mode copies pages (pypdf) at the most common size, upright (rotation baked in),
  cropped areas stay hidden, other sizes fitted and centred; preview/imposition/cover/notes use it; text
  formats are skipped with a log note. Rebuild mode reads characters with pdfium (fonts, sizes, positions,
  hyphen marks), drops running heads/page numbers (lines set apart at the page edges that repeat or are
  numbers), rebuilds paragraphs (gaps, indents, short last lines, centring), headings by size or bookmarks,
  lists, footnote lines, pictures; scanned pages kept as pictures; a scanned PDF explains OCR.
- Keep the source's look (bf_keepfmt, optional): Word, EPUB/HTML (style sheets + inline styles) and rebuilt
  PDFs keep other fonts (only fonts BookForge can use), relative sizes (%), colours, centred/right/indented
  paragraphs. Sizes in % are turned into points when typeset; paragraphs with bigger words get autoLeading.
- Dark-mode dropdown: the theme's selection colour was the light-mode tint and the clam theme shows unfocused
  selections on light grey; fixed in bf_theme for "." and every combobox/entry (both modes).
- Update check (bf_update): urllib + certifi (new small dependency, needed for secure connections in the
  packaged macOS/Linux apps) with the system certificates as fallback; header button, Help menu, Settings &
  storage toggle; startup check is silent unless a newer release exists. BOOKFORGE_NO_UPDATE_CHECK=1 turns
  the startup check off (tests).
- Version 1.6.0 (APP_VERSION, version_info.txt 1.6.0.0, README, main.yml default, cross-platform tags v*).
TESTS (all on this code): new tests/test_regressions_160.py (58 checks, no internet needed); all repo tests
0 failures (Linux and Windows Python under Wine); GUI test 0 failures + new GUI tests for contents editing,
pictures/cover, PDF modes and the update window; dropdown colours: 64 dropdowns, 0 wrong in both modes;
66 before/after builds identical; imposition checker identical to 1.5.1 (145 by-design); parity 184/193
(unchanged); semantic: same 2 checker-heuristic failures as 1.5.1; matrix 2412 builds, 12 intended "margins
too large", 0 output problems; local Linux workflow run all green; Windows folder + single-file exe rebuilt
under Wine with main.yml's commands, all required modules + certifi inside, app launches, CLI books from PDF
(kept and rebuilt), scanned PDF, Word with kept look, cover pictures + measured spine, preview checks pass.
NOT VERIFIED: real Windows/macOS hardware; a live update check against GitHub (blocked in the build
environment; tested against a local stand-in server); HTTPS from the packaged apps; OCR is not built in.

## 2026-10-20 — 1.6.0 additions: step order, paper presets and units, blank pages (Cowork session)
User asked (added to the 1.6.0 build, Windows workflow main.yml left exactly as it was):
1. Steps in this order: 1 Source, 2 Book info, 3 Front & back, 4 Chapters, 5 Layout, 6 Specific Text Edit (the
   old "Edit"), 7 Output; internal keys unchanged (src, info, front, chap, lay, edit, out).
2. Every paper preset on the requested list, the selected paper's size shown next to it, a "Display unit for
   paper selection" (inches, millimeters, centimeters, points) and a checked custom size typed in that unit.
3. "Blank pages at beginning" / "Blank pages at end": real, empty pages of the book, before imposition.

DONE
- bf_theme.TABS holds the order (key, label, colour) and tab_index(key); every place that selected a tab by
  number now uses the key (Next button, Edit chapter, editor commit on leaving the step). Ctrl+1..7 follow
  the new order. Opening Book info / Front & back / Chapters / Specific Text Edit reads the source first.
  The Shelf tab strip shrinks the tabs to fit narrow windows. Projects don't store tab numbers.
- Paper: bf_impose.SHEETS already had all 57 names on the requested list (56 sizes: Tabloid and 11x17 are the same
  sheet, merged as "Tabloid / 11x17"; Large Crown Octavo and Penguin Large Paperback share a size and keep
  both names) plus A2; nothing added, nothing duplicated. Sizes stay in points. Display units:
  in / mm / cm / pt (the requested four; no other units were asked for). New: UNIT_CHOICES, to_points / from_points,
  fmt_length, paper_label ("Letter (8.5 × 11.0 inches)"), custom_sheet_points (1 pt .. 14,400 pt = 200 in
  each side, finite numbers only, plain messages), sheet_points (Custom checked, never silently replaced).
  Output tab: "Paper size: ..." line, display unit dropdown, custom W x H in that unit. Changing the unit
  converts the stored custom size exactly (no rounding stored; 120 switches leave it unchanged); typing an
  invalid size keeps the last valid one and says so; preview/build refuse an invalid size. The sheet
  (printer paper) is separate from the book's page size; printing notes name the paper with its size.
- Blank pages (bf_core.parse_blank_count / blank_pages, 0..500 whole numbers): bf_pdf adds them before
  everything (title page, cover picture page) and after everything (notes pages, THE END); they carry no
  folio or running head (Marker -> doc.bf["userblank"]), and page labels skip the front ones, so the book's
  numbering is unchanged in every page-number style and the contents shows the printed labels. A kept PDF
  gets them through add_blank_pages (pypdf). Imposition treats them as ordinary pages; padding to fill the
  last signature and flyleafs are added on top as before. Word/EPUB/web/text files leave them out.
  Odd front counts swap left/right pages, so running heads alternate accordingly (physical parity).
  Saved in projects; older projects open with 0. bf_build.check_settings refuses an invalid blank count or
  custom paper before any file is written (CLI too).
- Fixes found on the way: the back of a front cover picture page is always blank now (it wasn't without a
  title page); bf_export's cover trim fallback used a short paper table and failed for most presets.
- GUI: hints under the new boxes wrap to the column's real width (narrow windows), errors show in red.
TESTS (on this code): new tests/test_steps_paper_blanks.py (108 checks: step order, all 57 presets and their
labels in 4 units, conversions, 342 real imposed PDFs for every preset x 3 layouts x rotation, custom sizes in
every unit, all 11 layouts x duplex/single x rotate-back x marks, signature formats, blank pages in every page
number style, blank pages imposed like marked pages in 92 layout/signature/count combinations, kept PDFs,
projects, the window); all 9 repo tests 0 failures on Linux and with Windows Python under Wine; GUI test 83
checks 0 failures; dropdown colours 88 dropdowns (incl. the unit dropdown) 0 wrong in both modes; 66
before/after builds identical to 1.6.0; imposition checker and parity identical to 1.6.0; semantic same as
1.6.0; matrix 2412 builds (12 "margins too large" + 8 refused 2000-inch custom paper, both intended) and a
176-build blank-page/paper matrix with 0 problems; Linux workflow steps run locally; Windows exes rebuilt with
main.yml's commands under Wine and used for books with blank pages and preset/custom paper.
NOT VERIFIED: real Windows/macOS hardware, real printing and folding.
LATER THE SAME DAY (reported: "the custom paper size is auto used"): the custom size was only applied when Paper size
was Custom, but its boxes were always editable and showed red messages, so it looked active. Now a "Use a custom
paper size" tick box (off by default) turns it on: ticking sets Paper size to Custom and opens the boxes, unticking
goes back to the paper chosen before (Letter if none) and greys the boxes out; choosing Custom or a preset in the
list ticks or unticks it. No new setting: the box follows sheet_size, so projects and settings are unchanged.
Text typed while unticked is never used. Tests added to tests/test_steps_paper_blanks.py (GUI section).
Released to Robert's folders as 1.6.1 (APP_VERSION 1.6.1, version_info.txt 1.6.1.0, BUILD_DATE 2026-10-20; the
v1.6.1 release notes in build-cross-platform.yml cover everything since 1.5.1, as 1.6.0 was never published).
main.yml was left exactly as it was: its manual "Run workflow" default tag still says v1.6.0, so type v1.6.1 there
(pushing the tag v1.6.1 needs nothing typed).

## 2026-10-20 — 1.7.0: paper sizes, page scaling and positioning audit, live page placement view (Cowork session)

Request: audit the paper sizes, scaling, positioning and live preview, trace every dimension from the window to
the PDF, make the preview and the PDF share one geometry, add a live "Adjust page placement" window with
diagnostics, test it all with real PDFs. Never name the reference imposer anywhere (it was used as a local
reference only; nothing copied).

- [x] Paper catalogue (bf_impose.SHEETS): exact sizes (ISO/JIS/ID/book sizes from millimetres, US/Arch from
      inches; before, they were whole points from a rounded list, up to 0.5 pt off). "Large Crown Octavo" and
      "Penguin Large Paperback" (the same size) merged into "Large Crown Octavo / Penguin Large Paperback";
      SHEET_ALIASES keeps old names (and Tabloid/11x17) opening the same paper. New: A10, JIS B8-B10, ANSI C/D/E,
      Arch D, Arch E1, SRA3, SRA4, Super B / A3+. 68 presets + Custom. Postcard kept at 283 x 416 pt (no single
      standard has that size; unchanged so old projects print the same).
- [x] Finished page sizes (bf_core.PAGE_SIZES, inches): A4/A5 exact (were 8.27 x 11.69 / 5.83 x 8.27 in);
      26 new presets (US trade, square, A6, ISO B4-B6, JIS B5/B6, British octavo/quarto, A/B-format paperbacks);
      34 + Custom. Every preset typesets with the default margins. Custom page size checked (0.1-200 in, finite)
      in core and in the window (typed text, never silently replaced). Dead bf_export.impose()/SHEET_SIZES removed.
- [x] One geometry: bf_impose.place_page / plan_imposition / Placement. impose() (the PDF) and the new
      bf_placement.PlacementWindow both use plan_imposition; the window only converts points to pixels.
      Formulas: area = cell - margins (from the page's own spine/fore-edge/head/foot); Keep proportional
      s = min(aw/w, ah/h); Stretch sx = aw/w, sy = ah/h; Original 1; Centered / Snug (against the spine-side
      margin); offsets + toward fore-edge / head. A page bigger than its cell is clipped to its cell (cropbox
      on the source page before merging) and the notes/window warn. Each page is fitted by its own size.
- [x] Offsets imp_offset_x / imp_offset_y (points, -10000..10000; margins 0..10000), checked by
      bf_impose.placement_settings (finite numbers, decimal comma, unicode minus); bf_build.check_settings
      refuses bad values before writing anything; settings_problem in the window; collect() reads the typed text.
      Old projects/settings: offsets 0; old paper names mapped in App._apply.
- [x] Marks: signature-order and sewing marks drawn on the fold (the cell's spine edge), not the page edge.
- [x] Output tab: offsets rows, hint/validation message, "Adjust page placement..." button. Window: sheet to scale,
      real typeset pages (typeset in a thread with the same bf_build.typeset), placeholders while setting,
      margins shaded, spine red, diagnostics (points), drag/arrow keys set offsets, Reset offsets, Escape closes.
      Live on every setting (var traces), 1.5 s watch for text boxes/book edits (App.book_rev counts edits).
      Its timers are cancelled when it closes.
- [x] Project switching: open project / new book / new source mark an open Preview window "Out of date" and make
      it again (when there is a book); the placement window sets the new pages.
- [x] tests/test_page_placement.py (new): catalogues, every finished preset typeset + imposed, every paper preset
      imposed (matrix and drawn content), the worked example (612 x 792 in 2004 x 2834: 3.27451, 2004 x 2593.41,
      120.29; stretch 3.27451 x 3.57828), a landscape page with margins, 360 scaling/position/margin/offset
      combinations on 4 fold layouts x 5 page shapes, source rotations, turned paper, large B sheets, clipping
      (rendered), mixed sizes, 96 imposition paths with all marks, marks on the fold, small layouts, typed-value
      checks, notes, projects, kept/rebuilt PDFs, and the window (8 configurations compared side by side with
      the preview/build PDF on every side, worked example in the window, live updates, drag, keys, reset,
      invalid values, project switching, new book, light/dark). About 900 PDFs per run.
- Version 1.7.0 (APP_VERSION, version_info 1.7.0.0); v1.7.0 release notes in build-cross-platform.yml.
  main.yml NOT changed (its manual-run default tag still says v1.6.0: type v1.7.0 there).
- After the first 1.7.0 upload (still 1.7.0, unreleased): the Windows CI run failed 2 window checks in
  tests/test_page_placement.py - the test clicked New book while BookForge was still remaking the open preview
  (slow runner; New book is ignored while busy, as always). The test now waits for BookForge to finish and for
  redraws instead of fixed pauses (reproduced and verified with a deliberately slow preview). Reported by Robert:
  (1) empty pages in the print PDF - in "Continuous" mode a part with its own text ends with a page break and the
  next part added another (bf_pdf: no second break); (2) scrolling with a dropdown list open moved the page under
  the list (App._wheel ignores the wheel while a ...popdown window is mapped). tests/test_regressions_170.py.

## 1.8.0 - core reliability fixes (Phase 2, 2026-10-27; unreleased, more phases to come)
Found in the Phase 1 audit (reproduced in the real window), fixed with tests/test_regressions_180.py:
- [x] Pictures in Specific Text Edit: a picture is now the embedded small copy named bfpic<key> (BookEditor._pics),
      not its label text or line tags. read() keeps every picture; text that ends up on a picture's line becomes
      its own paragraph (never dropped); the label (tag "pl") is never book text. normalise_pictures() puts a
      picture back on its own line after joins/typing/pastes and repairs or removes labels. Keys (Backspace,
      Delete, Enter, typing) never join or type into a picture line; styles skip picture lines; find & replace
      skips labels; cut/copy/paste carry the picture itself (BookEditor.clip). A picture whose small copy can't
      be made shows as a grey box and keeps its bytes. Picture settings find the picture by key when OK/Remove.
- [x] Source and book rules (App.changes_text / reread_source / update_source_note): the source is never changed;
      reading it makes the book; edits change only the book; an edited book is replaced only after asking.
      "Re-read source" button on the Source tab (with what would be lost). scan() clears `edited` only after a
      successful read, so a failed read keeps the book and its edits. "Keep your chapter changes?" -> Yes is
      remembered for that source. A preview that fails marks the open preview out of date. A failed editor
      commit keeps you in Specific Text Edit. "Undo all changes" keeps the book if reading fails.
- [x] Nothing to print (bf_build.book_problem / check_book / NothingToPrint): preview and build (GUI and run_build)
      refuse a book with no chapters, all left out, or no text/pictures left, with what to do; empty chapters are
      named in the log. Front text, pictures-only and poem-only chapters and kept PDFs are fine.
- [x] Titles & headings font: the PDF engine was already right for every title element (now checked from the PDF
      font resources: included/installed/custom/built-in, bold on/off, Same as body). What made it look broken:
      an open preview kept old pages (App._check_preview_current marks it out of date on any setting change),
      the editor showed headings in the body font (now the heading font), and a heading made from a paragraph
      set in one font kept that font (Heading style now clears a font set on the whole paragraph).
      Unchanged on purpose: chapter subtitles (body italic) and contents entries (body font).
- [x] Edit contents typed page numbers: Preview and Make the book use the window's changes even while it is open
      (App._apply_contents_window); its close button asks; Cancel goes back to how it was. The window says a typed
      number only changes the printed number. tests: 28 chapters, 1-14 -> 2 and 15-28 -> 3, preview, Print PDF,
      project reopen, clearing one.

## 1.8.0 - title and heading placement (Phase 3, 2026-10-27; unreleased)
- [x] Settings (bf_core.DEFAULTS, TITLE_LAYOUT_KEYS): tp_align / tp_pos (% down the text area, 20) / tp_title_size
      (0 = automatic, 1.5 x chapter title size, min 30), ch_align, part_align / part_pos (30) / part_size (0 = 1.2 x).
      chapter_sink ("Drop chapter start down") is reused for the chapter titles' position, unchanged, and moved into
      the new Layout group "Titles: alignment & position". Defaults print exactly as before (33 of 36 typeset
      configurations identical to the character; the other 3 are books that used to get an empty page, see below).
      Old projects open with the defaults (open_project_dialog setdefault). bf_pdf.title_layout checks and clamps
      every value (positions 0-90 %, sizes 0 or 6-144 pt, drop 0-12 in); text typed into a box counts as the default.
- [x] bf_pdf: styles btitle/bsub/bauth/bcred follow tp_align; label/ctitle/csub/toct and the new gsub (Contents,
      Work info, Summary/Notes, extra page and Notes headings) follow ch_align; plabel/part follow part_align; Rule
      (ornament) takes an alignment. In-text headings ("head" blocks, style sub) keep their own editor alignment.
      Title page and part blocks start at their % but are moved up just enough never to spill onto another page.
- [x] Fixed: a chapter title (and THE END) took the alignment/indent/space of the last paragraph before it
      (fmt_now was not reset between chapters).
- [x] Fixed (Phase 1 issue 8a): an empty page before a chapter whose first paragraph is longer than the rest of
      the page, with "Drop chapter start down" > 0 or after a part page in Continuous mode. KeepTop + AtTopAgain keep
      the page counted as "at the top" (ReportLab's KeepTogether otherwise breaks to the next frame); every line
      stays where it was. tests/test_titles_180.py.

## 1.8.0 - editable front & back matter and contents (Phase 4, 2026-10-28; unreleased)
- [x] Model (new bf_matter.py): Book.matter = {key: {"blocks": [Block] or None, "title": heading or None}} for 13
      pages: title, bookplate, dedication, note (extra front page), work_info, summary, work_notes, contents,
      front_text, the_end, end_matter (new: end pages after THE END), notes_page, blurb. Empty = automatic: the page is
      made from the settings/source exactly as before (auto_blocks; saving a page unchanged prints identically, all
      13 checked). Same Block/markup model as chapters; projects store it (PROJECT_FORMAT unchanged; older projects
      have no "matter" and open with every page automatic; older BookForge versions ignore the field).
- [x] One source of truth: title page and bookplate words = Book info fields / Bookplate wording (an edited page
      keeps its lines, order and formatting and shows the current words: bf_matter._synced); dedication, extra
      front page, blurb = the edited page, its plain words mirrored into the old settings, whose boxes become
      read-only while the page is edited (sync_matter_ui); fanfic pages and contents = edits kept beside what was
      read from the source (fic_meta/fic_summary/fic_notes/front_blocks/toc never changed).
- [x] Specific Text Edit: list = FRONT PAGES / CHAPTERS / BACK PAGES; select_section, _commit_section,
      Back to automatic, page heading field (note -> note_title, contents -> toc_title, others -> matter title),
      styles per page (bf_edit.MATTER_STYLES: Book title, Book subtitle, Author line, Credit line, Bookplate line,
      Dedication, Work info line, Text no indent, Closing line, Contents entry), pictures only on note, front_text,
      end_matter. Front & back tab: buttons opening each page; Book info / Output: "Edit with formatting...".
- [x] Contents as text: one line per shown entry; a page-number mark (embedded label, not text) at the end of each
      line identifies its entry (Chapter.uid) and opens the typed-page prompt. New line = custom entry, removed
      line = hidden entry, Indent = level, Space above = space, formatting = markup (words follow a renamed
      chapter: bf_matter.restyle in apply_contents_edits), Move up/down = reorder. Saved as Book.toc (same format
      as Edit contents, plus "markup"/"space"); the Edit contents window and the text never edit at the same time.
- [x] PDF (bf_pdf.matter_flowables + section()), cover blurb, EPUB / Word / web page / text exports all read
      bf_matter.section_blocks. Web page and text now also include the dedication and extra front page (they
      were missing there before).
- [x] Re-read source / preview / build re-reading the source keep the user's own pages (user_pages /
      restore_user_pages); edits to pages read from the source are listed in the "will be lost" question.
- [x] Fixed on the way (each reproduced on the Phase 3 code first): after switching light/dark on Specific Text
      Edit the text box was empty (typing there would have replaced the chapter); closing BookForge right after
      typing in Specific Text Edit closed without asking to save (the typing was lost); New book right after typing
      didn't ask either. Also select() now stays on the text when its edits can't be applied.
- [x] tests/test_matter_180.py (engine + window); tests/test_regressions_180.py list-size check follows the new list.


## 1.8.0 - blank pages and custom signature padding (Phase 5, 2026-10-28; unreleased)
Investigated with scans of the typesetter (14,224 books on the final code, 0 unexplained blank pages: every
chapter start mode, drop 0/1 in, long/short first paragraphs, headings, untitled chapters, parts with/without
text, pictures inline/own page/full page, author's notes, fanfic pages, dedication, extra page, contents, THE
END, end pages, Notes pages, blank pages, cover picture, many-chapter books, and boundary sweeps where a
chapter's text ends on every line of a page in turn before each kind of follower) and of the imposition (32,400
plans + 480 real imposed outputs rendered and checked side by side, every file). BookForge's own empty-page
check agreed with the rendered pages in every scan.
- [x] Cause 1 (typesetting): space after something (the 8 pt after an inline picture or a dedication-style line,
      the 14 pt after the fanfic summary/notes, the 8 pt after a run of author's notes, the 1 pt of an empty
      chapter) was a ReportLab Spacer. When it didn't fit below the last line it moved to the top of the next page
      on its own; the next chapter / contents / page picture then started a page later, leaving a page with
      nothing on it. Also when a line's own space after had already reached below the bottom. Fix: bf_pdf.Gap
      (a frame action: takes only the room left, none at the top of a page; where it fits it is exactly a Spacer).
- [x] Cause 2 (typesetting): a chapter with no title that opens with a picture on a page of its own (or edge to
      edge): ReportLab's PageBreakIfNotEmpty counted the chapter's invisible marks (contents link, drop space) as
      content and broke anyway. Fix: bf_pdf.PageForPicture (breaks only when something is printed on the page;
      otherwise the picture takes the page from its top), and such a chapter's contents link goes on the
      picture's page (Continuous mode pointed at the page before).
- [x] Cause 4 (typesetting): the 4 pt of space before a run of author's notes was a ReportLab Spacer too. When
      the page above was already full (a picture on a page of its own / edge to edge ending a chapter; or the
      chapter's text ending on the last line of a page when the line spacing leaves less than the paragraph
      space + 4 pt below it, as on the default Letter page) it moved to the next page alone; the note's label is
      kept with the note, and a label + note taller than a page then broke to a new page because that page was
      no longer "at the top" - leaving it empty. Fix: Gap(1, 4).
- [x] Cause 5 (typesetting): THE END emptied in Specific Text Edit with "Print THE END" still on printed its
      24 pt of space and nothing else; after a book whose text ended near the bottom of a page that space moved
      to a last page of its own. Now an emptied THE END prints nothing in the PDF either (as in EPUB/Word/HTML/TXT).
- [x] "Drop chapter start down" + long first paragraph (Phase 1 issue 8a): fixed in Phase 3 (KeepTop/AtTopAgain);
      re-checked here in 96 + 1,152 combinations with headings, untitled chapters, pictures, parts, every start mode.
- [x] Cause 3 (imposition, Phase 1 issue 8b): signature_plan used every custom size in the list, so a list longer
      than the book made whole signatures of nothing but blank pages (12-page book, folio, "4, 4, 6, 6": 68
      blanks, 3 empty signature files). Now the sizes are used in order, only as many as the book needs (the last
      repeats when the list runs out); each signature keeps its size; only the last is completed with padding.
      bf_impose.custom_sizes / signature_plan.
- [x] Printing notes (bf_build.padding_note): "N blank page(s) added after the book's last page to complete the
      last sheet/signature" (was always "to fill the last sheet", wrong for custom sizes), flyleafs counted
      apart, custom sizes not needed / repeated, signatures holding only flyleaf pages named as blank on purpose.
      plan_imposition records per_sheet, flyleaf_pages, flyleaf_only, custom, empty_spaces (small layouts).
- [x] Safety net: bf_pdf.empty_pages / empty_pages_note - after every typeset, pages with nothing printed that no
      setting asked for (planned: blank pages at beginning/end, left-hand page before a right-hand start, back of
      the front cover picture; marked with Marker(mark_planned) / userblank / fullpage) are reported: log
      WARNING, preview window line, printing notes, build_preview result "empty_pages".
- [x] Not changed (checked, correct): no padding during typesetting; flyleafs and padding counted once; plans
      and notes come from the current files (no stale counts); Standard/Perfect/Booklet plans identical.
- [x] Layout compared with Phase 4 (36 unedited test books: novel, parts, pictures, fanfic x 3 chapter starts x
      3 option sets): 21 identical; in the other 15 the only change is on a page where Phase 4 had moved a space
      to its top (8 pt after a picture, 14 pt after the fanfic summary + the heading's own 12 pt): that page now
      starts at the normal top margin. Same lines on every page, same page count, same page numbers.
- [x] Review fixes: merging a chapter now says when its contents entry had a typed page number / text / was hidden
      (C14); the headless build stops with the plain "Nothing to print" message (no traceback).
- [x] tests/test_blanks_180.py (78 checks; each bug check fails on the code before its fix - the Phase 4 code, or
      for causes 4 and 5 the Phase 5 code with only that fix undone).

## 1.8.0 - page size labels, contents page numbers kept when merging (Phase 6, 2026-10-28; unreleased)
- [x] Labels: "Book page size" (Layout step, the finished page of the book; group "Book page & margins (inches)",
      custom size hint "used when Book page size = Custom") and "Printer paper size" (Output step, the sheet that
      goes through the printer; "Use a custom printer paper size", "Custom printer paper size", the size line
      "Printer paper size: ..."). The cover's paper list is "Paper weight (sets spine width)" so it isn't read
      as a size (its hint now wraps to its column). Same names in Help, README, error messages ("Custom book
      page width/height", "Custom printer paper width/height", "(Layout step, Book page size.)"), the printing
      notes ("book page size W x H in", "sheet(s) of ... printer paper") and the placement window. Setting keys
      unchanged (page_size, custom_w/h, sheet_size, sheet_unit, sheet_w/h, paper): settings, presets and projects
      from every version load as before (old paper names still mapped). Tests updated to the new wording only.
- [x] Root cause (merge): contents edits (Book.toc) are keyed by chapter uid. "Merge into previous" deleted the
      absorbed chapter, so its entry - with a page number typed in Edit contents - pointed at a chapter that no
      longer existed and contents_rows dropped it (Phase 5 only said so in the status line). The surviving
      chapter keeps its uid, so its own entry was never the problem.
- [x] Fix (BookForge.App.merge_ch, bf_pdf.merged_contents_page / merge_contents_edits): the absorbed chapter's
      typed number moves to the surviving chapter's entry when that one has none; when both have different
      numbers the user chooses (Yes = keep the surviving chapter's, No = keep the absorbed chapter's, Cancel =
      no merge, nothing changed). The absorbed entry's other changes (typed text, formatting, hidden) go with it,
      and the status line says so. The rule is applied to an open Edit contents window too (its pending changes
      are used, as Preview does, and its Cancel goes back to the merged pre-window contents); Specific Text Edit
      loads its contents page again when a typed number changed elsewhere, so saving it can't restore old numbers.
      A typed number stays only a printed label: the chapter starts where the layout puts it (log note as before).
- [x] Unchanged: chapter ids; renaming / moving chapters (the number stays with the surviving chapter's id);
      projects without typed numbers or without contents edits merge exactly as before (contents stay automatic).
      Note (existing design, not changed here): once the contents were edited, their order is the order kept in
      Edit contents, so moving a chapter on the Chapters step didn't move its contents entry (changed in Phase 8:
      the two chapters' entries now swap too).
- [x] tests/test_contents_merge_180.py (new): merge rules; merge into an entry without a number; conflicting
      numbers (Cancel, keep absorbed, keep surviving); save/reopen; rename + move after merging; open Edit
      contents window; Specific Text Edit's contents page; an older project without contents edits or chapter
      ids; labels bound to the same setting keys, presets and older settings files; messages and printing notes.
      22 checks fail on the Phase 5 code. tests/test_blanks_180.py: the Phase 5 merge check now expects the
      number to be kept.

## 1.8.0 - drop chapter start down, custom signature sizes (Phase 7, 2026-10-28; unreleased)
Both reported defects were first reproduced on the original code (GitHub main 70839fc): "Drop chapter start
down" 1 in + long first paragraphs left an empty page before every chapter (Digest: pages 1, 8, 15), and "4, 4,
6, 6" padded a 1-page folio book with 79 blank pages (2,674 of 7,956 plans wrong). Both were already fixed in
Phases 3 and 5 and stay fixed (checked again below). Tracing them further found these, fixed now:
- [x] Drop bigger than the page has room for (bf_pdf.build_pdf): the drop was a fixed space before the title
      block, whatever the page size. On small pages (Pocket, A6, Mass Market with 3-4 in), or before a tall opening
      picture (any page size), the title block or the picture couldn't follow it: the page was left with only the
      drop space on it (an empty page), or the number line stayed alone at the bottom with the title on the next
      page, or the opening heading / drop cap lines went to the next page. A drop typed above the room of the page
      (e.g. 6 in on Mass Market; the field takes up to 12) stopped the book with a ReportLab LayoutError. Now the
      drop is never so low that the title block and what the chapter starts with (two lines of text, as many as a
      drop cap spans, an opening heading and two lines, or the opening picture) can't follow it on the page - the
      same rule as title and part pages. Where it fits, the drop is exactly as set (unchanged books).
- [x] Continuous: a titled chapter whose first paragraph didn't fit in the rest of the page moved (title and
      paragraph together, ReportLab keepWithNext) to the next page, but its contents link stayed behind: the
      contents gave the page before the one the chapter starts on (also the opening-page number hiding and the
      running head). The link now moves with the title (Anchor keepWithNext in Continuous). The text layout is
      unchanged; only those contents numbers change (to the right page).
      Not changed (existing Continuous behaviour): such a chapter still starts on the next page instead of under
      the end of the previous chapter.
- [x] Custom signature sizes were read leniently (bf_impose.custom_sizes): "4.5, 6" became three signatures of 4,
      5 and 6 sheets, "0" / "-4" / a word were skipped, and a list without a number (or "Custom" with an empty box)
      quietly used the standard size. Now only whole numbers 1-200 separated by commas (spaces / semicolons) are
      accepted; anything else stops the preview / build with a plain message (window: Output step, Binding layout;
      headless: the log), checked before anything is written (bf_build.check_settings). Small layouts don't use
      the sizes, so they aren't checked there.
- [x] Printing notes: the pages the layout leaves blank on purpose are listed apart from padding, flyleafs and
      the blank pages you added - "Blank pages in the book on purpose: page 3 (the back of the front cover picture);
      pages 6, 10 (left-hand pages left blank so the next chapter starts on a right-hand page)". bf_pdf records why
      each planned page is blank (book._planned_blanks; build_preview result "planned_blanks").
- [x] Checked, not changed: no padding before imposition (the print PDF has only the book's pages); flyleafs and
      padding counted once; nothing carried over between builds/previews (plans and notes come from the current
      files); Standard / Perfect bound / Booklet plans unchanged; padding only completes the last signature.
- [x] Headless build: an unusable setting is logged as a plain message (no traceback).

## 1.8.0 - complete front & back editing (Phase 8, 2026-10-28; unreleased)
Inspected first: the page model (bf_matter, Book.matter, Book.toc), Specific Text Edit (select / commit /
_commit_section / _commit_contents), project save/load, and every output. Every page was edited with its own
words (and a picture where pictures go) and every format made from it, then saved and reopened. The preview, the
print PDF and the imposed PDF had every edit; the gaps were in the other outputs and around them:
- [x] Text before chapter 1 (read from the source or edited) was only in the PDFs: the EPUB, Word document, web
      page and text file left it out. Now in all of them, after the contents and the extra front page, as in the
      PDF (bf_export.front_text_blocks: an edited page, or the paragraphs read from the source; edited to nothing
      = none anywhere; a picture alone counts). It also has its own button on Front & back ("Text before chapter
      1", with the other pages) and a hint saying where its text comes from.
- [x] Word: an edited contents (Edit contents or the contents page in Specific Text Edit) was ignored - the Word
      file always had Word's own contents field, listing every chapter under its original title. Now it lists the
      edited entries in their order (renamed, formatted, indented, space above, added; hidden ones left out), a
      typed page number as typed, otherwise a PAGEREF field to a bookmark on the chapter's heading (Word fills in
      the real page when it updates its fields; LibreOffice does it on opening). An unedited contents is still
      Word's own contents field (same XML as before).
- [x] Same order in every format: the Word document had the contents before the work info / summary / notes
      pages (the PDF has them before the contents); the EPUB always put the extra front page before the contents;
      the web page and text file put an extra front page set "Before contents" ahead of the work info. All now
      follow the PDF: title page, bookplate, dedication, work info, summary, notes, extra front page (before or
      after the contents, as set), contents, text before chapter 1, chapters, THE END, end pages, Notes pages.
- [x] Making the book could overwrite its own source: with the source file kept in the book's output folder
      under the name BookForge gives a file (e.g. "My Book.txt" with plain text on, or BookForge's own "My Book -
      Print.pdf" used again as a source) the source was replaced. Now such a file gets " (BookForge)" added
      (bf_core.not_the_source; run_build, the imposition, the READ ME, the headless log) and the printing notes say
      so. Save project... refuses to save onto the source file.
- [x] Contents vs chapters: moving a chapter (Chapters step, or Move up / down on a chapter in Specific Text Edit)
      left an edited contents in the old order, so it no longer matched the book. The two chapters' entries now
      swap too (App.swap_chapters, bf_pdf.swap_contents_entries), including changes still open in the Edit
      contents window. Editing the contents while a chapter was left out (unticked) dropped that chapter's entry,
      so putting it back lost its typed page number and words; those entries are now kept in place
      (bf_pdf.keep_left_out; Edit contents' Undo all still drops everything).
- [x] What a format can't hold is said in the printing notes and the log instead of being left out quietly
      (bf_build.format_limits): the edited bookplate (a print page: print PDF and Word only), edited Notes pages
      (lined pages for printing only), typed contents page numbers and contents entry formatting (the EPUB, web
      page and text file reflow and have no page numbers: print PDF and Word), pictures on edited pages (the text
      file has none), edited back-cover text when the cover isn't being made. The help text, the README and the
      Specific Text Edit hints say the same.
- [x] Checked, not changed: typing on a page is kept when another page, a chapter or another step is opened, and
      Preview, Make the book, Save project, Re-read source and closing all take the latest typing first; edits go
      to the page being edited (never a chapter); save / reopen brings back every page, heading, picture and the
      contents edits and makes the same files; Re-read source names the edited pages read from the source and
      keeps the user's own pages; the source file is never written to.
- [x] Unedited books: the print PDF is identical to Phase 7 (36 test books, every character and picture
      position); the EPUB, Word, web page and text files differ only by the order fixes above and the text before
      chapter 1.
- [x] tests/test_front_back_180.py (every page x every format, pictures, order, notes, Word contents incl. a
      LibreOffice check where installed, EPUB placement, save/reopen, source never overwritten, contents
      following chapters, window checks). Its bug checks fail on the Phase 7 code.

## 1.8.0 - title and heading settings in every format (Phase 9, 2026-10-28; unreleased)
Traced first: the Layout tab's "Titles: alignment & position" settings (tp_align, tp_pos, tp_title_size, ch_align,
chapter_sink, part_align, part_pos, part_size; checked by bf_pdf.title_layout) were used only by bf_pdf (print PDF,
preview, imposed sheets). The EPUB and web page centred every title in a fixed stylesheet, Word centred its
Heading styles and title paragraphs and put the title page title a fixed 140 pt down (its book title size ignored
"Book title size"), and the cover drew its own centred title at a fixed height. Chapter title size and the titles
font were already used by Word (Heading styles) and the PDFs; the EPUB and web page have no font settings
(unchanged).
- [x] One source of truth: bf_export.title_look reads the same checked values as the PDF (title_layout); no new
      Layout controls. What each setting moves is kept apart as in the PDF: title page (title, subtitle, author,
      credit; the bookplate stays centred), chapter titles (number line, title, chapter subtitles) and the
      headings BookForge adds (Contents, Work info, Summary, Notes, extra front page, end pages) = ch_align,
      parts = part_*. Headings typed in the text, the dedication, THE END and section breaks keep their own look.
- [x] EPUB and web page (bf_export.title_css, added after the fixed stylesheet so it wins; the chapter number line
      and title in a div "chead", parts in a div "part" in the web page too): text-align for each title; positions
      as space above (a screen has no fixed page): title page margin = 1.25 x its % (20 % -> 25 %, the old margin),
      part margin = its % (30 % = the old EPUB margin; the web page's part titles now get it too), chapter drop =
      padding in ems (drop / text size, none in Continuous, as in the PDF); Book title / part title sizes in ems of
      the text size (0 = automatic keeps the old sizes). The number line has no first-line indent any more, so it
      lines up with its title.
- [x] Word: Heading styles carry the alignment (Heading 1 = parts when the book has parts, else chapters) and the
      part size (part_size, or 1.2 x the chapter title size as in the PDF); title page paragraphs follow tp_align
      and Book title size; positions are the PDF's on Word's real pages: space above the title page title =
      tp_pos % of the text area, part titles part_pos %, chapter titles + the drop (never so much that the block
      leaves its page, estimated); generated headings and chapter subtitles follow ch_align. With the standard
      settings the title page title and part titles move to the PDF's places (Robert chose "Match the PDF").
- [x] Cover: the cover is laid out apart from the title page, so it gets its own settings (Robert's choice):
      cover_align ("Same as title page" (standard) / Centered / Left / Right: title, subtitle and author lines) and
      cover_pos (% down the front panel where the title line sits, 5-85, standard 32 = where it always was), Output
      tab, Cover group. Standard values draw the cover exactly as before; the title never leaves the cover and the
      subtitle never runs into the author line. Both are in TITLE_LAYOUT_KEYS (older projects get the standard
      values) and bf_placement.SHEET_ONLY_KEYS.
- [x] Not changed: the PDFs (print, preview, imposed: identical to Phase 8 for every setting); the plain text file
      (no layout); EPUB/web page fonts.
- [x] tests/test_title_exports_180.py: PDF positions; preview = print = imposed (rendered); EPUB and web page read
      with a small CSS cascade (specificity, order, inline styles, inheritance) on the real files; Word styles and
      paragraphs (and, where LibreOffice is installed, the Word file laid out and measured); cover on its own;
      what keeps its own look; plain text unchanged; project save/reopen; older projects; window checks. 14 of its
      checks fail on the Phase 8 code (which then stops at the missing cover settings). Also checked in Chromium
      (not part of the tests): every title's alignment, size and position in the EPUB pages and the web page.

## 1.8.1 - "Fit contents on one page" (2026-10-28; unreleased)
Traced first: the contents page is one ReportLab table (bf_pdf.BookTOC, a TableOfContents) made from
contents_entries + the Edit contents changes (apply_contents_edits), with the paragraph and table styles of
contents_styles(variant). "Contents spacing" only ever picks one of those fixed looks: Normal, Compact, or
Automatic, which tightens the spacing (type never below 8 pt) only when the last contents page would hold just a
few entries. Nothing aimed at one page: a list taller than the text area is split over as many pages as it needs
(the table splits; every page gets its page number). So there was no way to ask for one page.
- [x] Setting toc_one_page ("Fit contents on one page", Front & back -> Contents page), off as standard; in
      DEFAULTS, saved in projects; projects and presets without it open with it off (open_project_dialog's
      setdefault list too). Off: the contents are made exactly as in 1.8.0 (same code path).
- [x] bf_pdf.fit_contents: measures the contents list with the paragraphs, styles and table the contents page
      draws (contents_height = BookTOC.wrap's table) against the room under the heading, and uses the first look
      that fits, in this order: 0. the look the contents have without the option (Normal, Compact or what
      Automatic chose; unchanged if it fits); 1. no space between entries, less above
      part entries; 2. tighter line spacing (down to 1.15 x the type); 3. smaller contents type in 0.25 pt steps,
      never below max(8 pt, 0.7 x the body text size); 4. less space under the contents heading (20 -> 6 pt).
      Only the contents list's own styles change: the heading, the body text, chapter titles, margins and page
      size are not touched. Long titles wrap; page numbers stay in their own right-hand column (so the height
      doesn't depend on them and the multi-pass build can't loop: the look is chosen once, before the passes).
- [x] Can't fit at a readable size: the contents are made exactly as with the option off (all entries, normal
      look, Automatic/Compact as set) and a WARNING (log, printing notes, preview window info line) says how
      many pages it needs and what to do (shorten titles, hide entries, bigger page / smaller margins, or untick).
      Decided by the measured layout, not a chapter count. Safety net: if the contents still ran onto a second
      page (BookTOC counts its splits), the result is reported as not fitted.
- [x] Front & back shows a line under the option, worked out before any preview (contents_fit_estimate: the
      same measurement without typesetting the book): "The contents take about N pages. Tick to fit them on one
      page.", "The contents fit on one page (...)", or the warning. The "Automatic" spacing decision moved into
      automatic_contents_variant (used by build_pdf and the estimate; same logic as before).
- [x] Unchanged: Edit contents (rename, reorder, hide, add, typed page numbers = only the printed label, Indent +,
      space above, formatted entries), chapter order, pagination of the chapters (the chapters start earlier
      when the contents take fewer pages; the contents numbers are their real pages), EPUB / Word / web page /
      text files (they have no fixed pages; Word keeps its own contents).
- [x] tests/test_contents_one_page_181.py: reads the contents pages of the real PDFs (every word and its
      position): off / older settings identical; short list unchanged with the option on; 30, 46 and long
      wrapping titles on one page with nothing missing, cut, overlapping or below the text area, page numbers on
      the right, type above the limit; 120 chapters and 14 very long titles: normal contents + warnings; edited
      contents with parts; preview = print = imposed sheets with right-hand starts and blank pages; projects;
      on/off; the estimate = the PDF; window checks. On the 1.8.0 code it stops at the missing option.

## 1.8.1 - page numbers: numerals, number pictures, positions (2026-10-29; unreleased)
Traced first: page numbers are drawn only by bf_pdf's page furniture (onPageEnd of both page templates) from
BookDoc.page_label (pn_mode decides which pages count and where 1 is; "Roman front matter" uses roman().lower()
before chapter 1); the same labels go to the contents (TOCEntry) and to Edit contents (toc_labels). Positions
were "Bottom center" (default), "Bottom outside", "Top outside", "None"; pn_style (Rule above / Plain / Dashes) is
the decoration. The preview and imposed sheets are made from that PDF (imposition only places pages; its tiny
signature numbers are marks, not page numbers), so no second number can come from imposition. Word: a centred
PAGE field in the footer (header for Top...), nothing else. EPUB / web page / text: no page numbers.
- [x] bf_folio.py (new): numerals Arabic (standard) / lowercase / uppercase Roman (roman_numeral: subtractive
      forms, 1-3999, None outside - printed in Arabic with a note) / custom digit images / custom whole-number
      images; file-name patterns ({number}, {number:N} zero-padded; detect_pattern works it out from the files);
      folder checks (digit_files / check_digits / check_pack: missing, damaged, non-picture, > 4000 px); Folio =
      one book's numbers: text labels, pictures read when a page needs them (cached, each file once), the
      warnings (missing pictures by page number, Roman range, shrunk to fit, wider than the margin); anchor() =
      where a number goes (the four old positions computed exactly as before); drawing incl. contents numbers;
      Word format/alignment/notes.
- [x] Settings (bf_core DEFAULTS + PAGE_NUMBER_KEYS for older projects): pn_numerals (Arabic), pn_digits_dir,
      pn_glyphs_dir, pn_glyph_pattern ({number}.png), pn_img_height (0 = automatic: text size for digits, 2x for
      whole-number glyphs), pn_img_gap (1 pt). pn_position gains Top left / center / right, Bottom left / right,
      Middle outside edge (by the page's place in the book: odd = right-hand).
- [x] bf_pdf: BookDoc.page_value / page_label (numerals for the main sequence; the Roman front matter keeps i, ii,
      iii); furniture draws text through anchor() (old positions identical) or the pictures, kept inside the
      margin band (made smaller and said when too big); contents numbers drawn as the same pictures (typed numbers
      stay text: apply_contents_edits marks typed_page); notes -> log, printing notes, preview info line.
- [x] Projects: the ten digit pictures are kept in the book (Book.pn_digits, like the cover pictures) and used when
      the folder is gone; whole-number folders are only referenced; save_project also stores each folder relative
      to the project file and load_project uses that when a project was moved with its folders (moved_folders);
      otherwise the warning says the folder isn't there and the numbers print as 1, 2, 3.
- [x] Layout step: Numerals box; the picture settings (folder + Choose..., file names, picture height, space
      between digits, a status line with the numbers covered / problems, and a sample) appear only for the
      picture numerals; folders are refused (with the reason) unless usable; hints for Roman front matter, the
      Roman range, running headers at the top centre, the middle of the edge.
- [x] Word: Roman numerals as Word's own page-number format (w:pgNumType), left / centre / right; pictures and
      the middle / outside edge are said in the printing notes (bf_folio.word_note).
- [x] Checked: settings from before 1.8.1 and the standard print exactly as 1.8.0 (36 combinations of the old
      positions, styles and numbering modes: every character and line identical). tests/test_page_numbers_181.py
      (Cistercian numerals drawn as the codepo8 generator draws them - checked against the generator itself and
      against Robert's pictures of 1-20, not kept in the repository).
- [x] Found while checking (not new in 1.8.1, also in 1.8.0): with the window at 1400 x 1000, switching light/dark
      on the Output tab froze BookForge - two wrapping hint labels side by side kept changing each other's column
      width (BookForge.wrap_to_width rewrapped them back and forth forever). wrap_to_width no longer goes back up
      to the width a label just left (it keeps the narrower wrapping). Checked at 19 window sizes.
