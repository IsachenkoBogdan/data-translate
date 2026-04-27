from datasets import Dataset, DatasetDict

from data_translate.domain.translation_quality import QualityRule, audit_translation_quality


def test_quality_checker_reports_missing_columns_and_row_counts() -> None:
    source = DatasetDict({"train": Dataset.from_dict({"text": ["hello", "bye"]})})
    translated = DatasetDict({"train": Dataset.from_dict({"text": ["bonjour"]})})

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )

    codes = [issue.code for issue in report.issues]
    assert "row_count_mismatch" in codes
    assert "schema_missing_field" in codes
    assert report.error_count == 2


def test_quality_checker_reports_list_length_and_unchanged_translation() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "dialog": [["May I try this on?", "Hello there"]],
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "dialog": [["May I try this on?"]],
                    "dialog_fr": [["May I try this on?"]],
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="dialog", target="dialog_fr", strategy="text_list")],
    )

    codes = [issue.code for issue in report.issues]
    assert "list_length_mismatch" in codes
    assert "unchanged_translation" in codes


def test_quality_checker_reports_weblinx_action_changes() -> None:
    source = DatasetDict(
        {
            "validation": Dataset.from_dict(
                {
                    "query": ['User: Open Gmail\nAgent: load(url="https://mail.google.com")'],
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "validation": Dataset.from_dict(
                {
                    "query": ['User: Open Gmail\nAgent: load(url="https://mail.google.com")'],
                    "query_fr": ["User: Ouvrir Gmail"],
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="query", target="query_fr", strategy="weblinx_query")],
    )

    assert [issue.code for issue in report.issues] == ["weblinx_action_changed"]


def test_quality_checker_infers_fr_pairs_without_source_dataset() -> None:
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "knowledge": ["I only need a single room."],
                    "knowledge_fr": ["I only need a single room."],
                }
            )
        }
    )

    report = audit_translation_quality(source=None, translated=translated, rules=[])

    assert [issue.code for issue in report.issues] == ["unchanged_translation"]
