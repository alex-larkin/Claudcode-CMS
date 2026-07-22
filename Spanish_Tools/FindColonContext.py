# -*- coding: utf-8 -*-
import patterns
import re

patterns.setupCheck()

flags = re.MULTILINE | re.UNICODE
if MatchCase == "No":
    flags = flags | re.IGNORECASE
if DotAll == "Yes":
    flags = flags | re.DOTALL

def charClassSafe(s):
    result = u''
    for c in s:
        if c in u'\\]^-':
            result += u'\\' + c
        else:
            result += c
    return result

hs = u'[^\\S\\r\\n]'  # horizontal whitespace (not \r or \n)

# Build exclusion set: whitespace + user-defined quote chars + backslash
excluded = u'\\s' + charClassSafe(QuotationMarks) + u'\\\\'

# First word: must be capitalized (default) or any non-quote word
if CapitalizedOnly == "Yes":
    first_word = u'[A-Z][^' + excluded + u']*'
else:
    first_word = u'[^' + excluded + u']+'

more_word = u'[^' + excluded + u']+'

pattern = (u'\\b\\w+' + hs + u'*:'                       # one word before colon
           + hs                                            # required space after colon
           + u'(?:' + hs + u'?\\\\v \\d+' + hs + u')?'  # optional verse marker \v N
           + first_word                                    # first word after colon
           + u'(?:' + hs + u'+' + more_word + u')?')     # optional second word

patterns.addPattern(pattern, u' ')
patterns.scanText(flags)
