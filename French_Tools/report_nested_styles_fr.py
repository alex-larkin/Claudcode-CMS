# -*- coding: utf-8 -*-
import checking
import os
import re
import sys
import traceback

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
    Project
except NameError:
    Project = u''
Project = _to_unicode(Project)

# ---------------------------------------------------------------------------
# Book names (protestant canonical order, 1-66) -- same list used elsewhere
# in this repo (find_footnotes.py, marker_space/MarkerSpace.py,
# quotation_examiner.py).
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
    """Returns (merged_fields, diag). Keeps EVERY marker and EVERY field --
    footnote sub-markers (\\f itself, plus \\fr/\\fq/\\ft/etc.) are StyleType
    Note, not Character, while nested character styles (\\+it, \\+bd, \\+xt,
    ...) are StyleType Character and are what this check's '+' rule applies
    to (see _character_styles / _is_issue below)."""
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


# Footnote-level markers: these are the footnote's own internal structure
# (reference, quotation, text, etc.), not a character style borrowed from
# elsewhere -- so USFM3's '+' nesting rule never applies to them, regardless
# of whether they happen to carry StyleType Character in usfm.sty. Everything
# else that IS a real StyleType Character marker (\it, \bd, \w, \xt, ...)
# SHOULD carry '+' when it occurs inside a footnote; a plain '+' check alone
# can't tell these apart from footnote-level markers, so classification here
# is by marker identity, matching find_footnotes.py's own established fix.
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
    surfacing as its own issue -- see _is_issue) doesn't leave `inner` stuck
    open for the rest of the footnote. Every CLOSING token also gets its own
    zero-text segment (kind='close') at the point it occurs, so the closing
    marker stays visible in the rendered report instead of silently
    vanishing into whichever marker resumes afterward.
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
# Setup
# ---------------------------------------------------------------------------

checking.setupCheck()

_directory = _project_directory()
_links_on = _ptx_goto is not None and _ptx_goto.enabled(_directory)
_sty_fields, _diag = _load_footnote_styles(_directory)

# The '+' rule only applies to markers the stylesheet itself declares as
# StyleType Character -- unrecognized/typo marker codes are out of scope for
# this check (its job is to validate nesting of KNOWN character styles).
_character_styles = frozenset(
    marker for marker, fields in _sty_fields.items()
    if fields.get(u'styletype', u'').strip().lower() == u'character')

