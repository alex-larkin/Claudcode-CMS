# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import traceback
import unicodedata

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
SortAlphabetically = _to_unicode(SortAlphabetically)
_sort_alphabetically = SortAlphabetically.strip().lower() == u'yes'

try:
    HideMarkers
except NameError:
    HideMarkers = u'No'
HideMarkers = _to_unicode(HideMarkers)
_hide_markers = HideMarkers.strip().lower() == u'yes'

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

try:
    CheckFtCapitals
except NameError:
    CheckFtCapitals = u'No'
CheckFtCapitals = _to_unicode(CheckFtCapitals)
_check_ft_capitals = CheckFtCapitals.strip().lower() == u'yes'

try:
    CheckCapitalAfterFr
except NameError:
    CheckCapitalAfterFr = u'No'
CheckCapitalAfterFr = _to_unicode(CheckCapitalAfterFr)
_check_after_fr = CheckCapitalAfterFr.strip().lower() == u'yes'

try:
    OnlyCapitalIssues
except NameError:
    OnlyCapitalIssues = u'No'
OnlyCapitalIssues = _to_unicode(OnlyCapitalIssues)
_only_requested = OnlyCapitalIssues.strip().lower() == u'yes'
# Without a capitalization check there is nothing to filter on, so the
# option then has no effect (the report says so).
_only_capital = _only_requested and (_check_ft_capitals or _check_after_fr)

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (marker_space/MarkerSpace.py, quotation_examiner.py).
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
    # marks are ignored for ordering. Standalone IPA base letters (open-mid
    # vowels, engma, etc.) have no NFD decomposition of their own, so they
    # pass through unchanged and are not folded into a plain a/e/o/n --
    # only marks stacked on top of a base letter are dropped. The footnote
    # text actually written to the HTML is untouched; this is only ever
    # used as a sort key.
    decomposed = unicodedata.normalize('NFD', s)
    return u''.join(
        c for c in decomposed
        if unicodedata.category(c) not in (u'Mn', u'Mc', u'Me')
    ).lower()


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
    return path.encode('mbcs') if isinstance(path, type(u'')) else path


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


def _load_footnote_styles(project_directory):
    """Returns (merged_fields, diag). Unlike marker_space's loader, keeps
    EVERY marker and EVERY field -- footnote sub-markers (\\f itself, plus
    \\fr/\\fq/\\ft/etc.) are StyleType Note, not Character, and nested
    character styles (\\+it, \\+bd, \\+xt, ...) need their Bold/Italic/
    Superscript/Color fields regardless of StyleType."""
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
        'usfm_marker_count': len(base), 'custom_marker_count': len(custom),
    }
    return merged, diag


# ---------------------------------------------------------------------------
# .sty field -> CSS
# ---------------------------------------------------------------------------

def _flag_on(fields, name):
    if name not in fields:
        return False
    v = fields.get(name, u'').strip().lower()
    return v not in (u'no', u'off', u'false', u'0')


def _color_css(value):
    # \Color in a .sty file is a Windows COLORREF decimal integer in BGR
    # byte order (R = low byte, G = mid byte, B = high byte) -- e.g. the
    # value 16711680 (0x00FF0000) is pure BLUE, not red.
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


def _style_key(marker):
    # A marker's DISPLAY form (what's shown to the user, e.g. "+w*") keeps the
    # USFM3 nesting '+' and the closing '*' exactly as written in the source.
    # Its STYLE key strips both, since usfm.sty defines the style once under
    # the bare marker name (\Marker w) -- a nested or closing form is never
    # its own stylesheet entry.
    k = marker[1:] if marker.startswith(u'+') else marker
    return k[:-1] if k.endswith(u'*') else k


# ---------------------------------------------------------------------------
# Footnote scanning / sub-marker tokenizing
# ---------------------------------------------------------------------------

CHAPTER_RE = re.compile(ur'\\c\s+(\d+)', re.UNICODE)
VERSE_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)\s*', re.UNICODE)
FOOTNOTE_RE = re.compile(ur'\\f\s(.*?)\\f\*', re.UNICODE | re.DOTALL)
SUBMARKER_RE = re.compile(ur'\\\+?[a-zA-Z][a-zA-Z0-9]*\*?', re.UNICODE)


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


