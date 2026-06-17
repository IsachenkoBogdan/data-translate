import re
from typing import Any


ENGLISH_RESIDUE_MIN_TOKENS = 4
CONTENT_HEURISTIC_MAX_ALPHA = 250
LENGTH_RATIO_LOW = 0.35
LENGTH_RATIO_HIGH = 3.0
LENGTH_RATIO_MIN_ALPHA = 20
REPEATED_TRANSLATION_MIN_DISTINCT_SOURCES = 5
REPEATED_TRANSLATION_MAX_TEXT_CHARS = 500

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
_ENGLISH_RESIDUE_WORDS = {
    "are",
    "can",
    "could",
    "does",
    "have",
    "how",
    "need",
    "please",
    "should",
    "that",
    "then",
    "this",
    "try",
    "what",
    "where",
    "will",
    "with",
    "would",
    "you",
    "your",
}
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
_FILE_EXTENSION_RE = re.compile(
    r"(?i)\.(?:7z|avif|bmp|csv|doc|docx|gif|gz|htm|html|jpeg|jpg|json|pdf|png|ppt|pptx|tar|tsv|txt|webp|xls|xlsx|xml|zip)\b"
)
_FILE_ATTACHMENT_RE = re.compile(
    r"(?i)^\s*`?[^()\n]{0,180}\.(?:7z|avif|bmp|csv|doc|docx|gif|gz|htm|html|jpeg|jpg|json|pdf|png|ppt|pptx|tar|tsv|txt|webp|xls|xlsx|xml|zip)\s*(?:\([^)]*\))?\s*$"
)
_BARE_PATH_RE = re.compile(r"(?i)^\s*(?:[\w.-]+/)+[\w./-]+\s*$")
_HASH_OR_ID_RE = re.compile(r"(?i)^[a-f0-9]{16,}$|^[a-z0-9_-]{24,}$")
_HASH_OR_ID_TOKEN_RE = re.compile(r"(?i)\b[a-f0-9]{16,}\b|\b[a-z0-9_-]{24,}\b")
_PATH_FRAGMENT_RE = re.compile(r"(?i)(?:/[\w.+-]+){2,}")
_HANDLE_RE = re.compile(r"(?<![\w.])@[\w.-]+")
_HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
_BACKTICK_CODE_RE = re.compile(r"(?s)```.*?```|`[^`]+`")
_LATEX_RE = re.compile(r"(?s)\$[^$]+\$")
_COMMAND_RE = re.compile(r"(?i)(?:^|\s)(?:awk|df|ffmpeg|localedef|mkfs|sudo|umount)\b")
_TECHNICAL_LABELS = {"hth", "output", "source"}
_PLACEHOLDER_OR_MARKER_RE = re.compile(r"\[[^\[\]\n]{1,120}\]|\{[^{}\n]{1,120}\}|<[/]?[A-Za-z][^>\n]{0,120}>")
_HTML_ENTITY_RE = re.compile(r"&(?:[A-Za-z]{2,16}|#[0-9]{2,7}|#x[0-9A-Fa-f]{2,6});")


