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

    config_parser = subparsers.add_parser("config-show")
    config_parser.add_argument("--workflow", choices=sorted(workflow_names()), required=True)
    add_common_args(config_parser, dataset_optional=True)
    return parser
