from data_translate.config.models_workflow_common import WorkflowConfigBaseModel
from data_translate.workflow_registry import get_workflow_definition


def run_workflow(config: WorkflowConfigBaseModel) -> None:
    get_workflow_definition(config.meta.workflow).runner(config)
