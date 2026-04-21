from pathlib import Path

from datasets import DatasetDict

from data_translate.config.models_dataset_reformat import ReformatSpecModel
from data_translate.config.models_workflow import InspectSourceWorkflowConfigModel, ReformatWorkflowConfigModel
from data_translate.domain.reformat_conversion import reformat_candidate
from data_translate.domain.reformat_inspection import inspect_candidate
from data_translate.engine.candidate_run import CandidateProcessor
from data_translate.engine.manifests import build_manifest_payload, write_manifest


def build_reformat_processor(
    config: ReformatWorkflowConfigModel,
    source: DatasetDict,
    reformat: ReformatSpecModel,
) -> CandidateProcessor:
    output_root = Path(config.artifacts.materialized_output_path)
    output_root.mkdir(parents=True, exist_ok=True)

    def process_candidate(candidate_name: str, candidate_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
        converted, summary = reformat_candidate(
            candidate_name=candidate_name,
            candidate_path=candidate_path,
            rules=reformat.rules,
            source=source,
            missing_policy=reformat.missing_policy,
        )
        output = output_root / candidate_name
        output.mkdir(parents=True, exist_ok=True)
        converted.save_to_disk(str(output))
        manifest_path = write_manifest(
            output,
            build_manifest_payload(
                artifact_kind="reformatted_candidate",
                workflow=config.meta.workflow,
                dataset_id=config.meta.dataset_id or "",
                run_name=config.meta.run_name,
                output_path=str(output),
                target_lang=reformat.target_lang,
                extra={
                    "candidate_name": candidate_name,
                    "candidate_path": str(candidate_path),
                    "rules": reformat.rules.model_dump(mode="python"),
                    "splits": {split: len(converted[split]) for split in converted},
                },
            ),
        )
        summary["output"] = str(output)
        summary["manifest_path"] = str(manifest_path)
        records = [
            {
                "candidate": candidate_name,
                "split": split,
                "output": str(output),
                **dict(split_summary),
            }
            for split, split_summary in dict(summary["splits"]).items()
        ]
        return summary, records

    return process_candidate


def build_inspect_source_processor(
    config: InspectSourceWorkflowConfigModel,
    source: DatasetDict,
    reformat: ReformatSpecModel,
) -> CandidateProcessor:
    del config

    def process_candidate(candidate_name: str, candidate_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
        report = inspect_candidate(
            candidate_name=candidate_name,
            candidate_path=candidate_path,
            rules=reformat.rules,
            source=source,
        )
        return report, [report]

    return process_candidate