def norm_text(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def text_tokens(value: str) -> list[str]:
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


def letter_count(value: str) -> int:
    return sum(1 for char in value if char.isalpha())


def has_english_signal(value: str) -> bool:
    return any(token in _ENGLISH_SIGNAL_WORDS for token in text_tokens(value))


def _is_modelish_value(value: str) -> bool:
    parts = [part.strip("()[]{}:;,!?\"'`") for part in value.split()]
    parts = [part for part in parts if part]
    if len(parts) < 2 or len(parts) > 8:
        return False
    if not any(char.isdigit() for char in value):
        return False
    for part in parts:
        if part.isalpha() and part.islower() and part not in {"i"}:
            return False
    return True


def technical_unchanged_reason(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if _URL_RE.fullmatch(stripped.strip("()[]<>\"'`")) or _EMAIL_RE.fullmatch(stripped):
        return "url_or_email"
    without_urls = _URL_RE.sub("", stripped)
    if without_urls and not any(char.isalnum() for char in without_urls):
        return "url_wrapped_punctuation"
    if _FILE_ATTACHMENT_RE.fullmatch(stripped):
        return "file_attachment"
    if _BARE_PATH_RE.fullmatch(stripped):
        return "file_or_path"
    if _HASH_OR_ID_RE.fullmatch(stripped):
        return "hash_or_id"
    if _HASH_OR_ID_TOKEN_RE.search(stripped) and _PATH_FRAGMENT_RE.search(stripped):
        return "hash_or_id_path"
    if _is_modelish_value(stripped):
        return "model_or_product_name"

    technical_context = bool(
        _URL_RE.search(stripped)
        or _BACKTICK_CODE_RE.search(stripped)
        or _LATEX_RE.search(stripped)
        or _COMMAND_RE.search(stripped)
        or _PATH_FRAGMENT_RE.search(stripped)
        or "<code>" in stripped.lower()
        or "<a " in stripped.lower()
        or "href=" in stripped.lower()
        or "</a>" in stripped.lower()
    )
    if _COMMAND_RE.search(stripped):
        technical_chars = sum(1 for char in stripped if not char.isalpha() and not char.isspace())
        if technical_chars / max(1, len(stripped)) >= 0.08:
            return "command_or_shell"
    if _LATEX_RE.search(stripped) or _BACKTICK_CODE_RE.search(stripped):
        without_code = _LATEX_RE.sub("", _BACKTICK_CODE_RE.sub("", stripped))
        if not [token for token in text_tokens(without_code) if token not in _TECHNICAL_LABELS]:
            return "code_or_latex"

    tokens = text_tokens(stripped)
    if not tokens:
        return "no_text_tokens"
    if technical_context:
        semantic = _URL_RE.sub("", stripped)
        semantic = _EMAIL_RE.sub("", semantic)
        semantic = _BACKTICK_CODE_RE.sub("", semantic)
        semantic = _LATEX_RE.sub("", semantic)
        semantic = _HTML_TAG_RE.sub("", semantic)
        semantic = _HANDLE_RE.sub("", semantic)
        semantic_tokens = [token for token in text_tokens(semantic) if token not in _TECHNICAL_LABELS]
        if not semantic_tokens or not any(token in _ENGLISH_SIGNAL_WORDS for token in semantic_tokens):
            return "technical_context"
    if _URL_RE.search(stripped) or _FILE_EXTENSION_RE.search(stripped):
        signal_tokens = [token for token in tokens if token in _ENGLISH_SIGNAL_WORDS]
        technical_chars = sum(1 for char in stripped if not char.isalpha() and not char.isspace())
        technical_ratio = technical_chars / max(1, len(stripped))
        if len(signal_tokens) <= 1 and technical_ratio >= 0.18:
            return "url_or_file_context"
    return ""


def is_short_title_like_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or "\n" in stripped or any(char in stripped for char in "?!"):
        return False
    if len(stripped) > 120:
        return False

    raw_parts = [part.strip("()[]{}:;,\"'`") for part in stripped.split()]
    words = [part for part in raw_parts if part and any(char.isalpha() for char in part)]
    if len(words) == 1:
        return "-" in stripped or "." in stripped
    if not 2 <= len(words) <= 10:
        return False

    connectors = {
        "a",
        "am",
        "an",
        "and",
        "as",
        "by",
        "da",
        "das",
        "de",
        "del",
        "do",
        "dos",
        "du",
        "for",
        "i",
        "in",
        "la",
        "le",
        "n",
        "of",
        "on",
        "or",
        "the",
        "to",
    }
    dialogue_markers = {
        "am",
        "are",
        "can",
        "could",
        "did",
        "do",
        "does",
        "had",
        "has",
        "have",
        "he",
        "i",
        "it",
        "know",
        "like",
        "love",
        "my",
        "need",
        "she",
        "tell",
        "that",
        "they",
        "think",
        "this",
        "want",
        "was",
        "we",
        "were",
        "would",
        "you",
        "your",
    }

    title_case = all(
        word[0].isupper() or word.isupper() or "." in word or "-" in word or word.lower() in connectors for word in words
    )
    if title_case:
        return True

    tokens = text_tokens(stripped)
    english_signal_tokens = {token for token in tokens if token in _ENGLISH_SIGNAL_WORDS}
    if english_signal_tokens and english_signal_tokens <= {"am", "do", "i", "n"}:
        return True

    return not any(token in dialogue_markers for token in tokens)


def suspicious_unchanged_translation(source: str, translated: str, *, min_letters: int = 12) -> bool:
    return (
        letter_count(source) >= min_letters
        and not technical_unchanged_reason(source)
        and has_english_signal(source)
        and norm_text(source) == norm_text(translated)
    )


def _normalize_marker(value: str) -> str:
    return value.replace("–", "-").replace("—", "-").replace(" ", "")


def _looks_like_placeholder_or_marker(value: str) -> bool:
    if value.startswith("<") and value.endswith(">"):
        return True
    inner = value[1:-1] if len(value) >= 2 and value[0] in "[{" and value[-1] in "]}" else value
    return any(char.isdigit() for char in inner) or any(char in inner for char in "_:/")


def placeholder_or_marker_sequences(value: str) -> list[str]:
    return [_normalize_marker(match.group(0)) for match in _PLACEHOLDER_OR_MARKER_RE.finditer(value) if _looks_like_placeholder_or_marker(match.group(0))]


def html_entities(value: str) -> list[str]:
    return [match.group(0) for match in _HTML_ENTITY_RE.finditer(value)]


def length_ratio(source_alpha_count: int, translation_alpha_count: int) -> float | None:
    if source_alpha_count == 0:
        return None
    return round(translation_alpha_count / source_alpha_count, 4)


def pair_diagnostics(source_text: str, translated_text: str) -> dict[str, Any]:
    source_alpha_count = letter_count(source_text)
    translation_alpha_count = letter_count(translated_text)
    source_markers = placeholder_or_marker_sequences(source_text)
    translation_markers = placeholder_or_marker_sequences(translated_text)
    translation_entities = html_entities(translated_text)
    english_signal_tokens = [token for token in text_tokens(translated_text) if token in _ENGLISH_RESIDUE_WORDS]
    return {
        "source_len": len(source_text),
        "translation_len": len(translated_text),
        "source_alpha_count": source_alpha_count,
        "translation_alpha_count": translation_alpha_count,
        "length_ratio": length_ratio(source_alpha_count, translation_alpha_count),
        "source_markers": source_markers,
        "translation_markers": translation_markers,
        "html_entities_in_translation": translation_entities,
        "english_signal_tokens_in_translation": sorted(set(english_signal_tokens)),
        "english_signal_token_count_in_translation": len(english_signal_tokens),
        "unchanged_norm_match": bool(norm_text(source_text) and norm_text(source_text) == norm_text(translated_text)),
    }


def empty_translated(source: str, translated: str) -> bool:
    return bool(source.strip()) and not translated.strip()
