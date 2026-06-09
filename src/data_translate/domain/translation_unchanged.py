from collections.abc import Mapping

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import DEFAULT_MAX_CHUNK_CHARS, translate_text_with_chunks


Options = Mapping[str, object]


_ENGLISH_SIGNAL_WORDS = {
    "a",
    "am",
    "an",
    "and",
    "are",
    "be",
    "can",
    "could",
    "do",
    "does",
    "for",
    "have",
    "how",
    "i",
    "is",
    "it",
    "may",
    "my",
    "need",
    "not",
    "of",
    "offer",
    "on",
    "please",
    "should",
    "that",
    "the",
    "then",
    "this",
    "to",
    "try",
    "we",
    "what",
    "where",
    "will",
    "with",
    "you",
    "your",
}


def _normalized_for_unchanged_check(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in value.lower():
        if char.isalpha() or char == "'":
            current.append(char)
        elif current:
            tokens.append("".join(current).strip("'"))
            current = []
    if current:
        tokens.append("".join(current).strip("'"))
    return [token for token in tokens if token]


def _has_english_signal(value: str) -> bool:
    return any(token in _ENGLISH_SIGNAL_WORDS for token in _tokens(value))


def _letter_count(value: str) -> int:
    return sum(1 for char in value if char.isalpha())


def is_suspicious_unchanged_translation(source: str, translated: str, options: Options) -> bool:
    if not bool(options.get("retry_unchanged", False)):
        return False
    min_letters = int(options.get("unchanged_min_letters", 12))
    if _letter_count(source) < min_letters:
        return False
    if not _has_english_signal(source):
        return False
    return _normalized_for_unchanged_check(source) == _normalized_for_unchanged_check(translated)


async def retry_if_unchanged(
    source: str,
    translated: str,
    adapter: TranslationAdapter,
    options: Options,
) -> tuple[str, int, str]:
    if not is_suspicious_unchanged_translation(source, translated, options):
        return translated, 0, ""
    retry_text, retry_attempts, retry_error = await translate_text_with_chunks(
        source,
        adapter,
        use_cache=False,
        max_chunk_chars=int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS)),
    )
    if not retry_error and not is_suspicious_unchanged_translation(source, retry_text, options):
        return retry_text, retry_attempts, ""
    return translated, retry_attempts, "unchanged translation"
