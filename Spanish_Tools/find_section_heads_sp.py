# -*- coding: utf-8 -*-
# Spanish-output variant of find_section_heads.py -- same detection/grouping
# logic; only the user-facing text (HTML report, checking.outputError
# messages, stdout summary lines) is in Spanish. find_section_heads_sp.cms
# points \script at this file instead of find_section_heads.py. Keep this
# file's non-string logic in sync with find_section_heads.py -- only the
# literal u'...' text differs.
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
_sort_alphabetically = _to_unicode(SortAlphabetically).strip().lower() == u'yes'

try:
    IncludeReferences
except NameError:
    IncludeReferences = u'No'
_include_references = _to_unicode(IncludeReferences).strip().lower() == u'yes'

try:
    FlagPunctuation
except NameError:
    FlagPunctuation = u'No'
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
    FlagFollowedByM = u'No'
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

# Con las dos en Sí, se muestra un encabezado que tenga cualquiera de los dos
# problemas.
_filtering = _filter_punct or _filter_m


def _filter_label():
    if _filter_punct and _filter_m:
        return u'con puntuación o seguidos de \\m'
    if _filter_punct:
        return u'con puntuación'
    return u'seguidos de \\m'

try:
    IgnoreFootnotesAndCrossRefs
except NameError:
    IgnoreFootnotesAndCrossRefs = u'Yes'
_ignore_notes = _to_unicode(IgnoreFootnotesAndCrossRefs).strip().lower() == u'yes'

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
    return u'Libro {0}'.format(book_num) if book_num is not None else u'?'


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


_report_rows = []  # dicts: book_label, ref, s_segments, s_plain, r_text, final_punct, followed_by_m, seq
_seen_books = set()
_total_s = 0
_total_shown = 0
_total_r_standalone = 0
_total_punct_flagged = 0
_total_m_flagged = 0
_kind_counts = {u's': 0, u's1': 0, u's2': 0, u's3': 0, u's4': 0}
_footnote_row_count = 0
_xref_row_count = 0


