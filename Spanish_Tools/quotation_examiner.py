# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import traceback
import unicodedata
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Option guards
# ---------------------------------------------------------------------------

def _to_unicode(v):
    if isinstance(v, type(u'')):
        return v
    if not isinstance(v, bytes):
        # Paratext injects numeric-looking option defaults (e.g. MaxExamples)
        # as an int rather than a string, despite cms.md documenting all
        # options as strings.
        return unicode(v)
    try:
        return v.decode('utf-8')
    except UnicodeDecodeError:
        return v.decode('mbcs')

try:
    QuoteCharacters
except NameError:
    QuoteCharacters = u'" « » ‘ ’ ‚ ‛ “ ” „ ‟ › ‹'
QuoteCharacters = _to_unicode(QuoteCharacters)

try:
    DashCharacters
except NameError:
    DashCharacters = u'— ― –'
DashCharacters = _to_unicode(DashCharacters)

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
# in this repo (project_BT_reference_tool.py / convert_codes.py).
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
# Regex patterns
# ---------------------------------------------------------------------------

# Blank out footnotes/cross-refs with equal-length spaces so offsets survive.
INLINE_RE = re.compile(ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*|\\fig\s.*?\\fig\*', re.UNICODE | re.DOTALL)


def _blank_inline(text):
    return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)


CHAPTER_RE = re.compile(ur'\\c\s+(\d+)', re.UNICODE)
VERSE_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)\s*', re.UNICODE)
USFM_MARKER_RE = re.compile(ur'\\[a-zA-Z][a-zA-Z0-9]*\*?', re.UNICODE)

# True paragraph/poetry/list body-text markers only -- excludes section
# headings (s#), descriptive titles (d), and speaker labels (sp), which are
# not paragraph text and should not trigger continuer or dash-quote logic.
PARAGRAPH_MARKER_RE = re.compile(
    ur'\\(?:cls|pmo|pmc|pmr|pm|po|pr|pc|ph\d*|pi\d*|mi|nb|m|p|b'
    ur'|qac|qm\d*|qr|qc|qs|qa|qd|q\d*'
    ur'|lim\d*|litl|li\d*|lh|lf)\b',
    re.UNICODE)

# The "\m" margin paragraph specifically -- USFM's marker for continuing the
# SAME paragraph without a new first-line indent, as opposed to "\p" which
# conventionally starts a genuinely new paragraph/speaker turn. A dash sitting
# right after "\m" needs to be told apart from a dash after "\p"/"\q#" -- see
# the dash-handling branch in checkChapter.
MARGIN_MARKER_RE = re.compile(ur'\\m\b', re.UNICODE)

# Poetry markers specifically (the same set folded into PARAGRAPH_MARKER_RE
# above) -- a poetry sub-line break is a typographic device for laying out
# embedded verse (e.g. an OT citation quoted inline within NT prose dialogue),
# not a new paragraph/speaker turn. Used in checkChapter to stop these
# sub-line breaks from implicitly ending a still-open dash-quotation, whose
# speech may legitimately span several \q# lines before its real closer.
POETRY_MARKER_RE = re.compile(ur'\\(?:qac|qm\d*|qr|qc|qs|qa|qd|q\d*)\b', re.UNICODE)


def _skip_markers_and_space(text, pos):
    n = len(text)
    while pos < n:
        c = text[pos]
        if c in u' \t\r\n':
            pos += 1
            continue
        if c in u'[]':
            # Editorial bracket notation (USFM's convention for textually-
            # disputed passages, e.g. Mark 16:9-20) commonly sits right at
            # the start of a paragraph, before the real quote-relevant
            # content -- skip past it so paragraph-start detection lands on
            # the actual character instead of stopping on the bracket.
            pos += 1
            continue
        vm = VERSE_RE.match(text, pos)
        if vm:
            pos = vm.end()
            continue
        mm = USFM_MARKER_RE.match(text, pos)
        if mm:
            pos = mm.end()
            continue
        break
    return pos


def _is_word_char(c):
    if c is None:
        return False
    cat = unicodedata.category(c)
    return cat[0] == u'L' or cat in (u'Mn', u'Mc', u'Me')


_ANGLE_OPEN = u'<<'
_ANGLE_CLOSE = u'>>'


def _char_role(token):
    # << / >> are fixed two-character tokens (unicodedata.category only
    # accepts single characters), so special-case them before category
    # lookup.
    if token == _ANGLE_OPEN:
        return u'open'
    if token == _ANGLE_CLOSE:
        return u'close'
    cat = unicodedata.category(token)
    if cat in (u'Pi', u'Ps'):
        return u'open'
    if cat == u'Pf':
        return u'close'
    return u'ambiguous'


def _skip_markers_and_space_reverse(text, pos):
    """Mirror of _skip_markers_and_space, walking backward from `pos`:
    skips whitespace, `[`/`]`, and any USFM marker (\\tag or \\tag*) whose
    match ends exactly at the current position. Needed so opener/closer
    adjacency checks aren't fooled by an inline character-style marker
    (e.g. \\tl, \\tl*, \\wj) sitting directly between a quote mark and its
    neighboring word -- the same class of problem the forward version
    already solves for `[`/`]` (see the MAT 23:2 bracket-notation fix)."""
    while pos > 0:
        c = text[pos - 1]
        if c in u' \t\r\n' or c in u'[]':
            pos -= 1
            continue
        bs = text.rfind(u'\\', max(0, pos - 20), pos)
        if bs != -1:
            mm = USFM_MARKER_RE.match(text, bs)
            if mm and mm.end() == pos:
                pos = bs
                continue
        break
    return pos


def _prev_nonspace(text, pos):
    j = _skip_markers_and_space_reverse(text, pos)
    return text[j - 1] if j > 0 else None


