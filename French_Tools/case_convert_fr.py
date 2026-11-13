# -*- coding: utf-8 -*-
import checking
import re
import unicodedata
import sys as _sys

# ---------------------------------------------------------------------------
# Guard option variables injected by Paratext
# ---------------------------------------------------------------------------
try:
    CheckLowercase
except NameError:
    CheckLowercase = 'Yes'

try:
    CheckUppercase
except NameError:
    CheckUppercase = 'Yes'

try:
    MinLetters
except NameError:
    MinLetters = '2'

try:
    FilterWord
except NameError:
    FilterWord = u''

# Paratext injects option values as UTF-8 byte strings in Python 2
if isinstance(CheckLowercase, str):
    CheckLowercase = CheckLowercase.decode('utf-8')
if isinstance(CheckUppercase, str):
    CheckUppercase = CheckUppercase.decode('utf-8')
if isinstance(MinLetters, str):
    MinLetters = MinLetters.decode('utf-8')
if not isinstance(FilterWord, type(u'')):
    for _enc in ('utf-8', 'mbcs', 'latin-1'):
        try:
            FilterWord = FilterWord.decode(_enc)
            break
        except Exception:
            pass
    else:
        FilterWord = u''

_check_lower = str(CheckLowercase).strip().lower() == u'yes'
_check_upper = str(CheckUppercase).strip().lower() == u'yes'
try:
    _min_letters = int(str(MinLetters).strip())
except ValueError:
    _min_letters = 2
_filter_phrase = FilterWord.strip() if hasattr(FilterWord, 'strip') else u''

# ---------------------------------------------------------------------------
# Preprocessing patterns (replace matches with equal-length spaces to
# preserve character offsets into the original text)
# ---------------------------------------------------------------------------

# Blank footnote, cross-ref, and figure spans
INLINE_RE = re.compile(
    ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*|\\fig\s.*?\\fig\*',
    re.UNICODE | re.DOTALL)

# Blank USFM marker tags: \v, \q2, \wj*, \nd*, etc.
MARKER_RE = re.compile(ur'\\[a-zA-Z]+\d*\*?', re.UNICODE)

def _blank(text):
    # INLINE_RE must run first so \f/\x tags are consumed before MARKER_RE
    text = INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), text)
    text = MARKER_RE.sub(lambda m: u' ' * len(m.group(0)), text)
    return text

# ---------------------------------------------------------------------------
# Unicode-aware word finder
# ---------------------------------------------------------------------------

def _find_words(text):
    """
    Yield (start, end) index pairs for each word in text.

    A word begins at any Unicode Letter (category L*) and continues
    through Letters and Combining Marks (M*). This keeps base letters
    and their diacritic combining sequences together — e.g. bɛ̃̀ɛ̃ is
    one word even though the tildes/graves are not matched by \w.
    """
    i = 0
    n = len(text)
    while i < n:
        if unicodedata.category(text[i])[0] == u'L':
            start = i
            i += 1
            while i < n:
                cat = unicodedata.category(text[i])[0]
                if cat == u'L' or cat == u'M':
                    i += 1
                else:
                    break
            yield (start, i)
        else:
            i += 1

# ---------------------------------------------------------------------------
# Case helpers
# ---------------------------------------------------------------------------

def _classify(word):
    """
    Return ('all_lower'|'all_upper'|'mixed'|None, letter_count).
    Returns None when letter_count < _min_letters.
    Letters with no case (category Lo, Lm, Lt) make the result 'mixed'.
    """
    has_lower = False
    has_upper = False
    letter_count = 0
    for ch in word:
        cat = unicodedata.category(ch)
        if cat == u'Ll':
            has_lower = True
            letter_count += 1
        elif cat == u'Lu':
            has_upper = True
            letter_count += 1
        elif cat[0] == u'L':
            letter_count += 1  # Lo/Lm/Lt: counts toward min but no case info
    if letter_count < _min_letters:
        return None, letter_count
    if has_lower and not has_upper:
        return u'all_lower', letter_count
    if has_upper and not has_lower:
        return u'all_upper', letter_count
    return u'mixed', letter_count

def _to_upper(word):
    return u''.join(
        ch.upper() if unicodedata.category(ch)[0] == u'L' else ch
        for ch in word)

def _to_lower(word):
    return u''.join(
        ch.lower() if unicodedata.category(ch)[0] == u'L' else ch
        for ch in word)

def _to_title(word):
    """Uppercase the first letter of each word; leave all other characters unchanged."""
    result = list(word)
    at_word_start = True
    for i, ch in enumerate(word):
        cat = unicodedata.category(ch)[0]
        if cat == u'L':
            if at_word_start:
                result[i] = ch.upper()
            at_word_start = False
        elif cat != u'M':
            at_word_start = True
    return u''.join(result)

def _to_sentence(word):
    """Keep first letter unchanged; lowercase every subsequent letter."""
    result = list(word)
    first_seen = False
    for i, ch in enumerate(word):
        if unicodedata.category(ch)[0] == u'L':
            if first_seen:
                result[i] = ch.lower()
            else:
                first_seen = True
    return u''.join(result)

