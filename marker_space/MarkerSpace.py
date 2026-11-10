# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

# Optional helper from the cms folder (ptx_goto.py): makes the references in
# the HTML report clickable. Without it the references stay plain text.
try:
    import ptx_goto as _ptx_goto
except Exception:
    _ptx_goto = None
_links_on = False

def _goto(ref):
    return _ptx_goto.target(ref) if _links_on else None

def _ref_link(ref_html, tgt):
    return _ptx_goto.link(ref_html, tgt) if _links_on and tgt else ref_html

# ---------------------------------------------------------------------------
# Option guards
# ---------------------------------------------------------------------------

def _to_unicode(v):
    if isinstance(v, type(u'')):
        return v
    if not isinstance(v, bytes):
        # Paratext injects numeric-looking option defaults as an int rather
        # than a string, despite cms.md documenting all options as strings.
        return unicode(v)
    try:
        return v.decode('utf-8')
    except UnicodeDecodeError:
        return v.decode('mbcs')

try:
    ExcludeMarkers
except NameError:
    ExcludeMarkers = u''
ExcludeMarkers = _to_unicode(ExcludeMarkers)
_exclude_markers = frozenset(
    m.lstrip(u'\\') for m in ExcludeMarkers.split() if m.strip())

try:
    NoCloseMarkers
except NameError:
    NoCloseMarkers = u'v fk fp fq fqa ft fr xk xo xq'
NoCloseMarkers = _to_unicode(NoCloseMarkers)
_no_close_markers = frozenset(
    m.lstrip(u'\\') for m in NoCloseMarkers.split() if m.strip())

try:
    NoCloseInNoteMarkers
except NameError:
    # \xt is unlike the other NoCloseMarkers: real USFM uses it BOTH nested
    # inside \x...\x*/\f...\f* (where it commonly has no closing marker of
    # its own -- the enclosing \x*/\f* ends it) AND standalone in running
    # text (e.g. an introduction paragraph quoting Scripture), where it's a
    # normal character style that DOES need its own \xt*. So when nested in
    # a note span, only the "unclosed" verdict is suppressed for it (no
    # \xt* found is normal there); if it DOES carry its own \xt*, that pair
    # still gets the full normal spacing checks, note span or not.
    NoCloseInNoteMarkers = u'xt'
NoCloseInNoteMarkers = _to_unicode(NoCloseInNoteMarkers)
_note_context_markers = frozenset(
    m.lstrip(u'\\') for m in NoCloseInNoteMarkers.split() if m.strip())

try:
    ExtraSpacingMarkers
except NameError:
    # \f and \x are StyleType Note in usfm.sty, not Character, so they'd
    # otherwise never be picked up by the Character-style filter below --
    # but the same open/close spacing conventions apply to them too.
    ExtraSpacingMarkers = u'f x'
ExtraSpacingMarkers = _to_unicode(ExtraSpacingMarkers)
_extra_spacing_markers = frozenset(
    m.lstrip(u'\\') for m in ExtraSpacingMarkers.split() if m.strip())

try:
    NoSpaceBeforeMarkers
except NameError:
    # Unlike \nd/\tl/etc., a footnote or cross-reference caller conventionally
    # attaches DIRECTLY to the preceding word/punctuation with NO space (real
    # PDT15 data confirms this: "...matrimonio.\f + \fr..." with no space
    # before \f, every single time) -- a space there is the mistake, the
    # reverse of the normal "missing space before opening marker" check.
    NoSpaceBeforeMarkers = u'f x'
NoSpaceBeforeMarkers = _to_unicode(NoSpaceBeforeMarkers)
_no_space_before_markers = frozenset(
    m.lstrip(u'\\') for m in NoSpaceBeforeMarkers.split() if m.strip())

try:
    FootnotePrecedesText
except NameError:
    FootnotePrecedesText = u'No'
FootnotePrecedesText = _to_unicode(FootnotePrecedesText)
_footnote_precedes_text = FootnotePrecedesText.strip().lower() == u'yes'
if _footnote_precedes_text:
    # \f is normally in NoSpaceBeforeMarkers (attaches directly to the
    # PRECEDING word). In a project where the footnote precedes the word it
    # annotates instead, that direction reverses: \f now wants a normal
    # space before it, like any other marker (see checkChapter/_check_pair
    # for the mirrored "no space after \f*" half of this).
    _no_space_before_markers = _no_space_before_markers - frozenset([u'f'])

try:
    CrossReferencesPrecedeText
except NameError:
    CrossReferencesPrecedeText = u'Yes'
CrossReferencesPrecedeText = _to_unicode(CrossReferencesPrecedeText)
_xref_precedes_text = CrossReferencesPrecedeText.strip().lower() == u'yes'
if _xref_precedes_text:
    # \x is normally in NoSpaceBeforeMarkers (attaches directly to the
    # PRECEDING word/punctuation). Defaulting to Yes here means \x is
    # removed from that set by default -- a project using the traditional
    # "\x glued after the word" convention (e.g. real PDT15 data) must set
    # this option to No to keep that behavior. Independent of
    # FootnotePrecedesText: a project can have footnotes and
    # cross-references follow opposite conventions from each other.
    _no_space_before_markers = _no_space_before_markers - frozenset([u'x'])

try:
    MaxExamples
except NameError:
    MaxExamples = u'25'
MaxExamples = _to_unicode(MaxExamples)
try:
    _max_examples = int(MaxExamples)
except (TypeError, ValueError):
    _max_examples = 25
_max_examples = max(1, min(_max_examples, 500))

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

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
# Project directory / stylesheet locations
# ---------------------------------------------------------------------------

