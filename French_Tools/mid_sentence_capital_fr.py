# -*- coding: utf-8 -*-
import checking
import os
import re
import sys as _sys
import unicodedata
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Option guards
# ---------------------------------------------------------------------------

try:
    FinalPunctuation
except NameError:
    FinalPunctuation = '.!?'
if not isinstance(FinalPunctuation, type(u'')):
    try:
        FinalPunctuation = FinalPunctuation.decode('utf-8')
    except UnicodeDecodeError:
        FinalPunctuation = FinalPunctuation.decode('mbcs')
_final_set = set(FinalPunctuation)
_final_set.add(unichr(0x00a1))  # inverted exclamation (always sentence-opening)
_final_set.add(unichr(0x00bf))  # inverted question mark (always sentence-opening)

try:
    WordsToIgnore
except NameError:
    WordsToIgnore = ''
if not isinstance(WordsToIgnore, type(u'')):
    try:
        WordsToIgnore = WordsToIgnore.decode('utf-8')
    except UnicodeDecodeError:
        WordsToIgnore = WordsToIgnore.decode('mbcs')
_ignore_words = frozenset(unicodedata.normalize('NFC', w.strip()) for w in WordsToIgnore.split(u',') if w.strip())
_ignore_words_lower = frozenset(w.lower() for w in _ignore_words)

try:
    IgnoreCapAfterQuote
except NameError:
    IgnoreCapAfterQuote = 'No'
if not isinstance(IgnoreCapAfterQuote, type(u'')):
    try:
        IgnoreCapAfterQuote = IgnoreCapAfterQuote.decode('utf-8')
    except UnicodeDecodeError:
        IgnoreCapAfterQuote = IgnoreCapAfterQuote.decode('mbcs')
_ignore_cap_after_quote = IgnoreCapAfterQuote.strip().lower() == u'yes'

try:
    IgnoreBiblicalTerms
except NameError:
    IgnoreBiblicalTerms = 'Yes'
if not isinstance(IgnoreBiblicalTerms, type(u'')):
    try:
        IgnoreBiblicalTerms = IgnoreBiblicalTerms.decode('utf-8')
    except UnicodeDecodeError:
        IgnoreBiblicalTerms = IgnoreBiblicalTerms.decode('mbcs')
_ignore_bt = IgnoreBiblicalTerms.strip().lower() == u'yes'

try:
    IgnoreWordlistCapitals
except NameError:
    IgnoreWordlistCapitals = 'Yes'
if not isinstance(IgnoreWordlistCapitals, type(u'')):
    try:
        IgnoreWordlistCapitals = IgnoreWordlistCapitals.decode('utf-8')
    except UnicodeDecodeError:
        IgnoreWordlistCapitals = IgnoreWordlistCapitals.decode('mbcs')
_ignore_wordlist = IgnoreWordlistCapitals.strip().lower() == u'yes'

try:
    QuoteOpeningChars
except NameError:
    QuoteOpeningChars = unichr(0x00ab) + unichr(0x201c) + unichr(0x2014) + unichr(0x2018)
if not isinstance(QuoteOpeningChars, type(u'')):
    try:
        QuoteOpeningChars = QuoteOpeningChars.decode('utf-8')
    except UnicodeDecodeError:
        QuoteOpeningChars = QuoteOpeningChars.decode('mbcs')
_quote_openers = frozenset(QuoteOpeningChars.strip()) if QuoteOpeningChars.strip() else None

try:
    IgnoreStyles
except NameError:
    IgnoreStyles = ''
if not isinstance(IgnoreStyles, type(u'')):
    try:
        IgnoreStyles = IgnoreStyles.decode('utf-8')
    except UnicodeDecodeError:
        IgnoreStyles = IgnoreStyles.decode('mbcs')
_ignore_style_names = [s.strip().lstrip(u'\\') for s in IgnoreStyles.split(u',') if s.strip()]

try:
    IgnoreParaStyles
except NameError:
    IgnoreParaStyles = 'sp, r, ms, mr, sr'
if not isinstance(IgnoreParaStyles, type(u'')):
    try:
        IgnoreParaStyles = IgnoreParaStyles.decode('utf-8')
    except UnicodeDecodeError:
        IgnoreParaStyles = IgnoreParaStyles.decode('mbcs')
_ignore_para_names = [s.strip().lstrip(u'\\') for s in IgnoreParaStyles.split(u',') if s.strip()]

