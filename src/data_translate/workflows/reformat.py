import structlog

from data_translate.config.models_workflow import ReformatWorkflowConfigModel
from data_translate.workflows.candidate_entrypoint import run_candidate_entrypoint
from data_translate.workflows.candidate_processors import build_reformat_processor


logger = structlog.get_logger(__name__)


def run(config: ReformatWorkflowConfigModel) -> None:
    run_candidate_entrypoint(
        config=config,
        logger=logger,
        summary_key="profiles",
        processor_factory=build_reformat_processor,
    )