def _project_directory():
    scr = getattr(checking, 'scr', None)
    if scr is None:
        return None
    d = getattr(scr, 'Directory', None)
    if not d:
        return None
    if isinstance(d, bytes):
        d = d.decode('mbcs')
    return d


def _open_path(path):
    # Windows file APIs under Python 2 want the narrow (mbcs) encoding for
    # paths containing non-ASCII characters -- same pattern used throughout
    # this repo's other checks (quotation_examiner.py, project_BT_reference_tool.py).
    return path.encode('mbcs') if isinstance(path, type(u'')) else path


# ---------------------------------------------------------------------------
# .sty parsing and marker-vocabulary merge
# ---------------------------------------------------------------------------

# \t*-prefixed markers are almost always table/structure markers (\tc1, \tr,
# \th1, \toc1, etc.) that generate noise for this check and aren't meant to
# be tracked -- ignored by default. \tl is a genuine Character-style pair
# (\tl ... \tl*) and stays tracked normally; \ts-s/\ts-e (USFM 3 section
# milestone start/end) are exempted from this ignore rule too, though they
# aren't independently tracked as an open/close pair by this script (they're
# self-closing milestones, not an open-content-close span).
_T_PREFIX_KEEP = frozenset([u'tl', u'ts-s', u'ts-e'])


def _is_ignored_t_marker(marker):
    return marker.lower().startswith(u't') and marker not in _T_PREFIX_KEEP

def _parse_sty(path):
    """Line-based parser: a line starting with \\Marker opens a new entry
    keyed by the marker code; any other \\FieldName value line sets that
    field (lowercased) on the CURRENT entry. Blank lines and #-comments are
    ignored. Blank-line separation between entries is NOT relied upon --
    real .sty files aren't consistent about it (see TestProject/PDT15/usfm_mod.sty).
    Returns {marker_code: {field_name_lower: value_string}}."""
    entries = {}
    current = None
    if not path or not os.path.isfile(path):
        return entries
    try:
        with open(_open_path(path), 'rb') as f:
            data = f.read()
    except IOError:
        return entries
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('mbcs', 'replace')
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(u'#') or not stripped.startswith(u'\\'):
            continue
        parts = stripped[1:].split(None, 1)
        if not parts:
            continue
        field = parts[0]
        value = parts[1].strip() if len(parts) > 1 else u''
        if field == u'Marker':
            current = entries.setdefault(value, {})
        elif current is not None:
            current[field.lower()] = value
    return entries


def _merge_sty(base, custom):
    merged = {}
    for marker, fields in base.items():
        merged[marker] = dict(fields)
    for marker, fields in custom.items():
        target = merged.setdefault(marker, {})
        target.update(fields)
    return merged


def _resolve_endmarker(marker, fields):
    """Returns the bare closing-marker text, with NO leading backslash and
    no nesting '+' (e.g. u'nd*') -- callers build their own regex from this,
    since the marker code can be glued directly to content (needing the
    _open_marker_regex disambiguation) and the actual closing marker in real
    text may carry a leading '+' when nested (see _marker_regex)."""
    end_field = fields.get(u'endmarker', u'').split()
    return end_field[0] if end_field else (marker + u'*')


def _marker_regex(bare, all_marker_names=None):
    """Compiles a regex matching '\\bare' or '\\+bare' (USFM 3's nesting
    marker: a character style nested inside a footnote or another character
    style is written with a '+' right after the backslash, e.g. \\+nd ...
    \\+nd*, to disambiguate it from the outer style). When all_marker_names
    is given, also disambiguates against the real marker vocabulary so a
    marker glued directly to following content isn't missed (see
    _open_marker_regex's fuller explanation) -- used for opening markers
    only, since closing markers are unambiguous once '*' is reached."""
    lookahead = u''
    if all_marker_names is not None:
        extensions = sorted(
            (m[len(bare):] for m in all_marker_names if m != bare and m.startswith(bare)),
            key=len, reverse=True)
        if extensions:
            lookahead = ur'(?!' + u'|'.join(re.escape(e) for e in extensions) + ur')'
    return re.compile(ur'\\\+?' + re.escape(bare) + lookahead, re.UNICODE)


