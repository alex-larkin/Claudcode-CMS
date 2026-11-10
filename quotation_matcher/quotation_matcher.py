# -*- coding: utf-8 -*-
#
# Quotation Matcher -- compares each verse of the current project against a
# base project or resource (by verse number) and, where the base text shows
# quotation marks but the current verse has none, inserts matching
# quotation marks into the current project. Placement inside the verse is
# best-effort (anchored to nearby punctuation, or proportional position as a
# fallback) since the base and current texts are not word-aligned across
# languages.
#
# Deliberately no "if __name__ == '__main__':" debug-default block here:
# Paratext runs this file with __name__ == "__main__", so any such block
# would unconditionally clobber every option Paratext just injected (this
# is exactly what happened with an earlier hard-coded BaseProject default,
# which silently overrode a live, correctly-selected option value). Test
# this script by mocking the `checking`/`Paratext.Python` modules and
# exec()-ing the source with a pre-seeded globals dict instead.

import checking
import os
import re
from Paratext.Python import *  # noqa: F401,F403 -- provides ScrTextPy
from ScriptureObjects import ScriptureText

# ---------------------------------------------------------------------------
# Option guards
# ---------------------------------------------------------------------------


def _to_unicode(v):
    if isinstance(v, type(u'')):
        return v
    if not isinstance(v, bytes):
        return unicode(v)
    try:
        return v.decode('utf-8')
    except UnicodeDecodeError:
        return v.decode('mbcs')


# Plain top-level "try: NAME except NameError:" guards -- matching the
# proven pattern every other working check in this repo uses
# (quotation_examiner.py, comparePunctuation.py). A helper function that
# looks these up via globals()[name] does NOT work here: Project (a core
# variable Paratext always injects, not even a custom option) came back
# blank when read that way in a live run, so whatever mechanism Paratext
# uses to inject option values is not visible through a function's own
# globals() -- only through a direct top-level name reference.

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

try:
    OutputProject
except NameError:
    OutputProject = Project
OutputProject = _to_unicode(OutputProject)

try:
    BaseProject
except NameError:
    # Deliberately no real-looking fallback (e.g. "RVC") -- a missing
    # injection should fail loudly via the "not provided" message below,
    # not silently fall back to some other real project's name.
    BaseProject = u''
BaseProject = _to_unicode(BaseProject)

try:
    MaxQuoteLevel
except NameError:
    MaxQuoteLevel = u'1'
MaxQuoteLevel = _to_unicode(MaxQuoteLevel)

try:
    BaseQuotes
except NameError:
    BaseQuotes = u'\u201c \u201d'
BaseQuotes = _to_unicode(BaseQuotes)

try:
    BaseInnerQuotes
except NameError:
    BaseInnerQuotes = u'\u2018 \u2019'
BaseInnerQuotes = _to_unicode(BaseInnerQuotes)

try:
    BaseInnerInnerQuotes
except NameError:
    BaseInnerInnerQuotes = u'\u201c \u201d'
BaseInnerInnerQuotes = _to_unicode(BaseInnerInnerQuotes)

try:
    InsertQuotes
except NameError:
    InsertQuotes = u'\u201c \u201d'
InsertQuotes = _to_unicode(InsertQuotes)

try:
    InsertInnerQuotes
except NameError:
    InsertInnerQuotes = u'\u2018 \u2019'
InsertInnerQuotes = _to_unicode(InsertInnerQuotes)

try:
    InsertInnerInnerQuotes
except NameError:
    InsertInnerInnerQuotes = u'\u201c \u201d'
InsertInnerInnerQuotes = _to_unicode(InsertInnerInnerQuotes)

try:
    BaseContinuer
except NameError:
    BaseContinuer = u'\u00bb'
BaseContinuer = _to_unicode(BaseContinuer)

try:
    BaseInnerContinuer
except NameError:
    BaseInnerContinuer = u'\u201d'
BaseInnerContinuer = _to_unicode(BaseInnerContinuer)

try:
    BaseInnerInnerContinuer
except NameError:
    BaseInnerInnerContinuer = u'\u2019'
BaseInnerInnerContinuer = _to_unicode(BaseInnerInnerContinuer)

try:
    InsertContinuer
except NameError:
    InsertContinuer = u'\u00bb'
InsertContinuer = _to_unicode(InsertContinuer)

try:
    InsertInnerContinuer
except NameError:
    InsertInnerContinuer = u'\u201d'
InsertInnerContinuer = _to_unicode(InsertInnerContinuer)

try:
    InsertInnerInnerContinuer
except NameError:
    InsertInnerInnerContinuer = u'\u2019'
InsertInnerInnerContinuer = _to_unicode(InsertInnerInnerContinuer)

try:
    ApplyChanges
except NameError:
    ApplyChanges = u'No'
ApplyChanges = _to_unicode(ApplyChanges)

try:
    IgnoreNotes
except NameError:
    IgnoreNotes = u'Yes'
IgnoreNotes = _to_unicode(IgnoreNotes)

try:
    MaxExamples
except NameError:
    MaxExamples = u'100'
MaxExamples = _to_unicode(MaxExamples)

try:
    _max_level = int(MaxQuoteLevel)
except (TypeError, ValueError):
    _max_level = 1
_max_level = max(1, min(_max_level, 3))

