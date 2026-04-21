from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BackupFieldsModel(BaseModel):
    text: str = "source_text"
    history: str = "source_history"

    model_config = ConfigDict(extra="forbid")


class ReformatRulesModel(BaseModel):
    source_dialogue_id_field: str = "dialogue_id"
    source_text_field: str = "text"
    source_history_field: str = "history"
    target_text_field: str = "text"
    target_history_field: str = "history"
    external_log_field: str = "log"
    external_turn_text_field: str = "text"
    turns_per_row: int = Field(ge=1)
    user_turn_offset: int = Field(ge=0)
    history_role_cycle: list[str] = Field(min_length=1)
    history_content_field: str = "content"
    history_role_field: str = "role"
    dialogue_id_strip_prefixes: list[str] = Field(default_factory=list)
    backup_fields: BackupFieldsModel = Field(default_factory=BackupFieldsModel)
    variant_field: str = "reformat_variant"

    model_config = ConfigDict(extra="forbid")


class ReformatSpecModel(BaseModel):
    missing_policy: Literal["skip_dialogues", "keep_source"]
    target_lang: str = Field(min_length=1)
    rules: ReformatRulesModel
    candidates: dict[str, str] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")
