from pathlib import Path
import runpy
from unittest.mock import patch

import anyio
import pytest
from datasets import Dataset

from data_translate.adapters.translation_base import TranslationResult
from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.languages import extract_language_pair, language_code, language_label, language_names
from data_translate.domain.renderers import action_sequence, dialog_turns, numbered_list, render_value
from data_translate.domain.text_processing.guards import should_skip_translation
from data_translate.domain.text_processing.chunking import chunk_text
from data_translate.domain.text_processing.parsers import extract_quoted_value, split_structured_entity
from data_translate.domain.translation_checkpoints import (
    build_translate_records,
    pending_rows_for_range,
    restore_state_from_checkpoint,
    split_limit,
)
from data_translate.domain.translation_common import merge_translation_errors, rule_options, translate_sequence
from data_translate.domain.translation_markers import build_marked_text, parse_marked_translation
from data_translate.domain.translation_state import init_state, materialize_split
from data_translate.domain.translation_strategies.dialog import translate_dialog_turns_content
from data_translate.domain.translation_strategies.structured import translate_structured_entity
from data_translate.domain.translation_strategies.text import translate_text, translate_text_list
from data_translate.domain.translation_strategies.weblinx import _split_records, translate_weblinx_query
from data_translate.engine.jsonl import append_jsonl, load_jsonl, load_jsonl_index, write_jsonl


class QueueAdapter:
    def __init__(self, responses: list[TranslationResult]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, bool]] = []

    async def translate(self, text: str, *, use_cache: bool) -> TranslationResult:
        self.calls.append((text, use_cache))
        return self.responses.pop(0)


def test_translation_markers_roundtrip() -> None:
    text = build_marked_text(["hello", "world"])
    assert text == "@@0@@ hello\n@@1@@ world"
    assert parse_marked_translation("@@0@@ bonjour\n@@1@@ monde", 2) == ["bonjour", "monde"]


def test_translation_markers_reject_duplicate_and_empty_values() -> None:
    with pytest.raises(ValueError, match="duplicate marker"):
        parse_marked_translation("@@0@@ one\n@@0@@ again", 2)
    with pytest.raises(ValueError, match="empty translation"):
        parse_marked_translation("@@0@@   ", 1)


def test_translate_sequence_successful_marked_translation() -> None:
    adapter = QueueAdapter([TranslationResult(text="@@0@@ bonjour\n@@1@@ salut", status="ok", attempts=1, error="")])

    async def run():
        return await translate_sequence(["hello", "bye"], adapter, use_cache=True)

    translated, attempts, error = anyio.run(run)
    assert translated == ["bonjour", "salut"]
    assert attempts == 1
    assert error == ""
    assert adapter.calls == [("@@0@@ hello\n@@1@@ bye", False)]


def test_translate_sequence_falls_back_to_item_level_translation() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="unparseable", status="ok", attempts=1, error=""),
            TranslationResult(text="bonjour", status="ok", attempts=1, error=""),
            TranslationResult(text=None, status="error", attempts=1, error="provider failed"),
        ]
    )

    async def run():
        return await translate_sequence(["hello", "bye"], adapter, use_cache=True)

    translated, attempts, error = anyio.run(run)
    assert translated == ["bonjour", "bye"]
    assert attempts == 3
    assert "whole-list parse failed" in error
    assert "item 1: provider failed" in error


def test_translate_sequence_clears_marked_parse_error_after_clean_fallback() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="@@0@@ bonjour\n@@1@@ ", status="ok", attempts=1, error=""),
            TranslationResult(text="bonjour", status="ok", attempts=1, error=""),
            TranslationResult(text="  ", status="empty", attempts=0, error=""),
        ]
    )

    async def run():
        return await translate_sequence(["hello", "  "], adapter, use_cache=True)

    translated, attempts, error = anyio.run(run)
    assert translated == ["bonjour", "  "]
    assert attempts == 2
    assert error == ""


def test_translation_strategies_cover_text_dialog_and_weblinx() -> None:
    async def run():
        text_result = await translate_text(
            "hello",
            QueueAdapter([TranslationResult(text="bonjour", status="ok", attempts=1, error="")]),
            {},
            use_cache=True,
        )
        text_list_result = await translate_text_list(
            ["hello", "bye"],
            QueueAdapter([TranslationResult(text="@@0@@ bonjour\n@@1@@ salut", status="ok", attempts=1, error="")]),
            {},
            use_cache=True,
        )
        dialog_result = await translate_dialog_turns_content(
            [{"role": "user", "content": "hello"}],
            QueueAdapter([TranslationResult(text="@@0@@ bonjour", status="ok", attempts=1, error="")]),
            {},
            use_cache=True,
        )
        weblinx_result = await translate_weblinx_query(
            "User: hello\nclick(button)",
            QueueAdapter([TranslationResult(text="bonjour", status="ok", attempts=1, error="")]),
            {},
            use_cache=True,
        )
        return text_result, text_list_result, dialog_result, weblinx_result

    text_result, text_list_result, dialog_result, weblinx_result = anyio.run(run)
    assert text_result.value == "bonjour"
    assert text_list_result.value == ["bonjour", "salut"]
    assert dialog_result.value == [{"role": "user", "content": "bonjour"}]
    assert weblinx_result.value == "User: bonjour\nclick(button)"


