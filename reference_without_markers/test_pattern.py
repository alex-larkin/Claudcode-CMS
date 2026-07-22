# -*- coding: utf-8 -*-
import re, sys

_L    = u'[^\W\d_]'
_COMB = u'[̀-ͯؐ-ٟ᷀-᷿︠-︯]'
_BC   = u'(?:' + _L + _COMB + u'*)'
_CVS  = re.escape(u':')
_NBSP = u' '
_ENDASH = u'–'

_ORIG = re.compile(u'\\\\(?:fr|xo)\\b[^\\\\]*', re.UNICODE)

_pat = (
    u'(?<!\w)'
    u'(?:[123][ ' + _NBSP + u']' + _BC + u'{1,}'
    u'|' + _BC + u'{2,})'
    u'[ \t]+'
    u'\d{1,3}' + _CVS + u'\d{1,3}[a-z]?'
    u'(?:[-' + _ENDASH + u']\d{1,3}(?:' + _CVS + u'\d{1,3})?[a-z]?)?'
    u'(?:,[ ]?\d{1,3}[a-z]?(?:-\d{1,3}[a-z]?)?)*'
)
RE = re.compile(_pat, re.UNICODE)

def chk(desc, text, expected_count, expected_first=None, blank_orig=False):
    if blank_orig:
        text = _ORIG.sub(lambda m: u' ' * len(m.group(0)), text)
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
]

sys.stdout.write('\nAll passed: %s\n' % all(results))
