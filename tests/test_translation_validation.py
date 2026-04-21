import anyio
import pytest
from datasets import Dataset, DatasetDict

from data_translate.adapters.translation_base import TranslationResult
from data_translate.config.loader import load_workflow_model
from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.preflight import validate_translate_inputs
from data_translate.domain.translation_row import translate_by_rule, translate_row
from data_translate.domain.translation_state import apply_record, init_state, materialize_split, missing_rows, record_succeeded, row_complete
from data_translate.domain.translation_validation import rule_validation_error, validate_rule_value


class DummyAdapter:
    async def translate(self, text: str, *, use_cache: bool) -> TranslationResult:
        del use_cache
        if "@@0@@" in text:
            lines = []
            for line in text.splitlines():
                marker, content = line.split(" ", 1)
                lines.append(f"{marker} fr:{content}")
            return TranslationResult(text="\n".join(lines), status="ok", attempts=1, error="")
        return TranslationResult(text=f"fr:{text}", status="ok", attempts=1, error="")

    def close(self) -> None:
        return None


def test_validate_translate_inputs_checks_columns_but_not_full_row_shapes() -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    translation = config.dataset.translation
    assert translation is not None
    dataset = DatasetDict(
        {
            "test": Dataset.from_dict(
                {
                    "history": ["not-a-list"],
                    "knowledge": ["fact"],
                }
            )
        }
    )

    validate_translate_inputs(dataset, translation)


def test_rule_validation_error_for_dialog_content_requires_mappings() -> None:
    rule = TranslationRuleModel(source="text", strategy="dialog_turns_content")
    error = rule_validation_error(rule, ["hello", "world"])
    assert "must contain mappings" in error


def test_validate_rule_value_rejects_nested_text_list_items() -> None:
    rule = TranslationRuleModel(source="history", strategy="text_list")
    with pytest.raises(ValueError, match="must contain only scalar text-like items"):
        validate_rule_value(rule, [{"content": "hello"}])


def test_translate_row_raises_on_invalid_runtime_shape() -> None:
    rule = TranslationRuleModel(source="history", target="history_fr", strategy="text_list")

    async def run() -> None:
        await translate_row(0, {"history": "bad-shape"}, [rule], DummyAdapter())

    with pytest.raises(ValueError, match="strategy 'text_list' must be a list"):
        anyio.run(run)


def test_translate_row_collects_outputs_and_attempts() -> None:
    rules = [
        TranslationRuleModel(source="knowledge", target="knowledge_fr", strategy="text"),
        TranslationRuleModel(source="history", target="history_fr", strategy="text_list"),
    ]

    async def run() -> dict[str, object]:
        return await translate_row(2, {"knowledge": "fact", "history": ["hello", "bye"]}, rules, DummyAdapter())

    record = anyio.run(run)
    assert record["row_idx"] == 2
    assert record["knowledge_fr"] == "fr:fact"
    assert record["history_fr"] == ["fr:hello", "fr:bye"]
    assert record["attempts"] == 2
    assert record["status"] == "ok"
    assert record["error"] == ""


def test_serialized_dialog_turns_content_adds_content_fr() -> None:
    rule = TranslationRuleModel(
        source="query",
        target="query_fr",
        strategy="serialized_dialog_turns_content",
        options={"content_field": "content", "target_content_field": "content_fr"},
    )
    row = {
        "query": (
            '[{"role":"user","content":"hello"},{"role":"operator","content":"how can I help?"}]'
        )
    }

    async def run() -> dict[str, object]:
        return await translate_row(3, row, [rule], DummyAdapter())

    record = anyio.run(run)
    assert record["status"] == "ok"
    assert record["attempts"] == 1
    assert (
        record["query_fr"]
        == '[{"role": "user", "content": "hello", "content_fr": "fr:hello"}, {"role": "operator", "content": "how can I help?", "content_fr": "fr:how can I help?"}]'
    )


def test_serialized_dialog_turns_content_requires_json_string() -> None:
    rule = TranslationRuleModel(source="query", target="query_fr", strategy="serialized_dialog_turns_content")

    async def run() -> None:
        await translate_row(0, {"query": [{"role": "user", "content": "hello"}]}, [rule], DummyAdapter())

    with pytest.raises(ValueError, match="must be a string"):
        anyio.run(run)


def test_translate_by_rule_rejects_unknown_strategy() -> None:
    rule = TranslationRuleModel.model_construct(source="text", strategy="missing")

    async def run() -> None:
        await translate_by_rule(rule, {"text": "hello"}, DummyAdapter())

    with pytest.raises(ValueError, match="unknown translation strategy"):
        anyio.run(run)


def test_translation_state_helpers_cover_missing_rows_and_empty_materialization() -> None:
    fields = ["text_fr"]
    state = init_state(3, fields)

    apply_record(state, {"row_idx": 0, "text_fr": "bonjour"}, fields)
    assert row_complete(state, 0, fields) is True
    assert row_complete(state, 1, fields) is False
    assert missing_rows(state, 3, fields) == [1, 2]

    dataset = Dataset.from_dict({"text": []})
    materialized = materialize_split(dataset, 0, state, fields, ["text"], chunk_size=2)
    assert materialized.column_names == ["text_fr"]
    assert materialized["text_fr"] == []


def test_apply_record_requires_all_target_fields() -> None:
    state = init_state(1, ["text_fr"])

    with pytest.raises(ValueError, match="missing required translated fields"):
        apply_record(state, {"row_idx": 0}, ["text_fr"])


def test_record_succeeded_requires_non_error_status() -> None:
    assert record_succeeded({"row_idx": 0, "text_fr": "bonjour", "status": "ok"}, ["text_fr"]) is True
    assert record_succeeded({"row_idx": 0, "text_fr": "bonjour", "status": "error"}, ["text_fr"]) is False
