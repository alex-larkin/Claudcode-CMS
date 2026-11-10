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
    SortByTitle
except NameError:
    SortByTitle = u'No'
_sort_by_title = _to_unicode(SortByTitle).strip().lower() == u'yes'

try:
    SortByHeader
except NameError:
    SortByHeader = u'No'
_sort_by_header = _to_unicode(SortByHeader).strip().lower() == u'yes'

try:
    DisplayHeader
except NameError:
    DisplayHeader = u'No'
# The \h column is shown whenever the user asks for it OR whenever sorting
# by \h -- sorting by a hidden column would leave the ordering unexplained
# in the report, so SortByHeader=Yes implies the column regardless of this
# option.
_display_h = _to_unicode(DisplayHeader).strip().lower() == u'yes' or _sort_by_header

# SortByHeader overrides SortByTitle per the option's documented behavior.
if _sort_by_header:
    _sort_mode = u'h'
elif _sort_by_title:
    _sort_mode = u'mt'
else:
    _sort_mode = u'reference'

try:
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (toc_examiner.py, find_footnotes.py, quotation_examiner.py).
# Peripheral matter (FRT, BAK, OTH, INT, CNC, GLO, and the numbered XXA-XXG
# files) is out of scope for this check, same as toc_examiner.py.
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


_MT_SOFT_BREAK_RE = re.compile(ur'//')


def _strip_mt_soft_breaks(s):
    # Some projects use a literal // inside \mt text as a formatting device
    # forcing a soft line break -- it is not part of the title's wording, so
    # it is stripped (as a space, so words don't get glued together) before
    # display or sorting, same as toc_examiner.py.
    return _collapse_ws(_MT_SOFT_BREAK_RE.sub(u' ', s)).strip()


def _sort_fold(s):
    # Diacritic-insensitive sort key: NFD-decompose so an accented letter
    # becomes base letter + separate combining mark, then drop every
    # combining-mark character (categories Mn/Mc/Me) so accents and tone
    # marks are ignored for ordering (same approach as find_footnotes.py).
    # The title text actually written to the HTML is untouched; this is
    # only ever used as a sort key.
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


# ---------------------------------------------------------------------------
# \mt style loading (usfm.sty / custom.sty) -- adapted from toc_examiner.py,
# which solves the identical problem for main-title markers.
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
    toc_examiner.py's _load_mt_styles)."""
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
    log_path = os.path.join(directory, u'FindTitlesDebug.log')
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

# Only bare \h (not \h1/\h2/\h3) and \mt with zero or one trailing digit are
# matched -- same convention as toc_examiner.py.
HEADER_MARKER_RE = re.compile(ur'^\\(mt[0-9]?|h)[ \t]+([^\r\n]*)', re.UNICODE | re.MULTILINE)

_state = {'prev_book': None, 'resolved': False, 'h_text': None}
_seen_books = set()
_report_rows = []  # dicts: book_num, book_label, mt_combined, mt_segments, h_text
_title_count = 0
_missing_count = 0


def _flush_book(book_num):
    # Only reachable once a book boundary is crossed (or at the very end of
    # the scan) -- by then the chapter `text` a missing title would have
    # been in is no longer the one checkChapter is currently processing, so
    # there is no valid offset left to report this through
    # checking.outputError; it is HTML-report-only, same limitation as
    # toc_examiner.py's _flush_book. Only reached for a book that had NO
    # \mt or \h markers anywhere at all -- if either was found, the book
    # was already resolved and reported from inside _checkChapter_impl,
    # where a valid offset was still available.
    if book_num is None or book_num < 1 or book_num >= len(BOOK_NAMES):
        return
    global _missing_count
    if _state['resolved']:
        return
    _missing_count += 1
    _report_rows.append({
        'book_num': book_num, 'book_label': _book_label(book_num),
        'mt_combined': None, 'mt_segments': None, 'h_text': None,
    })


