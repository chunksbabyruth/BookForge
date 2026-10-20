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
