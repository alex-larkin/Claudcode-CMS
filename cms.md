# Creating a Paratext Custom Check (.cms + .py)

Every check is two files with the same base name, placed in the Paratext `cms/` folder:

| File | Purpose |
|------|---------|
| `mycheck.cms` | Declares the check to Paratext (menu, options, script name) |
| `mycheck.py` | Python 2 script that does the actual work |

---

## The .cms file

```
\check Display Name
\submenu SubMenuName
\script mycheck.py
\description One-sentence description shown in the UI.
\books
\noText
\toList
\utf8

\optionName OptionVarName
\optionLocalizedName Label shown in UI
\optionDescription Tooltip text.
\optionDefault defaultvalue
```

### Key directives

| Directive | Meaning |
|-----------|---------|
| `\check` | Name shown in the Checks menu |
| `\submenu` | Submenu group |
| `\script` | Python script filename |
| `\books` | Let user choose which books to check |
| `\noText` | Don't show a text input box |
| `\toList` | Output goes to a list (tab-delimited) |
| `\utf8` | Script expects UTF-8 output |
| `\optionName` | Variable name injected into the script |
| `\optionDefault` | Value used if the user has not changed it |

For Yes/No options, use `Yes` and `No` as the default. Paratext injects the
current value as a plain string (e.g. `"Yes"` or `"No"`).

---

## The .py file

### Minimal template

```python
# -*- coding: utf-8 -*-
import checking
import re

# Guard against NameError when running outside Paratext.
# Repeat this block for every option declared in the .cms file.
try:
    MyOption
except NameError:
    MyOption = "default"

# Required — opens the project and redirects stdout to the output file.
checking.setupCheck()

def checkChapter(reference, text, lastChapter):
    # text is a unicode string containing one chapter of USFM.
    pass

checking.checkAllChapters(checkChapter)
```

### checking module API

| Call | Description |
|------|-------------|
| `checking.setupCheck()` | Must be first. Opens project, sets up output. |
| `checking.checkAllChapters(fn)` | Calls `fn(reference, text, lastChapter)` for every selected chapter. |
| `checking.outputError(begin, end, msg)` | Reports one error. `begin`/`end` are character offsets into `text`. |

`checking.outputError` writes a tab-delimited line to stdout:
```
REF\t\t[count]TEXT\tMSG\n
```
where `count` is how many times that snippet appears near the same verse.

### Variables Paratext injects

| Variable | Source |
|----------|--------|
| `Project` | Current project name |
| `Books` | List of selected book flags |
| `Language` | Project language name |
| `OutputFile` | Path of the output file (empty = stdout) |
| `Parameter1` … | Text-box inputs (if `\noText` is not set) |
| One variable per `\optionName` | Current option values as strings |

Always guard each injected variable with `try/except NameError` so the script
does not crash if run outside Paratext.

---

## Python 2 requirements

Paratext 8/9 runs **Python 2**. Common differences from Python 3:

```python
print "message"              # not print("message")
except Exception, e:         # not except Exception as e:
ur'raw unicode string'       # unicode raw strings for regex patterns
isinstance(text, unicode)    # check for unicode type
text.decode('utf-8')         # decode bytes to unicode
```

Add `# -*- coding: utf-8 -*-` as the **first line** whenever the source file
contains any non-ASCII characters (accents, em dashes, curly quotes, etc.).

---

## Working with USFM text

The `text` parameter passed to `checkChapter` is a full chapter as a unicode
string. Typical markers:

| Marker | Meaning |
|--------|---------|
| `\v N` | Verse number |
| `\q`, `\q1`, `\q2` | Poetry lines |
| `\f … \f*` | Inline footnote |
| `\x … \x*` | Cross-reference |
| `\qs … \qs*` | Selah / special poetry |

### Regex tips

- Use `ur'...'` raw unicode strings for all patterns.
- Use `re.UNICODE` so `\w` matches accented characters.
- Use `re.MULTILINE` so `^`/`$` match at each line boundary.
- `[^\r\n]*` stays on one line; use `[ \t\r\n]+` to cross lines.
- USFM markers may be preceded by whitespace including newlines — match the
  post-marker space with `[ \t\r\n]+`, not just `\s`.
- On Windows (CRLF files), `$` in MULTILINE matches *before* `\n`, not before
  `\r`. Use `\r?$` or `[ \t\r]*(?=\n|$)` to handle trailing carriage returns.