# Paratext's own UI localizes generic Yes/No option values (confirmed:
# a Spanish-locale run showed/injected the accented "Si" spelling, not
# "Yes"), so a plain English-only comparison silently stays False
# regardless of what the user picks. Recognize known affirmative tokens
# across the languages this project's own UI supports (see
# Resources/Strings.*.xaml in the AutoCorrect projects: en, es, fr, pt,
# zh-Hans) rather than assuming English only. Built with unichr() rather
# than literal non-ASCII characters -- see feedback_cms_py_source_ascii_only
# in project memory.
_YES_TOKENS = frozenset([
    u'yes', u's' + unichr(0x00ed), u'si', u'oui', u'sim', unichr(0x662f), u'true', u'1',
])


def _is_yes(value):
    return value.strip().lower() in _YES_TOKENS


_apply_changes = _is_yes(ApplyChanges)
_ignore_notes = _is_yes(IgnoreNotes)

try:
    _max_examples = int(MaxExamples)
except (TypeError, ValueError):
    _max_examples = 100
_max_examples = max(1, min(_max_examples, 2000))

_MSG_APPLIED = 'Quotation mark(s) inserted here -- see QuotationMatcherReport.html for detail.'
_MSG_PREVIEW = 'Quotation mark(s) proposed here (preview only) -- see QuotationMatcherReport.html for detail.'

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (quotation_examiner.py / project_BT_reference_tool.py).
# ---------------------------------------------------------------------------

BOOK_NAMES = [
    None,
    u'GEN', u'EXO', u'LEV', u'NUM', u'DEU', u'JOS', u'JDG', u'RUT',
    u'1SA', u'2SA', u'1KI', u'2KI', u'1CH', u'2CH', u'EZR', u'NEH',
    u'EST', u'JOB', u'PSA', u'PRO', u'ECC', u'SNG', u'ISA', u'JER',
    u'LAM', u'EZK', u'DAN', u'HOS', u'JOL', u'AMO', u'OBA', u'JON',
    u'MIC', u'NAM', u'HAB', u'ZEP', u'HAG', u'ZEC', u'MAL', u'MAT',
    u'MRK', u'LUK', u'JHN', u'ACT', u'ROM', u'1CO', u'2CO', u'GAL',
    u'EPH', u'PHP', u'COL', u'1TH', u'2TH', u'1TI', u'2TI', u'TIT',
    u'PHM', u'HEB', u'JAS', u'1PE', u'2PE', u'1JN', u'2JN', u'3JN',
    u'JUD', u'REV',
]


def _book_label(book_num):
    if book_num is not None and 1 <= book_num < len(BOOK_NAMES) and BOOK_NAMES[book_num]:
        return BOOK_NAMES[book_num]
    return u'Book {0}'.format(book_num) if book_num is not None else u'?'


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


# ---------------------------------------------------------------------------
# Verse splitting (by \v number, marker text preserved so the current
# project's chapter can be rebuilt after editing only the verse bodies)
# ---------------------------------------------------------------------------

VERSE_MARKER_RE = re.compile(ur'\\v\s+\d+(?:[,-]\d+)*\s*', re.UNICODE)
VERSE_NUM_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)', re.UNICODE)
USFM_MARKER_RE = re.compile(ur'\\[a-zA-Z][a-zA-Z0-9]*\*?', re.UNICODE)

# Blank out footnotes/cross-refs with equal-length spaces so offsets survive
# -- same approach as quotation_examiner.py's _blank_inline. Used on the
# CURRENT side, where a result's offsets must remain valid indices into the
# original current_body for insertion.
INLINE_RE = re.compile(ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*|\\fig\s.*?\\fig\*', re.UNICODE | re.DOTALL)


def _blank_inline(text):
    if not _ignore_notes:
        return text
    return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)


def _strip_inline(text):
    """Removes footnotes/cross-refs outright, shortening the string --
    used only on the BASE side, where the result's length and offsets feed
    proportional math rather than a direct re-index into the original
    string. Padding (as _blank_inline does) would keep those blanked
    characters counting toward base_len, which distorts the proportional
    calculation for every mark in the verse when a note sits at or near the
    verse's own end -- confirmed on a real verse (Spanish text with two
    cross-references after its closing quote) where this pushed a close
    mark to land near the OTHER project's verse-start instead of after its
    own final punctuation."""
    if not _ignore_notes:
        return text
    return INLINE_RE.sub(u'', text)


def _clean_display(s):
    s = USFM_MARKER_RE.sub(u'', s)
    return u' '.join(s.split())


# Markers that introduce non-verse-text material (section headings,
# descriptive titles, speaker labels, parallel-passage references, etc.)
# that can appear between one \v marker and the next but are not part of
# that verse's own translatable content -- same exclusion set
# quotation_examiner.py's PARAGRAPH_MARKER_RE comment already identifies as
# "not paragraph text". A verse's usable content for insertion purposes
# ends at the first such marker, never inside or after it.
NON_VERSE_CONTENT_MARKER_RE = re.compile(
    ur'\\(?:sr|sp|s\d*|r|d|qa|rem|periph|ms\d*|mr)\b', re.UNICODE)


