import json
import sys

import structlog

from data_translate.cli.parser import build_parser
from data_translate.cli.registry import run_workflow
from data_translate.config.loader import load_workflow_model
from data_translate.services.translation_quality import format_quality_summary, run_translation_quality_check
from data_translate.services.upload_datasets import format_upload_summary, run_upload_datasets


def configure_logging() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    if args.command == "config-show":
        config = load_workflow_model(
            args.workflow,
            config_root=args.config_root,
            dataset_id=args.dataset or None,
            run_name=args.run or None,
            overrides=args.overrides,
        )
        payload = config.model_dump(mode="python")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "check-translation":
        payload = run_translation_quality_check(
            dataset_id=args.dataset or "",
            quality_id=args.quality or "",
            path=args.path or "",
            run_name=args.run or "",
            config_root=args.config_root,
            overrides=args.overrides,
            max_issues=args.max_issues,
            max_rows_per_split=args.max_rows_per_split,
            show_progress=not args.no_progress,
        )
        print(format_quality_summary(payload))
        if int(payload["error_count"]) > 0:
            sys.exit(1)
        return
    if args.command == "check-translation-fix":
        from data_translate.services.translation_quality_fix import format_fix_summary, run_translation_quality_fix

        payload = run_translation_quality_fix(
            dataset_id=args.dataset,
            run_name=args.run or "",
            config_root=args.config_root,
            overrides=args.overrides,
            max_fixes=args.max_fixes,
            show_progress=not args.no_progress,
        )
        print(format_fix_summary(payload))
        return
    if args.command == "upload-datasets":
        payload = run_upload_datasets(
            config_root=args.config_root,
            upload_ids=args.uploads,
            all_uploads=args.all,
            push=args.push,
            yes=args.yes,
        )
        print(format_upload_summary(payload))
        return
    config = load_workflow_model(
        args.command,
        config_root=args.config_root,
        dataset_id=args.dataset or None,
        run_name=args.run or None,
        overrides=args.overrides,
    )
    run_workflow(config)


if __name__ == "__main__":
    main()