try:
    PrefixesToIgnore
except NameError:
    PrefixesToIgnore = ''
if not isinstance(PrefixesToIgnore, type(u'')):
    try:
        PrefixesToIgnore = PrefixesToIgnore.decode('utf-8')
    except UnicodeDecodeError:
        PrefixesToIgnore = PrefixesToIgnore.decode('mbcs')
try:
    SuffixesToIgnore
except NameError:
    SuffixesToIgnore = ''
if not isinstance(SuffixesToIgnore, type(u'')):
    try:
        SuffixesToIgnore = SuffixesToIgnore.decode('utf-8')
    except UnicodeDecodeError:
        SuffixesToIgnore = SuffixesToIgnore.decode('mbcs')

# Each space-separated token is either a plain affix (strip-only, unchanged
# from prior behavior) or a '/'-separated group of interchangeable variants
# (e.g. "ɨ/ʉ", "ión/iones", "i/ɨ/ʉ") for languages where a suffix triggers a
# stem-final alternation rather than simple concatenation.
def _parse_affix_groups(raw):
    groups = []
    for tok in raw.split():
        variants = [v.lower() for v in tok.split(u'/') if v]
        if variants:
            groups.append(variants)
    return groups

_prefix_groups = _parse_affix_groups(PrefixesToIgnore)
_suffix_groups = _parse_affix_groups(SuffixesToIgnore)

try:
    MidWordPunctuation
except NameError:
    MidWordPunctuation = '-'
if not isinstance(MidWordPunctuation, type(u'')):
    try:
        MidWordPunctuation = MidWordPunctuation.decode('utf-8')
    except UnicodeDecodeError:
        MidWordPunctuation = MidWordPunctuation.decode('mbcs')
_joiner_chars = MidWordPunctuation

# ---------------------------------------------------------------------------
# TermRenderings helpers
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

def _find_current_project_renderings():
    """Locate TermRenderings.xml for the project currently being checked.
    Called after checking.setupCheck() so checking.scr is initialised."""
    d = _project_directory()
    if not d:
        return None
    p = os.path.join(d, u'TermRenderings.xml')
    return p if os.path.isfile(p) else None

# A letter, combining marks included: Paratext runs these checks under IronPython,
# whose .NET \w covers the combining marks (Mn, U+0300-U+036F among them). The
# old form (?:[^\W\d_]|[\u0300-\u036f]) matched each mark both ways, so a word
# with many stacked marks made a failing wildcard match take exponential time.
_WORD_CHAR_NO_DIGIT = u'[^\\W\\d_]'

# Regex metacharacters in a TermRenderings word are matched literally: only the
# '*' at either end is a wildcard. Unescaped, a rendering such as '(a+)+b*' could
# freeze the check, and 'Sant[o*' stopped it with a pattern error. Non-ASCII
# letters are not backslashed (IronPython's .NET engine rejects such escapes).
def _re_literal(s):
    return re.sub(u'([\\\\.^$|?*+()\\[\\]{}])', u'\\\\\\1', s)

def _build_word_spec(word):
    has_prefix_wild = word.startswith(u'*')
    has_suffix_wild = word.endswith(u'*')
    root_word = word.strip(u'*')
    if not root_word:
        return None
    if has_prefix_wild or has_suffix_wild:
        prefix_pat = _WORD_CHAR_NO_DIGIT + u'*' if has_prefix_wild else u''
        suffix_pat = _WORD_CHAR_NO_DIGIT + u'*' if has_suffix_wild else u''
        return re.compile(
            u'\\A' + prefix_pat + _re_literal(root_word) + suffix_pat + u'\\Z',
            re.UNICODE)
    return root_word

def _load_cap_renderings(path):
    phrases = []
    open_path = path.encode('mbcs') if isinstance(path, type(u'')) else path
    with open(open_path, 'rb') as f:
        data = f.read()
    root = ET.fromstring(data)
    for tr in root.iter(u'TermRendering'):
        r_elem = tr.find(u'Renderings')
        if r_elem is None or not r_elem.text:
            continue
        for token in r_elem.text.split(u'||'):
            at = token.find(u'@')
            if at >= 0:
                token = token[:at]
            words = token.split()
            if not words:
                continue
            first_root = words[0].strip(u'*')
            if not first_root or unicodedata.category(first_root[0]) != u'Lu':
                continue
            specs = []
            for word in words:
                spec = _build_word_spec(word)
                if spec is None:
                    specs = None
                    break
                specs.append(spec)
            if specs:
                phrases.append(specs)
    return phrases

