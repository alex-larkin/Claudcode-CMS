# Prompt: Build a unified "Paratext Project Checker" desktop app

> Paste everything below this line into a new Claude Code session opened at `C:\ClaudeCode Projects`.
> Start in **plan mode**.

---

## 1. Goal

Build a **standalone Windows desktop application** that runs, in one pass, all of the
**read-only** Paratext quality checks that currently live as separate CMS custom checks in
`CMS/`. The user should be able to:

1. Open a Paratext project folder (for example `...\My Paratext 8 Projects\PDT15`, or the test
   project at `TestProject/PDT15`).
2. Choose which books to check (select all, by testament, or individually), based on the books
   actually present in the project.
3. Choose which checks to run, and adjust each check's options.
4. Run the selected checks together and see the results in:
   - an **in-app results grid** that can be filtered by check, category, and book, and sorted and searched;
   - **one combined, self-contained HTML report** with a table of contents, one section per check,
     and collapsible groups per category, which can be saved and opened in a browser;
   - **CSV export** of the findings.

This app replaces `CMS/all_reports/All_Reports.py`, which tried to do the same job inside Paratext
by `exec()`-ing each check script. That approach proved fragile: stray BOMs, repeated
`checking.checkAllChapters()` calls, monkeypatched `setupCheck`/`os.startfile`, 10 separate reports
embedded through `<iframe srcdoc>`, and a 25-row cap. Read `All_Reports.py` to see what users
expect, but don't copy its mechanism.

