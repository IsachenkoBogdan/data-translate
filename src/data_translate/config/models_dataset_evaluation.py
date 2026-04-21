from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_translate.config.models_runtime import (
    InputDatasetModel,
    LLMSettingsOverrideModel,
    PromptSettingsOverrideModel,
    RunPolicyOverrideModel,
)


class FieldPairModel(BaseModel):
    name: str | None = None
    source_dataset: str = "translation"
    source_field: str = Field(min_length=1)
    source_format: str = "text"
    translation_dataset: str = "translation"
    translation_field: str = Field(min_length=1)
    translation_format: str = "text"

    model_config = ConfigDict(extra="forbid")


class PerSplitRandomSamplingModel(BaseModel):
    strategy: Literal["per_split_random"]
    dataset: str = "translation"
    samples_per_split: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class StratifiedByFieldSamplingModel(BaseModel):
    strategy: Literal["stratified_by_field"]
    dataset: str = "translation"
    field: str = Field(min_length=1)
    samples_per_value: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


SamplingModel = Annotated[
    PerSplitRandomSamplingModel | StratifiedByFieldSamplingModel,
    Field(discriminator="strategy"),
]


class EvaluationSpecModel(BaseModel):
    source_lang: str = Field(min_length=1)
    target_lang: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    split: str = Field(min_length=1)
    seed: int
    inputs: dict[str, InputDatasetModel] = Field(min_length=1)
    sampling: SamplingModel
    field_pairs: list[FieldPairModel] = Field(min_length=1)
    runtime_overrides: RunPolicyOverrideModel = Field(default_factory=RunPolicyOverrideModel)
    llm_overrides: LLMSettingsOverrideModel = Field(default_factory=LLMSettingsOverrideModel)
    prompt_overrides: PromptSettingsOverrideModel = Field(default_factory=PromptSettingsOverrideModel)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_inputs(self) -> "EvaluationSpecModel":
        if "translation" not in self.inputs:
            raise ValueError("evaluation inputs must define translation alias")
        if self.sampling.dataset not in self.inputs:
            raise ValueError(f"sampling dataset alias {self.sampling.dataset!r} is not defined")
        for field_pair in self.field_pairs:
            if field_pair.source_dataset not in self.inputs:
                raise ValueError(f"source_dataset alias {field_pair.source_dataset!r} is not defined")
            if field_pair.translation_dataset not in self.inputs:
                raise ValueError(f"translation_dataset alias {field_pair.translation_dataset!r} is not defined")
        return self