def _content_bound(text):
    m = NON_VERSE_CONTENT_MARKER_RE.search(text)
    bound = m.start() if m else len(text)
    # A verse body always ends with the next verse's own leading paragraph
    # marker tacked on (e.g. "...ku.\r\n\\m\r\n") -- if that marker has
    # nothing real after it, it's not this verse's own content either.
    # Excluding it (and any whitespace right before it) keeps every
    # anchor/proportional/bump computation confined to real text, so a
    # mark can never land inside that whitespace or get skipped straight
    # onto/past the bare marker itself -- confirmed on real verses
    # (Hebrews 1:5, James 5:12) where several marks collapsing onto the
    # same single anchor pushed the ordering bump right into "\\m"/"\\p".
    trailing = _TRAILING_CONTINUATION_MARKER_RE.search(text[:bound])
    if trailing:
        bound = trailing.start()
        while bound > 0 and text[bound - 1] in u' \r\n\t':
            bound -= 1
    return bound


def split_chapter_into_verses(text):
    """Returns [(verseNumber-or-None, markerText, bodyText), ...] covering
    the whole chapter; the first entry is the pre-verse-1 introduction with
    verseNumber None and an empty marker. Concatenating marker+body for
    every entry, in order, reproduces the original text exactly."""
    matches = list(VERSE_MARKER_RE.finditer(text))
    if not matches:
        return [(None, u'', text)]
    segments = [(None, u'', text[:matches[0].start()])]
    for i, m in enumerate(matches):
        marker = m.group(0)
        num_match = VERSE_NUM_RE.match(marker)
        verse_num = num_match.group(1) if num_match else None
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segments.append((verse_num, marker, text[body_start:body_end]))
    return segments


def rebuild_chapter(segments):
    return u''.join(marker + body for (_unused, marker, body) in segments)


def verse_bodies(text):
    """Returns {verseNumber: bodyText} for a chapter -- used for the base
    (read-only) side, where marker text does not need to be preserved."""
    bodies = {}
    for verse_num, _marker, body in split_chapter_into_verses(text):
        if verse_num:
            bodies[verse_num] = body
    return bodies


# Paragraph/poetry-type markers -- valid quotation-continuer positions.
# Adapted from quotation_examiner.py's PARAGRAPH_MARKER_RE, same exclusion
# of heading/title/speaker markers (NON_VERSE_CONTENT_MARKER_RE above) --
# a continuer belongs at a genuine new paragraph/poetry line, not a
# section heading.
CONTINUATION_MARKER_RE = re.compile(
    ur'\\(?:cls|pmo|pmc|pmr|pm|po|pr|pc|ph\d*|pi\d*|mi|nb|m|p|b'
    ur'|qac|qm\d*|qr|qc|qs|qa|qd|q\d*)\b', re.UNICODE)
_TRAILING_CONTINUATION_MARKER_RE = re.compile(
    CONTINUATION_MARKER_RE.pattern + ur'\s*$', re.UNICODE)


def verse_paragraph_starts(segments):
    """Given split_chapter_into_verses()'s output, returns the set of verse
    numbers whose own \\v marker is immediately preceded (in the chapter
    text) by a paragraph/poetry-type marker -- valid continuer positions.
    A verse's own body (as extracted above) never includes what precedes
    its \\v marker, so this looks at the PRECEDING segment's trailing
    content instead."""
    starts = set()
    prev_body = None
    for verse_num, _marker, body in segments:
        if prev_body is not None and verse_num and _TRAILING_CONTINUATION_MARKER_RE.search(prev_body):
            starts.add(verse_num)
        prev_body = body
    return starts


# ---------------------------------------------------------------------------
# Quote-pair options -> {level: (open, close)}
# ---------------------------------------------------------------------------


def _parse_pair(option_value):
    parts = option_value.split()
    open_c = parts[0] if len(parts) > 0 else u''
    close_c = parts[1] if len(parts) > 1 else u''
    return open_c, close_c


def _build_level_pairs(level1, level2, level3):
    pairs = {}
    options_by_level = [level1, level2, level3]
    for level in range(1, _max_level + 1):
        open_c, close_c = _parse_pair(options_by_level[level - 1])
        if open_c or close_c:
            pairs[level] = (open_c, close_c)
    return pairs


_base_pairs = _build_level_pairs(BaseQuotes, BaseInnerQuotes, BaseInnerInnerQuotes)
_insert_pairs = _build_level_pairs(InsertQuotes, InsertInnerQuotes, InsertInnerInnerQuotes)


def _build_level_singles(level1, level2, level3):
    singles = {}
    values_by_level = [level1.strip(), level2.strip(), level3.strip()]
    for level in range(1, _max_level + 1):
        v = values_by_level[level - 1]
        if v:
            singles[level] = v
    return singles


_base_continuers = _build_level_singles(BaseContinuer, BaseInnerContinuer, BaseInnerInnerContinuer)
_insert_continuers = _build_level_singles(InsertContinuer, InsertInnerContinuer, InsertInnerInnerContinuer)


def _combined_char_class(chars):
    chars = sorted(set(chars), key=len, reverse=True)
    if not chars:
        return None
    return re.compile(u'|'.join(re.escape(c) for c in chars), re.UNICODE)


def _pair_chars(pairs_dict):
    chars = []
    for open_c, close_c in pairs_dict.values():
        if open_c:
            chars.append(open_c)
        if close_c:
            chars.append(close_c)
    return chars


