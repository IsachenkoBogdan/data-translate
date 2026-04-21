from pydantic import BaseModel, ConfigDict, Field


class RunPolicyModel(BaseModel):
    concurrency: int = Field(ge=1)
    max_retries: int = Field(ge=0)
    retry_sleep: float = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class TranslationRunPolicyModel(RunPolicyModel):
    batch_size: int = Field(ge=1)
    max_rows_per_split: int = Field(ge=0)
    allow_errors: bool = False


class LLMRunPolicyModel(RunPolicyModel):
    requests_per_minute: int = Field(ge=0)
    max_completion_tokens: int = Field(ge=1)


class RunPolicyOverrideModel(BaseModel):
    concurrency: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    retry_sleep: float | None = Field(default=None, ge=0)
    batch_size: int | None = Field(default=None, ge=1)
    max_rows_per_split: int | None = Field(default=None, ge=0)
    allow_errors: bool | None = None
    requests_per_minute: int | None = Field(default=None, ge=0)
    max_completion_tokens: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")
