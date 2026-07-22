# -*- coding: utf-8 -*-
import checking
import re
import sys as _sys

_VERSE_TAG_RE = re.compile(ur'<Verse>(\d+)</Verse>', re.UNICODE)

try:
    Clickable
except NameError:
    Clickable = u'No'
if isinstance(Clickable, str):
    Clickable = Clickable.decode('utf-8')
_clickable = Clickable.strip().lower() == u'yes'

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


def convert_code(code):
    code = code.strip()
    if len(code) < 9:
        return None
    try:
        book_num = int(code[0:3])
        chapter  = int(code[3:6])
        verse    = int(code[6:9])
    except ValueError:
        return None
    if book_num < 1 or book_num > 66:
        return None
    return u'{} {}:{}'.format(BOOK_NAMES[book_num], chapter, verse)


def _read_clipboard():
    try:
        import ctypes
        import ctypes.wintypes
        CF_UNICODETEXT = 13
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        u32.OpenClipboard.argtypes    = [ctypes.wintypes.HWND]
        u32.OpenClipboard.restype     = ctypes.wintypes.BOOL
        u32.GetClipboardData.argtypes = [ctypes.c_uint]
        u32.GetClipboardData.restype  = ctypes.c_void_p
        k32.GlobalLock.argtypes       = [ctypes.c_void_p]
        k32.GlobalLock.restype        = ctypes.c_void_p
        k32.GlobalUnlock.argtypes     = [ctypes.c_void_p]
        k32.GlobalUnlock.restype      = ctypes.wintypes.BOOL
        if not u32.OpenClipboard(None):
            return u''
        try:
            handle = u32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return u''
            ptr = k32.GlobalLock(handle)
            if not ptr:
                return u''
            try:
                return ctypes.wstring_at(ptr)
            finally:
                k32.GlobalUnlock(handle)
        finally:
            u32.CloseClipboard()
    except Exception:
        return u''


checking.setupCheck()

_clipboard = _read_clipboard()
_xml_codes = _VERSE_TAG_RE.findall(_clipboard)
if _xml_codes:
    _lines = _xml_codes
else:
    _lines = [l.strip() for l in _clipboard.splitlines() if l.strip()]

if not _lines:
    _sys.stdout.write(u'# No codes found in clipboard. Copy a list of codes and run again.\n')
else:
    for _code in _lines:
        _ref = convert_code(_code)
        if _ref is not None:
            if _clickable:
                _sys.stdout.write(_ref + u'\t\t' + _code + u'\t\n')
            else:
                _sys.stdout.write(_ref + u'\n')
        else:
            _sys.stdout.write(u'# Invalid: ' + _code + u'\n')
