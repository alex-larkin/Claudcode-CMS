# -*- coding: utf-8 -*-
import re, sys

_L    = u'[^\W\d_]'
_COMB = u'[̀-ͯؐ-ٟ᷀-᷿︠-︯]'
_BC   = u'(?:' + _L + _COMB + u'*)'
_CVS  = re.escape(u':')
_NBSP = u' '
_ENDASH = u'–'

_ORIG = re.compile(u'\\\\(?:fr|xo)\\b[^\\\\]*', re.UNICODE)
_MARKED = re.compile(u'\\\\x\\s.*?\\\\x\\*', re.UNICODE | re.DOTALL)
_REM = re.compile(u'\\\\rem\\b[^\\\\]*', re.UNICODE)

_pat = (
    u'(?<!\w)'
    # Book-name prefix is optional -- a bare "1:11" with no book name matches too.
    u'(?:'
    u'(?:[123][ ' + _NBSP + u']' + _BC + u'{1,}'
    u'|' + _BC + u'{2,})'
    u'[ \t]+'
    u')?'
    u'\d{1,3}' + _CVS +
    u'(?!0{2,3}(?!\d))' +          # reject all-zero verse ("00"/"000")
    u'\d{1,3}[a-z]?'
    u'(?:[-' + _ENDASH + u']\d{1,3}(?:' + _CVS + u'\d{1,3})?[a-z]?)?'
    u'(?:,[ ]?\d{1,3}[a-z]?(?:-\d{1,3}[a-z]?)?)*'
)
RE = re.compile(_pat, re.UNICODE)

def chk(desc, text, expected_count, expected_first=None, blank_orig=False, blank_marked=False, blank_rem=False):
    if blank_marked:
        text = _MARKED.sub(lambda m: u' ' * len(m.group(0)), text)
    if blank_orig:
        text = _ORIG.sub(lambda m: u' ' * len(m.group(0)), text)
    if blank_rem:
        text = _REM.sub(lambda m: u' ' * len(m.group(0)), text)
    got = RE.findall(text)
    ok = len(got) == expected_count and (expected_first is None or (got and got[0] == expected_first))
    status = 'OK' if ok else 'FAIL'
    if not ok:
        sys.stdout.write('%s | %s | got_count=%d expected=%d\n' % (status, desc, len(got), expected_count))
    else:
        sys.stdout.write('%s | %s\n' % (status, desc))
    return ok

results = [
    chk('Mat 5:12',           u'Mat 5:12',                   1, u'Mat 5:12'),
    chk('1 S 31:3-5',         u'1 S 31:3-5',                 1, u'1 S 31:3-5'),
    chk('Lc 9:37-43a',        u'Lc 9:37-43a',                1, u'Lc 9:37-43a'),
    chk('Mr 8:31-9:1 endash', u'Mr 8:31–9:1',           1),
    chk('Lc 22:54-55,63-71',  u'Lc 22:54-55, 63-71',        1, u'Lc 22:54-55, 63-71'),
    chk('multi-book 3 matches', u'(Mr 14:53-65; Lc 22:54-55, 63-71; Jn 18:13-14, 19-24)', 3),
    # No upper bound on book-token length anymore (see reference_without_markers.py
    # comments) -- accepted trade-off: a long ordinary word before "N:N" now matches.
    chk('Israelitas (accepted false positive)', u'Israelitas 5:3', 1),
    chk('no refs',            u'un texto sin referencias',    0),
    chk('Genesis full name',  u'Génesis 25:26',             1, u'Génesis 25:26'),
    chk('Genesis endash range', u'Génesis 36:8–9',          1, u'Génesis 36:8–9'),
    chk('numbered full name', u'1 Corintios 5:3',           1, u'1 Corintios 5:3'),
    # NFD form: E (U+0045) + combining acute (U+0301) = é-like, treated as 2 code points
    chk('NFD Ex 3:14',        u'Éx 3:14',              1),
    # Greek letters (Unicode block U+0391-03C9)
    chk('Greek abbrev',       u'Αρ 5:3',           1),
    # Hebrew letters (Unicode block U+05D0-05EA)
    chk('Hebrew abbrev',      u'אב 5:3',           1),
    chk('\\fr origin skipped', u'\\fr 5:12 \\ft See Mat 5:12.', 1, blank_orig=True),
    chk('\\xo origin skipped', u'\\xo Mt 5:12 \\ft text', 0, blank_orig=True),

    # Book-less bare references (no book name at all).
    chk('bare 1:11, no book',            u'1:11',                    1, u'1:11'),
    chk('bare 1:1-9 after single-letter word', u'Texto y 1:1-9 fin', 1, u'1:1-9'),
    chk('bare cross-chapter, no book',   u'y 1:10–4:21 después',     1, u'1:10–4:21'),

    # All-zero verse ("00"/"000") excluded as a decimal-number artifact.
    chk('all-zero verse 00 excluded',    u'Costó 50:00 soles',       0),
    chk('all-zero verse 000 excluded',   u'Código 12:000 no aplica', 0),
    chk('verse 01 (not all-zero) still flagged', u'Vea 4:01 mañana', 1),

    # Existing exclusions still apply to the book-less form.
    chk('bare ref inside \\x...\\x* still excluded', u'\\x + \\xt 1:11\\x*', 0, blank_marked=True),
    chk('\\fr bare origin excluded, later bare ref in \\ft still flagged',
        u'\\fr 1:11 \\ft See 4:21.', 1, blank_orig=True),

    # \rem (remark) comments are translator notes, not project text -- refs inside excluded.
    chk('\\rem comment excluded',      u'\\rem see 5:12 for background', 0, blank_rem=True),
    chk('\\rem excluded, later bare ref still flagged',
        u'\\rem see 5:12 for background \\v 1 Texto 4:21 aqui', 1, blank_rem=True),
    chk('bare ref before \\rem still flagged',
        u'Texto 4:21 \\rem nota interna 5:12', 1, blank_rem=True),
]

sys.stdout.write('\nAll passed: %s\n' % all(results))
