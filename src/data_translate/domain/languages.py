import re

LANG_NAMES = {
    "ar": "Arabic", "cs": "Czech", "de": "German", "en": "English", "es": "Spanish",
    "et": "Estonian", "fi": "Finnish", "fr": "French", "hr": "Croatian", "ja": "Japanese",
    "ko": "Korean", "liv": "Livonian", "lv": "Latvian", "ne": "Nepali", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sah": "Sakha", "si": "Sinhala", "tr": "Turkish",
    "uk": "Ukrainian", "zh": "Chinese",
}
LANG_CODES = {name.lower(): code for code, name in LANG_NAMES.items()}


def language_label(value: str) -> str:
    text = str(value).strip()
    return LANG_NAMES.get(text.lower(), text)


def language_code(value: str) -> str:
    text = str(value).strip().lower()
    if text in LANG_NAMES:
        return text
    return LANG_CODES.get(text, text)


def language_names(lp: str) -> tuple[str, str]:
    parts = re.split(r"[-_]", str(lp), maxsplit=1)
    if len(parts) != 2:
        return str(lp), str(lp)
    src, tgt = parts[0].lower(), parts[1].lower()
    return LANG_NAMES.get(src, src), LANG_NAMES.get(tgt, tgt)


def extract_language_pair(value: object) -> str:
    text = str(value)
    if "/" in text:
        text = text.rsplit("/", maxsplit=1)[-1]
    return text.replace("_", "-")
