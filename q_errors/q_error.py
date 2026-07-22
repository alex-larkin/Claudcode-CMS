# -*- coding: utf-8 -*-
import checking
import re

# Safety defaults - Paratext injects these from the CMS options, but guard
# against NameError in case the check is run outside a normal Paratext context.
try:
    FinalPunctuation
except NameError:
    FinalPunctuation = ".!?"
try:
    NonFinalPunctuation
except NameError:
    NonFinalPunctuation = ",;:"
try:
    CheckFinalPunct
except NameError:
    CheckFinalPunct = "Yes"
try:
    CheckDoubleVerse
except NameError:
    CheckDoubleVerse = "Yes"
try:
    CheckTextBeforeVerse
except NameError:
    CheckTextBeforeVerse = "Yes"
try:
    CheckHangingWord
except NameError:
    CheckHangingWord = "No"
try:
    MinCharsBeforePunct
except NameError:
    MinCharsBeforePunct = "0"

# Must be called first - opens the project text and initializes globals
checking.setupCheck()

# Wrap stdout to put the message type first so the list can be sorted by problem.
# outputError writes: REF\t\t[cnt]TEXT\tMSG\n  — we reorder to MSG\tREF\t\tTEXT\n.
import sys as _sys

# Matches a line that opens with a poetry marker followed immediately by a verse
# marker, e.g. "\q1 \v 7" or "\q2 \v 12".  Group 1 captures the verse number.
_Q_VERSE_RE = re.compile(r'\\q\d?[ \t]+\\v[ \t]+(\d+)')

class _ReorderOutput(object):
    def __init__(self, wrapped):
        self._w = wrapped
    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                text = re.sub(r'^\[\d+\]', '', text)
                text = text.replace('\\u000d', '').replace('\\u000a', ' ')
                msg  = msg.rstrip('\n')
                # When the text begins with \q\d \v N, outputError was called
                # with a begin offset before the verse marker, so the checking
                # module reported the previous verse.  Correct it here.
                qv = _Q_VERSE_RE.match(text)
                if qv:
                    ref = re.sub(r':\d+$', ':' + qv.group(1), ref)
                self._w.write(ref + '\t\t' + msg + '\t' + text + '\n')
                return
            except ValueError:
                pass
        self._w.write(s)
    def flush(self):
        self._w.flush()
    def close(self):
        self._w.close()

_sys.stdout = _ReorderOutput(_sys.stdout)

# Match inline footnotes (\f...\f*), cross-refs (\x...\x*), and \qs...\qs* on one line.
# We replace matches with equal-length spaces so error positions remain valid.
INLINE_RE = re.compile(
    ur'\\f\s[^\r\n]*?\\f\*|\\x\s[^\r\n]*?\\x\*|\\qs\s[^\r\n]*?\\qs\*|\\fig\s[^\r\n]*?\\fig\*'
    ur'|\\[a-z]+\*',
    re.UNICODE
)

def blank_inline(text):
    return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)


def make_char_class(chars):
    result = u'['
    for c in chars:
        if c in u'\\]^-':
            result += u'\\' + c
        else:
            result += c
    result += u']'
    return result


