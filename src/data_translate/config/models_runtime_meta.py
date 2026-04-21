from pydantic import BaseModel, ConfigDict, Field


class WorkflowMetaModel(BaseModel):
    workflow: str
    dataset_id: str | None = None
    run_name: str = "default"
    config_name: str
    config_root: str
    overrides: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ArtifactPathsModel(BaseModel):
    results_root: str
    records_path: str
    summary_path: str
    checkpoint_dir: str
    cache_dir: str
    materialized_output_path: str = ""

    model_config = ConfigDict(extra="forbid")