# Words SpellingStatus.xml marks as always written with a given case
# (<Status Word="galilaaya"><SpecificCase>Galilaaya</SpecificCase>). Only the
# forms that start with a capital matter here.
def _load_specific_case(path):
    exact = set()
    open_path = path.encode('mbcs') if isinstance(path, type(u'')) else path
    with open(open_path, 'rb') as f:
        data = f.read()
    root = ET.fromstring(data)
    for sc in root.iter(u'SpecificCase'):
        word = (sc.text or u'').strip()
        if not word:
            continue
        if not isinstance(word, type(u'')):
            word = word.decode('utf-8')
        word = unicodedata.normalize('NFC', word)
        if unicodedata.category(word[0]) == u'Lu':
            exact.add(word)
    return frozenset(exact), frozenset(w.lower() for w in exact)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Strip \f...\f*, \x...\x*, \fig...\fig* spans from verse text.
INLINE_RE = re.compile(
    ur'\\f\s.*?\\f\*|\\x\s.*?\\x\*|\\fig\s.*?\\fig\*',
    re.UNICODE | re.DOTALL)

# Skip leading inline spans at the start of a verse's content.
LEADING_RE = re.compile(
    ur'^[\s\r\n]*(?:\\(?:f|x|fig)\b.*?\\(?:f\*|x\*|fig\*)\s*)*',
    re.UNICODE | re.DOTALL)

# Locate verse markers (\v N or \v N-M bridge).
VERSE_RE = re.compile(ur'\\v\s+\d+(?:-\d+)?\s*', re.UNICODE)

# Strip standalone and closing USFM character markers (\wj, \wj*, etc.)
USFM_MARKER_RE = re.compile(ur'\\[a-z][a-z0-9]*\*?', re.UNICODE)

# Gap allowed between consecutive words of a multi-word TermRenderings phrase:
# whitespace interleaved with USFM character markers (e.g. \wj Word\wj* Word2).
_PHRASE_GAP_RE = re.compile(
    ur'(?:[ \t\r\n]+|\\[a-z][a-z0-9]*\*?)*', re.UNICODE)

# Paragraph/structural markers -- signal a sentence boundary.
PARA_BREAK_RE = re.compile(
    ur'\\(?:cls|pmo|pmc|pmr|pm|po|pr|pc|ph\d*|pi\d*|mi|nb|m|p|b'
    ur'|qac|qm\d*|qr|qc|qs|qa|qd|q\d*'
    ur'|lim\d*|litl|li\d*|lh|lf'
    ur'|s\d*|d|sp|r)\b',
    re.UNICODE)

# Parallel-passage reference marker (\r) plus its same-line content.
# Blanked entirely so abbreviations inside (e.g. 'Cr' in '1 Cr 1:5') are
# not flagged as mid-sentence capitals.
PARA_REF_RE = re.compile(ur'\\r\b[^\r\n]*', re.UNICODE)

if _ignore_style_names:
    _style_pat = u'|'.join(
        u'\\\\' + _re_literal(s) + u'\\b.*?\\\\' + _re_literal(s) + u'\\*'
        for s in _ignore_style_names)
    IGNORE_STYLE_RE = re.compile(_style_pat, re.UNICODE | re.DOTALL)
else:
    IGNORE_STYLE_RE = None

if _ignore_para_names:
    _para_pat = u'|'.join(
        u'\\\\' + _re_literal(s) + u'\\b[^\\\\]*'
        for s in _ignore_para_names)
    IGNORE_PARA_RE = re.compile(_para_pat, re.UNICODE)
else:
    IGNORE_PARA_RE = None

# A "word char" is \w or a combining diacritical mark (U+0300-U+036F), so that
# words written with decomposed tone/accent marks (base letter + combining
# mark, e.g. o + combining grave = o-with-grave) are extracted whole instead
# of being truncated right before the mark.
_WORD_CHAR = u'(?:\\w|[\\u0300-\\u036f])'

def _build_word_pattern(joiners):
    if not joiners:
        return _WORD_CHAR + u'+'
    parts = []
    has_hyphen = u'-' in joiners
    for c in joiners:
        if c == u'-':
            continue
        parts.append(u'\\' + c if c in u'\\]^[' else c)
    cc = (u'-' if has_hyphen else u'') + u''.join(parts)
    return _WORD_CHAR + u'+(?:[' + cc + u']' + _WORD_CHAR + u'+)*'

