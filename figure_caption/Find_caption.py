# -*- coding: utf-8 -*-
# Version 1.1
# Keep VERSION, the .cms \check title and its \description "[Version x.y]"
# in step, and bump all three on every change.
import os
import re
import traceback
import unicodedata
import checking

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

try:
    DisplayCaption
except NameError:
    DisplayCaption = u'Yes'
if isinstance(DisplayCaption, str):
    DisplayCaption = DisplayCaption.decode('utf-8')
_display_caption = DisplayCaption.strip().lower() == u'yes'

try:
    DisplayCopyright
except NameError:
    DisplayCopyright = u'Yes'
if isinstance(DisplayCopyright, str):
    DisplayCopyright = DisplayCopyright.decode('utf-8')
_display_copyright = DisplayCopyright.strip().lower() == u'yes'

try:
    DisplayIllustrationFile
except NameError:
    DisplayIllustrationFile = u'Yes'
if isinstance(DisplayIllustrationFile, str):
    DisplayIllustrationFile = DisplayIllustrationFile.decode('utf-8')
_display_illustration_file = DisplayIllustrationFile.strip().lower() == u'yes'

try:
    SortByCaption
except NameError:
    SortByCaption = u'No'
if isinstance(SortByCaption, str):
    SortByCaption = SortByCaption.decode('utf-8')
_sort_by_caption = SortByCaption.strip().lower() == u'yes'

checking.setupCheck()

# The UnicodeEncodeError seen earlier on a real project (DBTALP, an IPA-based
# orthography) turned out to come from `text.decode('utf-8')` in
# _checkChapter_impl, not from checking.outputError() itself -- see
# FigureCaptionsDebug.log history. With that fixed, the results list reports
# each figure's actual caption/copyright text (not just an "empty" flag).
# Every outputError call is still wrapped defensively and any failure is
# logged to our own FigureCaptionsDebug.log (see _log_crash), bypassing
# Paratext's write pipeline entirely, so a bad occurrence can't silently
# break the rest of the chapter. _report_rows/FigureCaptions.html (built
# independently of outputError) remain the reliable source of truth
# regardless of what outputError does in this environment.
FIG_MARKER_LEN = len(u'\\fig')
VERSION = u'1.1'

# Protestant canonical order, 1-66 -- same list used elsewhere in this repo
# (quotation_examiner.py / quotation_matcher.py / project_BT_reference_tool.py).
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


FIG_RE = re.compile(ur'\\fig\s(.*?)\\fig\*', re.UNICODE | re.DOTALL)
USFM3_ATTR_RE = re.compile(ur'\b[a-zA-Z]+="', re.UNICODE)
COPY_ATTR_RE = re.compile(ur'\bcopy="([^"]*)"', re.UNICODE)
SRC_ATTR_RE = re.compile(ur'\bsrc="([^"]*)"', re.UNICODE)
VERSE_NUM_RE = re.compile(ur'\\v\s+(\d+(?:[,-]\d+)*)', re.UNICODE)


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


