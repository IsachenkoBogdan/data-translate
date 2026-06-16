import json
from unittest.mock import patch

from datasets import Dataset, DatasetDict

from data_translate.adapters.llm_response import success_response
from data_translate.config.loader import load_workflow_model
from data_translate.domain.translation_quality_reporting import build_quality_metrics, render_quality_html
from data_translate.domain.translation_quality import QualityRule, audit_translation_quality
from data_translate.engine.jsonl import load_jsonl
from data_translate.services.translation_quality import run_translation_quality_check
from data_translate.services.translation_quality_fix import run_translation_quality_fix


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
    assert report.suppressed_count == 6


def test_quality_checker_can_ignore_unchanged_title_like_values() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "topic": [
                        "Game of Thrones",
                        "Rio Grande do Sul",
                        "Abingdon-on-Thames",
                        "Do you think that it was effective?",
                    ],
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "topic_fr": [
                        "Game of Thrones",
                        "Rio Grande do Sul",
                        "Abingdon-on-Thames",
                        "Do you think that it was effective?",
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
                source="topic",
                target="topic_fr",
                strategy="text",
                options={"allow_unchanged_title_like": True},
            )
        ],
    )

    assert [(issue.code, issue.row_idx) for issue in report.issues] == [("unchanged_translation", 3)]


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


def test_quality_checker_reports_diagnostics_and_heuristic_warnings() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": [
                        "This source sentence contains enough alphabetic characters to compare length.",
                        "This source sentence is concise but still long enough for the ratio check.",
                        "Please book the hotel for tonight and tell me where it is.",
                        "I need 2 rooms for 3 nights.",
                        "It's mysterious.",
                        "Use [hotel-bookpeople 2] today.",
                    ]
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": source["train"]["text"],
                    "text_fr": [
                        "Bref.",
                        "Très " * 80,
                        "Veuillez keep what you need where it is.",
                        "J'ai besoin de 2 chambres pour 4 nuits.",
                        "C&apos;est mystérieux.",
                        "Utilisez [hotel-bookpeople 3] aujourd'hui.",
                    ],
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )

    codes = [issue.code for issue in report.issues]
    assert "length_ratio_low" in codes
    assert "length_ratio_high" in codes
    assert "english_residue" in codes
    assert "digit_sequence_changed" in codes
    assert "html_entity_leak" in codes
    assert "placeholder_or_marker_changed" in codes
    assert report.checked_pairs == 6
    assert report.checked_pairs_by_field == {"text_fr": 6}
    assert all("source_len" in issue.diagnostics for issue in report.issues)


