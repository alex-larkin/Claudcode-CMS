# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import traceback
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

def _book_goto(code):
    return _ptx_goto.book_target(code) if _links_on else None

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
    CompareToc1ToMt
except NameError:
    CompareToc1ToMt = u'Yes'
_compare_toc1_to_mt = _to_unicode(CompareToc1ToMt).strip().lower() == u'yes'

try:
    CompareToc2ToH
except NameError:
    CompareToc2ToH = u'Yes'
_compare_toc2_to_h = _to_unicode(CompareToc2ToH).strip().lower() == u'yes'

try:
    CompareToc1ToBookNames
except NameError:
    CompareToc1ToBookNames = u'Yes'
_compare_toc1_to_booknames = _to_unicode(CompareToc1ToBookNames).strip().lower() == u'yes'

try:
    CompareToc2ToBookNames
except NameError:
    CompareToc2ToBookNames = u'Yes'
_compare_toc2_to_booknames = _to_unicode(CompareToc2ToBookNames).strip().lower() == u'yes'

try:
    IgnoreCapitalizationOnly
except NameError:
    IgnoreCapitalizationOnly = u'No'
_ignore_capitalization_only = _to_unicode(IgnoreCapitalizationOnly).strip().lower() == u'yes'

try:
    IgnoreMt1
except NameError:
    IgnoreMt1 = u'No'
_ignore_mt1 = _to_unicode(IgnoreMt1).strip().lower() == u'yes'

try:
    IgnoreMt2
except NameError:
    IgnoreMt2 = u'No'
_ignore_mt2 = _to_unicode(IgnoreMt2).strip().lower() == u'yes'

try:
    IgnoreMt3
except NameError:
    IgnoreMt3 = u'No'
_ignore_mt3 = _to_unicode(IgnoreMt3).strip().lower() == u'yes'

try:
    CheckNumberedBooks
except NameError:
    CheckNumberedBooks = u'Yes'
_check_numbered = _to_unicode(CheckNumberedBooks).strip().lower() == u'yes'

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

# Which \mt#-level markers to exclude entirely when combining \mt text for
# comparison against \toc1 -- e.g. a project where \mt1 holds a short label
# rather than title wording, and the real title text is only in \mt2/\mt3.
# Bare \mt (no digit) has no ignore option -- not requested.
_IGNORED_MT_KINDS = frozenset(
    ([u'mt1'] if _ignore_mt1 else []) +
    ([u'mt2'] if _ignore_mt2 else []) +
    ([u'mt3'] if _ignore_mt3 else []))

# A marker is only worth checking for/reporting as "missing" if at least one
# enabled comparison actually needs it -- \toc1 and \toc2 each feed two
# comparisons, so this avoids reporting the same missing marker twice.
_need_toc1 = _compare_toc1_to_mt or _compare_toc1_to_booknames
_need_toc2 = _compare_toc2_to_h or _compare_toc2_to_booknames
_need_h = _compare_toc2_to_h
_need_mt = _compare_toc1_to_mt
_need_booknames = _compare_toc1_to_booknames or _compare_toc2_to_booknames

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (find_footnotes.py, Find_caption.py, quotation_examiner.py).
# Peripheral matter (FRT, BAK, OTH, INT, CNC, GLO, and the numbered XXA-XXG
# files) is out of scope for this check: those files can contain several
# \h/\toc2/\mt groups per file (one per section), so the one-header-per-book
# model below does not apply to them.
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


_WS_RUN_RE = re.compile(ur'[ \t]+', re.UNICODE)


def _collapse_ws(s):
    return _WS_RUN_RE.sub(u' ', s.replace(u'\r', u'').replace(u'\n', u' '))


_SOFT_BREAK_RE = re.compile(ur'//')


