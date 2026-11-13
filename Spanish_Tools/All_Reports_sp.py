# -*- coding: utf-8 -*-
import checking
import os
import re
import sys as _sys
import traceback

# ---------------------------------------------------------------------------
# Guard every variable Paratext injects: the framework variables, the ten
# per-check Include toggles, and the ten capital_at_verse options forwarded
# through when that check runs. Repeat-per-variable, no globals() helper --
# see feedback_cms_no_globals_option_helper in project memory for why.
# ---------------------------------------------------------------------------

try:
    Project
except NameError:
    Project = u''
try:
    Books
except NameError:
    Books = None
try:
    Language
except NameError:
    Language = u''
try:
    OutputFile
except NameError:
    OutputFile = u''

try:
    IncludeToc
except NameError:
    IncludeToc = 'Yes'
try:
    IncludeTitles
except NameError:
    IncludeTitles = 'Yes'
try:
    IncludeSectionHeads
except NameError:
    IncludeSectionHeads = 'Yes'
try:
    IncludeQuotationMarks
except NameError:
    IncludeQuotationMarks = 'Yes'
try:
    IncludePoetryErrors
except NameError:
    IncludePoetryErrors = 'Yes'
try:
    IncludeNestedStyles
except NameError:
    IncludeNestedStyles = 'Yes'
try:
    IncludeMarkerSpaces
except NameError:
    IncludeMarkerSpaces = 'Yes'
try:
    IncludeFootnotes
except NameError:
    IncludeFootnotes = 'Yes'
try:
    IncludeFigureCaptions
except NameError:
    IncludeFigureCaptions = 'Yes'
try:
    IncludeCapitalAtVerse
except NameError:
    IncludeCapitalAtVerse = 'Yes'

# Forwarded capital_at_verse options -- same names/defaults as
# capital_at_verse.cms; passed straight through when that check runs.
try:
    FinalPunctuation
except NameError:
    FinalPunctuation = '.!?'
try:
    WordsToIgnore
except NameError:
    WordsToIgnore = ''
try:
    IgnoreCapAfterQuote
except NameError:
    IgnoreCapAfterQuote = 'No'
try:
    IgnoreBiblicalTerms
except NameError:
    IgnoreBiblicalTerms = 'Yes'
try:
    IgnoreWordlistCapitals
except NameError:
    IgnoreWordlistCapitals = 'Yes'
try:
    QuoteOpeningChars
except NameError:
    QuoteOpeningChars = unichr(0x00ab) + unichr(0x201c) + unichr(0x2014) + unichr(0x2018)
try:
    IgnoreStyles
except NameError:
    IgnoreStyles = ''
try:
    IgnoreParaStyles
except NameError:
    IgnoreParaStyles = 'sp, r, ms, mr, sr'
try:
    PrefixesToIgnore
except NameError:
    PrefixesToIgnore = ''
try:
    SuffixesToIgnore
except NameError:
    SuffixesToIgnore = ''
try:
    MidWordPunctuation
except NameError:
    MidWordPunctuation = '-'
try:
    SkipBeforeVerse
except NameError:
    SkipBeforeVerse = '['


def _to_yes(value):
    try:
        return value.strip().lower() == 'yes'
    except AttributeError:
        return bool(value)


_include = {
    'toc_examiner_sp.py': _to_yes(IncludeToc),
    'Find_Titles_sp.py': _to_yes(IncludeTitles),
    'find_section_heads_sp.py': _to_yes(IncludeSectionHeads),
    'quotation_examiner_sp.py': _to_yes(IncludeQuotationMarks),
    'q_error_sp.py': _to_yes(IncludePoetryErrors),
    'report_nested_styles_sp.py': _to_yes(IncludeNestedStyles),
    'MarkerSpace.py': _to_yes(IncludeMarkerSpaces),
    'find_footnotes_sp.py': _to_yes(IncludeFootnotes),
    'Find_caption_sp.py': _to_yes(IncludeFigureCaptions),
    'capital_at_verse_sp.py': _to_yes(IncludeCapitalAtVerse),
}