def test_quality_checker_keeps_common_numeric_rewrites_quiet() -> None:
    source_texts = [
        "The band sold over 50 million albums in the early 2000s.",
        "This made them the 41st best selling artists of all time.",
        "The first match was played november6 1869.",
        "The date was August 16th, 1977.",
        "The range is 50yards and up to 35 yards.",
        "Around 80k people joined.",
        "The market size was about $76.3 trillion dollars.",
        "They sold over 100million albums total.",
        "In 2011, its population was 1,810,863.",
        "A few... 8,537,673 to be exact.",
        "The area has 360,000 residents.",
        "Most mopeds I have seen will travel 55-65mph.  Mopeds are very convenient for large cities, but I would be scared to ride one so slow in rural areas where the speed limit is over 65mph.",
        "There is evidence of Hippocrates and Aristotle trying to figure out ways to make braces around 400-300BCE",
        "I do, I liked her Superbowl halftime show, on 2/1/15.",
        "In 2016 the population of Paris was around 12,142,802, which accounted for approximately 18 percent of the population of France",
        "My best 5k run time is so embarassing I'd rather not say. I curse the gods for the whole 3.1 miles.",
        "It stems more from the 1940s and 50's. It came mostly from blues and country.",
        "that is just the population of the people within the city limits.  The population of the metropolitan area is 2,353,045.",
        "The weather is pretty fair in Dublin, Our city has a  population of nearly 1,347,359 people. Its pretty cramped here",
        "Yes it has a population of 10 million with over 2million of them of foreign origin.",
        "I was OK because I had my seat belt on and it was only about 15 mph.",
        "I grew up camping and recently made it my goal to hike at least 5 miles a day",
        "Yes, there is a Walmart less than 1/2 miles from my home.",
        "Wedding cakes are cool. I saw one that was once 5 feet tall!",
        "Anything else important I should know before I go drop 50 grand?",
        "The show first aired as a three hour miniseries in December of 03'.",
        "I love soccer and remember way back in '70.",
        "Not that late. I'm usually home by 8 pm.",
        "The first store in the United States was opened in1998.",
        "Walmart has 11,703 stores and clubs in 28countries",
        "It has an option 2.3L EcoBoost turbocharged and direct injected 4 cylinder engine.",
        "It was NOT under warranty. The a/c cost $1300.00 and the transmission was $2400.",
        "Maybe $180,000.00. I like the Bentley Turbo R.",
        "She has to keep them on for 1.5 years to straighten and align her teeth",
        "The first generation was released 6/29/2007.",
        "In the 02-03 year rowers were only 2% of all college athletes.",
        "This includes the top fifteen schools in the 2017 rankings.",
        "Hi, I like Sixties rock like the Rolling Stones. They formed in 1962.",
        "The metro area has a pop. of 2,353,045.",
        "South Park has been out since 1997 and is more than 2 decades old.",
        "In 2016, the city had 8,537, 673 people",
        "Still on history, in1516, Habsburg Spain unified kingdoms; the constitution dates to 1978.",
        "I tried to ride all 16 roller coasters, but only could get on like8 before the day was over.",
        "It's hard to believe there have been eleven generations. I still have a 6s and heard good things about the 8.",
        "When I started it was $8 an hour. Now it's probably $11. They get around the clock care.",
        "Red hair is only common to 1 to 2f percent of the population.",
        "Mauna Loa has been erupting for at least 700,00 years.",
        "Don't you think there may be chanced that out of 10 ,1 could last?",
        "Hamburgers were later added for .10 a piece.",
        "I am fairly certain it was worth about $.50.",
        "There were almost 900,ooo americans who relied on internet.",
        "A mile run is exactly 1,609.344 metres.",
        "It was published on 17 August 1945 four years before Nineteen Eighty-Four.",
        "The body has a density of 0.98 which allows it to float.",
        "5,6,7,8 What makes it so special.",
    ]
    translated_texts = [
        "Le groupe a vendu plus de 50 millions d'albums au début des années 2000.",
        "Cela en fait le 41e artiste le plus vendu de tous les temps.",
        "Le premier match a été joué le 6 novembre 1869.",
        "La date était le 16 août 1977.",
        "La portée est de 50 mètres et jusqu'à 35 mètres.",
        "Environ 80 000 personnes ont rejoint.",
        "La taille du marché était d'environ 76 300 milliards de dollars.",
        "Ils ont vendu plus de 100 millions d'albums au total.",
        "En 2011, sa population était de 1 810 863.",
        "Quelques... 8 537 673 pour être exact.",
        "La zone compte 360 000 habitants.",
        "La plupart des cyclomoteurs que j'ai vus parcourent entre 55 et 65 mph. Les cyclomoteurs sont très pratiques pour les grandes villes, mais j'aurais peur d'en conduire un aussi lentement dans les zones rurales où la limite de vitesse est supérieure à 65 mph.",
        "Il existe des preuves selon lesquelles Hippocrate et Aristote essayaient de trouver des moyens de fabriquer des appareils orthodontiques vers 400-300 avant notre ère.",
        "Oui, j'ai aimé son spectacle à la mi-temps du Superbowl, le 01/02/15.",
        "En 2016, la population de Paris était d'environ 12 142 802 habitants, ce qui représentait environ 18 % de la population française.",
        "Mon meilleur temps de course sur 5 km est tellement embarrassant que je préfère ne pas le dire. Je maudis les dieux pendant les 3,1 milles.",
        "Cela vient plutôt des années 40 et 50. Cela venait principalement du blues et de la country.",
        "c'est juste la population des habitants dans les limites de la ville. La population de la zone métropolitaine est de 2 353 045 habitants.",
        "Le temps est plutôt clément à Dublin. Notre ville compte près de 1 347 359 habitants. C'est assez exigu ici",
        "Oui, le pays compte 10 millions d'habitants, dont plus de 2 millions d'origine étrangère.",
        "J'allais bien parce que j'avais ma ceinture de sécurité et la vitesse n'était qu'à environ 24 km/h.",
        "J'ai grandi en camping et je me suis récemment fixé pour objectif de faire au moins 8 km par jour.",
        "Oui, il y a un Walmart à moins de 800 mètres de chez moi.",
        "Les gâteaux de mariage sont cool. J'en ai vu un qui mesurait autrefois 1,50 mètre !",
        "Y a-t-il autre chose d'important que je devrais savoir avant de déposer 50 000 $ ?",
        "La série a été diffusée pour la première fois sous forme de mini-série de trois heures en décembre 2003.",
        "J'adore le football et je me souviens en 1970.",
        "Pas si tard. Je suis généralement à la maison vers 20 heures.",
        "Le premier magasin aux États-Unis a ouvert ses portes en 1998.",
        "Walmart compte 11 703 magasins et clubs dans 28 pays",
        "Il dispose d'un moteur 4 cylindres EcoBoost de 2,3 L turbocompressé et à injection directe.",
        "Il n'était PAS sous garantie. La climatisation coûtait 1 300,00 $ et la transmission était de 2 400 $.",
        "Peut-être 180 000,00 $. J'aime la Bentley Turbo R.",
        "Elle doit les garder pendant 1 an et demi pour redresser et aligner ses dents",
        "La première génération est sortie le 29/06/2007.",
        "Au cours des années 2002-2003, les rameurs ne représentaient que 2 % des athlètes.",
        "Cela inclut les 15 meilleures écoles du classement 2017.",
        "Salut, j'aime le rock des années 60 comme les Rolling Stones. Ils se sont formés en 1962.",
        "La zone métropolitaine a du pop. de 2.353.045.",
        "South Park est sorti depuis 1997 et il a plus de 20 ans.",
        "En 2016, la ville comptait 8 537 673 habitants",
        "Toujours sur l'histoire, en 1516, l'Espagne des Habsbourg a unifié des royaumes ; la constitution date de 1978.",
        "J'ai essayé de monter les 16 montagnes russes, mais je n'ai pu monter que comme 8 avant la fin de la journée.",
        "Il est difficile de croire qu'il existe onze générations. J'ai toujours un 6s et entendu de bonnes choses sur les 8.",
        "Quand j'ai commencé, c'était 8 $ de l'heure. Maintenant, c'est probablement 11 $. Ils reçoivent des soins 24 heures sur 24.",
        "Les cheveux roux ne concernent que 1 à 2% de la population.",
        "Le Mauna Loa est en éruption depuis au moins 700 00 ans.",
        "Ne pensez-vous pas qu'il y a une chance que sur 10,1 puisse durer ?",
        "Des hamburgers ont ensuite été ajoutés pour 0,10 pièce.",
        "Je suis presque certain qu'elle valait environ 0,50 $.",
        "Près de 900 000 Américains dépendaient fortement d'Internet.",
        "Un mile run fait exactement 1 609,344 mètres.",
        "Il a été publié le 17 août 1945, quatre ans avant 1984.",
        "Le corps a une densité de 0,98 ce qui lui permet de flotter.",
        "5,6,7,8 Ce qui le rend si spécial.",
    ]
    source = DatasetDict({"train": Dataset.from_dict({"text": source_texts})})
    translated = DatasetDict({"train": Dataset.from_dict({"text": source_texts, "text_fr": translated_texts})})

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )

    assert [issue.code for issue in report.issues] == []


