# -*- coding: utf-8 -*-
import checking
import os
import re
import sys as _sys
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

# Safety defaults - Paratext injects these from the CMS options, but guard
# against NameError in case the check is run outside a normal Paratext context.
try:
    FinalPunctuation
except NameError:
    FinalPunctuation = ".!?"
try:
    NonFinalPunctuation
except NameError:
    NonFinalPunctuation = ",;:"
try:
    CheckFinalPunct
except NameError:
    CheckFinalPunct = "Yes"
try:
    CheckDoubleVerse
except NameError:
    CheckDoubleVerse = "Yes"
try:
    CheckTextBeforeVerse
except NameError:
    CheckTextBeforeVerse = "Yes"
try:
    CheckHangingWord
except NameError:
    CheckHangingWord = "No"
try:
    MinCharsBeforePunct
except NameError:
    MinCharsBeforePunct = "0"

# Must be called first - opens the project text and initializes globals
checking.setupCheck()

# Wrap stdout to put the message type first so the list can be sorted by problem.
# outputError writes: REF\t\t[cnt]TEXT\tMSG\n  — we reorder to MSG\tREF\t\tTEXT\n.

# Matches a line that opens with a poetry marker followed immediately by a verse
# marker, e.g. "\q1 \v 7" or "\q2 \v 12".  Group 1 captures the verse number.
_Q_VERSE_RE = re.compile(r'\\q\d?[ \t]+\\v[ \t]+(\d+)')

class _ReorderOutput(object):
    def __init__(self, wrapped):
        self._w = wrapped
        self.last_ref = None
    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                text = re.sub(r'^\[\d+\]', '', text)
                text = text.replace('\\u000d', '').replace('\\u000a', ' ')
                msg  = msg.rstrip('\n')
                # When the text begins with \q\d \v N, outputError was called
                # with a begin offset before the verse marker, so the checking
                # module reported the previous verse.  Correct it here.
                qv = _Q_VERSE_RE.match(text)
                if qv:
                    ref = re.sub(r':\d+$', ':' + qv.group(1), ref)
                self.last_ref = ref
                self._w.write(ref + '\t\t' + msg + '\t' + text + '\n')
                return
            except ValueError:
                pass
        self._w.write(s)
    def flush(self):
        self._w.flush()
    def close(self):
        self._w.close()

_sys.stdout = _ReorderOutput(_sys.stdout)

# Match inline footnotes (\f...\f*), cross-refs (\x...\x*), and \qs...\qs* on one line.
# We replace matches with equal-length spaces so error positions remain valid.
INLINE_RE = re.compile(
    ur'\\f\s[^\r\n]*?\\f\*|\\x\s[^\r\n]*?\\x\*|\\qs\s[^\r\n]*?\\qs\*|\\fig\s[^\r\n]*?\\fig\*'
    ur'|\\[a-z]+\*',
    re.UNICODE
)

def blank_inline(text):
    return INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)


def make_char_class(chars):
    result = u'['
    for c in chars:
        if c in u'\\]^-':
            result += u'\\' + c
        else:
            result += c
    result += u']'
    return result