_base_char_re = _combined_char_class(_pair_chars(_base_pairs))
_insert_char_re = _combined_char_class(_pair_chars(_insert_pairs))
# Broader than _insert_char_re -- also includes continuer characters, used
# only for the "already has quotes" skip check so a verse that already has
# a continuer (but no plain open/close mark) isn't double-touched.
_insert_any_char_re = _combined_char_class(
    _pair_chars(_insert_pairs) + list(_insert_continuers.values()))


def has_any_char(text, char_re):
    return bool(char_re) and char_re.search(text) is not None


# ---------------------------------------------------------------------------
# Quote-mark detection in the base verse text
# ---------------------------------------------------------------------------


def find_quote_marks(text, pairs_dict, char_re):
    """Returns a list of {'kind': 'open'|'close', 'level', 'offset'} for
    every configured quotation-mark character found in text, in document
    order. Deliberately does NOT try to pair an opener with its closer --
    a quote that opens in one verse and closes in a later one is common,
    and pairing would either miss both marks or require cross-verse state.
    Each occurrence is classified directly by which side of its level's
    configured pair it matches and handled entirely on its own; the caller
    inserts each mark into its own verse independently, as close as
    possible to the analogous position, with no assumption that its
    counterpart appears anywhere nearby."""
    if char_re is None:
        return []
    marks = []
    for m in char_re.finditer(text):
        ch = m.group(0)
        for lvl, (o, c) in pairs_dict.items():
            if o == ch:
                marks.append({'kind': u'open', 'level': lvl, 'offset': m.start()})
            if c == ch:
                marks.append({'kind': u'close', 'level': lvl, 'offset': m.start()})
    marks.sort(key=lambda d: d['offset'])
    return marks


# ---------------------------------------------------------------------------
# Best-effort insertion-point heuristics in the current project's verse
# ---------------------------------------------------------------------------

_OPEN_COLON_ANCHOR_RE = re.compile(ur'[:]\s*', re.UNICODE)
_OPEN_COMMA_ANCHOR_RE = re.compile(ur'[,]\s*', re.UNICODE)
_OPEN_CONTEXT_RE = re.compile(ur'[,:]\s*$', re.UNICODE)
_CLOSE_ANCHOR_RE = re.compile(ur'[.?!]+', re.UNICODE)
_OPEN_CONTEXT_WINDOW = 6


def _snap_to_word_boundary(text, offset):
    n = len(text)
    offset = max(0, min(offset, n))
    if offset == 0 or offset == n:
        return offset
    if text[offset - 1].isspace() or text[offset].isspace():
        return offset
    left = offset
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    right = offset
    while right < n and not text[right].isspace():
        right += 1
    return left if (offset - left) <= (right - offset) else right


def _word_end_forward(text, offset):
    """If offset sits strictly inside a word (not adjacent to whitespace
    on either side), walk forward to that word's end. Used only after the
    ordering-bump below, which can otherwise land one character at a time
    straight through the middle of a short word when several marks
    collapse onto the same anchor in a heavily compressed verse -- e.g.
    real John 1:21, where two marks bumping past each other split a short
    word into a mark-word-mark-word sequence mid-word. Doesn't fix the
    underlying collision (there may
    genuinely be nowhere better to put a mark when the current text has
    far fewer natural anchor points than the base has quote marks -- an
    accepted limitation), just guarantees the fallback never splits a
    word; worst case, marks land stacked together at the same boundary."""
    n = len(text)
    if offset <= 0 or offset >= n:
        return offset
    if text[offset - 1].isspace() or text[offset].isspace():
        return offset
    while offset < n and not text[offset].isspace():
        offset += 1
    return offset


def _skip_marker(text, offset):
    """If offset falls anywhere inside a backslash-marker token (\\q, \\s,
    etc.) -- at its backslash, inside its name, or on the single space
    that follows it -- advance to right after that space, so an insertion
    never ends up wedged inside a marker or between a marker and its own
    content. Unlike a simple "does a marker start exactly here" check,
    this also catches an offset that snapped to a point in the middle of
    the marker token itself."""
    for m in USFM_MARKER_RE.finditer(text):
        if m.start() > offset:
            break
        end = m.end()
        follow_end = end + 1 if end < len(text) and text[end] == u' ' else end
        if offset <= follow_end:
            return follow_end
    return offset


def _proportional_offset(current_len, base_len, base_offset):
    base_len = max(1, base_len)
    off = int(round(current_len * (base_offset / float(base_len))))
    return max(0, min(off, current_len))


def _base_supports_open_anchor(detect_body, base_open_start):
    """Only trust a comma/colon anchor in the CURRENT text if the BASE
    text's own open mark is itself immediately preceded by one -- a base
    quote that opens a verse or poetry line cold (no preceding punctuation
    at all) should land near the current verse's own start, not jump to
    some unrelated colon elsewhere in the verse."""
    window_start = max(0, base_open_start - _OPEN_CONTEXT_WINDOW)
    prefix = detect_body[window_start:base_open_start]
    return bool(_OPEN_CONTEXT_RE.search(prefix))