def _next_nonspace_from(text, pos):
    """First non-space, non-marker character at or after `pos` (pos is
    typically a matched token's end offset, so this looks at what
    immediately follows the token, unlike _prev_nonspace which looks
    before a start offset). Delegates to _skip_markers_and_space so an
    inline character-style marker sitting right against the token (e.g.
    "“\\tl Text") doesn't hide the real next word from view."""
    j = _skip_markers_and_space(text, pos)
    return text[j] if j < len(text) else None


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


def _paragraph_start_positions(text):
    positions = set()
    for m in PARAGRAPH_MARKER_RE.finditer(text):
        positions.add(_skip_markers_and_space(text, m.end()))
    # Additional marker types this specific project's own Settings.xml
    # (ContinueAt) declares as valid continuation points -- e.g. a section
    # heading (\s) -- which the generic hardcoded set above deliberately
    # excludes for projects that don't use them that way.
    if _EXTRA_CONTINUER_MARKER_RE:
        for m in _EXTRA_CONTINUER_MARKER_RE.finditer(text):
            positions.add(_skip_markers_and_space(text, m.end()))
    return positions


_STRAY_BACKSLASH_RE = re.compile(ur'\\(?![a-zA-Z])', re.UNICODE)


def _snippet(text, i, token_end, c):
    start = max(0, i - 25)
    end = min(len(text), token_end + 25)
    s = text[start:i] + u'[' + c + u']' + text[token_end:end]
    s = s.replace(u'\r', u'').replace(u'\n', u' ')
    s = USFM_MARKER_RE.sub(u'', s)
    # A marker may be truncated by the snippet window edge, leaving a lone
    # backslash with no following letter -- drop it rather than show a stray "\".
    s = _STRAY_BACKSLASH_RE.sub(u'', s)
    return u' '.join(s.split())


# ---------------------------------------------------------------------------
# Project Settings.xml -- comparison-only, never authoritative. See plan:
# actual usage is always discovered independently from the scanned text.
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


def _read_configured_levels(directory):
    if not directory:
        return []
    settings_path = os.path.join(directory, u'Settings.xml')
    if not os.path.isfile(settings_path):
        return []
    open_path = settings_path.encode('mbcs') if isinstance(settings_path, type(u'')) else settings_path
    try:
        with open(open_path, 'rb') as f:
            data = f.read()
        root = ET.fromstring(data)
    except Exception:
        return []

    def _text(tag):
        el = root.find(tag)
        if el is None or el.text is None:
            return None
        return _to_unicode(el.text)

    levels = []
    pairs = [
        (u'Quotes', u'Continuer', u'ContinueQuotes'),
        (u'InnerQuotes', u'InnerContinuer', u'ContinueInnerQuotes'),
        (u'InnerInnerQuotes', u'InnerInnerContinuer', u'ContinueInnerInnerQuotes'),
    ]
    for idx, (quote_tag, cont_tag, enable_tag) in enumerate(pairs, start=1):
        qtext = _text(quote_tag)
        if not qtext or not qtext.strip():
            continue
        parts = qtext.split()
        open_c = parts[0] if len(parts) > 0 else u''
        close_c = parts[1] if len(parts) > 1 else u''
        continuer = _text(cont_tag) or u''
        enabled = (_text(enable_tag) or u'').strip().lower() == u'yes'
        # Settings.xml can declare more than one valid opener for a level
        # using "|" (e.g. YUI/ZTG: "“|— ”" -- a dash is an
        # equally valid alternate opener to the curly quote, sharing the
        # SAME closer/continuer). Record any alternate that is itself a
        # dash character so a dash-dialogue open can later be recognized
        # as belonging to this level for continuer purposes -- referenced
        # here via the module-global `_dash_chars`, defined further down in
        # the file but already populated by the time this function is
        # actually called (after `checking.setupCheck()`).
        dash_alt = None
        for alt in open_c.split(u'|'):
            if alt in _dash_chars:
                dash_alt = alt
                break
        levels.append({
            'level': idx, 'open': open_c, 'close': close_c,
            'continuer': continuer, 'continue_enabled': enabled,
            'dash_opener': dash_alt,
        })
    return levels


def _read_continue_at(directory):
    """Reads Settings.xml's ContinueAt (e.g. "p pi b/q1 c/q1 s/q1 s/p"), a
    per-project list of marker names/transitions where this project expects a
    quotation continuer to appear. Returns a frozenset of bare marker names
    (e.g. {'p','pi','b','q1','c','s'}). Different projects genuinely use
    different marker sets for this (PDT15-style projects never continue at a
    section heading; DBTALP-style ones do, and also continue across a new
    chapter) -- a single hardcoded marker list can't cover every convention,
    so this is read as ADDITIONAL positions on top of the generic hardcoded
    set (see PARAGRAPH_MARKER_RE), never a replacement, to avoid regressing
    projects that don't set it. Absent/empty -> empty frozenset, no effect."""
    if not directory:
        return frozenset()
    settings_path = os.path.join(directory, u'Settings.xml')
    if not os.path.isfile(settings_path):
        return frozenset()
    open_path = settings_path.encode('mbcs') if isinstance(settings_path, type(u'')) else settings_path
    try:
        with open(open_path, 'rb') as f:
            data = f.read()
        root = ET.fromstring(data)
    except Exception:
        return frozenset()
    el = root.find(u'ContinueAt')
    if el is None or not el.text:
        return frozenset()
    text = _to_unicode(el.text)
    markers = set()
    for chunk in text.split():
        for part in chunk.split(u'/'):
            part = part.strip()
            if part:
                markers.add(part)
    return frozenset(markers)


# ---------------------------------------------------------------------------
# Character sets and combined scan regex
# ---------------------------------------------------------------------------

# Options list characters space-separated (e.g. "« » “ ”") so individual
# characters are easy to tell apart; split on whitespace rather than treating
# the whole option string as a set of characters.
_quote_chars = frozenset(QuoteCharacters.split())
_dash_chars = frozenset(DashCharacters.split())
_all_chars = _quote_chars | _dash_chars