def build_patterns():
    if CheckFinalPunct == "Yes" and not FinalPunctuation:
        print "# FinalPunctuation option cannot be empty when CheckFinalPunct is Yes"
        return None

    if CheckHangingWord == "Yes" and not NonFinalPunctuation:
        print "# NonFinalPunctuation option cannot be empty when CheckHangingWord is Yes"
        return None

    try:
        min_chars = max(0, int(MinCharsBeforePunct))
    except ValueError:
        min_chars = 0

    # [ \t\r\n]+ allows any whitespace after the marker, including a newline when
    # the poetry marker sits on its own line and content follows on the next line.
    q = ur'\\q[12]?[ \t\r\n]+'
    eol = ur'[ \t]*\r?\n[ \t]*'   # trailing spaces, newline, optional leading spaces on next line

    # {min_chars,}? requires at least min_chars characters of text before a final
    # punctuation character is considered.  When min_chars=0 this is identical to *?.
    before_punct = ur'[^\r\n]{' + unicode(min_chars) + ur',}?'

    p1a = p1b = None
    if CheckFinalPunct == "Yes":
        punct_class = make_char_class(FinalPunctuation)

        # Pattern 1a: final punct followed by a word character on the SAME line.
        p1a = re.compile(
            q + before_punct + punct_class + ur'(?=[^\r\n]*\w)',
            re.UNICODE | re.MULTILINE
        )

        # Pattern 1b: poetry line ends with final punct then newline, and the very
        # next line opens with \v N (no intervening \q marker).
        p1b = re.compile(
            q + before_punct + punct_class + eol + ur'\\v\s',
            re.UNICODE | re.MULTILINE
        )

    p2a = p2b = None
    if CheckDoubleVerse == "Yes":
        # Pattern 2a: a poetry line containing two \v markers on the SAME line.
        p2a = re.compile(
            q + ur'[^\r\n]*\\v\s+\d+[^\r\n]*\\v\s',
            re.UNICODE | re.MULTILINE
        )

        # Pattern 2b: a poetry line with \v N, then a newline, then another \v N.
        p2b = re.compile(
            q + ur'[^\r\n]*\\v\s+\d+[^\r\n]*' + eol + ur'\\v\s',
            re.UNICODE | re.MULTILINE
        )

    p3 = None
    if CheckTextBeforeVerse == "Yes":
        # Pattern 3: non-whitespace, non-marker text appears before a \v.
        # Normal form: \q1 \v 5 text or \q1\n\v 5 text.
        # Bad form: \q1 text \v 5 or \q1 text\n\v 5.
        # (?:\r?\n[ \t]*)? allows the \v to appear on the line after the text.
        p3 = re.compile(
            q + ur'[ \t]*[^ \t\r\n\\][^\r\n]*(?:\r?\n[ \t]*)?\\v\s',
            re.UNICODE | re.MULTILINE
        )

    p4 = None
    if CheckHangingWord == "Yes":
        non_final_class = make_char_class(NonFinalPunctuation)
        # \r?$ handles CRLF files where \r sits between the last word and \n.
        p4 = re.compile(
            q + ur'[^\r\n]*' + non_final_class + ur'[ \t]+\w+[ \t]*(?=\r?$|\\q)',
            re.UNICODE | re.MULTILINE
        )

    return p1a, p1b, p2a, p2b, p3, p4


try:
    compiled = build_patterns()
except Exception, e:
    print "# q_error: failed to build patterns: " + str(e)
    compiled = None


def checkChapter(reference, text, lastChapter):
    if compiled is None:
        return
    # Ensure unicode so regex \w etc. work correctly on accented characters.
    if not isinstance(text, unicode):
        text = text.decode('utf-8')
        checking.text = text   # keep module global in sync for outputError
    p1a, p1b, p2a, p2b, p3, p4 = compiled
    processed = blank_inline(text)

    reported = set()

    def report(start, end, msg):
        if start not in reported:
            reported.add(start)
            # Patterns end on the whitespace after \v; extend to include the
            # verse number so the text column shows e.g. "\v 4" not "\v ".
            vm = re.match(ur'\d+', text[end:end+6], re.UNICODE)
            checking.outputError(start, end + (vm.end() if vm else 0), msg)

    if p1a is not None:
        for m in p1a.finditer(processed):
            report(m.start(), m.end(), "Final punctuation in q")

    if p1b is not None:
        for m in p1b.finditer(processed):
            report(m.start(), m.end(), "Verse in q")

    if p2a is not None:
        for m in p2a.finditer(text):
            report(m.start(), m.end(), "Poetry line spans multiple verses")

    if p2b is not None:
        for m in p2b.finditer(text):
            report(m.start(), m.end(), "Verse in q")

    if p3 is not None:
        for m in p3.finditer(text):
            report(m.start(), m.end(), "Verse in q")

    if p4 is not None:
        for m in p4.finditer(text):
            report(m.start(), m.end(), "Single word after punctuation")


if compiled is not None:
    checking.checkAllChapters(checkChapter)