def _opening_insert_offset(current_body, detect_body, base_len, base_open_start):
    proportional = _proportional_offset(len(current_body), base_len, base_open_start)

    # The base's open sits immediately after an embedded paragraph/poetry
    # marker (a fresh \q/\m/\p line, not the verse's own absolute start)
    # -- anchor to the CURRENT text's own analogous structural marker,
    # mirroring _continuer_insert_offset, rather than punctuation, which
    # isn't the relevant cue for a quote that opens cold at a poetry
    # line's own start. Confirmed on a real verse (Hebrews 1:5) where the
    # base's open comes right after "\q " -- the opener belongs at the
    # front of the current text's own corresponding \q line, not one word
    # into it.
    if base_open_start > 0 and _TRAILING_CONTINUATION_MARKER_RE.search(detect_body[:base_open_start]):
        marker_off = _continuer_insert_offset(current_body, base_len, base_open_start)
        if marker_off is not None:
            return _skip_marker(current_body, marker_off), u'anchored'

    if _base_supports_open_anchor(detect_body, base_open_start):
        # A colon reliably introduces direct speech; a comma does not --
        # prefer any colon in the verse outright rather than picking
        # whichever punctuation happens to be numerically closest to the
        # proportional guess, which can pick an unrelated comma over the
        # real reported-speech colon when word-length ratios differ
        # between languages.
        colon_anchors = [m.end() for m in _OPEN_COLON_ANCHOR_RE.finditer(current_body)]
        anchors = colon_anchors or [m.end() for m in _OPEN_COMMA_ANCHOR_RE.finditer(current_body)]
        if anchors:
            best = min(anchors, key=lambda a: abs(a - proportional))
            return _skip_marker(current_body, best), u'anchored'
    elif base_open_start > 0:
        # Mid-prose, with no comma/colon right before the base's own open
        # at all (e.g. a "which means X" gloss) -- still prefer any colon
        # in the CURRENT text over blind proportional math, since these
        # translations often introduce the same gloss/reported-speech
        # with a colon even when the base doesn't punctuate it that way.
        # Confirmed on a real verse (Mark 15:22): Spanish glosses with a
        # bare "que significa" plus a guillemet-quoted gloss, but Otomi's
        # own equivalent introduces the same gloss with a real colon that
        # the base text solely lacks.
        colon_anchors = [m.end() for m in _OPEN_COLON_ANCHOR_RE.finditer(current_body)]
        if colon_anchors:
            best = min(colon_anchors, key=lambda a: abs(a - proportional))
            return _skip_marker(current_body, best), u'anchored'

    off = _snap_to_word_boundary(current_body, proportional)
    # An opener belongs at the FRONT of the word it introduces, never at
    # the tail of the preceding one -- _snap_to_word_boundary just picks
    # whichever adjacent space is numerically closer, which for an offset
    # starting mid-token (e.g. right on a comma) returns the space that
    # already follows it, i.e. BEFORE that space. Walking forward past any
    # such whitespace fixes a "word,<< space" result into ", <<word" --
    # confirmed on a real verse (Mark 15:22) where this produced a comma
    # then guillemet then space then word instead of the correct comma,
    # space, guillemet, word order. A no-op whenever the snap already
    # landed at a word's own start.
    while off < len(current_body) and current_body[off] in u' \r\n\t':
        off += 1
    return _skip_marker(current_body, off), u'proportional'


def _closing_insert_offset(current_body, base_len, base_close_start):
    # Mirrors _opening_insert_offset: search the whole current verse for
    # sentence-final punctuation closest to the proportional guess, insert
    # right after it (matching the base convention of period-then-closer,
    # e.g. period then closing guillemet, never closing guillemet then
    # period). No near-end gating -- a quote
    # that closes well before a long verse's own end still deserves a real
    # punctuation anchor rather than falling straight to unanchored
    # proportional math.
    proportional = _proportional_offset(len(current_body), base_len, base_close_start)
    anchors = [m.end() for m in _CLOSE_ANCHOR_RE.finditer(current_body)]
    if anchors:
        best = min(anchors, key=lambda a: abs(a - proportional))
        # A verse with only one (or only distant) sentence-final
        # punctuation mark would otherwise always "win" by default even
        # when it has nothing to do with where the quote actually closes
        # (e.g. a verse ending in a colon instead of a period, with the
        # only stray period sitting in an unrelated earlier sentence) --
        # confirmed on a real verse where this collided with the opener
        # and got shoved into the middle of the next word. Only trust an
        # anchor that's reasonably close to the proportional guess;
        # otherwise fall through to plain proportional placement, which is
        # imprecise but never corrupts a word or collides with another mark.
        if abs(best - proportional) <= max(20, int(0.5 * len(current_body))):
            return _skip_marker(current_body, best), u'anchored'
    off = _snap_to_word_boundary(current_body, proportional)
    return _skip_marker(current_body, off), u'proportional'


def _continuer_insert_offset(current_body, base_len, base_offset, min_offset=-1):
    """Mirrors _opening_insert_offset/_closing_insert_offset's own shape,
    except the anchor class is structural paragraph/poetry markers, not
    punctuation -- a continuer belongs right after the current project's
    OWN analogous \\q/\\m/\\p-etc. break, not at some proportional point in
    running prose. The verse's own start (offset 0) is always a candidate
    too, since a continuer detected at the base verse's own start should
    still be able to land at the current verse's start even though there's
    no marker there to find within current_body itself.

    min_offset excludes any candidate at or before it -- a verse with
    several continuers (e.g. a multi-line poetry citation with three \\q
    breaks) picks each one's "closest to proportional" candidate fully
    independently otherwise, and a LATER continuer's own proportional
    guess can easily be numerically closer to an EARLIER continuer's
    already-claimed marker than to its own analogous one -- confirmed on
    real MAT 4:6, where this caused two continuers to collide on the same
    \\q and the ordering safety net's "+1" bump then landed mid-word.
    Excluding already-claimed positions up front, rather than only fixing
    up the collision after the fact, keeps each continuer attached to an
    actual structural break instead of getting shoved into running text.

    Returns None (no sensible place to attach this continuer) rather than
    forcing a bad position when nothing is close enough or nothing is left
    after excluding min_offset -- the caller simply skips it for this
    specific mark."""
    proportional = _proportional_offset(len(current_body), base_len, base_offset)
    candidates = [c for c in [0] + [
        (m.end() + 1) if m.end() < len(current_body) and current_body[m.end()] == u' ' else m.end()
        for m in CONTINUATION_MARKER_RE.finditer(current_body)
    ] if c > min_offset]
    if not candidates:
        return None
    best = min(candidates, key=lambda a: abs(a - proportional))
    if abs(best - proportional) > max(20, int(0.5 * len(current_body))):
        return None
    return best