def test_quality_checker_keeps_suspicious_numeric_rewrites() -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": [
                        "I usually stay up until 1 but never until dawn.",
                        "My parents are both 5'4\" but my siblings are all taller than them.",
                    ]
                }
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": source["train"]["text"],
                    "text_fr": [
                        "Je reste généralement debout jusqu'à 13 heures, mais jamais jusqu'à l'aube.",
                        "Mes parents mesurent tous les deux 1,70 m, mais mes frères et sœurs sont tous plus grands qu'eux.",
                    ],
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )

    assert [issue.code for issue in report.issues] == ["digit_sequence_changed", "digit_sequence_changed"]


def test_quality_checker_reports_repeated_translation_groups() -> None:
    source_texts = [f"This is a distinct source sentence number {idx} with enough text." for idx in range(5)]
    source = DatasetDict({"train": Dataset.from_dict({"text": source_texts})})
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": source_texts,
                    "text_fr": ["La même traduction française assez longue."] * 5,
                }
            )
        }
    )

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )

    repeated = [issue for issue in report.issues if issue.code == "repeated_translation"]
    assert len(repeated) == 1
    assert repeated[0].diagnostics["distinct_source_count"] == 5
    assert repeated[0].diagnostics["occurrence_count"] == 5

    payload = {
        "dataset_id": "demo",
        "workflow": "check-translation",
        "splits": {"train": 5},
        **report.to_dict(),
    }
    metrics = build_quality_metrics(payload)
    html = render_quality_html(payload, metrics)

    assert "Source examples" in html
    assert "This is a distinct source sentence number 0" in html
    assert '"occurrence_count": 5' in html


