import re


_INDEX_RE = re.compile(r"\[(\d+)\]")


def normalized_field_path(field: str) -> str:
    return _INDEX_RE.sub("[]", field)


def root_field(field: str) -> str:
    if not field:
        return ""
    return re.split(r"[\[.]", field, maxsplit=1)[0]


def field_positions(field: str) -> tuple[int, ...]:
    return tuple(int(match) + 1 for match in _INDEX_RE.findall(field))


def field_position_kind(field: str) -> str:
    normalized = normalized_field_path(field).lower()
    if ".content" in normalized or "dialog" in normalized or "turn" in normalized:
        return "turn"
    return "item"


def field_position_note(field: str) -> str:
    positions = field_positions(field)
    if not positions:
        return ""
    kind = field_position_kind(field)
    if len(positions) == 1:
        return f"{kind} {positions[0]}"
    return " / ".join(f"{kind} {position}" for position in positions)


def field_group_position_summary(fields: set[str]) -> str:
    positions = sorted({position for field in fields for position in field_positions(field)})
    if not positions:
        return ""
    kind = field_position_kind(next(iter(fields)))
    if len(positions) == 1:
        return f"{kind} {positions[0]}"
    if positions == list(range(positions[0], positions[-1] + 1)):
        return f"{kind}s {positions[0]}-{positions[-1]}"
    if len(positions) <= 4:
        return f"{kind}s " + ", ".join(str(position) for position in positions)
    return f"{len(positions)} {kind} positions"