**The app never modifies project data.** It never writes, renames, or locks any book file,
`Settings.xml`, stylesheet, or other project file. Its **only** writes go into the project's
`local` subfolder (`<project>\local\`, created if it doesn't exist). Saved settings, reports, and
logs all go there (see §6).

## 2. Technology (confirm with me before starting)

My recommendation, which you should confirm with me in plan mode:
**C# 5 / WPF / .NET Framework 4.8, with no NuGet dependencies**, added as a new project to
`ClaudeCode Projects.sln`. This matches the existing `AutoCorrect/AutoCorrectEditor` app and the
Custom Versification Editor, so use their structure as the template:

- MVVM-lite: `Models/`, `Services/`, `Controls/`, `Resources/Strings.*.xaml`
- Runtime language switching in `App.xaml.cs`, the same way AutoCorrect Editor does it
- Build: `msbuild "ClaudeCode Projects.sln" /p:Configuration=Release /p:Platform="Any CPU"`

**Hard constraint: C# 5 only.** No `nameof`, no `?.`, no `$"..."` string interpolation, no
expression-bodied members, no `async`/`await` beyond what .NET 4.8 with `Task` supports under a C# 5
compiler. Run checks on a background thread (`Task.Factory.StartNew` or `BackgroundWorker`) with a
progress bar and a Cancel button.

If you think a different stack is clearly better (for example Python 3 with a GUI, which would make
porting easier), make the case in plan mode and let me decide. Don't switch on your own.

## 3. The checks to include: the existing Python scripts are the specification

Port each check **faithfully**. The existing `.py` file is the source of truth for behavior: what
gets flagged, what is skipped, how context is built, and edge cases. **Read each `.py` in full
before porting it.** Its long comments often record a real bug found on live data. Read the
matching `.cms` for option names, labels, descriptions, and defaults, and `CMS/cms.md` for what the
Paratext `checking` API calls mean. If the Python does something that looks wrong, **ask me** rather
than "fixing" it silently.

Include these 14 checks (English versions in `CMS/<folder>/`; Spanish versions in `CMS/Spanish_Tools/`):

| # | Check (menu name) | Folder / script | What it does | Options (default) |
|---|---|---|---|---|
| 1 | Report of TOC | `toc_examiner/toc_examiner.py` | `\toc1` vs combined `\mt*`, `\toc2` vs `\h`, both vs BookNames.xml; flags missing markers; "Capitalization only?" and "Spelling?" columns; `//` soft breaks ignored | CompareToc1ToMt (Yes), CompareToc2ToH (Yes), CompareToc1ToBookNames (Yes), CompareToc2ToBookNames (Yes), IgnoreCapitalizationOnly (No), IgnoreMt1 (No), IgnoreMt2 (No), IgnoreMt3 (No) |
| 2 | Report of Titles | `find_titles/Find_Titles.py` | Lists `\mt`/`\mt1-3` title per book, styled from the stylesheet; books with no `\mt` flagged missing | SortByTitle (No), DisplayHeader (Yes), SortByHeader (No) |
| 3 | Report of Section heads | `find_section_heads/find_section_heads.py` | Lists `\s`/`\s1-4` (consecutive heads merged), optional `\r`, punctuation in heads, heads followed by `\m`, optional non-title caps using the same ignore lists and TermRenderings as Mid-sentence Capital. Summary counts are always computed | SortAlphabetically (No), IncludeReferences (No), FlagPunctuation (Yes), PunctuationChars (`.?!`), FlagFollowedByM (Yes), IgnoreFootnotesAndCrossRefs (Yes), FlagNonTitleCaps (No), WordsToIgnore (), PrefixesToIgnore (), SuffixesToIgnore () |
| 4 | Report of Quotation marks | `quotation_examiner/quotation_examiner.py` | Classifies each quote/dash character as opener, closer, continuer, or unusual; nesting-level breakdown; comparison with the project's Quotation settings; dialogue dash at paragraph start = level-1 quote; `<<`/`>>` recognized | QuoteCharacters (`" ' « » ‹ › ‘ ’ ‚ ‛ “ ” „ ‟ < > << >>`), DashCharacters (`— ― –`), MaxExamples (25) |
| 5 | Report of Poetry Errors | `q_errors/q_error.py` | `\q`/`\q1`/`\q2` lines: final punctuation followed by text, two verses on one line, text before verse, optional hanging word; ignores `\f`, `\x`, `\qs` | FinalPunctuation (`.!?`), MinCharsBeforePunct (0), NonFinalPunctuation (`,;:`), CheckFinalPunct (Yes), CheckDoubleVerse (Yes), CheckTextBeforeVerse (Yes), CheckHangingWord (No) |
| 6 | Report of Nested Styles | `report_nested_styles/report_nested_styles.py` | Character styles inside `\f...\f*` missing the USFM3 `+` (e.g. `\xt` vs `\+xt`); opening and closing tokens checked independently; footnote-internal markers never flagged | none |
| 7 | Report of Marker spaces | `marker_space/MarkerSpace.py` | Spacing anomalies around character markers (list read from the stylesheets), `\f`, and `\x`; no-close markers; the space before `\|` in `\w`; `~` counts as a space; `\t*` markers ignored except `\tl`, `\ts-s`, `\ts-e` | ExcludeMarkers (), NoCloseMarkers (`v fk fp fq fqa ft fr xk xo xq`), NoCloseInNoteMarkers (`xt`), ExtraSpacingMarkers (`f x`), NoSpaceBeforeMarkers (`f x`), FootnotePrecedesText (No), CrossReferencesPrecedeText (Yes), MaxExamples (25) |
| 8 | Footnotes (`\f`) | `find_footnotes/find_footnotes.py` | Every footnote: reference, caller, `\fr`, and text rendered with stylesheet formatting; summary table of markers and resolved styles | SortAlphabetically (No), HideMarkers (No) |
| 9 | Report of Figure captions | `figure_caption/Find_caption.py` | Every `\fig`: caption, copyright, file; USFM2 (pipe) vs USFM3 (attributes) **autodetected** per figure; sorting by caption ignores diacritics | DisplayCaption (Yes), DisplayCopyright (Yes), DisplayIllustrationFile (Yes), SortByCaption (No) |
| 10 | Report of Capital at Verse | `capital_at_verse/capital_at_verse.py` | Capital after a verse number when the previous verse ended in non-final punctuation; context is 3 words before and after, excluding notes and figures | FinalPunctuation (`.!?`), WordsToIgnore (), IgnoreCapAfterQuote (No), QuoteOpeningChars (`«“—‘`), IgnoreStyles (), IgnoreParaStyles (`sp, r, ms, mr, sr`), PrefixesToIgnore (), SuffixesToIgnore (), MidWordPunctuation (`-`) |
| 11 | Mid-sentence Capital | `mid_sentence_capital/mid_sentence_capital.py` | Capital mid-sentence; capitalized words and multi-word phrases found in TermRenderings.xml are ignored | same 9 options and defaults as #10 |
| 12 | Short Verse 1 | `Short_V_1/short_v_1.py` | Short verse-1 text between `\p`/`\m` and the next `\p` | MinChars (40), CheckOtherMarkers (No), OtherMarkers (`q q1 q2 q3 q4`) |
| 13 | Colon not followed by quotation | `colon_not_followed_by_quotation/FindColonContext.py` (see also `FindExpression.py`) | Colon not followed by a quotation mark | QuotationMarks (`«“—‘`), CapitalizedOnly (Yes), MatchCase (Yes), DotAll (No) |
| 14 | Reference without markers | `reference_without_markers/reference_without_markers.py` | Scripture references in text that aren't inside `\xt`, `\rq`, `\ior`, `\fig`, `\r`, `\mr`, `\sr` | ChapterVerseSep (`:`) |

Before relying on this table, re-check the defaults against the `.cms` files. The `.cms` files win
if they disagree.

**Out of scope** (these write to the project or are interactive utilities; don't include them):
`quotation_matcher`, `quotation_matcher2`, `project_BT_reference_tool`, `case_convert`,
`convert_codes`, `all_reports`.

Where two checks share logic (#10/#11 and #3's caps option share ignore lists, prefix/suffix
handling, and TermRenderings matching; #7 and #6 both read character-style lists from the
stylesheets; #1, #2, and #8 all resolve formatting from the stylesheets), implement that logic
**once** in a shared service. Behavior must still match each original script.

## 4. Replacing Paratext's `checking` API

Paratext is not running, so the app has to supply everything the CMS scripts got from Paratext or
read from disk:

- **Project discovery:** the user picks a project folder. Validate it by the presence of `Settings.xml`.
- **`Settings.xml`:** book file naming (`<Naming PrePart=... PostPart=... BookNameForm=...>`) to map
  book codes to `.SFM` file names; encoding (`<Encoding>`: support at least UTF-8 and the common legacy
  code pages); language; the quotation settings quotation_examiner compares against (read
  `quotation_examiner.py` to see which fields it uses); and `<BooksPresent>`.
- **Stylesheets:** `usfm.sty` sits **one folder above the project folder** (see
  `toc_examiner.py` around line 300 and `find_footnotes.py` around line 172, which share this loader). Merge
  it with the project's `custom.sty` exactly the way those scripts do. If `usfm.sty` is missing,
  fall back to a copy bundled with the app and say so in the report. **`\Color` values are a decimal
  Windows COLORREF (BGR: red in the low byte), not RGB.**
- **`TermRenderings.xml`**, used by #11 and #3. See `mid_sentence_capital.py` around line 132.
- **`BookNames.xml`**, used by #1. See `toc_examiner.py` around line 227. If it's missing, skip those
  comparisons and note that in the report, as the script does.
- **Chapter iteration:** the equivalent of `checkAllChapters` handing `(reference, chapterText)` to each
  check's `checkChapter`. Build one shared USFM tokenizer (markers, verse numbers, notes, character
  styles with `+` nesting, `\fig` attributes, `~`) that every check uses, instead of 14 private regex
  parsers. Wherever an original script's regex behaves differently from the shared tokenizer, the
  script's behavior wins for that check.
- **References:** every finding carries book, chapter, verse, and a character offset where possible.
- Ignore `*.bak` files and any non-book files in the project folder.
- Open all project files **read-only with share-read/share-write**, so the app works while Paratext
  has the project open. The only exception is writing into `<project>\local\` (§6).

## 5. Architecture

- `Services/ProjectLoader`: parses Settings.xml, stylesheets, TermRenderings, BookNames; enumerates books.
- `Services/UsfmTokenizer`: shared tokenizer.
- `Checks/ICheck`: `Id`, localized display name and description, an option schema (name, type:
  bool / int / string / char-list, default, localized label and tooltip), and
  `Run(ProjectData project, IList<string> books, CheckOptions opts, IProgress, CancellationToken)`
  returning findings plus any per-check summary data (for example quotation_examiner's nesting table
  or section heads' always-computed counts).
- `Models/Finding`: check id, category (the original report's grouping, such as the error types in
  q_error), severity, book/chapter/verse, message, context (with the highlighted span given as offsets,
  not HTML), and optional extra columns for checks that have them (TOC, Titles, Footnotes, Figures).
- `Services/ReportRenderer`: one self-contained HTML file with inline CSS and no external resources.
  CSS class names are **namespaced per check** (for example `.qe-err` vs `.ms-err`), because the
  original scripts reuse names like `.err` and `.missing` with different meanings. Each section keeps
  the look and information of the original script's own HTML report (tables, red highlighting,
  stylesheet-rendered formatting, summary tables), but **don't truncate**. Replace the 25-row cap with
  collapsible groups. Where a check has a `MaxExamples` option, it still controls how many examples
  show per bucket, with a "+N more" note, as in the original.
- UI: project picker, book selector, a check list where each check has its own options panel
  (see §6, "Selecting check options"), Run/Cancel with progress, results grid, and Open HTML report /
  Export CSV / Open reports folder buttons.
- **Show in Paratext:** find out whether a reliable way exists to navigate Paratext to a reference
  from an external app (for example a URI scheme or SantaFe focus-sharing messages). Report back
  before building it; if nothing reliable exists, show the plain reference so the user can copy it.

## 6. Options, profiles, and output locations

### Selecting check options

The user must be able to see and change **every** option of **every** check before running. This is
a core feature, not an afterthought:

- Each check in the check list has its own options panel (shown when the check is selected, or opened
  with an "Options…" button next to it). The panel is generated from that check's option schema, so
  every option declared in its `.cms` is there.
- Use a control that fits each option's type:
  - Yes/No: checkbox
  - Integer (MinChars, MaxExamples, MinCharsBeforePunct): numeric spinner
  - Free text or marker lists (OtherMarkers, NoCloseMarkers, IgnoreParaStyles, ChapterVerseSep): text box
  - Character or word lists (QuoteCharacters, DashCharacters, QuoteOpeningChars, FinalPunctuation,
    WordsToIgnore, PrefixesToIgnore, SuffixesToIgnore): a list editor showing each item, with its
    `U+XXXX` code point for single characters so look-alike quotes (`‘` vs `‛` vs `'`) can be told apart,
    plus add and remove
- Each option shows a localized label and a tooltip or help text, taken from the `.cms`
  `\optionLocalizedName` and `\optionDescription` (Spanish from the `Spanish_Tools` `_sp.cms`).
- "Reset to defaults" for one check and for all checks. Any option that differs from its default is
  visibly marked.
- Validate values before a run (for example, an integer must be at least 0, and a separator must not be
  empty), and show the problem next to the option.
- Options with the same name in different checks (Capital at Verse and Mid-sentence Capital share 9;
  Section heads has its own ignore lists) stay **separate per check** by default. Offer a
  "copy options from…" action so the user can copy them from one check to another.
- At the top of each check's section in the HTML report, list the option values used for that run,
  so a saved report records how it was produced.

### Defaults, profiles, and autodetection

- Default option values match the `.cms` `\optionDefault` values exactly.
- Save and load named settings profiles (the selected checks, the selected books, and all options),
  and remember the last-used profile for each project.
- Where the project data reliably shows the answer (quote characters from Settings.xml's quotation
  settings, USFM2 vs USFM3, the footnote-before or footnote-after convention), **prefer autodetection
  and show the detected value** over asking the user to set an option. Propose each such case to me
  rather than silently changing a check's behavior.

### Where files are saved: the project's `local` folder

Everything the app writes for a project goes under **`<project>\local\ProjectChecker\`**. Create it
(including `local\` itself) on first use if it doesn't exist:

| What | Location |
|---|---|
| Saved settings profiles (named profiles plus the last-used one) | `<project>\local\ProjectChecker\Settings\` |
| Combined HTML reports and CSV exports, with timestamped file names | `<project>\local\ProjectChecker\Reports\` |
| Debug logs | `<project>\local\ProjectChecker\Logs\` |

- The app writes nothing anywhere else in the project folder.
- Paratext Send/Receive does **not** sync the `local` folder, so it's a safe place for per-user
  settings and output. Nothing written there reaches other team members or the project history.
- App-wide preferences that don't belong to any one project (UI language, recently opened projects,
  window size) can't live in a project folder. Propose where to keep them (for example
  `%APPDATA%\ParatextProjectChecker\`) and let me decide.

## 7. Localization: EN, ES, FR, PT, ZH-Hans

- All UI text, check names, option labels and tooltips, category names, messages, and report headings
  live in `Resources/Strings.en.xaml`, `Strings.es.xaml`, `Strings.fr.xaml`, `Strings.pt.xaml`, and
  `Strings.zh-Hans.xaml`, and switch at runtime the way AutoCorrect Editor does.
- The generated report uses the current UI language.
- **Reuse the existing Spanish wording** from `CMS/Spanish_Tools/*_sp.cms` and `*_sp.py` for check
  names, option labels and descriptions, and report headings, so Spanish users see the terms they
  already know. Translate FR, PT, and ZH-Hans fresh, and list those strings for me to have reviewed.
- USFM marker names such as `\toc1` and `\fr` are never translated.

## 8. Lessons already learned in this codebase (don't repeat these mistakes)

- **Unicode correctness:** quote and dash characters must be exact code points. A previous
  All Reports run produced mojibake (`â€œ` for `“`) from a byte-order and encoding bug. Read project
  files with the encoding declared in Settings.xml, handle a BOM if present, and write the HTML as
  UTF-8 with `<meta charset="utf-8">`. Include a test with curly quotes, guillemets, `¿`, `¡`, and
  combining diacritics.
- `~` (Paratext's non-breaking space) counts as a space in marker-spacing logic, in both directions.
- `\fig` USFM2 vs USFM3 is detected per figure, not set by an option.
- Section heads' summary counts (ends with punctuation, followed by `\m`) are computed over the full
  scan whatever the option toggles are.
- `.sty` `\Color` is BGR.
- Sorting "by caption" or "by title" ignores diacritics (see `Find_caption.py`).
- Each check's comments record real edge cases found on live data. Preserve them in the port and
  cite the original script and function in a comment.

## 9. Verification (required, per check)

A check isn't done until its output **matches the original Python check** on real data:

1. Build with the msbuild command above, with zero warnings introduced.
2. For each check, build an offline harness that runs the **original, unmodified** `.py` under
   `C:\Python27\python.exe` (it exists even though PATH lookups fail) with a mocked `checking` module,
   created as a real `types.ModuleType` rather than a plain class, as the All Reports test harness did.
   The mock feeds it the same chapters the app reads. Capture its findings.
3. Run the app's port on the same project (`TestProject/PDT15`, all books) and **diff the findings**
   (reference and message or category). Every difference is either fixed or explained to me with an
   example. Keep these harnesses and diff scripts in a `tests/` folder so they can be re-run.
4. Test with option combinations that aren't defaults, not just the defaults.
   - Changing an option in the UI changes the results as expected.
   - The change is saved to the profile in `<project>\local\ProjectChecker\Settings\`.
   - After the app restarts, the saved options load back correctly.
   - "Reset to defaults" restores the `.cms` values.
   - Take a listing of the project folder (with modified times) before and after a full run. Nothing
     outside `local\` may have changed.
5. Once all checks pass, I'll test on a real project (for example DBTALP) and compare against the
   individual CMS checks run inside Paratext.

Say plainly what has and hasn't been verified. Don't describe a check as working before its diff is clean.

## 10. How to work

- **Plan mode first:** confirm the stack (§2), the project layout, the tokenizer design, and the order checks will be ported in.
- Build incrementally: project loader and tokenizer, then the UI shell with one simple check
  (Short Verse 1 or Titles), then the remaining checks **one at a time**, each verified (§9) before
  starting the next.
- **Ask me** before changing any check's behavior, merging two checks' outputs, dropping an option, or
  adding a new option.
- Never modify anything in `CMS/`. Those scripts are the reference, and they stay deployed in Paratext.
- Update the root `CLAUDE.md` with the new project's build and run instructions when done.