_WORD_RE = re.compile(_build_word_pattern(_joiner_chars), re.UNICODE)

# Finds the preceding word (and any trailing non-word characters) at the end
# of a string; combining-mark-aware like _WORD_RE so a tone-marked word isn't
# truncated when locating the reported error span's start.
_PREV_WORD_RE = re.compile(
    u'(' + _WORD_CHAR + u'+)(?:[^\\w\\u0300-\\u036f])*$', re.UNICODE)

# ---------------------------------------------------------------------------
# Cross-chapter / cross-book state
# ---------------------------------------------------------------------------

_state = {
    'prev_end_char': None,
    'prev_book':     None,
}

# ---------------------------------------------------------------------------

def _base_char(s):
    # Skip trailing combining marks (Mn/Mc/Me) to find the base character a
    # verse actually ends with -- e.g. a vowel followed by a decomposed tone
    # mark should still be classified by the vowel's letter category, not the
    # mark's.
    i = len(s) - 1
    while i > 0 and unicodedata.category(s[i]) in (u'Mn', u'Mc', u'Me'):
        i -= 1
    return s[i]

def _is_recognized_root(root):
    root_nfc = unicodedata.normalize('NFC', root)
    root_lower = root_nfc.lower()
    if root_lower in _ignore_words_lower:
        return True
    if root_lower in _cap_single_word_exact_lower:
        return True
    if root_lower in _specific_case_lower:
        return True
    for spec in _cap_single_word_wildcards:
        if _spec_matches(spec, root_nfc):
            return True
    return False

def _word_has_affix(word_str):
    word_lower = word_str.lower()
    for group in _prefix_groups:
        for i, variant in enumerate(group):
            pl = len(variant)
            if len(word_str) <= pl or word_lower[:pl] != variant:
                continue
            if len(group) == 1:
                if _is_recognized_root(word_str[pl:]):
                    return True
            else:
                rest = word_str[pl:]
                for j, other in enumerate(group):
                    if j != i and _is_recognized_root(other + rest):
                        return True
    for group in _suffix_groups:
        for i, variant in enumerate(group):
            sl = len(variant)
            if len(word_str) <= sl or word_lower[-sl:] != variant:
                continue
            if len(group) == 1:
                if _is_recognized_root(word_str[:-sl]):
                    return True
            else:
                stem = word_str[:-sl]
                for j, other in enumerate(group):
                    if j != i and _is_recognized_root(stem + other):
                        return True
    return False

def _spec_matches(spec, word):
    if isinstance(spec, type(u'')):
        return word == spec
    return bool(spec.match(word))

def _extract_word_seq(text, start, max_words):
    words = []
    pos = start
    for i in range(max_words):
        if i > 0:
            gap_m = _PHRASE_GAP_RE.match(text, pos)
            new_pos = gap_m.end() if gap_m else pos
            if new_pos == pos:
                break
            pos = new_pos
        m = _WORD_RE.match(text, pos)
        if not m:
            break
        words.append(text[pos:m.end()])
        pos = m.end()
    return words

def _index_cap_phrases(phrases):
    by_first_word = {}
    wildcard_first = []
    for phrase in phrases:
        first = phrase[0]
        if isinstance(first, type(u'')):
            by_first_word.setdefault(first, []).append(phrase)
        else:
            wildcard_first.append(phrase)
    return by_first_word, wildcard_first

def _index_single_word_terms(phrases):
    exact_lower = set()
    wildcards = []
    for phrase in phrases:
        if len(phrase) != 1:
            continue
        spec = phrase[0]
        if isinstance(spec, type(u'')):
            exact_lower.add(spec.lower())
        else:
            wildcards.append(spec)
    return frozenset(exact_lower), wildcards

def _phrase_matches_at(text, start, phrase):
    words = _extract_word_seq(text, start, len(phrase))
    if len(words) != len(phrase):
        return False
    return all(_spec_matches(spec, words[i]) for i, spec in enumerate(phrase))

def _match_cap_phrase(text, start):
    m = _WORD_RE.match(text, start)
    if not m:
        return False
    first_word = text[start:m.end()]
    for phrase in _cap_phrases_by_first_word.get(first_word, ()):
        if len(phrase) == 1 or _phrase_matches_at(text, start, phrase):
            return True
    for phrase in _cap_phrases_wildcard_first:
        if _phrase_matches_at(text, start, phrase):
            return True
    return False