# Punctuation that commonly follows an opening quote before the first word
# (e.g. Spanish inverted question/exclamation marks: «¿Qué...» / «¡Vamos!»).
_OPENER_FOLLOW_PUNCT = frozenset(u'¿¡')

# << and >> are always treated as quotation marks (an ASCII approximation of
# guillemets some projects key in when proper Unicode input isn't available),
# in addition to whatever single characters QuoteCharacters/DashCharacters
# list -- checked first in the alternation since they are two characters wide.
_alt_parts = [re.escape(_ANGLE_OPEN), re.escape(_ANGLE_CLOSE)]
if _all_chars:
    _alt_parts.append(u'[' + re.escape(u''.join(_all_chars)) + u']')
CHAR_RE = re.compile(u'|'.join(_alt_parts), re.UNICODE)

# ---------------------------------------------------------------------------
# Collected data (module-level, accumulated across the whole project scan)
# ---------------------------------------------------------------------------

_stats = {}      # char -> {bucket: count}
_examples = {}   # (char, bucket) -> [(ref, snippet), ...] capped at _max_examples
_level_usage = {}  # level(int) -> {(open_char, close_char): count}
_unclosed = []   # [{'book':, 'char':, 'level':, 'opened_ref':}, ...]
# HTML-report-only, unlike the buckets recorded via _record: an open quote is
# only known to be unclosed once the book changes or the whole scan ends (see
# _flush_unclosed), by which point the chapter `text` its opening position
# belongs to is no longer the one checkChapter is currently processing -- so
# there is no valid offset left to report it through checking.outputError.

# A dash-opened quotation conventionally has no matching closing dash -- it is
# considered finished at the end of the paragraph it opened in (or sooner, if
# an explicit closing dash is found first; see _finish_open_dash / the dash
# branch in checkChapter). This label marks that implicit, no-error closure
# in the level-usage table, distinct from a real character pair.
_DASH_NO_CLOSER = u'(no closing dash)'

_state = {'stack': [], 'prev_book': None, 'dash_open': None}

# Buckets that represent an actual anomaly worth surfacing directly (as
# opposed to opener_reasonable/closer_reasonable/continuer_reasonable/
# dash_dialogue/dash_closing, which are just normal-usage tallies) -- used
# both to highlight these specific columns in the HTML summary table and to
# decide which occurrences get reported live via checking.outputError below.
_WARN_BUCKETS = frozenset([
    u'continuer_suspicious', u'closer_orphan',
    u'midword_possible_apostrophe', u'other_unusual',
])

# Deliberately pure ASCII, with no {0}-style embedded character -- both
# KOG_U and PDT15 (via checking.outputError, in real live Paratext runs)
# crashed on a UnicodeEncodeError as soon as this message contained ANY
# non-ASCII character, mangled (see _paratext_list_safe's docstring) or a
# genuine, unmangled character alike. The actual flagged character is still
# visible to the user via Paratext's own TEXT/snippet column (built by
# checking.py itself from the begin/end offsets into the real source text),
# which is already proven safe -- mid_sentence_capital.py relies on exactly
# that column, always passing an empty message, and never crashes.
_WARN_MESSAGES = {
    u'continuer_suspicious': u'Suspicious continuer at paragraph/poetry-line start with nothing open',
    u'closer_orphan': u'Used as a closer with no matching opener',
    u'midword_possible_apostrophe': u'Used mid-word (possible apostrophe, not a quotation mark)',
    u'other_unusual': u'In an unexpected position',
}


def _paratext_list_safe(s):
    """Historical workaround for a display-only bug in Paratext's results-
    list write pipeline (guillemet-based projects like PDT15 showed a tofu
    glyph instead of the flagged character). NO LONGER used for the message
    passed to checking.outputError() -- see _record() below. Every character
    in the curly-quote/dash block (U+2000-U+206F -- covers all of this
    check's curly quotes and em/en dashes) encodes in UTF-8 as bytes E2 80
    XX, and this transform's utf-8-encode-then-mbcs-decode round trip turns
    that middle 0x80 byte into a literal EURO SIGN (U+20AC) in the
    resulting text -- byte 0x80 is exactly what cp1252 maps it to. That is
    harmless for guillemets (a different, 2-byte UTF-8 encoding that never
    produces a stray euro sign), which is why this looked safe when only
    verified against PDT15. But it means this function unconditionally
    synthesizes a literal euro sign into the message for the (far more
    common) curly-quote/dash convention -- and a real KOG_U crash
    (UnicodeEncodeError, ascii codec, on that exact synthesized euro sign,
    deep in Paratext's own results-list handling, outside anything in this
    file) confirmed that content reaching checking.outputError() is not
    safe. Kept only for the plain-ASCII stdout summary lines below, where
    it is a no-op (pure ASCII text has nothing for the utf-8/mbcs round
    trip to alter) and changing them isn't necessary."""
    return s.encode('utf-8').decode('mbcs', 'replace')


def _record(begin, end, c, bucket, ref, snippet):
    st = _stats.setdefault(c, {})
    st[bucket] = st.get(bucket, 0) + 1
    if bucket in _WARN_BUCKETS:
        # Pure ASCII, no embedded character (see _WARN_MESSAGES above) --
        # any non-ASCII content here crashes checking.outputError()'s
        # downstream handling, confirmed on more than one real project.
        checking.outputError(begin, end, _WARN_MESSAGES[bucket])
    key = (c, bucket)
    lst = _examples.setdefault(key, [])
    if len(lst) < _max_examples:
        lst.append((ref, snippet))


def _finish_open_dash():
    d = _state['dash_open']
    if d:
        pair = (d['char'], _DASH_NO_CLOSER)
        lvl_dict = _level_usage.setdefault(1, {})
        lvl_dict[pair] = lvl_dict.get(pair, 0) + 1
        _state['dash_open'] = None


