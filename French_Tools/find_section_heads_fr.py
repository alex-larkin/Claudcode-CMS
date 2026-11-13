# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import traceback
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
    SortAlphabetically
except NameError:
    SortAlphabetically = u'No'
_sort_alphabetically = _to_unicode(SortAlphabetically).strip().lower() == u'yes'

try:
    IncludeReferences
except NameError:
    IncludeReferences = u'No'
_include_references = _to_unicode(IncludeReferences).strip().lower() == u'yes'

try:
    FlagPunctuation
except NameError:
    FlagPunctuation = u'Yes'
_flag_punctuation = _to_unicode(FlagPunctuation).strip().lower() == u'yes'

try:
    PunctuationChars
except NameError:
    PunctuationChars = u'.?!'
PunctuationChars = _to_unicode(PunctuationChars)
_punct_chars = set(c for c in PunctuationChars if not c.isspace())

try:
    FlagFollowedByM
except NameError:
    FlagFollowedByM = u'Yes'
_flag_followed_by_m = _to_unicode(FlagFollowedByM).strip().lower() == u'yes'

try:
    ShowOnlyPunctuation
except NameError:
    ShowOnlyPunctuation = u'No'
_filter_punct = _to_unicode(ShowOnlyPunctuation).strip().lower() == u'yes'

try:
    ShowOnlyFollowedByM
except NameError:
    ShowOnlyFollowedByM = u'No'
_filter_m = _to_unicode(ShowOnlyFollowedByM).strip().lower() == u'yes'

# With both Yes, a heading with either problem is shown.
_filtering = _filter_punct or _filter_m


def _filter_label():
    if _filter_punct and _filter_m:
        return u'avec ponctuation ou suivis de \\m'
    if _filter_punct:
        return u'avec ponctuation'
    return u'suivis de \\m'

try:
    IgnoreFootnotesAndCrossRefs
except NameError:
    IgnoreFootnotesAndCrossRefs = u'Yes'
_ignore_notes = _to_unicode(IgnoreFootnotesAndCrossRefs).strip().lower() == u'yes'

try:
    FlagNonTitleCaps
except NameError:
    FlagNonTitleCaps = u'No'
_flag_non_title_caps = _to_unicode(FlagNonTitleCaps).strip().lower() == u'yes'

try:
    WordsToIgnore
except NameError:
    WordsToIgnore = u''
WordsToIgnore = _to_unicode(WordsToIgnore)
_ignore_words = frozenset(
    unicodedata.normalize(u'NFC', w.strip())
    for w in WordsToIgnore.split(u',') if w.strip())
_ignore_words_lower = frozenset(w.lower() for w in _ignore_words)

try:
    PrefixesToIgnore
except NameError:
    PrefixesToIgnore = u''
PrefixesToIgnore = _to_unicode(PrefixesToIgnore)

try:
    SuffixesToIgnore
except NameError:
    SuffixesToIgnore = u''
SuffixesToIgnore = _to_unicode(SuffixesToIgnore)

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (find_titles/Find_Titles.py, find_footnotes/find_footnotes.py).
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
    return u'Livre {0}'.format(book_num) if book_num is not None else u'?'


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


_WS_RUN_RE = re.compile(ur'[ \t]+', re.UNICODE)


def _collapse_ws(s):
    return _WS_RUN_RE.sub(u' ', s.replace(u'\r', u'').replace(u'\n', u' '))


def _sort_fold(s):
    # Diacritic-insensitive sort key: NFD-decompose so an accented letter
    # becomes base letter + separate combining mark, then drop every
    # combining-mark character (categories Mn/Mc/Me) so accents and tone
    # marks are ignored for ordering (same approach as find_titles/
    # find_footnotes). The text actually written to the HTML is untouched;
    # this is only ever used as a sort key.
    decomposed = unicodedata.normalize(u'NFD', s)
    return u''.join(
        c for c in decomposed
        if unicodedata.category(c) not in (u'Mn', u'Mc', u'Me')
    ).lower()


def _to_utf8_bytes(s):
    # checking.py's own outputError2 builds the results-list line by
    # concatenating byte strings, so passing it a genuine unicode msg forces
    # an implicit ASCII encode that fails on any non-ASCII character.
    if isinstance(s, type(u'')):
        return s.encode('utf-8')
    return s


# ---------------------------------------------------------------------------
# Project directory
# ---------------------------------------------------------------------------