def _checkChapter_impl(reference, text, lastChapter):
    global _title_count, _missing_count
    book_num = reference.Book if reference is not None else None

    if book_num != _state['prev_book']:
        _flush_book(_state['prev_book'])
        _state['prev_book'] = book_num
        _state['resolved'] = False
        _state['h_text'] = None

    if book_num is None or book_num < 1 or book_num >= len(BOOK_NAMES):
        return
    _seen_books.add(book_num)

    if _state['resolved']:
        # This book's title status has already been determined and
        # reported (whether an \mt was found, or only \h was) -- ignore any
        # further \mt/\h occurrences later in the same book (e.g. a
        # secondary title page) so it is only listed once.
        return

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

    h = None
    mt_parts = []
    for m in matches:
        kind = m.group(1)
        val = _collapse_ws(m.group(2)).strip()
        if kind == u'h' and h is None:
            h = val
        elif kind.startswith(u'mt'):
            mt_parts.append((kind, val))

    if h is None and not mt_parts:
        return

    # This chapter is assumed to be the book's one header-marker location
    # (per this repo's existing convention -- see toc_examiner.py -- \h,
    # \toc1/2, and \mt always co-occur in one place, typically the front
    # matter ahead of chapter 1). Whether or not \mt itself was found, this
    # is the only chance to report through checking.outputError with a
    # valid offset -- once the book boundary is crossed, _flush_book can no
    # longer supply one -- so resolve and report the book's title status
    # right now.
    _state['resolved'] = True
    _state['h_text'] = h
    book_label = _book_label(book_num)

    mt_combined = None
    mt_segments = None
    if mt_parts:
        _title_count += 1
        anchor = [m for m in matches if m.group(1).startswith(u'mt')][0].start()
        # Combined in DOCUMENT order, not sorted by digit -- some books
        # split the title across more than one \mt marker with \mt2
        # physically before \mt1 (e.g. "\mt2 Primer libro de" then "\mt1
        # Samuel"), same as toc_examiner.py. mt_segments is also reused
        # below to build the results-list message; mt_combined is what
        # feeds the HTML sort key.
        mt_combined = _strip_mt_soft_breaks(u' '.join(val for (kind, val) in mt_parts if val))
        mt_segments = [(kind, _strip_mt_soft_breaks(val)) for (kind, val) in mt_parts if val]
        mt_label = u' '.join(u'\\{0} {1}'.format(kind, val) for kind, val in mt_segments)
    else:
        _missing_count += 1
        anchor = [m for m in matches if m.group(1) == u'h'][0].start()
        mt_label = u'ausente'

    if _display_h:
        h_display = h if h else u'ausente'
        mt_label = u'{0}  \\h {1}'.format(mt_label, h_display)

    # Anchor on a zero-width position rather than spanning from the first to
    # the last \mt match (same convention as toc_examiner.py's missing-
    # marker reports) -- when a title's \mt markers sit on separate physical
    # lines, checking.outputError's auto-sliced TEXT column would otherwise
    # include the raw \r\n between them, which Paratext's list view renders
    # as literal control-character escape text. A zero-width range (begin ==
    # end) keeps the position valid for click-to-navigate while making the
    # auto-sliced TEXT column empty -- a 1-character range would instead
    # always show a lone "\" (the marker's own leading backslash). Putting
    # the already-cleaned marker-labeled text in msg instead avoids both
    # problems entirely.
    try:
        checking.outputError(anchor, anchor, _to_utf8_bytes(mt_label))
    except Exception as e:
        _log_crash(u'{0} outputError'.format(book_label), e)

    _report_rows.append({
        'book_num': book_num, 'book_label': book_label,
        'mt_combined': mt_combined, 'mt_segments': mt_segments,
        'h_text': _state['h_text'],
    })


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
_mt_styles, _mt_styles_diag = _load_mt_styles(_directory)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _mt_cell(mt_combined, mt_segments):
    if mt_combined is None:
        return u'<span class="missing">ausente</span>'
    if not mt_segments:
        return _he(mt_combined)
    parts = []
    for kind, text in mt_segments:
        if not text:
            continue
        css = _marker_css(_mt_styles.get(kind, {}))
        style_attr = u' style="{0}"'.format(css) if css else u''
        parts.append(u'<span{0}>{1}</span>'.format(style_attr, _he(text)))
    return u' '.join(parts) if parts else _he(mt_combined)


