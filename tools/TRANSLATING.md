# Translating a CMS check (French in CMS/French_Tools/, Spanish in CMS/Spanish_Tools/)

These checks are Paratext 9 custom checks: a `.cms` (metadata, options) + a Python 2 `.py`
run inside Paratext's IronPython 2.7, + an `.rtf` help file (+ sometimes a `.txt` readme).
The Phils Custom (cms) Checks plugin carries them in English, Spanish and now French.

## The English files are the source of truth
The Spanish copies were made earlier and some lag behind later English fixes (e.g. Find_Titles'
DisplayHeader default). So each French file starts as a **byte copy of the current English
file**; the Spanish copy is only a guide to which strings are user-visible and how they were
phrased. Never port logic from the Spanish file.

## File names
- French: `CMS/French_Tools/<english base name>_fr.<ext>`, e.g. `toc_examiner_fr.cms`,
  `toc_examiner_fr.py`, `toc_examiner_fr.rtf`, `Find_Titles_fr.py`, `q_error_fr.py`,
  `MarkerSpace_fr.py`, `Short_V_1_fr.rtf`. Compare and Copy Figures: `Compare Figures/figures_fr/`.
- Every French check gets its own `_fr.py`, even where the Spanish one shares the English `.py`.
- Spanish (only where asked): `CMS/Spanish_Tools/<english base name>_sp.<ext>`.

## How to make the copy (avoid tool pitfalls)
1. `cp` the English file to the new name (keeps BOM, CRLF, bytes).
2. Change strings with the Edit tool, or with a Python script **written to a file with Write and
   run with python** (in Bash heredocs `\\` collapses to `\`). The Write tool turns `\uXXXX`
   escapes into literal characters, so never retype code with escapes or regexes.
3. Afterwards diff English vs translation: only string literals (and comments, optionally) may
   differ. Every `\u` escape, regex, identifier, option name and function name must be unchanged
   (All Reports calls the sub-scripts' functions and globals by name).

## .cms
- `\check` French name (Spanish: Spanish name), `\submenu Outils_Français`
  (Spanish: `Herramientas_Español`), `\script <name>_fr.py`.
- Translate `\description`, `\optionLocalizedName`, `\optionDescription`.
- Keep `\optionName`, `\optionDefault` and every other directive unchanged (Yes/No defaults
  lock the dropdown; the scripts read the option names).
- UTF-8 **with BOM**, same line endings as the English file.

## .py
- Translate only what the user sees: outputError messages, report text, HTML headings, labels,
  table headers, titles, notes, print/log lines meant for the user. Keep marker names (`\mt`,
  `\h`...), option names and file-format words.
- **outputError messages (and anything else that reaches Paratext's results list) must be
  ASCII-only**: no accents, no « », no U+00A0. Non-ASCII there crashed checks in Paratext (see the
  notes in `find_footnotes_sp.py` and `quotation_examiner_sp.py`). HTML reports keep full accents.
- Literal non-ASCII is allowed in the translated `.py` (as in the Spanish copies) but **only inside
  `u'...'` strings**; keep `# -*- coding: utf-8 -*-`; file is UTF-8 **with BOM**.
- Report file names: give the HTML report a French ASCII name (e.g. `RapportTitres.html`) and
  **list every such file name change in your final message** (All Reports reads them by name).
- The clickable-reference hint: `_ptx_goto.hint_html('fr')` (Spanish: `hint_html(True)`).
- French typography in prose: non-breaking space (U+00A0) before `: ; ! ?` and inside « ».
  Use `livre(s)`, `chapitre`, `verset`, `note de bas de page`, `appel de note`, `titre de section`,
  `intertitre` is not used; `marqueur` for marker; `projet`; `rapport`.
- Syntax check: `C:\Python27\python.exe -m py_compile FILE`, then delete the `.pyc`.

## .rtf and .txt
- `.rtf`: copy the English RTF and translate its text in place, keeping every control word,
  group and picture. Write non-ASCII as cp1252 escapes `\'e9` (é), `\'e8`, `\'ea`, `\'e0`,
  `\'e7`, `\'f4`, `\'ee`, `\'f9`, `\'fb`, `\'ab` («), `\'bb` (»), `\'92` (’), `\'9c` (œ),
  `\'a0` (no-break space); for Spanish `\'f1` (ñ), `\'e1`, `\'ed`, `\'f3`, `\'fa`, `\'bf`, `\'a1`.
  Option names in the help must match the `\optionLocalizedName`s of the translated `.cms`, and
  menu paths the translated `\submenu`. File should stay ASCII.
- `.txt` readme: translate as `<name>_fr.txt`, UTF-8 with BOM.

## Verify (required)
`C:\Python27\python.exe CMS\tools\compare_lang.py ENGLISH.cms TRANSLATED.cms` runs both under
Paratext's IronPython on a scratch copy of PDT15 and must print `SAME PLACES` (also try any
option that switches on a different code path, with `--options opts.json`). It prints a few
message pairs and saves the translated HTML reports in its work folder: open them (read the
text) and check nothing user-visible is left in English. Checks that change text
(`\outputProject`) or need a second project may not run in the harness: say so, and at least
py_compile them and diff them against English.