def _load_character_markers(project_directory):
    """Returns (char_markers, all_marker_names, no_close_endmarkers, diag):
    - char_markers: {marker: bare_endmarker} for merged StyleType=Character
      entries, minus anything in ExcludeMarkers or NoCloseMarkers, PLUS every
      marker named in NoCloseInNoteMarkers (e.g. \\xt) even if it's missing
      or not Character-styled in the merged stylesheet -- those markers go
      through the normal pipeline below, but are excused from being flagged
      as unclosed when found nested inside a \\x.../\\f... span with no
      closing marker of their own (see _note_spans/checkChapter); if one
      DOES carry its own closing marker there, it's checked normally
      -- PLUS every marker named in ExtraSpacingMarkers (e.g. \\f, \\x),
      which are StyleType Note rather than Character in usfm.sty and so
      would otherwise never be picked up, but get the exact same spacing
      checks as any other paired marker.
      `bare_endmarker` has no leading backslash and no nesting '+'
      (e.g. u'nd*') -- see _marker_regex.
    - all_marker_names: every marker name defined in either file (any
      StyleType), UNIONED with every marker named in any option (even if the
      stylesheet doesn't define it) -- needed so a marker glued to following
      letters isn't confused with a different, longer marker name that
      happens to start with the same letters (USFM has no marker-boundary
      character other than whitespace/backslash/asterisk/nesting '+', so
      this has to be disambiguated against the known marker vocabulary, not
      via a regex word boundary). Without the option-configured markers
      unioned in, "\\f" would incorrectly swallow "\\ft" whenever the
      stylesheet doesn't happen to define \\ft as its own entry.
    - no_close_endmarkers: {marker: bare_endmarker} for every marker named in
      the NoCloseMarkers option (e.g. v, fq -- markers that don't normally
      take a closing marker at all, in any context, so they're excluded from
      the usual open/close spacing checks). Resolved the same way as
      char_markers, but WITHOUT the StyleType=Character filter, since some
      of these (\\v in particular) aren't Character-style markers at all --
      a closing marker on any of them is still worth flagging if one is found.
    - diag: dict with the resolved usfm.sty/custom.sty paths and how many
      markers were found in each, for the report header.
    """
    usfm_path = None
    custom_path = None
    if project_directory:
        parent = os.path.dirname(project_directory.rstrip(u'\\/'))
        usfm_path = os.path.join(parent, u'usfm.sty')
        custom_path = os.path.join(project_directory, u'custom.sty')

    base = _parse_sty(usfm_path)
    custom = _parse_sty(custom_path)
    merged = _merge_sty(base, custom)

    char_markers = {}
    for marker, fields in merged.items():
        if fields.get(u'styletype', u'').strip().lower() != u'character':
            continue
        if marker in _exclude_markers or marker in _no_close_markers:
            continue
        if _is_ignored_t_marker(marker):
            continue
        char_markers[marker] = _resolve_endmarker(marker, fields)

    for marker in _note_context_markers:
        if marker in _exclude_markers or _is_ignored_t_marker(marker):
            continue
        char_markers.setdefault(marker, _resolve_endmarker(marker, merged.get(marker, {})))

    for marker in _extra_spacing_markers:
        if marker in _exclude_markers or marker in _no_close_markers or marker in _note_context_markers:
            continue
        if _is_ignored_t_marker(marker):
            continue
        char_markers.setdefault(marker, _resolve_endmarker(marker, merged.get(marker, {})))

    no_close_endmarkers = {}
    for marker in _no_close_markers:
        if _is_ignored_t_marker(marker):
            continue
        no_close_endmarkers[marker] = _resolve_endmarker(marker, merged.get(marker, {}))

    # The real usfm.sty always defines standard markers like \ft/\fr/\xo/\xt,
    # so merged.keys() alone would normally be enough to disambiguate "\f"
    # from "\ft" (see _marker_regex). But if a project's stylesheet is
    # missing one of these for any reason, silently falling back to matching
    # "\f" INTO "\ft" would be a much worse failure than over-including a
    # name here -- so every marker this script has been told about (via any
    # option) is unioned in too, regardless of whether the stylesheet
    # actually defines it.
    all_marker_names = (
        frozenset(merged.keys()) | frozenset(char_markers.keys()) |
        frozenset(no_close_endmarkers.keys()) | _exclude_markers |
        _no_close_markers | _note_context_markers | _extra_spacing_markers |
        _no_space_before_markers)

    diag = {
        'usfm_path': usfm_path, 'usfm_found': bool(base),
        'custom_path': custom_path, 'custom_found': bool(custom),
        'usfm_marker_count': len(base), 'custom_marker_count': len(custom),
    }
    return char_markers, all_marker_names, no_close_endmarkers, diag


# ---------------------------------------------------------------------------
# Regex / position helpers
# ---------------------------------------------------------------------------

CHAPTER_RE = re.compile(ur'\\c\s+(\d+)', re.UNICODE)
VERSE_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)\s*', re.UNICODE)
USFM_MARKER_RE = re.compile(ur'\\[a-zA-Z][a-zA-Z0-9]*\*?', re.UNICODE)

# Matches the start of a NoSpaceBeforeMarkers marker (by default \f/\x, the
# footnote/cross-reference callers) -- used so a closing marker immediately
# followed by one of these (e.g. "\tl*\f + ...", "\qs*\x - ...", real and
# common in PDT15: transliterated/technical terms followed directly by an
# explanatory footnote) is treated as normal, not a missing-space anomaly.
# That marker's OWN spacing is still checked separately by the normal
# pipeline (its inverted check A already expects no space before it).
_NO_SPACE_BEFORE_RE = (
    re.compile(ur'\\\+?(?:' + u'|'.join(re.escape(m) for m in _no_space_before_markers) + ur')\b', re.UNICODE)
    if _no_space_before_markers else None)

# Matches another closing marker (optionally nested, '\+xyz*') starting right
# where we are -- used to recognize adjacent closing markers (nested
# character styles ending together, e.g. "\+nd word\+nd*\add*"), which
# conventionally hug each other with no space in between.
_NEXT_CLOSE_MARKER_RE = re.compile(ur'\\\+?[a-zA-Z][a-zA-Z0-9]*\*', re.UNICODE)