# ---------------------------------------------------------------------------
# Per-verse processing
# ---------------------------------------------------------------------------


def find_continuer_marks(detect_body, is_paragraph_start):
    """Returns a list of {'kind':'continuer','level','offset','matched_len'}
    for every configured continuer character found immediately after a
    valid paragraph/poetry-marker position -- either the verse's own start
    (if is_paragraph_start) or any \\q/\\m/\\p-etc. marker embedded WITHIN
    the verse body itself. A single verse can have several of these (a
    multi-line poetry citation where the quote continues at each line,
    e.g. real MAT 4:6, which has three separate \\q breaks each with their
    own continuer) -- unlike the old design, this is not limited to a
    single check at the verse's own start.

    Checked BEFORE the normal open/close scan and excluded from it (the
    caller blanks out each matched occurrence before running
    find_quote_marks), so the same character is never also classified as
    a plain close mark just because it happens to share a character with
    one -- the exact bug quotation_examiner.py's own continuer logic
    guards against (see its DBTALP/Hebrews 3:10-11 history)."""
    positions = [0] if is_paragraph_start else []
    for m in CONTINUATION_MARKER_RE.finditer(detect_body):
        end = m.end()
        if end < len(detect_body) and detect_body[end] == u' ':
            end += 1
        positions.append(end)
    marks = []
    for pos in positions:
        for level in sorted(_base_continuers.keys()):
            c = _base_continuers[level]
            if c and detect_body[pos:pos + len(c)] == c:
                marks.append({'kind': u'continuer', 'level': level, 'offset': pos, 'matched_len': len(c)})
                break
    return marks


