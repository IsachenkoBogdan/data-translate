import re
from decimal import Decimal, InvalidOperation
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
_DIGIT_SEQUENCE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{1,3}(?:[,\.\u00a0 ]\d{3})+(?!\d)(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![A-Za-z0-9])"
)
_PLACEHOLDER_OR_MARKER_RE = re.compile(r"\[[^\[\]\n]{1,120}\]|\{[^{}\n]{1,120}\}|<[/]?[A-Za-z][^>\n]{0,120}>")
_HTML_ENTITY_RE = re.compile(r"&(?:[A-Za-z]{2,16}|#[0-9]{2,7}|#x[0-9A-Fa-f]{2,6});")
_GROUPED_OR_PLAIN_NUMBER = r"\d{1,3}(?:[,\u00a0 ]\d{3})+|\d+"
_ORDINAL_SUFFIX_RE = re.compile(rf"(?i)(?<![A-Za-z0-9])({_GROUPED_OR_PLAIN_NUMBER})(?:st|nd|rd|th)\b")
_DECADE_SUFFIX_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d{1,4})s\b")
_ATTACHED_UNIT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?|\.\d+)(?:mm|cm|m|km|mph|sq\s*ft|sqft|sq\s*feet|square\s*feet|yd|yards?|in|inch|inches|ft|feet|lbs?|pounds?|oz|ounces?|l|liters?|litres?|meters?|metres?)\b"
)
_ERA_SUFFIX_RE = re.compile(
    rf"(?<![A-Za-z0-9])({_GROUPED_OR_PLAIN_NUMBER})\s*(?:[bB]\.?[cC]\.?[eE]?\.?|[cC]\.[eE]\.|CE\b|[aA]\.?[dD]\.?)\b"
)
_LOOSE_NUMERIC_SUFFIX_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?|\.\d+)(?:ish|approx(?:imately)?)\b")
_ATTACHED_WORD_NUMBER_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?)(?=[A-Za-z]{2,})")
_WORD_ATTACHED_NUMBER_RE = re.compile(r"(?i)(?<=[A-Za-z])(\d+(?:[.,]\d+)?)\b")
_DIGIT_TYPO_PERCENT_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+)[A-Za-z]\s*percent\b")
_TYPO_THOUSANDS_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d{1,3})[,\u00a0 ]o{3}(?![A-Za-z0-9])")
_COMMA_DIGIT_LIST_RE = re.compile(r"(?<!\d)(\d(?:\s*,\s*\d){2,})(?!\d)")
_SPACED_COMMA_NUMBER_RE = re.compile(r"(?<!\d)(\d+)\s+,\s*(\d+)(?!\d)")
_DECADE_WITH_TRAILING_NUMBER_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d{1,4})s\.(\d+)\b")
_AROUND_THE_CLOCK_RE = re.compile(r"(?i)\b(?:around|round)\s+the\s+clock\b")
_APOSTROPHE_YEAR_RE = re.compile(r"(?<!\d)['’](\d{2})\b")
_TRAILING_APOSTROPHE_YEAR_RE = re.compile(r"(?<!\d)(\d{2})['’](?!\d)")
_TWELVE_HOUR_TIME_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b")
_FRACTIONAL_MILES_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+)\s*/\s*(\d+)\s*miles?\b")
_MILES_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?)\s*miles?\b")
_MPH_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?)\s*mph\b")
_FEET_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(\d+(?:[.,]\d+)?)\s*(?:feet|foot|ft)\b")
_MONTH_ATTACHED_DAY_RE = re.compile(
    r"(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(\d{1,2})(?:st|nd|rd|th)?\b"
)
_NUMBER_WITH_MULTIPLIER_RE = re.compile(
    r"(?i)(?<!\d)(\d+(?:[.,]\d+)?|\.\d+)\s*(k|grand|thousand|million|billion|trillion)s?\b"
)
_YEAR_RANGE_RE = re.compile(
    r"(?i)(?<!\d)(\d{2})\s*[-–—]\s*(\d{2})(?=\s*(?:year|season|school|academic|rowers?|athletes?))"
)
_DECADE_COUNT_RE = re.compile(r"(?i)(?<!\d)(\d+)\s+decades?\b")
_TRANSLATED_HALF_RE = re.compile(r"(?i)\b(?:demi|half|halb|media|mezza|mezzo)\b")
_MULTIPLIER_WORDS = {
    "k": Decimal("1000"),
    "grand": Decimal("1000"),
    "thousand": Decimal("1000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "trillion": Decimal("1000000000000"),
}
_NUMBER_WORD_EQUIVALENTS = {
    "zero": "0",
    "one": "1",
    "first": "1",
    "two": "2",
    "second": "2",
    "three": "3",
    "third": "3",
    "four": "4",
    "fourth": "4",
    "five": "5",
    "fifth": "5",
    "six": "6",
    "sixth": "6",
    "seven": "7",
    "seventh": "7",
    "eight": "8",
    "eighth": "8",
    "nine": "9",
    "ninth": "9",
    "ten": "10",
    "tenth": "10",
    "eleven": "11",
    "eleventh": "11",
    "twelve": "12",
    "twelfth": "12",
    "thirteen": "13",
    "thirteenth": "13",
    "fourteen": "14",
    "fourteenth": "14",
    "fifteen": "15",
    "fifteenth": "15",
    "sixteen": "16",
    "sixteenth": "16",
    "seventeen": "17",
    "seventeenth": "17",
    "eighteen": "18",
    "eighteenth": "18",
    "nineteen": "19",
    "nineteenth": "19",
    "twenty": "20",
    "twentieth": "20",
    "thirty": "30",
    "thirtieth": "30",
    "forty": "40",
    "fortieth": "40",
    "fifty": "50",
    "fiftieth": "50",
    "sixty": "60",
    "sixtieth": "60",
    "sixties": "60",
    "seventy": "70",
    "seventieth": "70",
    "seventies": "70",
    "eighty": "80",
    "eightieth": "80",
    "eighties": "80",
    "ninety": "90",
    "ninetieth": "90",
    "nineties": "90",
}
_CENTURY_WORD_EQUIVALENTS = {
    "eighteen": 1800,
    "nineteen": 1900,
    "twenty": 2000,
}


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


def _compact_number_group_spaces(value: str) -> str:
    return re.sub(r"(?<=\d),\s+(?=\d{3}(?:\D|$))", ",", value)


def _normalize_number_token(number_text: str) -> str:
    token = number_text.strip().replace("\u00a0", " ")
    if token.startswith("."):
        token = f"0{token}"
    token = re.sub(r"\s+", " ", token)
    separator_positions = [(idx, char) for idx, char in enumerate(token) if char in "., "]
    if not separator_positions:
        return token

    decimal_position: tuple[int, str] | None = None
    for idx, char in reversed(separator_positions):
        if char not in ",.":
            continue
        fraction = token[idx + 1 :]
        if fraction.isdigit() and len(fraction) != 3:
            decimal_position = (idx, char)
            break

    if decimal_position is not None:
        idx, _char = decimal_position
        integer = "".join(char for char in token[:idx] if char.isdigit())
        fraction = "".join(char for char in token[idx + 1 :] if char.isdigit())
        if integer and fraction:
            return f"{integer}.{fraction}"

    digits = "".join(char for char in token if char.isdigit())
    return digits or token


def digit_sequences(value: str) -> list[str]:
    values = []

    def append_unique(number_text: str) -> None:
        normalized = _normalize_number_token(number_text)
        if normalized not in values:
            values.append(normalized)

    normalized_value = _compact_number_group_spaces(value)
    for match in _DIGIT_SEQUENCE_RE.finditer(normalized_value):
        token = match.group(0)
        if "," in token and "\u00a0" not in token and " " not in token:
            parts = token.split(",")
            if len(parts) > 2 and parts[0].isdigit() and all(part.isdigit() and len(part) == 3 for part in parts[1:]):
                append_unique(token)
            else:
                integer, fraction = parts[0], parts[1]
                if len(integer) <= 2 and len(fraction) == 4:
                    append_unique(integer)
                    append_unique(fraction)
                elif integer.isdigit() and fraction.isdigit() and len(fraction) == 3:
                    append_unique(token)
                else:
                    append_unique(token)
        elif re.fullmatch(r"\d{1,3}(?:[,\.\u00a0 ]\d{3})+(?!\d)(?:[.,]\d+)?", token):
            append_unique(token)
        else:
            append_unique(token)
    for regex in (
        _ORDINAL_SUFFIX_RE,
        _DECADE_SUFFIX_RE,
        _ATTACHED_UNIT_RE,
        _ERA_SUFFIX_RE,
        _LOOSE_NUMERIC_SUFFIX_RE,
        _ATTACHED_WORD_NUMBER_RE,
        _WORD_ATTACHED_NUMBER_RE,
        _DIGIT_TYPO_PERCENT_RE,
        _MONTH_ATTACHED_DAY_RE,
        _NUMBER_WITH_MULTIPLIER_RE,
    ):
        for match in regex.finditer(value):
            append_unique(match.group(1))
    return values


def _canonical_digit_value(value: str) -> str:
    if "." not in value and value.isdigit():
        stripped = value.lstrip("0")
        return stripped or "0"
    if "." in value:
        integer, fraction = value.split(".", maxsplit=1)
        if integer.isdigit() and fraction.isdigit():
            canonical_integer = integer.lstrip("0") or "0"
            fraction = fraction.rstrip("0")
            if not fraction:
                return canonical_integer
            return f"{canonical_integer}.{fraction}"
    return value


def _decimal_int_string(value: Decimal) -> str | None:
    if value == value.to_integral_value():
        return str(int(value))
    return None


def _numeric_typo_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()
    for match in _TYPO_THOUSANDS_RE.finditer(source_text):
        equivalents.add(match.group(1) + "000")
    for match in _COMMA_DIGIT_LIST_RE.finditer(source_text):
        equivalents.update(part.strip() for part in match.group(1).split(",") if part.strip())
    for match in _SPACED_COMMA_NUMBER_RE.finditer(source_text):
        equivalents.add(f"{match.group(1)}.{match.group(2)}")
    for match in _DECADE_WITH_TRAILING_NUMBER_RE.finditer(source_text):
        equivalents.add(f"{match.group(1)}.{match.group(2)}")
    return equivalents


def _number_word_phrase_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()
    tokens = text_tokens(source_text)
    for idx in range(len(tokens) - 1):
        century = _CENTURY_WORD_EQUIVALENTS.get(tokens[idx])
        tens = _NUMBER_WORD_EQUIVALENTS.get(tokens[idx + 1])
        if century is None or tens is None:
            continue
        value = int(tens)
        if value < 20:
            continue
        year = century + value
        if idx + 2 < len(tokens):
            unit = _NUMBER_WORD_EQUIVALENTS.get(tokens[idx + 2])
            if unit is not None and int(unit) < 10:
                year += int(unit)
        equivalents.add(str(year))
    return equivalents


def _multiplied_number_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()
    for match in _NUMBER_WITH_MULTIPLIER_RE.finditer(source_text):
        number_text = match.group(1)
        unit = match.group(2).lower()
        try:
            number = Decimal(number_text.replace(",", "."))
        except InvalidOperation:
            continue
        equivalents.add(number_text.replace(",", "."))
        multiplied = number * _MULTIPLIER_WORDS[unit]
        multiplied_text = _decimal_int_string(multiplied)
        if multiplied_text is not None:
            equivalents.add(multiplied_text)
        if unit == "trillion":
            as_billions = _decimal_int_string(number * Decimal("1000"))
            if as_billions is not None:
                equivalents.add(as_billions)
    for match in re.finditer(r"(?<!\d)\.(\d+)", source_text):
        equivalents.add(f"0.{match.group(1)}")
    for token in text_tokens(source_text):
        if token in _NUMBER_WORD_EQUIVALENTS:
            equivalents.add(_NUMBER_WORD_EQUIVALENTS[token])
    for regex in (_ORDINAL_SUFFIX_RE, _DECADE_SUFFIX_RE, _ATTACHED_UNIT_RE, _MONTH_ATTACHED_DAY_RE):
        for match in regex.finditer(source_text):
            number_text = match.group(1).replace(",", ".")
            if number_text.startswith("."):
                equivalents.add(f"0{number_text}")
            else:
                equivalents.add(number_text)
    for match in re.finditer(r"\b(\d{2})(\d{2})\s*[-–—]\s*(\d{2})\b", source_text):
        equivalents.add(match.group(1) + match.group(3))
    return equivalents


def _time_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()
    for match in _TWELVE_HOUR_TIME_RE.finditer(source_text):
        hour = int(match.group(1))
        minute = match.group(2)
        marker = match.group(3).lower()
        if not 1 <= hour <= 12:
            continue
        if marker.startswith("p") and hour != 12:
            hour += 12
        elif marker.startswith("a") and hour == 12:
            hour = 0
        equivalents.add(str(hour))
        if minute:
            equivalents.add(f"{hour}.{minute}")
    return equivalents


def _short_year_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()
    for regex in (_APOSTROPHE_YEAR_RE, _TRAILING_APOSTROPHE_YEAR_RE):
        for match in regex.finditer(source_text):
            year = match.group(1)
            equivalents.add(year)
            equivalents.add(f"19{year}")
            equivalents.add(f"20{year}")
    for match in _DECADE_SUFFIX_RE.finditer(source_text):
        decade = match.group(1)
        if len(decade) == 2:
            equivalents.add(f"19{decade}")
            equivalents.add(f"20{decade}")
    for match in _YEAR_RANGE_RE.finditer(source_text):
        start_year = match.group(1)
        end_year = match.group(2)
        equivalents.update(
            {
                start_year,
                end_year,
                f"19{start_year}",
                f"20{start_year}",
                f"19{end_year}",
                f"20{end_year}",
            }
        )
    return equivalents


def _unit_conversion_equivalents(source_text: str) -> set[str]:
    equivalents: set[str] = set()

    def decimal_match(match: re.Match[str]) -> Decimal | None:
        try:
            return Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
            return None

    for match in _MPH_RE.finditer(source_text):
        value = decimal_match(match)
        if value is not None:
            equivalents.add(str(int((value * Decimal("1.609344")).to_integral_value())))
    for match in _MILES_RE.finditer(source_text):
        value = decimal_match(match)
        if value is not None:
            equivalents.add(str(int((value * Decimal("1.609344")).to_integral_value())))
    for match in _FRACTIONAL_MILES_RE.finditer(source_text):
        numerator = Decimal(match.group(1))
        denominator = Decimal(match.group(2))
        if denominator:
            meters = numerator / denominator * Decimal("1609.344")
            equivalents.add(str(int((meters / Decimal("100")).to_integral_value() * 100)))
    for match in _FEET_RE.finditer(source_text):
        value = decimal_match(match)
        if value is not None:
            meters = value * Decimal("0.3048")
            equivalents.add(str(meters.quantize(Decimal("0.1")).normalize()))
    return equivalents


def _duration_equivalents(source_text: str, translated_text: str = "") -> set[str]:
    equivalents: set[str] = set()
    for match in _DECADE_COUNT_RE.finditer(source_text):
        equivalents.add(str(int(match.group(1)) * 10))
    if _AROUND_THE_CLOCK_RE.search(source_text):
        equivalents.add("24")
    if translated_text and _TRANSLATED_HALF_RE.search(translated_text):
        for match in re.finditer(r"(?<!\d)(\d+)\.5(?!\d)", source_text):
            equivalents.add(match.group(1))
    return equivalents


def digit_equivalence_set(values: list[str], source_text: str = "", translated_text: str = "") -> set[str]:
    equivalents = set(values)
    for value in values:
        equivalents.add(_canonical_digit_value(value))
        if value in {"00", "000"}:
            equivalents.add("2000")
        if "." in value:
            integer, fraction = value.split(".", maxsplit=1)
            if integer.isdigit() and fraction.isdigit() and len(fraction) == 3:
                equivalents.add(integer + fraction)
            if fraction and set(fraction) == {"0"}:
                equivalents.add(fraction)
                equivalents.add("0")
        if value.isdigit() and len(value) == 4 and value.endswith("0"):
            equivalents.add(str(int(value[2:])))
    equivalents.update(_multiplied_number_equivalents(source_text))
    equivalents.update(_time_equivalents(source_text))
    equivalents.update(_short_year_equivalents(source_text))
    equivalents.update(_unit_conversion_equivalents(source_text))
    equivalents.update(_duration_equivalents(source_text, translated_text))
    equivalents.update(_numeric_typo_equivalents(source_text))
    equivalents.update(_number_word_phrase_equivalents(source_text))
    return equivalents | {_canonical_digit_value(value) for value in equivalents}


def digit_sequences_changed(source_values: list[str], translation_values: list[str], source_text: str = "", translated_text: str = "") -> bool:
    if not source_values or not translation_values:
        return False
    source_equivalents = digit_equivalence_set(source_values, source_text, translated_text)
    translation_set = {_canonical_digit_value(value) for value in translation_values}
    return not translation_set <= source_equivalents


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
    source_digits = digit_sequences(source_text)
    translation_digits = digit_sequences(translated_text)
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
        "source_digit_sequences": source_digits,
        "translation_digit_sequences": translation_digits,
        "source_markers": source_markers,
        "translation_markers": translation_markers,
        "html_entities_in_translation": translation_entities,
        "english_signal_tokens_in_translation": sorted(set(english_signal_tokens)),
        "english_signal_token_count_in_translation": len(english_signal_tokens),
        "unchanged_norm_match": bool(norm_text(source_text) and norm_text(source_text) == norm_text(translated_text)),
    }


def empty_translated(source: str, translated: str) -> bool:
    return bool(source.strip()) and not translated.strip()
