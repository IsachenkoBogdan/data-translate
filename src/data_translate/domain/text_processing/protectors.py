import re


ACTION_RE = re.compile(
    r"\b(?:say|click|load|text_input|scroll|change|paste|copy|tabcreate|tabswitch|submit|hover|tabremove)\("
)


def action_sequence(text: str) -> list[str]:
    return ACTION_RE.findall(text)
