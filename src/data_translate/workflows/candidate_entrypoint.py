from collections.abc import Callable
from pathlib import Path

from datasets import DatasetDict
import structlog

from data_translate.config.models_dataset_reformat import ReformatSpecModel
from data_translate.config.models_workflow import InspectSourceWorkflowConfigModel, ReformatWorkflowConfigModel
from data_translate.domain.preflight import validate_reformat_inputs
from data_translate.engine.candidate_run import CandidateProcessor, run_candidate_workflow
from data_translate.services.datasets import load_source_dataset


CandidateWorkflowConfig = ReformatWorkflowConfigModel | InspectSourceWorkflowConfigModel
CandidateProcessorFactory = Callable[[CandidateWorkflowConfig, DatasetDict, ReformatSpecModel], CandidateProcessor]


def run_candidate_entrypoint(
    *,
    config: CandidateWorkflowConfig,
    logger: structlog.stdlib.BoundLogger,
    summary_key: str,
    processor_factory: CandidateProcessorFactory,
) -> None:
    reformat = config.dataset.reformat
    if reformat is None:
        raise ValueError(f"{config.meta.workflow} workflow requires dataset.reformat")

    source = load_source_dataset(config.dataset.source)
    validate_reformat_inputs(config, source, reformat)
    process_candidate = processor_factory(config, source, reformat)
    candidates = list(reformat.candidates)

    logger.info(
        f"{config.meta.workflow}.start",
        dataset_id=config.meta.dataset_id,
        candidates=candidates,
    )
    run_candidate_workflow(
        workflow=config.meta.workflow,
        dataset_id=config.meta.dataset_id or "",
        run_name=config.meta.run_name,
        records_path=Path(config.artifacts.records_path),
        summary_path=Path(config.artifacts.summary_path),
        artifacts=config.artifacts.model_dump(mode="python"),
        external_root=Path(config.dataset.artifacts.external_root),
        selected_candidates=candidates,
        candidate_paths=reformat.candidates,
        summary_key=summary_key,
        process_candidate=process_candidate,
    )
    logger.info(
        f"{config.meta.workflow}.done",
        dataset_id=config.meta.dataset_id,
        candidates=candidates,
    )
