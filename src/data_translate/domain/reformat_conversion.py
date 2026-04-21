from pathlib import Path

from datasets import Dataset, DatasetDict, concatenate_datasets

from data_translate.config.models_dataset_reformat import ReformatRulesModel
from data_translate.domain.reformat_common import convert_dialogue_rows, group_indices_by_dialogue, load_json, normalize_dialogues


REFORMAT_CHUNK_SIZE = 1000


def _empty_reformatted_split(
    dataset: Dataset,
    *,
    candidate_name: str,
    rules: ReformatRulesModel,
) -> Dataset:
    empty = dataset.select([])
    empty_data = empty.to_dict()
    empty_data[rules.backup_fields.text] = []
    empty_data[rules.backup_fields.history] = []
    empty_data[rules.target_text_field] = []
    empty_data[rules.target_history_field] = []
    empty_data[rules.variant_field] = []
    return Dataset.from_dict(empty_data)


def _materialize_reformatted_split(
    dataset: Dataset,
    *,
    keep_indices: list[int],
    candidate_name: str,
    rules: ReformatRulesModel,
    new_text_by_idx: dict[int, str],
    new_history_by_idx: dict[int, list[dict[str, str]]],
    chunk_size: int = REFORMAT_CHUNK_SIZE,
) -> Dataset:
    if not keep_indices:
        return _empty_reformatted_split(
            dataset,
            candidate_name=candidate_name,
            rules=rules,
        )

    chunks: list[Dataset] = []
    step = max(1, int(chunk_size))
    for start_idx in range(0, len(keep_indices), step):
        chunk_indices = keep_indices[start_idx : start_idx + step]
        chunk = dataset.select(chunk_indices)
        chunk_data = chunk.to_dict()
        original_text = list(chunk_data[rules.source_text_field])
        original_history = list(chunk_data[rules.source_history_field])

        converted_text: list[str] = []
        converted_history: list[list[dict[str, str]]] = []
        for original_idx, old_text, old_history in zip(chunk_indices, original_text, original_history, strict=True):
            converted_text.append(new_text_by_idx.get(original_idx, old_text))
            converted_history.append(new_history_by_idx.get(original_idx, old_history))

        chunk_data[rules.backup_fields.text] = original_text
        chunk_data[rules.backup_fields.history] = original_history
        chunk_data[rules.target_text_field] = converted_text
        chunk_data[rules.target_history_field] = converted_history
        chunk_data[rules.variant_field] = [candidate_name] * len(chunk_indices)
        chunks.append(Dataset.from_dict(chunk_data))

    return chunks[0] if len(chunks) == 1 else concatenate_datasets(chunks)


def reformat_candidate(
    *,
    candidate_name: str,
    candidate_path: Path,
    rules: ReformatRulesModel,
    source: DatasetDict,
    missing_policy: str,
) -> tuple[DatasetDict, dict[str, object]]:
    normalized = normalize_dialogues(load_json(candidate_path), rules.dialogue_id_strip_prefixes)
    converted = DatasetDict()
    summary: dict[str, object] = {"candidate": candidate_name, "output": "", "splits": {}}

    for split, dataset in source.items():
        grouped = group_indices_by_dialogue(dataset, rules.source_dialogue_id_field)
        keep_indices: list[int] = []
        new_text_by_idx: dict[int, str] = {}
        new_history_by_idx: dict[int, list[dict[str, str]]] = {}
        missing_dialogues: list[str] = []
        bad_dialogues: list[dict[str, str]] = []

        for dialogue_id, indices in grouped.items():
            dialogue = normalized.get(dialogue_id)
            if dialogue is None:
                missing_dialogues.append(dialogue_id)
                if missing_policy == "keep_source":
                    keep_indices.extend(indices)
                continue
            try:
                texts, histories = convert_dialogue_rows(dialogue, len(indices), rules)
            except ValueError as exc:
                bad_dialogues.append({"dialogue_id": dialogue_id, "error": str(exc)})
                if missing_policy == "keep_source":
                    keep_indices.extend(indices)
                continue
            keep_indices.extend(indices)
            for row_idx, text, history in zip(indices, texts, histories, strict=True):
                new_text_by_idx[row_idx] = text
                new_history_by_idx[row_idx] = history

        keep_indices = sorted(set(keep_indices))
        converted[split] = _materialize_reformatted_split(
            dataset,
            keep_indices=keep_indices,
            candidate_name=candidate_name,
            rules=rules,
            new_text_by_idx=new_text_by_idx,
            new_history_by_idx=new_history_by_idx,
        )
        summary["splits"] = dict(summary["splits"])
        summary["splits"][split] = {
            "source_rows": len(dataset),
            "output_rows": len(keep_indices),
            "missing_dialogues": len(missing_dialogues),
            "bad_dialogues": len(bad_dialogues),
            "sample_missing_dialogues": missing_dialogues[:20],
            "sample_bad_dialogues": bad_dialogues[:5],
        }

    return converted, summary
