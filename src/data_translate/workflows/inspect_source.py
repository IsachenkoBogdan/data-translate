import structlog

from data_translate.config.models_workflow import InspectSourceWorkflowConfigModel
from data_translate.workflows.candidate_entrypoint import run_candidate_entrypoint
from data_translate.workflows.candidate_processors import build_inspect_source_processor


logger = structlog.get_logger(__name__)


def run(config: InspectSourceWorkflowConfigModel) -> None:
    run_candidate_entrypoint(
        config=config,
        logger=logger,
        summary_key="candidates",
        processor_factory=build_inspect_source_processor,
    )
