"""OCR post-correction and quality scoring for historical newsprint.

Old newspaper OCR has recurring, fixable problems: words hyphenated across
line breaks, the long s (ſ) and ligatures, stray column rules read as ``|`` or
``l``, runs of punctuation from ornaments, and whole lines of noise from
damaged film. These helpers fix what can safely be fixed and *score* the rest,
so retrieval can down-weight garbage instead of silently dropping it.
"""

from __future__ import annotations

import re
import unicodedata

_LIGATURES = {
    "ſ": "s", "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "‘": "'", "’": "'", "“": '"', "”": '"', "„": '"',
    "—": " - ", "–": "-", "­": "",
}
_LIG_RE = re.compile("|".join(map(re.escape, _LIGATURES)))
_HYPHEN_BREAK = re.compile(r"(\w)[-¬]\s*\n\s*(\w)")
_NOISE_RUN = re.compile(r"([^\w\s])\1{2,}")  # "......", "----", ",,,,"
_SPACES = re.compile(r"[ \t\f\v]+")
_WORD = re.compile(r"[A-Za-z]+")

# A small set of very common English words; real text contains many of them,
# OCR noise contains almost none. Used only for quality scoring.
_COMMON = set(
    """the of and to a in that is was he for it with as his on be at by i this had not are but from
    or have an they which one you were her all she there would their we him been has when who will more
    no if out so said what up its about into than them can only other new some could time these two may
    then do first any my now such like our over man me even most made after also did many before must
    through back years where much your way well down should because each just those people mr how too
    little state good very make world still own see men work long get here between both life being under
    never day same another know while last might us great old year off come since against go came right
    used take three city street president new york washington""".split()
)


def normalize(text: str) -> str:
    """Unicode-normalize and replace ligatures / long s / typographic quotes."""
    text = unicodedata.normalize("NFKC", text)
    return _LIG_RE.sub(lambda m: _LIGATURES[m.group(0)], text)


def clean_ocr_text(text: str) -> str:
    """Conservative cleanup: never invents words, only repairs layout damage."""
    text = normalize(text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "unprece-\ndented" -> "unprecedented"
    text = _NOISE_RUN.sub(r"\1", text)
    lines = []
    for line in text.splitlines():
        line = _SPACES.sub(" ", line).strip()
        if not line:
            continue
        if line_quality(line) < 0.2 and len(line) < 40:
            continue  # short line of pure noise (rules, ornaments, specks)
        lines.append(line)
    return "\n".join(lines)


def line_quality(line: str) -> float:
    if not line:
        return 0.0
    letters = sum(c.isalpha() for c in line)
    return letters / max(1, len(line.replace(" ", "")))


def quality_score(text: str) -> float:
    """0..1 heuristic: share of letters, plausible word shapes and common words.

    It is a rough signal, not a measure of character accuracy; use it to rank
    and to warn readers, not to make claims about a source.
    """
    words = _WORD.findall(text)
    if len(words) < 5:
        return 0.0
    letters = sum(c.isalpha() for c in text)
    non_space = sum(not c.isspace() for c in text) or 1
    alpha_ratio = letters / non_space
    plausible = sum(
        1 for w in words
        if 1 < len(w) < 16 and (w.islower() or w.istitle() or w.isupper()) and re.search(r"[aeiouy]", w, re.I)
    ) / len(words)
    common = sum(1 for w in words if w.lower() in _COMMON) / len(words)
    common_score = min(1.0, common / 0.35)  # ~35-45% of running English text is function words
    return round(0.35 * alpha_ratio + 0.35 * plausible + 0.30 * common_score, 3)