- To ignore footnote/cross-ref content without shifting character positions,
  replace matches with equal-length spaces:
  ```python
  INLINE_RE = re.compile(
      ur'\\f\s[^\r\n]*?\\f\*|\\x\s[^\r\n]*?\\x\*', re.UNICODE)
  def blank_inline(text):
      return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)
  ```

---

## Output format

The default `outputError` format is `REF\t\t[n]TEXT\tMSG`. If you want a
different column order (e.g. message first for sorting), wrap `sys.stdout`
**after** `checking.setupCheck()`:

```python
import sys as _sys

class _ReorderOutput(object):
    def __init__(self, wrapped):
        self._w = wrapped
    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                # Change this line to set your preferred column order:
                self._w.write(ref + '\t\t\t' + msg.rstrip('\n') + '\t' + text + '\n')
                return
            except ValueError:
                pass
        self._w.write(s)
    def flush(self):
        self._w.flush()
    def close(self):
        self._w.close()

_sys.stdout = _ReorderOutput(_sys.stdout)
```

### Hiding `\r\n` from output

USFM text snippets passed to `outputError` may contain `\r` or `\n`, which
breaks the tab-delimited output format and causes Paratext to display raw
control characters. Strip them from the `text` argument before reporting:

```python
def clean(s):
    return s.replace(u'\r', u'').replace(u'\n', u' ')

checking.outputError(begin, end, clean(snippet))
```

If you are using `_ReorderOutput`, strip inside the `write` method instead:

```python
def write(self, s):
    if '\t\t' in s and not s.startswith('#'):
        try:
            ref, rest = s.split('\t\t', 1)
            text, msg = rest.rsplit('\t', 1)
            text = text.replace('\r', '').replace('\n', ' ')
            msg  = msg.rstrip('\n').replace('\r', '')
            self._w.write(ref + '\t\t' + text + '\t' + msg + '\n')
            return
        except ValueError:
            pass
    self._w.write(s)
```

---

## File encoding

Paratext expects **Windows CRLF** line endings. After creating or editing
either file, run:
```
unix2dos mycheck.cms
unix2dos mycheck.py
```

### UTF-8 BOM required for non-ASCII characters

If a `.cms` file contains any non-ASCII Unicode characters — in `\description`,
`\optionDefault`, `\optionLocalizedName`, or `\optionDescription` — the file
**must begin with a UTF-8 BOM** (`EF BB BF`). Without it, the CMS tool reads
the file as Latin-1 and displays multi-byte sequences as garbage
(e.g. `—` U+2014 becomes `â€"`).

The `\utf8` directive alone is **not sufficient** for correct display — the BOM
is what triggers UTF-8 mode in the parser.

To write a UTF-8-with-BOM file in PowerShell:
```powershell
$utf8BOM = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($filePath, $content, $utf8BOM)
```

**Diagnosing encoding problems:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Multi-char sequences like `Âª` or `â€"` in option values | File has UTF-8 bytes but no BOM; tool reads as Latin-1 | Add UTF-8 BOM |
| `ï¿½` (or `???`) in `\description` regex | File was edited/saved without BOM; editor replaced unmapped chars with U+FFFD (`EF BF BD`), which Latin-1 renders as `ï¿½` | Add BOM **and** re-enter the correct Unicode characters — the U+FFFD bytes are corrupt and will not display correctly even with BOM |

Files that only use ASCII characters (no curly quotes, em dashes, accented
letters, etc.) work without a BOM and are unaffected by this rule.

---

## Prompts to consider when designing a new check

1. **What is the bad pattern?** Write two or three concrete examples of text
   that should be flagged, and two or three that should not.

2. **What should be ignored?** Footnotes (`\f…\f*`), cross-references
   (`\x…\x*`), and `\qs…\qs*` spans often contain content that would create
   false positives. Decide whether to strip them before matching.

3. **Does the pattern span lines?** USFM markers are often on their own lines.
   Account for `\r\n` between a marker and its content, and between content
   and the next marker.

4. **Are there configurable thresholds or character sets?** Expose these as
   `\optionName` entries so translators can tune the check for their language
   without editing Python.

5. **Should each sub-check be individually toggleable?** Add a `Yes/No` option
   per sub-check (defaulting to `Yes`) so users can disable noisy rules without
   disabling the whole check.

6. **What column order aids workflow?** If users will sort or filter the output
   list, put the most useful sort key in the first column.

7. **Test with both same-line and cross-line variants** of every bad pattern.
   Paratext may store a marker and its content on separate lines even when the
   editor shows them inline.