_CAV_OPTIONS = {
    'FinalPunctuation': FinalPunctuation,
    'WordsToIgnore': WordsToIgnore,
    'IgnoreCapAfterQuote': IgnoreCapAfterQuote,
    'IgnoreBiblicalTerms': IgnoreBiblicalTerms,
    'IgnoreWordlistCapitals': IgnoreWordlistCapitals,
    'QuoteOpeningChars': QuoteOpeningChars,
    'IgnoreStyles': IgnoreStyles,
    'IgnoreParaStyles': IgnoreParaStyles,
    'PrefixesToIgnore': PrefixesToIgnore,
    'SuffixesToIgnore': SuffixesToIgnore,
    'MidWordPunctuation': MidWordPunctuation,
    'SkipBeforeVerse': SkipBeforeVerse,
}

# quotation_examiner.py's own QuoteCharacters/DashCharacters/MaxExamples
# guard fallbacks (used whenever those names aren't already defined) are
# never normally exercised by Paratext itself, since Paratext always
# injects a value matching quotation_examiner.cms's own \optionDefault for
# a declared option -- but All Reports doesn't forward this check's
# options, so its fallback path is the ONLY code path that actually runs
# under All Reports, and it turned out to be the first time this exact
# code had ever really executed. Rather than rely on it, forward these
# three explicitly here, built with unichr() (not literal characters) to
# stay ASCII-only in this file's own source -- these are exact matches for
# quotation_examiner.cms's own \optionDefault values, not new options of
# All_Reports.cms's own.
_QUOTE_EXAMINER_OPTIONS = {
    'QuoteCharacters': u' '.join([
        u'"', u"'", unichr(0x00ab), unichr(0x00bb), unichr(0x2039), unichr(0x203a),
        unichr(0x2018), unichr(0x2019), unichr(0x201a), unichr(0x201b),
        unichr(0x201c), unichr(0x201d), unichr(0x201e), unichr(0x201f),
        u'<', u'>', u'<<', u'>>',
    ]),
    'DashCharacters': u' '.join([unichr(0x2014), unichr(0x2015), unichr(0x2013)]),
    'MaxExamples': u'25',
}

# ---------------------------------------------------------------------------
# Required -- opens the project, redirects stdout. Called exactly once for
# the whole combined run; each sub-check's own setupCheck() call is
# neutralized below so it cannot reopen/re-redirect a second time.
# ---------------------------------------------------------------------------
checking.setupCheck()


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


def _to_utf8_bytes(s):
    if isinstance(s, type(u'')):
        return s.encode('utf-8')
    return s


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


def _attr_escape(s):
    return (s.replace(u'&', u'&amp;')
             .replace(u'"', u'&quot;')
             .replace(u'<', u'&lt;')
             .replace(u'>', u'&gt;'))