def _project_directory():
    scr = getattr(checking, 'scr', None)
    d = getattr(scr, 'Directory', None) if scr is not None else None
    if not d:
        return None
    if isinstance(d, bytes):
        d = d.decode('mbcs')
    return d


def _open_path(path):
    return path.encode('mbcs') if isinstance(path, type(u'')) else path


def _log_crash(label, exc):
    directory = _directory if '_directory' in globals() else None
    directory = directory or os.environ.get('TEMP') or os.environ.get('TMP')
    if not directory:
        return
    try:
        tb_text = traceback.format_exc()
        if isinstance(tb_text, str):
            tb_text = tb_text.decode('utf-8', 'replace')
    except Exception:
        try:
            tb_text = unicode(repr(exc))
        except Exception:
            tb_text = u'<unformattable exception>'
    log_path = os.path.join(directory, u'FindSectionHeadsDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Marker scanning
# ---------------------------------------------------------------------------

# \s / \s1-\s4 (bare \s and up to 4 numbered levels are the real USFM marker
# set -- \b excludes \sp/\sr/\sig, which start with 's' but are not section
# headings). \r is the parallel-passage reference marker, always bare (no
# digit variants), distinct from \mr/\sr which do not start immediately
# after a backslash with 'r'.
SECTION_RE = re.compile(ur'^\\(s[1-4]?)\b[ \t]*([^\r\n]*)', re.UNICODE | re.MULTILINE)
REF_RE = re.compile(ur'^\\r\b[ \t]*([^\r\n]*)', re.UNICODE | re.MULTILINE)

# Generic USFM marker token, used to find whatever comes next in the
# stream regardless of kind (same idiom as marker_space.py/
# quotation_matcher.py's USFM_MARKER_RE).
USFM_MARKER_RE = re.compile(ur'\\[a-zA-Z][a-zA-Z0-9]*\*?', re.UNICODE)

# Whitespace/newlines only -- used to find the position immediately after
# an \s match, skipping blank lines but nothing else, so an \r is only
# treated as "paired" when it is truly the next marker line, not merely
# the next \r anywhere later in the chapter.
_WS_ONLY_RE = re.compile(ur'[ \t\r\n]*', re.UNICODE)

CHAPTER_RE = re.compile(ur'\\c\s+(\d+)', re.UNICODE)
VERSE_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)\s*', re.UNICODE)