def build_patterns():
    if CheckFinalPunct == "Yes" and not FinalPunctuation:
        print u'# Option "Caracteres de ponctuation finale" vide alors que "Signaler la ponctuation finale suivie de texte ?" vaut Yes'
        return None

    if CheckHangingWord == "Yes" and not NonFinalPunctuation:
        print u'# Option "Caracteres de ponctuation non finale" vide alors que "Signaler une ligne finissant par une ponctuation + un seul mot ?" vaut Yes'
        return None

    try:
        min_chars = max(0, int(MinCharsBeforePunct))
    except ValueError:
        min_chars = 0

    # [ \t\r\n]+ allows any whitespace after the marker, including a newline when
    # the poetry marker sits on its own line and content follows on the next line.
    q = ur'\\q[12]?[ \t\r\n]+'
    eol = ur'[ \t]*\r?\n[ \t]*'   # trailing spaces, newline, optional leading spaces on next line

    # {min_chars,}? requires at least min_chars characters of text before a final
    # punctuation character is considered.  When min_chars=0 this is identical to *?.
    before_punct = ur'[^\r\n]{' + unicode(min_chars) + ur',}?'

    p1a = p1b = None
    if CheckFinalPunct == "Yes":
        punct_class = make_char_class(FinalPunctuation)

        # Pattern 1a: final punct followed by a word character on the SAME line.
        # Group 1 (the highlight trigger) is the final punctuation character itself.
        p1a = re.compile(
            q + before_punct + u'(' + punct_class + u')' + ur'(?=[^\r\n]*\w)',
            re.UNICODE | re.MULTILINE
        )

        # Pattern 1b: poetry line ends with final punct then newline, and the very
        # next line opens with \v N (no intervening \q marker).
        # Group 1 (the highlight trigger) is the \v marker that follows final punctuation.
        p1b = re.compile(
            q + before_punct + punct_class + eol + u'(' + ur'\\v\s' + u')',
            re.UNICODE | re.MULTILINE
        )

    p2a = p2b = None
    if CheckDoubleVerse == "Yes":
        # Pattern 2a: a poetry line containing two \v markers on the SAME line.
        # Group 1 (the highlight trigger) is the SECOND \v marker.
        p2a = re.compile(
            q + ur'[^\r\n]*\\v\s+\d+[^\r\n]*(' + ur'\\v\s' + u')',
            re.UNICODE | re.MULTILINE
        )

        # Pattern 2b: a poetry line with \v N, then a newline, then another \v N.
        # Group 1 (the highlight trigger) is the second \v marker (after the newline).
        p2b = re.compile(
            q + ur'[^\r\n]*\\v\s+\d+[^\r\n]*' + eol + u'(' + ur'\\v\s' + u')',
            re.UNICODE | re.MULTILINE
        )

    p3 = None
    if CheckTextBeforeVerse == "Yes":
        # Pattern 3: non-whitespace, non-marker text appears before a \v.
        # Normal form: \q1 \v 5 text or \q1\n\v 5 text.
        # Bad form: \q1 text \v 5 or \q1 text\n\v 5.
        # (?:\r?\n[ \t]*)? allows the \v to appear on the line after the text.
        # Group 1 (the highlight trigger) is the misplaced text that wrongly precedes \v.
        p3 = re.compile(
            q + u'(' + ur'[ \t]*[^ \t\r\n\\][^\r\n]*(?:\r?\n[ \t]*)?' + u')' + ur'\\v\s',
            re.UNICODE | re.MULTILINE
        )

    p4 = None
    if CheckHangingWord == "Yes":
        non_final_class = make_char_class(NonFinalPunctuation)
        # \r?$ handles CRLF files where \r sits between the last word and \n.
        # Group 1 (the highlight trigger) is the non-final punctuation plus the hanging word.
        p4 = re.compile(
            q + ur'[^\r\n]*(' + non_final_class + ur'[ \t]+\w+' + u')' + ur'[ \t]*(?=\r?$|\\q)',
            re.UNICODE | re.MULTILINE
        )

    return p1a, p1b, p2a, p2b, p3, p4


try:
    compiled = build_patterns()
except Exception, e:
    print u'# q_error : impossible de construire les motifs : ' + str(e)
    compiled = None


# ---------------------------------------------------------------------------
# HTML report support
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


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


_WS_RUN_RE = re.compile(ur'[ \t]+', re.UNICODE)


def _collapse_ws(s):
    return _WS_RUN_RE.sub(u' ', s.replace(u'\r', u'').replace(u'\n', u' '))


_directory = _project_directory()
_links_on = _ptx_goto is not None and _ptx_goto.enabled(_directory)


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
    log_path = os.path.join(directory, u'ErreursQDebug.log')
    try:
        with open(_open_path(log_path), 'ab') as f:
            f.write(u'--- {0} ---\n'.format(label).encode('utf-8'))
            f.write(tb_text.encode('utf-8', 'replace'))
            f.write(u'\n'.encode('utf-8'))
    except Exception:
        pass


# Fixed section order for the HTML report; any unrecognized message (there
# shouldn't be one) is appended after these.
_MSG_ORDER = [
    u'Ponctuation finale dans q',
    u'Verset dans q',
    u'Ligne de poesie sur plusieurs versets',
    u'Mot seul apres une ponctuation',
]