def test_quality_metrics_and_html_rendering_escape_examples() -> None:
    source = DatasetDict({"train": Dataset.from_dict({"text": ["Do you need <b>help</b> today?"]})})
    translated = DatasetDict({"train": Dataset.from_dict({"text": ["Do you need <b>help</b> today?"], "text_fr": [""]})})
    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=[QualityRule(source="text", target="text_fr", strategy="text")],
    )
    payload = {
        "dataset_id": "demo",
        "workflow": "check-translation",
        "splits": {"train": 1},
        **report.to_dict(),
    }

    metrics = build_quality_metrics(payload)
    html = render_quality_html(payload, metrics)

    assert metrics["verdict"] == "fail"
    assert metrics["fields"][0]["checked_pairs"] == 1
    assert "const issueData =" in html
    assert "function escapeHtml" in html
    assert "Showing 50 cases per page" in html
    assert "Triggered Rules" in html
    assert "Coverage by field and split" in html
    assert "Field Coverage" in html
    assert "Empty field" in html
    assert "Suppressed" not in html
    assert "Ignored false positives" not in html
    assert "suppressed_count" not in html
    assert "Reason</th>" not in html


def test_split_metrics_hide_unchecked_passthrough_splits() -> None:
    payload = {
        "dataset_id": "demo",
        "workflow": "check-translation",
        "checked_rows": 1,
        "checked_pairs": 1,
        "error_count": 0,
        "warning_count": 1,
        "suppressed_count": 0,
        "splits": {"train": 1, "corpus_train": 10, "qrels_train": 20, "extra": 3},
        "checked_rows_by_split": {"train": 1},
        "checked_pairs_by_split": {"train": 1},
        "checked_pairs_by_field": {"text_fr": 1},
        "issues": [
            {
                "severity": "warning",
                "code": "split_extra",
                "split": "extra",
                "row_idx": None,
                "field": "",
                "message": "Translated dataset has an extra split.",
            }
        ],
        "suppressed": [],
    }

    metrics = build_quality_metrics(payload)
    split_names = [row["split"] for row in metrics["splits"]]

    assert "train" in split_names
    assert "extra" in split_names
    assert "corpus_train" not in split_names
    assert "qrels_train" not in split_names


def test_field_metrics_group_indexed_dialog_turns() -> None:
    payload = {
        "dataset_id": "demo",
        "workflow": "check-translation",
        "checked_rows": 10,
        "checked_pairs": 20,
        "error_count": 0,
        "warning_count": 2,
        "suppressed_count": 0,
        "splits": {"train": 10},
        "checked_rows_by_split": {"train": 10},
        "checked_pairs_by_split": {"train": 20},
        "checked_pairs_by_field": {"text_fr[0].content": 10, "text_fr[1].content": 10},
        "issues": [
            {
                "severity": "warning",
                "code": "digit_sequence_changed",
                "split": "train",
                "row_idx": 3,
                "field": "text_fr[0].content",
                "message": "digit sequences changed between source and translation",
                "sample": {"source": "I need 2 rooms.", "translation": "J'ai besoin de 3 chambres."},
                "diagnostics": {},
            },
            {
                "severity": "warning",
                "code": "english_residue",
                "split": "train",
                "row_idx": 4,
                "field": "text_fr[1].content",
                "message": "translation still contains several English signal words",
                "sample": {"source": "Where are you?", "translation": "Where êtes-vous ?"},
                "diagnostics": {},
            },
        ],
        "suppressed": [],
    }

    metrics = build_quality_metrics(payload)
    html = render_quality_html(payload, metrics)

    assert metrics["fields"] == [
        {
            "field": "text_fr[].content",
            "root_field": "text_fr",
            "exact_field_count": 2,
            "position_summary": "turns 1-2",
            "checked_pairs": 20,
            "errors": 0,
            "warnings": 2,
            "issue_rate": 0.1,
            "warning_rate": 0.1,
            "error_rate": 0.0,
            "top_codes": {"digit_sequence_changed": 1, "english_residue": 1},
        }
    ]
    assert "text_fr[].content" in html
    assert "turns 1-2" in html
    assert "turn 2" in html
    assert '"field": "text_fr[].content"' in html
    assert "First</button>" in html
    assert "Next</button>" in html


