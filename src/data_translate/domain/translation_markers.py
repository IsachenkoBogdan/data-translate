import re

MARKER_RE = re.compile(r"@@\s*(\d+)\s*@@")


def build_marked_text(items: list[str]) -> str:
    return "\n".join(f"@@{idx}@@ {item}" for idx, item in enumerate(items))


def parse_marked_translation(text: str, expected_count: int) -> list[str]:
    matches = list(MARKER_RE.finditer(text))
    if len(matches) != expected_count:
        raise ValueError(f"expected {expected_count} markers, found {len(matches)}")

    translations: dict[int, str] = {}
    for pos, match in enumerate(matches):
        idx = int(match.group(1))
        if idx in translations:
            raise ValueError(f"duplicate marker @@{idx}@@")
        if idx < 0 or idx >= expected_count:
            raise ValueError(f"unexpected marker @@{idx}@@")
        start = match.end()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if not value:
            raise ValueError(f"empty translation for marker @@{idx}@@")
        translations[idx] = value

    missing = sorted(set(range(expected_count)) - set(translations))
    if missing:
        raise ValueError(f"missing markers: {missing}")
    return [translations[idx] for idx in range(expected_count)]