# Footnote (\f ... \f*) and cross-reference (\x ... \x*) spans -- used only
# to tell whether a NoCloseInNoteMarkers occurrence (e.g. \xt) is nested
# inside one, where it's conventionally left unclosed (the enclosing \f*/\x*
# ends it), versus used standalone in running text, where it needs its own
# closing marker like any other character style.
NOTE_SPAN_RE = re.compile(ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*', re.UNICODE | re.DOTALL)


def _note_spans(text):
    return [(m.start(), m.end()) for m in NOTE_SPAN_RE.finditer(text)]


def _in_any_span(pos, spans):
    for start, end in spans:
        if start <= pos < end:
            return True
    return False


# Matches a marker token (optionally with inline \v/\c-style numeric content,
# e.g. "\v 21 ") through its own required trailing whitespace. finditer's
# match.end() positions are where that marker's own spacing ends and real
# content begins -- used to tell a NoSpaceBeforeMarkers marker (\f/\x)
# sitting right there ("\v 21 \f ...", "\c 9 \p \f ...") from one actually
# glued to word content with a stray space in between. Real PDT15 data has
# BOTH shapes: a footnote for a whole verse sits right after "\v N ", and a
# footnote on a Psalm heading sits right after "\c N \p " (two matches in a
# row: "\c 9 " ends right where "\p " begins, which ends right where \f
# begins) -- that leading space belongs to the marker's own required
# marker-to-content spacing, not a real word-to-\f/\x gap. '~' (Paratext's
# non-breaking space) counts as spacing here too, e.g. "\v 21~\f ...".
MARKER_SPACE_RE = re.compile(
    ur'\\\+?[a-zA-Z][a-zA-Z0-9]*\*?(?:[\s~]+\d+(?:[,-]\d+)*)?[\s~]+', re.UNICODE)


def _marker_space_ends(text):
    return frozenset(m.end() for m in MARKER_SPACE_RE.finditer(text))


def _verse_positions(text):
    return [(m.end(), m.group(1)) for m in VERSE_RE.finditer(text)]


def _verse_at(positions, offset):
    label = None
    for start, v in positions:
        if start <= offset:
            label = v
        else:
            break
    return label if label is not None else u'-'


def _is_punct(ch):
    # Backslash is Unicode category Po ("other punctuation"), but here it
    # always signals the START OF A MARKER, not prose punctuation -- treating
    # it as punctuation would wrongly excuse "glued directly to the next
    # marker with no space" (check A/D) and wrongly excuse "a stray space
    # before the next marker" from ever being mistaken for the new
    # space-before-punctuation check below, so it's excluded here.
    return ch is not None and ch != u'\\' and unicodedata.category(ch).startswith(u'P')


def _is_space(ch):
    # Paratext represents a non-breaking space in USFM source text as a
    # literal '~' (rendered as an actual non-breaking space) -- every
    # spacing check in this file treats it exactly like any other space.
    return ch is not None and (ch.isspace() or ch == u'~')


# Punctuation that should always hug the PRECEDING word/marker with no space
# before it (closing/attaching marks). Deliberately narrower than _is_punct:
# OPENING-style marks -- ( [ { the Spanish inverted question/exclamation
# marks, opening double/single/guillemet quotes -- normally DO take a space
# before them (e.g. "aviv (nisan)"), so a blanket Unicode-punctuation test
# would wrongly flag that normal spacing when checking for a stray space
# before punctuation. Non-ASCII members are built via unichr() so this
# source file itself stays plain ASCII (Paratext 8 loads .py scripts with
# the ANSI/mbcs codec, which chokes on a literal UTF-8 BOM/non-ASCII source).
_CLOSING_PUNCT = frozenset(
    u',.;:!?' u')]}'
    + unichr(0x2026)  # ... ellipsis
    + unichr(0x00BB)  # right guillemet (closing angle quote)
    + unichr(0x201D)  # right double quotation mark
    + unichr(0x2019)  # right single quotation mark
    + unichr(0x203A)  # single right-pointing angle quote
)


def _is_closing_punct(ch):
    return ch is not None and ch in _CLOSING_PUNCT


def _marker_content_starts_with_closing_punct(text, content_start):
    """True if, after skipping the marker's own required space(s), the
    marker's content begins with closing-style punctuation (see
    _CLOSING_PUNCT) -- e.g. "\\ft .". Punctuation must hug the PRECEDING
    word directly (see check E), so when a marker's content is itself just
    trailing punctuation, gluing the (invisible) marker to that word with
    NO space is what renders correctly tight against it -- not a missing-
    space mistake. Used to exempt the "missing space before" checks for
    OPENING markers only (checks A and the no-close-marker check); closing
    markers (e.g. "\\it* .") are NOT exempted -- that's check E's job, and
    it's unaffected by this."""
    n = len(text)
    k = content_start
    while k < n and _is_space(text[k]):
        k += 1
    return k < n and _is_closing_punct(text[k])


def _open_marker_regex(marker, all_marker_names):
    # Disambiguate against the real marker vocabulary: only exclude a match
    # here if some OTHER known marker actually starts with these letters --
    # otherwise "\ndDios" (marker glued to content) would never be
    # recognized as "\nd" at all under a plain \b-anchored regex, since
    # 'd' and 'D' are both word characters (no boundary between them).
    # The trailing (?!\*) keeps this from matching the "\nd" prefix of the
    # closing marker "\nd*" itself.
    base = _marker_regex(marker, all_marker_names).pattern
    return re.compile(base + ur'(?!\*)', re.UNICODE)


def _find_pairs(text, close_re, open_re, skip_predicate=None):
    """skip_predicate(pos), when given, is checked against each open match's
    start position -- it only suppresses the UNCLOSED outcome for that
    occurrence (see NoCloseInNoteMarkers: an \\xt nested in a footnote/xref
    span with no \\xt* of its own is normal, closed by the enclosing \\f*/
    \\x* instead). A pair is still formed normally, with the full set of
    checks applied, whenever a real closing marker IS found -- the predicate
    never suppresses that."""
    opens = list(open_re.finditer(text))
    pairs = []
    unclosed = []
    for idx, m in enumerate(opens):
        next_open_start = opens[idx + 1].start() if idx + 1 < len(opens) else len(text)
        close_m = close_re.search(text, m.end())
        if close_m is not None and close_m.start() < next_open_start:
            pairs.append((m.start(), m.end(), close_m.start(), close_m.end()))
        elif skip_predicate is None or not skip_predicate(m.start()):
            unclosed.append((m.start(), m.end()))
    return pairs, unclosed


def _check_pair(text, open_start, open_end, close_start, close_end,
                 invert_open_spacing=False, marker_space_ends=None,
                 invert_close_spacing=False):
    """Returns a list of failing check codes among 'A','B','C','D','E','F':
    A - missing space before the opening marker (normal-direction markers only
        -- see B for the NoSpaceBeforeMarkers/invert_open_spacing case).
        Exempt when the marker's own content is itself just trailing
        punctuation (e.g. "metal\\ft .\\f*") -- see
        _marker_content_starts_with_closing_punct: gluing the marker
        directly to the preceding word with NO space is what's needed for
        that punctuation to render correctly tight against it.
    B - unwanted space before the opening marker, when invert_open_spacing is
        True (NoSpaceBeforeMarkers, e.g. \\f/\\x footnote/xref callers, which
        conventionally attach directly to the preceding word/punctuation with
        NO space). Exempt when the marker sits right after another marker's
        own required spacing (\\v 21 \\f ..., \\c 9 \\p \\f ...) -- see
        MARKER_SPACE_RE/_marker_space_ends.
    C - unwanted space before the closing marker
    D - missing space after the closing marker, when invert_close_spacing is
        False: glued directly to following content with no space. Punctuation
        directly after is normal, not flagged (see E). So is a
        NoSpaceBeforeMarkers marker directly after, e.g. "\\tl*\\f + ..." --
        a footnote/xref caller right there is normal, and its OWN spacing is
        checked separately when its turn comes up in the pipeline. So is
        ANOTHER closing marker directly after (e.g. "\\+nd*\\add*", nested
        styles ending together) -- that's normal too, and any real anomaly
        belongs to that outer marker's own check.
    E - unwanted space before punctuation after the closing marker (e.g.
        "\\nd* ," -- the space is the mistake; punctuation should hug the
        closing marker directly). Applies the SAME either way regardless of
        invert_close_spacing -- punctuation should always hug tightly, so
        this rule doesn't flip with direction.
    F - unwanted space after the closing marker, when invert_close_spacing is
        True (FootnotePrecedesText for \\f, CrossReferencesPrecedeText for
        \\x): the mirror image of D -- this project's convention glues the
        closing marker directly to the following word with NO space, so a
        space there (when NOT followed by punctuation, which stays governed
        by E) is the anomaly instead.
    """
    anomalies = []
    n = len(text)

    before_open = text[open_start - 1] if open_start > 0 else None
    if invert_open_spacing:
        at_marker_space_end = marker_space_ends is not None and open_start in marker_space_ends
        if before_open is not None and _is_space(before_open) and not at_marker_space_end:
            anomalies.append(u'B')
    elif (before_open is not None and not _is_space(before_open) and not _is_punct(before_open)
          and not _marker_content_starts_with_closing_punct(text, open_end)):
        anomalies.append(u'A')

    before_close = text[close_start - 1] if close_start > 0 else None
    if before_close is not None and _is_space(before_close):
        anomalies.append(u'C')

    after_close = text[close_end] if close_end < n else None
    if after_close is not None:
        if after_close in u' \t~':
            # Punctuation directly after the closing marker is normal (no
            # space needed, e.g. "\nd*."), but a SPACE before that
            # punctuation is itself the mistake (e.g. "\nd* ,") -- a comma
            # should hug the preceding word/marker, not float after a stray
            # space. Only spaces/tabs/'~' are skipped here (not newlines), so
            # a closing marker at end of line followed by punctuation
            # starting a later line isn't mistaken for this on-the-same-line
            # pattern.
            k = close_end
            while k < n and text[k] in u' \t~':
                k += 1
            if k < n and _is_closing_punct(text[k]):
                anomalies.append(u'E')
            elif invert_close_spacing and k < n and not _is_punct(text[k]):
                anomalies.append(u'F')
        elif after_close == u'\\' and (
                (_NO_SPACE_BEFORE_RE is not None and _NO_SPACE_BEFORE_RE.match(text, close_end)) or
                _NEXT_CLOSE_MARKER_RE.match(text, close_end)):
            pass  # normal: directly followed by a footnote/xref caller,
                   # which itself requires NO preceding space (see
                   # NoSpaceBeforeMarkers) -- e.g. "\tl*\f + \fr..." -- OR by
                   # another closing marker, i.e. nested styles ending
                   # together (e.g. "\+nd*\add*") -- any real anomaly there
                   # belongs to that outer marker's own check, not this one
        elif not _is_space(after_close) and not _is_punct(after_close):
            if not invert_close_spacing:
                anomalies.append(u'D')
            # else: glued directly to content is the CORRECT state when the
            # footnote precedes the text it annotates (FootnotePrecedesText)

    return anomalies


_WS_RUN_RE = re.compile(ur'[ \t]+', re.UNICODE)


def _collapse_ws(s):
    # Collapses a run of 2+ spaces/tabs (and any \r\n) down to a single
    # space, WITHOUT stripping leading/trailing whitespace -- a boundary
    # space (or its absence) right next to the highlighted anomaly is often
    # the whole point of the snippet (e.g. check C's "unwanted space before
    # closing marker"), so it must survive exactly as one real space, not be
    # trimmed away or padded in.
    return _WS_RUN_RE.sub(u' ', s.replace(u'\r', u'').replace(u'\n', u' '))


def _snippet(text, window_start, window_end, hl_start, hl_end):
    """Returns an already-HTML-escaped snippet with the anomaly wrapped in
    <b> -- callers must NOT run this through _he() again (that would escape
    the tag itself into visible &lt;b&gt; text instead of rendering bold)."""
    start = max(0, window_start)
    end = min(len(text), window_end)
    before = _he(_collapse_ws(text[start:hl_start]))
    highlight = _he(_collapse_ws(text[hl_start:hl_end]))
    after = _he(_collapse_ws(text[hl_end:end]))
    return before + u'<b>' + highlight + u'</b>' + after


# ---------------------------------------------------------------------------
# Setup (must happen before checkChapter runs)
# ---------------------------------------------------------------------------

checking.setupCheck()

_directory = _project_directory()
_links_on = _ptx_goto is not None and _ptx_goto.enabled(_directory)
_character_markers, _all_marker_names, _no_close_endmarkers, _diag = _load_character_markers(_directory)
_open_regexes = dict(
    (marker, _open_marker_regex(marker, _all_marker_names))
    for marker in _character_markers)
_close_regexes = dict(
    (marker, _marker_regex(bare_endmarker))
    for marker, bare_endmarker in _character_markers.items())
_no_close_regexes = dict(
    (marker, _marker_regex(bare_endmarker))
    for marker, bare_endmarker in _no_close_endmarkers.items())
_no_close_open_regexes = dict(
    (marker, _open_marker_regex(marker, _all_marker_names))
    for marker in _no_close_endmarkers
    if marker not in _exclude_markers)

BUCKETS = [
    (u'A', u'Missing space before open'),
    (u'B', u'Unwanted space before open'),
    (u'C', u'Unwanted space before closing'),
    (u'D', u'Missing space after closing'),
    (u'E', u'Unwanted space after closing'),
]
if _footnote_precedes_text or _xref_precedes_text:
    # Only relevant (and only ever nonzero) when one of these options is on,
    # so it's left out of the report entirely otherwise. CrossReferencesPrecedeText
    # defaults to Yes, so this column/section appears by default.
    BUCKETS.append((u'F', u'Unwanted space after closing (precedes text)'))

# Per-occurrence MSG text for the Paratext results list (see checking.outputError
# below) -- distinct from BUCKETS' generic legend text used in the HTML report,
# since here the marker/endmarker involved can be named directly.
_BUCKET_MESSAGES = {
    u'A': u'Missing space before \\{0}',
    u'B': u'Unwanted space before \\{0}',
    u'C': u'Unwanted space before \\{0}',
    u'D': u'Missing space after \\{0}',
    u'E': u'Unwanted space before punctuation after \\{0}',
    u'F': u'Unwanted space after \\{0} (precedes text)',
}


def _bucket_message(marker, bucket, endmarker):
    if bucket in (u'A', u'B'):
        return _BUCKET_MESSAGES[bucket].format(marker)
    return _BUCKET_MESSAGES[bucket].format(endmarker)

_totals = {}      # marker -> total pair count
_bucket_counts = {}  # (marker, bucket) -> count
_examples = {}    # (marker, bucket) -> list of (ref, snippet)
_unclosed = []    # list of (marker, ref)
_unexpected_close_counts = {}    # marker -> count of endmarker sightings
_unexpected_close_examples = {}  # marker -> list of (ref, snippet)
_no_close_missing_space_counts = {}    # marker -> count of missing-space-before sightings
_no_close_missing_space_examples = {}  # marker -> list of (ref, snippet)
_w_pipe_space_issues = []  # list of (ref, snippet): \w...\w* with a space before its | link delimiter


def checkChapter(reference, text, lastChapter):
    book_num = reference.Book if reference is not None else None
    book_label = _book_label(book_num)
    cm = CHAPTER_RE.search(text)
    chapter_label = cm.group(1) if cm else u'?'
    verse_positions = _verse_positions(text)

    def ref_at(offset):
        v = _verse_at(verse_positions, offset)
        return u'{0} {1}:{2}'.format(book_label, chapter_label, v)

    note_spans = _note_spans(text) if _note_context_markers else []
    marker_space_ends = _marker_space_ends(text) if _no_space_before_markers else frozenset()

    for marker in _character_markers:
        open_re = _open_regexes[marker]
        close_re = _close_regexes[marker]
        skip_predicate = None
        if marker in _note_context_markers:
            skip_predicate = lambda pos: _in_any_span(pos, note_spans)
        pairs, unclosed = _find_pairs(text, close_re, open_re, skip_predicate)
        if not pairs and not unclosed:
            continue
        _totals[marker] = _totals.get(marker, 0) + len(pairs) + len(unclosed)

        for u_start, u_end in unclosed:
            _unclosed.append((marker, ref_at(u_start)))
            checking.outputError(
                u_start, u_end,
                u'Unclosed \\{0} (no matching \\{0}* found)'.format(marker))

        invert_open_spacing = marker in _no_space_before_markers
        invert_close_spacing = ((_footnote_precedes_text and marker == u'f') or
                                 (_xref_precedes_text and marker == u'x'))
        endmarker = _character_markers[marker]
        for (os_, oe, cs, ce) in pairs:
            for bucket in _check_pair(text, os_, oe, cs, ce, invert_open_spacing, marker_space_ends,
                                       invert_close_spacing):
                key = (marker, bucket)
                _bucket_counts[key] = _bucket_counts.get(key, 0) + 1
                if bucket in (u'A', u'B'):
                    window_start, hl_s, hl_e, window_end = os_ - 25, os_, oe, oe + 15
                else:
                    window_start, hl_s, hl_e, window_end = cs - 15, cs, ce, ce + 25
                checking.outputError(
                    hl_s, hl_e,
                    _bucket_message(marker, bucket, endmarker))
                examples = _examples.setdefault(key, [])
                if len(examples) < _max_examples:
                    examples.append((ref_at(os_), _snippet(text, window_start, window_end, hl_s, hl_e)))

            if marker == u'w':
                pipe_pos = text.find(u'|', oe, cs)
                if pipe_pos > oe and _is_space(text[pipe_pos - 1]):
                    hl_s, hl_e = pipe_pos - 1, pipe_pos + 1
                    checking.outputError(
                        hl_s, hl_e,
                        u'Unwanted space before | in \\w...\\w* (produces a double space)')
                    _w_pipe_space_issues.append((ref_at(os_), _snippet(text, hl_s - 20, hl_e + 20, hl_s, hl_e)))

    for marker in _no_close_endmarkers:
        close_re = _no_close_regexes[marker]
        endmarker = _no_close_endmarkers[marker]
        for m in close_re.finditer(text):
            hl_s, hl_e = m.start(), m.end()
            _unexpected_close_counts[marker] = _unexpected_close_counts.get(marker, 0) + 1
            checking.outputError(
                hl_s, hl_e,
                u'Unexpected \\{0} (\\{1} is not normally closed)'.format(endmarker, marker))
            examples = _unexpected_close_examples.setdefault(marker, [])
            if len(examples) < _max_examples:
                examples.append((ref_at(hl_s), _snippet(text, hl_s - 20, hl_e + 20, hl_s, hl_e)))

    for marker in _no_close_open_regexes:
        open_re = _no_close_open_regexes[marker]
        for m in open_re.finditer(text):
            hl_s, hl_e = m.start(), m.end()
            before = text[hl_s - 1] if hl_s > 0 else None
            if (before is None or _is_space(before) or _is_punct(before)
                    or _marker_content_starts_with_closing_punct(text, hl_e)):
                continue
            _no_close_missing_space_counts[marker] = _no_close_missing_space_counts.get(marker, 0) + 1
            checking.outputError(
                hl_s, hl_e,
                u'Missing space before \\{0}'.format(marker))
            examples = _no_close_missing_space_examples.setdefault(marker, [])
            if len(examples) < _max_examples:
                examples.append((ref_at(hl_s), _snippet(text, hl_s - 20, hl_e + 20, hl_s, hl_e)))


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _count_cell(count):
    """Renders a summary-table count cell, highlighted (same shade as an
    inline anomaly highlight) whenever the count is nonzero -- makes real
    problems easy to spot at a glance in the Marker/Total-free columns."""
    css_class = u' class="hit"' if count else u''
    return u'<td{0}>{1}</td>'.format(css_class, count)


def _examples_html(key, heading):
    examples = _examples.get(key)
    if not examples:
        return u''
    total = _bucket_counts.get(key, 0)
    rows = u''.join(
        u'<li>{0} &mdash; <code>{1}</code></li>'.format(_ref_link(_he(ref), _goto(ref)), snip)
        for ref, snip in examples)
    more = u'' if total <= len(examples) else u'<p>+{0} more not shown.</p>'.format(total - len(examples))
    return u'<p><b>{0} ({1}):</b></p><ul>{2}</ul>{3}'.format(_he(heading), total, rows, more)


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Marker Space Check &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'code{white-space:pre-wrap}')
    lines.append(u'code b{background:#ffe58a}')
    lines.append(u'td.hit{background:#ffe58a}')
    lines.append(u'h2{margin-top:28px}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Marker Space Check</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html())
    lines.append(u'<p>Project: <b>{0}</b></p>'.format(_he(project_name)))

    lines.append(u'<p>usfm.sty: <code>{0}</code> &mdash; {1}, {2} marker(s)<br>'
                  u'custom.sty: <code>{3}</code> &mdash; {4}, {5} marker(s)</p>'.format(
        _he(_diag['usfm_path'] or u'(project directory not found)'),
        u'found' if _diag['usfm_found'] else u'NOT FOUND',
        _diag['usfm_marker_count'],
        _he(_diag['custom_path'] or u'(project directory not found)'),
        u'found' if _diag['custom_found'] else u'not present',
        _diag['custom_marker_count']))

    if _note_context_markers:
        lines.append(u'<p><i>{0} {1} checked normally when used on its own, but skipped (no closing marker '
                      u'required) when nested inside a \\f...\\f* or \\x...\\x* span.</i></p>'.format(
            u', '.join(u'\\' + _he(m) for m in sorted(_note_context_markers)),
            u'is' if len(_note_context_markers) == 1 else u'are'))

    # --- Section 1: summary table ---------------------------------------
    lines.append(u'<h2>1. Character marker summary</h2>')
    if not _totals:
        lines.append(u'<p><i>No character markers (from usfm.sty/custom.sty) were found in the scanned text.</i></p>')
    else:
        lines.append(u'<table><tr><th>Marker</th><th>Total</th><th>Unclosed</th>' +
                     u''.join(u'<th>{0}</th>'.format(_he(label)) for _code, label in BUCKETS) + u'</tr>')
        unclosed_by_marker = {}
        for marker, _ref in _unclosed:
            unclosed_by_marker[marker] = unclosed_by_marker.get(marker, 0) + 1
        for marker in sorted(_totals.keys()):
            lines.append(u'<tr><td>\\{0} ... \\{0}*</td><td>{1}</td>{2}'.format(
                _he(marker), _totals[marker], _count_cell(unclosed_by_marker.get(marker, 0))))
            for code, _label in BUCKETS:
                lines.append(_count_cell(_bucket_counts.get((marker, code), 0)))
            lines.append(u'</tr>')
        lines.append(u'</table>')

    # --- Sections 2-5: one per check bucket -----------------------------
    section_num = 2
    for code, label in BUCKETS:
        lines.append(u'<h2>{0}. {1}</h2>'.format(section_num, label))
        section_num += 1
        any_html = False
        for marker in sorted(_totals.keys()):
            html = _examples_html((marker, code), u'\\{0} ... \\{0}*'.format(marker))
            if html:
                any_html = True
                lines.append(html)
        if not any_html:
            lines.append(u'<p>None found.</p>')

    # --- Section 6: unclosed markers -------------------------------------
    lines.append(u'<h2>{0}. Unclosed markers</h2>'.format(section_num))
    if _unclosed:
        shown = _unclosed[:_max_examples]
        rows = u''.join(
            u'<li>\\{0} at {1} &mdash; no matching \\{0}* found before end of chapter</li>'.format(_he(m), _ref_link(_he(r), _goto(r)))
            for m, r in shown)
        more = u'' if len(_unclosed) <= _max_examples else u'<p>+{0} more not shown.</p>'.format(
            len(_unclosed) - _max_examples)
        lines.append(u'<ul>{0}</ul>{1}'.format(rows, more))
    else:
        lines.append(u'<p>None found.</p>')
    section_num += 1

    # --- Section 7: markers not expected to have a closing marker -------
    lines.append(u'<h2>{0}. Markers not expected to have a closing marker</h2>'.format(section_num))
    if _no_close_endmarkers:
        lines.append(u'<p><i>{0} are treated as not normally requiring a closing marker (configurable via the '
                      u'NoCloseMarkers option) and are excluded from the checks above. If a closing marker is '
                      u'nonetheless found for one, it is listed here.</i></p>'.format(
            u', '.join(u'\\' + _he(m) for m in sorted(_no_close_endmarkers.keys()))))
    if _unexpected_close_counts:
        for marker in sorted(_unexpected_close_counts.keys()):
            endmarker = _no_close_endmarkers[marker]
            examples = _unexpected_close_examples.get(marker, [])
            total = _unexpected_close_counts[marker]
            rows = u''.join(
                u'<li>{0} &mdash; <code>{1}</code></li>'.format(_ref_link(_he(ref), _goto(ref)), snip)
                for ref, snip in examples)
            more = u'' if total <= len(examples) else u'<p>+{0} more not shown.</p>'.format(total - len(examples))
            lines.append(u'<p><b>\\{0} found ({1}):</b></p><ul>{2}</ul>{3}'.format(_he(endmarker), total, rows, more))
    else:
        lines.append(u'<p>None found.</p>')
    section_num += 1

    # --- Section 8: missing space before markers without a closing marker
    lines.append(u'<h2>{0}. Missing space before markers without a closing marker</h2>'.format(section_num))
    if _no_close_open_regexes:
        lines.append(u'<p><i>{0} are checked for a missing space before them, the same way any other marker\'s '
                      u'opening spacing is checked, even though they don\'t take a closing marker.</i></p>'.format(
            u', '.join(u'\\' + _he(m) for m in sorted(_no_close_open_regexes.keys()))))
    if _no_close_missing_space_counts:
        for marker in sorted(_no_close_missing_space_counts.keys()):
            examples = _no_close_missing_space_examples.get(marker, [])
            total = _no_close_missing_space_counts[marker]
            rows = u''.join(
                u'<li>{0} &mdash; <code>{1}</code></li>'.format(_ref_link(_he(ref), _goto(ref)), snip)
                for ref, snip in examples)
            more = u'' if total <= len(examples) else u'<p>+{0} more not shown.</p>'.format(total - len(examples))
            lines.append(u'<p><b>\\{0} ({1}):</b></p><ul>{2}</ul>{3}'.format(_he(marker), total, rows, more))
    else:
        lines.append(u'<p>None found.</p>')
    section_num += 1

    # --- Section 9: space before | inside \w...\w* -----------------------
    lines.append(u'<h2>{0}. Space before | inside \\w...\\w*</h2>'.format(section_num))
    lines.append(u'<p><i>A \\w...\\w* span may carry a |-delimited glossary link after the displayed word '
                  u'(e.g. \\w Word|Word in glossary\\w*). A space right before the | becomes part of the '
                  u'rendered text, producing a double space.</i></p>')
    if _w_pipe_space_issues:
        shown = _w_pipe_space_issues[:_max_examples]
        rows = u''.join(
            u'<li>{0} &mdash; <code>{1}</code></li>'.format(_ref_link(_he(ref), _goto(ref)), snip)
            for ref, snip in shown)
        more = u'' if len(_w_pipe_space_issues) <= len(shown) else u'<p>+{0} more not shown.</p>'.format(
            len(_w_pipe_space_issues) - len(shown))
        lines.append(u'<ul>{0}</ul>{1}'.format(rows, more))
    else:
        lines.append(u'<p>None found.</p>')

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

checking.checkAllChapters(checkChapter)

if _directory:
    _html_path = os.path.join(_directory, u'MarkerSpaceReport.html')
    write_html_report(_html_path, Project)
    os.startfile(_html_path)
    sys.stdout.write(u'# Report written to {0}\n'.format(_html_path))
    _total_anomalies = sum(_bucket_counts.values())
    _total_occurrences = sum(_totals.values())
    _total_unexpected_close = sum(_unexpected_close_counts.values())
    _total_no_close_missing_space = sum(_no_close_missing_space_counts.values())
    sys.stdout.write(
        u'# {0} character marker occurrence(s) scanned, {1} flagged, {2} unclosed, '
        u'{3} unexpected closing marker(s), {4} missing space before a no-close marker, '
        u'{5} space-before-| issue(s) in \\w\n'.format(
            _total_occurrences, _total_anomalies, len(_unclosed), _total_unexpected_close,
            _total_no_close_missing_space, len(_w_pipe_space_issues)))
    if not _diag['usfm_found']:
        sys.stdout.write(u'# Warning: usfm.sty was not found at {0}\n'.format(_diag['usfm_path']))
else:
    sys.stdout.write(u'# Error: could not determine project directory; no report written.\n')