def test_text_strategy_retries_unchanged_meaningful_translation_without_cache() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="May I try this on?", status="ok", attempts=1, error=""),
            TranslationResult(text="Puis-je l'essayer ?", status="ok", attempts=1, error=""),
        ]
    )

    async def run():
        return await translate_text(
            "May I try this on?",
            adapter,
            {"retry_unchanged": True, "unchanged_min_letters": 8},
            use_cache=True,
        )

    result = anyio.run(run)
    assert result.value == "Puis-je l'essayer ?"
    assert result.error == ""
    assert result.attempts == 2
    assert adapter.calls == [("May I try this on?", True), ("May I try this on?", False)]


def test_text_list_strategy_retries_unchanged_items_without_cache() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="@@0@@ May I try this on?\n@@1@@ Bonjour", status="ok", attempts=1, error=""),
            TranslationResult(text="Puis-je l'essayer ?", status="ok", attempts=1, error=""),
        ]
    )

    async def run():
        return await translate_text_list(
            ["May I try this on?", "Hello"],
            adapter,
            {"retry_unchanged": True, "unchanged_min_letters": 8},
            use_cache=True,
        )

    result = anyio.run(run)
    assert result.value == ["Puis-je l'essayer ?", "Bonjour"]
    assert result.error == ""
    assert result.attempts == 2
    assert adapter.calls == [
        ("@@0@@ May I try this on?\n@@1@@ Hello", False),
        ("May I try this on?", False),
    ]


def test_text_list_strategy_reports_unchanged_items_after_retry() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="@@0@@ May I try this on?", status="ok", attempts=1, error=""),
            TranslationResult(text="May I try this on?", status="ok", attempts=1, error=""),
        ]
    )

    async def run():
        return await translate_text_list(
            ["May I try this on?"],
            adapter,
            {"retry_unchanged": True, "unchanged_min_letters": 8},
            use_cache=True,
        )

    result = anyio.run(run)
    assert result.value == ["May I try this on?"]
    assert "item 0: unchanged translation" in result.error
    assert result.attempts == 2


def test_text_processing_guards_support_no_letters_and_fullmatch_regex() -> None:
    assert should_skip_translation("1978.", {"guards": [{"kind": "no_letters"}]}) is True
    assert should_skip_translation("English text.", {"guards": [{"kind": "no_letters"}]}) is False
    assert should_skip_translation("DOC-123", {"guards": [{"kind": "fullmatch_regex", "pattern": r"DOC-\d+"}]}) is True


def test_text_processing_parsers_cover_structured_entities_and_quoted_values() -> None:
    assert split_structured_entity("Name <S> tags <S> description", " <S> ") == ("Name", "tags", "description")
    assert extract_quoted_value('utterance="hello \\"world\\""', start_idx=len("utterance=")) == (
        'hello \\"world\\"',
        26,
    )


def test_text_processing_chunks_long_text_on_word_boundaries() -> None:
    chunks = chunk_text("alpha beta gamma delta", max_chars=11)
    assert chunks == ["alpha beta ", "gamma delta"]
    assert all(len(chunk) <= 11 for chunk in chunks)
    assert "".join(chunks) == "alpha beta gamma delta"


def test_structured_entity_translates_description_but_preserves_name_tags_and_separators() -> None:
    adapter = QueueAdapter([TranslationResult(text="description francaise", status="ok", attempts=1, error="")])
    value = (
        "Chester Newell Righter <S> organization.founder organization.member people.person <S> "
        "English biography."
    )

    async def run():
        return await translate_structured_entity(value, adapter, {}, use_cache=True)

    result = anyio.run(run)
    assert result.value == (
        "Chester Newell Righter <S> organization.founder organization.member people.person <S> "
        "description francaise"
    )
    assert result.attempts == 1
    assert result.error == ""
    assert adapter.calls == [("English biography.", True)]


def test_structured_entity_preserves_empty_description_marker_without_translation_call() -> None:
    adapter = QueueAdapter([])
    value = "Chester Newell Righter <S> organization.founder organization.member people.person <S> "

    async def run():
        return await translate_structured_entity(value, adapter, {}, use_cache=True)

    result = anyio.run(run)
    assert result.value == value
    assert result.attempts == 0
    assert result.error == ""
    assert adapter.calls == []


