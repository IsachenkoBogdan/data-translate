from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_translate.config.models_dataset_source import SourceSpecModel


class QualityRuleModel(BaseModel):
    source: str = Field(min_length=1)
    target: str | None = None
    strategy: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class QualityRulesFromDatasetModel(BaseModel):
    dataset_id: str = Field(min_length=1)
    workflow: Literal["auto", "translate", "reformat"] = "auto"
    run: str = ""
    upload_id: str = ""
    upload_config: str = ""

    model_config = ConfigDict(extra="forbid")


class QualityConfigModel(BaseModel):
    quality_id: str = Field(min_length=1)
    source: SourceSpecModel
    translation: SourceSpecModel
    split_map: dict[str, str] = Field(default_factory=dict)
    rules: list[QualityRuleModel] = Field(default_factory=list)
    rules_from: QualityRulesFromDatasetModel | None = None
    allowed_extra_splits: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_rules(self) -> "QualityConfigModel":
        if bool(self.rules) == bool(self.rules_from):
            raise ValueError("quality config must define exactly one of rules or rules_from")
        return self
