# -*- coding: utf-8 -*-
import checking
import re
import sys as _sys

# Guard option injected by Paratext; use colon as default when running outside Paratext.
try:
    ChapterVerseSep
except NameError:
    ChapterVerseSep = u':'

if isinstance(ChapterVerseSep, str):
    ChapterVerseSep = ChapterVerseSep.decode('utf-8')

checking.setupCheck()

# Strip CR/LF escape sequences from the text column in tab-delimited output.
class _StripCRLF(object):
    def __init__(self, wrapped):
        self._w = wrapped
    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                text = re.sub(r'^\[\d+\]', '', text)
                text = text.replace('\\u000d', '').replace('\\u000a', ' ')
                self._w.write(ref + '\t\t' + text + '\t' + msg)
                return
            except ValueError:
                pass
        self._w.write(s)
    def flush(self):
        self._w.flush()
    def close(self):
        self._w.close()

_sys.stdout = _StripCRLF(_sys.stdout)

# ---------------------------------------------------------------------------
# Blank regions already properly marked as scripture references so only bare
# (unmarked) references remain visible to the detector.
# Replace with equal-length spaces to preserve character offsets for outputError.
# ---------------------------------------------------------------------------

# Blank entire \x...\x* cross-reference spans: inside them \xt needs no closing marker.
# Then blank \xt...\xt* and \+xt...\+xt* outside \x spans (e.g. inline refs in intro text).
MARKED_SPAN_RE = re.compile(
    ur'\\x\s.*?\\x\*'
    ur'|\\[+]?xt\b.*?\\[+]?xt\*'
    ur'|\\[+]?xt\b[^\\]*'
    ur'|\\rq\b.*?\\rq\*'
    ur'|\\ior\b.*?\\ior\*'
    ur'|\\fig\b.*?\\fig\*',
    re.UNICODE | re.DOTALL)

# Line-level reference markers (\r, \mr, \sr) -- blank to end of line.
LINE_REF_RE = re.compile(
    ur'\\(?:r|mr|sr)\b[^\r\n]*',
    re.UNICODE)

# Inline origin markers (\fr inside footnotes, \xo inside cross-refs) -- blank
# to the next USFM marker.  \xo inside \x...\x* is already covered by
# MARKED_SPAN_RE, but \fr inside \f...\f* is not (we scan \f spans for bare refs).
ORIG_MARKER_RE = re.compile(
    ur'\\(?:fr|xo)\b[^\\]*',
    re.UNICODE)

# ---------------------------------------------------------------------------
# Pattern for a bare (unmarked) scripture reference.
#
# _L  : any Unicode letter or modifier letter -- [^\W\d_] with re.UNICODE covers
#        Lu Ll Lt Lm Lo (all letter categories), which includes every script.
# _COMB: common Unicode combining marks (diacritics, vowel marks across scripts).
#        These are not in \w, so they need a separate character class.
#        Ranges covered: Combining Diacritical Marks (U+0300-036F),
#        Arabic combining (U+0610-065F), Supplement (U+1DC0-1DFF),
#        Combining Half Marks (U+FE20-FE2F).
# _BC : one logical book-abbreviation character: a letter plus any trailing
#        combining marks (handles NFD-form text such as e + combining-acute).
# ---------------------------------------------------------------------------
_L    = u'[^\\W\\d_]'
_COMB = u'[̀-ͯؐ-ٟ᷀-᷿︠-︯]'
_BC   = u'(?:' + _L + _COMB + u'*)'
_CVS  = re.escape(ChapterVerseSep)

_pat = (
    u'(?<!\\w)'
    # Numbered-book form: "1 S", "2 Cr", "3 Jn", or fully spelled "1 Corintios".
    #   No upper bound so any fully spelled numbered book name matches.
    #   = non-breaking space; accept either space or NBSP after the digit.
    u'(?:[123][  ]' + _BC + u'{1,}'
    # Standard form: abbreviation or fully spelled book name, e.g. "Is",
    # "Mat", "Sal", "Génesis". Minimum of 2 prevents bare single-letter
    # false positives. No upper bound -- a long ordinary word immediately
    # followed by an "N:N" pattern can occasionally match too; accepted
    # trade-off since this is a manually-reviewed check.
    u'|' + _BC + u'{2,})'
    u'[ \\t]+'                                          # space(s) before chapter number
    u'\\d{1,3}' + _CVS + u'\\d{1,3}[a-z]?'            # chapter:verse with optional letter
    # Optional range end: – = en-dash.
    # Verse range: -65, -43a   Cross-chapter: -9:1 or –9:1
    u'(?:[-–]\\d{1,3}(?:' + _CVS + u'\\d{1,3})?[a-z]?)?'
    # Optional verse-sequence continuations: ", 63-71" or ",24"
    u'(?:,[ ]?\\d{1,3}[a-z]?(?:-\\d{1,3}[a-z]?)?)*'
)
BARE_REF_RE = re.compile(_pat, re.UNICODE)


def checkChapter(reference, text, lastChapter):
    if not isinstance(text, unicode):
        text = text.decode('utf-8')
    blanked = MARKED_SPAN_RE.sub(lambda m: u' ' * len(m.group(0)), text)
    blanked = LINE_REF_RE.sub(lambda m: u' ' * len(m.group(0)), blanked)
    blanked = ORIG_MARKER_RE.sub(lambda m: u' ' * len(m.group(0)), blanked)
    for m in BARE_REF_RE.finditer(blanked):
        checking.outputError(m.start(), m.end(),
                             u'')


checking.checkAllChapters(checkChapter)