# Footnote-level markers: not self-closing, run until the next marker token
# (whatever it is) rather than needing their own closer. Everything else
# encountered inside a footnote (\+it, \+xt, or a nested character style
# used WITHOUT the USFM3 '+' -- both forms occur in real data, see \w in
# GEN 2:24-style word-list entries) is treated as a nested character style:
# it opens a new active marker until its own closing token, then reverts to
# whatever footnote-level marker was active before it. Checking the '+'
# prefix alone (as an earlier version of this function did) misclassifies
# a plain, non-'+' character style like \w...\w* as a NEW footnote-level
# marker, which incorrectly ends the surrounding \ft context early and
# leaks trailing text into the caller.
_FOOTNOTE_LEVEL_MARKERS = frozenset([
    u'fr', u'fq', u'fqa', u'fk', u'fl', u'fp', u'ft', u'fv', u'fdc', u'fm'])


def _tokenize_footnote(content):
    """Splits a footnote's inner content (between "\\f " and "\\f*") into
    segments tagged with whichever marker is currently active. The leading
    text segment (before the first marker token) is the footnote caller and
    is tagged with marker=None. A text segment's marker is the DISPLAY form
    of whatever token opened it (e.g. "+w", keeping the USFM3 nesting '+') --
    open/close PAIRING still matches on the plus-and-star-stripped bare code
    below, so a mismatched '+' between an opener and its closer (itself worth
    surfacing in the Section 1 counts) doesn't leave `inner` stuck open for
    the rest of the footnote. Every CLOSING token also gets its own zero-text
    segment (kind='close') at the point it occurs, so the closing marker
    stays visible in the rendered report instead of silently vanishing into
    whichever marker resumes afterward.
    Returns a list of {'kind': 'text'|'close', 'marker': code_or_None,
    'text': text} dicts."""
    segments = []
    outer = None
    inner = None
    inner_display = None
    pos = 0

    def flush(end):
        text = content[pos:end]
        if text:
            marker = inner_display if inner is not None else outer
            segments.append({'kind': u'text', 'marker': marker, 'text': text})

    for m in SUBMARKER_RE.finditer(content):
        flush(m.start())
        token = m.group(0)
        raw = token[1:]  # drop the leading backslash only -- keep '+'/'*'
        is_close = raw.endswith(u'*')
        bare = raw[1:] if raw.startswith(u'+') else raw
        if is_close:
            bare = bare[:-1]
            segments.append({'kind': u'close', 'marker': raw, 'text': u''})
            if inner is not None and inner == bare:
                inner = None
                inner_display = None
            elif outer is not None and outer == bare:
                outer = None
        elif bare in _FOOTNOTE_LEVEL_MARKERS:
            inner = None
            inner_display = None
            outer = bare
        else:
            inner = bare
            inner_display = raw
        pos = m.end()
    flush(len(content))
    return segments


# ---------------------------------------------------------------------------
# Capitalization checks (options CheckFtCapitals / CheckCapitalAfterFr)
# ---------------------------------------------------------------------------
#
# Works on the RAW footnote content with its own token walk, not on
# _tokenize_footnote's segments: there, the 'ft' text that resumes after a
# nested \+it...\+it* looks the same as the text of a new \ft marker.

_SENTENCE_END = u'.?!'


def _bare_code(token):
    raw = token[1:]
    is_close = raw.endswith(u'*')
    bare = raw[1:] if raw.startswith(u'+') else raw
    if is_close:
        bare = bare[:-1]
    return bare, is_close


def _skippable(c):
    # White space, punctuation, symbols, marks and control/format characters
    # are skipped when looking for the next word.
    return c.isspace() or unicodedata.category(c)[0] in (u'P', u'S', u'M', u'C', u'Z')


