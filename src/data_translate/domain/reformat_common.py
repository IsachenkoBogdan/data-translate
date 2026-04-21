import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from datasets import Dataset

from data_translate.config.models_dataset_reformat import ReformatRulesModel


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_dialogue_id(dialogue_id: str, strip_prefixes: list[str]) -> str:
    for prefix in strip_prefixes:
        if dialogue_id.startswith(prefix):
            return dialogue_id[len(prefix) :]
    return dialogue_id


def normalize_dialogues(data: dict[str, Any], strip_prefixes: list[str]) -> dict[str, dict[str, Any]]:
    return {normalize_dialogue_id(dialogue_id, strip_prefixes): dialogue for dialogue_id, dialogue in data.items()}


def group_indices_by_dialogue(dataset: Dataset, dialogue_id_field: str) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for idx, dialogue_id in enumerate(dataset[dialogue_id_field]):
        grouped[str(dialogue_id)].append(idx)
    return dict(grouped)


def convert_dialogue_rows(dialogue: dict[str, Any], rows_count: int, rules: ReformatRulesModel) -> tuple[list[str], list[list[dict[str, str]]]]:
    log = list(dialogue.get(rules.external_log_field, []))
    if len(log) != rows_count * rules.turns_per_row:
        raise ValueError(f"expected {rows_count * rules.turns_per_row} turns, found {len(log)}")

    texts: list[str] = []
    histories: list[list[dict[str, str]]] = []
    for row_pos in range(rows_count):
        user_turn_idx = row_pos * rules.turns_per_row + rules.user_turn_offset
        history_turns = []
        for turn_idx in range(user_turn_idx):
            role = rules.history_role_cycle[turn_idx % len(rules.history_role_cycle)]
            history_turns.append(
                {
                    rules.history_content_field: str(log[turn_idx].get(rules.external_turn_text_field, "")),
                    rules.history_role_field: role,
                }
            )
        texts.append(str(log[user_turn_idx].get(rules.external_turn_text_field, "")))
        histories.append(history_turns)
    return texts, histories
