from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.config.models_dataset_translation import TranslationSpecModel
from data_translate.config.models_runtime_policies import TranslationRunPolicyModel
from data_translate.domain.translation_checkpoints import pending_rows_for_range, restore_state_from_checkpoint, split_limit
from data_translate.domain.translation_row import translate_row
from data_translate.domain.translation_state import apply_record, materialize_split, missing_rows, target_fields
from data_translate.engine.execution import process_jsonl_records


@dataclass(frozen=True)
class TranslationRunResult:
    dataset: DatasetDict
    failed_splits: list[str]


def _format_translation_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def _translation_error_record(
    task: tuple[int, dict[str, Any]],
    exc: BaseException,
    *,
    translation: TranslationSpecModel,
) -> dict[str, object]:
    row_idx, row = task
    outputs = {
        str(rule.target or rule.source): row.get(rule.source)
        for rule in translation.rules
    }
    return {
        "row_idx": row_idx,
        **outputs,
        "error": _format_translation_exception(exc),
        "attempts": 0,
        "status": "error",
    }


async def _translate_split(
    *,
    split: str,
    split_dataset: Dataset,
    translation: TranslationSpecModel,
    runtime: TranslationRunPolicyModel,
    checkpoint_path: Path,
    adapter: TranslationAdapter,
) -> tuple[Dataset, bool]:
    fields = target_fields(translation.rules)
    limit = split_limit(split_dataset, runtime.max_rows_per_split)
    state, _done = restore_state_from_checkpoint(
        checkpoint_path=checkpoint_path,
        limit=limit,
        fields=fields,
    )
    has_errors = False

    for start_idx in range(0, limit, runtime.batch_size):
        end_idx = min(start_idx + runtime.batch_size, limit)
        rows = pending_rows_for_range(
            dataset=split_dataset,
            state=state,
            fields=fields,
            start_idx=start_idx,
            end_idx=end_idx,
        )
        if not rows:
            continue
        records = await process_jsonl_records(
            output_path=checkpoint_path,
            tasks=rows,
            is_done=lambda _task: False,
            process_item=lambda item: translate_row(item[0], item[1], translation.rules, adapter),
            concurrency=runtime.concurrency,
            desc=f"translate {split} {start_idx}:{end_idx}",
            on_process_error=lambda item, exc: _translation_error_record(item, exc, translation=translation),
        )
        for record in records:
            apply_record(state, record, fields)
        if any(str(record.get("error", "")).strip() for record in records):
            has_errors = True

    missing = missing_rows(state, limit, fields)
    if missing:
        raise RuntimeError(f"{split}: missing translated rows after checkpoints: {missing[:20]}")

    materialized = materialize_split(
        split_dataset,
        limit,
        state,
        fields,
        translation.drop_columns,
        chunk_size=runtime.batch_size,
    )
    return materialized, has_errors


async def translate_dataset_splits(
    *,
    dataset: DatasetDict,
    translation: TranslationSpecModel,
    runtime: TranslationRunPolicyModel,
    checkpoint_dir: Path,
    adapter: TranslationAdapter,
) -> TranslationRunResult:
    translated = DatasetDict()
    failed_splits: list[str] = []

    for split, split_dataset in dataset.items():
        materialized, has_errors = await _translate_split(
            split=split,
            split_dataset=split_dataset,
            translation=translation,
            runtime=runtime,
            checkpoint_path=checkpoint_dir / f"{split}.jsonl",
            adapter=adapter,
        )
        translated[split] = materialized
        if has_errors:
            failed_splits.append(split)

    return TranslationRunResult(
        dataset=translated,
        failed_splits=sorted(set(failed_splits)),
    )