def _next_word(content, start, tokens, ti):
    """Looks for the first word after offset `start`, skipping white space,
    punctuation and character markers (open or close). Stops at the next
    footnote-level opening marker. Returns (is_lowercase, word_end) or None
    when no word comes before that marker. Digits and caseless letters
    count as not lowercase."""
    pos = start
    n = len(content)
    while pos < n:
        while ti < len(tokens) and tokens[ti].start() < pos:
            ti += 1
        if ti < len(tokens) and tokens[ti].start() == pos:
            bare, is_close = _bare_code(tokens[ti].group(0))
            if bare in _FOOTNOTE_LEVEL_MARKERS and not is_close:
                return None
            pos = tokens[ti].end()
            ti += 1
            continue
        c = content[pos]
        if _skippable(c):
            pos += 1
            continue
        end = pos
        while end < n and not content[end].isspace() and content[end] != u'\\':
            end += 1
        return (unicodedata.category(c) == u'Ll', end)
    return None


def _ends_sentence(s):
    """True when `s`, ignoring trailing white space and punctuation other
    than . ? !, ends with one of . ? !"""
    i = len(s) - 1
    while i >= 0:
        c = s[i]
        if c in _SENTENCE_END:
            return True
        if _skippable(c):
            i -= 1
            continue
        return False
    return False


def _capital_issues(content, check_ft, check_fr):
    """Returns a list of (begin, end, marker, kind) for the footnote's inner
    content: begin = the marker token's start, end = the end of the
    lowercase word. kind is 'ft' (a \\ft that is the first marker after
    \\fr -- or the first marker at all when there is no \\fr -- or a \\ft
    after a sentence end) or 'fr' (the first marker after \\fr).
    A \\ft that follows another marker such as \\fq (\\fq Dios \\ft o ...)
    needs a capital only after a sentence end."""
    issues = []
    if not (check_ft or check_fr):
        return issues
    tokens = list(SUBMARKER_RE.finditer(content))
    seen = set()
    outer = None
    prior = []          # footnote text after \fr, used for the sentence-end test
    first_marker = True # no footnote-level marker other than \fr seen yet
    after_fr = False
    prev_end = None     # None = still in the caller
    for i, tok in enumerate(tokens):
        if prev_end is not None and outer != u'fr':
            prior.append(content[prev_end:tok.start()])
        prev_end = tok.end()
        bare, is_close = _bare_code(tok.group(0))
        if is_close:
            if outer == bare:
                outer = None
            continue
        if bare not in _FOOTNOTE_LEVEL_MARKERS:
            continue
        outer = bare
        if bare == u'fr':
            after_fr = True
            continue
        want = None
        if after_fr:
            after_fr = False
            if check_fr:
                want = u'fr'
        is_first = first_marker
        first_marker = False
        if bare == u'ft':
            if check_ft and want is None:
                if is_first or _ends_sentence(u''.join(prior)):
                    want = u'ft'
        if want is None or tok.start() in seen:
            continue
        word = _next_word(content, tok.end(), tokens, i + 1)
        if word is not None and word[0]:
            seen.add(tok.start())
            issues.append((tok.start(), word[1], tok.group(0)[1:], want))
    return issues


def _capital_message(marker, kind):
    # ASCII only: this goes to checking.outputError.
    if kind == u'fr':
        return u'\\{0} sans majuscule suivant \\fr'.format(marker)
    return u'\\{0} sans majuscule'.format(marker)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

checking.setupCheck()

_directory = _project_directory()
_links_on = _ptx_goto is not None and _ptx_goto.enabled(_directory)
_sty_fields, _diag = _load_footnote_styles(_directory)

_marker_counts = {}    # display code ("w" open / "w*" close) -> token count
_occurrences = []      # every footnote found: {'ref':, 'caller':, 'fr_text':, 'rest_segments':, 'sort_key':}
_total_footnotes = 0


