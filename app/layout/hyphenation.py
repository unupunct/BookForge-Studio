"""Optional hyphenation (Liang patterns via pyphen) for justified body text."""
from __future__ import annotations

from functools import lru_cache

try:  # pyphen is a declared dependency, but a missing dictionary must never break layout
    import pyphen
except ImportError:  # pragma: no cover
    pyphen = None

PREFERRED = {"en": "en_US", "pt": "pt_PT", "pl": "pl_PL", "de": "de_DE", "ro": "ro_RO", "fr": "fr",
             "es": "es", "it": "it_IT", "hu": "hu_HU", "nl": "nl_NL", "ru": "ru_RU", "sv": "sv", "cs": "cs_CZ"}
MIN_WORD = 6
MIN_LEFT = 2
MIN_RIGHT = 3


@lru_cache(maxsize=16)
def get_hyphenator(language: str | None):
    """A hyphenator for a book language code ('ro', 'en-GB', 'fr_FR'...), or None if unsupported."""
    if pyphen is None or not language:
        return None
    lang = language.replace("-", "_")
    candidates = [lang, PREFERRED.get(lang[:2].lower(), "")] + \
        [k for k in pyphen.LANGUAGES if k.lower().startswith(lang[:2].lower())]
    for code in candidates:
        if code and code in pyphen.LANGUAGES:
            return pyphen.Pyphen(lang=code, left=MIN_LEFT, right=MIN_RIGHT)
    return None


def split_points(h, word: str) -> list[int]:
    """Character offsets where `word` may be split, best (latest) last. Only plain alphabetic words."""
    if h is None or len(word) < MIN_WORD or not word.isalpha():
        return []
    return sorted(h.positions(word))