def test_structured_entity_translates_long_description_in_chunks() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="fr:alpha beta", status="ok", attempts=1, error=""),
            TranslationResult(text="fr: gamma", status="ok", attempts=1, error=""),
        ]
    )
    value = "Name <S> tags <S> alpha beta gamma"

    async def run():
        return await translate_structured_entity(value, adapter, {"max_chunk_chars": 10}, use_cache=True)

    result = anyio.run(run)
    assert result.value == "Name <S> tags <S> fr:alpha betafr: gamma"
    assert result.attempts == 2
    assert result.error == ""
    assert adapter.calls == [("alpha beta", True), (" gamma", True)]


def test_weblinx_strategy_translates_agent_utterance_mode() -> None:
    async def run() -> None:
        return await translate_weblinx_query(
            'Agent: say(speaker="navigator", utterance="Please wait")',
            QueueAdapter([TranslationResult(text="Veuillez patienter", status="ok", attempts=1, error="")]),
            {"translate_agent_say_utterance": True},
            use_cache=True,
        )

    result = anyio.run(run)
    assert result.value == 'Agent: say(speaker="navigator", utterance="Veuillez patienter")'
    assert result.error == ""
    assert result.attempts == 1


def test_weblinx_split_records_groups_multiline_user_and_agent_blocks() -> None:
    query = (
        'User: to  Everyone:\n'
        '\tHi\n'
        'Agent: say(speaker="navigator", utterance="Please find below:\n'
        '\t-First item")\n'
        'User: Open the last option.\n'
        'Agent: click(x=1, y=2)'
    )

    assert _split_records(query, user_prefix="User: ", agent_prefix="Agent: ") == [
        'User: to  Everyone:\n\tHi',
        'Agent: say(speaker="navigator", utterance="Please find below:\n\t-First item")',
        'User: Open the last option.',
        'Agent: click(x=1, y=2)',
    ]


def test_weblinx_strategy_translates_full_multiline_user_block_and_preserves_agent_block() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(text="a Tous:\n\tSalut", status="ok", attempts=1, error=""),
            TranslationResult(text='Ouvre la derniere option "Can punishments be weakened?"', status="ok", attempts=1, error=""),
        ]
    )

    query = (
        'User: to  Everyone:\n'
        '\tHi\n'
        'Agent: say(speaker="navigator", utterance="Please find below:\n'
        '\t-First item")\n'
        'User: Open the last option "Can punishments be weakened?"\n'
        'Agent: hover(x=1, y=2)\n'
        'Agent: tabremove(target=3)'
    )

    async def run():
        return await translate_weblinx_query(query, adapter, {}, use_cache=True)

    result = anyio.run(run)
    assert result.value == (
        'User: a Tous:\n'
        '\tSalut\n'
        'Agent: say(speaker="navigator", utterance="Please find below:\n'
        '\t-First item")\n'
        'User: Ouvre la derniere option "Can punishments be weakened?"\n'
        'Agent: hover(x=1, y=2)\n'
        'Agent: tabremove(target=3)'
    )
    assert result.error == ""
    assert adapter.calls == [
        ("to  Everyone:\n\tHi", True),
        ('Open the last option "Can punishments be weakened?"', True),
    ]


def test_weblinx_strategy_translates_multiline_agent_utterance_and_preserves_action_shape() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(
                text="Veuillez trouver ci-dessous:\n\t-Premier element avec \\\"guillemets\\\"",
                status="ok",
                attempts=1,
                error="",
            )
        ]
    )
    query = (
        'Agent: say(speaker="navigator", utterance="Please find below:\n'
        '\t-First item with \\\"quotes\\\"")\n'
        "Agent: click(x=1, y=2)"
    )

    async def run():
        return await translate_weblinx_query(query, adapter, {"translate_agent_say_utterance": True}, use_cache=True)

    result = anyio.run(run)
    assert result.value == (
        'Agent: say(speaker="navigator", utterance="Veuillez trouver ci-dessous:\n'
        '\t-Premier element avec \\\"guillemets\\\"")\n'
        "Agent: click(x=1, y=2)"
    )
    assert result.error == ""
    assert adapter.calls == [('Please find below:\n\t-First item with \\\"quotes\\\"', True)]


def test_weblinx_strategy_preserves_blank_separator_lines_after_user_text() -> None:
    adapter = QueueAdapter([TranslationResult(text="Pouvez-vous ouvrir le calculateur ?", status="ok", attempts=1, error="")])
    query = (
        "User: Can you open the calculator?\n"
        "\n"
        "Agent: say(speaker=\"navigator\", utterance=\"Sure\")"
    )

    async def run():
        return await translate_weblinx_query(query, adapter, {}, use_cache=True)

    result = anyio.run(run)
    assert result.value == (
        "User: Pouvez-vous ouvrir le calculateur ?\n"
        "\n"
        "Agent: say(speaker=\"navigator\", utterance=\"Sure\")"
    )
    assert result.error == ""
    assert adapter.calls == [("Can you open the calculator?", True)]


