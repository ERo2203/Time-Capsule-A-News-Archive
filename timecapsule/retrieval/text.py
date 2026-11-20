"""Tokenization and OCR-aware query expansion.

Kept deliberately simple so that ``site/assets/search.js`` can mirror it
exactly: the browser and Python index the corpus the same way. If you change a
rule here, change it there too (``tests/test_retrieval.py`` pins the behaviour).
"""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers herself him himself his how i if in into is it its itself just me more most my
    myself no nor not now of off on once only or other our ours ourselves out over own same she should so
    some such than that the their theirs them themselves then there these they this those through to too
    under until up very was we were what when where which while who whom why will with would you your
    yours yourself yourselves said also upon shall"""
    # common Hindi function words (bilingual Indian sources such as the Gazette of India)
    """ का के की को में से पर है हैं और या यह इस एक भी तथा द्वारा लिए किया गया था थे""".split()
)

# Words that frame a research question ("How did papers report ...") but say
# nothing about its subject. Dropped from queries only, never from documents,
# unless the query consists of nothing else.
QUESTION_WORDS = frozenset(
    """report reports reported reporting describe described say says newspaper newspapers paper papers
    press coverage covered first later happen happened tell told""".split()
)

# Latin letters and digits, plus the Indic scripts (Devanagari, Bengali, Gurmukhi,
# Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam; danda punctuation excluded)
# and Urdu letters, so Indian-language sources are searchable too.
_TOKEN = re.compile(r"[a-z0-9\u0900-\u0963\u0966-\u0d7f\u0621-\u064a\u0660-\u0669\u0679-\u06d3]+")
ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# Character confusions typical of OCR on old newsprint (both directions listed).
OCR_CONFUSIONS = [
    ("m", "rn"), ("rn", "m"), ("h", "li"), ("li", "h"), ("d", "cl"), ("cl", "d"), ("w", "vv"),
    ("vv", "w"), ("u", "ii"), ("ii", "u"), ("e", "c"), ("c", "e"), ("o", "c"), ("c", "o"),
    ("i", "l"), ("l", "i"), ("l", "1"), ("1", "l"), ("o", "0"), ("0", "o"), ("n", "u"), ("u", "n"),
    ("s", "f"), ("f", "s"), ("t", "f"), ("f", "t"), ("b", "h"), ("h", "b"), ("a", "n"), ("n", "a"),
]


_LATIN_MARKS = re.compile(r"[\u0300-\u036f]")


def fold(text: str) -> str:
    """Lowercase, long s -> s, and strip Latin accents. Vowel signs of Indic
    scripts are combining characters too, but they are kept: they are letters."""
    return _LATIN_MARKS.sub("", unicodedata.normalize("NFKD", text.replace("ſ", "s").lower()))


def stem(w: str) -> str:
    """Harman's 'S' stemmer: conflates plurals only, which is safe for names."""
    if len(w) <= 3:
        return w
    if w.endswith("ies") and not w.endswith(("eies", "aies")):
        return w[:-3] + "y"
    if w.endswith("es") and not w.endswith(("aes", "ees", "oes")):
        return w[:-1]
    if w.endswith("s") and not w.endswith(("us", "ss")):
        return w[:-1]
    return w


def raw_tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(fold(text)) if len(t) > 1 and t not in STOPWORDS]


def query_tokens(text: str) -> list[str]:
    toks = raw_tokens(text)
    content = [t for t in toks if t not in QUESTION_WORDS]
    return content or toks


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in raw_tokens(text)]


GENERIC_EDIT_MIN_LEN = 7  # shorter words have too many real-word neighbours


def variants(word: str) -> set[str]:
    """Spellings an OCR engine plausibly produced for ``word``: the
    multi-character confusions above and, for longer words, every edit at
    distance one."""
    out: set[str] = set()
    n = len(word)
    for i in range(n + 1 if n >= GENERIC_EDIT_MIN_LEN else 0):
        for c in ALPHABET:
            out.add(word[:i] + c + word[i:])  # insertion
        if i < n:
            out.add(word[:i] + word[i + 1:])  # deletion
            for c in ALPHABET:
                out.add(word[:i] + c + word[i + 1:])  # substitution
        if i < n - 1:
            out.add(word[:i] + word[i + 1] + word[i] + word[i + 2:])  # transposition
    for a, b in OCR_CONFUSIONS:
        start = word.find(a)
        while start != -1:
            out.add(word[:start] + b + word[start + len(a):])
            start = word.find(a, start + 1)
    out.discard(word)
    return out