_findings = []   # {'ref':, 'msg':, 'html':}


def _line_end(processed_text, line_start):
    # Walks forward one physical line at a time from the \q marker, extending
    # across a newline only when the next line opens with \v -- mirroring the
    # same eol + \v construct the patterns above already use to recognize a
    # verse marker as continuing the SAME poetry line rather than ending it.
    n = len(processed_text)
    qm = re.match(ur'\\q[12]?[ \t\r\n]+', processed_text[line_start:n], re.UNICODE)
    pos = line_start + (qm.end() if qm else 0)
    while True:
        nl = re.search(ur'\r?\n', processed_text[pos:n], re.UNICODE)
        if not nl:
            return n
        line_end_here = pos + nl.start()
        after = pos + nl.end()
        wsm = re.match(ur'[ \t]*', processed_text[after:n], re.UNICODE)
        after_ws = after + wsm.end()
        if re.match(ur'\\v\s', processed_text[after_ws:n], re.UNICODE):
            pos = after_ws
            continue
        return line_end_here


# Display only: the \q line in the HTML report is shown without footnotes,
# cross-references, \qs and \fig spans, and without character markers that
# open and close on the line (\nd Mukama\nd* -> Mukama), so no stray marker or
# space is left behind. Marker names are compared ignoring case (\ND...\ND*);
# a closing marker also takes a |attribute part in front of it.
_DISPLAY_DROP_RE = re.compile(
    ur'\\f\s[^\r\n]*?\\f\*|\\x\s[^\r\n]*?\\x\*|\\qs\s[^\r\n]*?\\qs\*|\\fig\s[^\r\n]*?\\fig\*'
    ur'|(?:\|[^\\\r\n]*)?\\\+?([A-Za-z]+\d*)\*',
    re.UNICODE)
_DISPLAY_OPEN_RE = re.compile(ur'\\\+?([A-Za-z]+\d*)[ ]', re.UNICODE)


def _display_parts(text, start, trig_start, trig_end, line_end):
    # Returns the text before the trigger, the trigger and the text after it
    # (up to line_end), with the dropped spans and markers removed.
    drop = set()
    for m in _DISPLAY_DROP_RE.finditer(text, start, line_end):
        drop.update(xrange(m.start(), m.end()))
        name = m.group(1)
        if name:
            opener = None
            for o in _DISPLAY_OPEN_RE.finditer(text, start, m.start()):
                if o.group(1).lower() == name.lower():
                    opener = o
            if opener is not None:
                drop.update(xrange(opener.start(), opener.end()))

    def part(a, b):
        return u''.join(text[i] for i in xrange(a, b) if i not in drop)
    return (part(start, trig_start), part(trig_start, trig_end),
            part(trig_end, max(trig_end, line_end)))


def write_html_report(html_path, project_name, findings):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html><head><meta charset="utf-8">')
    lines.append(u'<title>Rapport des erreurs de q</title>')
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse;margin-bottom:12px}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px;vertical-align:top}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'h2{margin-top:28px}')
    lines.append(u'.err{color:#c00;font-weight:bold}')
    lines.append(u'.err-period{font-size:calc(1em + 2pt)}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h1>Rapport des erreurs de q</h1>')
    if _links_on:
        lines.append(_ptx_goto.hint_html('fr'))
    if project_name:
        lines.append(u'<p>Projet : <b>{0}</b></p>'.format(_he(project_name)))

    if not findings:
        lines.append(u'<p><i>Aucun problème trouvé.</i></p>')
    else:
        by_msg = {}
        for f in findings:
            by_msg.setdefault(f['msg'], []).append(f)
        ordered_msgs = [m for m in _MSG_ORDER if m in by_msg]
        ordered_msgs += [m for m in by_msg if m not in _MSG_ORDER]
        for msg in ordered_msgs:
            group = by_msg[msg]
            lines.append(u'<h2>{0} ({1})</h2>'.format(_he(msg), len(group)))
            lines.append(u'<table><tr><th>Référence</th><th>Ligne \\q</th></tr>')
            for f in group:
                lines.append(u'<tr><td><b>{0}</b></td><td>{1}</td></tr>'.format(
                    _ref_link(_he(f['ref']), _goto(f['ref'])), f['html']))
            lines.append(u'</table>')

    lines.append(u'</body></html>')
    html = u'\n'.join(lines)
    with open(_open_path(html_path), 'wb') as f:
        f.write(html.encode('utf-8'))


