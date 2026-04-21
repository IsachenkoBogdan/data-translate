from pathlib import Path

import anyio
from datasets import Dataset, DatasetDict

from data_translate.config.loader import load_workflow_model
from data_translate.engine.execution import process_jsonl_records
from data_translate.engine.jsonl import load_jsonl
from data_translate.engine.jsonl import write_jsonl
from data_translate.domain.translation_checkpoints import restore_state_from_checkpoint
from data_translate.engine.translation_run import translate_dataset_splits


class DummyAdapter:
    async def translate(self, text: str, *, use_cache: bool):
        del use_cache
        return type("Result", (), {"text": f"fr:{text}", "status": "ok", "attempts": 1, "error": ""})()

    def close(self) -> None:
        return None


def test_process_jsonl_records_uses_error_fallback(tmp_path: Path) -> None:
    output_path = tmp_path / "records.jsonl"

    async def process_item(task: int) -> dict[str, object]:
        if task == 2:
            raise RuntimeError("boom")
        return {"task": task, "status": "ok"}

    async def run() -> None:
        await process_jsonl_records(
            output_path=output_path,
            tasks=[1, 2, 3],
            is_done=lambda _task: False,
            process_item=process_item,
            on_process_error=lambda task, exc: {"task": task, "status": "error", "error": str(exc)},
            concurrency=2,
            desc="test",
        )

    anyio.run(run)
    rows = load_jsonl(output_path)
    assert len(rows) == 3
    assert any(row["status"] == "error" and row["task"] == 2 for row in rows)


def test_translate_dataset_splits_marks_failed_split_and_keeps_row_materializable(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    translation = config.dataset.translation
    assert translation is not None

    dataset = DatasetDict(
        {
            "test": Dataset.from_dict(
                {
                    "history": ["bad-shape"],
                    "knowledge": ["fact"],
                }
            )
        }
    )

    async def run():
        return await translate_dataset_splits(
            dataset=dataset,
            translation=translation,
            runtime=config.runtime,
            checkpoint_dir=tmp_path / "checkpoint",
            adapter=DummyAdapter(),
        )

    result = anyio.run(run)
    assert result.failed_splits == ["test"]
    assert result.dataset["test"]["history_fr"] == ["bad-shape"]
    assert result.dataset["test"]["knowledge_fr"] == ["fact"]


def test_restore_state_from_checkpoint_skips_error_rows_for_retry(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    write_jsonl(
        checkpoint_path,
        [
            {"row_idx": 0, "text_fr": "bonjour", "status": "ok", "error": ""},
            {"row_idx": 1, "text_fr": "hello", "status": "error", "error": "boom"},
        ],
    )

    state, done = restore_state_from_checkpoint(
        checkpoint_path=checkpoint_path,
        limit=2,
        fields=["text_fr"],
    )

    assert sorted(done) == [0, 1]
    assert 0 in state
    assert 1 not in state
