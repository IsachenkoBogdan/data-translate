import argparse

from data_translate.workflow_registry import workflow_definitions, workflow_names


def add_common_args(parser: argparse.ArgumentParser, *, dataset_optional: bool) -> None:
    parser.add_argument("--dataset", required=not dataset_optional, help="Dataset id from conf/datasets")
    parser.add_argument("--run", default="", help="Optional run preset from conf/runs/<workflow>")
    parser.add_argument("--config-root", default="conf", help="Hydra config root directory")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Hydra override, for example: --set runtime.concurrency=24",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-translate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for definition in workflow_definitions():
        workflow_parser = subparsers.add_parser(definition.name)
        add_common_args(workflow_parser, dataset_optional=definition.dataset_optional)

    check_parser = subparsers.add_parser("check-translation")
    check_parser.add_argument("--dataset", default="", help="Dataset id from conf/datasets")
    check_parser.add_argument("--quality", default="", help="Quality config id from conf/quality")
    check_parser.add_argument("--path", default="", help="Path to a load_from_disk translation artifact")
    check_parser.add_argument("--run", default="", help="Optional run preset from conf/runs/<workflow>")
    check_parser.add_argument("--config-root", default="conf", help="Hydra config root directory")
    check_parser.add_argument("--max-issues", type=int, default=50, help="Maximum issues to print; reports always keep all issues")
    check_parser.add_argument("--max-rows-per-split", type=int, default=0, help="Limit checked rows per split; 0 checks all rows")
    check_parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")
    check_parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Hydra override, for example: --set runtime.concurrency=24",
    )

    fix_parser = subparsers.add_parser("check-translation-fix")
    fix_parser.add_argument("--dataset", required=True, help="Dataset id from conf/datasets")
    fix_parser.add_argument("--run", default="", help="Optional run preset from conf/runs/evaluate")
    fix_parser.add_argument("--config-root", default="conf", help="Hydra config root directory")
    fix_parser.add_argument("--max-fixes", type=int, default=50, help="Maximum fix suggestions to request; -1 keeps all fixable issues")
    fix_parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")
    fix_parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Hydra override, for example: --set runtime.concurrency=4 llm.model=gpt-4o-mini",
    )

    upload_parser = subparsers.add_parser("upload-datasets")
    upload_parser.add_argument("--upload", dest="uploads", action="append", default=[], help="Upload id from conf/uploads")
    upload_parser.add_argument("--all", action="store_true", help="Export/upload all configs from conf/uploads")
    upload_parser.add_argument("--config-root", default="conf", help="Hydra config root directory")
    upload_parser.add_argument("--push", action="store_true", help="Create/update Hugging Face dataset repos and upload exports")
    upload_parser.add_argument("--yes", action="store_true", help="Required together with --push")

    config_parser = subparsers.add_parser("config-show")
    config_parser.add_argument("--workflow", choices=sorted(workflow_names()), required=True)
    add_common_args(config_parser, dataset_optional=True)
    return parser
