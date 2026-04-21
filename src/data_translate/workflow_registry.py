from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from data_translate.config.builder_common import WorkflowBuilder
from data_translate.config.models_workflow_common import WorkflowConfigBaseModel


WorkflowRunner = Callable[[Any], None]


def _load_object(path: str) -> Any:
    module_path, attr_name = path.rsplit(".", maxsplit=1)
    module = import_module(module_path)
    return getattr(module, attr_name)


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    dataset_optional: bool
    config_model_path: str
    builder_path: str
    runner_path: str

    @property
    def config_model(self) -> type[WorkflowConfigBaseModel]:
        return _load_object(self.config_model_path)

    @property
    def builder(self) -> WorkflowBuilder:
        return _load_object(self.builder_path)

    @property
    def runner(self) -> WorkflowRunner:
        return _load_object(self.runner_path)


WORKFLOW_REGISTRY: dict[str, WorkflowDefinition] = {
    "translate": WorkflowDefinition(
        name="translate",
        dataset_optional=False,
        config_model_path="data_translate.config.models_workflow.TranslateWorkflowConfigModel",
        builder_path="data_translate.config.builders_translate.build_translate_config",
        runner_path="data_translate.workflows.translate.run",
    ),
    "evaluate": WorkflowDefinition(
        name="evaluate",
        dataset_optional=False,
        config_model_path="data_translate.config.models_workflow.EvaluateWorkflowConfigModel",
        builder_path="data_translate.config.builders_llm.build_evaluate_config",
        runner_path="data_translate.workflows.evaluate.run",
    ),
    "benchmark-judge": WorkflowDefinition(
        name="benchmark-judge",
        dataset_optional=True,
        config_model_path="data_translate.config.models_workflow.BenchmarkWorkflowConfigModel",
        builder_path="data_translate.config.builders_llm.build_benchmark_config",
        runner_path="data_translate.workflows.benchmark_judge.run",
    ),
    "reformat": WorkflowDefinition(
        name="reformat",
        dataset_optional=False,
        config_model_path="data_translate.config.models_workflow.ReformatWorkflowConfigModel",
        builder_path="data_translate.config.builders_reformat.build_reformat_config",
        runner_path="data_translate.workflows.reformat.run",
    ),
    "inspect-source": WorkflowDefinition(
        name="inspect-source",
        dataset_optional=False,
        config_model_path="data_translate.config.models_workflow.InspectSourceWorkflowConfigModel",
        builder_path="data_translate.config.builders_reformat.build_inspect_source_config",
        runner_path="data_translate.workflows.inspect_source.run",
    ),
}


def get_workflow_definition(workflow: str) -> WorkflowDefinition:
    try:
        return WORKFLOW_REGISTRY[workflow]
    except KeyError as exc:
        raise ValueError(f"unknown workflow: {workflow}") from exc


def workflow_names() -> tuple[str, ...]:
    return tuple(WORKFLOW_REGISTRY)


def workflow_definitions() -> tuple[WorkflowDefinition, ...]:
    return tuple(WORKFLOW_REGISTRY.values())
