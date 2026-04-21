from pydantic import BaseModel, ConfigDict

from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_runtime import (
    ArtifactPathsModel,
    LLMRunPolicyModel,
    LLMSettingsModel,
    PromptSettingsModel,
    TranslationRunPolicyModel,
    WorkflowMetaModel,
)


class WorkflowConfigBaseModel(BaseModel):
    meta: WorkflowMetaModel
    artifacts: ArtifactPathsModel

    model_config = ConfigDict(extra="forbid")


class DatasetWorkflowConfigBaseModel(WorkflowConfigBaseModel):
    dataset: DatasetSpecModel


class TranslationWorkflowConfigBaseModel(DatasetWorkflowConfigBaseModel):
    runtime: TranslationRunPolicyModel


class JudgeWorkflowConfigBaseModel(WorkflowConfigBaseModel):
    runtime: LLMRunPolicyModel
    llm: LLMSettingsModel
    prompt: PromptSettingsModel


class DatasetJudgeWorkflowConfigBaseModel(JudgeWorkflowConfigBaseModel):
    dataset: DatasetSpecModel

class CandidateWorkflowConfigBaseModel(DatasetWorkflowConfigBaseModel):
    pass