def test_html_report_groups_duplicate_issue_cases() -> None:
    payload = {
        "dataset_id": "demo",
        "workflow": "check-translation",
        "checked_rows": 2,
        "checked_pairs": 2,
        "error_count": 0,
        "warning_count": 2,
        "suppressed_count": 0,
        "splits": {"train": 2},
        "checked_rows_by_split": {"train": 2},
        "checked_pairs_by_split": {"train": 2},
        "checked_pairs_by_field": {"topic_fr": 2},
        "issues": [
            {
                "severity": "warning",
                "code": "unchanged_translation",
                "split": "train",
                "row_idx": 0,
                "field": "topic_fr",
                "message": "meaningful English-looking source remained unchanged",
                "sample": {"source": "Guns N' Roses", "translation": "Guns N' Roses"},
                "diagnostics": {},
            },
            {
                "severity": "warning",
                "code": "unchanged_translation",
                "split": "train",
                "row_idx": 1,
                "field": "topic_fr",
                "message": "meaningful English-looking source remained unchanged",
                "sample": {"source": "Guns N' Roses", "translation": "Guns N' Roses"},
                "diagnostics": {},
            },
        ],
        "suppressed": [],
    }

    metrics = build_quality_metrics(payload)
    html = render_quality_html(payload, metrics)

    assert '"occurrence_count": 2' in html
    assert '"row_idx": "0"' in html
    assert '"row_idx": "1"' in html
    assert "Showing 50 cases per page" in html


def test_translation_quality_service_writes_full_artifacts(tmp_path, monkeypatch) -> None:
    source = DatasetDict(
        {
            "train": Dataset.from_dict(
                {"text": ["May I try this on today please?", "Where will you go with this tomorrow?"]}
            )
        }
    )
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": source["train"]["text"],
                    "text_fr": source["train"]["text"],
                }
            )
        }
    )
    summary_path = tmp_path / "results" / "summary.json"

    monkeypatch.setattr(
        "data_translate.services.translation_quality._dataset_quality_inputs",
        lambda **_kwargs: (
            source,
            translated,
            [QualityRule(source="text", target="text_fr", strategy="text")],
            summary_path,
            {"mode": "dataset", "workflow": "translate", "dataset_id": "demo", "run_name": "", "translated_path": "x"},
            [],
        ),
    )

    payload = run_translation_quality_check(dataset_id="demo", max_issues=1)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert len(summary["issues"]) == 2
    assert len(payload["display_issues"]) == 1
    assert payload["issue_count_truncated"] is True
    assert load_jsonl(tmp_path / "results" / "issues.jsonl")
    assert (tmp_path / "results" / "metrics.json").exists()
    assert "check-translation" in (tmp_path / "results" / "report.html").read_text(encoding="utf-8")


def test_translation_quality_service_writes_sample_artifacts_separately(tmp_path, monkeypatch) -> None:
    source = DatasetDict({"train": Dataset.from_dict({"text": ["May I try this on today please?", "Where will you go?"]})})
    translated = DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "text": source["train"]["text"],
                    "text_fr": source["train"]["text"],
                }
            )
        }
    )
    summary_path = tmp_path / "results" / "demo" / "check-translation" / "default" / "summary.json"

    monkeypatch.setattr(
        "data_translate.services.translation_quality._dataset_quality_inputs",
        lambda **_kwargs: (
            source,
            translated,
            [QualityRule(source="text", target="text_fr", strategy="text")],
            summary_path,
            {"mode": "dataset", "workflow": "translate", "dataset_id": "demo", "run_name": "", "translated_path": "x"},
            [],
        ),
    )

    payload = run_translation_quality_check(dataset_id="demo", max_rows_per_split=1)

    assert payload["summary_path"].endswith("/default-sample-1/summary.json")
    assert not summary_path.exists()
    assert (summary_path.parent.parent / "default-sample-1" / "report.html").exists()


class FakeFixAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, **_kwargs):
        self.calls += 1
        return success_response(
            content='{"suggested_translation":"Bonjour","confidence":0.91,"rationale":"Corrects the unchanged text."}',
            attempts=1,
            usage={"total_tokens": 12},
            cost=0.001,
            finish_reason="stop",
            rate_limit_waits=0,
            rate_limit_wait_seconds=0,
        )

    async def close(self) -> None:
        return None