# \f...\f* footnotes and \x...\x* cross-references embedded within a \s#
# heading -- \fig is intentionally NOT included, only \f/\x were requested.
FOOTNOTE_RE = re.compile(ur'\\f\s.*?\\f\*', re.UNICODE)
XREF_RE = re.compile(ur'\\x\s.*?\\x\*', re.UNICODE)
INLINE_RE = re.compile(ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*', re.UNICODE)


def _segment_display_text(raw_text):
    return _collapse_ws(INLINE_RE.sub(u' ', raw_text)).strip()


def _verse_positions(text):
    return [(m.end(), m.group(1)) for m in VERSE_RE.finditer(text)]


def _verse_at(positions, offset):
    label = None
    for start, v in positions:
        if start <= offset:
            label = v
        else:
            break
    return label if label is not None else u'0'


# ---------------------------------------------------------------------------
# Non-title capital detection (FlagNonTitleCaps) -- ported from
# mid_sentence_capital.py's WordsToIgnore/PrefixesToIgnore/SuffixesToIgnore
# and TermRenderings.xml machinery. Deliberately NOT ported:
# FinalPunctuation/IgnoreCapAfterQuote/QuoteOpeningChars (cross-verse and
# dialogue-opening state -- a single already-isolated \s heading has
# neither), IgnoreStyles/IgnoreParaStyles (not applicable to one isolated
# heading), and MidWordPunctuation (no option exposed here -- the joiner is
# hardcoded to mid_sentence_capital.py's own default of '-').
# ---------------------------------------------------------------------------

def _parse_affix_groups(raw):
    # Each space-separated token is either a plain affix, or a '/'-separated
    # group of interchangeable variants (e.g. "ion/iones") for languages
    # where attaching an affix triggers a stem-final alternation.
    groups = []
    for tok in raw.split():
        variants = [v.lower() for v in tok.split(u'/') if v]
        if variants:
            groups.append(variants)
    return groups

_prefix_groups = _parse_affix_groups(PrefixesToIgnore)
_suffix_groups = _parse_affix_groups(SuffixesToIgnore)

# Word char: \w or a combining diacritical mark (U+0300-U+036F), so a word
# written with a decomposed tone/accent mark (base letter + separate
# combining mark) is extracted whole rather than truncated right before the
# mark. Mid-word joiner hardcoded to '-' (no MidWordPunctuation option here).
_WORD_CHAR = u'(?:\\w|[\\u0300-\\u036f])'
_WORD_RE = re.compile(_WORD_CHAR + u'+(?:-' + _WORD_CHAR + u'+)*', re.UNICODE)

# A letter, combining marks included: Paratext runs these checks under IronPython,
# whose .NET \w covers the combining marks (Mn, U+0300-U+036F among them). The
# old form (?:[^\W\d_]|[\u0300-\u036f]) matched each mark both ways, so a word
# with many stacked marks made a failing wildcard match take exponential time.
_WORD_CHAR_NO_DIGIT = u'[^\\W\\d_]'


# Regex metacharacters in a TermRenderings word are matched literally: only the
# '*' at either end is a wildcard. Unescaped, a rendering such as '(a+)+b*' could
# freeze the check, and 'Sant[o*' stopped it with a pattern error. Non-ASCII
# letters are not backslashed (IronPython's .NET engine rejects such escapes).
def _re_literal(s):
    return re.sub(u'([\\\\.^$|?*+()\\[\\]{}])', u'\\\\\\1', s)

def _build_word_spec(word):
    has_prefix_wild = word.startswith(u'*')
    has_suffix_wild = word.endswith(u'*')
    root_word = word.strip(u'*')
    if not root_word:
        return None
    if has_prefix_wild or has_suffix_wild:
        prefix_pat = _WORD_CHAR_NO_DIGIT + u'*' if has_prefix_wild else u''
        suffix_pat = _WORD_CHAR_NO_DIGIT + u'*' if has_suffix_wild else u''
        return re.compile(
            u'\\A' + prefix_pat + _re_literal(root_word) + suffix_pat + u'\\Z', re.UNICODE)
    return root_word


def _load_cap_renderings(path):
    phrases = []
    open_path = path.encode('mbcs') if isinstance(path, type(u'')) else path
    with open(open_path, 'rb') as f:
        data = f.read()
    root = ET.fromstring(data)
    for tr in root.iter(u'TermRendering'):
        r_elem = tr.find(u'Renderings')
        if r_elem is None or not r_elem.text:
            continue
        for token in r_elem.text.split(u'||'):
            at = token.find(u'@')
            if at >= 0:
                token = token[:at]
            words = token.split()
            if not words:
                continue
            first_root = words[0].strip(u'*')
            if not first_root or unicodedata.category(first_root[0]) != u'Lu':
                continue
            specs = []
            for word in words:
                spec = _build_word_spec(word)
                if spec is None:
                    specs = None
                    break
                specs.append(spec)
            if specs:
                phrases.append(specs)
    return phrases


def _find_project_term_renderings(directory):
    # Reuses this file's own already-resolved project directory rather than
    # re-deriving it from checking.scr a second time.
    if not directory:
        return None
    p = os.path.join(directory, u'TermRenderings.xml')
    return p if os.path.isfile(p) else None


# Gap allowed between consecutive words of a multi-word TermRenderings
# phrase: whitespace interleaved with USFM character markers (e.g.
# \bd Word\bd* Word2). Uses [a-zA-Z] rather than mid_sentence_capital.py's
# [a-z]-only class to match this file's own USFM_MARKER_RE convention.
_PHRASE_GAP_RE = re.compile(
    ur'(?:[ \t\r\n]+|\\[a-zA-Z][a-zA-Z0-9]*\*?)*', re.UNICODE)


def _extract_word_seq(text, start, max_words):
    words = []
    pos = start
    for i in range(max_words):
        if i > 0:
            gap_m = _PHRASE_GAP_RE.match(text, pos)
            new_pos = gap_m.end() if gap_m else pos
            if new_pos == pos:
                break
            pos = new_pos
        m = _WORD_RE.match(text, pos)
        if not m:
            break
        words.append(text[pos:m.end()])
        pos = m.end()
    return words


def _index_cap_phrases(phrases):
    by_first_word = {}
    wildcard_first = []
    for phrase in phrases:
        first = phrase[0]
        if isinstance(first, type(u'')):
            by_first_word.setdefault(first, []).append(phrase)
        else:
            wildcard_first.append(phrase)
    return by_first_word, wildcard_first


def _index_single_word_terms(phrases):
    exact_lower = set()
    wildcards = []
    for phrase in phrases:
        if len(phrase) != 1:
            continue
        spec = phrase[0]
        if isinstance(spec, type(u'')):
            exact_lower.add(spec.lower())
        else:
            wildcards.append(spec)
    return frozenset(exact_lower), wildcards


def _spec_matches(spec, word):
    if isinstance(spec, type(u'')):
        return word == spec
    return bool(spec.match(word))


def _phrase_matches_at(text, start, phrase):
    words = _extract_word_seq(text, start, len(phrase))
    if len(words) != len(phrase):
        return False
    return all(_spec_matches(spec, words[i]) for i, spec in enumerate(phrase))


def _match_cap_phrase(text, start):
    m = _WORD_RE.match(text, start)
    if not m:
        return False
    first_word = text[start:m.end()]
    for phrase in _cap_phrases_by_first_word.get(first_word, ()):
        if len(phrase) == 1 or _phrase_matches_at(text, start, phrase):
            return True
    for phrase in _cap_phrases_wildcard_first:
        if _phrase_matches_at(text, start, phrase):
            return True
    return False


def _is_recognized_root(root):
    root_nfc = unicodedata.normalize('NFC', root)
    root_lower = root_nfc.lower()
    if root_lower in _ignore_words_lower:
        return True
    if root_lower in _cap_single_word_exact_lower:
        return True
    for spec in _cap_single_word_wildcards:
        if _spec_matches(spec, root_nfc):
            return True
    return False


def _word_has_affix(word_str):
    word_lower = word_str.lower()
    for group in _prefix_groups:
        for i, variant in enumerate(group):
            pl = len(variant)
            if len(word_str) <= pl or word_lower[:pl] != variant:
                continue
            if len(group) == 1:
                if _is_recognized_root(word_str[pl:]):
                    return True
            else:
                rest = word_str[pl:]
                for j, other in enumerate(group):
                    if j != i and _is_recognized_root(other + rest):
                        return True
    for group in _suffix_groups:
        for i, variant in enumerate(group):
            sl = len(variant)
            if len(word_str) <= sl or word_lower[-sl:] != variant:
                continue
            if len(group) == 1:
                if _is_recognized_root(word_str[:-sl]):
                    return True
            else:
                stem = word_str[:-sl]
                for j, other in enumerate(group):
                    if j != i and _is_recognized_root(stem + other):
                        return True
    return False


def _is_ignored_at(text, pos, word_str):
    if _match_cap_phrase(text, pos):
        return True
    if unicodedata.normalize('NFC', word_str) in _ignore_words:
        return True
    return _word_has_affix(word_str)


def _scan_non_title_caps(s_plain_parts):
    """s_plain_parts: list of per-segment plain (notes-stripped, whitespace-
    collapsed) strings, in the same filtered order as s_segments. Returns a
    list of (seg_index, local_word_index, word_str) for every word other
    than the very first word of the WHOLE combined row that starts with an
    uppercase letter and is not ignored. local_word_index is a 0-based count
    of _WORD_RE matches within that segment's own USFM-marker-blanked text,
    used later by _s_cell to find and highlight the exact same word
    regardless of IgnoreFootnotesAndCrossRefs's display mode."""
    flagged = []
    seen_first_word = False
    for seg_i, plain in enumerate(s_plain_parts):
        if not plain:
            continue
        scan = USFM_MARKER_RE.sub(lambda m: u' ' * len(m.group(0)), plain)
        for word_i, wm in enumerate(_WORD_RE.finditer(scan)):
            if not seen_first_word:
                seen_first_word = True
                continue
            word_str = scan[wm.start():wm.end()]
            if unicodedata.category(word_str[0]) != u'Lu':
                continue
            if _is_ignored_at(scan, wm.start(), word_str):
                continue
            flagged.append((seg_i, word_i, word_str))
    return flagged


def _group_section_matches(text, matches):
    # Merge SECTION_RE matches that are text-adjacent (nothing but
    # whitespace/newlines between one match's end and the next match's
    # start) into groups, each becoming one report row -- e.g. a \s3/\s2/\s1
    # run with no intervening verse content, in document order, same
    # combination rationale as find_titles/Find_Titles.py's mt_parts. A \r
    # (or any other marker) between two \s# matches is non-whitespace, so it
    # naturally breaks this probe -- a \r can never end up straddling the
    # middle of a group.
    groups = []
    i, n = 0, len(matches)
    while i < n:
        group = [matches[i]]
        i += 1
        while i < n:
            wm = _WS_ONLY_RE.match(text, group[-1].end())
            probe_pos = wm.end() if wm is not None else group[-1].end()
            if probe_pos != matches[i].start():
                break
            group.append(matches[i])
            i += 1
        groups.append(group)
    return groups


_report_rows = []  # dicts: book_label, ref, s_segments, s_plain, r_text, final_punct, ends_with_punct, followed_by_m, seq
_seen_books = set()
_total_s = 0
_total_shown = 0
_total_r_standalone = 0
_total_punct_flagged = 0
_total_ends_with_punct = 0
_total_m_flagged = 0
_total_non_title_caps = 0
_kind_counts = {u's': 0, u's1': 0, u's2': 0, u's3': 0, u's4': 0}
_footnote_row_count = 0
_xref_row_count = 0


def _checkChapter_impl(reference, text, lastChapter):
    global _total_s, _total_shown, _total_r_standalone, _total_punct_flagged, _total_ends_with_punct, _total_m_flagged
    global _footnote_row_count, _xref_row_count, _total_non_title_caps
    book_num = reference.Book if reference is not None else None
    if book_num is None or book_num < 1 or book_num >= len(BOOK_NAMES):
        return
    _seen_books.add(book_num)
    book_label = _book_label(book_num)

    if isinstance(text, str):
        # On this Paratext installation (very likely IronPython under the
        # hood), `text` can satisfy isinstance(text, str) while already
        # being proper Unicode text -- calling .decode('utf-8') on it makes
        # IronPython implicitly re-encode to ASCII first, raising
        # UnicodeEncodeError on any non-ASCII character. If decode() fails
        # either way, text is already usable as-is.
        try:
            text = text.decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

    cm = CHAPTER_RE.search(text)
    chapter_label = cm.group(1) if cm else u'?'
    verse_positions = _verse_positions(text)

    def ref_at(offset):
        v = _verse_at(verse_positions, offset)
        return u'{0} {1}:{2}'.format(book_label, chapter_label, v)

    paired_r_starts = set()

    matches = list(SECTION_RE.finditer(text))
    for group in _group_section_matches(text, matches):
        raw_segments = [(m.group(1), _collapse_ws(m.group(2)).strip()) for m in group]
        for kind, raw in raw_segments:
            _kind_counts[kind] += 1
        if any(FOOTNOTE_RE.search(raw) for _kind, raw in raw_segments):
            _footnote_row_count += 1
        if any(XREF_RE.search(raw) for _kind, raw in raw_segments):
            _xref_row_count += 1
        plain_segments = [(kind, _segment_display_text(raw)) for kind, raw in raw_segments]
        # Empty-text segments (e.g. a bare "\s3" line with nothing after it)
        # are dropped from what's displayed/combined, same filter
        # find_titles/Find_Titles.py applies to empty \mt vals -- the raw
        # match itself stays in `group`/`raw_segments` regardless, since
        # grouping/anchor/r-pairing must not depend on whether text was
        # typed after the marker.
        s_segments = [(kind, raw) for (kind, raw), (_, plain) in zip(raw_segments, plain_segments) if plain]
        s_plain_parts = [plain for _, plain in plain_segments if plain]
        s_plain = u' '.join(s_plain_parts)

        last = group[-1]
        unit_end = last.end()
        r_text = None

        wm = _WS_ONLY_RE.match(text, last.end())
        probe_pos = wm.end() if wm is not None else last.end()
        rm = REF_RE.match(text, probe_pos)
        if rm is not None:
            r_text = _collapse_ws(rm.group(1)).strip()
            unit_end = rm.end()
            paired_r_starts.add(rm.start())

        # Always computed (not gated by FlagFollowedByM) so this fact is
        # summarized in every report regardless of whether the option-
        # controlled \m column is displayed -- see write_html_report.
        nxt = USFM_MARKER_RE.search(text, unit_end)
        followed_by_m = bool(nxt and nxt.group(0) == u'\\m')
        if followed_by_m:
            _total_m_flagged += 1

        # Always computed, distinct from the opt-in FlagPunctuation check
        # below (which flags punctuation anywhere in the text) -- this one
        # specifically checks whether the heading ends with sentence-final
        # punctuation, using the same PunctuationChars set.
        ends_with_punct = bool(s_plain) and s_plain[-1] in _punct_chars
        if ends_with_punct:
            _total_ends_with_punct += 1

        has_punct = any(ch in _punct_chars for ch in s_plain)
        final_punct = None
        if _flag_punctuation:
            final_punct = has_punct
            if final_punct:
                _total_punct_flagged += 1

        non_title_caps = None
        if _flag_non_title_caps:
            non_title_caps = _scan_non_title_caps(s_plain_parts)
            if non_title_caps:
                _total_non_title_caps += 1

        _total_s += 1
        # The Show only options hide the other headings from the report and
        # the results list; every counter above still includes them.
        if not (not _filtering or (_filter_punct and has_punct)
                or (_filter_m and followed_by_m)):
            continue
        _total_shown += 1
        if final_punct is None and _filter_punct:
            final_punct = has_punct
        ref = ref_at(group[0].start())
        _report_rows.append({
            'book_label': book_label, 'ref': ref,
            's_segments': s_segments, 's_plain': s_plain, 'r_text': r_text,
            'final_punct': final_punct, 'ends_with_punct': ends_with_punct,
            'followed_by_m': followed_by_m,
            'non_title_caps': non_title_caps,
            'seq': len(_report_rows),
        })

        # Anchored zero-width (rather than spanning to unit_end) because
        # when a paired \r sits on the next physical line, the auto-sliced
        # TEXT column would otherwise include the raw \r\n between the \s
        # and \r lines, which Paratext's list view renders as literal
        # control-character escape text -- same problem and same fix as
        # find_titles/Find_Titles.py's multi-\mt-segment case. The message
        # always uses the notes-stripped plain_segments, never the raw
        # \f/\x markup, since the results list is plain text either way.
        head = u' '.join(u'\\{0} {1}'.format(kind, txt) for kind, txt in plain_segments if txt)
        if not head:
            head = u' '.join(u'\\{0}'.format(kind) for kind, _r in raw_segments)
        msg_parts = [head]
        if r_text is not None:
            msg_parts.append(u'\\r {0}'.format(r_text) if r_text else u'\\r')
        if final_punct:
            msg_parts.append(u'[ponctuation]')
        if followed_by_m:
            msg_parts.append(u'[suivi de \\m]')
        if non_title_caps:
            seen_words = set()
            flagged_words = []
            for _seg_i, _word_i, w in non_title_caps:
                if w not in seen_words:
                    seen_words.add(w)
                    flagged_words.append(w)
            msg_parts.append(u'[majuscule hors titre : {0}]'.format(u', '.join(flagged_words)))
        msg = u'  '.join(msg_parts)
        try:
            checking.outputError(group[0].start(), group[0].start(), _to_utf8_bytes(msg))
        except Exception as e:
            _log_crash(u'{0} outputError'.format(ref), e)

    if _include_references:
        for rm in REF_RE.finditer(text):
            if rm.start() in paired_r_starts:
                continue
            _total_r_standalone += 1
            # A standalone \r has no heading to show, so the Show only
            # options leave it out (it is still counted in the summary).
            if _filtering:
                continue
            r_text = _collapse_ws(rm.group(1)).strip()
            ref = ref_at(rm.start())
            _report_rows.append({
                'book_label': book_label, 'ref': ref,
                's_segments': None, 's_plain': None, 'r_text': r_text,
                'final_punct': None, 'ends_with_punct': None, 'followed_by_m': None,
                'non_title_caps': None,
                'seq': len(_report_rows),
            })
            msg = u'\\r {0}'.format(r_text) if r_text else u'\\r'
            try:
                checking.outputError(rm.start(), rm.start(), _to_utf8_bytes(msg))
            except Exception as e:
                _log_crash(u'{0} outputError'.format(ref), e)


def checkChapter(reference, text, lastChapter):
    try:
        _checkChapter_impl(reference, text, lastChapter)
    except Exception as e:
        book_num = reference.Book if reference is not None else None
        _log_crash(_book_label(book_num), e)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

checking.setupCheck()

_directory = _project_directory()
_links_on = _ptx_goto is not None and _ptx_goto.enabled(_directory)

if _flag_non_title_caps:
    _tr_path = _find_project_term_renderings(_directory)
    try:
        _cap_phrases = _load_cap_renderings(_tr_path) if _tr_path else []
    except Exception as e:
        _log_crash(u'_load_cap_renderings', e)
        _cap_phrases = []
else:
    _cap_phrases = []
_cap_phrases_by_first_word, _cap_phrases_wildcard_first = _index_cap_phrases(_cap_phrases)
_cap_single_word_exact_lower, _cap_single_word_wildcards = _index_single_word_terms(_cap_phrases)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_CHECK_MARK = unichr(0x2713)

# Hardcoded per-level styling (not read from the project's usfm.sty/
# custom.sty -- confirmed with the user that this should be fixed, not
# stylesheet-driven). \s4 isn't specified by the user; defaulting to plain
# like \s2.
_S_LEVEL_CSS = {
    u's':  u'font-weight:bold',
    u's1': u'font-weight:bold',
    u's2': u'',
    u's3': u'font-style:italic',
    u's4': u'',
}


def _split_inline_notes(raw_text):
    parts, pos = [], 0
    for nm in INLINE_RE.finditer(raw_text):
        if nm.start() > pos:
            parts.append((u'text', raw_text[pos:nm.start()]))
        parts.append((u'note', nm.group(0)))
        pos = nm.end()
    if pos < len(raw_text):
        parts.append((u'text', raw_text[pos:]))
    return parts


_NON_TITLE_CAP_CSS = u'color:#c00;text-decoration:underline'


def _s_cell(s_segments, flagged=None):
    if not s_segments:
        return u'<span class="missing">&#8212;</span>'
    flagged_by_segment = {}
    if flagged:
        for seg_i, word_i, _w in flagged:
            flagged_by_segment.setdefault(seg_i, set()).add(word_i)
    parts = []
    for seg_i, (kind, raw_text) in enumerate(s_segments):
        css = _S_LEVEL_CSS.get(kind, u'')
        style_attr = u' style="{0}"'.format(css) if css else u''
        seg_flagged = flagged_by_segment.get(seg_i)
        word_count = [0]  # mutable cell threaded across chunks (no nonlocal in Python 2)

        def render_chunk(chunk_text):
            if not seg_flagged:
                return _he(chunk_text)
            # Blank USFM markers on a local copy purely to find correct word
            # boundaries/indices -- slice/escape from the ORIGINAL chunk_text
            # so any un-stripped marker text still renders exactly as it
            # already does today (this feature doesn't change that).
            blanked = USFM_MARKER_RE.sub(lambda m: u' ' * len(m.group(0)), chunk_text)
            out, pos = [], 0
            for wm in _WORD_RE.finditer(blanked):
                idx = word_count[0]
                word_count[0] += 1
                if idx in seg_flagged:
                    out.append(_he(chunk_text[pos:wm.start()]))
                    out.append(u'<span style="{0}">{1}</span>'.format(
                        _NON_TITLE_CAP_CSS, _he(chunk_text[wm.start():wm.end()])))
                    pos = wm.end()
            out.append(_he(chunk_text[pos:]))
            return u''.join(out)

        if _ignore_notes:
            inner = render_chunk(_segment_display_text(raw_text))
        else:
            chunks = []
            for ptype, chunk in _split_inline_notes(raw_text):
                if ptype == u'note':
                    chunks.append(u'<span style="font-size:smaller">{0}</span>'.format(_he(chunk)))
                else:
                    chunks.append(render_chunk(chunk))
            inner = u''.join(chunks)
        parts.append(u'<span{0}>{1}</span>'.format(style_attr, inner))
    return u' '.join(parts)


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Rapport des titres de section &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.missing{color:#999;font-style:italic}')
    lines.append(u'.check{text-align:center}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Rapport des titres de section</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html('fr'))
    lines.append(u'<p>Projet : <b>{0}</b></p>'.format(_he(project_name)))

    lines.append(u'<p>Marqueurs de titre de section trouvés :</p>')
    lines.append(u'<ul>')
    for kind in (u's', u's1', u's2', u's3', u's4'):
        lines.append(u'<li>\\{0} : {1}</li>'.format(kind, _kind_counts[kind]))
    lines.append(u'</ul>')
    lines.append(u'<p>{0} titre(s) de section contien(nen)t des notes de bas de page (\\f...\\f*) ; '
                  u'{1} titre(s) de section contien(nen)t des renvois (\\x...\\x*).</p>'.format(
        _footnote_row_count, _xref_row_count))

    summary_parts = [
        u'{0} livre(s) examiné(s)'.format(len(_seen_books)),
        u'{0} titre(s) de section trouvé(s)'.format(_total_s),
    ]
    if _include_references:
        summary_parts.append(u'{0} référence(s) \\r isolée(s)'.format(_total_r_standalone))
    # Always shown, regardless of the FlagPunctuation/FlagFollowedByM option
    # states, so these two facts are never hidden by a toggle the user
    # forgot to enable.
    summary_parts.append(u'{0} titre(s) de section se termine(nt) par une ponctuation'.format(_total_ends_with_punct))
    summary_parts.append(u'{0} titre(s) de section suivi(s) de \\m'.format(_total_m_flagged))
    if _flag_punctuation:
        summary_parts.append(u'{0} signalé(s) pour une ponctuation n’importe où dans le texte'.format(_total_punct_flagged))
    if _flag_non_title_caps:
        summary_parts.append(u'{0} titre(s) de section contien(nen)t une majuscule initiale hors titre'.format(_total_non_title_caps))
    lines.append(u'<p>{0}.</p>'.format(u', '.join(summary_parts)))
    if _filtering:
        lines.append(u'<p><b>Seuls les titres de section {0} sont montrés : {1} sur {2}.</b></p>'.format(
            _he(_filter_label()), _total_shown, _total_s))

    if not _report_rows:
        if _filtering and _total_s:
            lines.append(u'<p><i>Aucun titre de section ne correspond aux options Montrer seulement.</i></p>')
        else:
            lines.append(u'<p><i>Aucun titre de section n’a été trouvé.</i></p>')
    else:
        if _sort_alphabetically:
            def _sort_key(row):
                if not row['s_plain']:
                    return (1, u'', row['seq'])
                return (0, _sort_fold(row['s_plain']), row['seq'])
            ordered = sorted(_report_rows, key=_sort_key)
            sort_label = u'texte \\s (ordre alphabétique)'
        else:
            ordered = sorted(_report_rows, key=lambda r: r['seq'])
            sort_label = u'ordre canonique'
        lines.append(u'<p>Trié par {0}.</p>'.format(sort_label))

        # A column that a Show only option filters on is always shown, so each row
        # shows why it is listed.
        show_punct_col = _flag_punctuation or _filter_punct
        show_m_col = _flag_followed_by_m or _filter_m
        headers = [u'Livre', u'Référence', u'\\s']
        if _include_references:
            headers.append(u'\\r')
        if show_punct_col:
            headers.append(u'Ponctuation')
        if show_m_col:
            headers.append(u'\\m')
        if _flag_non_title_caps:
            headers.append(u'Majuscule hors titre')
        lines.append(u'<table><tr>' + u''.join(
            u'<th>{0}</th>'.format(_he(h)) for h in headers) + u'</tr>')

        for row in ordered:
            cells = [
                u'<td><b>{0}</b></td>'.format(_he(row['book_label'])),
                u'<td>{0}</td>'.format(_ref_link(_he(row['ref']), _goto(row['ref']))),
            ]
            cells.append(u'<td>{0}</td>'.format(_s_cell(row['s_segments'], row['non_title_caps'])))
            if _include_references:
                cells.append(u'<td>{0}</td>'.format(_he(row['r_text']) if row['r_text'] else u''))
            if show_punct_col:
                cells.append(u'<td class="check">{0}</td>'.format(
                    _CHECK_MARK if row['final_punct'] else u''))
            if show_m_col:
                cells.append(u'<td class="check">{0}</td>'.format(
                    _CHECK_MARK if row['followed_by_m'] else u''))
            if _flag_non_title_caps:
                cells.append(u'<td class="check">{0}</td>'.format(
                    _CHECK_MARK if row['non_title_caps'] else u''))
            lines.append(u'<tr>' + u''.join(cells) + u'</tr>')
        lines.append(u'</table>')

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

checking.checkAllChapters(checkChapter)

if _directory:
    _html_path = os.path.join(_directory, u'RapportTitresSection.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(_to_utf8_bytes(u'# Rapport enregistre dans {0}\n'.format(_html_path)))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(_to_utf8_bytes(u'# Erreur lors de l\'ecriture du rapport HTML ; voir FindSectionHeadsDebug.log\n'))
    sys.stdout.write(_to_utf8_bytes(u'# {0} livre(s) examine(s), {1} titre(s) de section trouve(s)\n'.format(
        len(_seen_books), _total_s)))
    if _filtering:
        sys.stdout.write(_to_utf8_bytes(u'# {0} titre(s) de section montre(s) : seulement ceux {1}\n'.format(
            _total_shown, _filter_label())))
else:
    sys.stdout.write(_to_utf8_bytes(u'# Erreur : impossible de determiner le dossier du projet ; aucun rapport ecrit.\n'))