def _h_cell(h_text):
    if h_text:
        return _he(h_text)
    return u'<span class="missing">ausente</span>'


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Informe de Títulos &ndash; {0}</title>'.format(_he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.missing{color:#999;font-style:italic}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Informe de Títulos</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html(True))
    lines.append(u'<p>Proyecto: <b>{0}</b></p>'.format(_he(project_name)))

    if _mt_styles_diag is not None and not _mt_styles_diag['usfm_found']:
        lines.append(u'<p><i>Nota: no se encontró usfm.sty en {0} -- '
                      u'el texto \\mt se mostrará sin estilo por nivel.</i></p>'.format(
            _he(_mt_styles_diag['usfm_path'] or u'(no se encontró el directorio del proyecto)')))

    lines.append(u'<p>{0} libro(s) escaneado(s), {1} título(s) encontrado(s), {2} ausente(s).</p>'.format(
        len(_seen_books), _title_count, _missing_count))

    if not _report_rows:
        lines.append(u'<p><i>No se escaneó ningún libro.</i></p>')
    else:
        if _sort_mode == u'mt':
            def _sort_key(row):
                if row['mt_combined'] is None:
                    return (1, u'', row['book_num'])
                return (0, _sort_fold(row['mt_combined']), row['book_num'])
            ordered = sorted(_report_rows, key=_sort_key)
            sort_label = u'el título \\mt (alfabéticamente)'
        elif _sort_mode == u'h':
            def _sort_key(row):
                if not row['h_text']:
                    return (1, u'', row['book_num'])
                return (0, _sort_fold(row['h_text']), row['book_num'])
            ordered = sorted(_report_rows, key=_sort_key)
            sort_label = u'el texto \\h (alfabéticamente)'
        else:
            ordered = _report_rows
            sort_label = u'el orden canónico de escaneo'
        lines.append(u'<p>Ordenado por {0}.</p>'.format(sort_label))

        if _display_h:
            lines.append(u'<table><tr><th>Libro</th><th>\\mt</th><th>\\h</th></tr>')
        else:
            lines.append(u'<table><tr><th>Libro</th><th>\\mt</th></tr>')
        for row in ordered:
            mt_cell = _mt_cell(row['mt_combined'], row['mt_segments'])
            if _display_h:
                lines.append(u'<tr><td><b>{0}</b></td><td>{1}</td><td>{2}</td></tr>'.format(
                    _ref_link(_he(row['book_label']), _book_goto(row['book_label'])), mt_cell, _h_cell(row['h_text'])))
            else:
                lines.append(u'<tr><td><b>{0}</b></td><td>{1}</td></tr>'.format(
                    _ref_link(_he(row['book_label']), _book_goto(row['book_label'])), mt_cell))
        lines.append(u'</table>')

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

checking.checkAllChapters(checkChapter)
_flush_book(_state['prev_book'])

if _directory:
    _html_path = os.path.join(_directory, u'InformeTitulos.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(_to_utf8_bytes(u'# Informe escrito en {0}\n'.format(_html_path)))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(_to_utf8_bytes(u'# Error al escribir el informe HTML; consulte FindTitlesDebug.log\n'))
    sys.stdout.write(_to_utf8_bytes(u'# Se escanearon {0} libro(s); se encontraron {1} título(s); {2} ausente(s)\n'.format(
        len(_seen_books), _title_count, _missing_count)))
else:
    sys.stdout.write(_to_utf8_bytes(u'# Error: no se pudo determinar el directorio del proyecto; no se escribió ningún informe.\n'))
