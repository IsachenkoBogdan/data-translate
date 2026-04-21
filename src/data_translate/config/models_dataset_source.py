from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class SourceSpecModel(BaseModel):
    disk_path: str = ""
    hf_dataset_id: str = ""
    hf_config: str = ""
    hf_revision: str = ""
    trust_remote_code: bool = False
    source_kind: Literal["auto", "hf", "disk"] = "auto"
    prefer_local: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_source(self) -> "SourceSpecModel":
        if self.source_kind == "hf" and not self.hf_dataset_id:
            raise ValueError("source spec with source_kind='hf' must define hf_dataset_id")
        if self.source_kind == "disk" and not self.disk_path:
            raise ValueError("source spec with source_kind='disk' must define disk_path")
        if self.source_kind == "auto" and not self.disk_path and not self.hf_dataset_id:
            raise ValueError("source spec must define disk_path or hf_dataset_id")
        if self.source_kind == "hf" and self.prefer_local:
            raise ValueError("prefer_local cannot be used with source_kind='hf'")
        return self


class ArtifactSpecModel(BaseModel):
    raw_path: str = ""
    translated_basename: str = ""
    external_root: str = ""
    results_scope: str = ""

    model_config = ConfigDict(extra="forbid")
