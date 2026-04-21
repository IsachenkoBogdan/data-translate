import anyio
import structlog

from data_translate.config.models_workflow import TranslateWorkflowConfigModel
from data_translate.services.translation import run_translate_workflow


logger = structlog.get_logger(__name__)

def run(config: TranslateWorkflowConfigModel) -> None:
    anyio.run(run_translate_workflow, config, logger)