def process_verse(current_body, base_body, is_paragraph_start=False):
    """Returns (new_body, insertions, skip_reason). insertions is a list of
    {'level','kind','text','confidence'} dicts (empty if nothing changed).
    skip_reason is set (and insertions empty) when the current verse
    already has a configured quote character and was left untouched."""
    detect_body = _strip_inline(base_body)
    detect_body = detect_body[:_content_bound(detect_body)]

    continuer_marks = find_continuer_marks(detect_body, is_paragraph_start)
    scan_body = detect_body
    if continuer_marks:
        # Blank out just the matched continuer characters (same
        # length-preserving technique as _blank_inline) so the normal
        # open/close scan below can't also pick them up as plain closes --
        # these positions may be scattered anywhere in the verse, not just
        # a single leading prefix, so a simple slice-and-offset no longer
        # works here the way it used to.
        chars = list(scan_body)
        for cm in continuer_marks:
            for i in range(cm['offset'], min(cm['offset'] + cm['matched_len'], len(chars))):
                chars[i] = u' '
        scan_body = u''.join(chars)

    marks = list(continuer_marks)
    marks.extend(find_quote_marks(scan_body, _base_pairs, _base_char_re))
    marks.sort(key=lambda d: d['offset'])

    if not marks:
        return current_body, [], None

    check_body = _blank_inline(current_body)
    if has_any_char(check_body, _insert_any_char_re):
        return current_body, [], u'already_has_quotes'

    # Anchor/proportional searches must never look past current_bound --
    # otherwise a heading/reference line sitting right after the real verse
    # content (which often has its own punctuation, e.g. "\r (Mr. 5.1-20;
    # Lc. 8.26-39)") can win the "closest to proportional" comparison and
    # get clamped back to the boundary afterward, which visually reads as
    # the mark landing on the wrong side of a line break -- confirmed on a
    # real verse. Slicing here (rather than only clamping the final offset)
    # keeps the "closest anchor" comparison itself confined to real content.
    # Also blank the current side's own footnotes/cross-refs first (padded,
    # not stripped, so every index stays a valid position in current_body
    # for the actual insertion below) so a stray period or comma inside one
    # of the CURRENT project's own notes can't win an anchor search either.
    current_blanked = _blank_inline(current_body)
    current_bound = _content_bound(current_blanked)
    usable_body = current_blanked[:current_bound]
    base_len = len(detect_body)
    planned = []
    # Tracks the last offset actually placed so far, in the marks' natural
    # (base-document) order -- passed to _continuer_insert_offset so a
    # later continuer can never claim an earlier one's marker position
    # (see that function's docstring for why "closest to proportional"
    # alone isn't enough for continuers specifically).
    running_min = -1
    for mark in marks:
        if mark['kind'] == u'continuer':
            ins_text = _insert_continuers.get(mark['level'])
            if not ins_text:
                continue
            off = _continuer_insert_offset(usable_body, base_len, mark['offset'], running_min)
            if off is None:
                continue
            off = _skip_marker(usable_body, off)
            planned.append([off, ins_text, mark['level'], u'continuer', u'continuer'])
            running_min = off
            continue
        pair = _insert_pairs.get(mark['level'])
        if not pair:
            continue
        open_c, close_c = pair
        if mark['kind'] == u'open':
            if not open_c:
                continue
            off, conf = _opening_insert_offset(usable_body, detect_body, base_len, mark['offset'])
            planned.append([off, open_c, mark['level'], u'open', conf])
            running_min = off
        else:
            if not close_c:
                continue
            off, conf = _closing_insert_offset(usable_body, base_len, mark['offset'])
            planned.append([off, close_c, mark['level'], u'close', conf])
            running_min = off

    if not planned:
        return current_body, [], None

    # Clamp every offset so it can never land at/after a following
    # section-heading-type marker (see NON_VERSE_CONTENT_MARKER_RE), then
    # enforce a strict increase across the whole natural-order sequence
    # (open0, close0, open1, close1, ...) -- the two heuristic functions
    # above compute each offset independently and are not guaranteed to
    # keep a span's close after its own open, or to keep spans from
    # crossing each other. A strict "+1" bump (not just ">=") avoids a
    # same-offset tie, which would otherwise apply in the wrong visual
    # order under the reverse-offset apply step below. Record when either
    # adjustment actually changed anything so the report can flag it.
    last_offset = -1
    for entry in planned:
        off = min(entry[0], current_bound)
        if off <= last_offset:
            off = min(last_offset + 1, current_bound)
            # The bumped value is a brand new offset nobody has checked
            # yet -- without this, a bump can land squarely inside a
            # marker token (e.g. between "\" and "m" of "\m"), confirmed
            # on a real verse where several bogus marks collided near the
            # end of a short verse.
            off = min(_skip_marker(usable_body, off), current_bound)
            # Likewise, a bump can land squarely inside a WORD rather than
            # a marker -- confirmed on a real verse where two colliding
            # marks split a short word open. See _word_end_forward.
            off = min(_word_end_forward(usable_body, off), current_bound)
        if off != entry[0]:
            entry[4] = entry[4] + u'/adjusted'
        entry[0] = off
        last_offset = off

    # Apply from the highest offset down so earlier offsets stay valid.
    planned.sort(key=lambda t: t[0], reverse=True)
    new_body = current_body
    for off, ins_text, _level, _kind, _conf in planned:
        new_body = new_body[:off] + ins_text + new_body[off:]

    insertions = [{'level': lvl, 'kind': kind, 'text': ins_text, 'confidence': conf}
                  for (_off, ins_text, lvl, kind, conf) in planned]
    return new_body, insertions, None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_report_rows = []
_skip_rows = []
_write_errors = []
_backup_buffer = {}


def _project_directory():
    scr = getattr(checking, 'scr', None)
    d = getattr(scr, 'Directory', None) if scr is not None else None
    if not d:
        return None
    if isinstance(d, bytes):
        d = d.decode('mbcs')
    return d


def _open_for_write(path):
    return path.encode('mbcs') if isinstance(path, type(u'')) else path


def _record_insert(reference, verse_num, before_body, after_body, insertions):
    ref_str = u'{0} {1}:{2}'.format(_book_label(reference.Book), reference.Chapter, verse_num)
    confidences = sorted(set(i['confidence'] for i in insertions))
    _report_rows.append({
        'ref': ref_str,
        'confidence': u'/'.join(confidences),
        'before': _clean_display(before_body),
        'after': _clean_display(after_body),
    })


def _record_skip(reference, verse_num, reason):
    ref_str = u'{0} {1}:{2}'.format(_book_label(reference.Book), reference.Chapter, verse_num)
    _skip_rows.append(u'{0} -- {1}'.format(ref_str, reason))


def _write_backup(book_num, chapter_texts):
    directory = _project_directory()
    if not directory:
        _write_errors.append(u'{0} -- backup skipped: project directory unknown'.format(_book_label(book_num)))
        return
    path = os.path.join(directory, u'QuotationMatcherBackup_{0}.sfm'.format(_book_label(book_num)))
    try:
        with open(_open_for_write(path), 'wb') as f:
            f.write(u''.join(chapter_texts).encode('utf-8'))
    except Exception, e:
        _write_errors.append(u'{0} -- backup write failed: {1}'.format(_book_label(book_num), _to_unicode(repr(e))))