def test_translation_quality_fix_writes_suggestions_without_mutating_artifacts(tmp_path) -> None:
    quality_payload = {
        "summary_path": str(tmp_path / "summary.json"),
        "issues": [
            {
                "severity": "warning",
                "code": "unchanged_translation",
                "split": "train",
                "row_idx": 0,
                "field": "text_fr",
                "message": "meaningful English-looking source remained unchanged",
                "sample": {"source": "Hello", "translation": "Hello"},
                "diagnostics": {},
            },
            {
                "severity": "error",
                "code": "row_count_mismatch",
                "split": "train",
                "row_idx": None,
                "field": "",
                "message": "row count mismatch",
                "sample": {},
                "diagnostics": {},
            },
        ],
    }
    config = load_workflow_model("evaluate", dataset_id="faithdial")

    with patch("data_translate.services.translation_quality_fix.run_translation_quality_check", return_value=quality_payload), patch(
        "data_translate.services.translation_quality_fix.load_workflow_model", return_value=config
    ), patch("data_translate.services.translation_quality_fix.build_llm_adapter", return_value=FakeFixAdapter()):
        payload = run_translation_quality_fix(dataset_id="demo", max_fixes=10)

    assert payload["selected_issue_count"] == 1
    assert payload["selected_case_count"] == 1
    assert payload["suggestion_count"] == 1
    assert load_jsonl(tmp_path / "fix_suggestions.jsonl")[0]["suggested_translation"] == "Bonjour"
    assert (tmp_path / "fix_suggestions.html").exists()


def test_translation_quality_fix_groups_duplicate_cases_before_llm(tmp_path) -> None:
    quality_payload = {
        "summary_path": str(tmp_path / "summary.json"),
        "issues": [
            {
                "severity": "warning",
                "code": "unchanged_translation",
                "split": "train",
                "row_idx": 0,
                "field": "topic_fr",
                "message": "meaningful English-looking source remained unchanged",
                "sample": {"source": "Guns N' Roses", "translation": "Guns N' Roses"},
                "diagnostics": {},
            },
            {
                "severity": "warning",
                "code": "unchanged_translation",
                "split": "train",
                "row_idx": 1,
                "field": "topic_fr",
                "message": "meaningful English-looking source remained unchanged",
                "sample": {"source": "Guns N' Roses", "translation": "Guns N' Roses"},
                "diagnostics": {},
            },
        ],
    }
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    adapter = FakeFixAdapter()

    with patch("data_translate.services.translation_quality_fix.run_translation_quality_check", return_value=quality_payload), patch(
        "data_translate.services.translation_quality_fix.load_workflow_model", return_value=config
    ), patch("data_translate.services.translation_quality_fix.build_llm_adapter", return_value=adapter):
        payload = run_translation_quality_fix(dataset_id="demo", max_fixes=10)

    suggestions = load_jsonl(tmp_path / "fix_suggestions.jsonl")
    html = (tmp_path / "fix_suggestions.html").read_text(encoding="utf-8")

    assert adapter.calls == 1
    assert payload["selected_issue_count"] == 2
    assert payload["selected_case_count"] == 1
    assert payload["deduplicated_issue_count"] == 1
    assert payload["suggestion_count"] == 1
    assert suggestions[0]["issue"]["occurrence_count"] == 2
    assert len(suggestions[0]["issue"]["locations"]) == 2
    assert "2 occurrences" in html


def test_translation_quality_fix_skips_llm_when_no_fixable_issues(tmp_path) -> None:
    quality_payload = {
        "summary_path": str(tmp_path / "summary.json"),
        "issues": [
            {
                "severity": "error",
                "code": "row_count_mismatch",
                "split": "train",
                "row_idx": None,
                "field": "",
                "message": "row count mismatch",
                "sample": {},
                "diagnostics": {},
            }
        ],
    }
    config = load_workflow_model("evaluate", dataset_id="faithdial")

    with patch("data_translate.services.translation_quality_fix.run_translation_quality_check", return_value=quality_payload), patch(
        "data_translate.services.translation_quality_fix.load_workflow_model", return_value=config
    ), patch("data_translate.services.translation_quality_fix.build_llm_adapter") as build_adapter:
        payload = run_translation_quality_fix(dataset_id="demo", max_fixes=10)

    build_adapter.assert_not_called()
    assert payload["selected_issue_count"] == 0
    assert payload["selected_case_count"] == 0
    assert payload["suggestion_count"] == 0
    assert load_jsonl(tmp_path / "fix_suggestions.jsonl") == []
    assert (tmp_path / "fix_suggestions.html").exists()