def _log_crash(label, exc):
    directory = _directory or os.environ.get('TEMP') or os.environ.get('TMP')
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
    log_path = os.path.join(directory, u'FootnotesDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


def _checkChapter_impl(reference, text, lastChapter):
    global _total_footnotes
    book_num = reference.Book if reference is not None else None
    book_label = _book_label(book_num)
    cm = CHAPTER_RE.search(text)
    chapter_label = cm.group(1) if cm else u'?'
    verse_positions = _verse_positions(text)

    def ref_at(offset):
        v = _verse_at(verse_positions, offset)
        return u'{0} {1}:{2}'.format(book_label, chapter_label, v)

    for m in FOOTNOTE_RE.finditer(text):
        _total_footnotes += 1
        content = m.group(1)
        segments = _tokenize_footnote(content)

        # Tally every marker TOKEN exactly as written (open/close, with or
        # without the USFM3 nesting '+') directly from the raw content,
        # independent of the segment/active-marker logic above -- \w, \w*,
        # \+w, and \+w* are counted as up to 4 distinct rows in the Section 1
        # summary, so a mismatched '+' between an opener and its closer is
        # visible rather than silently collapsed together. Counting segments
        # instead (as before) would also silently undercount any open marker
        # immediately followed by another marker with no text in between.
        for tok_m in SUBMARKER_RE.finditer(content):
            display_code = tok_m.group(0)[1:]  # drop the leading backslash only
            _marker_counts[display_code] = _marker_counts.get(display_code, 0) + 1

        caller_parts = []
        fr_parts = []
        rest_segments = []
        for seg in segments:
            if seg['marker'] is None:
                caller_parts.append(seg['text'])
            elif seg['marker'] == u'fr':
                fr_parts.append(seg['text'])
            else:
                rest_segments.append(seg)
        caller = _collapse_ws(u''.join(caller_parts)).strip()
        fr_text = _collapse_ws(u''.join(fr_parts)).strip()
        rest_text = _collapse_ws(u' '.join(
            s['text'] for s in rest_segments if s['text'].strip())).strip()

        distinct_markers = sorted(set(
            seg['marker'] for seg in segments
            if seg['marker'] is not None and seg['kind'] != u'close'))
        if distinct_markers:
            msg = u'Note de bas de page : ' + u' '.join(distinct_markers)
        else:
            msg = u'Note de bas de page'

        issues = _capital_issues(content, _check_ft_capitals, _check_after_fr)
        if issues or not _only_capital:
            try:
                checking.outputError(m.start(), m.end(), msg)
            except Exception as e:
                _log_crash(u'{0} outputError'.format(ref_at(m.start())), e)

        flags = []
        base = m.start(1)
        for begin, end, marker, kind in issues:
            flag = _capital_message(marker, kind)
            flags.append(flag)
            try:
                checking.outputError(base + begin, base + end, flag)
            except Exception as e:
                _log_crash(u'{0} outputError (capitals)'.format(ref_at(m.start())), e)

        _occurrences.append({
            'flags': flags,
            'ref': ref_at(m.start()),
            'caller': caller,
            'fr_text': fr_text,
            'rest_segments': rest_segments,
            'sort_key': _sort_fold(rest_text),
        })


def checkChapter(reference, text, lastChapter):
    try:
        _checkChapter_impl(reference, text, lastChapter)
    except Exception as e:
        book_num = reference.Book if reference is not None else None
        cm = CHAPTER_RE.search(text) if text else None
        chapter_label = cm.group(1) if cm else u'?'
        _log_crash(u'{0} {1}'.format(_book_label(book_num), chapter_label), e)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _color_swatch(css_color):
    if not css_color:
        return u''
    return u'<span class="swatch" style="background:{0}"></span>'.format(css_color)


def _marker_row_html(marker):
    # A nested ("+w") or closing ("w*"/"+w*") form is essentially never its
    # own stylesheet entry -- the style is governed by the opening marker's
    # \Marker block (whose \EndMarker field just names the closer). Resolve
    # via _style_key so every one of "w"/"w*"/"+w"/"+w*" shows the SAME
    # resolved style instead of a spurious "not in stylesheet".
    fields = _sty_fields.get(_style_key(marker), {})
    css = _marker_css(fields)
    flags = []
    if _flag_on(fields, u'bold'):
        flags.append(u'Gras')
    if _flag_on(fields, u'italic'):
        flags.append(u'Italique')
    if _flag_on(fields, u'superscript'):
        flags.append(u'Exposant')
    if _flag_on(fields, u'smallcaps'):
        flags.append(u'Petites capitales')
    if _flag_on(fields, u'underline'):
        flags.append(u'Souligné')
    _EM_DASH = unichr(0x2014)
    flags_str = u', '.join(flags) if flags else _EM_DASH
    color = fields.get(u'color')
    css_color = _color_css(color) if color else None
    swatch = _color_swatch(css_color)
    styletype = fields.get(u'styletype', u'') or _EM_DASH
    sample_style = u' style="{0}"'.format(css) if css else u''
    sample = u'<span{0}>Texte d’exemple</span>'.format(sample_style)
    found = u'oui' if fields else u'absent de la feuille de style'
    return (u'<tr><td>\\{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>'
            u'<td>{4}</td><td>{5}</td><td>{6}</td></tr>').format(
        _he(marker), _marker_counts.get(marker, 0), _he(found),
        swatch, _he(styletype), _he(flags_str), sample)


def _render_segments(segments):
    parts = []
    for seg in segments:
        marker = seg['marker']
        if seg['kind'] == u'close':
            if not _hide_markers:
                parts.append(u'<span class="tag">{0}</span>'.format(_he(marker)))
            continue
        if marker == u'fp':
            # \fp starts a new paragraph within the footnote -- force a line
            # break plus a small paragraph-style indent, regardless of
            # HideMarkers, since this is structural, not a marker label
            # being hidden.
            parts.append(u'<br><span class="indent"></span>')
        text = _he(_collapse_ws(seg['text']))
        if not text.strip():
            continue
        css = _marker_css(_sty_fields.get(_style_key(marker), {}))
        style_attr = u' style="{0}"'.format(css) if css else u''
        tag_html = u'' if _hide_markers else u'<span class="tag">{0}</span>'.format(_he(marker))
        parts.append(u'{0}<span{1}>{2}</span>'.format(tag_html, style_attr, text))
    return u''.join(parts)


_ONLY_WITHOUT_CHECK = (u'L’option « Afficher seulement les notes ayant un problème de majuscule » est activée, '
                       u'mais aucune vérification des majuscules ne l’est ; toutes les notes sont donc affichées.')
# ASCII only: printed to the results list.
_ONLY_WITHOUT_CHECK_ASCII = (u'L\'option "Afficher seulement les notes ayant un probleme de majuscule" est activee, '
                             u'mais aucune verification des majuscules ne l\'est ; toutes les notes sont donc affichees.')


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Rapport des notes de bas de page &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'h2{margin-top:28px}')
    lines.append(u'.tag{display:inline-block;font-size:10px;font-family:monospace;'
                 u'color:#666;background:#eee;border:1px solid #ccc;border-radius:3px;'
                 u'padding:0 3px;margin:0 3px 0 8px;vertical-align:middle}')
    lines.append(u'.swatch{display:inline-block;width:12px;height:12px;'
                 u'border:1px solid #888;vertical-align:middle;margin-right:4px}')
    lines.append(u'.caller{color:#888;font-family:monospace}')
    lines.append(u'.indent{display:inline-block;width:2ch}')
    lines.append(u'tr.flagged td{background:#ffe9d6}')
    lines.append(u'.flag{display:block;color:#c00000;font-weight:bold;margin-top:3px}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Rapport des notes de bas de page</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html('fr'))
    lines.append(u'<p>Projet : <b>{0}</b></p>'.format(_he(project_name)))

    lines.append(u'<p>usfm.sty: <code>{0}</code> &mdash; {1}, {2} marqueur(s)<br>'
                  u'custom.sty: <code>{3}</code> &mdash; {4}, {5} marqueur(s)</p>'.format(
        _he(_diag['usfm_path'] or u'(dossier du projet introuvable)'),
        u'trouvé' if _diag['usfm_found'] else u'INTROUVABLE',
        _diag['usfm_marker_count'],
        _he(_diag['custom_path'] or u'(dossier du projet introuvable)'),
        u'trouvé' if _diag['custom_found'] else u'absent',
        _diag['custom_marker_count']))

    lines.append(u'<h2>1. Récapitulatif des marqueurs et styles des notes</h2>')
    if not _marker_counts:
        lines.append(u'<p><i>Aucune note de bas de page n’a été trouvée dans le texte examiné.</i></p>')
    else:
        lines.append(u'<table><tr><th>Marqueur</th><th>Nombre</th><th>Dans la feuille de style ?</th>'
                      u'<th>Couleur</th><th>StyleType</th><th>Attributs</th><th>Exemple</th></tr>')
        for marker in sorted(_marker_counts.keys()):
            lines.append(_marker_row_html(marker))
        lines.append(u'</table>')

    lines.append(u'<h2>2. Notes de bas de page trouvées</h2>')
    if _total_footnotes == 0:
        lines.append(u'<p><i>Aucune note de bas de page n’a été trouvée dans le texte examiné.</i></p>')
    else:
        if _sort_alphabetically:
            ordered = sorted(_occurrences, key=lambda o: (o['sort_key'], o['ref']))
            sort_label = u'texte de la note (ordre alphabétique)'
        else:
            ordered = _occurrences
            sort_label = u'référence canonique'
        mode_note = u' Les marqueurs sont masqués.' if _hide_markers else u''
        lines.append(u'<p>{0} note(s) de bas de page trouvée(s), triée(s) par {1}.{2}</p>'.format(
            _total_footnotes, sort_label, mode_note))
        if _check_ft_capitals or _check_after_fr:
            checks = []
            if _check_ft_capitals:
                checks.append(u'majuscule après un \\ft qui est le premier marqueur après '
                              u'\\fr, ou qui suit la fin d’une phrase')
            if _check_after_fr:
                checks.append(u'majuscule après le premier marqueur qui suit \\fr')
            flagged = len([o for o in _occurrences if o['flags']])
            lines.append(u'<p>Majuscules vérifiées : {0}. <b>{1} note(s) signalée(s)</b> '
                         u'(surlignées ci-dessous).</p>'.format(
                _he(u' ; '.join(checks)), flagged))
        if _only_capital:
            ordered = [o for o in ordered if o['flags']]
            lines.append(u'<p><b>{0} note(s) affichée(s) sur {1} : seulement celles qui ont '
                         u'un problème de majuscule.</b></p>'.format(len(ordered), _total_footnotes))
        elif _only_requested:
            lines.append(u'<p><i>{0}</i></p>'.format(_ONLY_WITHOUT_CHECK))
    if _total_footnotes and _only_capital and not ordered:
        lines.append(u'<p><i>Aucune note ayant un problème de majuscule n’a été trouvée.</i></p>')
    elif _total_footnotes:
        fr_css = _marker_css(_sty_fields.get(u'fr', {}))
        fr_style_attr = u' style="{0}"'.format(fr_css) if fr_css else u''
        lines.append(u'<table><tr><th>Référence</th><th>Appel de note</th><th>\\fr</th>'
                      u'<th>Texte de la note</th></tr>')
        for occ in ordered:
            caller_cell = _he(occ['caller']) if occ['caller'] else u''
            fr_cell = u'<span{0}>{1}</span>'.format(fr_style_attr, _he(occ['fr_text'])) if occ['fr_text'] else u''
            body = _render_segments(occ['rest_segments'])
            row_class = u''
            if occ['flags']:
                row_class = u' class="flagged"'
                body += u''.join(u'<span class="flag">{0}</span>'.format(_he(f))
                                 for f in occ['flags'])
            lines.append(u'<tr{4}><td><b>{0}</b></td><td class="caller">{1}</td><td>{2}</td>'
                          u'<td>{3}</td></tr>'.format(_ref_link(_he(occ['ref']), _goto(occ['ref'])), caller_cell, fr_cell, body, row_class))
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
    _html_path = os.path.join(_directory, u'RapportNotesBasDePage.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(u'# Rapport ecrit dans {0}\n'.format(_html_path))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(u'# Erreur pendant l\'ecriture du rapport HTML ; voir FootnotesDebug.log\n')
    sys.stdout.write(u'# {0} note(s) examinee(s), {1} sous-marqueur(s) different(s) vu(s)\n'.format(
        _total_footnotes, len(_marker_counts)))
    if _check_ft_capitals or _check_after_fr:
        sys.stdout.write(u'# {0} note(s) signalee(s) pour les majuscules\n'.format(
            len([o for o in _occurrences if o['flags']])))
    elif _only_requested:
        sys.stdout.write(u'# Remarque : ' + _ONLY_WITHOUT_CHECK_ASCII + u'\n')
    if not _diag['usfm_found']:
        sys.stdout.write(u'# Attention : usfm.sty introuvable dans {0}\n'.format(_diag['usfm_path']))
else:
    sys.stdout.write(u'# Erreur : impossible de determiner le dossier du projet ; aucun rapport ecrit.\n')