def _checkChapter_impl(reference, text, lastChapter):
    if compiled is None:
        return
    # Ensure unicode so regex \w etc. work correctly on accented characters.
    if not isinstance(text, unicode):
        text = text.decode('utf-8')
        checking.text = text   # keep module global in sync for outputError
    p1a, p1b, p2a, p2b, p3, p4 = compiled
    processed = blank_inline(text)

    reported = set()

    def report(start, end, msg, trig_start, trig_end):
        if start not in reported:
            reported.add(start)
            # Patterns end on the whitespace after \v; extend to include the
            # verse number so the text column shows e.g. "\v 4" not "\v ".
            vm = re.match(ur'\d+', text[end:end+6], re.UNICODE)
            ext = vm.end() if vm else 0
            checking.outputError(start, end + ext, msg)

            # The trigger group ends exactly at the match end for p1a/p1b/p2a/p2b
            # (their \v marker or punctuation is the last thing matched), so it
            # gets the same verse-digit extension; p3/p4's trigger ends earlier
            # in the match and is left alone.
            te = trig_end + ext if trig_end == end else trig_end
            ref = getattr(_sys.stdout, 'last_ref', None)
            line_end = _line_end(processed, start)
            before, trig_text, after = _display_parts(text, start, trig_start, te, line_end)
            # A bare period is easy to miss in a wall of text -- bump it up
            # 2pt so it stands out; other final-punctuation characters (!, ?)
            # are already visually distinct enough on their own.
            err_class = u'err err-period' if (msg == u'Ponctuation finale dans q' and trig_text == u'.') else u'err'
            html_line = u'{0}<span class="{1}">{2}</span>{3}'.format(
                _he(_collapse_ws(before)),
                err_class,
                _he(_collapse_ws(trig_text)),
                _he(_collapse_ws(after)))
            _findings.append({'ref': ref or u'?', 'msg': msg, 'html': html_line})

    if p1a is not None:
        for m in p1a.finditer(processed):
            report(m.start(), m.end(), u'Ponctuation finale dans q', m.start(1), m.end(1))

    if p1b is not None:
        for m in p1b.finditer(processed):
            report(m.start(), m.end(), u'Verset dans q', m.start(1), m.end(1))

    if p2a is not None:
        for m in p2a.finditer(text):
            report(m.start(), m.end(), u'Ligne de poesie sur plusieurs versets', m.start(1), m.end(1))

    if p2b is not None:
        for m in p2b.finditer(text):
            report(m.start(), m.end(), u'Verset dans q', m.start(1), m.end(1))

    if p3 is not None:
        for m in p3.finditer(text):
            report(m.start(), m.end(), u'Verset dans q', m.start(1), m.end(1))

    if p4 is not None:
        for m in p4.finditer(text):
            report(m.start(), m.end(), u'Mot seul apres une ponctuation', m.start(1), m.end(1))


def checkChapter(reference, text, lastChapter):
    try:
        _checkChapter_impl(reference, text, lastChapter)
    except Exception as e:
        _log_crash(u'checkChapter', e)


if compiled is not None:
    checking.checkAllChapters(checkChapter)

    if _directory:
        _html_path = os.path.join(_directory, u'RapportErreursQ.html')
        try:
            write_html_report(_html_path, u'', _findings)
            os.startfile(_open_path(_html_path))
            _sys.stdout.write(u'# Rapport HTML : {0}\n'.format(_html_path))
        except Exception as e:
            _log_crash(u'write_html_report', e)
            _sys.stdout.write(u'# Erreur pendant la creation du rapport HTML ; voir ErreursQDebug.log\n')
    else:
        _sys.stdout.write(u'# Erreur : dossier du projet introuvable ; aucun rapport HTML.\n')
