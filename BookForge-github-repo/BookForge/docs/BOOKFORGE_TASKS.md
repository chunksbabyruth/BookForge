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
- bookbinder-js source for reference: git clone https://github.com/momijizukamori/bookbinder-js (MPL-2.0:
  read for behaviour, do NOT copy code into MIT BookForge).
- Test inputs uploaded by user: End_of_the_Line.epub (AO3), of_the_tales_of_ulmo_s_daughter_Momijuzukamori.pdf
  (bookbinder-js reference output), On_the_Making_of_Man_-_Imposed_for_binding.pdf (BookForge output).

## Phase 1 — Inspection
- [x] T1.1 Repo state: sandbox code == delivered v1.3 zip (all 8 .py identical). User's LOCAL git status is not visible from here -> ask user to run `git status` before applying changes.
- [x] T1.2 Fold lines: ROOT CAUSE found (see findings log F1)
- [x] T1.3 bookbinder-js parity audit: see F2 (live app UI + source in /tmp/bbjs)
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
- Reference (bookbinder-js, portrait 612x792, content rotated): fold line y=396 drawn on PDF pages 1,3,... = the
  INSIDE face of each folio (pages that meet at the fold, e.g. contents 2|3). Outside faces have none.
- BookForge v1.3 (landscape 792x612): fold line x=396 on PDF pages 1,3,... = BookForge's "front" side, which is
  the OUTSIDE face (title page + last page of the signature).
- Code: bf_impose.py marks loop: `if s["fold_marks"] and side["front"]:` draws EVERY internal cell boundary on the
  front side. fold_plan() lays sheets printed-first-side DOWN, so "front" = outside of every fold.
- So root cause is not a left/right coordinate slip: fold lines are tied to the wrong FACE, and for multi-fold
  layouts all folds are drawn full-length on one face although each fold is made with a different face on top.
- bookbinder-js rule (utils/drawing.js drawFoldlines): 1st fold on inside face full length; later folds on the
  other face, only over the half that is showing, distinct dash patterns per fold.
- Planned fix: derive fold-guide segments from the fold simulation (for fold k: crease segment on the face that is
  on top of the packet just before fold k, only across the top layer's cells), convert to each face's print
  coordinates; add setting "Fold lines on: Inside (recommended) / Outside / Both". Rotations (/Rotate) are applied
  after the overlay merge, so lines follow rotate_back / rotate_paper automatically (verify in testing).


F2 bookbinder-js parity (reference = live app controls in index.html/src/html + source; BookForge v1.3):
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