def _checkChapter_impl(reference, text, lastChapter):
    global _total_s, _total_shown, _total_r_standalone, _total_punct_flagged, _total_m_flagged
    global _footnote_row_count, _xref_row_count
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
        s_plain = u' '.join(plain for _, plain in plain_segments if plain)

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

        # Siempre se calculan, para Mostrar solo; los totales y las columnas
        # siguen dependiendo de FlagFollowedByM/FlagPunctuation.
        nxt = USFM_MARKER_RE.search(text, unit_end)
        is_m = bool(nxt and nxt.group(0) == u'\\m')
        has_punct = any(ch in _punct_chars for ch in s_plain)

        followed_by_m = None
        if _flag_followed_by_m:
            followed_by_m = is_m
            if followed_by_m:
                _total_m_flagged += 1

        final_punct = None
        if _flag_punctuation:
            final_punct = has_punct
            if final_punct:
                _total_punct_flagged += 1

        _total_s += 1
        # Mostrar solo oculta los demás encabezados del informe y de la lista
        # de resultados; los totales de arriba siguen contándolos.
        if not (not _filtering or (_filter_punct and has_punct)
                or (_filter_m and is_m)):
            continue
        _total_shown += 1
        if final_punct is None and _filter_punct:
            final_punct = has_punct
        if followed_by_m is None and _filter_m:
            followed_by_m = is_m
        ref = ref_at(group[0].start())
        _report_rows.append({
            'book_label': book_label, 'ref': ref,
            's_segments': s_segments, 's_plain': s_plain, 'r_text': r_text,
            'final_punct': final_punct, 'followed_by_m': followed_by_m,
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
            msg_parts.append(u'[puntuación]')
        if followed_by_m:
            msg_parts.append(u'[seguido de \\m]')
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
            # Un \r independiente no tiene encabezado, así que Mostrar solo lo
            # omite (el resumen sigue contándolo).
            if _filtering:
                continue
            r_text = _collapse_ws(rm.group(1)).strip()
            ref = ref_at(rm.start())
            _report_rows.append({
                'book_label': book_label, 'ref': ref,
                's_segments': None, 's_plain': None, 'r_text': r_text,
                'final_punct': None, 'followed_by_m': None,
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


def _s_cell(s_segments):
    if not s_segments:
        return u'<span class="missing">&#8212;</span>'
    parts = []
    for kind, raw_text in s_segments:
        css = _S_LEVEL_CSS.get(kind, u'')
        style_attr = u' style="{0}"'.format(css) if css else u''
        if _ignore_notes:
            inner = _he(_segment_display_text(raw_text))
        else:
            chunks = []
            for ptype, chunk in _split_inline_notes(raw_text):
                if ptype == u'note':
                    chunks.append(u'<span style="font-size:smaller">{0}</span>'.format(_he(chunk)))
                else:
                    chunks.append(_he(chunk))
            inner = u''.join(chunks)
        parts.append(u'<span{0}>{1}</span>'.format(style_attr, inner))
    return u' '.join(parts)


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Informe de Encabezados de Sección &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.missing{color:#999;font-style:italic}')
    lines.append(u'.check{text-align:center}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Informe de Encabezados de Sección</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html(True))
    lines.append(u'<p>Proyecto: <b>{0}</b></p>'.format(_he(project_name)))

    lines.append(u'<p>Marcadores de encabezado de sección encontrados:</p>')
    lines.append(u'<ul>')
    for kind in (u's', u's1', u's2', u's3', u's4'):
        lines.append(u'<li>\\{0}: {1}</li>'.format(kind, _kind_counts[kind]))
    lines.append(u'</ul>')
    lines.append(u'<p>{0} encabezado(s) de sección contienen notas al pie (\\f...\\f*); '
                  u'{1} encabezado(s) de sección contienen referencias cruzadas (\\x...\\x*).</p>'.format(
        _footnote_row_count, _xref_row_count))

    summary_parts = [
        u'{0} libro(s) escaneado(s)'.format(len(_seen_books)),
        u'{0} encabezado(s) de sección encontrado(s)'.format(_total_s),
    ]
    if _include_references:
        summary_parts.append(u'{0} referencia(s) \\r independiente(s)'.format(_total_r_standalone))
    if _flag_punctuation:
        summary_parts.append(u'{0} marcado(s) por puntuación'.format(_total_punct_flagged))
    if _flag_followed_by_m:
        summary_parts.append(u'{0} marcado(s) \\s/\\m'.format(_total_m_flagged))
    lines.append(u'<p>{0}.</p>'.format(u', '.join(summary_parts)))
    if _filtering:
        lines.append(u'<p><b>Mostrando solo los encabezados de sección {0}: {1} de {2}.</b></p>'.format(
            _he(_filter_label()), _total_shown, _total_s))

    if not _report_rows:
        if _filtering and _total_s:
            lines.append(u'<p><i>Ningún encabezado de sección coincide con las opciones Mostrar solo.</i></p>')
        else:
            lines.append(u'<p><i>No se encontró ningún encabezado de sección.</i></p>')
    else:
        if _sort_alphabetically:
            def _sort_key(row):
                if not row['s_plain']:
                    return (1, u'', row['seq'])
                return (0, _sort_fold(row['s_plain']), row['seq'])
            ordered = sorted(_report_rows, key=_sort_key)
            sort_label = u'el texto \\s (alfabéticamente)'
        else:
            ordered = sorted(_report_rows, key=lambda r: r['seq'])
            sort_label = u'el orden canónico de escaneo'
        lines.append(u'<p>Ordenado por {0}.</p>'.format(sort_label))

        # Una columna por la que filtra Mostrar solo siempre se muestra, para
        # que cada fila muestre por qué aparece.
        show_punct_col = _flag_punctuation or _filter_punct
        show_m_col = _flag_followed_by_m or _filter_m
        headers = [u'Libro', u'Referencia', u'\\s']
        if _include_references:
            headers.append(u'\\r')
        if show_punct_col:
            headers.append(u'Puntuación')
        if show_m_col:
            headers.append(u'\\m')
        lines.append(u'<table><tr>' + u''.join(
            u'<th>{0}</th>'.format(_he(h)) for h in headers) + u'</tr>')

        for row in ordered:
            cells = [
                u'<td><b>{0}</b></td>'.format(_he(row['book_label'])),
                u'<td>{0}</td>'.format(_ref_link(_he(row['ref']), _goto(row['ref']))),
            ]
            cells.append(u'<td>{0}</td>'.format(_s_cell(row['s_segments'])))
            if _include_references:
                cells.append(u'<td>{0}</td>'.format(_he(row['r_text']) if row['r_text'] else u''))
            if show_punct_col:
                cells.append(u'<td class="check">{0}</td>'.format(
                    _CHECK_MARK if row['final_punct'] else u''))
            if show_m_col:
                cells.append(u'<td class="check">{0}</td>'.format(
                    _CHECK_MARK if row['followed_by_m'] else u''))
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
    _html_path = os.path.join(_directory, u'InformeEncabezadosSeccion.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(_to_utf8_bytes(u'# Informe escrito en {0}\n'.format(_html_path)))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(_to_utf8_bytes(u'# Error al escribir el informe HTML; consulte FindSectionHeadsDebug.log\n'))
    sys.stdout.write(_to_utf8_bytes(u'# Se escanearon {0} libro(s); se encontraron {1} encabezado(s) de sección\n'.format(
        len(_seen_books), _total_s)))
    if _filtering:
        sys.stdout.write(_to_utf8_bytes(u'# Se muestran {0} encabezado(s) de sección: solo los {1}\n'.format(
            _total_shown, _filter_label())))
else:
    sys.stdout.write(_to_utf8_bytes(u'# Error: no se pudo determinar el directorio del proyecto; no se escribió ningún informe.\n'))