_issue_counts = {}    # display code ("xt" / "xt*") -> occurrence count
_occurrences = []     # flagged footnotes only: {'ref':, 'segments':}
_total_footnotes = 0
_flagged_footnotes = 0


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
    log_path = os.path.join(directory, u'NestedStylesDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


def _is_issue(raw):
    """raw is a marker token's DISPLAY form (backslash stripped, '+'/'*'
    preserved exactly as written -- e.g. "xt", "+xt", "xt*", "+xt*"). Returns
    True iff this specific token is a known character style that is missing
    its required USFM3 '+' nesting prefix. Checked per-token (not per marker
    identity), so a mismatched pair -- e.g. \\+it ... \\it* -- flags only the
    one token that's actually wrong."""
    has_plus = raw.startswith(u'+')
    bare = raw[1:] if has_plus else raw
    style_key = bare[:-1] if bare.endswith(u'*') else bare
    if style_key in _FOOTNOTE_LEVEL_MARKERS:
        return False
    if style_key not in _character_styles:
        return False
    return not has_plus


def _checkChapter_impl(reference, text, lastChapter):
    global _total_footnotes, _flagged_footnotes
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

        issue_markers = []
        for tok_m in SUBMARKER_RE.finditer(content):
            display_code = tok_m.group(0)[1:]  # drop the leading backslash only
            if _is_issue(display_code):
                issue_markers.append(display_code)
        if not issue_markers:
            continue

        _flagged_footnotes += 1
        for code in issue_markers:
            _issue_counts[code] = _issue_counts.get(code, 0) + 1

        msg = u'+ manquant : ' + u', '.join(sorted(set(issue_markers)))
        try:
            checking.outputError(m.start(), m.end(), msg)
        except Exception as e:
            _log_crash(u'{0} outputError'.format(ref_at(m.start())), e)

        _occurrences.append({
            'ref': ref_at(m.start()),
            'segments': _tokenize_footnote(content),
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

def _render_segments(segments):
    parts = []
    for seg in segments:
        marker = seg['marker']
        if seg['kind'] == u'close':
            cls = u'tag tag-err' if _is_issue(marker) else u'tag'
            parts.append(u'<span class="{0}">{1}</span>'.format(cls, _he(marker)))
            continue
        if marker == u'fp':
            # \fp starts a new paragraph within the footnote -- force a line
            # break plus a small paragraph-style indent (structural, always
            # shown, matching find_footnotes.py's treatment of \fp).
            parts.append(u'<br><span class="indent"></span>')
        text = _he(_collapse_ws(seg['text']))
        if not text.strip():
            continue
        if marker is None:
            parts.append(u'<span>{0}</span>'.format(text))
            continue
        css = _marker_css(_sty_fields.get(_style_key(marker), {}))
        style_attr = u' style="{0}"'.format(css) if css else u''
        cls = u'tag tag-err' if _is_issue(marker) else u'tag'
        tag_html = u'<span class="{0}">{1}</span>'.format(cls, _he(marker))
        parts.append(u'{0}<span{1}>{2}</span>'.format(tag_html, style_attr, text))
    return u''.join(parts)


def write_html_report(html_path, project_name):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Rapport des styles imbriqués</title>')
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'h2{margin-top:28px}')
    lines.append(u'.tag{display:inline-block;font-size:10px;font-family:monospace;'
                 u'color:#666;background:#eee;border:1px solid #ccc;border-radius:3px;'
                 u'padding:0 3px;margin:0 3px 0 8px;vertical-align:middle}')
    lines.append(u'.tag-err{color:#c00;background:#fee;border-color:#c00;font-weight:bold}')
    lines.append(u'.indent{display:inline-block;width:2ch}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Rapport des styles imbriqués</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html('fr'))
    if project_name:
        lines.append(u'<p>Projet : <b>{0}</b></p>'.format(_he(project_name)))

    lines.append(u'<p>usfm.sty: <code>{0}</code> &mdash; {1}, {2} marqueur(s)<br>'
                  u'custom.sty: <code>{3}</code> &mdash; {4}, {5} marqueur(s)</p>'.format(
        _he(_diag['usfm_path'] or u'(dossier du projet introuvable)'),
        u'trouvé' if _diag['usfm_found'] else u'INTROUVABLE',
        _diag['usfm_marker_count'],
        _he(_diag['custom_path'] or u'(dossier du projet introuvable)'),
        u'trouvé' if _diag['custom_found'] else u'absent',
        _diag['custom_marker_count']))

    lines.append(u'<h2>1. Résumé</h2>')
    lines.append(u'<p>{0} note(s) de bas de page examinée(s), dont {1} signalée(s) avec un style de '
                  u'caractère auquel il manque le &#39;+&#39; requis.</p>'.format(
        _total_footnotes, _flagged_footnotes))
    if not _issue_counts:
        lines.append(u'<p><i>Aucun problème trouvé.</i></p>')
    else:
        lines.append(u'<table><tr><th>Marqueur</th><th>Occurrences</th></tr>')
        for marker in sorted(_issue_counts.keys(), key=lambda k: (-_issue_counts[k], k)):
            lines.append(u'<tr><td>\\{0}</td><td>{1}</td></tr>'.format(
                _he(marker), _issue_counts[marker]))
        lines.append(u'</table>')

    lines.append(u'<h2>2. Notes de bas de page avec des problèmes</h2>')
    if not _occurrences:
        lines.append(u'<p><i>Aucune note de bas de page avec des problèmes n’a été trouvée.</i></p>')
    else:
        lines.append(u'<table><tr><th>Référence</th><th>Texte de la note</th></tr>')
        for occ in _occurrences:
            body = _render_segments(occ['segments'])
            lines.append(u'<tr><td><b>{0}</b></td><td>{1}</td></tr>'.format(
                _ref_link(_he(occ['ref']), _goto(occ['ref'])), body))
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
    _html_path = os.path.join(_directory, u'RapportStylesImbriques.html')
    try:
        write_html_report(_html_path, Project)
        os.startfile(_open_path(_html_path))
        sys.stdout.write(u'# Rapport enregistre dans {0}\n'.format(_html_path))
    except Exception as e:
        _log_crash(u'write_html_report', e)
        sys.stdout.write(u'# Erreur lors de l\'ecriture du rapport HTML ; voir NestedStylesDebug.log\n')
    sys.stdout.write(u'# {0} note(s) de bas de page examinee(s), {1} signalee(s)\n'.format(
        _total_footnotes, _flagged_footnotes))
    if not _diag['usfm_found']:
        sys.stdout.write(u'# Attention : usfm.sty est introuvable a l\'emplacement {0}\n'.format(_diag['usfm_path']))
else:
    sys.stdout.write(u'# Erreur : impossible de determiner le dossier du projet ; aucun rapport ecrit.\n')