_directory = _project_directory()


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
    log_path = os.path.join(directory, u'AllReportsDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The ten checks, in the required order: (menu label, script filename,
# sibling check-folder name in this dev repo, output report filename).
# ---------------------------------------------------------------------------
_CHECKS = [
    (u'Informe de los TOC', 'toc_examiner_sp.py', 'Spanish_Tools', u'InformeExaminadorTOC.html'),
    (u'Informe de los títulos', 'Find_Titles_sp.py', 'Spanish_Tools', u'InformeTitulos.html'),
    (u'Informe de los encabezados de sección', 'find_section_heads_sp.py', 'Spanish_Tools', u'InformeEncabezadosSeccion.html'),
    (u'Informe de comillas', 'quotation_examiner_sp.py', 'Spanish_Tools', u'InformeExaminadorComillas.html'),
    (u'Informe de errores en q', 'q_error_sp.py', 'Spanish_Tools', u'InformeErroresQ.html'),
    (u'Informe de estilos anidados', 'report_nested_styles_sp.py', 'Spanish_Tools', u'InformeEstilosAnidados.html'),
    (u'Informe de espacios en marcadores', 'MarkerSpace.py', 'Spanish_Tools', u'MarkerSpaceReport.html'),
    (u'Informe de las notas al pie', 'find_footnotes_sp.py', 'Spanish_Tools', u'InformeNotasAlPie.html'),
    (u'Informe de leyendas de figuras', 'Find_caption_sp.py', 'Spanish_Tools', u'InformeDeFigura.html'),
    (u'Informe de mayúscula al inicio de versículo', 'capital_at_verse_sp.py', 'Spanish_Tools', u'CapitalAtVerseReport.html'),
]

_MAX_ROWS = 25

# Per-check config for regenerating a truncated report when a check's row
# list has more than _MAX_ROWS entries. 'style' selects how to re-invoke
# that script's own report-writing function after truncating row_var in
# its fresh globals dict (rebinding the dict entry is enough -- the
# function resolves the name against that same dict at call time, not at
# definition time):
#   'global_two_arg'  -- write_html_report(path, project); reads row_var
#                         itself, no explicit rows argument
#   'rows_param'       -- write_html_report(path, project_arg, rows); rows
#                          passed explicitly (project_arg=None means use
#                          the real Project value; some scripts pass their
#                          own hardcoded value instead, replicated here)
#   'zero_arg'         -- a differently-named function that takes no
#                          arguments at all and reads row_var itself
#
# Find_Titles.py, quotation_examiner.py, and MarkerSpace.py are deliberately
# absent: Find_Titles.py already lists every book unconditionally (capping
# it would cut off legitimate content on a 66-book project); the other two
# have no single row list -- they're already split into many per-bucket
# example lists, each already self-capped at their own MaxExamples option
# with its own "+N more not shown" note.
_TRUNCATE_CONFIG = {
    'toc_examiner_sp.py': {'row_var': '_report_rows', 'style': 'global_two_arg'},
    'find_section_heads_sp.py': {'row_var': '_report_rows', 'style': 'global_two_arg'},
    'q_error_sp.py': {'row_var': '_findings', 'style': 'rows_param', 'project_arg': u''},
    'report_nested_styles_sp.py': {'row_var': '_occurrences', 'style': 'global_two_arg'},
    'find_footnotes_sp.py': {'row_var': '_occurrences', 'style': 'global_two_arg'},
    'Find_caption_sp.py': {'row_var': '_report_rows', 'style': 'zero_arg', 'func': '_write_html_report_impl'},
    'capital_at_verse_sp.py': {'row_var': '_report_rows', 'style': 'rows_param', 'project_arg': None},
}


def _rerender_truncated(cfg, fresh_globals, report_path):
    style = cfg['style']
    if style == 'global_two_arg':
        fresh_globals['write_html_report'](report_path, fresh_globals.get('Project', Project))
    elif style == 'rows_param':
        project_arg = cfg.get('project_arg')
        if project_arg is None:
            project_arg = fresh_globals.get('Project', Project)
        fresh_globals['write_html_report'](report_path, project_arg, fresh_globals[cfg['row_var']])
    elif style == 'zero_arg':
        fresh_globals[cfg['func']]()


def _insert_before_close(html, note_html):
    marker = u'</body></html>'
    idx = html.rfind(marker)
    if idx == -1:
        return html + note_html
    return html[:idx] + note_html + html[idx:]


_own_dir = os.path.dirname(os.path.abspath(__file__))


def _resolve_script_path(filename, subfolder):
    # A real Paratext cms folder keeps every check's .cms/.py pair side by
    # side (flat) -- try that first. Fall back to this dev repo's layout,
    # where each check lives in its own folder alongside all_reports/.
    flat = os.path.join(_own_dir, filename)
    if os.path.isfile(flat):
        return flat
    sibling = os.path.join(os.path.dirname(_own_dir), subfolder, filename)
    if os.path.isfile(sibling):
        return sibling
    return None


class _Swallow(object):
    def __init__(self, wrapped):
        self._w = wrapped

    def write(self, s):
        pass

    def flush(self):
        try:
            self._w.flush()
        except Exception:
            pass

    def close(self):
        pass


_real_stdout = _sys.stdout
_real_setupCheck = checking.setupCheck
_real_startfile = os.startfile

_sections = []  # dicts: title, filename, html (or None), note (or None)

# NOTE: an earlier version of this file tried calling checking.checkAllChapters
# for real only once (for the first check that runs) and replaying its cached
# (reference, text, lastChapter) tuples into every later check instead of a
# fresh real call, on the theory that repeat real calls were corrupting
# scanned text. Live-tested and confirmed WORSE: two checks that had
# previously worked correctly (Report of Titles, Report of Section Heads)
# started reporting 0 books scanned, and Report of Quotation marks' own
# corruption got significantly worse rather than better. Reverted -- since
# the replay path is pure Python with no Paratext API calls in it at all,
# this points to the reference/text objects Paratext hands out not being
# safe to hold onto and reuse after the original call returns (likely a
# reused/mutated object internally), not merely to calling the real API
# more than once. Each check below once again calls the real
# checking.checkAllChapters independently, exactly as it did before that
# experiment.
_sys.stdout = _Swallow(_real_stdout)
checking.setupCheck = lambda: None
os.startfile = lambda *a, **k: None

try:
    for _title, _filename, _subfolder, _report_filename in _CHECKS:
        if not _include.get(_filename, True):
            _sections.append({'title': _title, 'filename': _filename, 'html': None,
                               'note': u'Omitido (desactivado por una opción).'})
            continue

        _script_path = _resolve_script_path(_filename, _subfolder)
        if not _script_path:
            _sections.append({'title': _title, 'filename': _filename, 'html': None,
                               'note': u'No se encontró el script: puede que esta verificación aún no esté instalada.'})
            continue

        _fresh_globals = {
            '__name__': '__main__',
            '__file__': _script_path,
            'Project': Project,
            'Books': Books,
            'Language': Language,
            'OutputFile': OutputFile,
        }
        if _filename == 'capital_at_verse_sp.py':
            _fresh_globals.update(_CAV_OPTIONS)
        if _filename == 'quotation_examiner_sp.py':
            _fresh_globals.update(_QUOTE_EXAMINER_OPTIONS)

        try:
            with open(_script_path, 'rb') as _f:
                _src = _f.read()
            # The translated scripts hold accented text. compile() of raw bytes ignores their
            # coding line under IronPython (the text came out garbled), so decode them first and
            # blank the coding cookie, which a unicode source may not carry (same line count).
            _src = _src.decode('utf-8')
            if _src.startswith(u'\ufeff'):
                _src = _src[1:]
            _src = re.sub(u'^([ \t\f]*#.*?)coding[:=]', u'\\1c0ding ', _src, count=2, flags=re.M)
            _code = compile(_src, _script_path, 'exec')
            exec(_code, _fresh_globals)
        except Exception as e:
            _log_crash(_title, e)
            _sections.append({'title': _title, 'filename': _filename, 'html': None,
                               'note': u'No se pudo ejecutar esta verificación: vea AllReportsDebug.log.'})
            continue

        _report_path = os.path.join(_directory, _report_filename) if _directory else None

        # If this check has more than _MAX_ROWS issues, regenerate its report
        # using the check's own write function with a truncated row list
        # (rather than slicing the finished HTML), so the truncated version
        # is rendered with the same real escaping/sorting/styling logic --
        # then overwrite the file it already wrote on disk.
        _truncated_total = None
        _cfg = _TRUNCATE_CONFIG.get(_filename)
        if _cfg and _report_path:
            try:
                _rows = _fresh_globals.get(_cfg['row_var'])
                if _rows is not None and len(_rows) > _MAX_ROWS:
                    _truncated_total = len(_rows)
                    _fresh_globals[_cfg['row_var']] = _rows[:_MAX_ROWS]
                    _rerender_truncated(_cfg, _fresh_globals, _report_path)
            except Exception as e:
                _log_crash(u'{0} (truncate)'.format(_title), e)
                _truncated_total = None

        _sub_html = None
        if _report_path and os.path.isfile(_report_path):
            try:
                with open(_open_path(_report_path), 'rb') as _f:
                    _sub_html = _f.read().decode('utf-8')
            except Exception as e:
                _log_crash(_title, e)
        if _sub_html is not None:
            if _truncated_total:
                _note_html = (
                    u'<p style="color:red;font-weight:bold">Se muestran los primeros {0} de {1} problemas encontrados. Ejecute "{2}" por separado para ver el resto.</p>'
                ).format(_MAX_ROWS, _truncated_total, _he(_title))
                _sub_html = _insert_before_close(_sub_html, _note_html)
            _sections.append({'title': _title, 'filename': _filename, 'html': _sub_html, 'note': None})
        else:
            _sections.append({'title': _title, 'filename': _filename, 'html': None,
                               'note': u'No se produjo ningún archivo de informe.'})
finally:
    _sys.stdout = _real_stdout
    checking.setupCheck = _real_setupCheck
    os.startfile = _real_startfile

# ---------------------------------------------------------------------------
# Build the combined report -- each sub-report is embedded via an iframe
# srcdoc so its own <style> block/class names never leak into another
# section (the ten scripts independently define overlapping class names
# such as .err/.missing with different meanings per script).
# ---------------------------------------------------------------------------


def _write_combined_report(html_path, project_name, sections):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Todos los informes</title>')
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px;margin:20px}')
    lines.append(u'h1{margin-bottom:4px}')
    lines.append(u'h2{margin-top:36px;border-top:3px solid #888;padding-top:10px}')
    lines.append(u'.note{color:#666;font-style:italic}')
    lines.append(u'iframe{width:100%;border:1px solid #ccc}')
    lines.append(u'ol{line-height:1.6}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Todos los informes</h1>')
    if project_name:
        lines.append(u'<p>Proyecto: <b>{0}</b></p>'.format(_he(project_name)))
    lines.append(u'<ol>')
    for i, sec in enumerate(sections):
        lines.append(u'<li><a href="#section{0}">{1}</a></li>'.format(i, _he(sec['title'])))
    lines.append(u'</ol>')
    for i, sec in enumerate(sections):
        lines.append(u'<h2 id="section{0}">{1}. {2} ({3})</h2>'.format(
            i, i + 1, _he(sec['title']), _he(sec['filename'])))
        if sec['html'] is not None:
            lines.append(
                u'<iframe srcdoc="{0}" '
                u'onload="this.style.height=(this.contentWindow.document.body.scrollHeight+40)+\'px\';">'
                u'</iframe>'.format(_attr_escape(sec['html'])))
        else:
            lines.append(u'<p class="note">{0}</p>'.format(_he(sec['note'] or u'')))
    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


if _directory:
    _combined_path = os.path.join(_directory, u'InformeTodosLosInformes.html')
    try:
        _write_combined_report(_combined_path, Project, _sections)
        os.startfile(_open_path(_combined_path))
        _sys.stdout.write(_to_utf8_bytes(u'# Ejecute cada verificacion por separado para ver la lista de problemas.\n'))
    except Exception as e:
        _log_crash(u'write_combined_report', e)
        _sys.stdout.write(_to_utf8_bytes(u'# Error al escribir el informe combinado; vea AllReportsDebug.log\n'))
else:
    _sys.stdout.write(_to_utf8_bytes(u'# Error: no se pudo determinar la carpeta del proyecto; no se escribio ningun informe.\n'))