def _strip_soft_breaks(s):
    # Some projects use a literal // inside \toc1, \mt, or a BookNames.xml
    # long/short name as a formatting device forcing a soft line break --
    # it is not part of the title's actual wording, so it must be stripped
    # (as a space, so words don't get glued together -- any space already
    # around // collapses into that same single space) before comparing,
    # not just before Capitalization/Spelling classification -- otherwise
    # every book using this convention would show a false-positive mismatch.
    return _collapse_ws(_SOFT_BREAK_RE.sub(u' ', s)).strip()


def _levenshtein(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[lb]


def _capitalization_only(a, b):
    return a != b and a.lower() == b.lower()


_SPELLING_MAX_RATIO = 0.3


def _spelling_difference(a, b):
    # Mutually exclusive with _capitalization_only: a pure case difference
    # is reported as capitalization, not spelling, even though its
    # case-folded edit distance is also (trivially) small.
    if a == b:
        return False
    la, lb = a.lower(), b.lower()
    if la == lb:
        return False
    longer = max(len(la), len(lb))
    if longer == 0:
        return False
    return (float(_levenshtein(la, lb)) / longer) <= _SPELLING_MAX_RATIO


def _to_utf8_bytes(s):
    # checking.py's own outputError2 builds the results-list line by
    # concatenating byte strings, so passing it a genuine unicode msg forces
    # an implicit ASCII encode that fails on any non-ASCII character (see
    # Find_caption.py for the crash this was originally found and fixed in).
    if isinstance(s, type(u'')):
        return s.encode('utf-8')
    return s


# ---------------------------------------------------------------------------
# Project directory / BookNames.xml
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


def _load_book_names(directory):
    """Returns (book_names, diag). book_names is {code: {'long':, 'short':}}
    built from every <book code="..." long="..." short="..." /> element."""
    book_names = {}
    diag = {'path': None, 'found': False, 'book_count': 0}
    if not directory:
        return book_names, diag
    path = os.path.join(directory, u'BookNames.xml')
    diag['path'] = path
    if not os.path.isfile(path):
        return book_names, diag
    try:
        with open(_open_path(path), 'rb') as f:
            data = f.read()
        root = ET.fromstring(data)
    except Exception:
        return book_names, diag
    for book_el in root.findall(u'book'):
        code = book_el.get(u'code')
        if not code:
            continue
        book_names[code] = {
            u'long': book_el.get(u'long', u''),
            u'short': book_el.get(u'short', u''),
            u'abbr': book_el.get(u'abbr', u''),
        }
    diag['found'] = True
    diag['book_count'] = len(book_names)
    return book_names, diag


# ---------------------------------------------------------------------------
# \mt style loading (usfm.sty / custom.sty) -- adapted from find_footnotes.py,
# which solves the identical problem for footnote sub-markers.
# ---------------------------------------------------------------------------

def _parse_sty(path):
    """Line-based parser: a line starting with \\Marker opens a new entry
    keyed by the marker code; any other \\FieldName value line sets that
    field (lowercased) on the CURRENT entry. Blank lines and #-comments are
    ignored. Returns {marker_code: {field_name_lower: value_string}}."""
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


def _load_mt_styles(project_directory):
    """Returns (merged_fields, diag). usfm.sty lives one level up from the
    project directory; custom.sty lives inside it (same convention as
    find_footnotes.py's _load_footnote_styles)."""
    usfm_path = None
    custom_path = None
    if project_directory:
        parent = os.path.dirname(project_directory.rstrip(u'\\/'))
        usfm_path = os.path.join(parent, u'usfm.sty')
        custom_path = os.path.join(project_directory, u'custom.sty')

    base = _parse_sty(usfm_path)
    custom = _parse_sty(custom_path)
    merged = _merge_sty(base, custom)

    diag = {
        'usfm_path': usfm_path, 'usfm_found': bool(base),
        'custom_path': custom_path, 'custom_found': bool(custom),
    }
    return merged, diag


def _flag_on(fields, name):
    if name not in fields:
        return False
    v = fields.get(name, u'').strip().lower()
    return v not in (u'no', u'off', u'false', u'0')


def _color_css(value):
    # \Color in a .sty file is a Windows COLORREF decimal integer in BGR
    # byte order (R = low byte, G = mid byte, B = high byte).
    try:
        n = int(value.strip())
    except (TypeError, ValueError):
        return None
    r = n & 0xFF
    g = (n >> 8) & 0xFF
    b = (n >> 16) & 0xFF
    return u'rgb({0},{1},{2})'.format(r, g, b)


def _marker_css(fields):
    if not fields:
        return u''
    parts = []
    if _flag_on(fields, u'bold'):
        parts.append(u'font-weight:bold')
    if _flag_on(fields, u'italic'):
        parts.append(u'font-style:italic')
    if _flag_on(fields, u'superscript'):
        parts.append(u'vertical-align:super;font-size:smaller')
    if _flag_on(fields, u'smallcaps'):
        parts.append(u'font-variant:small-caps')
    if _flag_on(fields, u'underline'):
        parts.append(u'text-decoration:underline')
    color = fields.get(u'color')
    if color:
        css_color = _color_css(color)
        if css_color:
            parts.append(u'color:' + css_color)
    return u';'.join(parts)


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
    log_path = os.path.join(directory, u'TocExaminerDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Header marker scanning
# ---------------------------------------------------------------------------

# Python 2's re module has no variable-length lookbehind, so the two given
# expressions -- (?<=\toc1 |\mt\d? )[^\r]* and (?<=\toc2 |\h )[^\r]* -- are
# reproduced here with a leading capturing group instead of a lookbehind.
# Only bare \h (not \h1/\h2/\h3) and \mt with zero or one trailing digit are
# matched, exactly as in the given expressions. [^\r\n]* (rather than just
# [^\r]*) so this also behaves correctly on \n-only line endings.
# \toc3 is only read for the numbered-book consistency check below; none
# of the pairwise comparisons use it.
HEADER_MARKER_RE = re.compile(ur'^\\(toc1|toc2|toc3|mt[0-9]?|h)[ \t]+([^\r\n]*)', re.UNICODE | re.MULTILINE)

_state = {'prev_book': None, 'header_found': False}
_seen_books = set()
_report_rows = []  # (book_label, msg, label_a, text_a, label_b, text_b, cap_only, spelling, segments_b)
_issue_count = 0

# ---------------------------------------------------------------------------
# Numbered books (1SA, 2SA, ... 3JN): is the number written the same way in
# every book? Each field (\h, \toc1, ...) is compared across the numbered
# books on its own -- \toc1 legitimately uses a word ("Primera carta de")
# while \toc2 uses a digit ("1 Juan"), so fields are never compared with
# each other. The most common style in a field is the usual one; books that
# use any other style are reported. Only known once every book has been
# scanned, so (like _flush_book) these are HTML-report-only, and they are
# counted apart from _issue_count so the existing summary line is unchanged.
# ---------------------------------------------------------------------------

_NUMBERED_FIELDS = [
    (u'h', u'\\h'),
    (u'toc1', u'\\toc1'),
    (u'toc2', u'\\toc2'),
    (u'toc3', u'\\toc3'),
    (u'mt', u'\\mt'),
    (u'bn_long', u'BookNames.xml (long)'),
    (u'bn_short', u'BookNames.xml (short)'),
    (u'bn_abbr', u'BookNames.xml (abbr)'),
]

_STYLE_LABELS = {
    u'digit': u'Number and space (1 John)',
    u'digit_nbsp': u'Number and non-breaking space',
    u'digit_nospace': u'Number with no space (1John)',
    u'digit_period': u'Number and period (1. John)',
    u'digit_suffix': u'Number with an ending (1st, 1.\u00ba, 1\u00aa)',
    u'roman': u'Roman numeral (I John)',
    u'after_digit': u'Number after the name (John 1)',
    u'after_roman': u'Roman numeral after the name (John I)',
    u'word': u'Word (First)',
}

_numbered = {}  # book_num -> {field_key: text}
_numbered_results = []  # (field_key, field_label, usual_style or None, counts, outliers {book_num: style})
_numbered_issue_count = 0

_LEAD_DIGIT_RE = re.compile(ur'^(\d+)(.*)$', re.UNICODE | re.DOTALL)
# Ordinal endings: English 1st/2nd/3rd, Spanish 1er/1ro/1ra/1o/1a/1.o,
# French 1er/1re/2e/2eme, and the ordinal indicators U+00AA/U+00BA/U+00B0. Only lowercase
# endings from this list count, so "1Juan" or a \toc3 like "1Jn" is a
# number with no space, not an ending.
_SUFFIX_RE = re.compile(
    ur'^\.?[\u00aa\u00ba\u00b0]|^\.?(?:st|nd|rd|th|er|re|ere|\u00e8re|eme|\u00e8me|e|ra|ro|o|a)(?=[ \u00a0.]|$)',
    re.UNICODE)
_LEAD_ROMAN_RE = re.compile(ur'^(I{1,3})[ \u00a0]', re.UNICODE)
_TRAIL_DIGIT_RE = re.compile(ur'[ \u00a0](\d+)$', re.UNICODE)
_TRAIL_ROMAN_RE = re.compile(ur'[ \u00a0](I{1,3})$', re.UNICODE)
_FIRST_WORD_RE = re.compile(ur'^\S+', re.UNICODE)


def _number_style(text):
    """Returns (style_key, token): how the book's number is written in this
    text, and the part of the text that shows it ("1st", "Primera")."""
    m = _LEAD_DIGIT_RE.match(text)
    if m:
        digits, rest = m.group(1), m.group(2)
        sm = _SUFFIX_RE.match(rest)
        if sm:
            return u'digit_suffix', digits + sm.group(0)
        if rest.startswith(u'.'):
            return u'digit_period', digits + u'.'
        if rest.startswith(u'\u00a0'):
            return u'digit_nbsp', digits
        if rest.startswith(u' ') or not rest:
            return u'digit', digits
        return u'digit_nospace', digits
    m = _LEAD_ROMAN_RE.match(text)
    if m:
        return u'roman', m.group(1)
    m = _TRAIL_DIGIT_RE.search(text)
    if m:
        return u'after_digit', m.group(1)
    m = _TRAIL_ROMAN_RE.search(text)
    if m:
        return u'after_roman', m.group(1)
    m = _FIRST_WORD_RE.match(text)
    return u'word', (m.group(0) if m else text)


def _is_numbered_book(book_num):
    code = _book_label(book_num)
    return code[:1] in (u'1', u'2', u'3')


def _evaluate_numbered():
    global _numbered_issue_count
    if not _check_numbered:
        return
    for book_num in _seen_books:
        if not _is_numbered_book(book_num):
            continue
        entry = _numbered.setdefault(book_num, {})
        bn = _book_names.get(_book_label(book_num)) if _book_names else None
        if bn:
            for key, attr in ((u'bn_long', u'long'), (u'bn_short', u'short'), (u'bn_abbr', u'abbr')):
                val = _strip_soft_breaks(bn.get(attr, u''))
                if val:
                    entry[key] = val
    for key, label in _NUMBERED_FIELDS:
        styles = {}
        for book_num, entry in _numbered.items():
            val = entry.get(key)
            if val:
                styles[book_num] = _number_style(val)[0]
        if len(styles) < 2:
            continue
        counts = {}
        for style in styles.values():
            counts[style] = counts.get(style, 0) + 1
        top = max(counts.values())
        leaders = [s for s in counts if counts[s] == top]
        if len(leaders) == 1:
            usual = leaders[0]
            outliers = dict((b, s) for (b, s) in styles.items() if s != usual)
            _numbered_issue_count += len(outliers)
        else:
            # No usual style: every book in the field is highlighted, and
            # the field counts as one issue.
            usual = None
            outliers = dict(styles)
            _numbered_issue_count += 1
        if outliers:
            _numbered_results.append((key, label, usual, counts, outliers))


def _report(book_label, msg, begin, end, label_a, text_a, label_b, text_b, segments_b=None):
    global _issue_count
    _issue_count += 1
    try:
        checking.outputError(begin, end, _to_utf8_bytes(msg))
    except Exception as e:
        _log_crash(u'{0} outputError'.format(book_label), e)
    cap_only = False
    spelling = False
    if text_a is not None and text_b is not None:
        cap_only = _capitalization_only(text_a, text_b)
        spelling = _spelling_difference(text_a, text_b)
    _report_rows.append((book_label, msg, label_a, text_a, label_b, text_b, cap_only, spelling, segments_b))


def _flush_book(book_num):
    # Only reachable once a book boundary is crossed (or at the very end of
    # the scan) -- by then the chapter `text` the header would have been in
    # is no longer the one checkChapter is currently processing, so there is
    # no valid offset left to report this through checking.outputError; it
    # is HTML-report-only.
    if book_num is None or book_num < 1 or book_num >= len(BOOK_NAMES):
        return
    if _state['header_found']:
        return
    if not (_need_toc1 or _need_toc2 or _need_h or _need_mt):
        return
    global _issue_count
    _issue_count += 1
    _report_rows.append((
        _book_label(book_num),
        u'No \\toc1/\\toc2/\\h/\\mt header markers found for this book',
        u'', None, u'', None, False, False, None,
    ))


def _checkChapter_impl(reference, text, lastChapter):
    book_num = reference.Book if reference is not None else None

    if book_num != _state['prev_book']:
        _flush_book(_state['prev_book'])
        _state['prev_book'] = book_num
        _state['header_found'] = False

    if book_num is None or book_num < 1 or book_num >= len(BOOK_NAMES):
        return
    _seen_books.add(book_num)

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

    matches = list(HEADER_MARKER_RE.finditer(text))
    if not matches:
        return

    _state['header_found'] = True
    book_label = _book_label(book_num)
    book_code = BOOK_NAMES[book_num]
    anchor = matches[0].start()

    toc1 = None
    toc2 = None
    toc3 = None
    h = None
    mt_parts = []
    for m in matches:
        kind = m.group(1)
        val = _collapse_ws(m.group(2)).strip()
        if kind == u'toc1' and toc1 is None:
            toc1 = (_strip_soft_breaks(val), m.start(), m.end())
        elif kind == u'toc2' and toc2 is None:
            toc2 = (val, m.start(), m.end())
        elif kind == u'toc3' and toc3 is None:
            toc3 = val
        elif kind == u'h' and h is None:
            h = (val, m.start(), m.end())
        elif kind.startswith(u'mt'):
            mt_parts.append((kind, val))

    # Combined in DOCUMENT order, not sorted by digit -- some books split
    # the title across more than one \mt marker with \mt2 physically before
    # \mt1 (e.g. "\mt2 Primer libro de" then "\mt1 Samuel"), and only
    # concatenating in file order reproduces \toc1's text. This plain string
    # is what every comparison/classification below actually uses; the
    # per-marker mt_segments below are for HTML display only and never feed
    # into the equality check, the outputError message, or the
    # Capitalization/Spelling classification. mt_filtered_parts excludes any
    # \mt#-level the user chose to ignore -- but the "\mt is missing" check
    # further below deliberately uses the RAW mt_parts, not this filtered
    # view, so a marker that genuinely exists but was excluded from
    # consideration is never reported missing.
    mt_filtered_parts = [(kind, val) for (kind, val) in mt_parts if kind not in _IGNORED_MT_KINDS]
    mt_combined = u' '.join(val for (kind, val) in mt_filtered_parts if val) if mt_filtered_parts else None
    if mt_combined is not None:
        mt_combined = _strip_soft_breaks(mt_combined)
    mt_segments = [(kind, _strip_soft_breaks(val)) for (kind, val) in mt_filtered_parts if val]

    if _check_numbered and _is_numbered_book(book_num) and book_num not in _numbered:
        _numbered[book_num] = {
            u'h': h[0] if h is not None else None,
            u'toc1': toc1[0] if toc1 is not None else None,
            u'toc2': toc2[0] if toc2 is not None else None,
            u'toc3': toc3,
            u'mt': mt_combined,
        }

    if _need_toc1 and toc1 is None:
        _report(book_label, u'\\toc1 is missing', anchor, anchor + 1, u'\\toc1', None, u'', None)
    if _need_toc2 and toc2 is None:
        _report(book_label, u'\\toc2 is missing', anchor, anchor + 1, u'\\toc2', None, u'', None)
    if _need_h and h is None:
        _report(book_label, u'\\h is missing', anchor, anchor + 1, u'\\h', None, u'', None)
    if _need_mt and not mt_parts:
        _report(book_label, u'\\mt is missing', anchor, anchor + 1, u'\\mt', None, u'', None)

    if _compare_toc1_to_mt and toc1 is not None and mt_combined is not None and toc1[0] != mt_combined:
        if not (_ignore_capitalization_only and _capitalization_only(toc1[0], mt_combined)):
            _report(book_label, u'\\toc1 does not match \\mt', toc1[1], toc1[2],
                     u'\\toc1', toc1[0], u'\\mt', mt_combined, segments_b=mt_segments)

    if _compare_toc2_to_h and toc2 is not None and h is not None and toc2[0] != h[0]:
        if not (_ignore_capitalization_only and _capitalization_only(toc2[0], h[0])):
            _report(book_label, u'\\toc2 does not match \\h', toc2[1], toc2[2],
                     u'\\toc2', toc2[0], u'\\h', h[0])

    bn_entry = _book_names.get(book_code) if _book_names else None
    if _compare_toc1_to_booknames and toc1 is not None and bn_entry is not None:
        bn_long = _strip_soft_breaks(bn_entry.get(u'long', u''))
        if bn_long and toc1[0] != bn_long:
            if not (_ignore_capitalization_only and _capitalization_only(toc1[0], bn_long)):
                _report(book_label, u'\\toc1 does not match BookNames.xml', toc1[1], toc1[2],
                         u'\\toc1', toc1[0], u'BookNames.xml (long)', bn_long)

    if _compare_toc2_to_booknames and toc2 is not None and bn_entry is not None:
        bn_short = _strip_soft_breaks(bn_entry.get(u'short', u''))
        if bn_short and toc2[0] != bn_short:
            if not (_ignore_capitalization_only and _capitalization_only(toc2[0], bn_short)):
                _report(book_label, u'\\toc2 does not match BookNames.xml', toc2[1], toc2[2],
                         u'\\toc2', toc2[0], u'BookNames.xml (short)', bn_short)


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
_book_names, _book_names_diag = _load_book_names(_directory) if (_need_booknames or _check_numbered) else ({}, None)
_mt_styles, _mt_styles_diag = _load_mt_styles(_directory) if _compare_toc1_to_mt else ({}, None)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_CHECK_MARK = unichr(0x2713)


def _marker_cell(label, text):
    if not label:
        return u''
    if text is None:
        return u'{0}: <span class="missing">missing</span>'.format(_he(label))
    return u'{0}: &quot;{1}&quot;'.format(_he(label), _he(text))


def _mt_segment_cell(label, segments):
    # Renders each \mt/\mt1/\mt2/\mt3 part with its own resolved style from
    # usfm.sty/custom.sty (e.g. \mt1 bold+larger, \mt2 plain, \mt3 italic),
    # instead of the combined text as one plain string -- returns None (not
    # an empty string) when there's nothing to style, so the caller falls
    # back to _marker_cell's plain rendering.
    if not segments:
        return None
    parts = []
    for kind, text in segments:
        if not text:
            continue
        css = _marker_css(_mt_styles.get(kind, {}))
        style_attr = u' style="{0}"'.format(css) if css else u''
        parts.append(u'<span{0}>{1}</span>'.format(style_attr, _he(text)))
    if not parts:
        return None
    return u'{0}: &quot;{1}&quot;'.format(_he(label), u' '.join(parts))


def _flag_cell(flag):
    return _CHECK_MARK if flag else u''


def _style_label(style):
    return _STYLE_LABELS.get(style, style)


def _counts_text(counts):
    parts = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return u', '.join(u'{0} \u00d7 {1}'.format(n, _style_label(s)) for (s, n) in parts)


def _numbered_section(lines):
    # Rows here start with <tr><td class=...>, never <tr><td><b>: Project
    # Checker's harness (report_extract.toc) collects the main table's rows
    # by that prefix.
    lines.append(u'<h2>Numbered books (1, 2, 3): how the number is written</h2>')
    lines.append(u'<p>{0} numbered book(s), {1} inconsistency(ies) found.</p>'.format(
        len(_numbered), _numbered_issue_count))
    if _book_names_diag is not None and not _book_names_diag['found']:
        lines.append(u'<p><i>Note: BookNames.xml was not found, so its names are not included.</i></p>')
    if len(_numbered) < 2:
        lines.append(u'<p><i>At least two numbered books are needed for a comparison.</i></p>')
        return
    results = dict((r[0], r) for r in _numbered_results)
    fields = [(k, l) for (k, l) in _NUMBERED_FIELDS
              if any(e.get(k) for e in _numbered.values())]

    if not _numbered_results:
        lines.append(u'<p><i>Every field writes the number the same way in every numbered book.</i></p>')
    else:
        lines.append(u'<table><tr><th>Book</th><th>Field</th><th>Text</th>'
                      u'<th>How the number is written</th><th>Usual in this field</th></tr>')
        for key, label in fields:
            if key not in results:
                continue
            _, _, usual, counts, outliers = results[key]
            total = sum(counts.values())
            if usual is None:
                usual_text = u'No usual style: ' + _he(_counts_text(counts))
            else:
                usual_text = u'{0} ({1} of {2} books)'.format(
                    _he(_style_label(usual)), counts[usual], total)
            for book_num in sorted(outliers):
                text = _numbered[book_num][key]
                lines.append(u'<tr><td class="bk">{0}</td><td>{1}</td><td>&quot;{2}&quot;</td>'
                              u'<td>{3} (&quot;{4}&quot;)</td><td>{5}</td></tr>'.format(
                    _ref_link(_he(_book_label(book_num)), _book_goto(_book_label(book_num))), _he(label), _he(text),
                    _he(_style_label(outliers[book_num])), _he(_number_style(text)[1]),
                    usual_text))
        lines.append(u'</table>')

    lines.append(u'<p>All numbered books (highlighted = differs from the usual style in that column):</p>')
    head = u''.join(u'<th>{0}</th>'.format(_he(l)) for (k, l) in fields)
    lines.append(u'<table><tr><th>Book</th>{0}</tr>'.format(head))
    usual_cells = []
    for key, label in fields:
        r = results.get(key)
        if r is not None and r[2] is None:
            usual_cells.append(u'<td class="usual">(no usual style)</td>')
        else:
            styles = [_number_style(e[key])[0] for e in _numbered.values() if e.get(key)]
            usual = r[2] if r is not None else (styles[0] if styles else None)
            usual_cells.append(u'<td class="usual">{0}</td>'.format(
                _he(_style_label(usual)) if usual else u''))
    lines.append(u'<tr><td class="usual">Usual</td>{0}</tr>'.format(u''.join(usual_cells)))
    for book_num in sorted(_numbered):
        entry = _numbered[book_num]
        cells = []
        for key, label in fields:
            val = entry.get(key)
            r = results.get(key)
            if not val:
                cells.append(u'<td><span class="missing">missing</span></td>')
            elif r is not None and book_num in r[4]:
                cells.append(u'<td class="odd" title="{0}">{1}</td>'.format(
                    _he(_style_label(r[4][book_num])).replace(u'"', u'&quot;'), _he(val)))
            else:
                cells.append(u'<td>{0}</td>'.format(_he(val)))
        lines.append(u'<tr><td class="bk">{0}</td>{1}</tr>'.format(
            _ref_link(_he(_book_label(book_num)), _book_goto(_book_label(book_num))), u''.join(cells)))
    lines.append(u'</table>')


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>TOC Examiner Report &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.missing{color:#999;font-style:italic}')
    if _check_numbered:
        lines.append(u'.bk{font-weight:bold}')
        lines.append(u'.odd{background:#fdd}')
        lines.append(u'.usual{background:#eee;font-style:italic}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>TOC Examiner Report</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html())
    lines.append(u'<p>Project: <b>{0}</b></p>'.format(_he(project_name)))

    if _need_booknames and _book_names_diag is not None and not _book_names_diag['found']:
        lines.append(u'<p><i>Note: BookNames.xml was not found at {0} -- '
                      u'BookNames.xml comparisons were skipped for every book.</i></p>'.format(
            _he(_book_names_diag['path'] or u'(project directory not found)')))

    if _compare_toc1_to_mt and _mt_styles_diag is not None and not _mt_styles_diag['usfm_found']:
        lines.append(u'<p><i>Note: usfm.sty was not found at {0} -- '
                      u'\\mt text will render without per-level styling.</i></p>'.format(
            _he(_mt_styles_diag['usfm_path'] or u'(project directory not found)')))

    lines.append(u'<p>{0} book(s) scanned, {1} issue(s) found.</p>'.format(len(_seen_books), _issue_count))

    if not _report_rows:
        lines.append(u'<p><i>No issues found.</i></p>')
    else:
        lines.append(u'<table><tr><th>Book</th><th>Issue</th><th>Marker A</th><th>Marker B</th>'
                      u'<th>Capitalization only?</th><th>Spelling?</th></tr>')
        for book_label, msg, label_a, text_a, label_b, text_b, cap_only, spelling, segments_b in _report_rows:
            cell_b = _mt_segment_cell(label_b, segments_b)
            if cell_b is None:
                cell_b = _marker_cell(label_b, text_b)
            lines.append(u'<tr><td><b>{0}</b></td><td>{1}</td><td>{2}</td><td>{3}</td>'
                          u'<td>{4}</td><td>{5}</td></tr>'.format(
                _ref_link(_he(book_label), _book_goto(book_label)), _he(msg), _marker_cell(label_a, text_a), cell_b,
                _flag_cell(cap_only), _flag_cell(spelling)))
        lines.append(u'</table>')

    if _check_numbered:
        _numbered_section(lines)

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

checking.checkAllChapters(checkChapter)
_flush_book(_state['prev_book'])
try:
    _evaluate_numbered()
except Exception as e:
    _log_crash(u'numbered books', e)

if _directory:
    _html_path = os.path.join(_directory, u'TocExaminerReport.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(u'# Report written to {0}\n'.format(_html_path))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(u'# Error writing HTML report; see TocExaminerDebug.log\n')
    sys.stdout.write(u'# {0} book(s) scanned, {1} issue(s) found\n'.format(len(_seen_books), _issue_count))
    if _check_numbered:
        sys.stdout.write(u'# Numbered books (1, 2, 3): {0} inconsistency(ies) in how the number is written\n'.format(
            _numbered_issue_count))
    if _need_booknames and _book_names_diag is not None and not _book_names_diag['found']:
        sys.stdout.write(u'# Note: BookNames.xml was not found; BookNames.xml comparisons were skipped.\n')
else:
    sys.stdout.write(u'# Error: could not determine project directory; no report written.\n')
