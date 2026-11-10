# -*- coding: utf-8 -*-
import checking
import re

try:
    MinChars
except NameError:
    MinChars = "40"

try:
    CheckOtherMarkers
except NameError:
    CheckOtherMarkers = "No"

try:
    OtherMarkers
except NameError:
    OtherMarkers = "q q1 q2 q3 q4"

checking.setupCheck()

INLINE_RE = re.compile(
    ur'\\f\s[^\r\n]*?\\f\*|\\x\s[^\r\n]*?\\x\*',
    re.UNICODE)

VERSE1_RE = re.compile(ur'\\v\s+1(?!\d)(?:-\d+)?[ \t\r\n]+', re.UNICODE)

# All paragraph-type markers — used to find the marker immediately before \v 1
ALL_PARA_RE = re.compile(
    ur'\\(p(?:[crhi]\d?)?|q[a-z]?\d?|mi?|nb|b|li\d?)(?=[\s\\]|$)',
    re.UNICODE | re.MULTILINE)

CHAR_MARKER_RE = re.compile(ur'\\[a-zA-Z]+\d*\*?\s*', re.UNICODE)

# \p always checked; \m always in before set
_before_set = {u'p', u'm'}
_after_set = {u'p'}

if CheckOtherMarkers == "Yes":
    _extra = [m.strip() for m in OtherMarkers.split() if m.strip()]
    _before_set.update(_extra)
    _after_set.update(_extra)

# Build the after-marker regex from _after_set
_after_parts = sorted(_after_set, key=len, reverse=True)
AFTER_RE = re.compile(
    ur'\\(' + u'|'.join(re.escape(m) for m in _after_parts) + ur')(?=[\s\\]|$)',
    re.UNICODE | re.MULTILINE)


def blank_inline(text):
    return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)


def count_plain_chars(segment):
    stripped = CHAR_MARKER_RE.sub(u'', segment)
    return len(stripped.strip())


def checkChapter(reference, text, lastChapter):
    min_chars = int(MinChars)
    clean = blank_inline(text)

    v1 = VERSE1_RE.search(clean)
    if not v1:
        return

    # The paragraph marker immediately before \v 1 must be in _before_set
    prev_marks = list(ALL_PARA_RE.finditer(clean, 0, v1.start()))
    if not prev_marks or prev_marks[-1].group(1) not in _before_set:
        return

    # The next paragraph marker after verse 1 content must be in _after_set
    content_start = v1.end()
    next_mark = AFTER_RE.search(clean, content_start)
    if not next_mark:
        return

    content_end = next_mark.start()
    verse1_text = clean[content_start:content_end]
    count = count_plain_chars(verse1_text)

    if count < min_chars:
        display_end = content_end
        while display_end > content_start and clean[display_end - 1] in u'\r\n\t ':
            display_end -= 1
        checking.outputError(
            v1.start(),
            display_end,
            u'%d chars (set = %d)' % (count, min_chars)
        )

checking.checkAllChapters(checkChapter)
