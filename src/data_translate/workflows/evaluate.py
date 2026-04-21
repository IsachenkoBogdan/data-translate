import structlog

from data_translate.config.models_workflow import EvaluateWorkflowConfigModel
from data_translate.workflows.judge_entrypoint import run_judge_entrypoint
from data_translate.workflows.judge_specs import build_evaluate_judge_spec


logger = structlog.get_logger(__name__)


def run(config: EvaluateWorkflowConfigModel) -> None:
    run_judge_entrypoint(
        config=config,
        logger=logger,
        spec_factory=build_evaluate_judge_spec,
    )