def _is_ignored_at(text, pos, word_str):
    if _match_cap_phrase(text, pos):
        return True
    word_nfc = unicodedata.normalize('NFC', word_str)
    if word_nfc in _ignore_words or word_nfc in _specific_case_words:
        return True
    return _word_has_affix(word_str)

# ---------------------------------------------------------------------------
checking.setupCheck()
# ---------------------------------------------------------------------------

_tr_path = _find_current_project_renderings() if _ignore_bt else None
_cap_phrases = _load_cap_renderings(_tr_path) if _tr_path else []
_cap_phrases_by_first_word, _cap_phrases_wildcard_first = _index_cap_phrases(_cap_phrases)
_cap_single_word_exact_lower, _cap_single_word_wildcards = _index_single_word_terms(_cap_phrases)

# A missing or unreadable SpellingStatus.xml just means no Wordlist words.
_specific_case_words, _specific_case_lower = frozenset(), frozenset()
_directory = _project_directory() if _ignore_wordlist else None
if _directory:
    _ss_path = os.path.join(_directory, u'SpellingStatus.xml')
    try:
        if os.path.isfile(_ss_path.encode('mbcs')):
            _specific_case_words, _specific_case_lower = _load_specific_case(_ss_path)
    except Exception:
        pass

class _StripCRLF(object):
    def __init__(self, wrapped):
        self._w = wrapped
    def write(self, s):
        if '\t\t' in s and not s.startswith('#'):
            try:
                ref, rest = s.split('\t\t', 1)
                text, msg = rest.rsplit('\t', 1)
                text = re.sub(r'^\[\d+\]', '', text)
                text = text.replace('\\u000d', '').replace('\\u000a', ' ')
                self._w.write(ref + '\t\t' + text + '\t' + msg)
                return
            except ValueError:
                pass
        self._w.write(s)
    def flush(self):
        self._w.flush()
    def close(self):
        self._w.close()

_sys.stdout = _StripCRLF(_sys.stdout)

# ---------------------------------------------------------------------------
# Characters to look past when scanning backwards for the preceding real
# character.  Includes opening/closing quotes (Pi/Pf category) and
# dialogue-opening dashes (U+2013 en dash, U+2014 em dash, U+2015 horizontal
# bar).  unichr() is used so that the source file stays pure ASCII.
_SKIP_CATS  = frozenset((u'Pi', u'Pf', u'Ps', u'Pe'))
_SKIP_CHARS = frozenset([
    u'"', u"'",
    unichr(0x00ab), unichr(0x00bb),  # guillemets << >>
    unichr(0x2018), unichr(0x2019),  # left/right single quotation marks
    unichr(0x201a), unichr(0x201b),  # single low-9, high-reversed-9
    unichr(0x201c), unichr(0x201d),  # left/right double quotation marks
    unichr(0x201e), unichr(0x201f),  # double low-9, high-reversed-9
    unichr(0x2013), unichr(0x2014),  # en dash, em dash
    unichr(0x2015),                  # horizontal bar
])


def _preceding_real_char(blanked, pos):
    """Scan backwards in blanked from pos, skipping spaces, quotes, and
    dialogue dashes.  Returns the first substantive character, or None."""
    i = pos - 1
    while i >= 0:
        c = blanked[i]
        if c in u' \t\r\n':
            i -= 1
            continue
        if unicodedata.category(c) in _SKIP_CATS or c in _SKIP_CHARS:
            i -= 1
            continue
        return c
    return None


