from pydantic import model_validator

from data_translate.config.models_runtime import LLMRunPolicyModel, LLMSettingsModel, PromptSettingsModel
from data_translate.config.models_workflow_common import (
    CandidateWorkflowConfigBaseModel,
    DatasetJudgeWorkflowConfigBaseModel,
    TranslationWorkflowConfigBaseModel,
    WorkflowConfigBaseModel,
)
from data_translate.config.models_workflow_benchmark import BenchmarkSpecModel


class TranslateWorkflowConfigModel(TranslationWorkflowConfigBaseModel):
    @model_validator(mode="after")
    def validate_dataset(self) -> "TranslateWorkflowConfigModel":
        if self.dataset.translation is None:
            raise ValueError("translate workflow requires dataset.translation")
        return self


class EvaluateWorkflowConfigModel(DatasetJudgeWorkflowConfigBaseModel):
    @model_validator(mode="after")
    def validate_dataset(self) -> "EvaluateWorkflowConfigModel":
        if self.dataset.evaluation is None:
            raise ValueError("evaluate workflow requires dataset.evaluation")
        return self


class BenchmarkWorkflowConfigModel(WorkflowConfigBaseModel):
    runtime: LLMRunPolicyModel
    llm: LLMSettingsModel
    prompt: PromptSettingsModel
    benchmark: BenchmarkSpecModel


class ReformatWorkflowConfigModel(CandidateWorkflowConfigBaseModel):
    @model_validator(mode="after")
    def validate_dataset(self) -> "ReformatWorkflowConfigModel":
        if self.dataset.reformat is None:
            raise ValueError("reformat workflow requires dataset.reformat")
        return self


class InspectSourceWorkflowConfigModel(ReformatWorkflowConfigModel):
    pass
