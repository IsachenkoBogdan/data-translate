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


def test_quality_checker_ignores_unchanged_technical_values() -> None:
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "query": [
                        "Capture.PNG (https://www.statcan.gc.ca/livechat/getfile.php?id=6661f0f16fbb99f81bea5cd5d2646a84)",
                        "https://www150.statcan.gc.ca/n1/en/subjects/labour/earnings_wages",
                        "@NesanMano https://unix.stackexchange.com/questions/84090/how-can-i-revert-a-chmod-on-the-etc-directory",
                        "`df -h` `sudo umount /dev/sda1`",
                        "8f5303e4b1afc818798425a700139133  /lib/firmware/ath10k/QCA6174/hw2.1/firmware-5.bin",
                        "Canon i-Sensys MF231",
                        "I need the report at https://www.statcan.gc.ca/example",
                        "I need 1 single room today",
                    ],
                    "query_fr": [
                        "Capture.PNG (https://www.statcan.gc.ca/livechat/getfile.php?id=6661f0f16fbb99f81bea5cd5d2646a84)",
                        "https://www150.statcan.gc.ca/n1/en/subjects/labour/earnings_wages",
                        "@NesanMano https://unix.stackexchange.com/questions/84090/how-can-i-revert-a-chmod-on-the-etc-directory",
                        "`df -h` `sudo umount /dev/sda1`",
                        "8f5303e4b1afc818798425a700139133  /lib/firmware/ath10k/QCA6174/hw2.1/firmware-5.bin",
                        "Canon i-Sensys MF231",
                        "I need the report at https://www.statcan.gc.ca/example",
                        "I need 1 single room today",
                    ],
                }
            )
        }
    )

    report = audit_translation_quality(source=None, translated=translated, rules=[])

    assert [(issue.code, issue.row_idx) for issue in report.issues] == [
        ("unchanged_translation", 6),
        ("unchanged_translation", 7),
    ]


def test_quality_checker_reports_nested_text_fields() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "turn": [
                        {
                            "question": "What did the user ask?",
                            "answers": [{"clr_ans": "Pest"}],
                        }
                    ]
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "turn": [
                        {
                            "question": "What did the user ask?",
                            "answers": [{"clr_ans": "Pest"}],
                        }
                    ],
                    "turn_fr": [
                        {
                            "question": "What did the user ask?",
                            "answers": [{"clr_ans": "Pest"}],
                        }
                    ],
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[
            QualityRule(
                source="turn",
                target="turn_fr",
                strategy="nested_text_fields",
                options={"paths": ["question", "answers[].clr_ans"]},
            )
        ],
    )

    assert [issue.code for issue in report.issues] == ["unchanged_translation"]


def test_quality_checker_reports_deep_map_text_fields() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "turn": [
                        {
                            "id": "do-not-check",
                            "question": "What did the user ask?",
                            "answers": [{"answer": "the west side of the river"}],
                        }
                    ]
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "turn": [
                        {
                            "id": "do-not-check",
                            "question": "What did the user ask?",
                            "answers": [{"answer": "the west side of the river"}],
                        }
                    ]
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[
            QualityRule(
                source="turn",
                target="turn",
                strategy="deep_map_texts",
                options={"exclude_keys": ["id"]},
            )
        ],
    )

    assert [issue.code for issue in report.issues] == ["unchanged_translation", "unchanged_translation"]
