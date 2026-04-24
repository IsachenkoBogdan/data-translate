def split_structured_entity(value: str, separator: str) -> tuple[str, str, str] | None:
    parts = value.split(separator, 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def extract_quoted_value(text: str, *, start_idx: int) -> tuple[str, int] | None:
    if start_idx >= len(text):
        return None
    quote = text[start_idx]
    if quote not in {'"', "'"}:
        return None

    # WebLINX occasionally stores quoted utterances as utterance=""..."".
    # Treat the inner quotes as content rather than an empty string payload.
    if start_idx + 1 < len(text) and text[start_idx + 1] == quote:
        value_chars = [quote]
        idx = start_idx + 2
        escaped = False
        while idx < len(text):
            char = text[idx]
            if escaped:
                value_chars.append(char)
                escaped = False
            elif char == "\\":
                value_chars.append(char)
                escaped = True
            elif char == quote and idx + 1 < len(text) and text[idx + 1] == quote:
                value_chars.append(char)
                return "".join(value_chars), idx + 1
            else:
                value_chars.append(char)
            idx += 1
        return None

    value_chars: list[str] = []
    idx = start_idx + 1
    escaped = False
    while idx < len(text):
        char = text[idx]
        if escaped:
            value_chars.append(char)
            escaped = False
        elif char == "\\":
            value_chars.append(char)
            escaped = True
        elif char == quote:
            return "".join(value_chars), idx
        else:
            value_chars.append(char)
        idx += 1
    return None