def _write_html_report():
    directory = _project_directory()
    if not directory:
        return
    path = os.path.join(directory, u'QuotationMatcherReport.html')
    parts = [
        u'<html><head><meta charset="utf-8">'
        u'<title>Quotation Matcher Report</title></head><body>',
        u'<h1>Quotation Matcher Report</h1>',
        u'<p>Project: {0} &nbsp; Base: {1} &nbsp; Apply Changes: {2}</p>'.format(
            _he(Project), _he(BaseProject), u'Yes' if _apply_changes else u'No (preview only)'),
    ]
    if Scr2 is None:
        parts.append(
            u'<p><strong>Warning: the base project/resource could not be '
            u'opened, so nothing below was compared.</strong> Check the '
            u'BaseProject option value and re-run.</p>')
    parts += [
        u'<h2>Inserted / proposed ({0})</h2>'.format(len(_report_rows)),
        u'<table border="1" cellpadding="4" cellspacing="0">'
        u'<tr><th>Reference</th><th>Confidence</th><th>Before</th><th>After</th></tr>',
    ]
    for row in _report_rows[:_max_examples]:
        parts.append(u'<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td></tr>'.format(
            _he(row['ref']), _he(row['confidence']), _he(row['before']), _he(row['after'])))
    parts.append(u'</table>')
    if len(_report_rows) > _max_examples:
        parts.append(u'<p>... and {0} more not shown (increase Max rows per report table to see more).</p>'.format(
            len(_report_rows) - _max_examples))
    parts.append(u'<h2>Skipped -- already had quotes ({0})</h2><ul>'.format(len(_skip_rows)))
    for row in _skip_rows[:_max_examples]:
        parts.append(u'<li>{0}</li>'.format(_he(row)))
    parts.append(u'</ul>')
    if _write_errors:
        parts.append(u'<h2><strong>Write errors ({0})</strong></h2><ul>'.format(len(_write_errors)))
        for row in _write_errors[:_max_examples]:
            parts.append(u'<li>{0}</li>'.format(_he(row)))
        parts.append(u'</ul>')
    parts.append(u'</body></html>')
    html = u''.join(parts)
    try:
        with open(_open_for_write(path), 'wb') as f:
            f.write(html.encode('utf-8'))
        os.startfile(_open_for_write(path))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

checking.setupCheck()  # always do this first to initialize before running the check

# Every [CAN CHANGE TEXT] example in the official SDK (SampleScript.py,
# insertFootnoteReferences.py, TransferSectionHeadings.py, etc.) writes via
# a dedicated ScriptureText(OutputProject) object obtained through the
# \outputProject directive -- never by writing directly to checking.scr.
# Live testing confirmed writing via checking.scr.PutText(...) directly
# fails with Paratext.Data.LockNotObtainedException even when Apply
# Changes is Yes and nothing else is obviously wrong; matching the proven
# pattern here is the fix.
try:
    _scr_out = ScriptureText(OutputProject)
except Exception, e:
    _scr_out = None
    print u'# Could not open output project: {0} -- {1}'.format(OutputProject, _to_unicode(repr(e)))

if not BaseProject.strip():
    Scr2 = None
    print u'# BaseProject option was not provided -- nothing to compare against.'
else:
    try:
        Scr2 = ScrTextPy(BaseProject)
    except Exception:
        Scr2 = None
        print u'# Could not open base project/resource: {0}'.format(BaseProject)


def checkChapter(reference, text, lastChapterInBook):
    if Scr2 is None:
        return

    book_num = reference.Book
    try:
        base_text = Scr2.GetText(reference, 1, 0)  # single chapter, no mapin
    except Exception:
        base_text = u''

    if _apply_changes:
        _backup_buffer.setdefault(book_num, []).append(text)

    base_segments = split_chapter_into_verses(base_text)
    base_verses = dict((v, b) for (v, _m, b) in base_segments if v)
    base_paragraph_starts = verse_paragraph_starts(base_segments)
    segments = split_chapter_into_verses(text)

    new_segments = []
    changed = False
    offset = 0
    for verse_num, marker, body in segments:
        body_start = offset + len(marker)
        new_body = body
        if verse_num and verse_num in base_verses:
            is_paragraph_start = verse_num in base_paragraph_starts
            new_body, insertions, skip_reason = process_verse(
                body, base_verses[verse_num], is_paragraph_start)
            if insertions:
                changed = True
                _record_insert(reference, verse_num, body, new_body, insertions)
                msg = _MSG_APPLIED if _apply_changes else _MSG_PREVIEW
                checking.outputError(body_start, body_start, msg)
            elif skip_reason:
                _record_skip(reference, verse_num, skip_reason)
        new_segments.append((verse_num, marker, new_body))
        offset += len(marker) + len(body)

    if changed and _apply_changes:
        new_text = rebuild_chapter(new_segments)
        if _scr_out is None:
            _write_errors.append(u'{0} {1} -- cannot write: output project not opened'.format(
                _book_label(book_num), reference.Chapter))
        else:
            try:
                # ScriptureText.putText's internal reference() only accepts
                # a plain str or its own Reference class, not the raw
                # native VerseRefPy checkAllChapters gives us -- convert.
                _scr_out.putText(reference.AsString.encode('utf-8'), new_text, 1, 0)
            except Exception, e:
                _write_errors.append(u'{0} {1} -- PutText failed: {2}'.format(
                    _book_label(book_num), reference.Chapter, _to_unicode(repr(e))))
                print u'# PutText failed -- see QuotationMatcherReport.html for detail.'

    if lastChapterInBook and _apply_changes and book_num in _backup_buffer:
        _write_backup(book_num, _backup_buffer.pop(book_num))


checking.checkAllChapters(checkChapter)

if _apply_changes and _scr_out is not None:
    # Matches every official [CAN CHANGE TEXT] example, which calls this
    # unconditionally after writing -- needed if PutText created a new
    # book, and possibly to finalize/flush pending writes generally.
    try:
        _scr_out.save(OutputProject)
    except Exception, e:
        _write_errors.append(u'save() failed: {0}'.format(_to_unicode(repr(e))))

_write_html_report()