def _read_clipboard():
    try:
        import ctypes
        import ctypes.wintypes
        CF_UNICODETEXT = 13
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        u32.OpenClipboard.argtypes  = [ctypes.wintypes.HWND]
        u32.OpenClipboard.restype   = ctypes.wintypes.BOOL
        u32.GetClipboardData.argtypes = [ctypes.c_uint]
        u32.GetClipboardData.restype  = ctypes.c_void_p
        k32.GlobalLock.argtypes   = [ctypes.c_void_p]
        k32.GlobalLock.restype    = ctypes.c_void_p
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.restype  = ctypes.wintypes.BOOL
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

# ---------------------------------------------------------------------------
checking.setupCheck()
# ---------------------------------------------------------------------------

class _StripCRLF(object):
    def __init__(self, wrapped):
        self._w = wrapped
        self._bin = getattr(wrapped, 'buffer', None)

    def _emit(self, u):
        if not isinstance(u, bytes):
            u = u.encode('utf-8', 'replace')
        if self._bin is not None:
            self._bin.write(u)
            self._bin.flush()
        else:
            try:
                self._w.write(u)
            except TypeError:
                self._w.write(u.decode('utf-8', 'replace'))

    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                text = re.sub(ur'^\[\d+\]', u'', text)
                text = text.replace(u'\r', u'').replace(u'\n', u' ')
                msg  = msg.rstrip(u'\n').replace(u'\r', u'')
                self._emit(ref + u'\t\t' + text + u'\t' + msg + u'\n')
                return
            except ValueError:
                pass
        self._emit(s)

    def flush(self):
        try:
            (self._bin or self._w).flush()
        except Exception:
            pass

    def close(self):
        try:
            (self._bin or self._w).flush()
        except Exception:
            pass
        try:
            self._w.close()
        except Exception:
            pass

try:
    _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass
_sys.stdout = _StripCRLF(_sys.stdout)

# ---------------------------------------------------------------------------

def checkChapter(reference, text, lastChapter):
    blanked = _blank(text)
    for start, end in _find_words(blanked):
        word = text[start:end]
        case, _ = _classify(word)

        if case == u'all_lower' and _check_lower:
            msg = u'Majuscules : ' + _to_upper(word) + u'   Titre : ' + _to_title(word)
            checking.outputError(start, end, msg)

        elif case == u'all_upper' and _check_upper:
            msg = u'Minuscules : ' + _to_lower(word) + u'   Phrase : ' + _to_sentence(word)
            checking.outputError(start, end, msg)

def _write(phrase, label, converted):
    _sys.stdout.write(phrase + u'\n' + label + u' : ' + converted + u'\n')

_clipboard = _read_clipboard().strip()
if _clipboard:
    _filter_phrase = _clipboard

if _filter_phrase:
    case, count = _classify(_filter_phrase)
    if count == 0 or case is None:
        _sys.stdout.write(u'# Aucun resultat : mot trop court ou sans lettres\n')
    elif case == u'all_lower':
        _write(_filter_phrase, u'Majuscules', _to_upper(_filter_phrase))
        _write(_filter_phrase, u'Titre', _to_title(_filter_phrase))
    elif case == u'all_upper':
        _write(_filter_phrase, u'Minuscules', _to_lower(_filter_phrase))
        _write(_filter_phrase, u'Phrase', _to_sentence(_filter_phrase))
    else:
        _write(_filter_phrase, u'Majuscules', _to_upper(_filter_phrase))
        _write(_filter_phrase, u'Minuscules', _to_lower(_filter_phrase))
        _write(_filter_phrase, u'Titre', _to_title(_filter_phrase))
        _write(_filter_phrase, u'Phrase', _to_sentence(_filter_phrase))
else:
    checking.checkAllChapters(checkChapter)

if __name__ == '__main__':
    try:
        _input = raw_input  # Python 2
    except NameError:
        _input = input      # Python 3

    while True:
        try:
            entry = _input(u'Quel mot ou quelle expression ? ')
        except EOFError:
            break
        if hasattr(entry, 'decode'):
            entry = entry.decode('utf-8')
        word = entry.strip()
        if not word:
            break
        case, count = _classify(word)
        if count == 0:
            print(u'Aucune lettre dans : ' + word)
        elif case is None:
            print(u'Le mot est trop court (moins de ' + str(_min_letters) + u' lettres).')
        elif case == u'all_lower':
            print(u'Majuscules : ' + _to_upper(word) + u'   Titre : ' + _to_title(word))
        elif case == u'all_upper':
            print(u'Minuscules : ' + _to_lower(word) + u'   Phrase : ' + _to_sentence(word))
        else:
            print(u'Casse mixte - toutes les conversions :')
            print(u'  Majuscules :  ' + _to_upper(word))
            print(u'  Minuscules :  ' + _to_lower(word))
            print(u'  Titre :       ' + _to_title(word))
            print(u'  Phrase :      ' + _to_sentence(word))
