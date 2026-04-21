from collections import Counter
from pathlib import Path

from datasets import DatasetDict

from data_translate.config.models_dataset_reformat import ReformatRulesModel
from data_translate.domain.reformat_common import load_json, normalize_dialogue_id


def inspect_candidate(
    *,
    candidate_name: str,
    candidate_path: Path,
    rules: ReformatRulesModel,
    source: DatasetDict,
) -> dict[str, object]:
    data = load_json(candidate_path)
    raw_ids = set(data.keys())
    normalized_ids = {normalize_dialogue_id(dialogue_id, rules.dialogue_id_strip_prefixes) for dialogue_id in raw_ids}

    ids_by_split = {split: set(source[split][rules.source_dialogue_id_field]) for split in source}
    rows_by_dialogue: Counter[str] = Counter()
    for split in source:
        rows_by_dialogue.update(source[split][rules.source_dialogue_id_field])

    turn_pairs = Counter()
    mismatched_turn_counts = 0
    for raw_id, dialogue in data.items():
        dialogue_id = normalize_dialogue_id(raw_id, rules.dialogue_id_strip_prefixes)
        if dialogue_id not in rows_by_dialogue:
            continue
        external_turns = len(dialogue.get(rules.external_log_field, []))
        source_rows = rows_by_dialogue[dialogue_id]
        turn_pairs[(source_rows, external_turns)] += 1
        if external_turns != source_rows * rules.turns_per_row:
            mismatched_turn_counts += 1

    split_coverage = {
        split: {
            "source_dialogues": len(ids),
            "covered": len(ids & normalized_ids),
            "missing": len(ids - normalized_ids),
        }
        for split, ids in ids_by_split.items()
    }

    first_text = ""
    if data:
        first_key = next(iter(data))
        turns = data[first_key].get(rules.external_log_field, [])
        if turns:
            first_text = str(turns[0].get(rules.external_turn_text_field, ""))

    return {
        "candidate": candidate_name,
        "path": str(candidate_path),
        "dialogues": len(raw_ids),
        "normalized_dialogues": len(normalized_ids),
        "source_dialogues": len(rows_by_dialogue),
        "intersection": len(normalized_ids & set(rows_by_dialogue)),
        "source_not_external": len(set(rows_by_dialogue) - normalized_ids),
        "external_not_source": len(normalized_ids - set(rows_by_dialogue)),
        "sample_source_not_external": sorted(set(rows_by_dialogue) - normalized_ids)[:20],
        "sample_external_not_source": sorted(normalized_ids - set(rows_by_dialogue))[:20],
        "split_coverage": split_coverage,
        "turn_alignment": {
            "mismatched_turn_counts": mismatched_turn_counts,
            "most_common_source_rows_vs_external_turns": [
                {"source_rows": pair[0][0], "external_turns": pair[0][1], "count": pair[1]}
                for pair in turn_pairs.most_common(20)
            ],
        },
        "first_text": first_text,
    }