def _flush_unclosed(book_num):
    _finish_open_dash()
    if _state['stack']:
        book_label = _book_label(book_num)
        for item in _state['stack']:
            _unclosed.append({
                'book': book_label, 'char': item['char'],
                'level': item['level'], 'opened_ref': item['ref'],
            })
    _state['stack'] = []


def _log_crash(book_label, chapter_label, exc):
    """Writes full crash diagnostics to our own plain UTF-8 file, entirely
    bypassing checking.py's/Paratext's write pipeline (the same reasoning as
    write_html_report below) -- so a bug in checkChapter can be diagnosed
    even though checking.py's own exception-reporting path has already been
    shown (see the KOG_U crash this guards against) to be unreliable for
    non-ASCII content."""
    directory = _project_directory()
    if not directory:
        return
    try:
        tb_text = _to_unicode(traceback.format_exc())
    except Exception:
        try:
            tb_text = _to_unicode(repr(exc))
        except Exception:
            tb_text = u'<unformattable exception>'
    log_path = os.path.join(directory, u'QuotationExaminerCrash.log')
    open_path = log_path.encode('mbcs') if isinstance(log_path, type(u'')) else log_path
    try:
        with open(open_path, 'ab') as f:
            header = u'--- {0} {1} ---\n'.format(book_label, chapter_label)
            f.write(header.encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


# ---------------------------------------------------------------------------
checking.setupCheck()

# checking.py's own error handling (in checkAllChapters) can do a plain
# `print`/`sys.stdout.write()` of text that contains a real curly-quote
# character. CPython's `print` statement encodes a unicode value differently
# depending on whether the target is a genuine C-level `file` object (uses a
# hardcoded ascii fallback if no `.encoding` is set -- this is what crashed)
# or a plain Python object with a `.write()` method (forwards the raw
# unicode value, no internal encoding attempt of its own). Simply replacing
# sys.stdout with a non-file wrapper like this one sidesteps that crash,
# regardless of what write() itself does below.
#
# Deliberately NOT pre-encoding every write here: Paratext's own checking.py
# writes (e.g. via outputError2) already handle non-ASCII text correctly on
# their own -- confirmed against a real, working sibling check
# (mid_sentence_capital.py, which doesn't touch encoding at all and whose
# checktext.out output is valid UTF-8 with no BOM). An earlier attempt to
# pre-encode every write here (first to UTF-8, then to the system codepage)
# broke that working behavior instead of fixing anything -- both attempts
# were "confirmed" only against a standalone python.exe test harness, which
# does not share Paratext's embedded interpreter's real default-encoding
# behavior (see project memory / the investigation plan for detail). Pass
# writes straight through; only fall back to a safe replacement if the
# normal write actually raises, so this still never hard-crashes.
class _SafeStdout(object):
    def __init__(self, stream):
        self._stream = stream

    def write(self, s):
        try:
            self._stream.write(s)
        except UnicodeError:
            # The fallback below has itself been observed to raise (see the
            # KOG_U crash it was meant to guard against) -- re-encoding can
            # collide with whatever encoding step Paratext's own write
            # pipeline applies downstream. This write() must never raise, so
            # any failure here is swallowed rather than re-attempted further.
            try:
                if isinstance(s, unicode):
                    self._stream.write(s.encode('utf-8', 'replace'))
                else:
                    self._stream.write(s.decode('utf-8', 'replace').encode('utf-8', 'replace'))
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


sys.stdout = _SafeStdout(sys.stdout)
# ---------------------------------------------------------------------------

_configured_levels = _read_configured_levels(_project_directory())
_configured_by_level = dict((cfg['level'], cfg) for cfg in _configured_levels)

# Dash character -> level, for levels whose Settings.xml opener declares that
# dash as a valid alternate to a curly quote (e.g. YUI: {u'—': 1}). Empty for
# projects without such a "|" alternation (e.g. PDT15's plain "« »"), so the
# dash-continuer recognition added below never engages for them.
_dash_open_levels = dict(
    (cfg['dash_opener'], cfg['level']) for cfg in _configured_levels if cfg.get('dash_opener'))


def _effective_configured_for_level(level):
    """Configured-level info to use for `level`, cycling back through the
    configured sequence once `level` exceeds how many levels Settings.xml
    actually defines. Real quotations sometimes nest deeper than a project's
    formally configured levels (e.g. a long multi-layer reported speech) --
    when that happens, translators/typesetters reuse the same 2-3 level
    cycle rather than inventing an unknown convention for a 4th+ level, so
    this assumes the same. Without this, any level beyond what's configured
    falls back to the generic closer-category heuristic, which reintroduces
    the exact swallowed-closer bug this project's continuer/closer mismatch
    exposed -- just one level deeper, where it can no longer self-correct."""
    if not _configured_levels or level is None or level < 1:
        return None
    return _configured_levels[(level - 1) % len(_configured_levels)]


def _match_continuer_run(text, start_pos, stack):
    """Tries to match consecutive continuer characters at start_pos against
    ALL of the stack's currently-open levels, OUTER to INNER (stack[0]
    first, matching e.g. DBTALP's "“ ‘" -- a level-1 continuer, a space,
    then a level-2 continuer, reminding the reader both levels are still
    open across one paragraph break). Whitespace/markers between
    consecutive continuers are skipped. Returns a list of
    (char, char_start, char_end), one per stack level in order, ONLY if
    every level matched -- an all-or-nothing match, not just an outer
    prefix. A character that matches an OUTER level's continuer but is not
    immediately followed by the INNER level's continuer too (e.g. a level-1
    "“" opening a fresh level-3 quote while a level-2 quote is separately
    still open, where "“" also happens to be level-1's continuer) is
    genuinely ambiguous from the character alone -- requiring the full
    stack to match is what tells a real continuation (every open level
    reminded together) apart from a coincidental character collision (see
    Hebrews 3:10-11, where "“" matches level 1's continuer but is not
    followed by level 2's, and must fall through to open a fresh level 3
    instead of being swallowed as continuing level 1)."""
    matched = []
    pos = start_pos
    for entry in stack:
        cfg = _effective_configured_for_level(entry['level'])
        m = CHAR_RE.match(text, pos)
        if not m:
            return []
        cand = m.group()
        if cfg and cfg['continuer']:
            ok = (cand == cfg['continuer'])
        else:
            ok = (_char_role(cand) == u'close')
        if not ok:
            return []
        matched.append((cand, pos, m.end()))
        pos = _skip_markers_and_space(text, m.end())
    return matched


_continue_at_markers = _read_continue_at(_project_directory())
_continue_at_chapter = u'c' in _continue_at_markers
_continue_at_text_markers = _continue_at_markers - frozenset([u'c'])
if _continue_at_text_markers:
    _EXTRA_CONTINUER_MARKER_RE = re.compile(
        ur'\\(?:' + u'|'.join(re.escape(m) for m in sorted(_continue_at_text_markers)) + ur')\b',
        re.UNICODE)
else:
    _EXTRA_CONTINUER_MARKER_RE = None


def _checkChapter_impl(reference, text, lastChapter):
    book_num = reference.Book if reference is not None else None
    if book_num != _state['prev_book']:
        _flush_unclosed(_state['prev_book'])
        _state['prev_book'] = book_num

    book_label = _book_label(book_num)
    text = _blank_inline(text)
    cm = CHAPTER_RE.search(text)
    chapter_label = cm.group(1) if cm else u'?'
    verse_positions = _verse_positions(text)
    para_starts = _paragraph_start_positions(text)
    if _continue_at_chapter and cm:
        # This project's ContinueAt setting includes "c" -- a quotation may
        # continue right at the start of a new chapter (common in poetry-
        # heavy books), a position the generic marker set never checks.
        para_starts.add(_skip_markers_and_space(text, cm.end()))

    line_starts = set(para_starts)
    for start, _v in verse_positions:
        line_starts.add(_skip_markers_and_space(text, start))

    # Positions immediately following a "\m" marker specifically (see
    # MARGIN_MARKER_RE) -- used to tell a dash that's CONTINUING/CLOSING an
    # already-open dash-quote across an embedded citation apart from a dash
    # that's genuinely opening new dialogue at an ordinary paragraph break.
    margin_starts = set(
        _skip_markers_and_space(text, m.end()) for m in MARGIN_MARKER_RE.finditer(text))

    # Positions immediately following a poetry marker (\q, \q1, \q2, ...).
    # These are typographic sub-line breaks for laid-out verse, not paragraph/
    # speaker breaks -- crossing one must not implicitly finish a still-open
    # dash-quotation (e.g. an embedded OT citation quoted across several \q#
    # lines inside an ongoing dash-opened speech; see the boundary sweep
    # below).
    poetry_starts = set(
        _skip_markers_and_space(text, m.end()) for m in POETRY_MARKER_RE.finditer(text))

    # Neither a poetry sub-line break nor a "\m" margin-paragraph continuation
    # ends an open dash-quotation by itself -- "\m" is USFM's marker for
    # continuing the SAME paragraph without a new first-line indent (e.g. a
    # narrative attribution clause like "...it is written." following an
    # embedded citation), not a new paragraph/speaker turn the way "\p" is.
    non_terminating_starts = poetry_starts | margin_starts

    def ref_at(offset):
        v = _verse_at(verse_positions, offset)
        return u'{0} {1}:{2}'.format(book_label, chapter_label, v)

    # Paragraph-marker boundaries in position order, used to finish a still-
    # open dash-quotation "at the end of the paragraph" it opened in.
    boundary_positions = sorted(para_starts)
    bi = 0
    nb = len(boundary_positions)

    # Advanced past whenever a multi-level continuer run (see
    # _match_continuer_run) consumes more than one character, so those
    # already-recorded characters aren't reprocessed as fresh opens/closes.
    skip_until = 0

    for m in CHAR_RE.finditer(text):
        i = m.start()
        if i < skip_until:
            continue
        end = m.end()
        c = m.group()

        # A paragraph boundary strictly before this match means we've moved
        # past the paragraph the open dash-quote (if any) started in -- finish
        # it here. A boundary located exactly at `i` is left to the dash/quote
        # handling below, which takes precedence at that position (e.g. a
        # fresh dash-open or a continuer) -- but still consume it here so it
        # isn't mistaken for a boundary crossed later, by a subsequent match
        # still within the same paragraph.
        while bi < nb and boundary_positions[bi] < i:
            # A boundary that is only a poetry sub-line break or a "\m"
            # margin-paragraph continuation doesn't end an open dash-quotation
            # -- see non_terminating_starts above.
            if boundary_positions[bi] not in non_terminating_starts:
                _finish_open_dash()
            bi += 1
        if bi < nb and boundary_positions[bi] == i:
            bi += 1

        ref = ref_at(i)
        snippet = _snippet(text, i, end, c)

        if c in _dash_chars:
            next_c = _next_nonspace_from(text, end)
            prev_c = _prev_nonspace(text, i)
            # A dash opens dialogue either at a paragraph/verse start, or
            # right after a colon introducing quoted speech within the same
            # line (e.g. "le dijo: —¿Qué..."). Either way it's commonly
            # followed by a word, or by Spanish inverted ¿/¡ before one.
            is_dialogue_position = (i in line_starts) or (prev_c == u':')
            if i in margin_starts and _state['dash_open']:
                # A dash right after "\m" while a dash-quote is already open
                # is that quote's own closing attribution continuing after
                # an embedded citation (e.g. YUI MAT 4:6: a Psalm citation
                # via "\q1" lines, then a "\m" line closing v6's dash-quote)
                # -- not a fresh dialogue opening. Falls through to the
                # explicit-closing-dash branch below instead.
                is_dialogue_position = False
            follows_ok = _is_word_char(next_c) or (next_c is not None and next_c in _OPENER_FOLLOW_PUNCT)
            if is_dialogue_position and follows_ok:
                # A fresh dash-opening always ends whatever dash-quote was
                # still open (a new speaker turn implicitly ends the previous
                # one, even within the same paragraph).
                if _state['dash_open']:
                    _finish_open_dash()
                _state['dash_open'] = {'char': c, 'ref': ref, 'level': _dash_open_levels.get(c)}
                _record(i, end, c, 'dash_dialogue', ref, snippet)
            elif _state['dash_open']:
                # A dash appearing later, not itself a dialogue-opening
                # position, while a dash-quote is open: treat it as an
                # explicit closing dash (e.g. "—Hola? —preguntó María.")
                # rather than waiting for the implicit end-of-paragraph finish.
                opened = _state['dash_open']
                pair = (opened['char'], c)
                lvl_dict = _level_usage.setdefault(1, {})
                lvl_dict[pair] = lvl_dict.get(pair, 0) + 1
                _state['dash_open'] = None
                _record(i, end, c, 'dash_closing', ref, snippet)
            # Anything else (a dash not opening/closing a quotation, e.g. a
            # parenthetical aside) isn't quotation-relevant and isn't tallied.
            continue

        # Quote character candidate for a paragraph-break continuer. When
        # Settings.xml tells us exactly what this project's continuer looks
        # like for a level, trust it EXCLUSIVELY rather than also accepting
        # any generic closer-family (Pf) character -- otherwise a project
        # whose continuer differs from its closer (e.g. DBTALP: continuer
        # "“", closer "”") has its genuine closing "”" swallowed
        # here as a false continuer every time it lands on a paragraph-start
        # position, permanently leaking one open quote per occurrence instead
        # of popping the stack. The generic closer-family guess is only used
        # as a fallback when Settings.xml doesn't cover this level at all.
        #
        # More than one currently-open level can each show their own
        # continuer together at the SAME paragraph break (e.g. DBTALP's
        # "“ ‘" -- outer level-1 continuer, then inner level-2 continuer),
        # so match a whole run against the stack (outer to inner), not just
        # the single top-of-stack level.
        if i in para_starts:
            if _state['stack']:
                run = _match_continuer_run(text, i, _state['stack'])
                if run:
                    for r_char, r_start, r_end in run:
                        _record(r_start, r_end, r_char, 'continuer_reasonable',
                                 ref_at(r_start), _snippet(text, r_start, r_end, r_char))
                    skip_until = run[-1][2]
                    continue
            elif _state['dash_open']:
                # A dash-opened quote isn't on `_state['stack']`, but if
                # Settings.xml declares that dash as a valid alternate
                # opener for a level (see `_dash_open_levels`), the SAME
                # continuer that level configures for its curly-quote form
                # is just as valid a reminder that the dash-quote is still
                # open (e.g. YUI: dash-opened level 1, continuer "”" --
                # MAT 12:39 opens with "—", MAT 12:40 continues with "”"
                # after a paragraph break). Only this exact configured
                # continuer is accepted; anything else falls through to the
                # same generic-closer labeling as when nothing is open at
                # all, unchanged for projects with no such alternation
                # (e.g. PDT15, where `dash_level` is always None).
                dash_level = _state['dash_open'].get('level')
                cfg = _effective_configured_for_level(dash_level) if dash_level else None
                if cfg and cfg['continuer'] and c == cfg['continuer']:
                    _record(i, end, c, 'continuer_reasonable', ref, snippet)
                    continue
                if _char_role(c) == u'close':
                    _record(i, end, c, 'continuer_suspicious', ref, snippet)
                    continue
            elif _char_role(c) == u'close':
                # Nothing is open, so nothing here mutates the stack either
                # way -- this is purely a reporting label (continuer vs.
                # closer_orphan). The `_char_role(c) == u'close'` gate is
                # required, not just a refinement: an opener-family character
                # (e.g. DBTALP's "“", which is also its own continuer) must
                # always fall through unconditionally to the normal opener
                # logic below when nothing is open -- an ordinary new
                # quotation starting here is far more common than a stray
                # continuer, and mislabeling it here would mean it never gets
                # pushed at all, silently dropping a real opener.
                _record(i, end, c, 'continuer_suspicious', ref, snippet)
                continue

        # Mid-word-ness (e.g. an apostrophe/elision mark) is defined by having
        # NO space on either side -- check immediate adjacency, not the
        # whitespace-skipping neighbors used below for opener/closer context.
        # U+2019 in particular is formally Pf (a "closer") but is at least as
        # often just an apostrophe, so this check must take priority over the
        # Unicode-category role.
        immediate_prev = text[i - 1] if i > 0 else None
        immediate_next = text[end] if end < len(text) else None

        if _is_word_char(immediate_prev) and _is_word_char(immediate_next):
            role = u'midword'
        else:
            prev_c = _prev_nonspace(text, i)
            next_c = _next_nonspace_from(text, end)
            prev_word = _is_word_char(prev_c)
            next_word = _is_word_char(next_c)
            role = _char_role(c)
            if role == u'ambiguous':
                if prev_word and not next_word:
                    role = u'close'
                elif next_word and not prev_word:
                    role = u'open'
                else:
                    role = u'unusual'

        if role == u'open':
            opens_ok = (next_word or
                        (next_c is not None and next_c in _quote_chars) or
                        (next_c is not None and next_c in _OPENER_FOLLOW_PUNCT))
            if opens_ok:
                _state['stack'].append({
                    'char': c, 'level': len(_state['stack']) + 1, 'ref': ref,
                })
                _record(i, end, c, 'opener_reasonable', ref, snippet)
            else:
                _record(i, end, c, 'other_unusual', ref, snippet)
        elif role == u'close':
            if _state['stack']:
                opened = _state['stack'].pop()
                lvl = opened['level']
                pair = (opened['char'], c)
                lvl_dict = _level_usage.setdefault(lvl, {})
                lvl_dict[pair] = lvl_dict.get(pair, 0) + 1
                _record(i, end, c, 'closer_reasonable', ref, snippet)
            else:
                _record(i, end, c, 'closer_orphan', ref, snippet)
        elif role == u'midword':
            _record(i, end, c, 'midword_possible_apostrophe', ref, snippet)
        else:
            _record(i, end, c, 'other_unusual', ref, snippet)

    # Finish a still-open dash-quote at any paragraph boundary remaining
    # after the last quote/dash character match in this chapter.
    while bi < nb:
        _finish_open_dash()
        bi += 1


def checkChapter(reference, text, lastChapter):
    # A bug in our own logic must never reach checkAllChapters's exception
    # handler -- that handler mixes byte strings and unicode in a bare
    # print, which has been observed (KOG_U New Testament) to crash on
    # non-ASCII content and mask whatever the real, original exception was.
    # Catching it here, logging it ourselves (see _log_crash), and letting
    # the scan continue to the next chapter keeps this check's own bugs
    # from taking down the entire run and losing the actual error.
    try:
        _checkChapter_impl(reference, text, lastChapter)
    except Exception as e:
        book_num = reference.Book if reference is not None else None
        book_label = _book_label(book_num)
        cm = CHAPTER_RE.search(text) if text else None
        chapter_label = cm.group(1) if cm else u'?'
        _log_crash(book_label, chapter_label, e)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _fmt_char(c):
    if len(c) == 1:
        return u'{0} (U+{1:04X})'.format(_he(c), ord(c))
    return _he(c)


def _fmt_pair(open_c, close_label, n):
    # Descriptive labels (e.g. "(no closing dash)") get a separating space;
    # a real character pair is shown run together (e.g. "«»").
    sep = u' ' if close_label.startswith(u'(') else u''
    return u'{0}{1}{2} &times; {3}'.format(_he(open_c), sep, _he(close_label), n)


def _level_openers_and_closers(pairs):
    """Group a level's {(open, close): count} dict by opener, picking each
    opener's most frequent closer. Returns (openers, closers), positionally
    aligned lists -- e.g. (['«', '—'], ['»', '']), where an empty string
    means that opener has no explicit closer (e.g. a dash-quote, which
    finishes implicitly at the end of its paragraph)."""
    by_opener = {}
    for (o, cl), n in pairs.items():
        d = by_opener.setdefault(o, {})
        d[cl] = d.get(cl, 0) + n
    ranked = sorted(by_opener.items(), key=lambda kv: -sum(kv[1].values()))
    openers, closers = [], []
    for o, close_counts in ranked:
        dominant = max(close_counts.items(), key=lambda kv: kv[1])[0]
        openers.append(o)
        closers.append(u'' if dominant == _DASH_NO_CLOSER else dominant)
    return openers, closers


def _count_cell(count, bucket):
    """Renders a Section-1 summary-table count cell, highlighted (reusing
    the same .warn style as Section 2's mismatch rows) whenever the count is
    nonzero AND the bucket is an actual anomaly (_WARN_BUCKETS) -- normal-
    usage columns like opener/closer/continuer counts are always heavily
    nonzero and would swamp the highlight if included."""
    css_class = u' class="warn"' if (bucket in _WARN_BUCKETS and count) else u''
    return u'<td{0}>{1}</td>'.format(css_class, count)


def _examples_html(key, label=None):
    lst = _examples.get(key, [])
    if not lst:
        return u''
    rows = u''.join(
        u'<li>{0} &mdash; <code>{1}</code></li>'.format(_he(ref), _he(snippet))
        for ref, snippet in lst
    )
    heading = label if label else u'Examples'
    return u'<details><summary>{0} ({1} shown)</summary><ul>{2}</ul></details>'.format(
        _he(heading), len(lst), rows)


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Quotation Examiner &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.warn{background:#ffd0d0}')
    lines.append(u'code{white-space:pre-wrap}')
    lines.append(u'h2{margin-top:28px}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Quotation Examiner</h1>')
    lines.append(u'<p>Project: <b>{0}</b></p>'.format(_he(project_name)))

    # --- Section 1: character summary ---------------------------------
    lines.append(u'<h2>1. Character usage summary</h2>')
    buckets = [
        ('opener_reasonable', 'Opener'), ('closer_reasonable', 'Closer'),
        ('continuer_reasonable', 'Continuer'), ('continuer_suspicious', 'Continuer (suspicious)'),
        ('closer_orphan', 'Closer (no opener)'), ('midword_possible_apostrophe', 'Mid-word (poss. apostrophe)'),
        ('dash_dialogue', 'Dialogue dash (opener)'), ('dash_closing', 'Dialogue dash (explicit closer)'),
        ('other_unusual', 'Other/unusual'),
    ]
    lines.append(u'<table><tr><th>Character</th><th>Total</th>' +
                 u''.join(u'<th>{0}</th>'.format(label) for _key, label in buckets) + u'</tr>')
    for c in sorted(_stats.keys()):
        st = _stats[c]
        total = sum(st.values())
        lines.append(u'<tr><td>{0}</td><td>{1}</td>'.format(_fmt_char(c), total))
        for key, _label in buckets:
            lines.append(_count_cell(st.get(key, 0), key))
        lines.append(u'</tr>')
    lines.append(u'</table>')

    # --- Section 2: configured vs. actual -----------------------------
    lines.append(u'<h2>2. Configured quotation settings vs. actual usage found in text</h2>')
    _all_levels = sorted(set(_level_usage.keys()) | set(_configured_by_level.keys()))
    if not _all_levels:
        lines.append(u'<p><i>No quotation marks were found in the scanned text.</i></p>')
    else:
        if not _configured_levels:
            lines.append(u'<p><i>No Quotation settings found in Settings.xml for this project '
                          u'&mdash; showing actual usage only.</i></p>')
        else:
            lines.append(u'<p><i>&ldquo;Configured continuer&rdquo; is what this project\'s '
                          u'Settings.xml declares; the other columns show what was actually '
                          u'found while scanning the text. A mismatch does not necessarily mean '
                          u'an error &mdash; it means the text does not follow the configured '
                          u'setting.</i></p>')
        lines.append(u'<table><tr><th>Level</th><th>Openers found</th><th>Closes with</th>'
                      u'<th>Configured continuer</th><th>Matches configured pair?</th></tr>')
        for lvl in _all_levels:
            actual = _level_usage.get(lvl, {})
            openers, closers = _level_openers_and_closers(actual)
            openers_str = u'|'.join(_he(o) for o in openers) if openers else u'(none found)'
            closers_str = u'|'.join(_he(c) for c in closers)
            cfg = _configured_by_level.get(lvl)
            if cfg:
                continuer_str = _he(cfg['continuer']) if cfg['continuer'] else u'(none configured)'
                cfg_pair = (cfg['open'], cfg['close'])
                matches = bool(actual) and cfg_pair in actual
                css = u'' if (not actual or matches) else u' class="warn"'
                match_text = u'-' if not actual else (u'yes' if matches else u'no')
            else:
                continuer_str = u'(not configured)'
                css = u''
                match_text = u'n/a'
            lines.append(
                u'<tr{0}><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td></tr>'.format(
                    css, lvl, openers_str, closers_str, continuer_str, match_text))
        lines.append(u'</table>')
        lines.append(u'<p><i>When a level lists more than one opener, the continuer applies to '
                      u'whichever opener began the quotation, not to a specific one.</i></p>')

    # --- Section 3: unclosed / orphan quotes ----------------------------
    lines.append(u'<h2>3. Unclosed and orphaned quotation marks</h2>')
    if _unclosed:
        shown = _unclosed[:_max_examples]
        rows = u''.join(
            u'<li>{0} &mdash; opened with {1} at level {2}, ref {3}, never closed before end of book</li>'.format(
                _he(u['book']), _fmt_char(u['char']), u['level'], _he(u['opened_ref']))
            for u in shown)
        more = u'' if len(_unclosed) <= _max_examples else u'<p>+{0} more not shown.</p>'.format(
            len(_unclosed) - _max_examples)
        lines.append(u'<b>{0} unclosed quote(s) at end of book:</b><ul>{1}</ul>{2}'.format(
            len(_unclosed), rows, more))
    else:
        lines.append(u'<p>None found.</p>')
    orphan_any = False
    for c in sorted(_stats.keys()):
        html = _examples_html((c, 'closer_orphan'), u'{0} used as a closer with no matching opener'.format(_fmt_char(c)))
        if html:
            orphan_any = True
            lines.append(html)
    if not orphan_any:
        lines.append(u'<p>No orphaned closers found.</p>')

    # --- Section 4: continuers ------------------------------------------
    lines.append(u'<h2>4. Continuers (quote repeated at the start of a new paragraph/poetry line)</h2>')
    for c in sorted(_stats.keys()):
        html = _examples_html((c, 'continuer_reasonable'), u'{0} used as a reasonable continuer'.format(_fmt_char(c)))
        if html:
            lines.append(html)
    lines.append(u'<p><b>Suspicious continuers</b> &mdash; a closing-type character at the very start '
                  u'of a paragraph/poetry line with no quotation currently open:</p>')
    susp_any = False
    for c in sorted(_stats.keys()):
        html = _examples_html((c, 'continuer_suspicious'), u'{0} at paragraph start with nothing open'.format(_fmt_char(c)))
        if html:
            susp_any = True
            lines.append(html)
    if not susp_any:
        lines.append(u'<p>None found.</p>')

    # --- Section 5: unusual placements -----------------------------------
    lines.append(u'<h2>5. Unusual placements</h2>')
    unusual_any = False
    for c in sorted(_stats.keys()):
        html = _examples_html((c, 'other_unusual'), u'{0} in an unexpected position'.format(_fmt_char(c)))
        if html:
            unusual_any = True
            lines.append(html)
    if not unusual_any:
        lines.append(u'<p>No unusual placements found.</p>')

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    open_path = html_path.encode('mbcs') if isinstance(html_path, type(u'')) else html_path
    with open(open_path, 'wb') as f:
        f.write(html.encode('utf-8'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

checking.checkAllChapters(checkChapter)
_flush_unclosed(_state['prev_book'])

_directory = _project_directory()
if _directory:
    _html_path = os.path.join(_directory, u'QuotationExaminerReport.html')
    write_html_report(_html_path, Project)
    os.startfile(_html_path)
    sys.stdout.write(_paratext_list_safe(u'# Report written to {0}\n'.format(_html_path)))
    _total_chars = sum(sum(st.values()) for st in _stats.values())
    _total_unusual = sum(
        st.get('other_unusual', 0) + st.get('midword_possible_apostrophe', 0) +
        st.get('closer_orphan', 0) + st.get('continuer_suspicious', 0)
        for st in _stats.values())
    sys.stdout.write(_paratext_list_safe(
        u'# {0} quotation/dash characters scanned, {1} flagged for review, '
        u'{2} unclosed at end of book\n'.format(_total_chars, _total_unusual, len(_unclosed))))
else:
    sys.stdout.write(_paratext_list_safe(u'# Error: could not determine project directory; no report written.\n'))