def test_weblinx_strategy_skips_symbol_only_user_text() -> None:
    adapter = QueueAdapter([])

    async def run():
        return await translate_weblinx_query("User: \u20ac\u20ac.", adapter, {}, use_cache=True)

    result = anyio.run(run)
    assert result.value == "User: \u20ac\u20ac."
    assert result.error == ""
    assert adapter.calls == []


def test_weblinx_strategy_translates_double_quoted_agent_utterance() -> None:
    adapter = QueueAdapter(
        [
            TranslationResult(
                text='"Les procureurs fédéraux ont obtenu l’enregistrement."',
                status="ok",
                attempts=1,
                error="",
            )
        ]
    )
    query = (
        'Agent: say(speaker="navigator", utterance=""Federal prosecutors obtained the recording."")\n'
        'Agent: scroll(x=0, y=59)'
    )

    async def run():
        return await translate_weblinx_query(query, adapter, {"translate_agent_say_utterance": True}, use_cache=True)

    result = anyio.run(run)
    assert result.value == (
        'Agent: say(speaker="navigator", utterance=""Les procureurs fédéraux ont obtenu l’enregistrement."")\n'
        'Agent: scroll(x=0, y=59)'
    )
    assert result.error == ""
    assert adapter.calls == [('"Federal prosecutors obtained the recording."', True)]


def test_languages_and_renderers_helpers() -> None:
    assert language_label("fr") == "French"
    assert language_code("French") == "fr"
    assert language_names("en-fr") == ("English", "French")
    assert language_names("broken") == ("broken", "broken")
    assert extract_language_pair("zouharvi/wmt_en_ru") == "wmt-en-ru"
    assert numbered_list(["a", "b"]) == "1. a\n2. b"
    assert dialog_turns([{"role": "user", "content": "hello"}, "bye"]) == "user: hello\nbye"
    assert render_value(["a", "b"], "text_list") == "1. a\n2. b"
    assert action_sequence("say(x)\nclick(y)\nnoop") == ["say(", "click("]
    with pytest.raises(ValueError, match="unknown formatter"):
        render_value("x", "unknown")


def test_rule_options_and_merge_translation_errors() -> None:
    rule = TranslationRuleModel(source="query", strategy="weblinx_query", options={"user_prefix": "User: "})
    assert rule_options(rule) == {"user_prefix": "User: "}
    assert merge_translation_errors("", "bad", "", "worse") == "bad; worse"


def test_jsonl_helpers_and_translation_checkpoints(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    write_jsonl(path, [{"row_idx": 1, "text": "a"}])
    append_jsonl(path, [{"row_idx": 0, "text": "b"}])
    assert load_jsonl(path) == [{"row_idx": 1, "text": "a"}, {"row_idx": 0, "text": "b"}]
    assert load_jsonl_index(path, "row_idx")[1]["text"] == "a"

    checkpoint_dir = tmp_path / "checkpoint"
    write_jsonl(checkpoint_dir / "test.jsonl", [{"row_idx": 1, "field": "x"}, {"row_idx": 0, "field": "y"}])
    assert build_translate_records(checkpoint_dir, ["test"]) == [
        {"row_idx": 0, "field": "y", "split": "test"},
        {"row_idx": 1, "field": "x", "split": "test"},
    ]

    dataset = Dataset.from_dict({"source": ["a", "b", "c"]})
    state, done = restore_state_from_checkpoint(
        checkpoint_path=checkpoint_dir / "test.jsonl",
        limit=2,
        fields=["field"],
    )
    assert done[0]["field"] == "y"
    assert split_limit(dataset, 0) == 3
    assert split_limit(dataset, 2) == 2
    pending = pending_rows_for_range(
        dataset=dataset,
        state=init_state(3, ["field"]),
        fields=["field"],
        start_idx=0,
        end_idx=2,
    )
    assert pending == [(0, {"source": "a"}), (1, {"source": "b"})]
    assert pending_rows_for_range(
        dataset=dataset,
        state=state,
        fields=["field"],
        start_idx=0,
        end_idx=2,
    ) == []

    materialized = materialize_split(
        dataset,
        2,
        state,
        ["field"],
        [],
        chunk_size=1,
    )
    assert materialized["source"] == ["a", "b"]
    assert materialized["field"] == ["y", "x"]


def test_app_main_module_invokes_cli_main() -> None:
    with patch("data_translate.cli.main.main") as main_mock:
        runpy.run_module("data_translate.app", run_name="__main__")
    main_mock.assert_called_once()