def _log_crash(label, exc):
    # Own plain UTF-8 log file, entirely bypassing checking.py's/Paratext's
    # write pipeline -- same reasoning as quotation_examiner.py's
    # _log_crash, plus a TEMP-dir fallback: every existing copy of
    # _project_directory() in this repo silently loses diagnostics if it
    # returns None, which is exactly the kind of ambiguity that has already
    # cost multiple debugging round-trips on this check.
    directory = _project_directory() or os.environ.get('TEMP') or os.environ.get('TMP')
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
    log_path = os.path.join(directory, u'FigureCaptionsDebug.log')
    open_path = _open_for_write(log_path)
    try:
        with open(open_path, 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


def _usfm2_fields(content):
    fields = content.split(u'|')
    while len(fields) < 7:
        fields.append(u'')
    return fields[5].strip(), fields[4].strip(), fields[1].strip()


def _usfm3_fields(content):
    parts = content.split(u'|', 1)
    caption = parts[0].strip()
    attrs = parts[1] if len(parts) > 1 else u''
    m = COPY_ATTR_RE.search(attrs)
    copyright_ = m.group(1).strip() if m else u''
    m2 = SRC_ATTR_RE.search(attrs)
    filename = m2.group(1).strip() if m2 else u''
    return caption, copyright_, filename


def _to_utf8_bytes(s):
    # checking.py's own outputError2 builds the results-list line by
    # concatenating byte strings (it explicitly does verse.encode('utf-8')
    # before concatenating). Passing it a genuine unicode msg breaks that
    # all-bytes concatenation and forces an implicit ASCII encode that
    # fails on any non-ASCII character. Matching its own convention here
    # avoids that crash instead of fighting it from outside.
    if isinstance(s, type(u'')):
        return s.encode('utf-8')
    return s


def _verse_before(text, pos):
    verse = u'0'
    for vm in VERSE_NUM_RE.finditer(text):
        if vm.start() >= pos:
            break
        verse = vm.group(1)
    return verse


_report_rows = []


def _checkChapter_impl(reference, text, lastChapter):
    if not (_display_caption or _display_copyright or _display_illustration_file):
        return
    if isinstance(text, str):
        # On this Paratext installation (very likely IronPython under the
        # hood, given Paratext is a .NET application), `text` can satisfy
        # isinstance(text, str) while already being proper Unicode text --
        # calling .decode('utf-8') on it makes IronPython implicitly
        # re-encode to ASCII first, which raises UnicodeEncodeError (not
        # UnicodeDecodeError) on any non-ASCII character. Confirmed via
        # FigureCaptionsDebug.log: this line, not anything related to
        # checking.outputError, was the actual crash site all along -- every
        # previous fix attempt targeting outputError changed nothing because
        # execution never got past this line on real DBTALP chapters. If
        # decode() fails either way, text is already usable as-is.
        try:
            text = text.decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    book_num = reference.Book if reference is not None else None
    chapter_num = reference.Chapter if reference is not None else u'?'
    for m in FIG_RE.finditer(text):
        content = m.group(1)
        if USFM3_ATTR_RE.search(content):
            caption, copyright_, filename = _usfm3_fields(content)
        else:
            caption, copyright_, filename = _usfm2_fields(content)

        verse = _verse_before(text, m.start())
        ref_str = u'{0} {1}:{2}'.format(_book_label(book_num), chapter_num, verse)
        _report_rows.append((ref_str, caption, copyright_, filename))

        begin = m.start()
        end = begin + FIG_MARKER_LEN
        if _display_caption:
            caption_msg = caption if caption else u'empty'
            try:
                checking.outputError(begin, end, _to_utf8_bytes(caption_msg))
            except Exception as e:
                _log_crash(u'{0} caption outputError'.format(ref_str), e)
        if _display_copyright:
            copyright_msg = copyright_ if copyright_ else u'Copyright: empty'
            try:
                checking.outputError(begin, end, _to_utf8_bytes(copyright_msg))
            except Exception as e:
                _log_crash(u'{0} copyright outputError'.format(ref_str), e)
        if _display_illustration_file:
            filename_msg = filename if filename else u'empty'
            try:
                checking.outputError(begin, end, _to_utf8_bytes(filename_msg))
            except Exception as e:
                _log_crash(u'{0} illustration file outputError'.format(ref_str), e)


def checkChapter(reference, text, lastChapter):
    try:
        _checkChapter_impl(reference, text, lastChapter)
    except Exception as e:
        book_num = reference.Book if reference is not None else None
        chapter_num = reference.Chapter if reference is not None else u'?'
        _log_crash(u'{0} {1}'.format(_book_label(book_num), chapter_num), e)


_links_on = _ptx_goto is not None and _ptx_goto.enabled(_project_directory())

checking.checkAllChapters(checkChapter)


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


def _attr(s):
    return _he(s).replace(u'"', u'&quot;')


def _file_url(path):
    url = path.replace(u'\\', u'/').replace(u'%', u'%25').replace(u' ', u'%20').replace(u'#', u'%23')
    return u'file:///' + url


# Picture types a browser can show; .tif is not one of them.
SHOWABLE_EXTS = (u'.jpg', u'.jpeg', u'.png', u'.gif', u'.bmp')


def _figures_index(directory):
    # {lowercase file name: full path} for the project's figures folder --
    # same lookup as Compare Figures/CompareCopyFigures.py.
    idx = {}
    try:
        d = os.path.join(directory, u'figures')
        for name in os.listdir(d):
            idx[name.lower()] = os.path.join(d, name)
    except Exception:
        pass
    return idx


def _find_thumbnail(idx, src):
    # A picture the browser can show for src: the exact file name, otherwise
    # the same name with a showable extension (Paratext keeps .jpg copies of
    # the .tif files named in \fig). None if there is no such picture.
    if not src:
        return None
    name = os.path.basename(src.replace(u'/', u'\\'))
    stem = os.path.splitext(name)[0].lower()
    for cand in [name.lower()] + [stem + ext for ext in SHOWABLE_EXTS]:
        path = idx.get(cand)
        if path and os.path.splitext(path)[1].lower() in SHOWABLE_EXTS:
            return path
    return None


def _sort_fold(s):
    # Diacritic-insensitive sort key: NFD-decompose so an accented letter
    # becomes base letter + separate combining mark, then drop every
    # combining-mark character (categories Mn/Mc/Me) so accents and tone
    # marks are ignored for ordering. IPA base letters (e.g. ɛ, ɔ, ŋ) have no
    # NFD decomposition of their own, so they pass through unchanged and are
    # not folded into a/e/o/n -- only marks stacked on top of a base letter
    # are dropped. The caption text actually written to the HTML is
    # untouched; this is only ever used as a sort key.
    decomposed = unicodedata.normalize('NFD', s)
    return u''.join(
        c for c in decomposed
        if unicodedata.category(c) not in (u'Mn', u'Mc', u'Me')
    ).lower()


def _write_html_report_impl():
    directory = _project_directory()
    if not directory:
        return

    if _sort_by_caption:
        # Sort by whichever of Caption / Illustration File / Copyright is
        # actually being displayed, in that priority order -- sorting by a
        # hidden field isn't useful. At least one of the three is always on
        # here, since _checkChapter_impl's early return already requires it.
        if _display_caption:
            sort_index, sort_label = 1, u'caption text (alphabetically)'
        elif _display_illustration_file:
            sort_index, sort_label = 3, u'illustration file name (alphabetically)'
        elif _display_copyright:
            sort_index, sort_label = 2, u'copyright text (alphabetically)'
        else:
            sort_index, sort_label = 1, u'caption text (alphabetically)'
        ordered_rows = sorted(_report_rows, key=lambda row: (_sort_fold(row[sort_index]), row[0]))
    else:
        ordered_rows = _report_rows
        sort_label = u'canonical reference'

    # Thumbnails are always written when a picture exists, but hidden until
    # the reader ticks the checkbox above the table (unseen lazy images are
    # not loaded, so a big report stays fast).
    figures_idx = _figures_index(directory)
    thumbs = [_find_thumbnail(figures_idx, row[3]) for row in ordered_rows]
    n_thumbs = len([t for t in thumbs if t])

    parts = [
        u'<html><head><meta charset="utf-8"><title>Figure Captions</title>',
        u'<style>table{border-collapse:collapse;font-family:sans-serif}',
        u'td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}',
        u'.empty{color:#999;font-style:italic}.ver{color:#777;font-size:12px;margin-top:-12px}',
        u'.pic{display:none}body.thumbs .pic{display:table-cell}',
        u'img.th{display:block;max-width:150px;max-height:110px;border:1px solid #ddd}</style></head><body>',
        u'<h1>Figure Captions</h1>',
        u'<p class="ver">Version {0}</p>'.format(VERSION),
        u'<p>{0} figure(s) found, sorted by {1}.</p>'.format(len(_report_rows), sort_label),
    ]
    if _links_on:
        parts.append(_ptx_goto.hint_html())
    if n_thumbs:
        parts.append(
            u'<p><label><input type="checkbox" id="showThumbs" autocomplete="off" '
            u'onclick="document.body.className=this.checked?\'thumbs\':\'\'"> '
            u'Show picture thumbnails ({0} of {1} figures have a picture in the figures folder)</label></p>'
            .format(n_thumbs, len(ordered_rows)))
    else:
        parts.append(u'<p class="empty">No pictures for these figures were found in the project\'s figures folder.</p>')
    parts.append(u'<table><tr><th>Reference</th>')
    if n_thumbs:
        parts.append(u'<th class="pic">Picture</th>')
    if _display_caption:
        parts.append(u'<th>Caption</th>')
    if _display_copyright:
        parts.append(u'<th>Copyright</th>')
    if _display_illustration_file:
        parts.append(u'<th>Illustration File</th>')
    parts.append(u'</tr>')

    for (ref_str, caption, copyright_, filename), thumb in zip(ordered_rows, thumbs):
        parts.append(u'<tr><td>{0}</td>'.format(_ref_link(_he(ref_str), _goto(ref_str))))
        if n_thumbs:
            if thumb:
                parts.append(u'<td class="pic"><img class="th" loading="lazy" src="{0}" alt=""></td>'
                             .format(_attr(_file_url(thumb))))
            else:
                parts.append(u'<td class="pic empty">no picture</td>')
        if _display_caption:
            cell = u'<td>{0}</td>'.format(_he(caption)) if caption else u'<td class="empty">empty</td>'
            parts.append(cell)
        if _display_copyright:
            cell = u'<td>{0}</td>'.format(_he(copyright_)) if copyright_ else u'<td class="empty">empty</td>'
            parts.append(cell)
        if _display_illustration_file:
            cell = u'<td>{0}</td>'.format(_he(filename)) if filename else u'<td class="empty">empty</td>'
            parts.append(cell)
        parts.append(u'</tr>')

    parts.append(u'</table></body></html>')
    html = u''.join(parts)

    path = os.path.join(directory, u'FigureCaptions.html')
    with open(_open_for_write(path), 'wb') as f:
        f.write(html.encode('utf-8'))
    os.startfile(_open_for_write(path))


def _write_html_report():
    if not _report_rows:
        return
    try:
        _write_html_report_impl()
    except Exception as e:
        _log_crash(u'_write_html_report', e)


_write_html_report()