def checkChapter(reference, text, lastChapter):
    book = reference.Book if reference else None

    if book != _state['prev_book']:
        _state['prev_end_char'] = None
        _state['prev_book'] = book

    verse_matches = list(VERSE_RE.finditer(text))
    if not verse_matches:
        return

    # Structural markers before the first \v suppress any carry-over state.
    if PARA_BREAK_RE.search(text[:verse_matches[0].start()]):
        _state['prev_end_char'] = None

    for idx, vm in enumerate(verse_matches):
        content_start = vm.end()
        if idx + 1 < len(verse_matches):
            content_end = verse_matches[idx + 1].start()
        else:
            content_end = len(text)
        verse_text = text[content_start:content_end]

        # ---- Check 1: verse-boundary capital --------------------------------
        prev = _state['prev_end_char']
        if prev and (prev in (u',', u';') or unicodedata.category(prev).startswith('L')):
            m    = LEADING_RE.match(verse_text)
            skip = m.end() if m else 0
            while skip < len(verse_text) and verse_text[skip] in ' \t\r\n':
                skip += 1
            if skip < len(verse_text):
                first_char = verse_text[skip]
                if unicodedata.category(first_char) == 'Lu':
                    m_next = _WORD_RE.match(verse_text, skip)
                    word_str = verse_text[skip:m_next.end()] if m_next else u''
                    if not _is_ignored_at(verse_text, skip, word_str):
                        pre_blanked = INLINE_RE.sub(
                            lambda m: u' ' * len(m.group(0)), text[:vm.start()])
                        m_prev = _PREV_WORD_RE.search(pre_blanked)
                        span_start = m_prev.start(1) if m_prev else vm.start()
                        if m_next:
                            span_end = content_start + m_next.end()
                        else:
                            span_end = content_start + skip + 1
                        checking.outputError(span_start, span_end, u'')

        # ---- Check 2: within-verse capitals ---------------------------------
        blanked = INLINE_RE.sub(lambda m: u' ' * len(m.group(0)), verse_text)
        blanked = PARA_REF_RE.sub(lambda m: u' ' * len(m.group(0)), blanked)
        if IGNORE_STYLE_RE:
            blanked = IGNORE_STYLE_RE.sub(lambda m: u' ' * len(m.group(0)), blanked)
        if IGNORE_PARA_RE:
            blanked = IGNORE_PARA_RE.sub(lambda m: u'.' + u' ' * (len(m.group(0)) - 1), blanked)
        blanked = PARA_BREAK_RE.sub(
            lambda m: u'.' + u' ' * (len(m.group(0)) - 1), blanked)
        blanked = USFM_MARKER_RE.sub(lambda m: u' ' * len(m.group(0)), blanked)

        m_lead = LEADING_RE.match(verse_text)
        first_pos = m_lead.end() if m_lead else 0
        while first_pos < len(blanked) and blanked[first_pos] in u' \t\r\n':
            first_pos += 1
        m_fw = _WORD_RE.search(blanked[first_pos:])
        first_word_end = (first_pos + m_fw.end()) if m_fw else 0

        for wm in _WORD_RE.finditer(blanked):
            if wm.start() < first_word_end:
                continue
            word_str = verse_text[wm.start():wm.end()]
            if not word_str or unicodedata.category(word_str[0]) != u'Lu':
                continue
            preceding = _preceding_real_char(blanked, wm.start())
            if preceding is None:
                continue
            if preceding in _final_set:
                continue
            if _ignore_cap_after_quote:
                i = wm.start() - 1
                while i >= 0 and blanked[i] in u' \t\r\n':
                    i -= 1
                if i >= 0:
                    c = blanked[i]
                    _is_opener = (c in _quote_openers) if _quote_openers is not None else (unicodedata.category(c) == u'Pi')
                    if _is_opener:
                        continue
            if _is_ignored_at(blanked, wm.start(), word_str):
                continue
            checking.outputError(content_start + wm.start(),
                                  content_start + wm.end(), u'')

        # ---- Compute END character of this verse ----------------------------
        suppress = False
        last_break = None
        for mb in PARA_BREAK_RE.finditer(verse_text):
            last_break = mb
        if last_break is not None:
            after = verse_text[last_break.end():]
            if not USFM_MARKER_RE.sub(u'', after).strip():
                suppress = True

        if suppress:
            _state['prev_end_char'] = None
        else:
            stripped = INLINE_RE.sub(u'', verse_text)
            if IGNORE_STYLE_RE:
                stripped = IGNORE_STYLE_RE.sub(u'', stripped)
            stripped = PARA_REF_RE.sub(u'', stripped)
            if IGNORE_PARA_RE:
                stripped = IGNORE_PARA_RE.sub(u'', stripped)
            stripped = USFM_MARKER_RE.sub(u'', stripped).rstrip()
            while stripped:
                c = stripped[-1]
                cat = unicodedata.category(c)
                if cat in ('Pi', 'Pf') or c in ('"', "'"):
                    stripped = stripped[:-1].rstrip()
                else:
                    break
            _state['prev_end_char'] = _base_char(stripped) if stripped else None

checking.checkAllChapters(checkChapter)
